import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.core.config import Config
from app.pricing.mcp_client import CalculatorMcpClient
from app.pricing.renderer import render_aws_pricing_section
from app.pricing.service import AwsPricingService


class _Result:
    def __init__(self, value):
        self.text = json.dumps(value)


class _LLM:
    def __init__(self, *values):
        self.values = list(values)

    def generate(self, *_args, **_kwargs):
        return _Result(self.values.pop(0))


class _Client:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def call(self, tool, arguments):
        self.calls.append((tool, arguments))
        if tool == "search_services":
            return [{"key": "aWSLambda", "name": "AWS Lambda"}]
        if tool == "get_service_fields":
            return {"key": "aWSLambda", "fields": [{"id": "monthlyRequests", "type": "number"}]}
        if tool == "build_estimate":
            return {"sharable_url": "https://calculator.aws/#/estimate?id=abc", "aws_estimate_id": "abc"}
        raise AssertionError(tool)


class _PricedService(AwsPricingService):
    def _read_cost(self, _url):
        return {"monthlyCost": 12.5, "monthlyByService": {"AWS Lambda": 12.5}}


class AwsPricingTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            AWS_PRICING_ENABLED=True,
            WRITER_MODEL_ID="writer",
            AWS_PRICING_COST_READER=Path("missing"),
            AWS_PRICING_NODE_BINARY="node",
            AWS_PRICING_COST_TIMEOUT_SECONDS=30,
        )
        self.requirements = {
            "aws_services": ["AWS Lambda"],
            "confirmed_aws_services": ["AWS Lambda"],
            "proposed_aws_services": [],
            "_original_objective": "AWS Lambda processes 100000 requests per month.",
        }
        self.plan = {
            "region": None,
            "services": [{
                "service_name": "AWS Lambda",
                "environment": "Production",
                "usage_facts": {"monthly requests": 100000},
                "evidence_quote": "AWS Lambda processes 100000 requests per month",
            }],
        }

    def test_missing_region_stops_before_external_calculator(self):
        service = AwsPricingService(self.config, llm=_LLM(self.plan), client_factory=lambda: self.fail("client must not run"))
        result = service.generate(self.requirements, {}, "")
        self.assertEqual(result["status"], "needs_input")
        self.assertIn("AWS region", [item["field"] for item in result["missing_inputs"]])

    def test_invented_evidence_quote_is_rejected(self):
        plan = {**self.plan, "services": [{**self.plan["services"][0], "evidence_quote": "one million requests"}]}
        service = AwsPricingService(self.config, llm=_LLM(plan), client_factory=lambda: self.fail("client must not run"))
        result = service.generate(self.requirements, {"pricing_region": "ap-south-1"}, "")
        self.assertEqual(result["status"], "needs_input")
        self.assertFalse(result["services"])

    def test_proposed_service_collection_is_an_allowed_pricing_candidate(self):
        requirements = {
            "aws_services": [],
            "confirmed_aws_services": [],
            "proposed_aws_services": ["AWS Lambda"],
            "_original_objective": "AWS Lambda processes 100000 requests per month.",
        }
        client = _Client()
        mapped = {"config": {"monthlyRequests": "100000"}, "missing_inputs": []}
        service = _PricedService(self.config, llm=_LLM(self.plan, mapped), client_factory=lambda: client)
        result = service.generate(requirements, {"pricing_region": "ap-south-1"}, "")
        self.assertEqual(result["status"], "priced")
        self.assertEqual(result["services"][0]["service"], "AWS Lambda")

    def test_service_usage_can_be_supported_across_multiple_source_passages(self):
        plan = {
            "region": None,
            "services": [{
                "service_name": "AWS Lambda",
                "environment": "Shared",
                "usage_facts": {"monthly requests": 100000, "duration ms": 250},
                "evidence_quote": "AWS Lambda processes the workload",
            }],
        }
        source = "AWS Lambda processes the workload. Monthly requests are 100000. Duration is 250 ms."
        validated = AwsPricingService._validated_plan_services(plan, ["AWS Lambda"], source)
        self.assertEqual(len(validated), 1)

    def test_invalid_region_is_rejected_before_calculator(self):
        service = AwsPricingService(
            self.config,
            llm=_LLM(self.plan),
            client_factory=lambda: self.fail("client must not run"),
        )
        result = service.generate(self.requirements, {"pricing_region": "Mumbai"}, "")
        self.assertEqual(result["status"], "needs_input")
        self.assertTrue(any("valid AWS region code" in row["reason"] for row in result["missing_inputs"]))

    def test_missing_usage_is_service_specific_not_generic_project_clarification(self):
        empty_plan = {
            "region": None,
            "services": [],
            "missing_inputs": [
                {"field": "Timeline", "reason": "Confirm project duration"},
                {"field": "Security", "reason": "Confirm compliance requirements"},
            ],
        }
        service = AwsPricingService(
            self.config,
            llm=_LLM(empty_plan),
            client_factory=lambda: self.fail("client must not run"),
        )
        result = service.generate(self.requirements, {"pricing_region": "ap-south-1"}, "")
        self.assertEqual(result["status"], "needs_input")
        self.assertEqual([row["field"] for row in result["missing_inputs"]], ["AWS Lambda usage"])
        self.assertIn("monthly invocations", result["missing_inputs"][0]["reason"])

    def test_validated_estimate_and_rendered_cost_are_returned(self):
        client = _Client()
        mapped = {"config": {"monthlyRequests": "100000"}, "missing_inputs": []}
        service = _PricedService(self.config, llm=_LLM(self.plan, mapped), client_factory=lambda: client)
        result = service.generate(
            self.requirements,
            {"pricing_region": "ap-south-1", "pricing_read_cost": True},
            "",
        )
        self.assertEqual(result["status"], "priced")
        self.assertEqual(result["monthly_cost"], 12.5)
        build = next(arguments for tool, arguments in client.calls if tool == "build_estimate")
        sent = json.loads(build["services"])
        self.assertEqual(sent[0]["config"]["region"], "ap-south-1")
        self.assertNotIn("AWS Lambda processes", sent[0]["config"]["description"])

    def test_renderer_never_asks_llm_to_calculate_arr(self):
        content = render_aws_pricing_section({
            "status": "priced",
            "estimate_url": "https://calculator.aws/#/estimate?id=abc",
            "currency": "USD",
            "monthly_cost": "12.50",
        })
        self.assertIn("| AWS ARR | USD 150.00 |", content)
        self.assertIn("calculator.aws", content)
        self.assertLess(content.index("calculator.aws"), content.index("| Item |"))

    def test_renderer_places_volume_metrics_before_cost_summary(self):
        content = render_aws_pricing_section({
            "status": "priced",
            "estimate_url": "https://calculator.aws/#/estimate?id=abc",
            "currency": "USD",
            "monthly_cost": "12.50",
            "volume_metrics": [{"metric": "Monthly conversations", "value": "100,000"}],
        })
        self.assertIn("| Metric | Estimated Volume |", content)
        self.assertLess(content.index("Estimated Volume Metrics"), content.index("AWS Cost Summary"))

    def test_renderer_blocks_stale_pricing_from_looking_current(self):
        content = render_aws_pricing_section({"status": "stale", "monthly_cost": "99.00"})
        self.assertIn("must be recalculated", content)
        self.assertNotIn("99.00", content)

    def test_volumetric_fallback_produces_a_visible_planning_range(self):
        result = AwsPricingService._with_volumetric_fallback({
            "status": "failed",
            "currency": "USD",
            "volume_metrics": [
                {"metric": "Monthly conversation volume", "value": "100,000 conversations per month"},
                {"metric": "Average message turns", "value": "6-8 turns"},
                {"metric": "Backend API call percentage", "value": "60-70%"},
            ],
        }, ["Amazon Bedrock", "AWS Lambda"], "calculator unavailable")

        self.assertEqual(result["status"], "fallback_priced")
        self.assertGreater(result["monthly_cost"], 0)
        self.assertGreater(
            result["fallback_estimate"]["monthly_high"],
            result["fallback_estimate"]["monthly_low"],
        )
        content = render_aws_pricing_section(result)
        self.assertIn("Volumetric planning range", content)
        self.assertIn("not an AWS quote", content)

    def test_partial_calculator_total_is_supplemented_not_presented_as_full_arr(self):
        result = AwsPricingService._with_volumetric_fallback({
            "status": "priced",
            "currency": "USD",
            "estimate_url": "https://calculator.aws/#/estimate?id=partial",
            "calculator_monthly_cost": 0.67,
            "calculator_priced_services": 2,
            "calculator_planned_services": 11,
            "volume_metrics": [
                {"metric": "Annual conversation volume", "value": "12 lakh conversations per year"},
                {"metric": "Average message turns", "value": "6-8 turns"},
                {"metric": "Backend API call percentage", "value": "60-70%"},
            ],
        }, ["Amazon Bedrock", "AWS Lambda"], "calculator priced 2 of 11 services")

        self.assertEqual(result["status"], "hybrid_priced")
        self.assertEqual(result["calculator_monthly_cost"], 0.67)
        self.assertGreater(result["monthly_cost"], result["calculator_monthly_cost"])
        content = render_aws_pricing_section(result)
        self.assertIn("priced subtotal (2 of 11 services)", content)
        self.assertIn("Whole-workload planning range", content)
        self.assertNotIn("AWS ARR | USD 8.04", content)

    def test_partial_calculator_without_volumetrics_never_claims_full_arr(self):
        result = AwsPricingService._with_volumetric_fallback({
            "status": "priced",
            "currency": "USD",
            "estimate_url": "https://calculator.aws/#/estimate?id=partial",
            "monthly_cost": 0.67,
            "calculator_monthly_cost": 0.67,
            "calculator_priced_services": 2,
            "calculator_planned_services": 11,
            "volume_metrics": [],
        }, ["Amazon Bedrock"], "calculator priced 2 of 11 services")
        self.assertEqual(result["status"], "partial_priced")
        self.assertIsNone(result["monthly_cost"])
        content = render_aws_pricing_section(result)
        self.assertIn("AWS Calculator priced subtotal", content)
        self.assertNotIn("AWS ARR", content)

    def test_volumetric_fallback_understands_lakh_per_year(self):
        result = AwsPricingService._with_volumetric_fallback({
            "status": "needs_input",
            "currency": "USD",
            "volume_metrics": [{
                "metric": "Annual conversation volume (design point)",
                "value": "12 lakh conversations per year",
            }],
        }, ["Amazon Bedrock"], "calculator fields incomplete")
        self.assertEqual(result["fallback_estimate"]["monthly_interactions_base"], 100000)

    def test_volumetric_fallback_understands_monthly_k_notation(self):
        result = AwsPricingService._with_volumetric_fallback({
            "status": "needs_input",
            "currency": "USD",
            "volume_metrics": [{
                "metric": "Monthly conversation volume",
                "value": "~ 50k conversations per month",
            }],
        }, ["Amazon Bedrock"], "calculator fields incomplete")
        self.assertEqual(result["fallback_estimate"]["monthly_interactions_base"], 50000)

    def test_fallback_is_not_created_without_a_source_backed_workload(self):
        original = {"status": "needs_input", "currency": "USD", "volume_metrics": []}
        result = AwsPricingService._with_volumetric_fallback(original, ["AWS Lambda"], "missing")
        self.assertIs(result, original)

    def test_source_recovers_pricing_candidates_when_objective_json_was_empty(self):
        services = AwsPricingService._candidate_services(
            {"aws_services": [], "confirmed_aws_services": [], "proposed_aws_services": []},
            {"pricing_include_proposed": True},
            "The agentic AI solution uses Amazon Redshift and requires live agent handover and observability.",
        )
        self.assertIn("Amazon Redshift", services)
        self.assertIn("Amazon Bedrock", services)
        self.assertIn("Amazon Connect", services)
        self.assertIn("Amazon CloudWatch", services)

    def test_descriptive_service_name_maps_to_calculator_service_code(self):
        self.assertEqual(
            AwsPricingService._calculator_service_code("AWS Lambda for serverless backend integrations")[0],
            "aWSLambda",
        )
        self.assertEqual(
            AwsPricingService._calculator_service_code("Amazon S3 for conversation history")[0],
            "amazonS3Standard",
        )
        self.assertEqual(
            AwsPricingService._calculator_service_code("Amazon DynamoDB for scalable state")[0],
            "dynamoDbOnDemand",
        )

    def test_service_usage_is_enriched_from_source_backed_volumetrics(self):
        service = AwsPricingService._enrich_service_with_volumetrics({
            "service_name": "AWS Lambda for serverless compute",
            "usage_facts": {"source label": "Backend integrations"},
        }, [
            {"metric": "Current monthly conversation volume", "value": "~50k conversations per month"},
            {"metric": "Average number of message turns per conversation", "value": "6-8"},
            {"metric": "Percentage of conversations requiring backend API calls", "value": "60-70%"},
            {"metric": "Number of backend API calls per transactional conversation", "value": "3"},
        ])
        self.assertEqual(service["usage_facts"]["monthly conversations (source-backed)"], 50000)
        self.assertEqual(service["usage_facts"]["derived monthly invocations"], 147500)
        self.assertTrue(service["planning_assumptions"])

    def test_enriched_lambda_uses_verified_calculator_field_contract(self):
        service = AwsPricingService._enrich_service_with_volumetrics({
            "service_name": "AWS Lambda for serverless compute",
            "usage_facts": {},
        }, [
            {"metric": "Monthly conversation volume", "value": "50,000"},
            {"metric": "Percentage requiring backend API calls", "value": "60-70%"},
            {"metric": "Number of backend API calls per transactional conversation", "value": "3"},
        ])
        config = AwsPricingService._deterministic_config("aWSLambda", service)
        self.assertEqual(config["numberOfRequests"], {"value": "147500", "unit": "perMonth"})
        self.assertEqual(config["durationOfEachRequest"], "500")
        self.assertEqual(config["sizeOfMemoryAllocated"], {"value": "512", "unit": "mb|NA"})
        self.assertEqual(config["selectArchitectureRequests"], "1")

    def test_source_backed_storage_profiles_use_child_service_fields(self):
        service = AwsPricingService._enrich_service_with_volumetrics({
            "service_name": "Amazon S3 for conversation history",
            "usage_facts": {},
        }, [{"metric": "Monthly conversation volume", "value": "50,000"}])
        self.assertEqual(
            AwsPricingService._deterministic_config("amazonS3Standard", service),
            {"s3StandardStorageSize": {"value": "15", "unit": "gb|NA"}},
        )

    def test_renderer_exposes_plain_calculator_url_on_one_line(self):
        content = render_aws_pricing_section({"status": "needs_input"})
        self.assertIn("AWS Pricing Calculator Link:** https://calculator.aws/", content)
        self.assertNotIn("](https://calculator.aws/)", content)

    def test_vendored_mcp_runtime_handshake(self):
        config = Config()
        with CalculatorMcpClient(config.AWS_PRICING_CALCULATOR_BUNDLE, timeout=15) as client:
            info = client.call("get_server_info")
        self.assertEqual(info["version"], "1.3.0")
        self.assertIn("build_estimate", info["tools"])


if __name__ == "__main__":
    unittest.main()
