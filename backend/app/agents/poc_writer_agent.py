"""Template-driven SOW writer with bounded, section-level generation."""

from __future__ import annotations

import html
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import boto3

from app.core.sow_quality import (
    clean_markdown_preserving_structure,
    classify_complexity,
    normalize_requirements,
    section_quality_issues,
    validate_generated_sections,
)
from app.core.sow_section_preferences import (
    SECTION_LABELS,
    excluded_section_labels,
    parse_selected_section_ids,
    section_category,
)


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

    def __init__(self, config, template_type: str = "POC"):
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
        self.template_raw = self._load_template()
        self.global_template_contract = self._extract_global_template_contract(self.template_raw)
        self.sections = self._parse_template()

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
        rag_context: Optional[Dict[str, Any]] = None,
        supporting_context: Optional[str] = None,
        selected_sow_sections: Optional[List[str]] = None,
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

        active_sections = [
            section for section in self.sections
            if (
                section_category(section.name) is None
                or section_category(section.name) in selected_set
            ) and (
                req.get("ui_required") or section.name not in {
                    "User Interaction Layer", "User Access & Interaction Layer", "UI Development"
                }
            )
        ]
        self.selected_section_preferences = selected_preferences
        self.excluded_section_preferences = excluded_section_labels(selected_preferences, mode)
        source_context = self._context_excerpt(supporting_context, rag_context)
        output: Dict[str, str] = {}
        rendered: Dict[int, Tuple[str, str, bool]] = {}
        generation_jobs: List[Tuple[int, TemplateSection, str]] = []
        consistency_notes = self._consistency_notes(req, metadata, selected_set)

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
            rendered[index] = (key, self._clean_content(content, section.name), False)

        worker_count = self._section_worker_count(len(generation_jobs))
        if generation_jobs:
            print(
                f"   ⚡ Generating {len(generation_jobs)} LLM-authored sections "
                f"with {worker_count} concurrent worker(s)"
            )

        def generate_job(job: Tuple[int, TemplateSection, str]) -> Tuple[int, str, str]:
            index, section, key = job
            print(f"  [{index}/{len(active_sections)}] {section.name}")
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
                cleaned = self._clean_content(
                    self._deterministic_fallback(section, req), resolved_section_name
                )
            return index, key, cleaned

        if worker_count == 1:
            for job in generation_jobs:
                index, key, content = generate_job(job)
                rendered[index] = (key, content, True)
        else:
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="sow-section",
            ) as executor:
                future_jobs = {
                    executor.submit(generate_job, job): job
                    for job in generation_jobs
                }
                completed = 0
                for future in as_completed(future_jobs):
                    job = future_jobs[future]
                    index, section, key = job
                    try:
                        result_index, result_key, content = future.result()
                    except Exception as exc:
                        print(f"    ❌ Unhandled section worker error for {section.name}: {exc}")
                        result_index, result_key = index, key
                        content = self._clean_content(
                            self._deterministic_fallback(section, req), section.name
                        )
                    rendered[result_index] = (result_key, content, True)
                    completed += 1
                    print(
                        f"   ✓ Completed LLM section {completed}/{len(generation_jobs)}: "
                        f"{section.name}"
                    )

        # Reassemble strictly in template order; concurrent completion order must
        # never affect the document's section order or legacy key contract.
        for index in range(1, len(active_sections) + 1):
            key, content, _ = rendered[index]
            output[key] = content

        expected_generated_keys = {
            key for key, _content, generated in rendered.values() if generated
        }
        missing, issues = validate_generated_sections(
            output, mode, required_keys=expected_generated_keys
        )
        if missing:
            print(f"⚠ Generation gate missing expected sections: {', '.join(missing)}")
        if issues:
            print(f"⚠ Generation gate reported {len(issues)} quality issue(s)")
        output["generation_quality_summary"] = self._quality_summary(missing, issues, req)
        print(f"✅ Assembly complete - {len(output)} sections")
        return output

    def _section_worker_count(self, job_count: int) -> int:
        configured = getattr(self.config, "SOW_SECTION_WORKERS", 4)
        try:
            configured = int(configured)
        except (TypeError, ValueError):
            configured = 4
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
            unnumbered_poc_title = self.template_type == "POC" and (
                title.casefold().startswith("document control")
                or "acceptance and signator" in title.casefold()
            )
            if unnumbered_poc_title:
                lines.append(title)
            else:
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
        prompt = self._build_individual_prompt(
            section, requirements, metadata, source_context,
            prior_context="\n".join(prior_summaries[-4:]),
        )
        content = self._call_bedrock(prompt, max_tokens=self._section_token_budget(section))
        issues = self._authoring_issues(content, section)
        if issues:
            retry = f"""The previous draft of the {section.name!r} section failed these checks:
{chr(10).join('- ' + issue for issue in issues)}

Rewrite the section completely. Preserve every source-grounded fact, label proposals and
planning assumptions, answer the template instructions, and return only the Markdown body.

ORIGINAL AUTHORING BRIEF:
{prompt}

PREVIOUS DRAFT:
{content[:8000]}"""
            revised = self._call_bedrock(retry, max_tokens=self._section_token_budget(section))
            revised_issues = self._authoring_issues(revised, section)
            if not revised_issues:
                content = revised
            elif not content.strip():
                content = revised
            elif (
                revised.strip()
                and any("word section limit" in issue for issue in issues)
                and len(re.findall(r"\b\w+\b", revised))
                < len(re.findall(r"\b\w+\b", content))
            ):
                # Keep a materially shorter revision even when it still carries
                # a separate review flag; this prevents a verbose first draft
                # from winning merely because neither draft is perfect.
                content = revised
        if not content.strip():
            content = self._deterministic_fallback(section, requirements)
        return content

    @staticmethod
    def _authoring_issues(content: str, section: TemplateSection) -> List[str]:
        issues = section_quality_issues(content, section.name)
        name = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", section.name).casefold()
        word_count = len(re.findall(r"\b\w+\b", content or ""))
        word_limit = POCWriterAgent._section_word_limit(section)
        if word_count > word_limit:
            issues.append(
                f"exceeds the {word_limit}-word section limit; remove repetition and non-essential detail"
            )
        for line in (content or "").splitlines():
            if re.match(r"^\s*\|.+\|\s*$", line):
                columns = len(line.strip().strip("|").split("|"))
                if columns > 5:
                    issues.append("contains a table wider than five columns")
                    break

        # Section-specific contract checks turn the detailed Markdown template
        # into an enforceable generation gate rather than optional guidance.
        normalized = (content or "").casefold()
        table_lines = [
            line.casefold() for line in (content or "").splitlines()
            if re.match(r"^\s*\|.+\|\s*$", line)
        ]
        if name.startswith("document control"):
            if not any(all(label in line for label in ("version", "date", "prepared by", "status", "classification")) for line in table_lines):
                issues.append("Document Control is missing the required five-column control table")
            if "revision basis" not in normalized:
                issues.append("Document Control is missing Revision Basis")
        elif name.startswith("deliverable scope at a glance"):
            if not any(all(label in line for label in ("module/workstream", "core outcome", "depends on")) for line in table_lines):
                issues.append("Scope at a Glance is missing the required module dependency table")
        elif name.startswith("detailed scope of work"):
            module_headings = re.findall(r"(?m)^###\s+4\.\d+\s+.+$", content or "")
            if len(module_headings) < 2:
                issues.append("Detailed Scope needs at least two numbered module/workstream subsections")
            if len(module_headings) > 6:
                issues.append("Detailed Scope has more than six modules; consolidate supporting layers unless the source explicitly requires them")
            if not any(all(label in line for label in ("id", "requirement", "detail")) for line in table_lines):
                issues.append("Detailed Scope is missing a compact ID / Requirement / Detail table")
            if "dependencies and validation" not in normalized:
                issues.append("Detailed Scope is missing module dependencies and validation evidence")
            workflow_blocks = re.split(
                r"(?m)^####\s+(?:\d+(?:\.\d+)*\s+)?workflow\s*$",
                content or "",
                flags=re.I,
            )[1:]
            total_workflow_steps = 0
            for workflow in workflow_blocks:
                workflow = re.split(r"(?m)^#{3,5}\s+", workflow, maxsplit=1)[0]
                count = len(re.findall(r"(?m)^\s*\d+[.)]\s+", workflow))
                total_workflow_steps += count
                if count > 8:
                    issues.append("A Workflow subsection exceeds eight steps and must be consolidated into phases")
                    break
            if total_workflow_steps > 30:
                issues.append("Detailed Scope contains more than thirty workflow steps across modules; remove sparse or non-sequential workflows")
        elif name.startswith("solution architecture"):
            for required in ("high-level architecture", "end-to-end data flow", "low-level architecture", "security and observability"):
                if required not in normalized:
                    issues.append(f"Architecture is missing {required}")
        elif name.startswith("open clarifications"):
            if not any(all(label in line for label in ("module/area", "open item", "status / note")) for line in table_lines):
                issues.append("Open Clarifications is missing the required register table")
        elif name.startswith("aws pricing"):
            if "pricing calculator" not in normalized and "pricing is pending" not in normalized:
                issues.append("AWS Pricing neither reproduces a calculator basis nor marks pricing pending")
        elif name.endswith("project team effort"):
            if not any(all(label in line for label in ("resource", "resource count", "effort duration in weeks")) for line in table_lines):
                issues.append("Project Team Effort is missing the required staffing table")
        return issues

    @staticmethod
    def _section_word_limit(section: TemplateSection) -> int:
        """Return a compact but workable maximum for one generated section."""
        name = re.sub(
            r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", section.name
        ).casefold()
        if name.startswith("document control"):
            return 350
        if name.startswith("about "):
            return 220
        if any(term in name for term in ("detailed scope", "technical specification")):
            return 1200
        if "architecture" in name:
            return 800
        if any(term in name for term in ("terms and conditions", "testing and acceptance")):
            return 650
        return 450

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
        return f"""You are a principal solutions architect and senior commercial technical writer.
Write the body of one section in a benchmark-quality {type_label} Statement of Work.

DOCUMENT CONTEXT
- Customer: {metadata.get('company_name', '')}
- Project: {metadata.get('project_title', '')}
- Author organization: {metadata.get('author_org', '')}
- Mode: {self.template_type}

AUTHORITATIVE REQUIREMENTS BASELINE
{json.dumps(requirements, indent=2, default=str)}

SOURCE EXCERPT (supporting evidence; may be empty)
{supporting_context or '(none)'}

DOCUMENT CONSISTENCY NOTES
{prior_context or '(none)'}

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

SECTION LENGTH BUDGET
- Hard maximum: {self._section_word_limit(section)} words, including tables and lists.
- Use fewer words when the source is sparse. Completeness means covering the necessary
  decision, scope, dependency, responsibility, and validation information once; it does
  not mean expanding every possible implementation detail.

NON-NEGOTIABLE AUTHORING STANDARD
- Return only the Markdown body. Do not repeat the top-level section heading and do not use code fences.
- Use British Indian English throughout, never US spelling. Prefer forms such as
  organisation, organise, centralised, analyse, behaviour, colour, programme,
  licence (noun), and fulfilment. Preserve official product names, API fields,
  source quotations, and other identifiers exactly as supplied.
- Treat user/source values as confirmed; treat architect-derived choices as "Proposed"; put
  unknown material facts under "Open clarification" or state that they require confirmation.
- Never invent customer facts, dates, prices, volumes, user counts, compliance claims, SLAs,
  model versions, named contacts, or achieved results.
- Do not present a planning target as an agreed acceptance criterion. If the source is silent,
  propose a testable target and explicitly label it "proposed for baseline confirmation".
- Be specific about capability, owner, input, output, boundary, dependency, and validation method.
- Preserve cross-section consistency for terminology, timeline, scope, services, and metrics.
- Preserve supplied compliance and regulatory wording exactly, including regulator names,
  disclaimer language, residency constraints, qualifications, and human-review boundaries.
  Never turn an expectation, design intent, or pending confirmation into a compliance claim.
- Prefer one short orienting paragraph followed by the lightest useful structure. Do not
  restate the project objective, customer context, or the same requirement in multiple forms.
- Avoid more than two consecutive prose paragraphs. Use concise bullets for three or more
  non-comparable items and Markdown tables only for genuinely comparable records.
- Use ### and #### for real subsection headings, standard '-' bullets, and '1.' numbered steps.
- Put every bullet on its own Markdown line. Use one idea per bullet, normally one sentence,
  and keep lists to three-to-seven items unless the source requires more. Use two leading
  spaces for a nested bullet and never embed bullet symbols inside a prose paragraph.
- Keep heading hierarchy complete and consistent. The DOCX renderer normalizes every
  generated heading to 1.1 / 1.2 / 4.1 / 4.1.1 form; never use a bold Normal paragraph
  as a substitute for a heading and never skip from a module heading to an unstructured label.
- Use numbered workflows only for genuine sequences, keep each to four-to-eight stages,
  and never continue numbering across separate modules or workflow blocks.
- For tables, emit a valid pipe table with one separator row; use <br> only for multiple items in a cell.
- Use no more than five table columns, and prefer two to four. Put explanatory detail below
  the table or split it into sequential compact tables instead of creating narrow columns.
- Do not create a new top-level section. Keep every requested detail within this section's
  benchmark-defined boundary and do not append generic SOW boilerplate.
- Omit generic background, textbook explanations, marketing language, and implementation
  possibilities that do not change scope, ownership, dependency, acceptance, or a decision.
- When Architecture Diagram is selected, write only the decisions, constraints, flows and unresolved
  boundaries needed to interpret the generated visual. Do not duplicate the visual as a long component
  catalogue, and never claim that a source-supplied diagram exists when it does not.
- The section should be complete enough for commercial and technical review, without filler or repetition.
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

    def _call_bedrock(self, prompt: str, max_tokens: int = 6000) -> str:
        try:
            response = self.bedrock.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": min(max_tokens, 8192),
                    "temperature": 0.15,
                    "messages": [{"role": "user", "content": prompt}],
                }),
            )
            body = json.loads(response["body"].read())
            from app.core.nodes import _track_tokens
            _track_tokens(body, "SOW Section Generation")
            return body["content"][0]["text"].strip()
        except Exception as exc:
            print(f"    ❌ Section generation error: {exc}")
            return ""

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
        # Give the model enough room for Markdown structure without allowing a
        # multi-thousand-word section that later has to be cut down.
        word_limit = POCWriterAgent._section_word_limit(section)
        return max(900, min(3200, word_limit * 2))

    @staticmethod
    def _context_excerpt(
        supporting_context: Optional[str],
        rag_context: Optional[Dict[str, Any]],
        limit: int = 18000,
    ) -> str:
        sources: List[str] = []
        if supporting_context:
            sources.append(str(supporting_context))
        rag_data = (rag_context or {}).get("rag_data", {}) if isinstance(rag_context, dict) else {}
        if isinstance(rag_data, dict) and rag_data.get("extracted_content"):
            sources.append(str(rag_data["extracted_content"]))
        text = "\n\n".join(sources)
        if len(text) <= limit:
            return text
        third = limit // 3
        middle_start = max(0, len(text) // 2 - third // 2)
        return (
            text[:third] + "\n\n[...middle excerpt...]\n\n" +
            text[middle_start:middle_start + third] + "\n\n[...final excerpt...]\n\n" +
            text[-third:]
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
        if "clarification" in section.name.lower():
            items = requirements.get("open_clarifications", [])
            return "\n".join(f"- {item}" for item in items) or "- Scope baseline requires customer confirmation."
        overview = requirements.get("project_overview") or "The section requires completion from the approved requirements baseline."
        return (
            f"{overview}\n\n"
            "This draft section could not be expanded by the generation service. Its detailed baseline must be completed during review."
        )

    def _enrich_requirements(self, req: Dict[str, Any]) -> Dict[str, Any]:
        return normalize_requirements(req, req.get("_original_objective", ""), self.template_type)

    def _classify_complexity(self, req: Dict[str, Any]) -> ProjectComplexity:
        return ProjectComplexity(classify_complexity(req))

    @staticmethod
    def _needs_generation(content: str) -> bool:
        return bool(re.search(r"\b(generate|write|derive|using objective|instructions?|rules?)\b", content or "", re.I))

    def _clean_content(self, content: str, section_name: str) -> str:
        content = clean_markdown_preserving_structure(content or "")
        lines = content.splitlines()
        while lines and re.match(r"^#{1,2}\s+", lines[0]):
            heading = re.sub(r"^#{1,2}\s+", "", lines[0]).strip()
            if heading.casefold() == section_name.casefold():
                lines.pop(0)
                while lines and not lines[0].strip():
                    lines.pop(0)
            else:
                break
        return clean_markdown_preserving_structure("\n".join(lines))

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
            "START_DATE": metadata.get("start_date") or "To be confirmed",
            "END_DATE": metadata.get("end_date") or "To be confirmed",
            "AUTHOR_ORG_DESCRIPTION": metadata.get("author_org_description", ""),
            "COMPANY_DESCRIPTION": metadata.get("company_description", ""),
            "PLANNING_DURATION_WEEKS": req.get("planning_duration_weeks", "To be confirmed"),
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
            "purpose and scope of this deliverable": "project_overview",
            "deliverable scope at a glance": "scope_at_a_glance",
            "current state": "current_state_and_business_context",
            "executive summary and project overview": "project_overview",
            "detailed scope of work": "scope_of_work",
            "detailed production scope of work": "scope_of_work",
            "architecture & integrations": "architecture_integrations",
            "architecture and integrations": "architecture_integrations",
            "architecture overview": "architecture_diagram",
            "solution architecture — aws": "architecture_diagram",
            "solution architecture - aws": "architecture_diagram",
            "timeline and deliverables": "timelines_and_deliverables",
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
