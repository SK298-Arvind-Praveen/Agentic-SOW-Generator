"""
Objective Agent - Analyzes project objectives and extracts comprehensive requirements
UPDATED: Extracts all fields needed for fully dynamic template generation
"""
import json
import os
import re
import boto3
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from typing import Dict, Any
from app.core.bedrock_llm import BedrockLLM
from app.core.document_context import chunk_document
from app.core.sow_quality import merge_requirement_extractions, normalize_requirements


class ObjectiveAgent:
    """
    Agent for analyzing project objectives and extracting structured requirements.

    Extracts the full set of fields required for adaptive, objective-driven SOW generation:
    - Standard fields (key_features, aws_services, workflow_steps, etc.)
    - New fields: primary_personas, data_volume_gb, concurrent_users, deployment_environment,
      compliance_requirements, mrr_estimate, performance_requirements, accuracy_metrics
    """

    def __init__(self, config):
        self.config = config
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=config.BEDROCK_REGION,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            config=config.BOTO_CONFIG
        )
        self.llm = BedrockLLM(config, self.bedrock)

    def analyze_objective(self, objective: str, supporting_context: str = None) -> Dict[str, Any]:
        """
        Analyze the project objective and extract a comprehensive structured requirements dict.

        Args:
            objective: Project objective description
            supporting_context: Optional additional context from supporting documents

        Returns:
            Dictionary containing all analyzed requirements for template generation
        """
        objective = (objective or "").strip()
        has_supporting_context = bool((supporting_context or "").strip())
        document_only = not objective and has_supporting_context
        if document_only:
            print("📄 Empty project-details box — supporting documents are the authoritative source")
        elif not objective:
            print("⚠️  Empty objective provided — preserving the gap for clarification")

        if len(objective) < 10:
            print(f"⚠️  Very short objective ({len(objective)} chars) — analyzing without inventing scope")

        # Deterministic extraction is appropriate only when typed details are
        # the sole baseline. With an upload, typed text is generation guidance
        # and must not be directly mapped into confirmed requirements.
        print("🔍 Extracting specific data from typed baseline..." if not has_supporting_context else
              "🧭 Applying typed text as guidance over uploaded evidence...")
        extracted_data = (
            self._extract_specific_data_from_objective(objective)
            if objective and not has_supporting_context else {}
        )
        
        if extracted_data:
            print(f"✅ Found specific data in objective:")
            for key, value in extracted_data.items():
                if value:
                    print(f"   {key}: {value}")

        chunks = chunk_document(
            supporting_context or "",
            max_chars=getattr(self.config, "DOCUMENT_ANALYSIS_CHUNK_CHARS", 120_000),
            overlap_chars=getattr(self.config, "DOCUMENT_ANALYSIS_OVERLAP_CHARS", 6_000),
        )
        if not chunks:
            chunks = [""]

        if len(chunks) > 1:
            print(
                f"📚 Analysing the complete supporting corpus in {len(chunks)} "
                "overlapping evidence chunks"
            )

        extractions = []
        worker_count = min(4, len(chunks))
        with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="requirements") as executor:
            futures = {
                executor.submit(
                    copy_context().run,
                    self._analyze_chunk,
                    objective,
                    chunk,
                    index,
                    len(chunks),
                ): index
                for index, chunk in enumerate(chunks, 1)
            }
            ordered: Dict[int, Dict[str, Any]] = {}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    parsed = future.result()
                    if parsed:
                        ordered[index] = parsed
                except Exception as exc:
                    print(f"⚠ Requirements chunk {index}/{len(chunks)} failed: {exc}")
            extractions = [ordered[index] for index in sorted(ordered)]

        if extractions:
            requirements = merge_requirement_extractions(extractions)
            print(f"✅ ObjectiveAgent: merged {len(extractions)}/{len(chunks)} complete-document analyses")
        else:
            print("❌ ObjectiveAgent: no valid analysis JSON — using fallback")
            requirements = self._get_fallback_requirements(objective, supporting_context)

        # ✅ NEW: Override LLM-generated data with user-provided specific data
        if extracted_data:
            print("🔄 Overriding LLM data with user-provided specific data...")
            requirements = self._merge_extracted_data(requirements, extracted_data)

        # Ensure all required fields are present (fill gaps with defaults)
        requirements = self._ensure_complete_fields(
            requirements,
            "" if has_supporting_context else objective,
        )
        if objective:
            requirements["_generation_guidance"] = objective

        # ✅ NEW: Override UI detection if negative context is present
        negative_indicators = [
            "no user interface", "without user interface", "no frontend", "without frontend",
            "no web interface", "without web interface", "no dashboard", "without dashboard",
            "no web application", "without web application", "no portal", "without portal",
            "no screen", "without screen", "no screens", "without screens",
            "no visualization", "without visualization", "backend-only", "api-only",
            "without any", "no ui", "without ui"
        ]
        
        objective_lower = objective.lower()
        has_negative_context = any(neg in objective_lower for neg in negative_indicators)
        
        if has_negative_context and requirements.get('ui_required', False):
            print("🔄 Overriding UI requirement due to negative context in objective")
            requirements['ui_required'] = False

        self._log_analysis_summary(requirements)
        return requirements

    def _analyze_chunk(
        self,
        objective: str,
        supporting_context: str,
        index: int,
        total: int,
    ) -> Dict[str, Any]:
        chunk_context = supporting_context
        if total > 1:
            chunk_context = (
                f"SUPPORTING CORPUS PART {index} OF {total}. Extract every fact present in "
                "this part. Do not interpret absence from this part as absence from the complete corpus.\n\n"
                f"{supporting_context}"
            )
        prompt = self._build_analysis_prompt(objective, chunk_context)
        result = self.llm.generate(
            prompt,
            task="analysis",
            max_tokens=min(getattr(self.config, "MAX_TOKENS", 8192), 8192),
            temperature=getattr(self.config, "TEMPERATURE", 0.2),
            call_name=f"Objective Analysis {index}/{total}",
            fallback_model_id=getattr(self.config, "WRITER_MODEL_ID", None),
        )
        return self._parse_json(result.text)

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        raw = (content or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I)
        start = raw.find("{")
        if start < 0:
            return {}

        candidates = [raw[start:]]
        balanced = ObjectiveAgent._balanced_json_object(raw, start)
        if balanced:
            candidates.insert(0, balanced)
        repaired = ObjectiveAgent._close_truncated_json(raw[start:])
        if repaired:
            candidates.append(repaired)
        complete_members = ObjectiveAgent._truncate_to_complete_members(raw[start:])
        if complete_members:
            candidates.append(complete_members)

        last_error = None
        seen = set()
        for candidate in candidates:
            candidate = re.sub(r",\s*([}\]])", r"\1", candidate.strip())
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                value = json.loads(candidate, strict=False)
                if isinstance(value, dict):
                    if candidate != raw[start:]:
                        print("[OBJECTIVE][JSON] Recovered a wrapped or truncated JSON response", flush=True)
                    return value
            except json.JSONDecodeError as exc:
                last_error = exc
        if last_error:
            print(
                f"[OBJECTIVE][JSON] Could not recover response: {last_error.msg} "
                f"at character {last_error.pos}/{len(raw)}",
                flush=True,
            )
        return {}

    @staticmethod
    def _balanced_json_object(text: str, start: int) -> str:
        stack = []
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in "[{":
                stack.append(char)
            elif char in "]}":
                if not stack:
                    return ""
                expected = "[" if char == "]" else "{"
                if stack[-1] != expected:
                    return ""
                stack.pop()
                if not stack:
                    return text[start:index + 1]
        return ""

    @staticmethod
    def _close_truncated_json(text: str) -> str:
        """Close an otherwise valid top-level response cut off by token output."""
        start = text.find("{")
        if start < 0:
            return ""
        value = text[start:].strip()
        stack = []
        in_string = False
        escaped = False
        for char in value:
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in "[{":
                stack.append(char)
            elif char in "]}" and stack:
                expected = "[" if char == "]" else "{"
                if stack[-1] != expected:
                    return ""
                stack.pop()
        if not stack:
            return value
        if in_string:
            if escaped:
                value += "\\"
            value += '"'
        value = re.sub(r",\s*$", "", value)
        if re.search(r":\s*$", value):
            value += "null"
        value += "".join("]" if char == "[" else "}" for char in reversed(stack))
        return value

    @staticmethod
    def _truncate_to_complete_members(text: str) -> str:
        """Salvage completed top-level fields when truncation cuts a key/value."""
        start = text.find("{")
        if start < 0:
            return ""
        stack = []
        in_string = False
        escaped = False
        last_top_level_comma = None
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char in "[{":
                stack.append(char)
            elif char in "]}" and stack:
                stack.pop()
            elif char == "," and stack == ["{"]:
                last_top_level_comma = index
        if last_top_level_comma is None:
            return ""
        return text[start:last_top_level_comma].rstrip() + "}"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_analysis_prompt(self, objective: str, supporting_context: str = None) -> str:
        objective = (objective or "").strip()
        has_objective = bool(objective)
        has_supporting_context = bool((supporting_context or "").strip())
        context_section = ""
        if supporting_context:
            context_section = f"""

SOURCE 1 - SUPPORTING DOCUMENT CORPUS (primary factual and scope authority):
The following extracted documents provide requirements and project context:

{supporting_context}

Extract the complete named workflows, modules, deliverables, requirements, systems, roles,
data fields, rules, dependencies, exclusions, and acceptance evidence. Preserve identifiers,
numbers, and customer terminology. Do not replace specifics with generic summaries.
"""

        guidance_section = objective if has_objective else "(No additional generation guidance supplied.)"
        typed_baseline = objective if has_objective else "(No typed project details supplied.)"

        source_intro = (
            f"""{context_section}

USER GENERATION GUIDANCE (applies across the complete SOW):
{guidance_section}

Treat this as instructions for interpreting and presenting the uploaded evidence, not as a
replacement factual objective. It may prioritise deliverables, exclude or defer capabilities,
change scope treatment, or specify tone and structure. Follow explicit instructions such as
moving a document capability to future scope, while preserving traceability to the document.
Do not convert casual guidance into an unstated customer fact."""
            if has_supporting_context else
            f"""SOURCE 1 - TYPED PROJECT DETAILS (primary source because no document was uploaded):
{typed_baseline}"""
        )

        return f"""You are the requirements analyst for a professional AWS Statement of Work.

{source_intro}

Extract facts and produce a useful solution hypothesis, while keeping the two separate.
Never turn an absent number, integration, compliance framework, service, SLA, date, data
volume, user count, or accuracy threshold into a confirmed requirement. Use null or [] for
unknown facts. Recommended architecture belongs in proposed_aws_services or
planning_assumptions. Do not invent facts about the customer.

Evidence-status rule: an uploaded document can contain questions, vendor responses, assumptions
and proposals as well as facts. Preserve explicit labels such as "Assumption", "Derived",
"Proposed", "To be confirmed", "Not stated", "Needs clarification", "optional" and "future".
Do not promote those statements to confirmed requirements. If two uploaded sources disagree,
record the conflict in open_clarifications and retain both qualified positions.

Return one valid JSON object using this contract:
{{
  "project_overview": "2-4 factual sentences grounded in the source",
  "business_problem": "problem and operational impact stated or directly implied",
  "desired_outcomes": ["outcome"],
  "current_state": ["known current-state fact"],
  "key_features": ["functional capability"],
  "functional_requirements": ["testable functional requirement"],
  "non_functional_requirements": ["only explicitly supplied constraints"],
  "confirmed_aws_services": ["only services named in a source"],
  "proposed_aws_services": ["architectural recommendations, kept distinct from facts"],
  "aws_services": ["deduplicated union of confirmed and proposed services"],
  "architecture_components": ["logical component or layer"],
  "workflow_steps": ["ordered end-to-end step"],
  "use_cases": ["specific scenario"],
  "primary_personas": ["role - responsibility"],
  "data_sources": ["source and owner if known"],
  "data_characteristics": {{"volume": null, "format": null, "access_pattern": null, "retention": null, "classification": null}},
  "data_volume_gb": null,
  "concurrent_users": null,
  "deployment_environment": null,
  "integration_details": ["system/interface/auth/owner if known"],
  "security_requirements": ["only stated controls"],
  "compliance_requirements": ["only stated frameworks"],
  "performance_requirements": ["only stated SLOs or constraints"],
  "accuracy_metrics": {{"target_percentage": null, "measurement_method": null, "domain_constraints": null}},
  "success_metrics": ["source-grounded measurable metric; omit invented targets"],
  "key_deliverables": ["explicit or directly implied deliverable"],
  "timeline": null,
  "duration_weeks": null,
  "budget_monthly": null,
  "mrr_estimate": null,
  "ui_required": false,
  "industry": "financial_services|healthcare|retail_ecommerce|manufacturing|technology|government|education|media_entertainment|generic",
  "confirmed_requirements": {{"field": "source-grounded value"}},
  "planning_assumptions": ["clearly labelled assumption used to make the draft actionable"],
  "open_clarifications": ["material question whose answer affects scope, design, schedule, cost, or acceptance"],
  "source_basis": ["User product details", "supporting document name or type"],
  "requirements_provenance": {{"field": "confirmed|inferred|proposed|unknown"}}
}}

Rules:
- ui_required is true only for an explicitly positive UI/dashboard/portal requirement.
- Do not automatically add CloudWatch, CloudTrail, IAM, KMS, Lambda, S3, or any other service.
- Proposed services must be justified by the workflow and presented as proposed.
- When supporting documents are supplied, their explicit facts, scope and deliverables are
  authoritative. User guidance controls prioritisation, inclusion, deferral and presentation;
  it does not silently replace the evidence baseline.
- Do not infer a current-state shortcoming solely from a requested target capability. A requested
  feature proves desired scope, not that the existing platform lacks it.
- Preserve each source-required contractual output in key_deliverables, but do not imply that every
  output must become a separate top-level architectural delivery package.
- Extract all useful detail from short input, but express unknowns as clarifications rather than fake precision.
- Respond with JSON only, beginning with {{ and ending with }}.
"""

    def _ensure_complete_fields(self, req: Dict[str, Any], objective: str) -> Dict[str, Any]:
        """
        Fill structural gaps without converting unknowns into commitments.
        """
        return normalize_requirements(req, objective=objective, mode="POC")

    def _log_analysis_summary(self, req: Dict[str, Any]) -> None:
        print("\n📊 Objective Analysis Summary:")
        print(f"  Industry:          {req.get('industry', 'unknown')}")
        print(f"  UI Required:       {req.get('ui_required', False)}")
        print(f"  Deployment:        {req.get('deployment_environment', 'unknown')}")
        print(f"  Data Volume:       {req.get('data_volume_gb', '?')} GB")
        print(f"  Concurrent Users:  {req.get('concurrent_users', '?')}")
        print(f"  AWS Services:      {len(req.get('aws_services', []))} services")
        print(f"  Integrations:      {len(req.get('integration_details', []))} external systems")
        print(f"  Compliance:        {req.get('compliance_requirements', []) or 'None'}")
        print(f"  Workflow Steps:    {len(req.get('workflow_steps', []))} steps")
        print(f"  Personas:          {len(req.get('primary_personas', []))} roles")
        mrr = req.get('mrr_estimate')
        print(f"  MRR Estimate:      {f'${mrr:,}/month' if isinstance(mrr, (int, float)) else 'not provided'}")
        print(f"  Accuracy Target:   {req.get('accuracy_metrics', {}).get('target_percentage', '?')}%\n")

    def _get_fallback_requirements(
        self, objective: str, supporting_context: str = None
    ) -> Dict[str, Any]:
        """
        Minimal fallback requirements when AI analysis fails entirely.
        All downstream code must handle these defaults gracefully.
        """
        source_lines = [
            re.sub(r"\s+", " ", line).strip(" |-:")
            for line in str(supporting_context or "").splitlines()
            if line.strip() and not re.fullmatch(r"[-= ]+", line.strip())
        ]
        specific_lines = []
        for line in source_lines:
            lowered = line.casefold()
            if any(token in lowered for token in (
                "requirement", "deliverable", "module", "workflow", "acceptance",
                "output", "must", "shall", "integration", "data",
            )):
                specific_lines.append(line)
        overview = (
            " ".join(source_lines[:3])[:1200]
            if supporting_context
            else f"The stated project need is: {objective}"
        )
        return normalize_requirements({
            "project_overview": overview,
            "functional_requirements": specific_lines[:30],
            "key_deliverables": specific_lines[:20],
            "source_basis": ["Supporting document corpus"] if supporting_context else ["User product details"],
            "requirements_provenance": {"project_overview": "confirmed"},
            "planning_assumptions": [
                "The draft will use a proposed AWS architecture until discovery confirms the target environment and constraints."
            ],
            "open_clarifications": [
                "Functional scope and prioritized user journeys must be confirmed because automated requirements analysis was unavailable."
            ],
            "industry": "generic",
            "ui_required": False,
            "_generation_guidance": objective if objective else "",
        }, objective="" if supporting_context else objective, mode="POC")
    def _extract_specific_data_from_objective(self, objective: str) -> Dict[str, Any]:
        """
        Extract specific data like pricing, timelines, SKUs, etc. from the objective text
        
        Args:
            objective: The user's project objective text
            
        Returns:
            Dictionary containing extracted specific data
        """
        import re
        
        extracted = {}
        objective_lower = objective.lower()
        
        # Extract pricing information
        pricing_patterns = [
            r'\$\s*(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:per\s+month|monthly|/month|mrr)',
            r'(\d+(?:,\d{3})*(?:\.\d{2})?)\s*(?:dollars?|usd)\s*(?:per\s+month|monthly|/month)',
            r'budget\s*(?:of|is|:)?\s*\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'cost\s*(?:of|is|:)?\s*\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'price\s*(?:of|is|:)?\s*\$?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)'
        ]
        
        for pattern in pricing_patterns:
            matches = re.findall(pattern, objective_lower)
            if matches:
                # Clean up the price (remove commas, convert to float)
                price_str = matches[0].replace(',', '')
                try:
                    price = float(price_str)
                    extracted['monthly_budget'] = price
                    extracted['pricing_info'] = f"${price:,.2f}/month"
                    break
                except ValueError:
                    continue
        
        # Extract timeline information
        timeline_patterns = [
            # Range patterns first (more specific)
            r'(\d+)\s*[-–]\s*(\d+)\s*(weeks?|wks?)',
            r'(\d+)\s*[-–]\s*(\d+)\s*(months?|mos?)',
            r'(\d+)\s*[-–]\s*(\d+)\s*(days?)',
            r'timeline\s*(?:of|is|:)?\s*(\d+)\s*[-–]\s*(\d+)\s*(weeks?|months?|days?)',
            r'duration\s*(?:of|is|:)?\s*(\d+)\s*[-–]\s*(\d+)\s*(weeks?|months?|days?)',
            r'complete\s*(?:in|within)?\s*(\d+)\s*[-–]\s*(\d+)\s*(weeks?|months?|days?)',
            # Single number patterns
            r'(\d+)\s*(weeks?|wks?)',
            r'(\d+)\s*(months?|mos?)',
            r'(\d+)\s*(days?)',
            r'timeline\s*(?:of|is|:)?\s*(\d+)\s*(weeks?|months?|days?)',
            r'duration\s*(?:of|is|:)?\s*(\d+)\s*(weeks?|months?|days?)',
            r'complete\s*(?:in|within)?\s*(\d+)\s*(weeks?|months?|days?)'
        ]
        
        timeline_info = []
        for pattern in timeline_patterns:
            matches = re.findall(pattern, objective_lower)
            if matches:
                for match in matches:
                    try:
                        if len(match) == 3:  # Range pattern (min, max, unit)
                            min_duration = int(match[0])
                            max_duration = int(match[1])
                            unit = match[2]
                            
                            if 'week' in unit:
                                timeline_info.append(f"{min_duration}-{max_duration} weeks")
                            elif 'month' in unit:
                                timeline_info.append(f"{min_duration}-{max_duration} months")
                            elif 'day' in unit:
                                timeline_info.append(f"{min_duration}-{max_duration} days")
                        elif len(match) == 2:  # Single number pattern (number, unit)
                            duration = int(match[0])
                            unit = match[1]
                            
                            if 'week' in unit:
                                timeline_info.append(f"{duration} weeks")
                            elif 'month' in unit:
                                timeline_info.append(f"{duration} months")
                            elif 'day' in unit:
                                timeline_info.append(f"{duration} days")
                    except (ValueError, IndexError):
                        continue
                
                # Break after first successful pattern match
                if timeline_info:
                    break
        
        if timeline_info:
            extracted['timeline_info'] = timeline_info
            extracted['project_duration'] = timeline_info[0]  # Use first found
        
        # Extract team size information
        team_patterns = [
            r'(\d+)\s*(?:developers?|devs?)',
            r'(\d+)\s*(?:engineers?)',
            r'(\d+)\s*(?:people|persons?|team\s*members?)',
            r'team\s*(?:of|size)?\s*(\d+)',
            r'(\d+)\s*(?:resources?|staff)'
        ]
        
        for pattern in team_patterns:
            matches = re.findall(pattern, objective_lower)
            if matches:
                try:
                    team_size = int(matches[0])
                    extracted['team_size'] = team_size
                    extracted['team_info'] = f"{team_size} team members"
                    break
                except ValueError:
                    continue
        
        # Extract technology/platform information
        tech_keywords = {
            'aws_services': [
                # Core compute services
                'lambda', 'ec2', 'ecs', 'fargate', 'batch',
                # Storage services
                's3', 'efs', 'fsx', 'storage gateway',
                # Database services
                'dynamodb', 'rds', 'aurora', 'redshift', 'documentdb', 'neptune', 'timestream',
                # AI/ML services
                'bedrock', 'sagemaker', 'comprehend', 'textract', 'rekognition', 'polly', 'transcribe', 'translate', 'lex', 'kendra', 'personalize',
                # Analytics services
                'kinesis', 'glue', 'athena', 'quicksight', 'emr', 'msk', 'opensearch',
                # Integration services
                'api gateway', 'step functions', 'eventbridge', 'sqs', 'sns', 'mq', 'appflow',
                # Security services
                'iam', 'cognito', 'secrets manager', 'kms', 'waf', 'shield', 'guardduty', 'inspector', 'macie',
                # Monitoring services
                'cloudwatch', 'cloudtrail', 'x-ray', 'config', 'systems manager',
                # Networking services
                'vpc', 'cloudfront', 'route 53', 'elb', 'alb', 'nlb', 'direct connect', 'vpn',
                # Developer tools
                'codecommit', 'codebuild', 'codedeploy', 'codepipeline', 'cloud9', 'codestar',
                # Application services
                'amplify', 'appsync', 'pinpoint', 'ses', 'workspaces', 'appstream',
                # Alternative names and variations
                'textextract', 'amazon textract', 'amazon bedrock', 'amazon s3', 'amazon dynamodb',
                'amazon rds', 'amazon lambda', 'amazon api gateway', 'amazon cloudfront',
                'amazon sqs', 'amazon sns', 'amazon kinesis', 'amazon redshift'
            ],
            'programming_languages': ['python', 'javascript', 'java', 'node.js', 'react', 'angular', 'vue', 'typescript', 'go', 'rust', 'c#', 'php'],
            'databases': ['dynamodb', 'rds', 'mongodb', 'postgresql', 'mysql', 'aurora', 'redshift', 'documentdb', 'neptune'],
            'ai_ml': ['machine learning', 'artificial intelligence', 'ai', 'ml', 'bedrock', 'sagemaker', 'textract', 'textextract', 'comprehend', 'rekognition', 'deep learning', 'neural network']
        }
        
        found_tech = {}
        for category, keywords in tech_keywords.items():
            found = []
            for kw in keywords:
                if kw in objective_lower:
                    # Normalize service names (remove "amazon " prefix, handle variations)
                    normalized_kw = kw.replace('amazon ', '').replace('textextract', 'textract')
                    if normalized_kw not in found:
                        found.append(normalized_kw)
            if found:
                found_tech[category] = found
        
        if found_tech:
            extracted['technology_stack'] = found_tech
        
        # Extract specific deliverables mentioned
        deliverable_patterns = [
            r'(?:deliver|build|create|develop)\s+([^.!?]+?)(?:\.|!|\?|$)',
            r'(?:deliverables?|outputs?)\s*(?:include|are|:)\s*([^.!?]+?)(?:\.|!|\?|$)'
        ]
        
        deliverables = []
        for pattern in deliverable_patterns:
            matches = re.findall(pattern, objective, re.IGNORECASE)
            deliverables.extend([match.strip() for match in matches if len(match.strip()) > 10])
        
        if deliverables:
            extracted['specific_deliverables'] = deliverables[:3]  # Limit to first 3
        
        # Extract compliance/security requirements
        compliance_keywords = ['gdpr', 'hipaa', 'sox', 'pci', 'compliance', 'security', 'encryption', 'audit']
        found_compliance = [kw for kw in compliance_keywords if kw in objective_lower]
        if found_compliance:
            extracted['compliance_requirements'] = found_compliance
        
        # Extract data volume information
        data_patterns = [
            # Direct storage sizes
            r'(\d+(?:\.\d+)?)\s*(?:gb|gigabytes?)',
            r'(\d+(?:\.\d+)?)\s*(?:tb|terabytes?)',
            r'(\d+(?:\.\d+)?)\s*(?:mb|megabytes?)',
            # Simple record counts
            r'(\d+(?:,\d{3})*)\s*(?:records?|rows?|documents?)',
            # Invoice/document volume patterns with ranges
            r'(\d+(?:,\d{3})*)\s*[–-]\s*(\d+(?:,\d{3})*)\s*(?:medical\s*claim\s*)?(?:invoices?|documents?|files?)\s*(?:per\s+month|monthly|/month)',
            r'(\d+(?:,\d{3})*[–-]\d+(?:,\d{3})*)\s*(?:invoices?|documents?|files?)\s*(?:per\s+month|monthly|/month)',
            r'process(?:ing)?\s*(?:approximately\s*)?(\d+(?:,\d{3})*[–-]\d+(?:,\d{3})*)\s*(?:medical\s*claim\s*)?(?:invoices?|documents?|files?)',
            # Range patterns with dashes (both en-dash and hyphen)
            r'(\d+(?:,\d{3})*)\s*[–-]\s*(\d+(?:,\d{3})*)\s*(?:invoices?|documents?|files?|records?)',
            # SKU/item patterns
            r'(\d+(?:,\d{3})*[–-]\d+(?:,\d{3})*)\s*(?:skus?|items?|products?)',
            # Line item patterns
            r'(\d+(?:,\d{3})*[–-]\d+(?:,\d{3})*)\s*(?:line\s*items?|product\s*line\s*items?)'
        ]
        
        for pattern in data_patterns:
            matches = re.findall(pattern, objective_lower)
            if matches:
                try:
                    if isinstance(matches[0], tuple) and len(matches[0]) == 2:
                        # Handle range patterns (min, max)
                        volume_min = matches[0][0].replace(',', '') if matches[0][0] else '0'
                        volume_max = matches[0][1].replace(',', '') if matches[0][1] else volume_min
                        volume_desc = f"{matches[0][0]}–{matches[0][1]}"
                    else:
                        # Handle single values or ranges in one string
                        volume_str = matches[0].replace(',', '')
                        if '–' in volume_str or '-' in volume_str:
                            # Range in single string
                            range_parts = re.split(r'[–-]', volume_str)
                            volume_min = range_parts[0]
                            volume_max = range_parts[1] if len(range_parts) > 1 else range_parts[0]
                            volume_desc = matches[0]
                        else:
                            volume_min = volume_max = volume_str
                            volume_desc = matches[0]
                    
                    # Determine data type and estimate storage
                    if 'gb' in pattern or 'tb' in pattern or 'mb' in pattern:
                        if 'gb' in pattern:
                            extracted['data_volume'] = f"{volume_desc} GB"
                        elif 'tb' in pattern:
                            extracted['data_volume'] = f"{volume_desc} TB"
                        elif 'mb' in pattern:
                            extracted['data_volume'] = f"{volume_desc} MB"
                    elif 'invoice' in pattern or 'document' in pattern or 'file' in pattern:
                        # Estimate storage for documents (assume ~1-3MB per document)
                        avg_volume = (int(volume_min) + int(volume_max)) / 2
                        estimated_gb = (avg_volume * 2) / 1024  # 2MB average per document
                        extracted['data_volume'] = f"{estimated_gb:.1f} GB"
                        extracted['document_volume'] = f"{volume_desc} documents/month"
                        print(f"   ✅ Detected document volume: {volume_desc} documents/month")
                    elif 'records' in pattern or 'rows' in pattern:
                        extracted['data_records'] = f"{volume_desc} records"
                        # Estimate storage for records (assume ~1KB per record)
                        avg_volume = (int(volume_min) + int(volume_max)) / 2
                        estimated_gb = (avg_volume * 0.001) / 1024  # 1KB per record
                        extracted['data_volume'] = f"{max(0.1, estimated_gb):.1f} GB"
                    elif 'sku' in pattern or 'item' in pattern or 'product' in pattern:
                        extracted['sku_count'] = f"{volume_desc} SKUs"
                    
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract UI requirements - only when explicitly mentioned
        # More specific patterns that indicate explicit UI requirements
        ui_explicit_patterns = [
            r'build.*(?:web interface|user interface|frontend|dashboard|portal|web app)',
            r'create.*(?:web interface|user interface|frontend|dashboard|portal|web app)',
            r'develop.*(?:web interface|user interface|frontend|dashboard|portal|web app)',
            r'need.*(?:web interface|user interface|frontend|dashboard|portal|web app)',
            r'require.*(?:web interface|user interface|frontend|dashboard|portal|web app)',
            r'want.*(?:web interface|user interface|frontend|dashboard|portal|web app)',
            r'(?:web interface|user interface|frontend|dashboard|portal|web app).*(?:for|to)',
            r'(?:react|angular|vue|next\.js|nuxt).*(?:app|application|interface)',
            r'web-based.*(?:interface|application|portal|dashboard)',
            r'browser-based.*(?:interface|application|portal|dashboard)',
            r'admin panel',
            r'management console',
            r'interactive.*(?:web|browser|ui|interface)',
            r'graphical.*(?:interface|ui)',
            r'client.*(?:interface|portal|dashboard)',
            r'web.*ui',
            r'ui.*(?:component|development|implementation)',
            r'frontend.*(?:component|development|implementation)'
        ]
        
        ui_found = any(re.search(pattern, objective_lower) for pattern in ui_explicit_patterns)
        if ui_found:
            extracted['ui_required'] = True
            print(f"   ✅ Detected explicit UI requirement in objective")
        
        # Extract key features mentioned in objective
        feature_keywords = {
            'document_processing': ['document processing', 'document ingestion', 'file processing'],
            'data_extraction': ['data extraction', 'text extraction', 'information extraction'],
            'analytics': ['analytics', 'reporting', 'dashboards', 'insights'],
            'cost_analysis': ['cost analysis', 'cost comparison', 'pricing analysis', 'billing analysis'],
            'anomaly_detection': ['anomaly detection', 'outlier detection', 'fraud detection'],
            'automated_processing': ['automated', 'automation', 'auto-processing'],
            'benchmarking': ['benchmarking', 'comparison', 'baseline analysis'],
            'claim_processing': ['claim processing', 'claims management', 'claim validation']
        }
        
        detected_features = []
        for feature_name, keywords in feature_keywords.items():
            if any(keyword in objective_lower for keyword in keywords):
                detected_features.append(feature_name.replace('_', ' ').title())
        
        if detected_features:
            extracted['key_features_detected'] = detected_features
            print(f"   ✅ Detected key features: {', '.join(detected_features)}")
        
        return extracted

    def _merge_extracted_data(self, requirements: Dict[str, Any], extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge extracted specific data with LLM-generated requirements
        
        Args:
            requirements: LLM-generated requirements
            extracted_data: User-provided specific data from objective
            
        Returns:
            Merged requirements with user data taking precedence
        """
        merged = requirements.copy()
        
        # Override pricing information
        if 'monthly_budget' in extracted_data:
            merged['budget_monthly'] = extracted_data['monthly_budget']
            merged['budget_total'] = extracted_data['monthly_budget'] * 12  # Assume 12 months
            print(f"   ✅ Using user-provided budget: ${extracted_data['monthly_budget']:,.2f}/month")
        
        if 'pricing_info' in extracted_data:
            merged['pricing_details'] = extracted_data['pricing_info']
        
        # Override timeline information
        if 'project_duration' in extracted_data:
            merged['timeline'] = extracted_data['project_duration']
            merged['duration_weeks'] = self._parse_duration_to_weeks(extracted_data['project_duration'])
            print(f"   ✅ Using user-provided timeline: {extracted_data['project_duration']}")
        
        if 'timeline_info' in extracted_data:
            merged['timeline_details'] = extracted_data['timeline_info']
        
        # Override team information
        if 'team_size' in extracted_data:
            merged['team_size'] = extracted_data['team_size']
            merged['resource_allocation'] = f"{extracted_data['team_size']} team members"
            print(f"   ✅ Using user-provided team size: {extracted_data['team_size']} members")
        
        # Override technology stack
        if 'technology_stack' in extracted_data:
            tech_stack = extracted_data['technology_stack']
            if 'aws_services' in tech_stack:
                # Merge user-specified AWS services with LLM-generated ones
                existing_services = merged.get('aws_services', [])
                user_services = tech_stack['aws_services']
                
                # Normalize and deduplicate services
                normalized_existing = [svc.lower().replace('amazon ', '').replace('textextract', 'textract') for svc in existing_services]
                
                # Add user services that aren't already present (case-insensitive, normalized)
                for service in user_services:
                    normalized_service = service.lower().replace('amazon ', '').replace('textextract', 'textract')
                    if normalized_service not in normalized_existing:
                        existing_services.append(service)
                        normalized_existing.append(normalized_service)
                
                merged['aws_services'] = existing_services
                print(f"   ✅ Enhanced AWS services with user-specified: {', '.join(user_services)}")
            
            if 'programming_languages' in tech_stack:
                merged['technical_stack'] = tech_stack['programming_languages']
                print(f"   ✅ Using user-specified tech stack: {', '.join(tech_stack['programming_languages'])}")
        
        # Override deliverables
        if 'specific_deliverables' in extracted_data:
            merged['key_deliverables'] = extracted_data['specific_deliverables']
            merged['deliverables_user_specified'] = True
            print(f"   ✅ Using user-specified deliverables: {len(extracted_data['specific_deliverables'])} items")
        
        # Override compliance requirements
        if 'compliance_requirements' in extracted_data:
            merged['compliance_requirements'] = extracted_data['compliance_requirements']
            print(f"   ✅ Using user-specified compliance: {', '.join(extracted_data['compliance_requirements'])}")
        
        # Override data volume - preserve original format when possible
        if 'data_volume' in extracted_data:
            # Only convert to GB if the original was already in storage units
            original_volume = extracted_data['data_volume']
            if any(unit in original_volume.lower() for unit in ['gb', 'tb', 'mb']):
                merged['data_volume_gb'] = self._parse_data_volume_to_gb(original_volume)
            else:
                # Keep original format for document counts
                merged['data_volume_description'] = original_volume
                merged['data_volume_gb'] = None
            print(f"   ✅ Using user-specified data volume: {original_volume}")
        
        if 'invoice_volume' in extracted_data:
            merged['invoice_volume'] = extracted_data['invoice_volume']
            print(f"   ✅ Using user-specified invoice volume: {extracted_data['invoice_volume']}")
        
        if 'document_volume' in extracted_data:
            merged['document_volume'] = extracted_data['document_volume']
            print(f"   ✅ Using user-specified document volume: {extracted_data['document_volume']}")
        
        if 'sku_count' in extracted_data:
            merged['sku_count'] = extracted_data['sku_count']
            print(f"   ✅ Using user-specified SKU count: {extracted_data['sku_count']}")
        
        if 'data_records' in extracted_data:
            merged['data_records_count'] = extracted_data['data_records']
        
        # Override UI requirements
        if 'ui_required' in extracted_data:
            merged['ui_required'] = extracted_data['ui_required']
            print(f"   ✅ Using user-specified UI requirement: {extracted_data['ui_required']}")
        
        # Override key features
        if 'key_features_detected' in extracted_data:
            # Merge detected features with LLM-generated ones
            existing_features = merged.get('key_features', [])
            detected_features = extracted_data['key_features_detected']
            
            # Add detected features that aren't already present
            for feature in detected_features:
                if not any(feature.lower() in existing.lower() for existing in existing_features):
                    existing_features.append(feature)
            
            merged['key_features'] = existing_features
            print(f"   ✅ Enhanced key features with detected items: {', '.join(detected_features)}")
        
        # Add flag to indicate user data was used
        merged['user_data_extracted'] = True
        merged['extracted_data_summary'] = {k: v for k, v in extracted_data.items() if v}
        
        return merged

    def _parse_duration_to_weeks(self, duration_str: str):
        """Parse duration string to weeks"""
        import re
        
        duration_lower = duration_str.lower()
        
        # Handle ranges like "6-8 weeks", "8-12 weeks"
        range_match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*(weeks?|months?|days?)', duration_lower)
        if range_match:
            min_num = int(range_match.group(1))
            max_num = int(range_match.group(2))
            unit = range_match.group(3)
            
            # Use the maximum value from the range for production planning
            number = max_num
            
            if 'week' in unit:
                return number
            elif 'month' in unit:
                return number * 4  # 4 weeks per month
            elif 'day' in unit:
                return max(1, number // 7)  # Convert days to weeks
        
        # Extract single number and unit
        match = re.search(r'(\d+)\s*(weeks?|months?|days?)', duration_lower)
        if not match:
            return None
        
        number = int(match.group(1))
        unit = match.group(2)
        
        if 'week' in unit:
            return number
        elif 'month' in unit:
            return number * 4  # 4 weeks per month
        elif 'day' in unit:
            return max(1, number // 7)  # Convert days to weeks
        
        return None

    def _parse_data_volume_to_gb(self, volume_str: str) -> float:
        """Parse data volume string to GB"""
        import re
        
        volume_lower = volume_str.lower()
        
        # Extract number and unit
        match = re.search(r'(\d+(?:\.\d+)?)\s*(gb|tb|mb)', volume_lower)
        if not match:
            return None
        
        number = float(match.group(1))
        unit = match.group(2)
        
        if unit == 'gb':
            return number
        elif unit == 'tb':
            return number * 1024  # TB to GB
        elif unit == 'mb':
            return number / 1024  # MB to GB
        
        return None
