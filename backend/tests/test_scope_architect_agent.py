import json
from types import SimpleNamespace

from app.agents.scope_architect_agent import ScopeArchitectAgent
from app.core.graph import create_fast_preview_graph, create_graph, create_preview_graph
from app.core.nodes import scope_architecture_node


def _agent(*responses):
    values = iter(json.dumps(value) for value in responses)
    return ScopeArchitectAgent(
        SimpleNamespace(ANALYSIS_MODEL_ID="analysis", WRITER_MODEL_ID="writer"),
        call_fn=lambda *_args, **_kwargs: next(values),
    )


def test_architect_repairs_missing_capability_assignment():
    inventory = {"capability_units": [
        {"id": "CAP-001", "name": "Ticket routing"},
        {"id": "CAP-002", "name": "Agent handover"},
    ]}
    incomplete = {"deliverables": [{
        "name": "Support platform",
        "modules": [{"name": "Ticket routing", "capability_ids": ["CAP-001"]}],
    }]}
    repaired = {"deliverables": [{
        "name": "Support platform",
        "separation_basis": "One release and acceptance boundary",
        "modules": [
            {"name": "Ticket routing", "capability_ids": ["CAP-001"]},
            {"name": "Agent handover", "capability_ids": ["CAP-002"]},
        ],
    }]}
    plan = _agent(inventory, incomplete, repaired).architect({}, {"project_title": "Support"}, "Source")
    assigned = [
        capability_id
        for deliverable in plan["deliverables"]
        for module in deliverable["modules"]
        for capability_id in module["capability_ids"]
    ]
    assert assigned == ["CAP-001", "CAP-002"]
    assert plan["deliverables"][0]["display_name"] == "Deliverable 1 - Support platform"


def test_missing_assignment_is_repaired_without_another_model_call():
    inventory = {"capability_units": [
        {"id": "CAP-001", "name": "Web channel"},
        {"id": "CAP-002", "name": "CRM integration"},
    ]}
    invalid = {"deliverables": [{
        "name": "Channels",
        "modules": [{"name": "Web", "capability_ids": ["CAP-001"]}],
    }]}
    plan = _agent(inventory, invalid).architect({}, {"project_title": "Customer Platform"}, "Source")
    assert len(plan["deliverables"]) == 1
    assert len(plan["deliverables"][0]["modules"]) == 2
    assigned = {
        capability_id
        for module in plan["deliverables"][0]["modules"]
        for capability_id in module["capability_ids"]
    }
    assert assigned == {"CAP-001", "CAP-002"}


def test_boundary_classification_uses_writer_model_and_surfaces_phase_evidence():
    captured = {}

    def respond(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["model_id"] = kwargs.get("model_id")
        return json.dumps({"deliverables": [{
            "name": "Core platform",
            "boundary_type": "phase",
            "separation_basis": "Day 1 go-live",
            "modules": [{"name": "Core", "capability_ids": ["CAP-001"]}],
        }]})

    agent = ScopeArchitectAgent(
        SimpleNamespace(ANALYSIS_MODEL_ID="analysis", WRITER_MODEL_ID="writer"),
        call_fn=respond,
    )
    agent._classify(
        [{"id": "CAP-001", "name": "Core chatbot"}],
        {},
        {"project_title": "Support"},
        "Core platform is Day 1. Tata Neu is the default Phase 2 after go-live stabilisation.",
    )

    assert captured["model_id"] == "writer"
    assert "Tata Neu is the default Phase 2" in captured["prompt"]
    assert "Day 1 versus later scope" in captured["prompt"]


def test_local_assignment_repair_reuses_one_supporting_module():
    inventory = [
        {"id": "CAP-001", "name": "Core chatbot"},
        {"id": "CAP-002", "name": "Regional catalogue"},
        {"id": "CAP-003", "name": "Survey export"},
    ]
    plan = {"deliverables": [{
        "name": "Platform",
        "modules": [{"name": "Core", "capability_ids": ["CAP-001"]}],
    }]}

    repaired = ScopeArchitectAgent._complete_assignments(plan, inventory)
    supporting = [
        module
        for module in repaired["deliverables"][0]["modules"]
        if module["name"] == "Supporting Source Requirements"
    ]
    assert len(supporting) == 1
    assert supporting[0]["capability_ids"] == ["CAP-002", "CAP-003"]


def test_source_only_phase_capability_requires_exact_evidence():
    inventory = [{"id": "CAP-001", "name": "Core customer support"}]
    source = "Core customer support is Day 1. Tata Neu is the default Phase 2 after stabilisation."
    discovered = ScopeArchitectAgent._validated_discovered_capabilities([{
        "id": "CAP-SRC-001",
        "name": "Tata Neu channel extension",
        "evidence_quote": "Tata Neu is the default Phase 2 after stabilisation",
        "disposition": "in_scope",
        "evidence_status": "Source Assumption",
    }, {
        "id": "CAP-SRC-002",
        "name": "Invented voice implementation",
        "evidence_quote": "Voice is included in Phase 2",
        "disposition": "in_scope",
    }], source, inventory)

    assert [item["id"] for item in discovered] == ["CAP-SRC-001"]
    assert discovered[0]["disposition"] == "in_scope"


def test_single_scope_accepts_modules_without_deliverable_wrapper():
    from app.agents.poc_writer_agent import POCWriterAgent, TemplateSection

    section = TemplateSection("6. Scope of Work", "", {"type": "GENERATED"}, 0)
    issues = POCWriterAgent._authoring_issues(
        "### Conversation Orchestration\n\n- Configure the source-backed routing workflow.",
        section,
    )
    assert not any("deliverable" in issue.casefold() for issue in issues)


def test_one_to_one_capability_modules_trigger_consolidation_audit():
    inventory = [
        {"id": f"CAP-{index:03d}", "name": f"Agent workflow {index}", "disposition": "in_scope"}
        for index in range(1, 9)
    ]
    plan = {"deliverables": [{
        "name": "Support platform",
        "modules": [
            {"name": f"Agent workflow {index}", "capability_ids": [f"CAP-{index:03d}"]}
            for index in range(1, 9)
        ],
    }]}
    issues = ScopeArchitectAgent._module_fragmentation_issues(plan, inventory)
    assert any("one-for-one" in issue for issue in issues)


def test_architect_consolidates_fragmented_module_plan():
    inventory = {"capability_units": [
        {"id": f"CAP-{index:03d}", "name": f"Agent workflow {index}", "disposition": "in_scope"}
        for index in range(1, 9)
    ]}
    fragmented = {"deliverables": [{
        "name": "Support platform",
        "boundary_type": "single_package",
        "separation_basis": "One accepted platform",
        "modules": [
            {"name": f"Agent workflow {index}", "capability_ids": [f"CAP-{index:03d}"]}
            for index in range(1, 9)
        ],
    }]}
    consolidated = {"deliverables": [{
        "name": "Support platform",
        "boundary_type": "single_package",
        "separation_basis": "One accepted platform",
        "modules": [
            {"name": "Agent routing", "capability_ids": [f"CAP-{index:03d}" for index in range(1, 5)]},
            {"name": "Agent operations", "capability_ids": [f"CAP-{index:03d}" for index in range(5, 9)]},
        ],
    }]}
    plan = _agent(inventory, fragmented, consolidated).architect(
        {}, {"project_title": "Support"}, "Agent workflow source"
    )
    assert len(plan["deliverables"][0]["modules"]) == 2


def test_explicit_refinement_deliverables_override_single_package_bias():
    requirements = {
        "key_deliverables": [
            "Web customer journeys", "WhatsApp customer journeys",
            "Live agent handover", "Agent assist",
            "Conversation reporting", "Operational monitoring",
        ]
    }
    one_package = {"deliverables": [{
        "name": "Customer support platform",
        "boundary_type": "single_package",
        "separation_basis": "One implementation",
        "modules": [
            {"name": "Customer channels", "capability_ids": ["CAP-001", "CAP-002"]},
            {"name": "Agent operations", "capability_ids": ["CAP-003", "CAP-004"]},
            {"name": "Reporting and monitoring", "capability_ids": ["CAP-005", "CAP-006"]},
        ],
    }]}
    plan = _agent(one_package).architect(
        requirements,
        {"project_title": "Support"},
        "Source",
        refinement_constraints={
            "requested_deliverable_count": 2,
            "requested_deliverable_names": ["Customer Experience", "Agent Operations"],
        },
    )
    assert [item["display_name"] for item in plan["deliverables"]] == [
        "Deliverable 1 - Customer Experience",
        "Deliverable 2 - Agent Operations",
    ]
    assigned = {
        capability_id
        for deliverable in plan["deliverables"]
        for module in deliverable["modules"]
        for capability_id in module["capability_ids"]
    }
    assert assigned == {f"CAP-{index:03d}" for index in range(1, 7)}


def test_fallback_plan_consolidates_large_inventory_and_excludes_future_scope():
    inventory = [
        {"id": "CAP-001", "name": "Fashion web channel", "requirements": ["Fashion web channel"]},
        {"id": "CAP-002", "name": "Luxury WhatsApp channel", "requirements": ["Luxury WhatsApp channel"]},
        {"id": "CAP-003", "name": "Live agent handover", "requirements": ["Live agent handover"]},
        {"id": "CAP-004", "name": "Agent context transfer", "requirements": ["Agent context transfer"]},
        {"id": "CAP-005", "name": "Conversation analytics", "requirements": ["Conversation analytics"]},
        {"id": "CAP-006", "name": "Performance reporting", "requirements": ["Performance reporting"]},
        {"id": "CAP-007", "name": "Voice bot", "disposition": "future"},
    ]
    agent = _agent()
    plan = agent._fallback_plan(inventory, {"project_title": "Support"}, ["repair failed"])
    assigned = {
        capability_id
        for module in plan["deliverables"][0]["modules"]
        for capability_id in module["capability_ids"]
    }
    assert assigned == {f"CAP-{index:03d}" for index in range(1, 7)}
    assert len(plan["deliverables"][0]["modules"]) < 6
    assert plan["open_boundaries"][0]["capability_id"] == "CAP-007"


def test_explicit_source_deliverables_are_validated_and_preserved():
    source = """
    Deliverable 1 - Historical Data Migration
    Deliverable 2 - Ticket Management
    Deliverable 3 - Email Management
    Deliverable 4 - Reporting and SLA Management
    """
    requirements = {
        "source_deliverables": [
            {"name": "Historical Data Migration", "evidence_quote": "Deliverable 1 - Historical Data Migration"},
            {"name": "Ticket Management", "evidence_quote": "Deliverable 2 - Ticket Management"},
            {"name": "Email Management", "evidence_quote": "Deliverable 3 - Email Management"},
            {"name": "Reporting and SLA Management", "evidence_quote": "Deliverable 4 - Reporting and SLA Management"},
            {"name": "Invented", "evidence_quote": "not in the source"},
        ]
    }
    boundaries = ScopeArchitectAgent._explicit_source_deliverables(requirements, source)
    assert [item["name"] for item in boundaries] == [
        "Historical Data Migration", "Ticket Management", "Email Management",
        "Reporting and SLA Management",
    ]


def test_source_deliverable_constraint_splits_one_package_into_named_outcomes():
    agent = _agent()
    plan = {
        "deliverables": [{
            "name": "Unified CRM",
            "modules": [
                {"name": "Migration", "capability_ids": ["CAP-001"]},
                {"name": "Ticket Management", "capability_ids": ["CAP-002"]},
                {"name": "Email Management", "capability_ids": ["CAP-003"]},
                {"name": "Reporting", "capability_ids": ["CAP-004"]},
            ],
        }],
    }
    constrained = agent._enforce_refinement_constraints(
        plan,
        [],
        {
            "requested_deliverable_count": 4,
            "requested_deliverable_names": [
                "Historical Data Migration", "Ticket Management",
                "Email Management", "Reporting and SLA Management",
            ],
            "constraint_source": "explicit_source_deliverables",
        },
    )
    assert [item["name"] for item in constrained["deliverables"]] == [
        "Historical Data Migration", "Ticket Management", "Email Management",
        "Reporting and SLA Management",
    ]
    assert all(
        item["separation_basis"] == "Explicit customer-authored deliverable boundary"
        for item in constrained["deliverables"]
    )


def test_multi_deliverable_single_package_label_is_normalised_to_acceptance():
    inventory = [
        {"id": "CAP-001", "disposition": "in_scope", "evidence_status": "Confirmed"},
        {"id": "CAP-002", "disposition": "in_scope", "evidence_status": "Confirmed"},
    ]
    plan = {
        "deliverables": [
            {
                "name": "Data Migration",
                "boundary_type": "single_package",
                "separation_basis": "Distinct migration validation outcome",
                "modules": [{"name": "Migration", "capability_ids": ["CAP-001"]}],
            },
            {
                "name": "Reporting",
                "boundary_type": "single_package",
                "separation_basis": "Distinct management reporting outcome",
                "modules": [{"name": "Dashboards", "capability_ids": ["CAP-002"]}],
            },
        ]
    }
    normalised, issues = ScopeArchitectAgent._normalise_plan(plan, inventory)
    assert issues == []
    assert [item["boundary_type"] for item in normalised["deliverables"]] == [
        "acceptance", "acceptance"
    ]


def test_incomplete_explicit_headings_expand_to_distinct_source_outcomes():
    names = ScopeArchitectAgent._source_outcome_boundary_names({
        "key_deliverables": [
            "Migration of historical data and attachments",
            "Ticketing functionality with escalation and follow-up",
            "Email desk, compose, and communication management",
            "Manager reporting dashboards and agent scorecards",
        ]
    })
    assert names == [
        "Data Migration",
        "Ticketing and Case Management",
        "Email Desk and Communication",
        "Management Reporting and Dashboards",
    ]


def test_brd_outcome_families_are_enforced_when_labels_are_inconsistent():
    requirements = {
        "key_deliverables": [
            "Migration of historical data and attachments",
            "Ticketing functionality in Connect",
            "Escalation matrix implementation",
            "Follow-up module",
            "Email Desk solution with routing and compose capabilities",
            "Manager and agent reporting dashboards",
            "Service Level Management configuration and breach handling",
        ]
    }
    one_package = {
        "discovered_capabilities": [],
        "deliverables": [{
            "name": "Unified CRM",
            "boundary_type": "single_package",
            "separation_basis": "Shared implementation",
            "modules": [
                {"name": "Data Migration", "capability_ids": ["CAP-001"]},
                {"name": "Ticketing and Escalation", "capability_ids": ["CAP-002", "CAP-003", "CAP-004"]},
                {"name": "Email Desk", "capability_ids": ["CAP-005"]},
                {"name": "Reporting and SLA Management", "capability_ids": ["CAP-006", "CAP-007"]},
            ],
        }],
    }
    plan = _agent(one_package).architect(requirements, {"project_title": "CRM"}, "BRD source")
    assert [item["display_name"] for item in plan["deliverables"]] == [
        "Deliverable 1 - Data Migration",
        "Deliverable 2 - Ticketing and Case Management",
        "Deliverable 3 - Email Desk and Communication",
        "Deliverable 4 - Management Reporting and Dashboards",
    ]


def test_scope_node_skips_when_scope_is_not_selected():
    result = scope_architecture_node({"selected_sow_sections": ["aws_pricing"]})
    assert result["scope_architecture_plan"] == {}
    assert result["current_step"] == "scope_architecture"


def test_all_graphs_include_scope_architecture_before_pricing():
    for graph in (create_graph(), create_preview_graph(), create_fast_preview_graph()):
        edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
        assert ("validate", "scope_architecture") in edges
        assert ("scope_architecture", "pricing") in edges
        assert ("validate", "pricing") not in edges
