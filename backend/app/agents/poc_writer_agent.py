"""Template-driven SOW writer with bounded, section-level generation."""

from __future__ import annotations

import html
import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import boto3

from app.core.bedrock_llm import BedrockLLM
from app.core.section_formats import presentation_contract
from app.core.document_context import select_section_evidence
from app.core.sow_editorial import (
    editorial_category, section_editorial_contract, strip_bullet_leadins,
)
from app.core.sow_quality import (
    clean_markdown_preserving_structure,
    classify_complexity,
    normalize_requirements,
    remove_missing_information_disclaimers,
    remove_client_facing_meta_language,
    section_quality_issues,
    validate_generated_sections,
)
from app.core.sow_presentation import strip_text_diagrams
from app.core.sow_section_preferences import (
    SECTION_LABELS,
    excluded_section_labels,
    parse_selected_section_ids,
    section_catalogue,
    section_category,
)


def _normalise_heading_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


class SectionType(Enum):
    STATIC = "STATIC"
    GENERATED = "GENERATED"
    TABLE = "TABLE"
    STATIC_TABLE = "STATIC_TABLE"
    HYBRID = "HYBRID"


class ProjectComplexity(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    ENTERPRISE = "enterprise"


class TemplateSection:
    def __init__(self, name: str, content: str, metadata: Dict[str, Any], order: int):
        self.name = name
        self.content = content
        self.metadata = metadata
        self.order = order
        self.has_explicit_metadata = metadata.get("_explicit", False)
        try:
            self.section_type = SectionType[metadata.get("type", "GENERATED")]
        except KeyError:
            self.section_type = SectionType.GENERATED
        self.dependencies = metadata.get("depends_on", [])
        self.context = metadata.get("context", "")

    def __repr__(self):
        return f"TemplateSection({self.name!r}, type={self.section_type.value})"


class POCWriterAgent:
    """Generate each substantive section against one shared requirements baseline.

    The former implementation requested the entire document as one enormous JSON
    object.  This implementation uses bounded plain-Markdown calls, retries only the
    section that fails a deterministic gate, and never mutates the parsed template.
    """

    def __init__(
        self,
        config,
        template_type: str = "POC",
        custom_template_markdown: Optional[str] = None,
        custom_template_sections: Optional[List[Dict[str, Any]]] = None,
    ):
        self.config = config
        self.template_type = (template_type or "POC").upper()
        self.bedrock = boto3.client(
            service_name="bedrock-runtime",
            region_name=config.BEDROCK_REGION,
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
            config=config.BOTO_CONFIG,
        )
        self.llm = BedrockLLM(config, self.bedrock)
        self.template_raw = self._load_template()
        self.global_template_contract = self._extract_global_template_contract(self.template_raw)
        self.sections = self._parse_template()
        self._merge_custom_template(
            custom_template_markdown or "", custom_template_sections or []
        )
        for item in section_catalogue():
            category_id = str(item.get("id") or "")
            if not category_id:
                continue
            matching = [section for section in self.sections if self._section_category(section) == category_id]
            if matching:
                custom_instruction = str(item.get("prompt") or "").strip()
                if custom_instruction:
                    for section in matching:
                        if section.section_type in {SectionType.STATIC, SectionType.STATIC_TABLE}:
                            continue
                        section.content = f"{section.content}\n\nAdministrator instruction: {custom_instruction}".strip()
                continue
            label = str(item.get("label") or category_id.replace("_", " ").title())
            prompt = str(item.get("prompt") or f"Write a concise, source-grounded {label} section.")
            self.sections.append(TemplateSection(
                label,
                prompt,
                {"type": "GENERATED", "category_id": category_id, "_explicit": True},
                len(self.sections),
            ))

        for section in self.sections:
            if self._section_category(section) == 'timelines_deliverables':
                section.name = 'Project Timeline'

    @staticmethod
    def _section_category(section: TemplateSection) -> Optional[str]:
        return section.metadata.get("category_id") or section_category(section.name)

    def _load_template(self) -> str:
        if self.template_type == "PROD":
            template_file = self.config.PRODUCTION_TEMPLATE_FILE
        elif self.template_type == "POC_TO_PROD":
            template_file = getattr(self.config, "POC_TO_PROD_TEMPLATE_FILE", self.config.PRODUCTION_TEMPLATE_FILE)
        else:
            template_file = self.config.POC_TEMPLATE_FILE
        if not template_file.exists():
            raise FileNotFoundError(f"SOW template not found: {template_file}")
        content = template_file.read_text(encoding="utf-8")
        print(f"✓ Loaded template: {template_file.name}")
        return content

    @staticmethod
    def _extract_global_template_contract(template: str) -> str:
        """Return the non-rendered authoring contract embedded in the template.

        The benchmark PDF is a design reference during development, not a runtime
        dependency.  Its observable content and formatting rules live between
        explicit sentinels in the Markdown template and are included in every
        section-generation prompt.
        """
        match = re.search(
            r"<!--\s*BEGIN_GLOBAL_TEMPLATE_CONTRACT\s*-->(.*?)"
            r"<!--\s*END_GLOBAL_TEMPLATE_CONTRACT\s*-->",
            template or "",
            re.I | re.S,
        )
        return match.group(1).strip() if match else ""

    def _parse_template(self) -> List[TemplateSection]:
        decoded = html.unescape(self.template_raw or "")
        decoded = re.sub(
            r"<!--\s*BEGIN_GLOBAL_TEMPLATE_CONTRACT\s*-->.*?"
            r"<!--\s*END_GLOBAL_TEMPLATE_CONTRACT\s*-->",
            "",
            decoded,
            flags=re.I | re.S,
        )
        lines = decoded.splitlines()
        marker = re.compile(r"^\s*\[META_([A-Z_]+)(?:_(.+?))?\]\s*$", re.I)
        sections: List[TemplateSection] = []
        pending_meta: Dict[str, Any] = {}
        name: Optional[str] = None
        body: List[str] = []

        def flush() -> None:
            nonlocal name, body, pending_meta
            if name is None:
                return
            metadata = pending_meta or self._infer_metadata(name, "\n".join(body))
            sections.append(TemplateSection(name, "\n".join(body).strip(), metadata, len(sections)))
            name, body, pending_meta = None, [], {}

        for line in lines:
            match = marker.match(line)
            if match:
                if name is not None:
                    flush()
                pending_meta = self._parse_meta_marker(match.group(1).upper(), match.group(2) or "")
                pending_meta["_explicit"] = True
                continue
            if line.startswith("## "):
                flush()
                name = line[3:].strip()
                continue
            if name is not None:
                body.append(line)
        flush()
        print(f"✓ Parsed {len(sections)} template sections")
        return sections

    def _merge_custom_template(
        self, markdown: str, section_definitions: List[Dict[str, Any]]
    ) -> None:
        """Merge supplementary guidance without replacing protected base content."""
        if not markdown.strip() or not section_definitions:
            return
        definitions = {
            _normalise_heading_text(item.get("label")): item
            for item in section_definitions
            if item.get("id") and item.get("label")
        }
        chunks = re.split(r"(?m)^##\s+", markdown)
        for chunk in chunks[1:]:
            lines = chunk.splitlines()
            name = lines[0].strip()
            definition = definitions.get(_normalise_heading_text(name))
            if not definition:
                continue
            category_id = str(definition["id"])
            content = "\n".join(lines[1:]).strip()
            content = re.sub(r"(?im)^\s*\[META_[A-Z_]+(?:_[^\]]+)?\]\s*", "", content).strip()
            base_section_id = str(definition.get("base_section_id") or "")
            match = next((
                item for item in self.sections
                if (
                    base_section_id
                    and self._section_category(item) == base_section_id
                ) or _normalise_heading_text(item.name) == _normalise_heading_text(name)
            ), None)
            if match:
                # The base template remains authoritative. The extracted SOW
                # contributes reusable guidance to the same rendered section.
                match.metadata.setdefault("selection_ids", []).append(category_id)
                protected = self._section_category(match) in {"about_shellkode", "service_agreement", "change_order", "project_plan_termination", "marketing_authorization", "terms_conditions"} or "{PROJECT_TITLE}" in match.name
                if content and not protected:
                    match.metadata["custom_template"] = True
                    match.content = (
                        "CUSTOM TEMPLATE GUIDANCE (authoritative when it conflicts with generic base guidance):\n"
                        f"{content}\n\nBASE TEMPLATE GUIDANCE (use only where the custom template is silent):\n"
                        f"{match.content}"
                    ).strip()
                    if match.section_type in {SectionType.STATIC, SectionType.STATIC_TABLE}:
                        match.section_type = SectionType.GENERATED
                        match.metadata["type"] = "GENERATED"
                continue
            self.sections.append(TemplateSection(
                name,
                content or f"Write a concise, client-ready {name} section.",
                {
                    "type": "GENERATED",
                    "category_id": category_id,
                    "selection_ids": [category_id],
                    "custom_template": True,
                    "_explicit": True,
                },
                len(self.sections),
            ))

    @staticmethod
    def _parse_meta_marker(meta_type: str, extra: str) -> Dict[str, Any]:
        valid = {item.name for item in SectionType}
        if meta_type not in valid:
            for candidate in sorted(valid, key=len, reverse=True):
                if meta_type.startswith(candidate + "_"):
                    extra = extra or meta_type[len(candidate) + 1:]
                    meta_type = candidate
                    break
        metadata: Dict[str, Any] = {"type": meta_type if meta_type in valid else "GENERATED"}
        if extra:
            metadata["context"] = extra.lower()
        return metadata

    @staticmethod
    def _infer_metadata(name: str, content: str) -> Dict[str, Any]:
        has_table = bool(re.search(r"(?m)^\s*\|.+\|\s*$", content))
        has_instruction = bool(re.search(
            r"\b(generate|write|include|derive|output|rules?|structure|using objective)\b",
            content,
            re.I,
        ))
        if has_table and has_instruction:
            return {"type": "TABLE", "_explicit": False}
        if has_table:
            return {"type": "STATIC_TABLE", "_explicit": False}
        if has_instruction:
            return {"type": "GENERATED", "_explicit": False}
        if re.search(r"\{[A-Z_]+\}", content):
            return {"type": "HYBRID", "_explicit": False}
        return {"type": "STATIC", "_explicit": False}

    def generate_poc(
        self,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        supporting_context: Optional[str] = None,
        selected_sow_sections: Optional[List[str]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        scope_architecture_plan: Optional[Dict[str, Any]] = None,
        refinement_plan: Optional[Dict[str, Any]] = None,
        phase_callback: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        mode = self.template_type
        selected_preferences = parse_selected_section_ids(selected_sow_sections, mode)
        selected_set = set(selected_preferences)
        req = normalize_requirements(requirements, requirements.get("_original_objective", metadata.get("objective", "")), mode)
        req["_complexity"] = classify_complexity(req)
        req["_selected_sow_sections"] = selected_preferences
        req["_excluded_sow_sections"] = excluded_section_labels(selected_preferences, mode)
        metadata = dict(metadata)
        metadata["selected_sow_sections"] = selected_preferences
        metadata["author_org_short"] = self._short_name(metadata.get("author_org", ""))
        metadata["company_name_short"] = self._short_name(metadata.get("company_name", ""))
        metadata.setdefault("project_title", "Project Statement of Work")

        eligible_sections = [
            section for section in self.sections
            if (
                self._section_category(section) is None
                or bool(self._selection_ids(section) & selected_set)
            ) and (
                req.get("ui_required") or section.name not in {
                    "User Interaction Layer", "User Access & Interaction Layer", "UI Development"
                }
            )
        ]
        active_sections = self._order_sections_by_preference(
            eligible_sections, selected_preferences
        )
        self.selected_section_preferences = selected_preferences
        self.excluded_section_preferences = excluded_section_labels(selected_preferences, mode)
        output: Dict[str, str] = {}
        self.solution_architecture_context = ""
        rendered: Dict[int, Tuple[str, str, bool]] = {}
        generation_jobs: List[Tuple[int, TemplateSection, str]] = []
        consistency_notes = self._consistency_notes(req, metadata, selected_set)
        supplied_scope_plan = scope_architecture_plan is not None
        self.scope_architecture_plan = dict(scope_architecture_plan or {})
        self.refinement_plan = dict(refinement_plan or {})
        if (
            not supplied_scope_plan
            and not self.scope_architecture_plan
            and any(self._section_category(section) == "scope_of_work" for section in active_sections)
        ):
            scope_evidence = self._context_excerpt(
                supporting_context,
                section_name="Scope of Work deliverables modules workflows inputs outputs",
                requirements=req,
                limit=max(getattr(self.config, "SECTION_EVIDENCE_MAX_CHARS", 48_000), 64_000),
            )
            self.scope_architecture_plan = self._architect_scope(
                req, metadata, scope_evidence
            )

        print(f"\n🚀 Starting {mode} SOW generation ({len(active_sections)} sections)")
        for index, section in enumerate(active_sections, 1):
            key = self._section_key(section.name, metadata)
            if key == "toc_structure":
                content = self._dynamic_toc(active_sections, metadata)
            elif section.section_type in {SectionType.STATIC, SectionType.STATIC_TABLE}:
                content = self._replace_placeholders(section.content, metadata, req)
            elif section.section_type == SectionType.HYBRID and not self._needs_generation(section.content):
                content = self._replace_placeholders(section.content, metadata, req)
                # A hybrid section backed only by an optional metadata field must
                # not silently become an empty body section.  Empty selected
                # sections otherwise leave a stale TOC entry with no bookmark.
                if not content.strip():
                    generation_jobs.append((index, section, key))
                    continue
            else:
                generation_jobs.append((index, section, key))
                continue
            # Reference clauses are literal contractual text, not LLM prose.
            protected = self._section_category(section) in {"service_agreement", "change_order", "project_plan_termination", "marketing_authorization", "terms_conditions", "about_shellkode"}
            rendered[index] = (key, content if protected else self._clean_content(content, section.name), False)

        worker_count = self._section_worker_count(len(generation_jobs))
        if generation_jobs:
            print(
                f"   ⚡ Generating {len(generation_jobs)} LLM-authored sections "
                f"with {worker_count} concurrent worker(s)"
            )

        def generate_job(job: Tuple[int, TemplateSection, str]) -> Tuple[int, str, str]:
            index, section, key = job
            print(f"  [{index}/{len(active_sections)}] {section.name}")
            source_context = self._context_excerpt(
                supporting_context,
                section_name=section.name,
                requirements=req,
                limit=(getattr(self.config, "SECTION_EVIDENCE_MAX_CHARS", 48_000)
                       if self._section_category(section) == "scope_of_work" else 12000),
            )
            content = self._generate_section(
                section, req, metadata, source_context, consistency_notes
            )
            resolved_section_name = self._replace_placeholders(
                section.name, metadata, req
            )
            cleaned = self._clean_content(content, resolved_section_name)
            # A model can occasionally return only the requested heading.  The
            # cleaner correctly removes that duplicate heading, but the result
            # must still contain a body if the user selected the section.
            if not cleaned.strip():
                if self._section_category(section) == "about_client":
                    cleaned = self._about_company_fallback(metadata)
            if not cleaned.strip() and self._section_category(section) != 'success_criteria':
                raise RuntimeError(
                    f"{resolved_section_name} returned no usable content; generation halted"
                )
            return index, key, cleaned

        # The authored design is a dependency, not a concurrent sibling of scope.
        total_generation_jobs = len(generation_jobs)
        completed = 0
        for job in list(generation_jobs):
            if self._section_category(job[1]) == "architecture_diagram":
                index, key, content = generate_job(job)
                rendered[index] = (key, content, True)
                self.solution_architecture_context += content + "\n"
                generation_jobs.remove(job)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total_generation_jobs, job[1].name)

        if worker_count == 1:
            for job in generation_jobs:
                index, key, content = generate_job(job)
                rendered[index] = (key, content, True)
                completed += 1
                if progress_callback:
                    progress_callback(completed, total_generation_jobs, job[1].name)
        else:
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="sow-section",
            ) as executor:
                future_jobs = {
                    executor.submit(copy_context().run, generate_job, job): job
                    for job in generation_jobs
                }
                for future in as_completed(future_jobs):
                    job = future_jobs[future]
                    index, section, key = job
                    try:
                        result_index, result_key, content = future.result()
                    except Exception as exc:
                        for pending in future_jobs:
                            pending.cancel()
                        raise RuntimeError(
                            f"SOW section generation failed for {section.name}; generation halted: {exc}"
                        ) from exc
                    rendered[result_index] = (result_key, content, True)
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, total_generation_jobs, section.name)
                    print(
                        f"   ✓ Completed LLM section {completed}/{total_generation_jobs}: "
                        f"{section.name}"
                    )

        if not total_generation_jobs and progress_callback:
            progress_callback(1, 1, "Static document sections")

        # Reassemble strictly in the user's selected order; concurrent completion
        # order must never affect the document or preview sequence.
        for index in range(1, len(active_sections) + 1):
            key, content, _ = rendered[index]
            output[key] = content

        self.review_context = {'requirements': req, 'mode': mode, 'metadata': metadata,
                              'scope_plan': getattr(self, 'scope_architecture_plan', {}),
                              '_review_source_text': supporting_context or '',
                              'instructions': requirements.get('_generation_guidance', '')}
        if phase_callback:
            phase_callback('Checking and correcting SOW consistency')
        editorial_omissions = self._review_document_relevance(output, active_sections, metadata)
        from app.core.section_formats import sequence_gantt_markdown
        for section in active_sections:
            if self._section_category(section) == 'project_team_effort':
                key = self._section_key(section.name, metadata)
                if isinstance(output.get(key), str):
                    output[key] = self._clean_content(output[key], section.name)
            if self._section_category(section) == 'timelines_deliverables':
                key = self._section_key(section.name, metadata)
                if isinstance(output.get(key), str):
                    output[key] = sequence_gantt_markdown(output[key])
        expected_generated_keys = {
            key for key, _content, generated in rendered.values() if generated
        } - editorial_omissions
        missing, issues = validate_generated_sections(
            output, mode, required_keys=expected_generated_keys
        )
        # Missing output is a real failure. Stylistic checks are best-effort
        # repair signals and must not discard an otherwise usable SOW.
        if missing:
            details = "; ".join(f"missing {item}" for item in missing)
            raise RuntimeError(f"SOW generation quality gate failed; generation halted: {details}")
        output["generation_quality_summary"] = self._quality_summary([], getattr(self, '_review_issues', []), req)
        print(f"✅ Assembly complete - {len(output)} sections")
        return output

    def _review_document_relevance(self, output, sections, metadata):
        """Apply bounded, context-aware corrections instead of a whole-SOW rewrite."""
        from app.agents.sow_reviewer_agent import SOWReviewerAgent
        categories = {}
        for section in sections:
            category = editorial_category(section.name, self._section_category(section))
            key = self._section_key(section.name, metadata)
            if (section.section_type in {SectionType.STATIC, SectionType.STATIC_TABLE}
                    or section.metadata.get('custom_template')
                    or category in {'about_shellkode', 'service_agreement', 'change_order',
                                    'project_plan_termination', 'marketing_authorization',
                                    'terms_conditions', 'aws_pricing'}
                    or key not in output):
                continue
            if category == 'success_criteria' and not output[key].strip():
                # No source-backed targets is a deliberate blank, not an
                # invitation for the reviewer to invent acceptance conditions.
                continue
            refinement = getattr(self, 'refinement_plan', None)
            if refinement and self._section_category(section) not in set(refinement.get('affected_sections') or []):
                continue
            if category:
                categories[key] = category
        if not categories:
            return set()
        reviewer = SOWReviewerAgent(self.config)
        reviewed = reviewer.review(
            output, categories, getattr(self, 'review_context', {'metadata': metadata}))
        audit = getattr(reviewer, 'last_review_audit', {})
        self._review_issues = [f'Review incomplete: {key}' for key in audit.get('incomplete_sections', [])]
        self._review_issues.extend(f'Correction rejected: {key}' for key in audit.get('rejected_sections', []))
        self._review_issues.extend(f'Formatting requires review: {key}' for key in audit.get('remaining_format_issues', {}))
        output.update(reviewed)
        return set()

    def _order_sections_by_preference(
        self,
        sections: List[TemplateSection],
        selected_preferences: List[str],
    ) -> List[TemplateSection]:
        """Keep fixed front matter first, then group body sections in UI order."""
        front_matter: List[TemplateSection] = []
        sections_by_category: Dict[str, List[TemplateSection]] = {
            category: [] for category in selected_preferences
        }

        for section in sections:
            category = self._section_category(section)
            if category is None:
                front_matter.append(section)
            else:
                matching = next(
                    (item for item in selected_preferences if item in self._selection_ids(section)),
                    None,
                )
                category = matching or category
            if category in sections_by_category:
                # A selectable area can span several template sections. Keep
                # those sections together and retain their internal template
                # order while moving the whole group to the requested position.
                sections_by_category[category].append(section)

        return front_matter + [
            section
            for category in selected_preferences
            for section in sections_by_category.get(category, [])
        ]

    @classmethod
    def _selection_ids(cls, section: TemplateSection) -> set[str]:
        values = set(str(item) for item in section.metadata.get("selection_ids", []) if item)
        category = cls._section_category(section)
        if category:
            values.add(category)
        return values

    def _section_worker_count(self, job_count: int) -> int:
        configured = getattr(self.config, "SOW_SECTION_WORKERS", 2)
        try:
            configured = int(configured)
        except (TypeError, ValueError):
            configured = 2
        return max(1, min(configured, 8, max(1, job_count)))

    @staticmethod
    def _consistency_notes(
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        selected_sections: Optional[set[str]] = None,
    ) -> List[str]:
        """Create immutable cross-section notes suitable for concurrent authors."""
        notes = [
            f"Use the project name {metadata.get('project_title', 'Project')!r} consistently.",
            "The authoritative requirements baseline overrides any generic recommendation.",
        ]
        duration = None
        if selected_sections is None or "timelines_deliverables" in selected_sections:
            duration = requirements.get("duration_weeks") or requirements.get("planning_duration_weeks")
        if duration:
            label = "confirmed" if requirements.get("duration_weeks") else "planning assumption"
            notes.append(f"Duration is {duration} weeks ({label}); do not present it differently.")
        services = requirements.get("aws_services") or []
        if services:
            notes.append("Named AWS services: " + ", ".join(map(str, services)) + ".")
        return notes

    def _dynamic_toc(
        self,
        active_sections: List[TemplateSection],
        metadata: Dict[str, Any],
    ) -> str:
        """Build a contiguous TOC containing only sections selected for this SOW."""
        lines: List[str] = []
        counter = 0
        for section in active_sections:
            key = self._section_key(section.name, metadata)
            if key in {"cover_page", "toc_structure"}:
                continue
            title = self._replace_placeholders(section.name, metadata)
            title = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", title).strip()
            counter += 1
            lines.append(f"{counter}. {title}")
        return "\n".join(lines)

    def _generate_section(
        self,
        section: TemplateSection,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source_context: str,
        prior_summaries: List[str],
    ) -> str:
        if self._section_key(section.name, metadata) == "aws_pricing":
            from app.pricing import render_aws_pricing_section
            return render_aws_pricing_section(requirements.get("aws_pricing_result") or {})
        prompt = self._build_individual_prompt(
            section, requirements, metadata, source_context,
            prior_context="\n".join(prior_summaries[-4:]),
        )
        architected_scope = (
            self._section_key(section.name, metadata) == "scope_of_work"
            and (getattr(self, "scope_architecture_plan", {}) or {}).get("deliverables")
        )
        if architected_scope:
            content = self._generate_scope_deliverables(
                requirements, metadata, source_context, prior_summaries
            )
        else:
            content = self._call_bedrock(
                prompt,
                max_tokens=self._section_token_budget(section),
                model_id=getattr(self.config, "FAST_MODEL_ID", None) if self._section_category(section) in {
                    "about_client", "business_benefits", "raci_matrix", "customer_responsibilities",
                    "contacts_reporting", "project_team_effort", "timelines_deliverables"
                } else getattr(self.config, "WRITER_MODEL_ID", None),
                call_name=f"SOW Section - {section.name}",
            )
        if self._section_category(section) == 'success_criteria' and content.strip() in {
            '[NO_SOURCE_BACKED_SUCCESS_CRITERIA]', '[NO_QUANTITATIVE_TARGETS]',
        }:
            content = ''  # Internal transport sentinel, never client-facing content.
        resolved_name = self._replace_placeholders(section.name, metadata, requirements)
        content = self._clean_content(content, resolved_name)
        issues = self._authoring_issues(content, section)
        about_client = self._section_category(section) == "about_client"
        if issues and about_client and not architected_scope:
            # Enforce the two-paragraph profile through focused retries, but do
            # not fail the entire document because of a presentational miss.
            for attempt in range(2):
                detected = "; ".join(issues)
                retry_prompt = (
                    prompt
                    + "\n\nSelf-review the previous draft. The deterministic validator found: "
                    + detected
                    + ". Rewrite it as exactly two short factual prose paragraphs. "
                    "Describe only the company; remove headings, bullets, project context, engagement "
                    "language, disclaimers and unsupported claims. Silently verify that every finding "
                    "is resolved, then return only the two corrected paragraphs.\n\n"
                    + content[:4000]
                )
                try:
                    revised = self._call_bedrock(
                        retry_prompt,
                        max_tokens=600,
                        model_id=getattr(self.config, "WRITER_MODEL_ID", None),
                        call_name=f"SOW Section - {section.name} repair {attempt + 1}",
                    )
                except Exception:
                    break
                revised = self._clean_content(revised, resolved_name)
                if revised:
                    content = revised
                issues = self._authoring_issues(content, section)
                if not issues:
                    break
        if not content.strip() and about_client:
            content = self._about_company_fallback(metadata)
        if not content.strip() and self._section_category(section) != 'success_criteria':
            raise RuntimeError(f"{section.name} returned empty content; generation halted")
        return content

    @staticmethod
    def _about_company_fallback(metadata: Dict[str, Any]) -> str:
        """Keep optional company enrichment from aborting an otherwise valid SOW."""
        supplied = str(metadata.get("company_description") or "").strip()
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", supplied) if item.strip()]
        if paragraphs:
            return "\n\n".join(re.sub(r'^[-*]\s+', '', p) for p in paragraphs[:2])
        company = str(metadata.get("company_name") or "The customer").strip()
        return f"{company} is the client organisation."

    def _generate_scope_deliverables(
        self,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source_context: str,
        prior_summaries: List[str],
    ) -> str:
        """Expand each architected deliverable independently, then assemble in plan order."""
        plan = getattr(self, "scope_architecture_plan", {}) or {}
        from app.core.authoring_context import authoring_facts
        generation_guidance = requirements.get('_generation_guidance') or '(none)'
        requirements = authoring_facts(requirements)
        blocks: List[str] = []
        deliverables = plan.get("deliverables") or []
        multiple_deliverables = len(deliverables) > 1
        if multiple_deliverables:
            rows = ["| Deliverable | Outcome |", "|---|---|"]
            for deliverable_index, deliverable in enumerate(deliverables, 1):
                name = re.sub(
                    r"^\s*deliverable\s+\d+\s*[-:–—]\s*", "",
                    str(deliverable.get("name") or "").strip(), flags=re.I,
                ) or f"Work Package {deliverable_index}"
                outcome = str(deliverable.get("purpose") or "").strip()
                values = [f"Deliverable {deliverable_index} - {name}", outcome]
                rows.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in values) + " |")
            blocks.append("\n".join(rows))

        for deliverable_index, deliverable in enumerate(deliverables, 1):
            modules = deliverable.get("modules") or []
            deliverable_name = re.sub(
                r"^\s*deliverable\s+\d+\s*[-:–—]\s*",
                "",
                str(deliverable.get("name") or "").strip(),
                flags=re.I,
            )
            display_name = str(
                deliverable.get("display_name")
                or f"Deliverable {deliverable_index} - {deliverable_name}"
            )
            structure_instruction = (
                f"Return only Markdown for this deliverable, beginning with `### {display_name}`.\n"
                "Create exactly one `#### <Module Name>` heading for every module in the supplied blueprint, in order."
                if multiple_deliverables else
                "Return only Markdown for the modules. Do not emit a Deliverable heading or wrapper.\n"
                "Create exactly one `### <Module Name>` heading for every module in the supplied blueprint, in order."
            )
            prompt = f"""You are a principal solutions architect writing one deliverable within Scope of Work.
{structure_instruction}
{section_editorial_contract('scope_of_work')}

CUSTOMER: {metadata.get('company_name', '')}
PROJECT: {metadata.get('project_title', '')}
MODE: {self.template_type}

EXPLICIT USER REFINEMENT INSTRUCTIONS:
{generation_guidance}

DELIVERABLE BLUEPRINT:
{json.dumps(deliverable, indent=2, default=str)}

CROSS-CUTTING DECISIONS AND OPEN BOUNDARIES:
{json.dumps({key: plan.get(key, []) for key in ('cross_cutting_decisions', 'open_boundaries')}, indent=2, default=str)}

AUTHORITATIVE REQUIREMENTS:
{json.dumps(requirements, indent=2, default=str)}

SOURCE EVIDENCE:
{source_context or '(none)'}

SOLUTION DESIGN CONTEXT:
{getattr(self, 'solution_architecture_context', '') or '(Use the shared blueprint and authoritative requirements; no separate architecture narrative selected.)'}
Use this design to make each module's implementation consistent with the chosen runtime, storage and integration boundaries.
It is context, not a coverage checklist: mention an AWS service only when it clarifies that module's action or interface.
Do not add modules or bullets merely to cover services; shared infrastructure setup belongs once in the appropriate workstream.
Source requirements and explicit scope boundaries override any unsupported proposal in this narrative.

CONSISTENCY NOTES:
{chr(10).join(prior_summaries[-4:]) or '(none)'}

For each module, think through the delivery boundary, actors, triggering inputs, architecture/functionality requirements, implementation actions, operating output, dependencies, exceptions and validation evidence. Express only direct implementation-scope actions. Do not narrate the reasoning framework, source history, client pain points or negative impacts.

Module writing rules:
- Do not create standalone or inline pseudo-sections named Proposed Approach, Proposed Implementation, Implementation Approach, Key Outputs, Dependencies, Validation Evidence, Roles, Inputs, Requirements, or similar categories.
- Do not repeat the module heading in an opening paragraph. Include an opening sentence only when it establishes a boundary that the bullets cannot express clearly.
- Each bullet must add a distinct scope action, business rule, integration, boundary, qualification, or acceptance-relevant outcome. Remove any bullet that merely restates another bullet in different words.
- Every bullet must be one sentence of no more than 25 words and short enough to render in one or two lines.
- Combine closely related actions into one bullet where separating them adds no scope clarity. For example: `- Configure platform and integration monitoring with alerts to the agreed support channels.`
- Do not add bold summary labels before bullets. Start directly with the action and retain necessary subjects in the sentence.
- Integrate a unique dependency, proposal status, open point, output, or validation condition into the relevant implementation bullet instead of repeating category lists at the end of every module.
- Avoid exhaustive technology catalogues and adjectives such as comprehensive or enterprise-grade unless the evidence defines their meaning. Name an AWS service only when it represents a confirmed or clearly labelled Proposed design decision.
- Preserve the complete source scope, but say each requirement once in the module where it naturally belongs. Do not repeat the same capability in Deliverables, module introductions, approach, outputs and validation wording.

Preserve all source-specific workflows, business rules, systems, data, thresholds, roles, channels and exceptions assigned to the module. Keep unresolved decisions in Open Clarifications rather than describing missing inputs or confirmation status in scope. Do not invent facts or contractual commitments. Do not add unrelated lifecycle boilerplate. Use British Indian English and standard unordered Markdown bullets, not numbered lists. Tables are optional and only for genuinely comparable source requirements.
"""
            # Each deliverable receives its own output allowance, preventing a
            # large multi-deliverable scope from being truncated by one call.
            # Scope must remain concise and preview-safe. This is an output
            # ceiling, not a required word/module count.
            token_budget = min(12000, max(3500, len(modules) * 1200))
            block = self._call_bedrock(
                prompt,
                max_tokens=token_budget,
                model_id=getattr(self.config, "WRITER_MODEL_ID", None),
                call_name=f"Scope Deliverable {deliverable_index}",
            ).strip()
            expected_modules = [str(item.get("name") or "").strip() for item in modules]
            block_key = _normalise_heading_text(block)
            missing_deliverable_heading = (
                multiple_deliverables and _normalise_heading_text(display_name) not in block_key
            )
            missing_modules = [
                name for name in expected_modules
                if name and _normalise_heading_text(name) not in block_key
            ]
            if block and (missing_deliverable_heading or missing_modules):
                omissions = list(missing_modules)
                if missing_deliverable_heading:
                    omissions.insert(0, f"the exact heading '{display_name}'")
                retry_structure = (
                    "use the exact requested deliverable heading"
                    if multiple_deliverables else
                    "do not add a Deliverable 1 wrapper; use each module as a level-three heading"
                )
                retry_prompt = (
                    prompt
                    + "\n\nThe previous draft omitted or misformatted: "
                    + ", ".join(omissions)
                    + f". Rewrite this deliverable completely, {retry_structure}, "
                    "and include every supplied module exactly once using the requested heading levels.\n\n"
                    + block[:12000]
                )
                revised = self._call_bedrock(
                    retry_prompt,
                    max_tokens=token_budget,
                    model_id=getattr(self.config, "FALLBACK_MODEL_ID", None),
                ).strip()
                if revised:
                    block = revised
                block_key = _normalise_heading_text(block)
                remaining_modules = [
                    name for name in expected_modules
                    if name and _normalise_heading_text(name) not in block_key
                ]
                if remaining_modules:
                    raise RuntimeError(
                        f"Scope Deliverable {deliverable_index} omitted required modules after validation: "
                        + ", ".join(remaining_modules)
                    )
            structure_issues = self._scope_block_structure_issues(block)
            if block and structure_issues:
                compact_prompt = (
                    prompt
                    + "\n\nRewrite the draft to remove these structural problems: "
                    + "; ".join(structure_issues)
                    + ". Preserve every source-backed scope item and every module, but remove repetition "
                    "and integrate status, dependencies, outputs and validation into the relevant direct bullets.\n\n"
                    + block[:16000]
                )
                revised = self._call_bedrock(
                    compact_prompt,
                    max_tokens=token_budget,
                    model_id=getattr(self.config, "FALLBACK_MODEL_ID", None),
                ).strip()
                if revised and not self._scope_block_structure_issues(revised):
                    block = revised
                remaining_structure_issues = self._scope_block_structure_issues(block)
                if remaining_structure_issues:
                    raise RuntimeError(
                        f"Scope Deliverable {deliverable_index} failed structure validation: "
                        + "; ".join(remaining_structure_issues)
                    )
            concise_issues = self._concise_sow_issues(block)
            if block and concise_issues:
                concise_prompt = (
                    section_editorial_contract('scope_of_work')
                    + "\n\nRewrite the draft below without changing or omitting any deliverable or "
                    "module heading. Preserve every material scope commitment, name, value and boundary. "
                    "Remove background, pain-point narratives, rationale and repetition. Beneath each "
                    "module, use direct action bullets only; every bullet must be one sentence of no "
                    "more than 25 words. The deterministic style check found: "
                    + "; ".join(concise_issues)
                    + ". Return only the revised Markdown.\n\nDRAFT:\n"
                    + block[:18000]
                )
                try:
                    revised = self._call_bedrock(
                        concise_prompt,
                        max_tokens=token_budget,
                        model_id=getattr(self.config, "EDITOR_MODEL_ID", getattr(self.config, "FAST_MODEL_ID", None)),
                        call_name=f"Scope Deliverable {deliverable_index} concise rewrite",
                    ).strip()
                    revised_key = _normalise_heading_text(revised)
                    headings_preserved = (
                        not multiple_deliverables
                        or _normalise_heading_text(display_name) in revised_key
                    )
                    headings_preserved = headings_preserved and all(
                        not name or _normalise_heading_text(name) in revised_key
                        for name in expected_modules
                    )
                    if (
                        revised
                        and headings_preserved
                        and len(self._concise_sow_issues(revised)) < len(concise_issues)
                    ):
                        block = revised
                except Exception:
                    pass
            if block:
                # Heading names and numbering are contractual document structure,
                # so do not leave them to probabilistic model compliance.
                if multiple_deliverables:
                    module_start = re.search(r"(?m)^####\s+", block)
                    if module_start:
                        block = block[module_start.start():].strip()
                    else:
                        block = re.sub(r"(?im)^###\s+.*(?:\n+|$)", "", block, count=1).strip()
                    block = self._sanitize_scope_reasoning_labels(block)
                    blocks.append(f"### {display_name}\n\n{block}".strip())
                else:
                    # A single delivery package does not need an artificial
                    # "Deliverable 1" level. Modules sit directly below Scope.
                    block = re.sub(
                        r"(?im)^###\s+deliverable\s+1\s*[-:–—].*(?:\n+|$)", "", block, count=1
                    ).strip()
                    block = re.sub(r"(?m)^####\s+", "### ", block)
                    blocks.append(self._sanitize_scope_reasoning_labels(block))
        return "\n\n".join(blocks)

    @staticmethod
    def _sanitize_scope_reasoning_labels(content: str) -> str:
        """Flatten leaked analysis labels into ordinary scope bullets."""
        category = (
            r"(?:proposed\s+(?:implementation\s+)?approach|implementation\s+approach|"
            r"key\s+outputs?|dependencies|validation\s+evidence|roles?|inputs?|"
            r"functional\s+requirements?|requirements?|outputs?)"
        )
        cleaned: List[str] = []
        for line in str(content or "").splitlines():
            if re.match(
                r"^\s*(?:[-*+]\s*)?(?:\*\*)?(?:evidence\s+status|assumption\s+flagged)\s*:",
                line,
                flags=re.I,
            ):
                # Provenance annotations are not implementation work. Their
                # underlying questions belong in Open Clarifications.
                continue
            match = re.match(
                rf"^\s*(?:[-*+]\s*)?(?:\*\*)?{category}\s*:\s*(?:\*\*)?\s*(.*)$",
                line,
                flags=re.I,
            )
            if match:
                remainder = match.group(1).strip()
                if remainder:
                    cleaned.append(f"- {remainder}")
                continue
            if re.match(rf"^\s*#+\s+{category}\s*:?\s*$", line, flags=re.I):
                continue
            cleaned.append(line)
        return re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()

    @staticmethod
    def _scope_block_structure_issues(content: str) -> List[str]:
        """Reject repeated reasoning labels without imposing a length/count limit."""
        issues: List[str] = []
        category = (
            r"(?:proposed\s+(?:implementation\s+)?approach|implementation\s+approach|"
            r"key\s+outputs?|dependencies|validation\s+evidence|roles?|inputs?|"
            r"functional\s+requirements?|requirements?|outputs?)"
        )
        if re.search(rf"(?im)^\s*(?:\*\*)?{category}\s*:\s*(?:\*\*)?", content or ""):
            issues.append("module reasoning labels are present as separate category blocks")
        if re.search(rf"(?im)^\s*(?:#+\s+){category}\s*:?\s*$", content or ""):
            issues.append("module reasoning categories are rendered as headings")
        return issues

    def _architect_scope(
        self,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source_context: str,
    ) -> Dict[str, Any]:
        """Compatibility entry point delegated to the dedicated scope architect."""
        from app.agents.scope_architect_agent import ScopeArchitectAgent
        return ScopeArchitectAgent(
            self.config,
            template_type=self.template_type,
            call_fn=self._call_bedrock,
        ).architect(requirements, metadata, source_context)

    def _legacy_architect_scope(
        self,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source_context: str,
    ) -> Dict[str, Any]:
        """Legacy implementation retained temporarily for old serialized test fixtures."""
        prompt = f"""You are the principal solution architect for this engagement.
Analyse the complete source and create the internal work-breakdown blueprint used to author the SOW.
Return JSON only; do not write SOW prose.

CUSTOMER: {metadata.get('company_name', '')}
PROJECT: {metadata.get('project_title', '')}
MODE: {self.template_type}

NORMALISED REQUIREMENTS:
{json.dumps(requirements, indent=2, default=str)}

AUTHORITATIVE SOURCE EVIDENCE:
{source_context or '(none)'}

Return this shape:
{{
  "deliverables": [
    {{
      "name": "outcome-oriented deliverable name",
      "purpose": "business and solution boundary",
      "separation_basis": "independent phase, deployment, acceptance boundary, or other source-backed reason",
      "modules": [
        {{
          "name": "cohesive implementation module or workstream",
          "task_statement": "problem this module solves",
          "objective": "target operating outcome",
          "actors": [],
          "inputs": [],
          "requirements": [],
          "delivery_approach": [],
          "outputs": [],
          "dependencies": [],
          "validation_evidence": [],
          "source_basis": [],
          "evidence_status": "Confirmed|Source Assumption|Proposed|Open"
        }}
      ]
    }}
  ],
  "cross_cutting_decisions": [],
  "open_boundaries": []
}}

Architecture rules:
- Determine the natural number of deliverables and modules from the problem; there is no target, minimum, or maximum count.
- A deliverable is a separately deployable or acceptably complete business outcome, release, or phase. It is not a synonym for a source table row, feature, integration, technical layer, workstream, or module.
- First cluster capabilities that share the same users, release boundary, operating workflow, deployment and acceptance event. Promote a cluster to a separate deliverable only when it has a credible independent phase, deployment or acceptance boundary, and record that reason in separation_basis.
- Preserve explicitly numbered or named customer-authored deliverables as top-level deliverables when
  each describes a distinct reviewable business outcome. A shared programme, deployment, or acceptance
  event does not override those explicit boundaries. Ordinary feature rows, artefacts, technical layers,
  and checklists remain modules or outputs.
- Perform a final cohesion audit before returning JSON: if two proposed deliverables would be designed, built, demonstrated and accepted together, merge them while retaining every module and source requirement.
- Every deliverable must contain the modules needed to deliver its outcome. A module is a cohesive implementation workstream, not a generic document category.
- Decompose source workflows, business rules, integrations, data, AI behaviour, user interaction, platform work, security, testing, and readiness where they materially affect delivery.
- For every module reason from task/problem through objective, inputs, requirements and implementation approach to observable output and validation.
- Preserve all source-specific systems, actors, thresholds, classifications, workflows, exceptions, channels, data objects and future-phase boundaries.
- Respect status language inside the evidence. Text explicitly labelled Assumption, Derived, Proposed, To be confirmed, Not stated, Needs clarification, optional or future must retain that status; it is not confirmed merely because it appears in an uploaded file. Conflicting sources create an open boundary.
- Do not invent facts. Mark architect-derived design choices as Proposed and unresolved customer decisions as open boundaries.
- Do not create empty boilerplate modules merely to cover a standard delivery lifecycle.
"""
        raw = self._call_bedrock(
            prompt,
            max_tokens=8192,
            model_id=getattr(self.config, "WRITER_MODEL_ID", None),
        )
        parsed = self._extract_json(raw)
        if not parsed:
            return {}
        try:
            value = json.loads(parsed)
        except json.JSONDecodeError:
            return {}
        deliverables = value.get("deliverables") if isinstance(value, dict) else None
        if not isinstance(deliverables, list):
            return {}
        # Remove structurally empty model output; the section writer will fall
        # back to the authoritative baseline rather than trust a broken plan.
        clean_deliverables = []
        for item in deliverables:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                continue
            modules = [
                module for module in (item.get("modules") or [])
                if isinstance(module, dict) and str(module.get("name") or "").strip()
            ]
            if not modules:
                continue
            clean_deliverables.append({**item, "modules": modules})
        value["deliverables"] = clean_deliverables
        if not value["deliverables"]:
            return {}
        if self._scope_plan_looks_fragmented(value):
            reviewed = self._review_fragmented_scope_plan(
                value, requirements, metadata, source_context
            )
            if reviewed:
                value = reviewed
        for index, deliverable in enumerate(value["deliverables"], 1):
            clean_name = re.sub(
                r"^\s*deliverable\s+\d+\s*[-:–—]\s*",
                "",
                str(deliverable.get("name") or "").strip(),
                flags=re.I,
            )
            deliverable["name"] = clean_name
            deliverable["number"] = index
            deliverable["display_name"] = f"Deliverable {index} - {clean_name}"
        return value

    @staticmethod
    def _scope_plan_looks_fragmented(plan: Dict[str, Any]) -> bool:
        """Flag capability buckets masquerading as independent deliverables."""
        deliverables = plan.get("deliverables") or []
        if len(deliverables) < 2:
            return False
        module_counts = [len(item.get("modules") or []) for item in deliverables]
        thin_deliverables = sum(count <= 2 for count in module_counts)
        missing_boundaries = sum(
            not str(item.get("separation_basis") or "").strip()
            for item in deliverables
        )
        return thin_deliverables >= max(2, math.ceil(len(deliverables) * 0.6)) or (
            len(deliverables) >= 3
            and missing_boundaries >= max(2, math.ceil(len(deliverables) * 0.6))
        )

    def _review_fragmented_scope_plan(
        self,
        plan: Dict[str, Any],
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        source_context: str,
    ) -> Dict[str, Any]:
        """Ask a second architect pass to merge artificial capability deliverables."""
        original_deliverables = plan.get("deliverables") or []
        original_module_count = sum(len(item.get("modules") or []) for item in original_deliverables)
        prompt = f"""You are the architecture review authority for a Statement of Work.
The draft work breakdown appears fragmented. Return JSON only in exactly the same shape as DRAFT_PLAN.

CUSTOMER: {metadata.get('company_name', '')}
PROJECT: {metadata.get('project_title', '')}
MODE: {self.template_type}

DRAFT_PLAN:
{json.dumps(plan, indent=2, default=str)}

NORMALISED REQUIREMENTS:
{json.dumps(requirements, indent=2, default=str)}

SOURCE EVIDENCE:
{source_context or '(none)'}

Review rules:
- Merge deliverables that are merely channels, integrations, platform layers, functional capabilities, or source-table rows belonging to the same implemented and accepted solution.
- Retain every module, requirement, source_basis item, output, dependency, qualification, and open boundary. Do not reduce coverage while merging.
- Keep separate deliverables only for a real independent phase, release, deployment, commercial hand-off, or acceptance event; state that reason in separation_basis.
- Do not target a particular count. A single coherent deliverable with many modules is valid; multiple deliverables are valid only when their boundaries are real.
- Preserve evidence status. Source Assumption, Proposed, Open, To be confirmed, optional and future items must not become Confirmed.
"""
        raw = self._call_bedrock(
            prompt,
            max_tokens=8192,
            model_id=getattr(self.config, "WRITER_MODEL_ID", None),
        )
        parsed = self._extract_json(raw)
        if not parsed:
            return {}
        try:
            reviewed = json.loads(parsed)
        except json.JSONDecodeError:
            return {}
        revised_deliverables = reviewed.get("deliverables") if isinstance(reviewed, dict) else None
        if not isinstance(revised_deliverables, list) or not revised_deliverables:
            return {}
        revised_deliverables = [
            item for item in revised_deliverables
            if isinstance(item, dict)
            and str(item.get("name") or "").strip()
            and isinstance(item.get("modules"), list)
            and item.get("modules")
        ]
        revised_module_count = sum(len(item["modules"]) for item in revised_deliverables)
        # A cohesion pass may merge containers, but it must never achieve that
        # by silently dropping source-backed modules.
        if revised_module_count < original_module_count:
            return {}
        if len(revised_deliverables) >= len(original_deliverables):
            return {}
        reviewed["deliverables"] = revised_deliverables
        return reviewed

    @staticmethod
    def _authoring_issues(content: str, section: TemplateSection) -> List[str]:
        issues = section_quality_issues(content, section.name)
        name = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", section.name).casefold()
        # Section-specific contract checks turn the detailed Markdown template
        # into an enforceable generation gate rather than optional guidance.
        normalized = (content or "").casefold()
        direct_headings = re.findall(r"(?m)^###\s+.+$", content or "")
        nested_headings = re.findall(r"(?m)^####+\s+.+$", content or "")
        table_lines = [
            line.casefold() for line in (content or "").splitlines()
            if re.match(r"^\s*\|.+\|\s*$", line)
        ]
        if name == "about {company_name}":
            paragraphs = [
                paragraph.strip()
                for paragraph in re.split(r"\n\s*\n", content or "")
                if paragraph.strip()
            ]
            if len(paragraphs) != 2:
                issues.append("About Client must contain exactly two brief paragraphs")
            if re.search(r'(?m)^\s*(?:[-*+]\s|#|\|)', content or ''):
                issues.append("About Client must not contain bullets, headings or tables")
            if re.search(
                r"(?i)\b(?:this engagement|project scope|project objectives?|"
                r"statement of work|requirements relevant to|specific operational context|"
                r"supplied project|proposed solution|shellkode(?:'s)? involvement)\b",
                content or "",
            ):
                issues.append("About Client must describe only the company, not the engagement or its problem")
        elif name in {"scope of work", "detailed scope of work"}:
            deliverables = re.findall(r"(?im)^###\s+.*\bdeliverable\b.*$", content or "")
            modules = re.findall(r"(?m)^####\s+.+$", content or "")
            if deliverables:
                if not modules:
                    issues.append("Scope of Work must decompose each deliverable into architected modules")
                deliverable_blocks = re.split(
                    r"(?im)(?=^###\s+.*\bdeliverable\b.*$)", content or ""
                )[1:]
                if any(not re.search(r"(?m)^####\s+.+$", block) for block in deliverable_blocks):
                    issues.append("Every deliverable in Scope of Work must contain at least one module")
            else:
                if not re.search(r"(?m)^###\s+.+$", content or ""):
                    issues.append("Scope of Work must decompose the scope by deliverable/module boundaries into architected modules")
                if modules:
                    issues.append("Module headings cannot be nested without a deliverable heading")
            forbidden = re.findall(
                r"(?im)^#{3,6}\s+(?:\d+(?:\.\d+)*[.)]?\s*)?"
                r"(?:task statement|objective|inputs?|outputs?|requirements?)\s*$",
                content or "",
            )
            if forbidden:
                issues.append("Task statement, objective, inputs, requirements and outputs must be integrated into module content, not emitted as numbered headings")
        elif name.startswith("aws pricing"):
            if "pricing calculator" not in normalized:
                issues.append("AWS Pricing is missing the calculator link or estimate basis")
        elif name.endswith("project team effort"):
            if not any(all(label in line for label in ("resource", "resource count", "effort duration in weeks")) for line in table_lines):
                issues.append("Project Team Effort is missing the required staffing table")
        if name not in {"scope of work", "detailed scope of work"}:
            if len(direct_headings) > 2 or nested_headings:
                issues.append("contains too many subsections; retain at most two direct subsections and use bullets")
        return issues

    @staticmethod
    def _concise_sow_issues(content: str) -> List[str]:
        """Identify prose-heavy SOW output without making style a fatal gate."""
        issues: List[str] = []
        text = str(content or "")
        negative = re.findall(
            r"(?i)\b(?:pain points?|root causes?|current-state deficiencies?|"
            r"client shortcomings?|operational weaknesses?)\b",
            text,
        )
        if negative:
            issues.append("contains client problem or deficiency framing")

        long_bullets = 0
        multi_sentence_bullets = 0
        long_paragraphs = 0
        prose_run = 0
        max_prose_run = 0
        for block in re.split(r"\n\s*\n", text):
            stripped = block.strip()
            if not stripped:
                continue
            lines = [line.strip() for line in stripped.splitlines() if line.strip()]
            is_structured = all(
                re.match(r"^(?:#{1,6}\s+|[-*+]\s+|\|)", line)
                for line in lines
            )
            if is_structured:
                prose_run = 0
            else:
                prose_run += 1
                max_prose_run = max(max_prose_run, prose_run)
                if len(re.findall(r"\b[\w'-]+\b", stripped)) > 45:
                    long_paragraphs += 1
            for line in lines:
                bullet = re.match(r"^[-*+]\s+(.+)$", line)
                if not bullet:
                    continue
                body = re.sub(r"[*_`]", "", bullet.group(1))
                if len(re.findall(r"\b[\w'-]+\b", body)) > 25:
                    long_bullets += 1
                if len(re.findall(r"[.!?](?=\s|$)", body)) > 1:
                    multi_sentence_bullets += 1

        if long_paragraphs:
            issues.append(f"contains {long_paragraphs} prose paragraph(s) longer than 45 words")
        if max_prose_run > 1:
            issues.append("contains consecutive prose paragraphs")
        if long_bullets:
            issues.append(f"contains {long_bullets} bullet(s) longer than 25 words")
        if multi_sentence_bullets:
            issues.append(f"contains {multi_sentence_bullets} multi-sentence bullet(s)")
        return issues

    @staticmethod
    def _contractual_section_issues(content: str, category: str) -> List[str]:
        """Trigger a focused rewrite when contract sections drift into commentary."""
        if category not in {"assumptions", "out_of_scope"}:
            return []
        issues: List[str] = []
        lines = [line.strip() for line in str(content or "").splitlines() if line.strip()]
        if any(line.startswith("#") or line.startswith("|") for line in lines):
            issues.append("must use a simple bullet list without subsections or tables")
        if any(not re.match(r"^[-*+]\s+", line) for line in lines):
            issues.append("must not include an opening or explanatory paragraph")
        if re.search(
            r"(?i)\b(?:not (?:provided|specified|confirmed|clarified|known)|"
            r"customer (?:did not|has not|could not)|due to (?:a )?(?:lack|absence)|"
            r"based on (?:the )?(?:lack|absence)|because (?:the )?customer|"
            r"source|evidence|proposed|pending confirmation|subject to confirmation)\b",
            content or "",
        ):
            issues.append("contains missing-input, evidence-status, or decision-rationale commentary")
        if category == "out_of_scope" and re.search(
            r"(?i)\b(?:anything|everything|all (?:items|features|services|work))\s+"
            r"(?:not|outside|beyond)\b|\bother work not explicitly\b",
            content or "",
        ):
            issues.append("contains a blanket exclusion instead of material project boundaries")
        return issues

    @staticmethod
    def _section_word_limit(section: TemplateSection) -> Optional[int]:
        """Return a compact but workable maximum for one generated section."""
        name = re.sub(
            r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", section.name
        ).casefold()
        if name.startswith(("document control", "document version control")):
            return 350
        if name == "about {company_name}":
            return 180
        if name.startswith("about "):
            return 220
        if "scope of work" in name:
            return None
        if "technical specification" in name:
            return 900
        if "architecture" in name:
            return 550
        if any(term in name for term in ("terms and conditions", "testing and acceptance")):
            return 450
        return 320

    def _build_individual_prompt(
        self,
        section: TemplateSection,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        supporting_context: Optional[str] = None,
        prior_context: str = "",
    ) -> str:
        type_label = {
            "POC": "proof-of-concept",
            "PROD": "production implementation",
            "POC_TO_PROD": "POC-to-production transition",
        }.get(self.template_type, self.template_type.lower())
        company_research_context = "(not applicable to this section)"
        if self._section_category(section) == "about_client":
            company_research_context = (
                metadata.get("company_description")
                or ""
            )
        category = self._section_category(section)
        about_client = category == "about_client"
        from app.diagram.knowledge import reference_context
        architecture_references = reference_context(requirements) if category == "architecture_diagram" else ""
        if category == "architecture_diagram":
            from app.diagram.planning import ARCHITECTURE_PLANNING_RULES
            architecture_references += '\n' + ARCHITECTURE_PLANNING_RULES
        from app.core.authoring_context import authoring_facts, boundary_summary
        requirements_context = (
            {"company_name": metadata.get("company_name", "")}
            if about_client else authoring_facts(requirements)
        )
        section_source_context = supporting_context or "(none)"
        refinement_contract = "(not a regeneration request)"
        if getattr(self, "refinement_plan", None):
            affected = {
                str(value).strip() for value in self.refinement_plan.get("affected_sections") or []
            }
            if category in affected:
                refinement_contract = (
                    "This section is explicitly affected. Apply only the requested changes, preserve "
                    "all unrelated baseline facts and boundaries, and enforce every structured "
                    "constraint in the refinement plan.\n"
                    + json.dumps(self.refinement_plan, indent=2, default=str)
                )
            else:
                refinement_contract = (
                    "This section is NOT affected by the refinement request. Preserve its baseline "
                    "meaning, facts, scope status, tables, and subsection structure. Do not introduce "
                    "new requirements, assumptions, phases, commitments, or template material."
                )
        architecture_blueprint = "(not applicable to this section)"
        solution_design_context = "(not applicable to this section)"
        if category in {
            "scope_of_work", "architecture_diagram",
            "timelines_deliverables", "customer_dependencies", "assumptions",
            "out_of_scope", "open_clarifications", "success_criteria",
            "project_team_effort",
        }:
            architecture_blueprint = json.dumps(
                (getattr(self, "scope_architecture_plan", {}) or {}) if category == "scope_of_work"
                else boundary_summary(getattr(self, "scope_architecture_plan", {}) or {}),
                separators=(',', ':'), default=str
            ) or "(not available; derive directly from the authoritative baseline)"
            if category != "architecture_diagram":
                solution_design_context = getattr(self, "solution_architecture_context", "")
        contractual_section_contract = "(not applicable to this section)"
        if category == "out_of_scope":
            contractual_section_contract = """Treat Out of Scope as a short contractual boundary, not a catalogue.
- Include only exclusions that prevent a realistic post-delivery dispute or scope misunderstanding.
- Relevant examples may include post-acceptance model/provider/version migration, new use cases, new integrations, capacity beyond the agreed baseline, or ongoing operations; include only those applicable here.
- A boundary may be inferred from what the agreed delivery ends at, but it must be material and must not contradict Scope of Work.
- Use only plain one-sentence bullets. State what is excluded, never why, and never mention evidence, uncertainty, missing inputs, proposals, or confirmation status.
- Silently remove generic boilerplate, obvious non-scope, minor details, and anything unlikely to be requested as part of this delivery."""
        elif category == "assumptions":
            contractual_section_contract = """Treat Assumptions as the smallest set of critical delivery baselines, not a list of unknowns.
- Include a condition only when changing it would materially affect architecture, scope, cost, schedule, security, compliance, or acceptance.
- State the adopted baseline directly in simple English; use only actual agreed sizing values, never example values.
- Never say the customer did not know, specify, provide, confirm, or clarify something, and never explain why the baseline was chosen.
- Include project-specific delivery premises: usable linked data, representative test material, approved rules, existing integration/identity access and agreed operating baselines, only where material to this project.
- Do not invent values, environments, approval deadlines or schedules. Do not list features, repeat the access checklist, or turn minor unknowns into assumptions. A material data-quality or rule-availability condition is legitimate even when the client supplies it.
- Keep roughly a short 6-9-bullet list when the evidence warrants it, never pad to a count. Use one brief sentence and one meaningful inline bold phrase per bullet.
- Put only critical unanswered decisions in Open Clarifications and omit non-critical unknowns.
- Use only plain one-sentence bullets with no opening paragraph, subsections, or table."""
        length_instruction = (
            "- No fixed word, deliverable, or module limit applies. Use the natural amount of detail "
            "needed to cover the source clearly and concisely. "
            "Do not target a fixed word count, pad sparse evidence, or repeat information."
        )
        return f"""You are a principal solutions architect and senior commercial technical writer.
Write the body of one section in a benchmark-quality {type_label} Statement of Work.

DOCUMENT CONTEXT
- Customer: {metadata.get('company_name', '')}
- Project: {metadata.get('project_title', '')}
- Author organization: {metadata.get('author_org', '')}
- Mode: {self.template_type}

AUTHORITATIVE REQUIREMENTS BASELINE
{json.dumps(requirements_context, separators=(',', ':'), default=str)}

{architecture_references}

USER GENERATION GUIDANCE
{requirements.get('_generation_guidance') or '(none)'}
- Apply this guidance consistently across every section, including scope,
  exclusions, future scope, assumptions and acceptance treatment.
- When supporting evidence is present, guidance controls how evidence is prioritised or
  scoped but does not authorise unrelated facts or deliverables.

REFINEMENT PRESERVATION CONTRACT
{refinement_contract}

SOURCE EXCERPT (supporting evidence; may be empty)
{section_source_context}

CLIENT RESEARCH CONTEXT (use only when writing About Client)
{company_research_context}

DOCUMENT CONSISTENCY NOTES
{prior_context or '(none)'}

SHARED SOLUTION-ARCHITECTURE WORK BREAKDOWN
{architecture_blueprint}

SOLUTION DESIGN CONTEXT
{solution_design_context}
Use only design decisions relevant to this section. This is not a checklist to reproduce.
Do not repeat the infrastructure inventory, add service-by-service bullets, or turn design facts into assumptions.
Keep actions consistent with the chosen design without inventing scope, sizing or commitments; authoritative requirements take precedence.

USER-SELECTED DOCUMENT CUSTOMISATION
- Topics to include: {', '.join(SECTION_LABELS.get(item, item) for item in getattr(self, 'selected_section_preferences', [])) or '(none)'}
- Topics to exclude: {', '.join(getattr(self, 'excluded_section_preferences', [])) or '(none)'}
- Author only the selected document structure. Do not introduce a section, table,
  schedule, cost estimate, signature block, or substantive discussion for an excluded
  topic elsewhere in the document. A brief source-grounded cross-reference is allowed
  only when it is necessary to keep a selected section internally coherent.

GLOBAL TEMPLATE AND REFERENCE-BENCHMARK CONTRACT
{self.global_template_contract or '(no global contract supplied)'}

SECTION TO WRITE: {section.name}
TEMPLATE AUTHORING INSTRUCTIONS:
{self._replace_placeholders(section.content, metadata, requirements)}

RELEVANCE AND SECTION OWNERSHIP (takes priority over exhaustive coverage lists):
{section_editorial_contract(editorial_category(section.name, self._section_category(section)))}

MANDATORY SELECTED PRESENTATION (overrides conflicting generic/custom template guidance)
{presentation_contract(self._section_category(section), metadata)}
{'Before returning an empty section, check the BRD/user inputs for both numerical targets and required functional outcomes. Absence of numbers is not a reason to omit descriptive criteria. Only when neither exists, return exactly [NO_SOURCE_BACKED_SUCCESS_CRITERIA] as the entire response; this internal sentinel becomes a blank section.' if self._section_category(section) == 'success_criteria' else ''}
Preserve explicitly requested custom-template layout; apply these relevance rules to its content without adding filler rows.

CONTRACTUAL SECTION MATERIALITY RULES
{contractual_section_contract}

SECTION LENGTH BUDGET
{length_instruction}
- Completeness means covering the necessary
  decision, scope, dependency, responsibility, and validation information once; it does
  not mean expanding every possible implementation detail.

NON-NEGOTIABLE AUTHORING STANDARD
- Return only the Markdown body. Do not repeat the top-level section heading and do not use code fences.
- Write as an execution agreement. Lead with what the delivery team will design, configure, build,
  integrate, migrate, test, document or hand over, together with the relevant boundary or evidence.
- Do not narrate customer pain points, shortcomings, deficiencies, failures, weaknesses, root causes,
  or negative business impact. Translate source concerns directly into neutral delivery actions and outcomes.
- Use British Indian English throughout, never US spelling. Prefer forms such as
  organisation, organise, centralised, analyse, behaviour, colour, programme,
  licence (noun), and fulfilment. Preserve official product names, API fields,
  source quotations, and other identifiers exactly as supplied.
- Treat only unqualified source assertions as confirmed. Preserve source-authored labels such as
  Assumption (as "Source Assumption"), Derived, Proposed, To be confirmed, Not stated, Needs clarification, optional and
  future. Conflicts between uploaded sources are Open; do not silently choose one. Treat
  architect-derived choices as recommendations internally and put unknown material facts under Open Clarifications.
- The final SOW is client-facing. Never mention uploaded files, source documents, supporting documents,
  source material, source-backed facts, model output, prompts, generation, extraction, evidence status,
  provenance, or internal requirement field names. Do not append Confirmed, Proposed, Open, Source
  Assumption, Derived, or pending-confirmation labels to client-facing statements or table cells.
- Never invent customer facts, dates, prices, volumes, user counts, compliance claims, SLAs,
  model versions, named contacts, or achieved results.
- Never describe information as absent in any section or emit phrases such as "not provided",
  "not specified", "unknown", "TBD", "to be confirmed", "inputs were not provided", or equivalent
  disclaimers. Omit unsupported ordinary-section content. In Open Clarifications, express the item
  directly as an answerable question and leave any unavailable value cell blank.
- Do not diagnose a current-state deficiency merely because the target solution includes that
  capability. Describe a gap as confirmed only when a source states or directly demonstrates it.
- A source-required capability must not appear in Out of Scope. A conflicting, optional or
  unconfirmed capability belongs in Open Clarifications or a clearly labelled future phase.
- For Out of Scope and Assumptions, apply the section-specific materiality rules above instead of
  producing a comprehensive checklist. Keep only clauses that protect or establish the delivery baseline.
- Do not present a planning target as an agreed acceptance criterion. When a material target is unresolved,
  ask a direct question in Open Clarifications without adding a status or provenance label.
- Include only the detail this section owns; do not enumerate capability, owner, input, output,
  dependency and validation for every point. Scope describes work; acceptance describes tests.
- Preserve cross-section consistency for terminology, timeline, scope, services, and metrics.
- Preserve supplied compliance and regulatory wording exactly, including regulator names,
  disclaimer language, residency constraints, qualifications, and human-review boundaries.
  Never turn an expectation, design intent, or pending confirmation into a compliance claim.
- Preserve each distinct implementation commitment in Scope of Work; do not repeat its
  workflow, fields, controls and tests in every other selected section. Ancillary sections
  add only their own distinct contractual facts. Do not replace specific business rules
  with generic cloud activities or vague summaries.
- Except for About Client, use short bullets, with no opening or closing paragraph. Do not
  restate the project objective, customer context, or the same requirement in multiple forms.
- About Client is the two-paragraph exception. Other generated narrative sections use short bullets. Preserve required tables.
- Default to no subsection headings. Follow any essential opening sentence with concise action bullets. Convert labels such as Roles, Data, Dependencies, Controls,
  Validation, or Risks into ordinary sentences instead of separate headings or bold lead-in labels.
- Outside Scope of Work, use at most two direct subsections and no nested subsections. In Scope of
  Work, use `### Deliverable 1 - <name>` and `#### <Module Name>` headings. Do not create headings for
  Task Statement, Objective, Inputs, Requirements, Outputs, Dependencies, or Validation; integrate
  those concerns naturally into the module opening and implementation bullets.
- Avoid more than one consecutive prose paragraph. Use concise bullets for three or more
  non-comparable items and Markdown tables only for genuinely comparable records. Aim for at
  least 60% of non-table content after the opening to be concise bullet points.
- Use ### and #### for real subsection headings and standard '-' bullets only.
- Put every bullet on its own Markdown line. Every bullet must contain one sentence and one idea,
  normally no more than 25 words and short enough to render in one or two lines. Start with the action or subject, never a bold capability label and colon. Use the natural number of source-supported items and never add filler to meet a count. Use two leading
  spaces for a nested bullet and never embed bullet symbols inside a prose paragraph.
- Keep heading hierarchy complete and consistent. The DOCX renderer normalizes every
  generated heading to 1.1 / 1.2 / 4.1 / 4.1.1 form; never use a bold Normal paragraph
  as a substitute for a heading and never skip from a module heading to an unstructured label.
- Use bullet lists for workflows and sequences; never emit Markdown ordered lists.
  Keep each workflow to the natural set of meaningful stages without splitting low-value micro-actions.
- For tables, emit a valid pipe table with one separator row; use <br> only for multiple items in a cell.
- Prefer two to five table columns where practical. Preserve a wider source-backed table when
  splitting it would obscure the relationship between fields; table width is never a failure condition.
- Do not create a new top-level section. Keep every requested detail within this section's
  benchmark-defined boundary and do not append generic SOW boilerplate.
- Omit generic background, textbook explanations, marketing language, and implementation
  possibilities that do not change scope, ownership, dependency, acceptance, or a decision.
- When writing Solution Architecture, explain the end-to-end flow and how the relevant logical layers
  and chosen services interact, followed by only material deployment, data and security decisions.
  Do not duplicate the visual as a long component
  catalogue, and never claim that a source-supplied diagram exists when it does not.
- The section should be complete enough for commercial and technical review, without filler or repetition.
- For About Client, write exactly two short factual paragraphs about the company, without engagement commentary or bullets. Never invent facts to pad them.
"""

    def _build_prompt(
        self,
        sections: List[TemplateSection],
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        supporting_context: Optional[str] = None,
    ) -> str:
        """Backward-compatible prompt helper used by diagnostics."""
        return "\n\n".join(
            self._build_individual_prompt(s, requirements, metadata, supporting_context)
            for s in sections
        )

    def _call_bedrock(
        self,
        prompt: str,
        max_tokens: int = 6000,
        model_id: Optional[str] = None,
        call_name: str = "SOW Section Generation",
    ) -> str:
        try:
            result = self.llm.generate(
                prompt,
                task="writer",
                max_tokens=int(max_tokens),
                temperature=0.15,
                call_name=call_name,
                model_id=model_id,
            )
            return result.text.strip()
        except Exception as exc:
            print(f"    ❌ Section generation error: {exc}")
            raise

    def _call_bedrock_batch(self, prompt: str, sections: List[TemplateSection]) -> Dict[str, str]:
        """Compatibility shim; generation no longer depends on oversized batch JSON."""
        result: Dict[str, str] = {}
        raw = self._call_bedrock(prompt, max_tokens=8192)
        parsed = self._extract_json(raw)
        if parsed:
            try:
                data = json.loads(parsed)
                if isinstance(data, dict):
                    result = {str(k): str(v) for k, v in data.items()}
            except json.JSONDecodeError:
                pass
        return result

    @staticmethod
    def _section_token_budget(section: TemplateSection) -> int:
        # Give each section enough room for its natural structure without
        # exposing every call to the model's maximum output allowance.
        name = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", section.name).casefold()
        if "scope of work" in name:
            return 12000
        if "technical specification" in name:
            return 5000
        if "architecture" in name:
            return 3000
        if name == "about {company_name}" or name.startswith("about "):
            return 600
        return 1800

    @staticmethod
    def _context_excerpt(
        supporting_context: Optional[str],
        limit: int = 48000,
        section_name: str = "Project Overview",
        requirements: Optional[Dict[str, Any]] = None,
    ) -> str:
        text = str(supporting_context or "")
        if len(text) <= limit:
            return text
        return select_section_evidence(
            text,
            section_name=section_name,
            requirements=requirements,
            max_chars=limit,
        )

    @staticmethod
    def _plain_summary(content: str, limit: int = 500) -> str:
        text = re.sub(r"[`*_#|]", " ", content or "")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]

    @staticmethod
    def _quality_summary(missing: List[str], issues: List[str], requirements: Dict[str, Any]) -> str:
        status = "Passed" if not missing and not issues else "Completed with review flags"
        lines = [
            f"**Generation quality gate:** {status}",
            f"- Missing expected sections: {', '.join(missing) if missing else 'None'}",
            f"- Automated content flags: {len(issues)}",
            f"- Open clarifications carried forward: {len(requirements.get('open_clarifications', []))}",
            "- Diagram generation: intentionally excluded from this probe",
        ]
        return "\n".join(lines)

    @staticmethod
    def _deterministic_fallback(section: TemplateSection, requirements: Dict[str, Any]) -> str:
        name = re.sub(
            r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", section.name
        ).casefold()
        if "clarification" in name:
            items = requirements.get("open_clarifications", [])
            return "\n".join(f"- {item}" for item in items) or "- Scope baseline requires customer confirmation."

        # If Bedrock is unavailable, retain extracted BRD facts instead of
        # replacing them with a generic failure paragraph.
        evidence: List[str] = []
        for field in (
            "key_deliverables", "functional_requirements", "key_features",
            "workflow_steps", "integration_details", "success_metrics",
        ):
            value = requirements.get(field, [])
            values = value if isinstance(value, list) else ([value] if value else [])
            for item in values:
                item = re.sub(r"\s+", " ", str(item)).strip()
                if item and item.casefold() not in {seen.casefold() for seen in evidence}:
                    evidence.append(item)

        overview = requirements.get("project_overview") or ""
        if any(token in name for token in ("deliverable", "scope at a glance")) and evidence:
            rows = ["| Module/Workstream | Core Outcome |", "|---|---|"]
            rows.extend(f"| Source requirement | {item.replace('|', '/')} |" for item in evidence[:12])
            return "\n".join(rows)
        if evidence:
            prefix = f"{overview}\n\n" if overview else ""
            return prefix + "\n".join(f"- {item}" for item in evidence[:20])
        return overview or ""

    def _enrich_requirements(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return normalize_requirements(req, req.get("_original_objective", ""), self.template_type)

    def _classify_complexity(self, req: Dict[str, Any]) -> ProjectComplexity:
        return ProjectComplexity(classify_complexity(req))

    @staticmethod
    def _needs_generation(content: str) -> bool:
        return bool(re.search(r"\b(generate|write|derive|using objective|instructions?|rules?)\b", content or "", re.I))

    def _clean_content(self, content: str, section_name: str) -> str:
        if section_category(section_name) == 'architecture_diagram':
            content = strip_text_diagrams(content or '')
        content = clean_markdown_preserving_structure(content or "")
        lines = content.splitlines()
        section_label = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", section_name).strip()

        def heading_key(value: str) -> str:
            value = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", value).strip().casefold()
            # Treat a plural-only restatement (Objective/Objectives) as the same
            # heading, while leaving genuinely distinct headings untouched.
            return value[:-1] if value.endswith("s") and not value.endswith("ss") else value

        # Models sometimes insert a short orienting paragraph before repeating
        # the section title (for example Objective -> ### Objectives).  The old
        # cleaner only inspected line 1, so that duplicate survived.  Remove a
        # heading equivalent to its owning section wherever it occurs, while
        # preserving genuinely distinct subsections.
        filtered: List[str] = []
        for line in lines:
            match = re.match(r"^#{1,4}\s+(.+?)\s*$", line)
            if match and heading_key(match.group(1)) == heading_key(section_label):
                if filtered and not filtered[-1].strip():
                    filtered.pop()
                continue
            filtered.append(line)
        content = clean_markdown_preserving_structure("\n".join(filtered))
        name_key = heading_key(section_label)
        content = remove_client_facing_meta_language(content)
        blocked_columns = set()
        if "architecture" in name_key:
            blocked_columns.update({"status", "proposed", "open", "source", "evidence status"})
        if "clarification" in name_key:
            blocked_columns.update({"status", "status / note", "proposed", "open", "source", "evidence status"})
        if "customer dependenc" in name_key:
            blocked_columns.update({"status", "proposed", "open", "source", "evidence status"})
        if blocked_columns:
            content = self._remove_table_columns(content, blocked_columns)
        if name_key == "about {company_name}" or name_key.startswith("about "):
            paragraphs = [
                paragraph.strip()
                for paragraph in re.split(r"\n\s*\n", content)
                if paragraph.strip()
            ]
            paragraphs = [
                paragraph for paragraph in paragraphs
                if not re.search(
                    r"(?i)\b(?:this engagement|project scope|project objectives?|"
                    r"statement of work|requirements relevant to|specific operational context|"
                    r"supplied project|proposed solution|shellkode(?:'s)? involvement)\b",
                    paragraph,
                )
            ]
            content = "\n\n".join(paragraphs)
        if section_category(section_label) in {'raci_matrix', 'project_team_effort'}:
            table = '\n'.join(line for line in content.splitlines() if line.strip().startswith('|'))
            # Do not erase malformed legacy prose merely because no table exists.
            if table or section_category(section_label) == 'raci_matrix':
                content = table
        return strip_bullet_leadins(clean_markdown_preserving_structure(content))

    @staticmethod
    def _remove_table_columns(content: str, blocked_headers: set[str]) -> str:
        """Remove internal status/provenance columns from Markdown tables."""
        lines = str(content or "").splitlines()
        output: List[str] = []
        index = 0
        normalise = lambda value: re.sub(r"[`*_]", "", value).strip().casefold()
        while index < len(lines):
            if not (lines[index].strip().startswith("|") and lines[index].strip().endswith("|")):
                output.append(lines[index])
                index += 1
                continue
            table: List[str] = []
            while index < len(lines) and lines[index].strip().startswith("|") and lines[index].strip().endswith("|"):
                table.append(lines[index])
                index += 1
            header = [cell.strip() for cell in table[0].strip().strip("|").split("|")]
            keep = [position for position, value in enumerate(header) if normalise(value) not in blocked_headers]
            if not keep or len(keep) == len(header):
                output.extend(table)
                continue
            for row in table:
                cells = [cell.strip() for cell in row.strip().strip("|").split("|")]
                cells += [""] * (len(header) - len(cells))
                output.append("| " + " | ".join(cells[position] for position in keep) + " |")
        return clean_markdown_preserving_structure("\n".join(output))

    def _clean_markdown_artifacts(self, text: str) -> str:
        return clean_markdown_preserving_structure(text)

    @staticmethod
    def _ensure_spacing(content: str) -> str:
        return clean_markdown_preserving_structure(content)

    def _replace_placeholders(
        self,
        content: str,
        metadata: Dict[str, Any],
        requirements: Optional[Dict[str, Any]] = None,
    ) -> str:
        req = requirements or {}
        author_org = metadata.get("author_org", "")
        company_name = metadata.get("company_name", "")
        replacements = {
            "AUTHOR_ORG": author_org,
            "AUTHOR_ORG_SHORT": metadata.get("author_org_short") or self._short_name(author_org),
            "COMPANY_NAME": company_name,
            "COMPANY_NAME_SHORT": metadata.get("company_name_short") or self._short_name(company_name),
            "PROJECT_TITLE": metadata.get("project_title", ""),
            "PROJECT_SUBTITLE": metadata.get("project_subtitle", ""),
            "AUTHOR_NAME": metadata.get("author_name", ""),
            "DOCUMENT_DATE": metadata.get("document_date", ""),
            "VERSION": metadata.get("version", "1.0"),
            "START_DATE": metadata.get("start_date") or "",
            "END_DATE": metadata.get("end_date") or "",
            "AUTHOR_ORG_DESCRIPTION": metadata.get("author_org_description", ""),
            "COMPANY_DESCRIPTION": metadata.get("company_description", ""),
            "PLANNING_DURATION_WEEKS": req.get("planning_duration_weeks") or "",
        }
        result = content or ""
        for placeholder, value in replacements.items():
            result = result.replace("{" + placeholder + "}", str(value))
        return result

    def _section_key(self, name: str, metadata: Dict[str, Any]) -> str:
        if "{PROJECT_TITLE}" in name:
            return "cover_page"
        normalized_name = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", name).strip().casefold()
        if normalized_name.startswith("about {company_name}"):
            return "about_company"
        if normalized_name.startswith("about {author_org_short}"):
            return "about_shellkode"
        resolved = self._replace_placeholders(name, metadata)
        if "table" in resolved.lower() and "content" in resolved.lower():
            return "toc_structure"
        resolved = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", resolved).strip()
        mappings = {
            "document control": "document_control_and_basis",
            "document version control": "document_control_and_basis",
            "objective": "project_overview",
            "purpose and scope of this deliverable": "project_overview",
            "current state": "current_state_and_business_context",
            "executive summary and project overview": "project_overview",
            "detailed scope of work": "scope_of_work",
            "scope of work": "scope_of_work",
            "roles and responsibilities": "raci_matrix",
            "detailed production scope of work": "scope_of_work",
            "architecture & integrations": "architecture_integrations",
            "architecture and integrations": "architecture_integrations",
            "architecture overview": "architecture_diagram",
            "solution architecture": "architecture_diagram",
            "solution architecture — aws": "architecture_diagram",
            "solution architecture - aws": "architecture_diagram",
            "timeline and deliverables": "timelines_and_deliverables",
            "project timeline": "timelines_and_deliverables",
            "timelines and deliverables": "timelines_and_deliverables",
            "customer dependencies & responsibilities": "customer_dependencies_responsibilities",
            "shellkode implementation cost": "shellkode_implementation_cost",
        }
        lowered = resolved.lower()
        if lowered.endswith(" project team effort"):
            return "shellkode_implementation_cost"
        if lowered == "assumptions and dependencies":
            return "assumptions"
        if lowered in mappings:
            return mappings[lowered]
        key = re.sub(r"[^\w\s-]", "", lowered)
        return re.sub(r"[-\s]+", "_", key).strip("_")

    @staticmethod
    def _short_name(full_name: str) -> str:
        name = full_name or ""
        for suffix in (
            " Pvt Ltd", " Private Limited", " Pvt. Ltd.", " Ltd", " LLC", " Inc",
            " Corporation", " Corp", " Limited", " Co", " Company",
        ):
            if name.lower().endswith(suffix.lower()):
                return name[:-len(suffix)].strip()
        return name

    @staticmethod
    def _extract_json(text: str) -> Optional[str]:
        match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text or "", re.I | re.S)
        if match:
            return match.group(1)
        start, end = (text or "").find("{"), (text or "").rfind("}")
        return text[start:end + 1] if start >= 0 and end > start else None

    @staticmethod
    def _fmt_list(items: List[str]) -> str:
        return "\n".join(f"- {item}" for item in items) if items else "(none)"

    @staticmethod
    def _fmt_ordered_list(items: List[str]) -> str:
        return "\n".join(f"{i}. {item}" for i, item in enumerate(items, 1)) if items else "(none)"
