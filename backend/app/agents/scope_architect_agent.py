"""Dedicated deliverable/module boundary architect for SOW generation."""

from __future__ import annotations

import json
import re
from typing import Any, Callable, Dict, List, Optional

import boto3

from app.core.bedrock_llm import BedrockLLM


def _json_object(text: str) -> Dict[str, Any]:
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip(), flags=re.I)
    start, end = value.find("{"), value.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(value[start:end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


class ScopeArchitectAgent:
    """Inventory capabilities, classify boundaries, and audit complete assignment."""

    def __init__(
        self,
        config: Any,
        template_type: str = "POC",
        llm: Optional[Any] = None,
        call_fn: Optional[Callable[..., str]] = None,
    ) -> None:
        self.config = config
        self.template_type = template_type
        self.call_fn = call_fn
        if llm is None and call_fn is None:
            bedrock = boto3.client(
                "bedrock-runtime", region_name=config.BEDROCK_REGION, config=config.BOTO_CONFIG
            )
            llm = BedrockLLM(config, bedrock)
        self.llm = llm

    def _call(self, prompt: str, call_name: str, max_tokens: int = 12000) -> str:
        boundary_decision = call_name in {"Scope Boundary Classification", "Scope Boundary Audit"}
        task = "writer" if boundary_decision else "analysis"
        model_id = (
            getattr(self.config, "WRITER_MODEL_ID", None)
            if boundary_decision
            else getattr(self.config, "ANALYSIS_MODEL_ID", getattr(self.config, "WRITER_MODEL_ID", None))
        )
        if self.call_fn:
            return str(self.call_fn(
                prompt,
                max_tokens=max_tokens,
                model_id=model_id,
            ) or "")
        result = self.llm.generate(
            prompt,
            task=task,
            max_tokens=max_tokens,
            temperature=0.0,
            call_name=call_name,
            fallback_model_id=getattr(self.config, "WRITER_MODEL_ID", None),
        )
        return str(result.text or "")

    def architect(
        self,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source_context: str,
        refinement_constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        refinement_constraints = dict(refinement_constraints or {})
        source_deliverables = self._explicit_source_deliverables(requirements, source_context)
        try:
            declared_count = int(requirements.get("declared_deliverable_count") or 0)
        except (TypeError, ValueError):
            declared_count = 0
        derived_outcome_names = self._source_outcome_boundary_names(requirements)
        if (
            source_deliverables
            and 2 <= declared_count <= 10
            and len(source_deliverables) >= declared_count
            and not refinement_constraints.get("requested_deliverable_count")
        ):
            refinement_constraints.update({
                "requested_deliverable_count": declared_count,
                "requested_deliverable_names": [item["name"] for item in source_deliverables[:declared_count]],
                "constraint_source": "explicit_source_deliverables",
            })
            print(
                f"[SCOPE-ARCHITECT] Preserving {declared_count} declared source deliverable(s): "
                + ", ".join(item["name"] for item in source_deliverables[:declared_count]),
                flush=True,
            )
        elif (
            len(source_deliverables) >= 2
            and len(derived_outcome_names) >= len(source_deliverables)
            and not refinement_constraints.get("requested_deliverable_count")
        ):
            refinement_constraints.update({
                "requested_deliverable_count": len(derived_outcome_names),
                "requested_deliverable_names": derived_outcome_names,
                "constraint_source": "explicit_source_deliverables",
            })
            print(
                f"[SCOPE-ARCHITECT] Preserving {len(derived_outcome_names)} distinct source outcomes: "
                + ", ".join(derived_outcome_names),
                flush=True,
            )
        elif (
            len(derived_outcome_names) >= 3
            and "Data Migration" in derived_outcome_names
            and self._crm_outcome_split_applicable(requirements, metadata, source_context)
            and sum(
                len(requirements.get(key) or [])
                for key in ("key_deliverables", "functional_requirements")
                if isinstance(requirements.get(key) or [], list)
            ) >= 4
            and not refinement_constraints.get("requested_deliverable_count")
        ):
            # This legacy inference is intentionally limited to migration-led
            # CRM replacement BRDs. Without that anchor, ordinary mentions of
            # email, cases and reporting in a platform RFQ can falsely create
            # three or four top-level deliverables.
            refinement_constraints.update({
                "requested_deliverable_count": len(derived_outcome_names),
                "requested_deliverable_names": derived_outcome_names,
                "constraint_source": "source_outcome_families",
            })
            print(
                f"[SCOPE-ARCHITECT] Preserving {len(derived_outcome_names)} source-backed outcome families: "
                + ", ".join(derived_outcome_names),
                flush=True,
            )
        # Objective analysis already produced a structured requirements baseline.
        # Build the inventory locally instead of spending a large model call
        # restating those same facts. Use the LLM inventory only for truly sparse
        # legacy records.
        inventory = self._fallback_inventory(requirements)
        if not inventory:
            inventory = self._inventory(requirements, metadata, source_context)
        if not inventory:
            print("[SCOPE-ARCHITECT] No valid capability inventory returned", flush=True)
            return {}
        print(f"[SCOPE-ARCHITECT] Built {len(inventory)} source capability unit(s)", flush=True)
        plan = self._classify(
            inventory, requirements, metadata, source_context, refinement_constraints
        )
        if not plan:
            raise RuntimeError("Scope boundary classification returned invalid or empty JSON")
        discovered = self._validated_discovered_capabilities(
            plan.pop("discovered_capabilities", []), source_context, inventory
        )
        if discovered:
            inventory.extend(discovered)
            print(
                f"[SCOPE-ARCHITECT] Added {len(discovered)} source-only capability unit(s) "
                "needed to preserve delivery boundaries",
                flush=True,
            )
        plan = self._complete_assignments(plan, inventory)
        plan = self._enforce_refinement_constraints(plan, inventory, refinement_constraints)
        requested_count = int(refinement_constraints.get("requested_deliverable_count") or 0)
        if requested_count and len(plan.get("deliverables") or []) != requested_count:
            raise RuntimeError(
                f"Scope architecture did not preserve the required {requested_count} deliverable boundaries"
            )
        plan, issues = self._normalise_plan(plan, inventory)
        deliverable_fragmentation = (
            []
            if refinement_constraints.get("requested_deliverable_count")
            else self._deliverable_fragmentation_issues(plan)
        )
        fragmentation = (
            []
            if refinement_constraints.get("requested_deliverable_count")
            else self._module_fragmentation_issues(plan, inventory)
        )
        if deliverable_fragmentation or fragmentation:
            print(
                "[SCOPE-ARCHITECT] Scope consolidation required: "
                + "; ".join(deliverable_fragmentation + fragmentation),
                flush=True,
            )
        if issues or deliverable_fragmentation or fragmentation:
            revised = self._repair(
                plan, inventory, requirements, metadata, source_context,
                issues + deliverable_fragmentation + fragmentation, refinement_constraints,
            )
            revised = self._complete_assignments(revised, inventory)
            revised = self._enforce_refinement_constraints(
                revised, inventory, refinement_constraints
            )
            revised, revised_issues = self._normalise_plan(revised, inventory)
            revised_deliverable_fragmentation = (
                []
                if refinement_constraints.get("requested_deliverable_count")
                else self._deliverable_fragmentation_issues(revised)
            )
            revised_fragmentation = (
                []
                if refinement_constraints.get("requested_deliverable_count")
                else self._module_fragmentation_issues(revised, inventory)
            )
            if (
                not revised_issues
                and not revised_deliverable_fragmentation
                and not revised_fragmentation
            ):
                plan, issues = revised, []
                print(
                    f"[SCOPE-ARCHITECT] Consolidated scope into "
                    f"{sum(len(item['modules']) for item in plan['deliverables'])} cohesive module(s)",
                    flush=True,
                )
            else:
                issues = revised_issues + revised_deliverable_fragmentation + revised_fragmentation
        if issues:
            # If the only unresolved problem is unsupported top-level splitting,
            # consolidate deterministically rather than failing or trusting a
            # second verbose model response. Explicit source/user boundaries
            # are protected above and never enter this fallback.
            if not requested_count and deliverable_fragmentation:
                modules = [
                    module
                    for deliverable in (plan.get("deliverables") or [])
                    for module in (deliverable.get("modules") or [])
                    if isinstance(module, dict)
                ]
                if modules:
                    plan = {
                        **plan,
                        "deliverables": [{
                            "name": str(metadata.get("project_title") or "Solution Delivery").strip(),
                            "purpose": "One cohesive implementation and acceptance package",
                            "boundary_type": "single_package",
                            "separation_basis": "No independent source-backed delivery boundary",
                            "modules": modules,
                        }],
                    }
                    plan, remaining = self._normalise_plan(plan, inventory)
                    remaining += self._module_fragmentation_issues(plan, inventory)
                    if not remaining:
                        issues = []
            if issues:
                print(f"[SCOPE-ARCHITECT] Plan rejected: {', '.join(issues)}", flush=True)
                raise RuntimeError("Scope architecture validation failed; generation halted: " + "; ".join(issues))
        print(
            f"[SCOPE-ARCHITECT] Approved {len(plan['deliverables'])} deliverable(s), "
            f"{sum(len(item['modules']) for item in plan['deliverables'])} module(s)",
            flush=True,
        )
        return plan

    @staticmethod
    def _explicit_source_deliverables(
        requirements: Dict[str, Any], source_context: str
    ) -> List[Dict[str, str]]:
        """Validate explicit deliverable boundaries against verbatim source evidence."""
        source_key = re.sub(r"\s+", " ", str(source_context or "").casefold())
        clean: List[Dict[str, str]] = []
        seen = set()
        for item in requirements.get("source_deliverables") or []:
            if not isinstance(item, dict):
                continue
            name = re.sub(r"\s+", " ", str(item.get("name") or "")).strip()
            quote = re.sub(r"\s+", " ", str(item.get("evidence_quote") or "")).strip()
            key = name.casefold()
            if not name or not quote or quote.casefold() not in source_key or key in seen:
                continue
            # A table headed "Deliverables" commonly lists implementation
            # activities. Only a numbered/labelled package is a mandatory
            # contractual boundary; unnumbered rows remain candidate modules.
            if not re.search(
                r"\b(?:deliverable|phase|wave|release)\s*(?:no\.?\s*)?#?\s*\d+\b",
                quote,
                flags=re.I,
            ):
                continue
            seen.add(key)
            clean.append({"name": name, "evidence_quote": quote})
        # A single labelled item does not establish a multi-deliverable structure.
        return clean if 2 <= len(clean) <= 10 else []

    @staticmethod
    def _deliverable_fragmentation_issues(plan: Dict[str, Any]) -> List[str]:
        """Reject capability/checklist rows promoted to contractual deliverables."""
        deliverables = [
            item for item in plan.get("deliverables") or []
            if isinstance(item, dict) and item.get("modules")
        ]
        if len(deliverables) < 3:
            return []
        thin_ratio = sum(
            len(item.get("modules") or []) <= 2 for item in deliverables
        ) / len(deliverables)
        generic_basis = re.compile(
            r"\b(?:per (?:the )?(?:validated )?source list|distinct (?:platform build|"
            r"workstream|capability|integration deliverable)|knowledge.transfer completion)\b",
            flags=re.I,
        )
        sequenced_basis = re.compile(
            r"\b(?:day\s*1|phase\s*\d+|wave\s*\d+|release\s*\d+|later|subsequent|"
            r"before|after|follow(?:ing|ed by)|post.go.live|hypercare|separate go.live|"
            r"commercial hand.?off|contract duration)\b",
            flags=re.I,
        )
        unsupported = sum(
            bool(generic_basis.search(str(item.get("separation_basis") or "")))
            or not sequenced_basis.search(str(item.get("separation_basis") or ""))
            for item in deliverables
        )
        lifecycle_rows = sum(bool(re.search(
            r"\b(?:solution design|architecture|testing|go.live|training|documentation|"
            r"support|continuous improvement)\b",
            str(item.get("name") or ""),
            flags=re.I,
        )) for item in deliverables)
        if thin_ratio >= 0.6 and unsupported >= max(2, len(deliverables) - 2):
            return [
                "implementation checklist rows were promoted to deliverables; consolidate them "
                "under the smallest source-backed phase/release packages"
            ]
        if lifecycle_rows >= 2:
            return [
                "architecture, testing, training or support lifecycle rows were promoted to "
                "deliverables; keep them as modules unless explicitly numbered as separate packages"
            ]
        return []

    @staticmethod
    def _source_outcome_boundary_names(requirements: Dict[str, Any]) -> List[str]:
        """Identify broad contractual outcomes when explicit headings are incomplete.

        This is deliberately activated only by the caller after at least two
        source-validated deliverable headings have established that the source
        uses a multi-deliverable structure.
        """
        source_items: List[Any] = []
        for key in ("key_deliverables", "functional_requirements"):
            values = requirements.get(key) or []
            source_items.extend(values if isinstance(values, list) else [values])
        text = "\n".join(
            str(item.get("name") if isinstance(item, dict) else item or "")
            for item in source_items
        ).casefold()
        families = [
            ("Data Migration", ("migration", "historical data", "data transfer")),
            ("Ticketing and Case Management", ("ticket", "case management", "escalation", "follow-up")),
            ("Email Desk and Communication", ("email", "mailbox", "compose", "communication")),
            ("Management Reporting and Dashboards", ("report", "dashboard", "analytics", "scorecard")),
        ]
        return [name for name, signals in families if any(signal in text for signal in signals)]

    @staticmethod
    def _crm_outcome_split_applicable(
        requirements: Dict[str, Any], metadata: Dict[str, Any], source_context: str
    ) -> bool:
        """Limit the legacy four-family split to actual CRM replacement work.

        Generic cloud-migration BRDs commonly mention data migration,
        communication, and dashboards.  Those incidental words must not create
        ticketing or email-desk deliverables that the engagement never requests.
        """
        title = " ".join(str(metadata.get(key) or "") for key in ("project_title", "project_name"))
        if re.search(r"\b(?:crm|customer relationship management)\b", title, flags=re.I):
            return True
        source = "\n".join([
            str(source_context or ""),
            "\n".join(str(item) for item in requirements.get("key_deliverables") or []),
            "\n".join(str(item) for item in requirements.get("functional_requirements") or []),
        ])
        domain_signals = (
            r"\bticket(?:ing)?\b",
            r"\bcase management\b",
            r"\bemail desk\b",
            r"\bcustomer service\b",
            r"\bcontact cent(?:re|er)\b",
        )
        return sum(bool(re.search(pattern, source, flags=re.I)) for pattern in domain_signals) >= 2

    @staticmethod
    def _fallback_inventory(requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        values: List[Any] = []
        primary_keys = ("key_deliverables", "functional_requirements")
        for key in primary_keys:
            value = requirements.get(key) or []
            values.extend(value if isinstance(value, list) else [value])
        # Features and workflow steps usually restate the primary requirements.
        # Use them only when the primary extraction is sparse.
        if len(values) < 4:
            for key in ("key_features", "workflow_steps"):
                value = requirements.get(key) or []
                values.extend(value if isinstance(value, list) else [value])
        clean = []
        seen = set()
        for value in values:
            name = str(value.get("name") if isinstance(value, dict) else value or "").strip()
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            clean.append({
                "id": f"CAP-{len(clean) + 1:03d}",
                "name": name,
                "requirements": [name],
                "source_basis": [name],
                "disposition": "in_scope",
                "evidence_status": (
                    str(value.get("evidence_status") or "Source Assumption")
                    if isinstance(value, dict) else "Source Assumption"
                ),
            })
        return clean

    @staticmethod
    def _validated_discovered_capabilities(
        values: Any,
        source: str,
        inventory: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Admit source-only phase capabilities omitted by objective normalisation.

        The boundary classifier sees the complete source, whereas the fast local
        inventory is normally built from the objective agent's primary lists.
        Requiring an exact evidence excerpt keeps this escape hatch useful for
        Day-1/Phase-2 boundaries without allowing the classifier to invent scope.
        """
        source_key = re.sub(r"[^a-z0-9]+", " ", str(source or "").casefold()).strip()
        known_names = {
            re.sub(r"[^a-z0-9]+", " ", str(item.get("name") or "").casefold()).strip()
            for item in inventory
        }
        known_ids = {str(item.get("id") or "") for item in inventory}
        allowed_dispositions = {"in_scope", "future", "optional", "open"}
        clean: List[Dict[str, Any]] = []
        for index, item in enumerate(values if isinstance(values, list) else [], 1):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            quote = str(item.get("evidence_quote") or "").strip()
            quote_key = re.sub(r"[^a-z0-9]+", " ", quote.casefold()).strip()
            name_key = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
            if not name or not quote_key or quote_key not in source_key or name_key in known_names:
                continue
            item_id = re.sub(
                r"[^A-Za-z0-9_-]+", "-", str(item.get("id") or f"CAP-SRC-{index:03d}")
            )[:40]
            if not item_id or item_id in known_ids:
                item_id = f"CAP-SRC-{index:03d}"
            disposition = str(item.get("disposition") or "open").casefold()
            if disposition not in allowed_dispositions:
                disposition = "open"
            evidence_status = str(item.get("evidence_status") or "Source Assumption")
            clean.append({
                **item,
                "id": item_id,
                "name": name,
                "requirements": list(item.get("requirements") or [name]),
                "source_basis": list(item.get("source_basis") or [quote]),
                "evidence_quote": quote,
                "disposition": disposition,
                "evidence_status": evidence_status,
            })
            known_names.add(name_key)
            known_ids.add(item_id)
        return clean

    @staticmethod
    def _complete_assignments(plan: Dict[str, Any], inventory: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Repair ID coverage locally without another slow model round-trip."""
        if not isinstance(plan, dict):
            return {}
        deliverables = [item for item in plan.get("deliverables") or [] if isinstance(item, dict)]
        if not deliverables:
            return plan
        in_scope = {
            str(item["id"]): item
            for item in inventory
            if str(item.get("disposition") or "in_scope").casefold() == "in_scope"
        }
        used = set()
        modules = []
        for deliverable in deliverables:
            for module in deliverable.get("modules") or []:
                if not isinstance(module, dict):
                    continue
                unique = []
                for capability_id in module.get("capability_ids") or []:
                    capability_id = str(capability_id)
                    if capability_id in in_scope and capability_id not in used:
                        unique.append(capability_id)
                        used.add(capability_id)
                module["capability_ids"] = unique
                modules.append(module)
        missing = [item for item_id, item in in_scope.items() if item_id not in used]
        if missing:
            if not modules:
                deliverables[0]["modules"] = []
            for capability in missing:
                capability_words = set(re.findall(r"[a-z0-9]+", str(capability.get("name") or "").casefold()))
                best = None
                best_score = 0
                for module in modules:
                    module_words = set(re.findall(
                        r"[a-z0-9]+",
                        (str(module.get("name") or "") + " " + str(module.get("objective") or "")).casefold(),
                    ))
                    score = len(capability_words & module_words)
                    if score > best_score:
                        best, best_score = module, score
                if best is None:
                    best = next(
                        (module for module in deliverables[0].get("modules") or []
                         if str(module.get("name") or "").casefold() == "supporting source requirements"),
                        None,
                    )
                    if best is None:
                        best = {
                            "name": "Supporting Source Requirements",
                            "capability_ids": [],
                            "requirements": [],
                            "evidence_status": "Source Assumption",
                        }
                        deliverables[0].setdefault("modules", []).append(best)
                        modules.append(best)
                best.setdefault("capability_ids", []).append(str(capability["id"]))
                best.setdefault("requirements", []).append(str(capability.get("name") or ""))
        plan["deliverables"] = deliverables
        return plan

    def _fallback_plan(self, inventory: List[Dict[str, Any]], metadata: Dict[str, Any], issues: List[str]) -> Dict[str, Any]:
        project = str(metadata.get("project_title") or "Solution").strip()
        in_scope = [
            item for item in inventory
            if str(item.get("disposition") or "in_scope").casefold() == "in_scope"
        ]
        modules = self._fallback_modules(in_scope)
        open_boundaries = [{
            "capability_id": str(item.get("id") or ""),
            "reason": f"Preserved as {str(item.get('disposition') or 'open')} scope from source evidence",
        } for item in inventory if item not in in_scope]
        return {
            "deliverables": [{
                "name": project,
                "display_name": f"Deliverable 1 - {project}",
                "number": 1,
                "purpose": "Cohesive implementation and acceptance of the sourced capabilities",
                "boundary_type": "single_package",
                "separation_basis": "Fallback single delivery boundary pending architecture review",
                "modules": modules,
            }],
            "cross_cutting_decisions": [],
            "open_boundaries": open_boundaries,
            "classification_warning": "; ".join(issues),
        }

    @staticmethod
    def _enforce_refinement_constraints(
        plan: Dict[str, Any],
        inventory: List[Dict[str, Any]],
        constraints: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Enforce an explicit user-requested deliverable count and names.

        The normal architecture policy deliberately avoids arbitrary splitting.
        A refinement instruction is different: it is a direct document-boundary
        decision and must survive classification, audit, and fallback paths.
        """
        try:
            requested = int(constraints.get("requested_deliverable_count") or 0)
        except (TypeError, ValueError):
            return plan
        if requested < 1 or requested > 10 or not isinstance(plan, dict):
            return plan

        deliverables = [
            dict(item) for item in plan.get("deliverables") or []
            if isinstance(item, dict)
        ]
        requested_names = [
            str(value).strip() for value in constraints.get("requested_deliverable_names") or []
            if str(value).strip()
        ]
        names = [
            requested_names[index] if index < len(requested_names)
            else (
                str(deliverables[index].get("name") or "").strip()
                if index < len(deliverables) else f"Delivery Package {index + 1}"
            )
            for index in range(requested)
        ]
        if len(deliverables) == requested and all(
            deliverable.get("modules") for deliverable in deliverables
        ) and constraints.get("constraint_source") != "source_outcome_families":
            for index, deliverable in enumerate(deliverables):
                deliverable["name"] = names[index]
                deliverable["boundary_type"] = "acceptance"
                deliverable["separation_basis"] = (
                    "Explicit customer-authored deliverable boundary"
                    if constraints.get("constraint_source") == "explicit_source_deliverables"
                    else (
                        "Distinct source-backed business outcome boundary"
                        if constraints.get("constraint_source") == "source_outcome_families"
                        else "Explicit deliverable boundary requested for this SOW refinement"
                    )
                )
            plan["deliverables"] = deliverables
            plan["user_deliverable_constraint_applied"] = True
            print(
                f"[SCOPE-ARCHITECT] Applied mandatory outcome boundary: {requested} deliverable(s)",
                flush=True,
            )
            return plan
        modules = [
            dict(module)
            for deliverable in deliverables
            for module in deliverable.get("modules") or []
            if isinstance(module, dict) and module.get("capability_ids")
        ]
        # If the model produced fewer modules than requested deliverables, split
        # multi-capability modules without duplicating or inventing capability IDs.
        while len(modules) < requested:
            split_index = next((
                index for index, module in enumerate(modules)
                if len(module.get("capability_ids") or []) > 1
            ), None)
            if split_index is None:
                return plan
            module = modules.pop(split_index)
            ids = list(module.get("capability_ids") or [])
            midpoint = max(1, len(ids) // 2)
            for part_number, part_ids in enumerate((ids[:midpoint], ids[midpoint:]), 1):
                part = dict(module)
                part["capability_ids"] = part_ids
                part["name"] = f"{module.get('name') or 'Solution Workstream'} {part_number}"
                modules.insert(split_index + part_number - 1, part)

        stopwords = {"and", "the", "for", "with", "solution", "platform", "deliverable"}

        def words(value: Any) -> set[str]:
            return {
                token for token in re.findall(r"[a-z0-9]+", str(value or "").casefold())
                if len(token) > 2 and token not in stopwords
            }

        def boundary_words(value: Any) -> set[str]:
            tokens = words(value)
            if "migration" in tokens:
                tokens.update({"migrate", "historical", "data", "attachment", "reconciliation"})
            if "ticketing" in tokens or "case" in tokens:
                tokens.update({"ticket", "case", "classification", "tat", "sla", "escalation", "follow", "lifecycle"})
            if "email" in tokens or "communication" in tokens:
                tokens.update({"email", "mail", "compose", "inbox", "outbox", "acknowledgement", "template", "routing"})
            if "reporting" in tokens or "dashboard" in tokens:
                tokens.update({"report", "reporting", "dashboard", "analytics", "scorecard", "insight"})
            return tokens

        groups: List[List[Dict[str, Any]]] = [[] for _ in range(requested)]
        remaining = list(modules)
        # Seed every requested deliverable with its strongest matching module.
        for index, name in enumerate(names):
            name_words = boundary_words(name)
            best_index = max(
                range(len(remaining)),
                key=lambda candidate: len(name_words & words(
                    str(remaining[candidate].get("name") or "") + " "
                    + " ".join(map(str, remaining[candidate].get("requirements") or []))
                )),
            )
            groups[index].append(remaining.pop(best_index))
        for module in remaining:
            module_words = words(
                str(module.get("name") or "") + " "
                + " ".join(map(str, module.get("requirements") or []))
            )
            scores = [len(module_words & boundary_words(name)) for name in names]
            best_score = max(scores)
            candidates = [index for index, score in enumerate(scores) if score == best_score]
            target = min(candidates, key=lambda index: len(groups[index]))
            groups[target].append(module)

        plan["deliverables"] = [{
            "name": names[index],
            "purpose": (
                str(deliverables[index].get("purpose") or "").strip()
                if index < len(deliverables) else "User-directed delivery outcome"
            ),
            "boundary_type": "acceptance",
            "separation_basis": (
                "Explicit customer-authored deliverable boundary"
                if constraints.get("constraint_source") == "explicit_source_deliverables"
                else (
                    "Distinct source-backed business outcome boundary"
                    if constraints.get("constraint_source") == "source_outcome_families"
                    else "Explicit deliverable boundary requested for this SOW refinement"
                )
            ),
            "modules": group,
        } for index, group in enumerate(groups)]
        plan["user_deliverable_constraint_applied"] = True
        print(
            f"[SCOPE-ARCHITECT] Applied mandatory outcome boundary: {requested} deliverable(s)",
            flush=True,
        )
        return plan

    @staticmethod
    def _fallback_modules(inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Consolidate a large inventory deterministically if model repair fails."""
        if len(inventory) < 6:
            return [{
                "name": str(item["name"]),
                "capability_ids": [str(item["id"])],
                "task_statement": str(item.get("problem") or item["name"]),
                "objective": str(item.get("outcome") or ""),
                "requirements": list(item.get("requirements") or []),
                "source_basis": list(item.get("source_basis") or []),
                "evidence_status": str(item.get("evidence_status") or "Confirmed"),
            } for item in inventory]

        workstreams = [
            ("Channel Experience and Deployments", (
                "channel", "omnichannel", "whatsapp", "mobile app", "web integration",
                "fashion", "luxury", "brand experience",
            )),
            ("Analytics, Reporting and Observability", (
                "analytics", "report", "dashboard", "monitor", "metric", "performance", "insight",
            )),
            ("Agent Service and Escalation", (
                "live agent", "agent assist", "handover", "escalat", "routing", "agent desktop",
                "context transfer",
            )),
            ("Enterprise Integrations and Transactions", (
                "integration", "api", "transaction", "order", "payment", "refund", "return",
                "crm", "sap", "data warehouse",
            )),
            ("Security, Reliability and Platform Controls", (
                "authentication", "authorisation", "authorization", "security", "privacy", "audit",
                "availability", "scalab", "sla", "governance",
            )),
            ("Conversational AI and Self-Service", (
                "chatbot", "conversational", "intent", "query", "personal", "language", "knowledge",
                "proactive", "natural language", "self-service", "agentic",
            )),
            ("Delivery Enablement", (
                "evaluation", "documentation", "proposal", "commercial", "technology partner",
                "maintenance", "service level",
            )),
        ]
        grouped: Dict[str, List[Dict[str, Any]]] = {name: [] for name, _ in workstreams}
        grouped["Core Solution Capabilities"] = []
        for item in inventory:
            haystack = " ".join([
                str(item.get("name") or ""),
                " ".join(str(value) for value in item.get("requirements") or []),
                str(item.get("problem") or ""),
                str(item.get("outcome") or ""),
            ]).casefold()
            target = next(
                (name for name, signals in workstreams if any(signal in haystack for signal in signals)),
                "Core Solution Capabilities",
            )
            grouped[target].append(item)

        status_priority = {"Confirmed": 0, "Source Assumption": 1, "Proposed": 2, "Open": 3}
        modules = []
        for name, items in grouped.items():
            if not items:
                continue
            statuses = [str(item.get("evidence_status") or "Confirmed") for item in items]
            evidence_status = max(statuses, key=lambda value: status_priority.get(value, 1))
            modules.append({
                "name": name,
                "capability_ids": [str(item["id"]) for item in items],
                "task_statement": f"Implement the related {name.casefold()} capabilities as one cohesive workstream",
                "objective": "; ".join(str(item.get("outcome") or "").strip() for item in items if item.get("outcome")),
                "requirements": [
                    str(requirement)
                    for item in items
                    for requirement in (item.get("requirements") or [item.get("name")])
                    if str(requirement or "").strip()
                ],
                "source_basis": [
                    str(basis)
                    for item in items for basis in (item.get("source_basis") or [])
                    if str(basis or "").strip()
                ],
                "evidence_status": evidence_status,
            })
        return modules

    def _inventory(self, requirements: Dict[str, Any], metadata: Dict[str, Any], source: str) -> List[Dict[str, Any]]:
        prompt = f"""You are a requirements inventory agent. Return JSON only.

CUSTOMER: {metadata.get('company_name', '')}
PROJECT: {metadata.get('project_title', '')}
MODE: {self.template_type}

NORMALISED REQUIREMENTS:
{json.dumps(requirements, indent=2, default=str)}

AUTHORITATIVE SOURCE:
{source or '(none)'}

Return {{"capability_units":[{{"id":"CAP-001","name":"concise capability", "problem":"problem solved", "outcome":"observable output", "actors":[], "inputs":[], "requirements":[], "dependencies":[], "source_basis":[], "evidence_status":"Confirmed|Source Assumption|Proposed|Open", "disposition":"in_scope|future|optional|open", "independent_boundary":false, "boundary_basis":""}}]}}.

Inventory every distinct source-required capability, workflow, integration, data responsibility,
control, operational requirement, and explicitly deferred/future item exactly once. A source row
called a deliverable is still only a capability unit at this stage. Do not group units yet. Preserve
source identifiers, names, quantities, qualifications, status, and disposition. Do not add generic lifecycle work.
Set independent_boundary true only when the source supports a separate phase, release, deployment,
commercial hand-off, or acceptance event; explain that evidence in boundary_basis.
"""
        value = _json_object(self._call(prompt, "Scope Capability Inventory"))
        clean: List[Dict[str, Any]] = []
        seen = set()
        for index, item in enumerate(value.get("capability_units") or [], 1):
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                continue
            item_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(item.get("id") or f"CAP-{index:03d}"))[:40]
            if item_id in seen:
                item_id = f"CAP-{index:03d}"
            seen.add(item_id)
            clean.append({**item, "id": item_id})
        return clean

    def _classify(
        self,
        inventory: List[Dict[str, Any]],
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source: str,
        refinement_constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        boundary_evidence = self._boundary_evidence(source)
        prompt = f"""You are the independent solution-boundary architect. Return JSON only.

CUSTOMER: {metadata.get('company_name', '')}
PROJECT: {metadata.get('project_title', '')}
MODE: {self.template_type}

CAPABILITY INVENTORY:
{json.dumps(inventory, separators=(',', ':'), default=str)}

POTENTIAL DELIVERY-BOUNDARY EVIDENCE (locally extracted; validate against the source):
{boundary_evidence or '(none detected)'}

VALIDATED EXPLICIT SOURCE DELIVERABLES (preserve each; this list may be incomplete):
{json.dumps(self._explicit_source_deliverables(requirements, source), indent=2)}

EXPLICIT USER REFINEMENT CONSTRAINTS (mandatory when present):
{json.dumps(refinement_constraints or {}, indent=2, default=str)}

Return {{"discovered_capabilities":[], "deliverables":[{{"name":"outcome-oriented delivery package", "purpose":"brief business outcome and boundary", "boundary_type":"single_package|phase|release|deployment|acceptance|commercial_handoff", "separation_basis":"brief source-backed boundary", "modules":[{{"name":"cohesive mini-problem/workstream", "capability_ids":["CAP-001"], "task_statement":"brief implementation scope", "objective":"brief operating outcome", "evidence_status":"Confirmed|Source Assumption|Proposed|Open"}}]}}], "cross_cutting_decisions":[], "open_boundaries":[{{"capability_id":"CAP-999","reason":"future, optional or open item"}}]}}.

Classification rules:
- Assign every in_scope capability ID exactly once. Never omit or duplicate an ID.
- The supplied inventory is authoritative. Do not copy its requirements, source evidence, actors,
  inputs, outputs, dependencies or validation details into the plan; modules reference them by ID.
- Do not place future, optional or open capability IDs inside a delivery module; preserve them in open_boundaries.
- A deliverable is a separately deployable or acceptably complete business outcome, release, or phase.
- Features, channels, integrations, AWS layers, document rows, and workstreams are normally modules,
  not separate deliverables, when they share one design, deployment, demonstration and acceptance event.
- Create multiple deliverables only for credible independent phase, release, deployment, hand-off,
  commercial, timeline, go-live or acceptance boundaries. Do not target a count.
- EXPLICIT USER REFINEMENT CONSTRAINTS take precedence over inferred cohesion. When their
  constraint_source is explicit_source_deliverables, the customer-authored names and count are
  contractual boundaries: preserve them even when they share one implementation or acceptance event.
- Distinct explicitly labelled customer deliverables may represent independently reviewable business
  outcomes without separate deployments. Data migration, operational workflow capability, channel/email
  capability, and reporting/management capability are valid separate deliverables when the source names
  them that way. Place their detailed requirements beneath them as modules.
- Preserve every VALIDATED EXPLICIT SOURCE DELIVERABLE as a distinct named outcome. The list may be
  incomplete, so add another deliverable when the remaining capabilities form a comparably distinct,
  independently reviewable outcome; never reduce the plan merely to match the extracted list length.
- When returning more than one deliverable, use phase, release, deployment, acceptance, or
  commercial_handoff as boundary_type. `single_package` is valid only when exactly one deliverable exists.
- Do not mistake a generic artefact list, feature checklist, AWS layer, or table row for an explicit
  source deliverable; those remain modules or outputs.
- A table titled "Deliverables" is not proof that every row is a separate contractual deliverable.
  Architecture, chatbot build, channels, integrations, handover, analytics, testing, training and
  support rows normally describe modules or lifecycle workstreams. Group them by the fewest credible
  phase/release boundaries unless the rows themselves are explicitly numbered as Deliverable N,
  Phase N, Wave N or Release N.
- Strong split evidence includes explicit Deliverable/Phase/Wave labels; Day 1 versus later scope;
  a core platform followed by an extension; separate go-live or stabilisation sequencing; a distinct
  duration, commercial line, sign-off, dependency gate, target channel/surface, or deployment boundary.
- Use one deliverable when all capabilities are required for the same usable outcome and share the
  same implementation, go-live and acceptance boundary. A technology layer or workstream alone is not a split.
- A coherent later-phase package may be a deliverable even when some details are "To be confirmed",
  provided the source supplies a credible default phase, sequence or extension boundary. Preserve that
  uncertainty as Source Assumption/Open evidence and in open_boundaries; do not silently fold it into Day 1.
- Optional ideas with no committed/default phase, and future roadmap items that are not being delivered,
  remain open boundaries rather than deliverables. An assessment deliverable is distinct from implementing
  the assessed capability (for example, voice readiness versus voice implementation).
- A module is a cohesive mini-problem; combine units solved through the same workflow and technical change.
- Preserve future/optional/open status and do not invent facts or commitments.
- Return the smallest valid JSON needed to express grouping and boundaries. Never restate capability text.
"""
        return _json_object(self._call(prompt, "Scope Boundary Classification", max_tokens=12000))

    @staticmethod
    def _boundary_evidence(source: str) -> str:
        """Surface likely release-boundary statements without another model call."""
        signals = re.compile(
            r"\b(deliverable\s*\d+|phase\s*\d+|wave\s*\d+|day\s*1|go[- ]live|"
            r"stabili[sz]ation|sequential|subsequent|later phase|future phase|to be confirmed|"
            r"timeline|duration|acceptance|sign[- ]off|commercial|optional)\b",
            flags=re.I,
        )
        candidates: List[str] = []
        seen = set()
        for raw in re.split(r"[\r\n]+|(?<=[.!?])\s+", str(source or "")):
            line = re.sub(r"\s+", " ", raw).strip()
            key = line.casefold()
            if len(line) < 12 or key in seen or not signals.search(line):
                continue
            seen.add(key)
            candidates.append(line[:1200])
            if len(candidates) >= 40:
                break
        return "\n".join(f"- {item}" for item in candidates)

    @staticmethod
    def _module_fragmentation_issues(
        plan: Dict[str, Any], inventory: List[Dict[str, Any]]
    ) -> List[str]:
        """Detect inventory-to-heading mirroring without imposing a module cap."""
        modules = [
            module
            for deliverable in plan.get("deliverables") or [] if isinstance(deliverable, dict)
            for module in deliverable.get("modules") or [] if isinstance(module, dict)
        ]
        in_scope_count = sum(
            str(item.get("disposition") or "in_scope").casefold() == "in_scope"
            for item in inventory
        )
        if in_scope_count < 6 or len(modules) < 6:
            return []
        singleton_count = sum(len(module.get("capability_ids") or []) <= 1 for module in modules)
        mirrored = len(modules) / max(in_scope_count, 1)
        singleton_ratio = singleton_count / max(len(modules), 1)

        stopwords = {
            "and", "the", "for", "with", "requirements", "requirement", "implementation",
            "capabilities", "capability", "system", "platform", "management", "support",
        }
        repeated_topics: Dict[str, int] = {}
        for module in modules:
            words = {
                word for word in re.findall(r"[a-z0-9]+", str(module.get("name") or "").casefold())
                if len(word) >= 4 and word not in stopwords
            }
            for word in words:
                repeated_topics[word] = repeated_topics.get(word, 0) + 1
        families = sorted(word for word, count in repeated_topics.items() if count >= 3)
        issues = []
        if mirrored >= 0.8 and singleton_ratio >= 0.75:
            issues.append(
                "capability inventory is mirrored almost one-for-one as module headings instead of cohesive workstreams"
            )
        if families and singleton_ratio >= 0.6:
            issues.append(
                "related module families remain split across headings: " + ", ".join(families[:8])
            )
        return issues

    @staticmethod
    def _normalise_plan(plan: Dict[str, Any], inventory: List[Dict[str, Any]]) -> tuple[Dict[str, Any], List[str]]:
        dispositions = {
            str(item["id"]): str(item.get("disposition") or "in_scope").casefold()
            for item in inventory
        }
        expected = {item_id for item_id, disposition in dispositions.items() if disposition == "in_scope"}
        excluded = set(dispositions) - expected
        statuses = {str(item["id"]): str(item.get("evidence_status") or "") for item in inventory}
        assigned: List[str] = []
        clean_deliverables = []
        for deliverable in plan.get("deliverables") or []:
            if not isinstance(deliverable, dict) or not str(deliverable.get("name") or "").strip():
                continue
            modules = []
            for module in deliverable.get("modules") or []:
                if not isinstance(module, dict) or not str(module.get("name") or "").strip():
                    continue
                ids = [str(item) for item in module.get("capability_ids") or [] if str(item) in expected]
                assigned.extend(ids)
                modules.append({**module, "capability_ids": ids})
            if modules:
                clean_deliverables.append({**deliverable, "modules": modules})
        clean = {**plan, "deliverables": clean_deliverables}
        issues = []
        missing = sorted(expected - set(assigned))
        duplicates = sorted({item for item in assigned if assigned.count(item) > 1})
        raw_assigned = {
            str(capability_id)
            for deliverable in plan.get("deliverables") or [] if isinstance(deliverable, dict)
            for module in deliverable.get("modules") or [] if isinstance(module, dict)
            for capability_id in module.get("capability_ids") or []
        }
        if not clean_deliverables:
            issues.append("no valid deliverables")
        if missing:
            issues.append(f"unassigned capability IDs: {', '.join(missing)}")
        if duplicates:
            issues.append(f"duplicate capability IDs: {', '.join(duplicates)}")
        misplaced = sorted(raw_assigned & excluded)
        if misplaced:
            issues.append(f"future/optional/open capability IDs placed in scope: {', '.join(misplaced)}")
        forbidden_module_names = {"requirements", "inputs", "outputs", "validation evidence", "dependencies", "roles"}
        if any(str(module.get("name") or "").strip().casefold() in forbidden_module_names
               for deliverable in clean_deliverables for module in deliverable["modules"]):
            issues.append("generic reasoning categories used as modules")
        status_priority = {"Confirmed": 0, "Source Assumption": 1, "Proposed": 2, "Open": 3}
        for deliverable in clean_deliverables:
            for module in deliverable["modules"]:
                source_statuses = [statuses.get(capability_id) for capability_id in module["capability_ids"]]
                source_statuses = [status for status in source_statuses if status in status_priority]
                if source_statuses:
                    safest = max(source_statuses, key=status_priority.get)
                    if status_priority.get(str(module.get("evidence_status") or "Confirmed"), 0) < status_priority[safest]:
                        module["evidence_status"] = safest
        if len(clean_deliverables) > 1:
            valid_boundaries = {"phase", "release", "deployment", "acceptance", "commercial_handoff"}
            for item in clean_deliverables:
                if (
                    str(item.get("boundary_type") or "") == "single_package"
                    and str(item.get("separation_basis") or "").strip()
                ):
                    # The model often uses single_package to mean one cohesive
                    # work package inside a multi-deliverable SOW. In the plan
                    # schema that is an independently reviewable acceptance boundary.
                    item["boundary_type"] = "acceptance"
            if any(
                str(item.get("boundary_type") or "") not in valid_boundaries
                or not str(item.get("separation_basis") or "").strip()
                for item in clean_deliverables
            ):
                issues.append("multiple deliverables lack independent typed boundaries")
        for index, deliverable in enumerate(clean_deliverables, 1):
            name = re.sub(r"^\s*deliverable\s+\d+\s*[-:–—]\s*", "", str(deliverable["name"]).strip(), flags=re.I)
            deliverable["name"] = name
            deliverable["number"] = index
            deliverable["display_name"] = f"Deliverable {index} - {name}"
        return clean, issues

    def _repair(
        self,
        plan: Dict[str, Any],
        inventory: List[Dict[str, Any]],
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source: str,
        issues: List[str],
        refinement_constraints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prompt = f"""You are the final scope-boundary review authority. Return corrected JSON only.

AUDIT FAILURES: {json.dumps(issues)}
DRAFT PLAN: {json.dumps(plan, indent=2, default=str)}
CAPABILITY INVENTORY: {json.dumps(inventory, indent=2, default=str)}
REQUIREMENTS: {json.dumps(requirements, indent=2, default=str)}
SOURCE: {source or '(none)'}
EXPLICIT USER REFINEMENT CONSTRAINTS (mandatory when present):
{json.dumps(refinement_constraints or {}, indent=2, default=str)}

Return the same plan shape. Assign every in_scope capability ID exactly once and preserve future,
optional or open IDs only in open_boundaries. Merge capability buckets that
share a design, deployment, demonstration and acceptance event. Keep separate deliverables only for
a real independent phase, release, deployment, hand-off, commercial or acceptance boundary. Preserve
all inventory facts and status labels; do not add capabilities or drop modules to pass the audit.
An unnumbered table or checklist headed "Deliverables" does not establish separate contractual
boundaries. Architecture, platform build, channels, integrations, handover, analytics, testing,
training and support should remain modules of the same implementation phase unless the source gives
concrete, explicitly numbered delivery-package sequencing. Prefer a core/Day-1 package plus a later
extension package when that is the actual source-backed boundary; do not add a third package merely
for design, testing, training, hypercare, support or continuous improvement.

Module consolidation rules:
- Do not mirror capability inventory rows as one module per row. A module is a cohesive implementation
  workstream and should own all capability IDs solved through the same design and operating workflow.
- Merge channel matrices, channel variants and brand/surface deployments when they share one channel
  framework; preserve genuine phase boundaries at the deliverable level.
- Merge conversational intelligence, context, intent, personalisation and language functions when they
  form one bot/AI engine workstream. Merge live-agent integration, routing, handover, context transfer,
  assist and escalation when they form one agent-service workstream.
- Merge related reporting, conversation analytics, agent analytics and monitoring requirements into a
  coherent observability/analytics workstream unless the source gives them independent acceptance.
- Vendor questionnaire rows, capability matrices and proposal-document requirements are constraints or
  source evidence, not standalone implementation modules unless the engagement explicitly commissions
  an independent evaluation or documentation outcome.
- There is no minimum or maximum module count. Use the smallest natural set that preserves distinct
  architecture responsibilities, inputs/outputs and acceptance boundaries without creating vague buckets.
"""
        return _json_object(self._call(prompt, "Scope Boundary Audit"))
