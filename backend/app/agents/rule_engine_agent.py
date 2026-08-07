"""
Rule Engine Agent - Validates requirements against POC hygiene rules
"""
import json
import boto3
from typing import Dict, Any


class RuleEngineAgent:
    """Agent for validating requirements against POC best practices"""
    
    def __init__(self, config):
        self.config = config
        self.bedrock = boto3.client(
            service_name='bedrock-runtime',
            region_name=config.AWS_REGION,
            config=config.BOTO_CONFIG

        )
        self.rules = self._load_rules()
    
    def _load_rules(self) -> Dict[str, Any]:
        """Load POC rules from JSON file"""
        rules_file = self.config.POC_RULES_FILE
        if rules_file.exists():
            with open(rules_file, 'r') as f:
                rules = json.load(f)
                print(f"✓ Loaded {len(rules)} rule categories from {rules_file.name}")
                return rules
        print(f"⚠ Warning: Rules file not found at {rules_file}")
        return {}
    
    def validate_requirements(self, requirements: Dict[str, Any], objective: str) -> Dict[str, Any]:
        """
        Validate and enhance requirements against POC rules
        
        Args:
            requirements: Analyzed requirements from ObjectiveAgent
            objective: Original project objective
            
        Returns:
            Enhanced and validated requirements
        """
        if not self.rules:
            print("⚠ No rules loaded, returning original requirements")
            return requirements
        
        # Preserve user-specified data that should not be overridden
        user_specified_fields = {
            'duration_weeks': requirements.get('duration_weeks'),
            'timeline': requirements.get('timeline'),
            'aws_services': requirements.get('aws_services'),
            'document_volume': requirements.get('document_volume'),
            'data_volume': requirements.get('data_volume'),
            'ui_required': requirements.get('ui_required'),
            'extracted_data_summary': requirements.get('extracted_data_summary'),
            'user_data_extracted': requirements.get('user_data_extracted')
        }
        
        rules_text = self._format_rules_as_text()
        
        prompt = f"""You are an AWS POC specialist. Validate and enhance requirements according to POC hygiene rules.

🚨 CRITICAL: The requirements below contain USER-PROVIDED DATA that was extracted from their specific objective. You MUST preserve these exact values and NOT override them with your own analysis:

USER-PROVIDED DATA TO PRESERVE:
- Duration/Timeline: {user_specified_fields['duration_weeks']} weeks / {user_specified_fields['timeline']}
- AWS Services: {user_specified_fields['aws_services']}
- Document Volume: {user_specified_fields['document_volume']}
- Data Volume: {user_specified_fields['data_volume']}
- UI Required: {user_specified_fields['ui_required']}

POC HYGIENE RULES (MANDATORY):
{rules_text}

PROJECT OBJECTIVE:
{objective}

CURRENT REQUIREMENTS:
{json.dumps(requirements, indent=2)}

YOUR TASK:
Review requirements against EVERY rule category. For each rule:
1. Check if the requirement addresses it
2. If missing, add specific details
3. Make vague statements specific and measurable
4. Ensure AWS service choices are justified per rules
5. Add architecture considerations per rules
6. Define testing approach per rules
7. Clarify scope per rules

MANDATORY ADDITIONS (only add if missing):
- assumptions: Specific, measurable assumptions (8-12 items with numbers)
- out_of_scope: Items explicitly out of scope (8-10 items)
- testing_approach: Manual/automated testing details
- architecture_notes: AWS service justifications
- dependencies: Technical and data dependencies
- success_metrics: Quantified success criteria with percentages

🚨 CRITICAL PRESERVATION RULES:
1. DO NOT change duration_weeks, timeline, aws_services, document_volume, data_volume, or ui_required
2. DO NOT override user-specified values with your own analysis
3. ONLY enhance missing fields, do not replace existing user data
4. Keep all user-provided metrics and specifications exactly as provided

Return enhanced requirements as JSON with ALL these sections filled, but preserving user-specified data.
Respond with ONLY valid JSON, no markdown:"""

        response = self.bedrock.invoke_model(
            modelId=self.config.MODEL_ID,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "temperature": 0.2,
                "messages": [{"role": "user", "content": prompt}]
            })
        )
        
        response_body = json.loads(response['body'].read())
        
        # Track token usage
        from app.core.nodes import _track_tokens
        _track_tokens(response_body, "Requirements Validation")
        
        content = response_body['content'][0]['text'].strip()
        
        content = self._clean_json_response(content)
        
        try:
            validated = json.loads(content)
            
            # Force preservation of user-specified fields even if LLM ignored instructions
            for field, value in user_specified_fields.items():
                if value is not None:
                    validated[field] = value
                    print(f"   🔒 Force-preserved user field: {field} = {value}")
            
            print(f"✓ Requirements validated against {len(self.rules)} rule categories")
            print(f"✓ User-specified data preserved and protected")
            return validated
        except json.JSONDecodeError as e:
            print(f"⚠ Warning: Could not parse validation response: {e}")
            return requirements
    
    def _format_rules_as_text(self) -> str:
        """Format rules dictionary as readable text"""
        rules_text = []
        
        for category, details in self.rules.items():
            rules_text.append(f"\n{'='*60}")
            rules_text.append(f"CATEGORY: {category.upper().replace('_', ' ')}")
            rules_text.append(f"{'='*60}")
            
            if isinstance(details, dict):
                if 'description' in details:
                    rules_text.append(f"Description: {details['description']}")
                if 'rules' in details:
                    rules_text.append("\nRules:")
                    for rule in details['rules']:
                        rules_text.append(f"  • {rule}")
                if 'good_example' in details:
                    rules_text.append(f"\nGood Example: {details['good_example']}")
                if 'bad_example' in details:
                    rules_text.append(f"Bad Example: {details['bad_example']}")
        
        return "\n".join(rules_text)
    
    def _clean_json_response(self, content: str) -> str:
        """Clean JSON response from LLM"""
        content = content.strip()
        
        if '```json' in content:
            content = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            content = content.split('```')[1].split('```')[0].strip()
        
        return content