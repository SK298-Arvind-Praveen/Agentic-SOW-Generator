"""
Smart Content Editor - Analyzes user input and updates specific sections
Uses LLM to identify which sections need changes
"""
import json
import sys
import boto3
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.core.config import Config

class SmartContentEditor:
    """Enhanced content editor with section selection and dependency management"""
    
    def __init__(self):
        self.config = Config()
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=self.config.AWS_REGION,
            config=self.config.BOTO_CONFIG
        )
        
        # Define section dependencies - when one section changes, these might need updates too
        self.section_dependencies = {
            'budget': ['timeline', 'resources', 'deliverables'],
            'timeline': ['budget', 'resources', 'milestones'],
            'resources': ['budget', 'timeline', 'team_structure'],
            'scope': ['deliverables', 'timeline', 'budget'],
            'deliverables': ['timeline', 'budget', 'scope'],
            'team_structure': ['resources', 'budget'],
            'risk_assessment': ['timeline', 'budget', 'mitigation_strategies'],
            'technical_requirements': ['deliverables', 'timeline', 'resources']
        }
    
    def get_editable_sections(self, poc_content: Dict[str, Any], mode: str) -> List[Dict[str, Any]]:
        """
        Get list of editable sections with user-friendly names and descriptions
        Returns ALL sections from content, with mode-specific mappings
        
        Args:
            poc_content: Current document content
            mode: Document mode (POC, PROD, etc.)
            
        Returns:
            List of section info dictionaries
        """
        # Define user-friendly section mappings for both POC and PROD modes
        section_mappings = {
            # Common sections (both POC and PROD)
            'project_overview': {
                'name': 'Project Overview', 
                'description': 'Project description and objectives',
                'category': 'overview'
            },
            'scope_of_work': {
                'name': 'Scope of Work',
                'description': 'Project deliverables and tasks',
                'category': 'scope'
            },
            'out_of_scope': {
                'name': 'Out of Scope',
                'description': 'What is excluded from the project',
                'category': 'scope'
            },
            'timelines_and_deliverables': {
                'name': 'Timelines and Deliverables',
                'description': 'Project schedule and milestones',
                'category': 'timeline'
            },
            'implementation_cost': {
                'name': 'Implementation Cost',
                'description': 'Resource allocation and pricing',
                'category': 'financial'
            },
            'aws_pricing': {
                'name': 'AWS Pricing',
                'description': 'AWS service costs and estimates',
                'category': 'financial'
            },
            'assumptions': {
                'name': 'Assumptions',
                'description': 'Project assumptions and constraints',
                'category': 'requirements'
            },
            'customer_dependencies': {
                'name': 'Customer Dependencies',
                'description': 'Requirements from customer side',
                'category': 'requirements'
            },
            'customer_responsibilities': {
                'name': 'Customer Responsibilities',
                'description': 'What customer needs to provide',
                'category': 'requirements'
            },
            'success_criteria': {
                'name': 'Success Criteria',
                'description': 'How success will be measured',
                'category': 'requirements'
            },
            'about_shellkode': {
                'name': 'About Shellkode',
                'description': 'Company information',
                'category': 'overview'
            },
            'deliverable_acceptance': {
                'name': 'Deliverable Acceptance',
                'description': 'Acceptance criteria and process',
                'category': 'requirements'
            },
            'change_order': {
                'name': 'Change Order',
                'description': 'Process for handling scope changes',
                'category': 'requirements'
            },
            'change_management': {
                'name': 'Change Management',
                'description': 'Process for handling scope changes',
                'category': 'requirements'
            },
            'terms_conditions': {
                'name': 'Terms & Conditions',
                'description': 'Legal terms and conditions',
                'category': 'legal'
            },
            'contacts_and_reporting': {
                'name': 'Contacts and Reporting',
                'description': 'Project contacts and communication',
                'category': 'administrative'
            },
            'duration_of_work': {
                'name': 'Duration of Work',
                'description': 'Project timeline and duration',
                'category': 'timeline'
            },
            'marketing_authorization': {
                'name': 'Marketing Authorization',
                'description': 'Permission for marketing use',
                'category': 'legal'
            },
            'project_plan_termination': {
                'name': 'Project Plan Termination',
                'description': 'Termination conditions',
                'category': 'legal'
            },
            'acceptance_and_signatories_to_statement_of_work': {
                'name': 'Acceptance and Signatories',
                'description': 'Document acceptance and signatures',
                'category': 'legal'
            },
            
            # POC-specific sections
            'architecture_diagram': {
                'name': 'Architecture Diagram',
                'description': 'System architecture and design',
                'category': 'technical'
            },
            
            # PROD-specific sections
            'project_overview_objectives': {
                'name': 'Project Overview & Objectives',
                'description': 'Detailed project goals and business objectives',
                'category': 'overview'
            },
            'technical_specifications_system_design': {
                'name': 'Technical Specifications & System Design',
                'description': 'Detailed technical specifications and system design',
                'category': 'technical'
            },
            'architecture_integrations': {
                'name': 'Architecture & Integrations',
                'description': 'System architecture and integration points',
                'category': 'technical'
            },
            'customer_dependencies_responsibilities': {
                'name': 'Customer Dependencies & Responsibilities',
                'description': 'Customer requirements and responsibilities',
                'category': 'requirements'
            },
            'day_2_operations_support': {
                'name': 'Day-2 Operations & Support',
                'description': 'Ongoing operations and support model',
                'category': 'operational'
            },
            'design_validation': {
                'name': 'Design Validation',
                'description': 'Design validation and approval process',
                'category': 'technical'
            },
            
            # PROD scope subsections (numbered)
            '1_application_backend_implementation': {
                'name': '1. Application & Backend Implementation',
                'description': 'Core application and backend development',
                'category': 'scope'
            },
            '1_content_data_definition': {
                'name': '1. Content & Data Definition',
                'description': 'Data structure and content definitions',
                'category': 'technical'
            },
            '2_personas_usage_patterns': {
                'name': '2. Personas & Usage Patterns',
                'description': 'User personas and usage scenarios',
                'category': 'technical'
            },
            '2_user_access_interaction_layer': {
                'name': '2. User Access & Interaction Layer',
                'description': 'User interface and interaction design',
                'category': 'scope'
            },
            '3_infrastructure_scalability_operations': {
                'name': '3. Infrastructure, Scalability & Operations',
                'description': 'Infrastructure and operational setup',
                'category': 'scope'
            },
            '3_system_workflow_overview': {
                'name': '3. System Workflow Overview',
                'description': 'Overall system workflow and processes',
                'category': 'technical'
            },
            '4_data_processing_ai_capabilities': {
                'name': '4. Data Processing & AI Capabilities',
                'description': 'AI and data processing features',
                'category': 'scope'
            },
            '4_processing_characteristics': {
                'name': '4. Processing Characteristics',
                'description': 'System processing behavior and performance',
                'category': 'technical'
            },
            '5_data_lifecycle_retention': {
                'name': '5. Data Lifecycle & Retention',
                'description': 'Data management and retention policies',
                'category': 'technical'
            },
            '5_testing_go_live_production_readiness': {
                'name': '5. Testing, Go-Live & Production Readiness',
                'description': 'Testing and deployment preparation',
                'category': 'scope'
            },
            '6_access_control_human_review': {
                'name': '6. Access Control & Human Review',
                'description': 'Security and review processes',
                'category': 'technical'
            },
            '7_security_compliance_auditability': {
                'name': '7. Security, Compliance & Auditability',
                'description': 'Security and compliance requirements',
                'category': 'technical'
            },
            '8_architecture_mapping_to_aws_services': {
                'name': '8. Architecture Mapping to AWS Services',
                'description': 'AWS service architecture mapping',
                'category': 'technical'
            },
            '9_performance_scaling_availability': {
                'name': '9. Performance, Scaling & Availability',
                'description': 'Performance and scalability specifications',
                'category': 'technical'
            }
        }
        
        sections_info = []
        
        # Process ALL sections from content, not just predefined ones
        for section_key, content in poc_content.items():
            # Skip certain system/metadata sections
            skip_sections = {
                'cover_page', 'toc_structure', 'table_of_contents', 
                'critical_rules', 'duration_allocation_rules_strict',
                'output_format_do_not_change', 'phase_wise_subpoints_mandatory',
                'project_difficulty_inputs_mandatory_internal_reasoning_only'
            }
            
            if section_key in skip_sections:
                continue
            
            # Use predefined mapping if available, otherwise generate one
            if section_key in section_mappings:
                section_info = section_mappings[section_key].copy()
            else:
                # Generate user-friendly info for unmapped sections
                section_info = {
                    'name': section_key.replace('_', ' ').title(),
                    'description': f'Content for {section_key.replace("_", " ").title()}',
                    'category': self._categorize_section(section_key)
                }
            
            section_info['key'] = section_key
            section_info['has_content'] = bool(content and str(content).strip())
            
            # Handle content preview
            content_str = str(content) if content else ""
            if content_str.strip():
                section_info['content_preview'] = content_str[:150] + "..." if len(content_str) > 150 else content_str
            else:
                section_info['content_preview'] = "No content available"
            
            sections_info.append(section_info)
        
        # Sort by category and name
        sections_info.sort(key=lambda x: (x['category'], x['name']))
        
        return sections_info
    
    def _categorize_section(self, section_key: str) -> str:
        """Categorize a section based on its key"""
        key_lower = section_key.lower()
        
        if any(word in key_lower for word in ['cost', 'pricing', 'budget', 'financial']):
            return 'financial'
        elif any(word in key_lower for word in ['scope', 'work', 'deliverable', 'out_of_scope']):
            return 'scope'
        elif any(word in key_lower for word in ['timeline', 'duration', 'phase', 'schedule']):
            return 'timeline'
        elif any(word in key_lower for word in ['assumption', 'dependency', 'responsibility', 'acceptance', 'criteria']):
            return 'requirements'
        elif any(word in key_lower for word in ['architecture', 'technical', 'diagram', 'system', 'specification', 'design']):
            return 'technical'
        elif any(word in key_lower for word in ['overview', 'summary', 'about', 'objective']):
            return 'overview'
        elif any(word in key_lower for word in ['terms', 'conditions', 'legal', 'contract', 'authorization', 'signatories']):
            return 'legal'
        elif any(word in key_lower for word in ['contact', 'reporting', 'team', 'resource']):
            return 'administrative'
        elif any(word in key_lower for word in ['operations', 'support', 'day_2', 'monitoring']):
            return 'operational'
        elif any(word in key_lower for word in ['change', 'termination', 'management']):
            return 'governance'
        else:
            return 'other'
    
    def apply_section_edits(self, poc_content: Dict[str, Any], selected_sections: List[str], 
                          user_input: str, mode: str, full_replace: bool = False) -> Dict[str, Any]:
        """
        Apply edits to selected sections and auto-update dependent sections
        
        Args:
            poc_content: Current document content
            selected_sections: List of section keys user wants to edit
            user_input: User's edit instructions
            mode: Document mode
            full_replace: If True, completely replace section content (bypass instruction extraction)
            
        Returns:
            {
                'updated_content': {...},
                'edited_sections': [...],
                'auto_updated_sections': [...],
                'dependency_changes': {...}
            }
        """
        print(f"\n✏️  Applying section-based edits...")
        print(f"   Selected sections: {selected_sections}")
        print(f"   Full replace mode: {full_replace}")
        
        updated_content = json.loads(json.dumps(poc_content))  # Deep copy
        edited_sections = []
        auto_updated_sections = []
        dependency_changes = {}
        
        # Step 1: Edit user-selected sections
        for section_key in selected_sections:
            if section_key in updated_content:
                print(f"   🔄 Editing section: {section_key}")
                
                current_value = updated_content[section_key]
                
                if full_replace:
                    # For explicit full replacement, use the user input directly
                    section_instruction = user_input
                    print(f"   🔄 Using EXPLICIT FULL REPLACE mode")
                else:
                    # Generate section-specific instruction (existing behavior)
                    section_instruction = self._extract_section_instruction(user_input, section_key)
                
                # Generate new content for this section
                new_content = self._regenerate_section_content_simple(
                    section_key, current_value, section_instruction, force_full_replace=full_replace
                )
                
                # Update the section
                updated_content[section_key] = new_content
                edited_sections.append(section_key)
                
                print(f"   ✓ Section updated: {section_key}")
        
        # Step 2: Identify and update dependent sections (skip if full_replace to avoid confusion)
        if not full_replace:
            dependent_sections = self._get_dependent_sections(selected_sections)
            
            for dep_section in dependent_sections:
                if dep_section in updated_content and dep_section not in selected_sections:
                    print(f"   🔗 Auto-updating dependent section: {dep_section}")
                    
                    # Analyze if this section needs updating based on the changes
                    needs_update = self._analyze_dependency_impact(
                        dep_section, updated_content, selected_sections, user_input
                    )
                    
                    if needs_update['should_update']:
                        current_value = updated_content[dep_section]
                        dependency_instruction = needs_update['instruction']
                        
                        new_content = self._regenerate_section_content_simple(
                            dep_section, current_value, dependency_instruction
                        )
                        
                        updated_content[dep_section] = new_content
                        auto_updated_sections.append(dep_section)
                        dependency_changes[dep_section] = needs_update['reasoning']
                        
                        print(f"   ✓ Auto-updated: {dep_section}")
        else:
            print(f"   ⏭️  Skipping dependency updates in full replace mode")
        
        # Debug: Verify the updated content before returning
        print(f"\n🔍 DEBUG: Returning edit result...")
        print(f"   Edited sections: {edited_sections}")
        for section in edited_sections:
            if section in updated_content:
                content_preview = str(updated_content[section])[:100]
                print(f"   {section}: {content_preview}...")
        
        return {
            'updated_content': updated_content,
            'edited_sections': edited_sections,
            'auto_updated_sections': auto_updated_sections,
            'dependency_changes': dependency_changes
        }
    
    def _get_dependent_sections(self, changed_sections: List[str]) -> List[str]:
        """Get all sections that might be affected by changes to the given sections"""
        dependent_sections = set()
        
        for section in changed_sections:
            if section in self.section_dependencies:
                dependent_sections.update(self.section_dependencies[section])
        
        return list(dependent_sections)
    
    def _extract_section_instruction(self, user_input: str, section_key: str) -> str:
        """Extract section-specific instruction from user input"""
        section_name = section_key.replace('_', ' ').title()
        
        # Check if user input contains "replace entire" phrases for this section
        replace_phrases = [
            f'replace the entire {section_name.lower()}',
            f'replace entire {section_name.lower()}',
            f'replace the whole {section_name.lower()}',
            f'replace whole {section_name.lower()}',
            f'replace the entire {section_key}',
            f'replace entire {section_key}',
            'replace the entire out of scope',
            'replace entire out of scope',
            'replace the entire section',
            'replace entire section'
        ]
        
        user_input_lower = user_input.lower()
        has_replace_phrase = any(phrase in user_input_lower for phrase in replace_phrases)
        
        if has_replace_phrase:
            print(f"   🔍 DETECTED 'replace entire' phrase for {section_name}")
            # For replace entire, return the instruction with the trigger phrase preserved
            return user_input  # Return original to preserve trigger phrases
        
        # For non-replace instructions, use LLM extraction
        prompt = f"""Extract the specific instruction for the "{section_name}" section from this user input:

USER INPUT: {user_input}

SECTION: {section_name}

Return only the specific instruction for this section. If no specific instruction is given for this section, return a general instruction based on the overall user intent.

Keep it concise and actionable."""

        try:
            response = self.bedrock.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 200,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            
            response_body = json.loads(response['body'].read())
            instruction = response_body['content'][0]['text'].strip()
            
            return instruction
            
        except Exception as e:
            print(f"   ⚠️  Could not extract section instruction: {e}")
            return user_input  # Fallback to original input
    
    def _analyze_dependency_impact(self, dep_section: str, updated_content: Dict[str, Any], 
                                 changed_sections: List[str], user_input: str) -> Dict[str, Any]:
        """Analyze if a dependent section needs updating based on changes"""
        
        prompt = f"""Analyze if the "{dep_section}" section needs updating based on changes made to other sections.

CHANGED SECTIONS: {', '.join(changed_sections)}
USER CHANGES: {user_input}
DEPENDENT SECTION: {dep_section}

Current content of {dep_section}:
{str(updated_content.get(dep_section, 'No content'))[:500]}

Determine:
1. Should this section be updated? (yes/no)
2. If yes, what specific changes are needed?
3. Brief reasoning

Return JSON:
{{
    "should_update": true/false,
    "instruction": "specific instruction if updating",
    "reasoning": "why this section needs/doesn't need updating"
}}"""

        try:
            response = self.bedrock.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 300,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            
            response_body = json.loads(response['body'].read())
            response_text = response_body['content'][0]['text'].strip()
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            
            if json_match:
                analysis = json.loads(json_match.group())
                return analysis
            else:
                return {"should_update": False, "instruction": "", "reasoning": "Could not analyze dependency"}
                
        except Exception as e:
            print(f"   ⚠️  Dependency analysis failed: {e}")
            return {"should_update": False, "instruction": "", "reasoning": "Analysis failed"}
    
    def analyze_edit_request(self, user_input: str, poc_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze user input to determine which sections need editing
        
        Args:
            user_input: User's edit instructions
            poc_content: Current poc_content structure (original format)
            
        Returns:
            {
                "sections_to_edit": ["executive_summary", "timeline"],
                "edit_instructions": {
                    "executive_summary": "specific instruction",
                    "timeline": "specific instruction"
                },
                "reasoning": "Why these sections were selected"
            }
        """
        print(f"\n🔍 Analyzing edit request...")
        print(f"   User input: {user_input[:100]}...")
        
        # Build section summary for LLM
        section_summary = self._build_section_summary_from_poc(poc_content)
        
        prompt = f"""You are a document editor assistant. Analyze the user's edit request and identify which sections of the document need to be modified.

USER'S EDIT REQUEST:
{user_input}

CURRENT DOCUMENT SECTIONS:
{section_summary}

Your task:
1. Identify which sections need editing based on the user's request
2. For each section, extract the specific instruction
3. Explain your reasoning

IMPORTANT:
- Be VERY specific about what needs to change
- Only identify sections that are directly mentioned or clearly implied
- Do NOT suggest changes to sections that aren't related to the request
- Keep instructions focused and precise

Return ONLY a valid JSON object with this structure:
{{
    "sections_to_edit": ["section_key_1", "section_key_2"],
    "edit_instructions": {{
        "section_key_1": "specific instruction",
        "section_key_2": "specific instruction"
    }},
    "reasoning": "explanation of why these sections were selected"
}}

IMPORTANT: 
- Use the exact section keys from the document structure
- Only include sections that NEED to be changed
- Be specific about what needs to change in each section
- Return ONLY valid JSON, no markdown
"""
        
        try:
            response = self.bedrock.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            
            response_body = json.loads(response['body'].read())
            response_text = response_body['content'][0]['text'].strip()
            
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            
            if json_match:
                analysis = json.loads(json_match.group())
                print(f"   ✓ Identified {len(analysis.get('sections_to_edit', []))} sections to edit")
                return analysis
            else:
                print(f"   ⚠️  Could not parse LLM response")
                return self._fallback_analysis(user_input, poc_content)
                
        except Exception as e:
            print(f"   ❌ Analysis failed: {e}")
            return self._fallback_analysis(user_input, poc_content)
    
    def apply_edits(self, poc_content: Dict[str, Any], edit_analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply edits to specific sections
        
        Args:
            poc_content: Current poc_content structure
            edit_analysis: Analysis from analyze_edit_request
            
        Returns:
            Updated poc_content structure
        """
        print(f"\n✏️  Applying edits to {len(edit_analysis.get('sections_to_edit', []))} sections...")
        
        updated_content = json.loads(json.dumps(poc_content))  # Deep copy
        sections_to_edit = edit_analysis.get("sections_to_edit", [])
        edit_instructions = edit_analysis.get("edit_instructions", {})
        
        for section_key in sections_to_edit:
            instruction = edit_instructions.get(section_key, "")
            
            # Find the section in poc_content
            if section_key in updated_content:
                print(f"   🔄 Editing section: {section_key}")
                
                current_value = updated_content[section_key]
                
                # Generate new content for this section
                new_content = self._regenerate_section_content_simple(section_key, current_value, instruction)
                
                # Update the section
                updated_content[section_key] = new_content
                
                print(f"   ✓ Section updated")
            else:
                print(f"   ⚠️  Section not found: {section_key}")
        
        return updated_content
    
    def _build_section_summary_from_poc(self, poc_content: Dict[str, Any]) -> str:
        """Build a summary of sections from poc_content for LLM analysis"""
        summary_lines = []
        
        for key, value in poc_content.items():
            # Format the key nicely
            display_key = key.replace("_", " ").title()
            
            # Determine content type
            if isinstance(value, dict):
                summary_lines.append(f"- {key}: {display_key} (nested structure with {len(value)} items)")
            elif isinstance(value, list):
                summary_lines.append(f"- {key}: {display_key} (list with {len(value)} items)")
            else:
                preview = str(value)[:100] + "..." if len(str(value)) > 100 else str(value)
                summary_lines.append(f"- {key}: {display_key} - {preview}")
        
        return "\n".join(summary_lines)
    
    def _regenerate_section_content_simple(self, section_key: str, current_value: Any, instruction: str, force_full_replace: bool = False) -> Any:
        """Regenerate content for a specific section using LLM"""
        try:
            section_title = section_key.replace("_", " ").title()
            
            # Convert current value to string for LLM
            if isinstance(current_value, (dict, list)):
                current_content = json.dumps(current_value, indent=2)
                is_structured = True
            else:
                current_content = str(current_value)
                is_structured = False
            
            # Detect if this is a table section
            is_table_section = any(keyword in section_key.lower() for keyword in [
                'timeline', 'deliverable', 'pricing', 'cost', 'contact', 'signator'
            ]) or '|' in current_content
            
            # Determine replacement mode
            if force_full_replace:
                # Explicit full replacement requested via API
                is_full_replacement = True
                print(f"   🔄 EXPLICIT FULL REPLACE requested via API")
            else:
                # Check if this is a "replace entire section" instruction from natural language
                replace_phrases = [
                    'replace the entire', 'replace entire', 'replace all', 'completely replace',
                    'replace the whole', 'replace whole', 'new content for', 'change everything'
                ]
                has_replace_phrase = any(phrase in instruction.lower() for phrase in replace_phrases)
                
                # ✅ ENHANCED: Auto-detect if user pasted structured content (bullet points, numbered lists)
                # If the instruction looks like complete content rather than an instruction, treat as full replace
                instruction_lines = instruction.strip().split('\n')
                has_multiple_lines = len(instruction_lines) > 2
                has_bullet_points = any(line.strip().startswith(('•', '-', '*', '●', '○')) for line in instruction_lines)
                has_numbered_list = any(re.match(r'^\d+[\.)]\s', line.strip()) for line in instruction_lines)
                
                # Check if it looks like pasted content vs an instruction
                looks_like_instruction = any(word in instruction.lower()[:50] for word in [
                    'add', 'remove', 'change', 'update', 'modify', 'edit', 'delete', 
                    'insert', 'replace', 'rewrite', 'improve', 'fix', 'correct'
                ])
                
                # If it has structured content and doesn't look like an instruction, treat as full replace
                is_pasted_content = (has_bullet_points or has_numbered_list) and has_multiple_lines and not looks_like_instruction
                
                is_full_replacement = has_replace_phrase or is_pasted_content
                
                if is_pasted_content:
                    print(f"   🔍 AUTO-DETECTED pasted content (bullets/numbers, {len(instruction_lines)} lines, no instruction keywords)")
            
            print(f"   🔍 Instruction analysis:")
            print(f"      Instruction: {instruction[:100]}...")
            print(f"      Is full replacement: {is_full_replacement}")
            print(f"      Is table section: {is_table_section}")
            print(f"      Is structured data: {is_structured}")
            print(f"      Force full replace: {force_full_replace}")
            
            # ✅ NEW: For full replacement, use user text directly without LLM
            if is_full_replacement:
                print(f"   🚀 DIRECT REPLACEMENT: Using user text directly (no LLM call)")
                
                # Clean up the user input and use it directly
                direct_content = instruction.strip()
                
                # ✅ ENHANCED: Remove ALL section key markers from user input
                # Remove specific section marker for this section
                section_key_pattern = r'\[' + re.escape(section_key) + r'\]\s*'
                direct_content = re.sub(section_key_pattern, '', direct_content, flags=re.IGNORECASE)
                
                # Remove any generic section markers (at start of content or on their own line)
                direct_content = re.sub(r'^\[[\w_]+\]\s*\n?', '', direct_content, flags=re.MULTILINE)
                direct_content = re.sub(r'\n\[[\w_]+\]\s*\n?', '\n', direct_content)
                
                # Remove markers that might be at the very start
                direct_content = re.sub(r'^\s*\[[\w_]+\]\s*', '', direct_content)
                
                # ✅ CRITICAL: Preserve bullet points and line breaks
                # Do NOT apply aggressive spacing cleanup for pasted content
                # Only remove section markers, keep everything else as-is
                print(f"   ✅ Direct replacement content ({len(direct_content)} chars)")
                print(f"   📝 First 200 chars: {direct_content[:200]}...")
                
                # ✅ DIAGNOSTIC: Show exact characters to debug bullet point issues
                lines = direct_content.split('\n')[:5]  # First 5 lines
                for i, line in enumerate(lines):
                    if line.strip():
                        # Show first few characters with their Unicode codes
                        first_chars = line[:10]
                        char_codes = [f"{c}(U+{ord(c):04X})" for c in first_chars[:3]]
                        print(f"   Line {i+1}: {char_codes} -> {line[:50]}")
                
                # Count bullet points to verify they're preserved
                bullet_count = len(re.findall(r'^[•\-*●○]\s', direct_content, re.MULTILINE))
                numbered_count = len(re.findall(r'^\d+[\.)]\s', direct_content, re.MULTILINE))
                print(f"   📊 Detected: {bullet_count} bullet points, {numbered_count} numbered items")
                
                # Try to parse as JSON if original was structured
                if is_structured:
                    try:
                        parsed_content = json.loads(direct_content)
                        print(f"   ✅ Successfully parsed direct content as JSON")
                        return parsed_content
                    except json.JSONDecodeError:
                        print(f"   ℹ️  Direct content is not JSON, returning as string")
                        return direct_content
                
                return direct_content
            
            # For partial edits, use LLM to intelligently apply changes
            else:
                # For partial modifications, use LLM to apply changes intelligently
                if is_table_section:
                    prompt = f"""You are editing the "{section_title}" table section of a document.

CURRENT TABLE:
{current_content}

USER INSTRUCTION: {instruction}

CRITICAL FORMATTING RULES:
1. Apply the requested changes to the table
2. Maintain the table format with | separators
3. Keep the same structure unless specifically asked to change it
4. Use proper spacing: no extra spaces around | separators
5. Align columns properly
6. Do NOT add explanations or introductory text
7. Return ONLY the updated table content

Apply the changes now:"""
                else:
                    prompt = f"""You are editing the "{section_title}" section of a document.

CURRENT CONTENT:
{current_content}

USER INSTRUCTION: {instruction}

CRITICAL FORMATTING RULES:
1. Apply the requested changes to the content
2. Keep the same format and structure unless specifically asked to change it
3. Do NOT add explanations, headers, or introductory text
4. Use proper spacing: single space between words, no trailing spaces
5. Use single line breaks between paragraphs
6. For bullet points, use "• " (bullet + single space)
7. Return ONLY the updated content, nothing else

Apply the changes now:"""
                print(f"   📝 Using PARTIAL EDIT prompt")
            
            # Call Bedrock API for partial edits only
            print(f"   🤖 Calling Bedrock API for partial edit...")
            response = self.bedrock.invoke_model(
                modelId=self.config.MODEL_ID,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,  # Increased to prevent truncation
                    "temperature": 0.1,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            
            response_body = json.loads(response['body'].read())
            new_content = response_body['content'][0]['text'].strip()
            
            print(f"   🤖 LLM raw response ({len(new_content)} chars): {new_content[:200]}...")
            
            # ✅ ENHANCED: Remove ALL section key markers from LLM response
            # Remove specific section marker for this section
            section_key_pattern = r'\[' + re.escape(section_key) + r'\]\s*'
            new_content = re.sub(section_key_pattern, '', new_content, flags=re.IGNORECASE)
            
            # Remove any generic section markers (at start of content or on their own line)
            new_content = re.sub(r'^\[[\w_]+\]\s*\n?', '', new_content, flags=re.MULTILINE)
            new_content = re.sub(r'\n\[[\w_]+\]\s*\n?', '\n', new_content)
            
            # Remove markers that might be at the very start
            new_content = re.sub(r'^\s*\[[\w_]+\]\s*', '', new_content)
            
            print(f"   🧹 After removing section markers: {new_content[:200]}...")
            
            # Enhanced cleanup for better spacing
            if is_table_section:
                # Clean up table-specific artifacts
                lines = new_content.split('\n')
                cleaned_lines = []
                
                for line in lines:
                    line = line.strip()
                    # Skip empty lines and markdown artifacts
                    if not line or line.startswith('```'):
                        continue
                    # Skip explanatory text
                    if line.lower().startswith(('here is', 'here\'s', 'the updated', 'updated:')):
                        continue
                    cleaned_lines.append(line)
                
                new_content = '\n'.join(cleaned_lines)
                print(f"   🧹 After table cleanup: {new_content[:200]}...")
            else:
                # Enhanced cleanup for text sections with better spacing control
                if new_content.startswith('```'):
                    lines = new_content.split('\n')
                    if lines[0].startswith('```'):
                        lines = lines[1:]
                    if lines and lines[-1].startswith('```'):
                        lines = lines[:-1]
                    new_content = '\n'.join(lines).strip()
                    print(f"   🧹 After code block cleanup: {new_content[:200]}...")
                
                # Remove common prefixes but be more conservative
                unwanted_starts = ['Here is', 'Here\'s', 'The updated', 'Updated:', 'New content:']
                for prefix in unwanted_starts:
                    if new_content.startswith(prefix):
                        first_newline = new_content.find('\n')
                        if first_newline > 0:
                            new_content = new_content[first_newline + 1:].strip()
                            print(f"   🧹 After prefix removal: {new_content[:200]}...")
                        break
            
            # ✅ NEW: Enhanced spacing cleanup to remove unwanted spaces
            new_content = self._clean_spacing_issues(new_content, is_table_section)
            
            # ✅ FINAL CLEANUP: Remove any remaining section markers one more time
            new_content = self._remove_all_section_markers(new_content)
            
            print(f"   🔧 Final generated content ({len(new_content)} chars): {new_content[:100]}...")
            
            # Try to parse as JSON if original was dict/list
            if is_structured:
                try:
                    parsed_content = json.loads(new_content)
                    print(f"   ✅ Successfully parsed as JSON")
                    return parsed_content
                except json.JSONDecodeError as e:
                    print(f"   ⚠️  Could not parse as JSON: {e}")
                    print(f"   ⚠️  Returning as string instead")
                    return new_content
            
            # ✅ FINAL CHECK: Ensure no markers in string content before returning
            new_content = self._remove_all_section_markers(new_content)
            
            return new_content
            
        except Exception as e:
            print(f"   ❌ Content regeneration failed: {e}")
            import traceback
            traceback.print_exc()
            print(f"   🔄 Returning original content as fallback")
            return current_value  # Return original on failure

    def _clean_spacing_issues(self, content: str, is_table_section: bool = False) -> str:
        """
        ✅ ENHANCED: Clean up spacing issues in generated content while preserving bullet points
        """
        if not content:
            return content
        
        if is_table_section:
            # For tables, ensure proper spacing between rows
            lines = content.split('\n')
            cleaned_lines = []
            
            for line in lines:
                stripped_line = line.strip()
                if stripped_line:  # Only keep non-empty lines for tables
                    cleaned_lines.append(stripped_line)
            
            return '\n'.join(cleaned_lines)
        else:
            # For text content, normalize spacing while preserving bullet points
            lines = content.split('\n')
            cleaned_lines = []
            previous_was_empty = False
            
            for line in lines:
                stripped_line = line.strip()
                
                if not stripped_line:
                    # Empty line
                    if not previous_was_empty:  # Only allow one consecutive empty line
                        cleaned_lines.append('')
                        previous_was_empty = True
                else:
                    # Non-empty line - preserve bullet point formatting
                    # Check if line starts with bullet point or number
                    is_bullet = re.match(r'^[•\-*●○]\s', stripped_line)
                    is_numbered = re.match(r'^\d+[\.)]\s', stripped_line)
                    
                    if is_bullet or is_numbered:
                        # Preserve bullet/number formatting exactly as is
                        cleaned_lines.append(stripped_line)
                    else:
                        # Regular line - apply normal cleanup
                        cleaned_lines.append(stripped_line)
                    
                    previous_was_empty = False
            
            # Remove leading and trailing empty lines
            while cleaned_lines and not cleaned_lines[0]:
                cleaned_lines.pop(0)
            while cleaned_lines and not cleaned_lines[-1]:
                cleaned_lines.pop()
            
            # Join with proper spacing
            result = '\n'.join(cleaned_lines)
            
            # Fix common spacing issues (but preserve bullet points)
            result = self._fix_common_spacing_issues(result)
            
            return result
    
    def _fix_common_spacing_issues(self, content: str) -> str:
        """
        ✅ ENHANCED: Fix common spacing issues in text content while preserving bullet points
        """
        
        # Remove excessive spaces between words (but not at line start for indentation)
        lines = content.split('\n')
        fixed_lines = []
        
        for line in lines:
            # Check if line starts with bullet or number
            is_bullet_line = re.match(r'^([•\-*●○]\s+|\d+[\.)]\s+)', line)
            
            if is_bullet_line:
                # For bullet/numbered lines, preserve the bullet/number and clean the rest
                bullet_part = is_bullet_line.group(1)
                rest_of_line = line[len(bullet_part):]
                # Clean excessive spaces in the text part only
                rest_of_line = re.sub(r' +', ' ', rest_of_line)
                fixed_lines.append(bullet_part + rest_of_line)
            else:
                # For regular lines, clean excessive spaces
                fixed_lines.append(re.sub(r' +', ' ', line))
        
        content = '\n'.join(fixed_lines)
        
        # Fix spacing around punctuation (but not for bullet points)
        content = re.sub(r' +([,.;:!?])', r'\1', content)  # Remove space before punctuation
        content = re.sub(r'([,.;:!?])([A-Za-z])', r'\1 \2', content)  # Add space after punctuation
        
        # Normalize bullet point spacing (ensure single space after bullet)
        content = re.sub(r'•\s+', '• ', content)
        content = re.sub(r'●\s+', '● ', content)
        content = re.sub(r'○\s+', '○ ', content)
        
        # Normalize dash spacing for bullet points (but not for regular dashes)
        # Only at start of line
        content = re.sub(r'^-\s+', '- ', content, flags=re.MULTILINE)
        content = re.sub(r'^\*\s+', '* ', content, flags=re.MULTILINE)
        
        # Fix numbered list spacing
        content = re.sub(r'(\d+)\.\s+', r'\1. ', content)
        content = re.sub(r'(\d+)\)\s+', r'\1) ', content)
        
        # Remove trailing spaces from lines
        lines = content.split('\n')
        lines = [line.rstrip() for line in lines]
        content = '\n'.join(lines)
        
        return content
    
    def _remove_all_section_markers(self, content: str) -> str:
        """
        ✅ NEW: Remove all section markers like [success_criteria], [out_of_scope], etc.
        This is a comprehensive cleanup to ensure no markers appear in final content
        """
        if not content or not isinstance(content, str):
            return content
        
        # Remove markers at the start of the content
        content = re.sub(r'^\s*\[[\w_]+\]\s*\n?', '', content)
        
        # Remove markers at the start of any line
        content = re.sub(r'^\[[\w_]+\]\s*\n?', '', content, flags=re.MULTILINE)
        
        # Remove markers that appear on their own line
        content = re.sub(r'\n\s*\[[\w_]+\]\s*\n', '\n', content)
        
        # Remove markers followed by content on the same line
        content = re.sub(r'\[[\w_]+\]\s+', '', content)
        
        # Remove any remaining brackets with underscores (likely section markers)
        content = re.sub(r'\[[\w_]+\]', '', content)
        
        return content.strip()
    
    def _fallback_analysis(self, user_input: str, poc_content: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback analysis when LLM fails - use keyword matching"""
        print(f"   ℹ️  Using fallback keyword matching...")
        
        sections_to_edit = []
        edit_instructions = {}
        
        user_input_lower = user_input.lower()
        
        # Simple keyword matching
        for section_key in poc_content.keys():
            section_title = section_key.replace("_", " ").lower()
            
            # Check if section title appears in user input
            if section_title in user_input_lower or section_key.lower() in user_input_lower:
                sections_to_edit.append(section_key)
                edit_instructions[section_key] = user_input
        
        # If no matches, edit the first section
        if not sections_to_edit and poc_content:
            first_key = list(poc_content.keys())[0]
            sections_to_edit.append(first_key)
            edit_instructions[first_key] = user_input
        
        return {
            "sections_to_edit": sections_to_edit,
            "edit_instructions": edit_instructions,
            "reasoning": "Fallback keyword matching used"
        }
