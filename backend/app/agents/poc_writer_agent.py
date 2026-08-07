"""
POC Writer Agent - FULLY ADAPTIVE, OBJECTIVE-DRIVEN Generation
UPDATED: All generation is driven by objective_analysis fields with no hardcoded assumptions.
Supports POC and PROD template types with conditional logic matching updated templates.
"""
import json
import os
import re
import html
import boto3
from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

class TemplateSection:
    def __init__(self, name: str, content: str, metadata: Dict[str, Any], order: int):
        self.name = name
        self.content = content
        self.metadata = metadata
        self.order = order
        self.has_explicit_metadata = metadata.get('_explicit', False)
        self.section_type = SectionType[metadata.get('type', 'GENERATED')]
        self.dependencies = metadata.get('depends_on', [])
        self.context = metadata.get('context', '')

    def __repr__(self):
        marker = "✓" if self.has_explicit_metadata else "→"
        return f"TemplateSection({marker} {self.name}, type={self.section_type.value})"


# ---------------------------------------------------------------------------
# Main agent
# ---------------------------------------------------------------------------

class POCWriterAgent:
    """
    Fully adaptive SOW writer.

    The agent reads template instructions as authoritative prompts, injects
    the complete objective_analysis into every generation call, and applies
    conditional logic (ui_required, complexity, integration_details,
    compliance_requirements) consistently across all sections.
    """

    def __init__(self, config, template_type: str = "POC"):
        self.config = config
        self.template_type = template_type
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=config.AWS_REGION,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN'),
            config=config.BOTO_CONFIG
        )
        self.template_raw = self._load_template()
        self.sections = self._parse_template()

    # ------------------------------------------------------------------
    # Template loading & parsing
    # ------------------------------------------------------------------

    def _load_template(self) -> str:
        template_file = (
            self.config.PRODUCTION_TEMPLATE_FILE
            if self.template_type == "PROD"
            else self.config.POC_TEMPLATE_FILE
        )
        if template_file.exists():
            with open(template_file, 'r', encoding='utf-8') as f:
                content = f.read()
                print(f"✓ Loaded template: {template_file.name}")
                return content
        print(f"⚠  Template not found: {template_file}")
        return ""

    def _parse_template(self) -> List[TemplateSection]:
        if not self.template_raw:
            return []

        decoded = html.unescape(self.template_raw)
        lines = decoded.split('\n')
        meta_pattern = re.compile(r'\[META_([A-Z_]+)(?:_(.+?))?\]', re.IGNORECASE)

        # Pass 1: collect metadata line markers
        metadata_map: Dict[int, Dict] = {}
        for i, line in enumerate(lines):
            m = meta_pattern.search(line.strip())
            if m:
                meta_type = m.group(1).upper()
                extra = m.group(2) or ""
                metadata_map[i] = self._parse_meta_marker(meta_type, extra)
                metadata_map[i]['_explicit'] = True

        # Pass 2: build sections
        sections: List[TemplateSection] = []
        cur_name: Optional[str] = None
        cur_content: List[str] = []
        cur_meta: Dict = {}
        order = 0

        for i, line in enumerate(lines):
            if i in metadata_map:
                continue
            stripped = line.strip()
            # Only top-level ## headers start new sections
            if stripped.startswith('## ') and not stripped.startswith('### '):
                if cur_name:
                    sections.append(TemplateSection(
                        name=cur_name,
                        content='\n'.join(cur_content).strip(),
                        metadata=cur_meta,
                        order=order
                    ))
                    order += 1
                cur_name = stripped[3:].strip()
                cur_content = []
                # Find the closest preceding metadata marker
                cur_meta = {}
                for check in range(max(0, i - 4), i):
                    if check in metadata_map:
                        cur_meta = metadata_map[check].copy()
                        break
                if not cur_meta:
                    cur_meta = {'_explicit': False, '_infer_later': True}
            elif cur_name:
                cur_content.append(line)

        if cur_name:
            sections.append(TemplateSection(
                name=cur_name,
                content='\n'.join(cur_content).strip(),
                metadata=cur_meta,
                order=order
            ))

        # Pass 3: infer metadata for unmarked sections
        for s in sections:
            if s.metadata.get('_infer_later'):
                inferred = self._infer_metadata(s.name, s.content)
                inferred['_explicit'] = False
                s.metadata = inferred
                s.has_explicit_metadata = False
                s.section_type = SectionType[inferred.get('type', 'GENERATED')]

        explicit = sum(1 for s in sections if s.has_explicit_metadata)
        print(f"✓ Parsed {len(sections)} sections ({explicit} explicit, {len(sections)-explicit} inferred)")
        return sections

    def _parse_meta_marker(self, meta_type: str, extra: str) -> Dict[str, Any]:
        valid_composites = {'STATIC_TABLE'}
        if '_' in meta_type and meta_type not in valid_composites:
            parts = meta_type.split('_', 1)
            if not extra and len(parts) > 1:
                extra = parts[1]
            meta_type = parts[0]
        meta: Dict[str, Any] = {'type': meta_type}
        if extra:
            parts = extra.lower().split('_')
            if meta_type == 'HYBRID':
                meta['context'] = parts[0]
            elif meta_type == 'TABLE':
                meta['depends_on'] = parts
            else:
                meta['context'] = '_'.join(parts)
        return meta

    def _infer_metadata(self, name: str, content: str) -> Dict[str, Any]:
        has_table = '|' in content and content.count('|') > 3
        instruction_kws = ['write', 'format', 'list', 'generate', 'provide', 'describe',
                           'using', 'derive', 'include', 'only if', 'conditional']
        has_instructions = any(kw in content.lower() for kw in instruction_kws)
        has_placeholders = bool(re.search(r'\{[A-Z_]+\}', name + content))

        if has_table and not has_instructions:
            return {'type': 'STATIC_TABLE'}
        if has_table and has_instructions:
            return {'type': 'TABLE'}
        if has_instructions:
            return {'type': 'GENERATED'}
        if has_placeholders:
            return {'type': 'HYBRID'}
        return {'type': 'STATIC'}

    # ------------------------------------------------------------------
    # Main generation entry point
    # ------------------------------------------------------------------

    def generate_poc(
        self,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        rag_context: Optional[Dict[str, Any]] = None,
        supporting_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate the complete SOW document.

        Args:
            requirements: Output from ObjectiveAgent.analyze_objective()
            metadata: Document metadata (company_name, project_title, author_name, etc.)
            rag_context: Optional RAG enrichment data
            supporting_context: Optional additional context from supporting documents

        Returns:
            Dict mapping section keys to rendered markdown content
        """
        print(f"\n🚀 Starting {'PROD' if self.template_type == 'PROD' else 'POC'} SOW Generation")

        # Compute derived fields consumed by templates
        requirements = self._enrich_requirements(requirements)

        # Filter out UI-related sections if ui_required=false
        ui_required = requirements.get('ui_required', False)
        if not ui_required:
            ui_section_names = ['User Interaction Layer', 'User Access & Interaction Layer', 'UI Development']
            original_sections = self.sections
            self.sections = [s for s in self.sections if s.name not in ui_section_names]
            filtered_count = len(original_sections) - len(self.sections)
            if filtered_count > 0:
                print(f"  🚫 Filtered out {filtered_count} UI-related sections (ui_required=false)")

        # Metadata shorthands
        metadata['author_org_short'] = self._short_name(metadata.get('author_org', ''))
        metadata['company_name_short'] = self._short_name(metadata.get('company_name', ''))

        if not metadata.get('project_title'):
            metadata['project_title'] = metadata.get('objective', 'Untitled Project')

        print(f"  Project: {metadata['project_title']}")
        print(f"  Company: {metadata.get('company_name', '')}")
        print(f"  Complexity: {requirements.get('_complexity', 'unknown')}")

        # Optionally merge RAG data
        if rag_context and rag_context.get('rag_data'):
            requirements = self._merge_rag(requirements, rag_context['rag_data'])

        # Identify sections to generate
        generatable_types = {SectionType.GENERATED, SectionType.TABLE}
        sections_to_generate = [
            s for s in self.sections
            if s.section_type in generatable_types
            or (s.section_type == SectionType.HYBRID and self._needs_generation(s.content))
        ]

        print(f"\n⚡ Generating {len(sections_to_generate)} dynamic sections...")
        section_names = [s.name for s in sections_to_generate]
        print(f"  📝 Sections to generate: {section_names}")

        # Build prompt and call LLM
        prompt = self._build_prompt(sections_to_generate, requirements, metadata, supporting_context)
        generated = self._call_bedrock_batch(prompt, sections_to_generate)
        
        # Check if any critical sections are missing and try individual generation
        template_names = {s.name for s in self.sections}
        missing_sections = [s for s in sections_to_generate if s.name not in generated]
        
        if missing_sections:
            print(f"  🔄 Attempting individual generation for {len(missing_sections)} missing sections...")
            for section in missing_sections:
                try:
                    # For complex sections that might truncate, use focused prompt
                    if self._is_complex_section(section.name):
                        print(f"    🎯 Using focused prompt for complex section: {section.name}")
                        focused_result = self._retry_with_focused_prompt(section, requirements, metadata)
                        if focused_result:
                            generated[section.name] = focused_result
                            print(f"    ✓ Generated {section.name} with focused approach")
                            continue
                    
                    individual_prompt = self._build_individual_prompt(section, requirements, metadata, supporting_context)
                    individual_result = self._call_bedrock(individual_prompt, max_tokens=60000)
                    
                    # Try to extract JSON from individual result
                    json_str = self._extract_json(individual_result)
                    if json_str:
                        # Clean control characters before parsing
                        cleaned_json = self._clean_json_control_chars(json_str)
                        section_data = json.loads(cleaned_json)
                        if isinstance(section_data, dict) and section.name in section_data:
                            content = section_data[section.name]
                            # Check if content is truncated and retry with focused prompt
                            if self._is_content_truncated(content):
                                print(f"    ⚠️ Content truncated for {section.name}, retrying with focused prompt...")
                                focused_result = self._retry_with_focused_prompt(section, requirements, metadata)
                                if focused_result:
                                    generated[section.name] = focused_result
                                    print(f"    ✓ Generated {section.name} with focused retry")
                                else:
                                    generated[section.name] = content  # Use truncated version as fallback
                                    print(f"    ⚠️ Using truncated content for {section.name}")
                            else:
                                generated[section.name] = content
                                print(f"    ✓ Generated {section.name} individually")
                        elif isinstance(section_data, str):
                            content = section_data
                            if self._is_content_truncated(content):
                                print(f"    ⚠️ Content truncated for {section.name}, retrying with focused prompt...")
                                focused_result = self._retry_with_focused_prompt(section, requirements, metadata)
                                if focused_result:
                                    generated[section.name] = focused_result
                                    print(f"    ✓ Generated {section.name} with focused retry")
                                else:
                                    generated[section.name] = content
                                    print(f"    ⚠️ Using truncated content for {section.name}")
                            else:
                                generated[section.name] = content
                                print(f"    ✓ Generated {section.name} individually (string)")
                except Exception as e:
                    print(f"    ❌ Failed to generate {section.name}: {e}")
                    # Add a placeholder to prevent complete failure
                    generated[section.name] = f"[Section {section.name} generation failed - please regenerate]"

        # Filter to only sections present in this template
        template_names = {s.name for s in self.sections}
        generatable_names = {s.name for s in sections_to_generate}
        
        print(f"  📋 Generatable sections: {sorted(generatable_names)}")
        print(f"  🤖 Generated sections: {sorted(generated.keys())}")
        
        # Check for mismatches in generatable sections only
        missing_from_generated = generatable_names - set(generated.keys())
        extra_in_generated = set(generated.keys()) - generatable_names
        
        if missing_from_generated:
            print(f"  ⚠️  Missing from LLM response: {sorted(missing_from_generated)}")
        if extra_in_generated:
            print(f"  ℹ️  Extra in LLM response: {sorted(extra_in_generated)}")
        
        generated = {k: v for k, v in generated.items() if k in template_names}

        print(f"✓ Generated {len(generated)} sections successfully")

        # Assemble final output
        output: Dict[str, str] = {}
        for section in self.sections:
            key = self._section_key(section.name, metadata)

            if section.name in generated:
                content = generated[section.name]
                content = self._replace_placeholders(content, metadata)
                content = self._clean_content(content, section.name)
                output[key] = content
            else:
                # Static, static-table, or ungenerated hybrid sections
                if section.section_type in (SectionType.STATIC, SectionType.STATIC_TABLE):
                    output[key] = self._replace_placeholders(section.content, metadata)
                elif section.section_type == SectionType.HYBRID:
                    output[key] = self._replace_placeholders(section.content, metadata)
                else:
                    print(f"  ⚠ Skipping ungenerated section: {section.name}")

        print(f"\n✅ Assembly complete — {len(output)} sections in final document")
        return output

    # ------------------------------------------------------------------
    # Requirements enrichment
    # ------------------------------------------------------------------

    def _enrich_requirements(self, req: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compute derived fields from objective_analysis so templates and prompts
        receive ready-to-use values without repeated calculations.
        """
        enriched = req.copy()

        # Complexity classification
        complexity = self._classify_complexity(req)
        enriched['_complexity'] = complexity.value

        # Accuracy floor based on complexity
        accuracy_floors = {
            'simple': 85, 'moderate': 90, 'complex': 95, 'enterprise': 99
        }
        prod_accuracy_floors = {
            'simple': 90, 'moderate': 93, 'complex': 97, 'enterprise': 99
        }
        floors = prod_accuracy_floors if self.template_type == 'PROD' else accuracy_floors
        enriched['_accuracy_floor'] = floors[complexity.value]

        # Latency targets based on complexity
        latency_map = {
            'simple': 5, 'moderate': 3, 'complex': 2, 'enterprise': 1
        }
        enriched['_latency_target'] = latency_map[complexity.value]

        # Retention duration
        retention_map = {
            'simple': '7 days', 'moderate': '30 days',
            'complex': '90 days', 'enterprise': '1 year'
        }
        enriched['_retention'] = retention_map[complexity.value]

        # Feedback SLA
        feedback_map = {
            'simple': 3, 'moderate': 5, 'complex': 5, 'enterprise': 7
        }
        enriched['_feedback_sla_days'] = feedback_map[complexity.value]

        # AWS account access provision time
        access_map = {'simple': 1, 'moderate': 1, 'complex': 2, 'enterprise': 2}
        enriched['_access_provision_weeks'] = access_map[complexity.value]

        # Bullet counts for different sections
        bullet_map = {'simple': 3, 'moderate': 3, 'complex': 4, 'enterprise': 5}
        enriched['_bullet_count'] = bullet_map[complexity.value]

        # Persona paragraph count cap
        persona_map = {'simple': 2, 'moderate': 3, 'complex': 4, 'enterprise': 5}
        enriched['_max_personas'] = persona_map[complexity.value]

        # Incident SLAs
        sla_map = {
            'simple': {'p1': '4hr', 'p2': '8hr', 'p3': 'next business day'},
            'moderate': {'p1': '2hr', 'p2': '4hr', 'p3': '8hr'},
            'complex': {'p1': '1hr', 'p2': '2hr', 'p3': '4hr'},
            'enterprise': {'p1': '30min', 'p2': '1hr', 'p3': '2hr'},
        }
        enriched['_incident_sla'] = sla_map[complexity.value]

        # Duration ranges - respect user-provided timeline if available
        if 'duration_weeks' in req and req['duration_weeks']:
            # User provided specific timeline, use it
            user_weeks = req['duration_weeks']
            enriched['_duration_range'] = (user_weeks, user_weeks)
            print(f"   ✅ Using user-specified duration: {user_weeks} weeks")
        else:
            # Use default duration ranges based on complexity
            poc_durations = {
                'simple': (4, 6), 'moderate': (6, 8),
                'complex': (8, 10), 'enterprise': (10, 14)
            }
            prod_durations = {
                'simple': (8, 12), 'moderate': (12, 18),
                'complex': (18, 24), 'enterprise': (24, 32)
            }
            durations = prod_durations if self.template_type == 'PROD' else poc_durations
            enriched['_duration_range'] = durations[complexity.value]

        # Annual data volume (for end-state vision)
        data_gb = req.get('data_volume_gb', 5)
        enriched['_annual_data_gb'] = data_gb * 12

        # Double-capacity for scalability success criterion
        enriched['_scale_users'] = req.get('concurrent_users', 20) * 2

        # Whether 24x7 monitoring is required
        enriched['_monitoring_24x7'] = complexity.value in ('complex', 'enterprise')

        return enriched

    def _classify_complexity(self, req: Dict[str, Any]) -> ProjectComplexity:
        """
        Score-based complexity classification using objective_analysis fields.
        Each signal contributes a weighted score.
        """
        aws_services = req.get('aws_services', [])
        integration_details = req.get('integration_details', [])
        workflow_steps = req.get('workflow_steps', [])
        data_volume_gb = req.get('data_volume_gb', 5)
        ui_required = req.get('ui_required', False)
        compliance = req.get('compliance_requirements', [])
        concurrent_users = req.get('concurrent_users', 20)

        # AI/ML service count
        ai_services = [s for s in aws_services
                       if any(k in s.lower() for k in ('bedrock', 'sagemaker', 'comprehend',
                                                        'rekognition', 'forecast', 'personalize'))]
        score = 0
        score += min(len(ai_services), 4) * 2          # 0–8
        score += min(len(integration_details), 5) * 2  # 0–10
        score += min(len(workflow_steps) - 2, 4)        # 0–4
        score += 2 if data_volume_gb > 50 else (1 if data_volume_gb > 5 else 0)
        score += 2 if ui_required else 0
        score += 2 if compliance else 0
        score += 2 if concurrent_users > 100 else (1 if concurrent_users > 20 else 0)

        if score <= 5:
            return ProjectComplexity.SIMPLE
        elif score <= 10:
            return ProjectComplexity.MODERATE
        elif score <= 16:
            return ProjectComplexity.COMPLEX
        else:
            return ProjectComplexity.ENTERPRISE

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        sections: List[TemplateSection],
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        supporting_context: Optional[str] = None
    ) -> str:
        """
        Build a comprehensive single-shot prompt for batch section generation.
        The prompt injects the full objective_analysis as a structured context block
        so every section is driven by the actual project data.
        """
        ui_required = requirements.get('ui_required', False)
        complexity = requirements.get('_complexity', 'moderate')
        aws_services = requirements.get('aws_services', [])
        integration_details = requirements.get('integration_details', [])
        compliance = requirements.get('compliance_requirements', [])
        primary_personas = requirements.get('primary_personas', [])
        workflow_steps = requirements.get('workflow_steps', [])
        data_chars = requirements.get('data_characteristics', {})
        success_metrics = requirements.get('success_metrics', [])
        industry = requirements.get('industry', 'generic')

        supporting_section = ""
        if supporting_context:
            supporting_section = f"""

===============================================================
SUPPORTING DOCUMENTS CONTEXT
===============================================================
The following additional documents were provided to enrich the SOW generation.
Use this information to add specific details, requirements, and context to all sections:

{supporting_context}

===============================================================
"""

        prompt = f"""You are an expert technical writer generating a {'Production' if self.template_type == 'PROD' else 'POC'} Statement of Work (SOW).

🚨 CRITICAL INSTRUCTION: The objective analysis below contains USER-PROVIDED DATA that was extracted from their specific requirements. You MUST use these exact values instead of making assumptions or using defaults. When the user specifies timeline, data volume, or other metrics, use those EXACT values.

🚨🚨🚨 TIMELINE PRIORITY SYSTEM 🚨🚨🚨
For the "Timelines and Deliverables" section, follow this STRICT priority:
1. If Duration (weeks) shows a number → USE THAT EXACT NUMBER as total project duration
2. If Timeline field shows a duration → USE THAT EXACT DURATION as total project duration
3. ONLY if both show "Not specified" → use complexity-based calculations

EXAMPLE: If Duration (weeks) = 8, your project MUST be exactly 8 weeks total, NOT 6-8 weeks or any other range.
{supporting_section}
===============================================================
DOCUMENT CONTEXT
===============================================================
Company:       {metadata.get('company_name', '')}
Project:       {metadata.get('project_title', '')}
Template Type: {self.template_type}
Document Date: {metadata.get('document_date', '')}

===============================================================
OBJECTIVE ANALYSIS — USE THIS DATA TO DRIVE ALL CONTENT
===============================================================
Industry:            {industry}
Complexity Level:    {complexity}
UI Required:         {ui_required}
Deployment Env:      {requirements.get('deployment_environment', 'serverless')}
Data Volume (GB):    {requirements.get('data_volume_gb', 5)}
Data Volume Desc:    {requirements.get('data_volume_description', 'Not specified')}
Invoice Volume:      {requirements.get('invoice_volume', 'Not specified')}
Document Volume:     {requirements.get('document_volume', 'Not specified')}
SKU Count:           {requirements.get('sku_count', 'Not specified')}
Timeline:            {requirements.get('timeline', 'Not specified')}
Duration (weeks):    {requirements.get('duration_weeks', 'Not specified')}
Concurrent Users:    {requirements.get('concurrent_users', 20)}
Annual Data (GB):    {requirements.get('_annual_data_gb', 60)}
Scale Users (2×):    {requirements.get('_scale_users', 40)}
Accuracy Floor:      {requirements.get('_accuracy_floor', 90)}%
Latency Target:      <{requirements.get('_latency_target', 3)}s p95
Retention Policy:    {requirements.get('_retention', '30 days')}
Feedback SLA:        {requirements.get('_feedback_sla_days', 5)} business days
Access Provision:    {requirements.get('_access_provision_weeks', 1)} week(s) after SOW
Bullet Count:        {requirements.get('_bullet_count', 3)} bullets per section
Max Personas:        {requirements.get('_max_personas', 3)}
Duration Range:      {requirements.get('_duration_range', (6, 8))[0]}–{requirements.get('_duration_range', (6, 8))[1]} weeks
Incident SLAs:       P1={requirements.get('_incident_sla', {}).get('p1', '2hr')}, P2={requirements.get('_incident_sla', {}).get('p2', '4hr')}, P3={requirements.get('_incident_sla', {}).get('p3', '8hr')}
24×7 Monitoring:     {requirements.get('_monitoring_24x7', False)}

AWS Services:
{self._fmt_list(aws_services)}

Key Features:
{self._fmt_list(requirements.get('key_features', []))}

Workflow Steps (in order):
{self._fmt_ordered_list(workflow_steps)}

Primary Personas:
{self._fmt_list(primary_personas)}

Use Cases:
{self._fmt_list(requirements.get('use_cases', []))}

Success Metrics:
{self._fmt_list(success_metrics)}

Data Characteristics:
  Volume:         {data_chars.get('volume', 'Not specified')}
  Format:         {data_chars.get('format', 'Not specified')}
  Access Pattern: {data_chars.get('access_pattern', 'Not specified')}

Integration Details:
{self._fmt_list(integration_details) if integration_details else '  (None — no external system integrations)'}

Compliance Requirements:
{self._fmt_list(compliance) if compliance else '  (None — standard AWS security best practices apply)'}

Security Requirements:
{self._fmt_list(requirements.get('security_requirements', []))}

Performance Requirements:
{self._fmt_list(requirements.get('performance_requirements', []))}

Accuracy Metrics:
  Target:      {requirements.get('accuracy_metrics', {}).get('target_percentage', 90)}%
  Method:      {requirements.get('accuracy_metrics', {}).get('measurement_method', 'human review')}
  Constraints: {requirements.get('accuracy_metrics', {}).get('domain_constraints', 'English only')}

MRR Estimate:  ${requirements.get('mrr_estimate', 500):,}/month (POC scale)

===============================================================
INDUSTRY CONTEXT: {industry.upper().replace('_', ' ')}
===============================================================
{self._get_industry_guidance(industry)}

===============================================================
CONDITIONAL GENERATION RULES (apply to ALL sections)
===============================================================
1. UI_REQUIRED={ui_required}
   - If FALSE: rename "User Interaction Layer" → "API & Service Integration Layer"
              describe API contracts, auth, rate limiting — NOT web UI
   - If TRUE:  describe web-based dashboard, role-based UI, review workflows

2. INTEGRATIONS: {len(integration_details)} external systems detected
   - If EMPTY: do NOT mention third-party API integration in scope/arch
              replace with "Internal Service Communication" patterns
   - If NON-EMPTY: reference these specific systems: {', '.join(integration_details[:3]) or 'none'}

3. COMPLIANCE: {len(compliance)} frameworks detected: {', '.join(compliance) or 'none'}
   - If EMPTY: state "No specific regulatory framework applies; standard AWS security best practices followed"
   - If NON-EMPTY: reference each framework explicitly; add audit/logging requirements

4. COMPLEXITY={complexity}
   - Bullet count per section: {requirements.get('_bullet_count', 3)}
   - Persona paragraphs (max): {requirements.get('_max_personas', 3)}
   - Use complexity-appropriate technical depth

5. DEPLOYMENT={requirements.get('deployment_environment', 'serverless')}
   - serverless: Lambda + API Gateway; no VPC section needed; implicit multi-AZ
   - containerized: ECS/EKS; include VPC with private subnets
   - ec2_based: ASG; include VPC, subnets, NAT Gateway
   - hybrid: describe coexistence of serverless and container layers

6. AWS SERVICES: Use ONLY services listed in the AWS Services section above.
   DO NOT invent or add services not in that list.

===============================================================
EXTRACTED DOCUMENT CONTENT (POC_TO_PROD MODE)
==============================================================="""

        # Add extracted document content for POC_TO_PROD mode
        if requirements.get('_rag') and requirements['_rag'].get('extracted_content'):
            prompt += f"""
The following content was extracted from the uploaded POC document.
Use this as the primary context for understanding the existing project:

{requirements['_rag']['extracted_content']}

IMPORTANT: Base your content generation on the above extracted document content.
This represents the existing POC that needs to be converted to production.
"""
        else:
            prompt += """
No extracted document content available for this generation.
"""

        prompt += """
===============================================================
TASK: Generate content for the following sections.
Return a valid JSON object where keys are EXACT section names
and values are the markdown content body (NO section heading — heading is added by template).
===============================================================
"""

        for section in sections:
            prompt += f"\n--- SECTION: {section.name} ---\n"
            prompt += f"INSTRUCTIONS:\n{section.content}\n"

        prompt += """
===============================================================
CRITICAL OUTPUT RULES
===============================================================
1. Return ONLY valid JSON — no markdown wrappers, no code blocks, no preamble
2. Keys MUST match section names exactly (case-sensitive)
3. Values are markdown content bodies — do NOT include the ## section heading
4. Follow every conditional rule above (ui_required, integrations, compliance, complexity)
5. Use ONLY AWS services from the provided list — never invent services
6. Replace {COMPANY_NAME} with the actual company name from document context
7. FORMATTING RULES:
   - Keep all bullet points concise (maximum 2 lines each)
   - Avoid overly detailed sub-bullets or nested lists
   - Use clear, actionable language without excessive technical jargon
   - Break long sentences into multiple bullet points instead of creating long single bullets
8. Use industry-specific terminology from the industry context block
9. Numbers must come from objective_analysis — never invent metrics
10. No marketing language: avoid "robust", "seamless", "cutting-edge", "world-class"
11. Use \\n for newlines within JSON string values — no raw control characters
12. Double line break (\\n\\n) before every subsection heading (###)
13. Bullets use • symbol unless template specifies ●
14. Follow the exact bullet counts specified in the conditional rules
15. For Out of Scope: apply every conditional rule — wrong items invalidate the SOW
    CRITICAL: Never include items that contradict the project scope. For example:
    - If ui_required=true, do NOT put "web UI development" out of scope
    - If compliance_requirements contains specific frameworks, do NOT put those frameworks out of scope
    - If key_features contains analytics, do NOT put "analytics" generally out of scope
7. Use industry-specific terminology from the industry context block
8. Numbers must come from objective_analysis — never invent metrics
9. No marketing language: avoid "robust", "seamless", "cutting-edge", "world-class"
10. Use \\n for newlines within JSON string values — no raw control characters
11. Double line break (\\n\\n) before every subsection heading (###)
12. Bullets use • symbol unless template specifies ●
13. Follow the exact bullet counts specified in the conditional rules
14. For Out of Scope: apply every conditional rule — wrong items invalidate the SOW
    CRITICAL: Never include items that contradict the project scope. For example:
    - If ui_required=true, do NOT put "web UI development" out of scope
    - If compliance_requirements contains specific frameworks, do NOT put those frameworks out of scope
    - If key_features contains analytics, do NOT put "analytics" generally out of scope

MANDATORY: USE USER-PROVIDED DATA FROM OBJECTIVE ANALYSIS
- Timeline: If "Duration (weeks)" is specified, use that EXACT value instead of complexity-based ranges
- Data Volume: Use "Data Volume (GB)" and "Data Volume Desc" EXACTLY as provided
- Invoice/Document Volume: Include "Invoice Volume", "Document Volume", "SKU Count" in relevant sections
- UI Requirements: Strictly follow ui_required flag - if true, include web UI; if false, exclude ALL UI
- All metrics, numbers, and specifications must come from the objective analysis data above

🚨🚨🚨 TIMELINE ENFORCEMENT 🚨🚨🚨
For "Timelines and Deliverables" section specifically:
- Check Duration (weeks): {requirements.get('duration_weeks', 'Not specified')}
- Check Timeline: {requirements.get('timeline', 'Not specified')}
- If EITHER shows a number, use that EXACT number as total project duration
- Do NOT use complexity ranges if user provided specific timeline
- EXAMPLE: Duration (weeks) = 8 means project is exactly 8 weeks, not 6-8 or any range

🚨 PROFESSIONAL TIMELINE FORMATTING REQUIRED 🚨
- Use "Week X" for single weeks (e.g., "Week 1", "Week 5")
- Use "Week X-Y" for multi-week phases (e.g., "Week 1-2", "Week 3-5")
- Start from Week 1 and number sequentially to project end
- NO OLD FORMAT: Do NOT use "3 weeks" or "2 weeks for this"
- EXAMPLE for 8-week project: "Week 1-2", "Week 3-4", "Week 5-6", "Week 7-8"

CRITICAL: The LLM must prioritize user-extracted data over template defaults. When user provides specific values (timeline, data volume, etc.), those take absolute precedence over any complexity-based calculations or default ranges.

RESPOND WITH ONLY THE JSON OBJECT — START WITH { AND END WITH }
"""
        return prompt
    
    def _build_individual_prompt(
        self,
        section: TemplateSection,
        requirements: Dict[str, Any],
        metadata: Dict[str, Any],
        supporting_context: Optional[str] = None
    ) -> str:
        """Build a prompt for generating a single section"""

        # Use the same context as the batch prompt but focus on one section
        ui_required = requirements.get('ui_required', False)
        complexity = requirements.get('_complexity', 'moderate')
        aws_services = requirements.get('aws_services', [])

        supporting_section = ""
        if supporting_context:
            supporting_section = f"""

===============================================================
SUPPORTING DOCUMENTS CONTEXT
===============================================================
{supporting_context}
===============================================================
"""

        prompt = f"""You are an expert technical writer generating a single section for a {'Production' if self.template_type == 'PROD' else 'POC'} Statement of Work (SOW).

🚨 CRITICAL INSTRUCTION: Use the exact data from the objective analysis below. Do not make assumptions or use defaults.
{supporting_section}
===============================================================
DOCUMENT CONTEXT
===============================================================
Company:       {metadata.get('company_name', '')}
Project:       {metadata.get('project_title', '')}
Template Type: {self.template_type}

===============================================================
OBJECTIVE ANALYSIS DATA
===============================================================
Industry:            {requirements.get('industry', 'generic')}
Complexity Level:    {complexity}
UI Required:         {ui_required}
Data Volume (GB):    {requirements.get('data_volume_gb', 5)}
Timeline:            {requirements.get('timeline', 'Not specified')}
Duration (weeks):    {requirements.get('duration_weeks', 'Not specified')}
AWS Services:        {', '.join(aws_services)}

===============================================================
EXTRACTED DOCUMENT CONTENT (POC_TO_PROD MODE)
==============================================================="""

        # Add extracted document content for POC_TO_PROD mode
        if requirements.get('_rag') and requirements['_rag'].get('extracted_content'):
            prompt += f"""
The following content was extracted from the uploaded POC document.
Use this as the primary context for understanding the existing project:

{requirements['_rag']['extracted_content']}

IMPORTANT: Base your content generation on the above extracted document content.
This represents the existing POC that needs to be converted to production.
"""
        else:
            prompt += """
No extracted document content available for this generation.
"""

        prompt += f"""
===============================================================
SECTION TO GENERATE: {section.name}
===============================================================
INSTRUCTIONS:
{section.content}

===============================================================
OUTPUT REQUIREMENTS
===============================================================
Return ONLY a JSON object with the section name as key and content as value:
{{"{section.name}": "markdown content here"}}

Use the exact section name "{section.name}" as the JSON key.
Content should be markdown without the section heading (## will be added automatically).

FORMATTING RULES:
- Keep all bullet points concise (maximum 2 lines each)
- Avoid overly detailed sub-bullets or nested lists
- Use clear, actionable language without excessive technical jargon
- Break long sentences into multiple bullet points instead of creating long single bullets
"""
        return prompt
    
    def _clean_json_control_chars(self, json_str: str) -> str:
        """Clean control characters from JSON string to prevent parsing errors"""
        import re
        
        # Replace problematic control characters with escaped versions
        # but preserve intentional newlines in content
        cleaned = json_str
        
        # Fix unescaped newlines within JSON string values
        # This regex finds content between quotes and escapes newlines
        def escape_newlines_in_strings(match):
            content = match.group(1)
            # Escape unescaped newlines and tabs
            content = content.replace('\n', '\\n').replace('\t', '\\t').replace('\r', '\\r')
            return f'"{content}"'
        
        # Apply to quoted strings
        cleaned = re.sub(r'"([^"]*)"', escape_newlines_in_strings, cleaned)
        
        return cleaned

    def _is_complex_section(self, section_name: str) -> bool:
        """Check if this is a section known to be complex and prone to truncation"""
        complex_sections = [
            "Technical Specifications & System Design",
            "Architecture & Integrations", 
            "Scope of Work",
            "Day-2 Operations & Support"
        ]
        return section_name in complex_sections
    
    def _is_content_truncated(self, content: str) -> bool:
        """Check if content appears to be truncated"""
        if not content:
            return False
        
        truncation_indicators = [
            "[Content truncated for length",
            "continuing in next part",
            "[truncated]",
            "... [content continues]",
            "Content truncated",
            "[Content continues",
            "... (content truncated)"
        ]
        
        content_lower = content.lower()
        return any(indicator.lower() in content_lower for indicator in truncation_indicators)
    
    def _retry_with_focused_prompt(self, section: TemplateSection, requirements: Dict[str, Any], metadata: Dict[str, Any]) -> Optional[str]:
        """Retry generation with a more focused, shorter prompt to avoid truncation"""
        try:
            # Build a much more concise prompt for complex sections
            if self._is_complex_section(section.name):
                focused_prompt = f"""Generate CONCISE content for "{section.name}" section.

Company: {metadata.get('company_name', '')}
Project: {metadata.get('project_title', '')}
UI Required: {requirements.get('ui_required', False)}
AWS Services: {', '.join(requirements.get('aws_services', [])[:5])}  # Limit to first 5

CRITICAL: Keep content brief and focused. Maximum 6 subsections, 2-3 sentences each.

Return JSON: {{"{section.name}": "brief markdown content"}}"""
            else:
                # Use the original focused prompt for other sections
                focused_prompt = f"""Generate content for the "{section.name}" section of a {'Production' if self.template_type == 'PROD' else 'POC'} Statement of Work.

Company: {metadata.get('company_name', '')}
Project: {metadata.get('project_title', '')}
Industry: {requirements.get('industry', 'generic')}
Complexity: {requirements.get('_complexity', 'moderate')}

Section Instructions (summarized):
{section.content[:500]}...

Requirements:
- Return ONLY a JSON object: {{"{section.name}": "content"}}
- Content should be comprehensive but concise
- Use markdown format without section heading
- Focus on essential information only
- Maximum 2000 words

JSON Response:"""

            result = self._call_bedrock(focused_prompt, max_tokens=60000)
            json_str = self._extract_json(result)
            
            if json_str:
                cleaned_json = self._clean_json_control_chars(json_str)
                section_data = json.loads(cleaned_json)
                
                if isinstance(section_data, dict) and section.name in section_data:
                    content = section_data[section.name]
                    # Check if still truncated
                    if not self._is_content_truncated(content):
                        return content
                elif isinstance(section_data, str) and not self._is_content_truncated(section_data):
                    return section_data
            
            return None
            
        except Exception as e:
            print(f"      ❌ Focused retry failed: {e}")
            return None

    def _get_industry_guidance(self, industry: str) -> str:
        """Return industry-specific terminology and focus areas for the prompt."""
        guidance = {
            "financial_services": (
                "Use terminology: regulatory compliance, risk management, audit trail, "
                "KYC, AML, transaction processing, data lineage. "
                "Reference: GDPR, PCI-DSS, SOX where compliance_requirements is non-empty. "
                "Focus on: data security, real-time processing, audit readiness."
            ),
            "healthcare": (
                "Use terminology: clinical workflow, patient data, EHR integration, "
                "diagnostic accuracy, care pathway, clinical validation. "
                "Reference: HIPAA, HL7, FHIR where compliance_requirements is non-empty. "
                "Focus on: PHI protection, clinical accuracy, interoperability."
            ),
            "retail_ecommerce": (
                "Use terminology: customer journey, personalisation, product catalogue, "
                "conversion rate, basket analysis, real-time recommendation. "
                "Focus on: customer experience, revenue impact, scalability for peak traffic."
            ),
            "manufacturing": (
                "Use terminology: IoT telemetry, predictive maintenance, OEE, "
                "quality control, production line, sensor data, asset uptime. "
                "Focus on: operational efficiency, equipment reliability, real-time monitoring."
            ),
            "technology": (
                "Use terminology: microservices, API gateway, event-driven, CI/CD, "
                "observability, SLO, developer experience, platform engineering. "
                "Focus on: system performance, developer productivity, scalability."
            ),
            "government": (
                "Use terminology: citizen services, public sector, data sovereignty, "
                "accessibility, GovCloud, FedRAMP. "
                "Focus on: compliance, security clearance, audit trails, accessibility standards."
            ),
            "education": (
                "Use terminology: learner engagement, course content, LMS integration, "
                "assessment, adaptive learning, academic performance. "
                "Focus on: student outcomes, content quality, platform accessibility."
            ),
            "media_entertainment": (
                "Use terminology: content pipeline, media asset, metadata enrichment, "
                "transcoding, rights management, content discovery, audience engagement. "
                "Focus on: content processing speed, metadata accuracy, scalability."
            ),
            "generic": (
                "Use professional, domain-neutral terminology. "
                "Focus on: business value, operational efficiency, measurable outcomes."
            ),
        }
        return guidance.get(industry, guidance["generic"])

    # ------------------------------------------------------------------
    # LLM calls
    # ------------------------------------------------------------------

    def _call_bedrock_batch(
        self,
        prompt: str,
        sections: List[TemplateSection]
    ) -> Dict[str, str]:
        try:
            response = self.bedrock.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 60000,  # Within model limit
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            body = json.loads(response['body'].read())
            
            # Track token usage
            from app.core.nodes import _track_tokens
            _track_tokens(body, "POC Content Generation (Batch)")
            
            raw = body['content'][0]['text'].strip()
            print(f"  Raw response: {len(raw):,} characters")

            json_str = self._extract_json(raw)
            if not json_str:
                print("❌ No JSON found in batch response")
                return {}

            try:
                data = json.loads(json_str)
                if not isinstance(data, dict):
                    print("❌ Parsed JSON is not a dict")
                    return {}
                print(f"✓ Batch generation: {len(data)} sections")
                return data
            except json.JSONDecodeError as e:
                print(f"⚠  JSON parse error at pos {e.pos} — attempting repair")
                fixed = self._fix_json(json_str)
                if fixed:
                    try:
                        data = json.loads(fixed)
                        print("✓ JSON repaired successfully")
                        return data
                    except Exception:
                        pass
                print("❌ JSON repair failed")
                return {}

        except Exception as e:
            print(f"❌ Batch generation error: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def _call_bedrock(self, prompt: str, max_tokens: int = 60000) -> str:
        try:
            response = self.bedrock.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "temperature": 0.2,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            body = json.loads(response['body'].read())
            
            # Track token usage
            from app.core.nodes import _track_tokens
            _track_tokens(body, "POC Content Generation")
            
            return body['content'][0]['text'].strip()
        except Exception as e:
            print(f"❌ Bedrock call error: {e}")
            return ""

    # ------------------------------------------------------------------
    # JSON utilities
    # ------------------------------------------------------------------

    def _extract_json(self, text: str) -> Optional[str]:
        # Strategy 1: ```json block
        m = re.search(r'```json\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            return m.group(1)
        # Strategy 2: any ``` block
        m = re.search(r'```\s*(\{.*?\})\s*```', text, re.DOTALL)
        if m:
            return m.group(1)
        # Strategy 3: balanced braces
        start = text.find('{')
        if start >= 0:
            result = self._balanced_extract(text[start:])
            if result:
                return result
        # Strategy 4: first { to last }
        end = text.rfind('}') + 1
        if start >= 0 and end > start:
            return text[start:end]
        return None

    def _balanced_extract(self, text: str) -> Optional[str]:
        if not text or text[0] != '{':
            return None
        depth = 0
        in_str = False
        escaped = False
        for i, ch in enumerate(text):
            if escaped:
                escaped = False
                continue
            if ch == '\\':
                escaped = True
                continue
            if ch == '"':
                in_str = not in_str
            elif ch == '{' and not in_str:
                depth += 1
            elif ch == '}' and not in_str:
                depth -= 1
                if depth == 0:
                    return text[:i + 1]
        return None

    def _fix_json(self, json_str: str) -> str:
        cleaned = []
        in_str = False
        escaped = False
        for ch in json_str:
            if escaped:
                cleaned.append(ch)
                escaped = False
                continue
            if ch == '\\':
                escaped = True
                cleaned.append(ch)
                continue
            if ch == '"':
                in_str = not in_str
                cleaned.append(ch)
            elif in_str and ord(ch) < 32:
                if ch == '\n':
                    cleaned.append('\\n')
                elif ch == '\r':
                    cleaned.append('\\r')
                elif ch == '\t':
                    cleaned.append('\\t')
                # skip other control chars
            else:
                cleaned.append(ch)
        result = ''.join(cleaned)
        # Remove trailing commas before closing brackets
        result = re.sub(r',(\s*[}\]])', r'\1', result)
        return result

    # ------------------------------------------------------------------
    # RAG integration
    # ------------------------------------------------------------------

    def _merge_rag(self, requirements: Dict[str, Any], rag_data: Dict[str, Any]) -> Dict[str, Any]:
        enriched = requirements.copy()
        enriched['_rag'] = {
            'use_cases': rag_data.get('unique_use_cases', []),
            'technical_components': rag_data.get('unique_technical_components', []),
            'data_sources': rag_data.get('unique_data_sources', []),
            'integrations': rag_data.get('unique_integrations', []),
            'success_criteria': rag_data.get('unique_success_criteria', []),
            'challenges_addressed': rag_data.get('unique_challenges_addressed', []),
            'aws_services': rag_data.get('unique_aws_service_usage', []),
            'extracted_content': rag_data.get('extracted_content', '')  # Add extracted content
        }
        return enriched

    # ------------------------------------------------------------------
    # Content helpers
    # ------------------------------------------------------------------

    def _needs_generation(self, content: str) -> bool:
        markers = ['guidelines:', 'instructions:', 'using ', 'derive ', 'only if ',
                   'conditional', 'generate', 'write exactly', '[', 'TODO', 'TBD']
        cl = content.lower()
        return any(m in cl for m in markers)

    def _clean_content(self, content: str, section_name: str) -> str:
        """Remove duplicate section headings, fix spacing, and clean markdown artifacts."""
        if not content:
            return content
            
        lines = content.split('\n')
        cleaned = []
        
        for line in lines:
            stripped = line.strip()
            
            # Strip duplicate ## headings matching the section name
            if stripped.startswith('## '):
                heading = stripped[3:].strip()
                if heading.lower() == section_name.lower():
                    continue
            
            # Clean markdown artifacts from the line
            cleaned_line = self._clean_markdown_artifacts(line)
            cleaned.append(cleaned_line)
            
        return self._ensure_spacing('\n'.join(cleaned))
    
    def _clean_markdown_artifacts(self, text: str) -> str:
        """Clean common markdown artifacts that appear in generated content."""
        import re
        
        # Remove various markdown artifacts
        text = re.sub(r'\*{3,}', '', text)  # Remove 3+ asterisks
        text = re.sub(r'_{3,}', '', text)   # Remove 3+ underscores
        text = re.sub(r'-{3,}', '', text)   # Remove 3+ dashes
        text = re.sub(r'#{3,}', '', text)   # Remove 3+ hashes
        
        # Handle proper bold formatting **text** -> keep as **text** for document builder
        # Don't convert here, let document builder handle it
        
        # Clean up any remaining isolated asterisks or markdown symbols (but preserve intentional formatting)
        text = re.sub(r'(?<!\w)\*{3,}(?!\w)', '', text)  # Remove 3+ isolated asterisks
        text = re.sub(r'(?<!\w)_{3,}(?!\w)', '', text)   # Remove 3+ isolated underscores
        
        # Remove single trailing asterisks from headings and bullet points
        text = re.sub(r'(\w)\*\s*$', r'\1', text)  # Remove trailing asterisk at end of line
        text = re.sub(r'(\w)\*(\s)', r'\1\2', text)  # Remove asterisk followed by space
        
        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text

    def _ensure_spacing(self, content: str) -> str:
        """Ensure blank lines before ### subheadings."""
        lines = content.split('\n')
        result = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith('###') and i > 0 and result and result[-1].strip():
                result.append('')
            result.append(line)
        return '\n'.join(result)

    def _replace_placeholders(self, content: str, metadata: Dict[str, Any]) -> str:
        author_org = metadata.get('author_org', '')
        company_name = metadata.get('company_name', '')
        replacements = {
            'AUTHOR_ORG': author_org,
            'AUTHOR_ORG_SHORT': metadata.get('author_org_short') or self._short_name(author_org),
            'COMPANY_NAME': company_name,
            'COMPANY_NAME_SHORT': metadata.get('company_name_short') or self._short_name(company_name),
            'PROJECT_TITLE': metadata.get('project_title', ''),
            'PROJECT_SUBTITLE': metadata.get('project_subtitle', ''),
            'AUTHOR_NAME': metadata.get('author_name', ''),
            'DOCUMENT_DATE': metadata.get('document_date', ''),
            'VERSION': metadata.get('version', '1.0'),
            'START_DATE': metadata.get('start_date', 'TBD'),
            'END_DATE': metadata.get('end_date', 'TBD'),
            'AUTHOR_ORG_DESCRIPTION': metadata.get('author_org_description', ''),
            'COMPANY_DESCRIPTION': metadata.get('company_description', ''),
        }
        
        # Handle conditional data volume display
        data_volume_desc = metadata.get('data_volume_description', '')
        data_volume_gb = metadata.get('data_volume_gb', 5)
        
        if data_volume_desc:
            # Use original description format (e.g., "10,000–25,000 documents per month")
            content = content.replace('{data_volume_description if available, else "Approximately {data_volume_gb} GB total for project implementation"}', data_volume_desc)
            content = content.replace('{data_volume_description if available, else "{data_volume_gb} GB"}', data_volume_desc)
        else:
            # Fallback to GB format
            content = content.replace('{data_volume_description if available, else "Approximately {data_volume_gb} GB total for project implementation"}', f"Approximately {data_volume_gb} GB total for project implementation")
            content = content.replace('{data_volume_description if available, else "{data_volume_gb} GB"}', f"{data_volume_gb} GB")
        
        for placeholder, value in replacements.items():
            content = content.replace('{' + placeholder + '}', str(value))
        return content

    def _section_key(self, name: str, metadata: Dict[str, Any]) -> str:
        if '{PROJECT_TITLE}' in name:
            return 'cover_page'
        resolved = self._replace_placeholders(name, metadata)
        lower = resolved.lower()
        if 'table' in lower and 'content' in lower:
            return 'toc_structure'
        
        # Handle special cases for common section names
        key_mappings = {
            'architecture & integrations': 'architecture_integrations',
            'customer dependencies & responsibilities': 'customer_dependencies_responsibilities',
            'out of scope': 'out_of_scope',
            'timelines and deliverables': 'timelines_and_deliverables',
            'aws pricing': 'aws_pricing',
            'shellkode implementation cost': 'shellkode_implementation_cost',
            'success criteria': 'success_criteria',
            'day-2 operations & support': 'day_2_operations_support',
            'project overview & objectives': 'project_overview_objectives'
        }
        
        if lower in key_mappings:
            return key_mappings[lower]
        
        # Default key generation
        key = re.sub(r'[^\w\s-]', '', lower)
        key = re.sub(r'[-\s]+', '_', key)
        short = (metadata.get('author_org_short', '') or '').lower()
        if short and key.startswith(short + '_'):
            key = key[len(short) + 1:]
        return key

    def _short_name(self, full_name: str) -> str:
        suffixes = [' Pvt Ltd', ' Private Limited', ' Pvt. Ltd.', ' Pvt.Ltd.',
                    ' Ltd', ' LLC', ' Inc', ' Corporation', ' Corp', ' Limited',
                    ' Co', ' Company']
        name = full_name
        for suffix in suffixes:
            if name.lower().endswith(suffix.lower()):
                name = name[:len(name) - len(suffix)].strip()
                break
        return name

    # ------------------------------------------------------------------
    # Formatting utilities
    # ------------------------------------------------------------------

    def _fmt_list(self, items: List[str]) -> str:
        if not items:
            return "  (none)"
        return '\n'.join(f"  • {item}" for item in items)

    def _fmt_ordered_list(self, items: List[str]) -> str:
        if not items:
            return "  (none)"
        return '\n'.join(f"  {i+1}. {item}" for i, item in enumerate(items))