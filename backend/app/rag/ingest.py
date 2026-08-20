"""
Updated DynamoDB Schema Manager with Integrated Schema Cleaner
Separate schemas and prompts for POC vs PROD/POC_TO_PROD modes
✅ NEW: Built-in schema cleaning before DynamoDB save
"""

import json
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import boto3
from botocore.exceptions import ClientError
import PyPDF2
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage
import re

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")

AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')
BEDROCK_REGION = os.getenv('BEDROCK_REGION', 'us-east-1')

# Initialize AWS clients with explicit credentials
dynamodb = boto3.resource(
    'dynamodb', 
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    aws_session_token=os.getenv('AWS_SESSION_TOKEN')
)
s3_client = boto3.client(
    's3', 
    region_name=AWS_REGION,
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    aws_session_token=os.getenv('AWS_SESSION_TOKEN')
)
bedrock_client = boto3.client(
    'bedrock-runtime', 
    region_name=BEDROCK_REGION,
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    aws_session_token=os.getenv('AWS_SESSION_TOKEN')
)


class SchemaCleaner:
    """Clean and normalize schemas before saving to DynamoDB"""
    
    def __init__(self):
        self.removed_count = 0
        self.empty_fields = []
    
    def clean_schema(self, schema: Dict[str, Any], mode: str = "POC") -> Dict[str, Any]:
        """✅ Main method: Clean entire schema by removing empty values"""
        self.removed_count = 0
        self.empty_fields = []
        
        print("\n" + "="*60)
        print(f"🧹 Cleaning {mode} Schema...")
        print("="*60)
        
        cleaned = json.loads(json.dumps(schema))
        cleaned = self._clean_recursive(cleaned, mode)
        
        # Print summary
        print(f"\n✓ Schema Cleaning Summary:")
        print(f"  Empty objects removed: {self.removed_count}")
        if self.empty_fields:
            print(f"  Empty fields removed: {len(self.empty_fields)}")
            for field in self.empty_fields[:10]:
                print(f"    - {field}")
            if len(self.empty_fields) > 10:
                print(f"    ... and {len(self.empty_fields) - 10} more")
        
        return cleaned
    
    def _clean_recursive(self, obj: Any, mode: str, path: str = "") -> Any:
        """✅ Recursively clean object, removing empty values"""
        
        if isinstance(obj, dict):
            cleaned = {}
            for key, value in obj.items():
                current_path = f"{path}.{key}" if path else key
                cleaned_value = self._clean_recursive(value, mode, current_path)
                
                if not self._is_empty(cleaned_value):
                    cleaned[key] = cleaned_value
                else:
                    if isinstance(value, str) and value == "":
                        self.empty_fields.append(current_path)
            
            return cleaned if cleaned else {}
        
        elif isinstance(obj, list):
            cleaned_list = []
            for idx, item in enumerate(obj):
                current_path = f"{path}[{idx}]"
                cleaned_item = self._clean_recursive(item, mode, current_path)
                
                if not self._is_empty(cleaned_item):
                    cleaned_list.append(cleaned_item)
                else:
                    if isinstance(item, dict):
                        self.removed_count += 1
            
            return cleaned_list
        
        else:
            return obj
    
    def _is_empty(self, value: Any) -> bool:
        """✅ Determine if a value should be considered empty"""
        
        if value is None:
            return True
        
        if isinstance(value, str):
            return value.strip() == ""
        
        if isinstance(value, list):
            if len(value) == 0:
                return True
            return all(self._is_empty(item) for item in value)
        
        if isinstance(value, dict):
            if len(value) == 0:
                return True
            non_empty_values = [v for v in value.values() if not self._is_empty(v)]
            return len(non_empty_values) == 0
        
        return False
    
    def clean_mode_specific_fields(self, schema: Dict[str, Any], mode: str) -> Dict[str, Any]:
        """✅ Clean mode-specific fields to ensure required arrays have content"""
        
        if mode == "POC":
            required_arrays = [
                "use_cases",
                "technical_stack",
                "aws_services",
                "success_metrics",
            ]
        else:  # PROD
            required_arrays = [
                "production_use_cases",
                "timelines_and_deliverables",
            ]
        
        for array_key in required_arrays:
            if array_key in schema:
                original_count = len(schema[array_key])
                schema[array_key] = [
                    item for item in schema[array_key]
                    if not self._is_empty_object(item)
                ]
                
                if original_count > len(schema[array_key]):
                    removed = original_count - len(schema[array_key])
                    print(f"  ✓ Removed {removed} empty objects from '{array_key}'")
        
        return schema
    
    def _is_empty_object(self, obj: Any) -> bool:
        """Check if object is empty (all fields empty strings)"""
        if not isinstance(obj, dict):
            return False
        return all(isinstance(v, str) and v.strip() == "" for v in obj.values())


class DynamicSchemaManager:
    """Manages dynamic JSON schema for POC/PROD documents"""
    
    def __init__(self, table_name: str = None, region: str = None):
        self.table_name = table_name or os.getenv(
            'DYNAMODB_TABLE_RAG_SCHEMA', 'rag-schema'
        )
        self.region = region or os.getenv('AWS_REGION', 'us-east-1')
        self.dynamodb = boto3.resource(
            'dynamodb', 
            region_name=self.region,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN')
        )
        self.table = self.dynamodb.Table(self.table_name)
        self.cleaner = SchemaCleaner()  # ✅ NEW: Initialize cleaner
        print(f"✓ Initialized Schema Manager with table: {self.table_name} ({self.region})")
    
    def get_poc_schema_template(self) -> Dict:
        """Get the POC-specific schema template"""
        return {
            "metadata": {
                "document_id": "",
                "mode": "POC",
                "created_date": "",
                "version": "1.0",
                "extraction_confidence": ""
            },
            "organization": {
                "client_name": "",
                "vendor_name": "",
                "project_title": ""
            },
            "poc_objectives": {
                "business_objective": "",
                "technical_objective": "",
                "expected_outcome": ""
            },
            "scope": {
                "included": [],
                "excluded": []
            },
            "use_cases": [
                {
                    "name": "",
                    "description": "",
                    "validation_focus": ""
                }
            ],
            "architecture": {
                "deployment_model": "",
                "processing_flow": []
            },
            "technical_stack": [
                {
                    "component": "",
                    "technology": "",
                    "purpose": ""
                }
            ],
            "data_details": {
                "input_types": [],
                "formats": [],
                "volume_estimate": ""
            },
            "constraints": [],
            "assumptions": [],
            "success_metrics": [
                {
                    "metric": "",
                    "target": ""
                }
            ],
            "aws_services": [
                {
                    "service": "",
                    "usage": ""
                }
            ],
            "key_learnings": []
        }
    
    def get_prod_schema_template(self) -> Dict:
        """Get the PROD schema template"""
        return {
            "metadata": {
                "document_id": "",
                "mode": "PROD",
                "created_date": "",
                "version": "1.0",
                "extraction_confidence": ""
            },
            "organization": {
                "client_name": "",
                "vendor_name": "",
                "project_title": ""
            },
            "business_objectives": [],
            "scope_of_work": {
                "included": [],
                "excluded": []
            },
            "production_use_cases": [
                {
                    "name": "",
                    "description": "",
                    "business_impact": ""
                }
            ],
            "system_architecture": {
                "deployment_model": "",
                "availability_model": "",
                "processing_flow": []
            },
            "technical_stack": {
                "compute": [],
                "storage": [],
                "ai_services": [],
                "integration_services": []
            },
            "performance_targets": {
                "concurrent_users": "",
                "latency": "",
                "availability": ""
            },
            "security_and_compliance": {
                "standards": [],
                "data_protection": [],
                "access_control": []
            },
            "customer_dependencies": [],
            "customer_responsibilities": [],
            "timelines_and_deliverables": [
                {
                    "phase": "",
                    "deliverables": []
                }
            ],
            "commercials": {
                "monthly_cost": "",
                "annual_cost": ""
            },
            "success_criteria": [],
            "operations_support": {
                "support_model": "",
                "sla": ""
            }
        }
    
    def get_schema_template(self, mode: str) -> Dict:
        """Get schema template based on mode"""
        normalized_mode = self.normalize_mode(mode)
        
        if normalized_mode == "POC":
            return self.get_poc_schema_template()
        else:
            template = self.get_prod_schema_template()
            template["metadata"]["mode"] = normalized_mode
            return template
    
    def normalize_mode(self, mode: str) -> str:
        """Normalize project mode to standard format"""
        mode_mapping = {
            "poc": "POC",
            "production": "PROD",
            "prod": "PROD",
            "poc_to_prod": "POC_TO_PROD",
            "poc_to_production": "POC_TO_PROD",
            "poctoprod": "POC_TO_PROD",
            "conversion": "POC_TO_PROD"
        }
        return mode_mapping.get(mode.lower(), mode.upper())
    
    def merge_schemas(self, base_schema: Dict, extracted_data: Dict) -> Dict:
        """Merge extracted data into schema template"""
        def deep_merge(base, extracted):
            for key, value in extracted.items():
                if key in base:
                    if isinstance(base[key], dict) and isinstance(value, dict):
                        base[key] = deep_merge(base[key], value)
                    elif isinstance(base[key], list) and isinstance(value, list):
                        if value and isinstance(value[0], dict):
                            base[key].extend(value)
                        else:
                            base[key] = value
                    else:
                        base[key] = value
                else:
                    base[key] = value
            return base
        
        merged = deep_merge(base_schema.copy(), extracted_data)
        return merged
    
    def save_to_dynamodb(self, schema_data: Dict, mode: str) -> str:
        """✅ UPDATED: Save schema to DynamoDB with deduplication and automatic cleaning"""
        try:
            normalized_mode = self.normalize_mode(mode)
            
            # ✅ NEW: Clean schema before saving
            print("\n[Cleaning schema before DynamoDB save...]")
            cleaned_schema = self.cleaner.clean_schema(schema_data, normalized_mode)
            cleaned_schema = self.cleaner.clean_mode_specific_fields(cleaned_schema, normalized_mode)
            
            # Extract company and project info for deduplication
            client_name = cleaned_schema.get("organization", {}).get("client_name", "").strip()
            project_title = cleaned_schema.get("organization", {}).get("project_title", "").strip()
            
            # ✅ NEW: Remove existing records with same company, project, and mode
            if client_name and project_title:
                self._remove_duplicate_schemas(client_name, project_title, normalized_mode)
            
            document_id = cleaned_schema.get("metadata", {}).get("document_id") or str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            # Extract counts based on mode
            if normalized_mode == "POC":
                use_case_count = len(cleaned_schema.get("use_cases", []))
                component_count = len(cleaned_schema.get("technical_stack", []))
            else:
                use_case_count = len(cleaned_schema.get("production_use_cases", []))
                component_count = len(cleaned_schema.get("technical_stack", {}).get("compute", [])) + \
                                 len(cleaned_schema.get("technical_stack", {}).get("storage", []))
            
            # Create lowercase versions for GSI queries
            client_name_lower = client_name.lower() if client_name else ""
            project_title_lower = project_title.lower() if project_title else ""
            
            item = {
                "document_id": document_id,
                "timestamp": timestamp,
                "mode": normalized_mode,
                "schema_version": "1.0",
                "client_name": client_name,
                "project_title": project_title,
                "client_name_lower": client_name_lower,  # ✅ NEW: For GSI queries
                "project_title_lower": project_title_lower,  # ✅ NEW: For GSI queries
                "vendor_name": cleaned_schema.get("organization", {}).get("vendor_name", ""),
                "full_schema": json.dumps(cleaned_schema, default=str),
                "use_case_count": use_case_count,
                "component_count": component_count,
                "created_date": cleaned_schema.get("metadata", {}).get("created_date", timestamp),
                "extraction_confidence": cleaned_schema.get("metadata", {}).get("extraction_confidence", "medium"),
                "mode_friendly": self._get_mode_friendly_name(normalized_mode),
                "is_poc": normalized_mode == "POC",
                "is_prod": normalized_mode == "PROD",
                "is_poc_to_prod": normalized_mode == "POC_TO_PROD",
                "empty_fields_removed": len(self.cleaner.empty_fields),  # ✅ NEW
                "empty_objects_removed": self.cleaner.removed_count,     # ✅ NEW
            }
            
            self.table.put_item(Item=item)
            
            print(f"\n✓ Schema saved to DynamoDB with ID: {document_id}")
            print(f"  Mode: {normalized_mode}")
            print(f"  Company: {client_name}")
            print(f"  Project: {project_title}")
            print(f"  Empty fields removed: {item['empty_fields_removed']}")
            print(f"  Empty objects removed: {item['empty_objects_removed']}")
            print(f"  Created: {timestamp}")
            
            return document_id
        
        except ClientError as e:
            print(f"❌ Error saving to DynamoDB: {e}")
            raise
    
    def _remove_duplicate_schemas(self, client_name: str, project_title: str, mode: str):
        """Remove existing schemas with same company, project, and mode"""
        try:
            client_name_lower = client_name.lower().strip()
            project_title_lower = project_title.lower().strip()
            
            print(f"\n[Checking for duplicates...]")
            print(f"  Company: {client_name}")
            print(f"  Project: {project_title}")
            print(f"  Mode: {mode}")
            
            # Get all records for this mode first, then filter manually
            # This handles both old records (without lowercase fields) and new records
            response = self.table.scan(
                FilterExpression='#mode = :mode',
                ExpressionAttributeNames={
                    '#mode': 'mode'
                },
                ExpressionAttributeValues={
                    ':mode': mode
                }
            )
            
            all_items = response.get('Items', [])
            existing_items = []
            
            # Manual filtering to handle both old and new record formats
            for item in all_items:
                item_client = item.get('client_name', '').strip()
                item_project = item.get('project_title', '').strip()
                
                # Check if this record matches (case-insensitive)
                if (item_client.lower() == client_name_lower and 
                    item_project.lower() == project_title_lower):
                    existing_items.append(item)
                    print(f"  Found match: {item_client} / {item_project} (ID: {item.get('document_id', 'N/A')})")
            
            if existing_items:
                print(f"  Found {len(existing_items)} existing record(s) to remove")
                
                # Delete existing records
                removed_count = 0
                for item in existing_items:
                    try:
                        self.table.delete_item(
                            Key={
                                'document_id': item['document_id'],
                                'timestamp': item['timestamp']
                            }
                        )
                        print(f"  ✓ Removed: {item['document_id']} ({item.get('created_date', 'N/A')})")
                        removed_count += 1
                    except ClientError as e:
                        print(f"  ⚠️  Failed to remove {item['document_id']}: {e}")
                
                print(f"  ✓ Deduplication complete - removed {removed_count} old record(s)")
            else:
                print(f"  ✓ No duplicates found - this is a new record")
                
        except ClientError as e:
            print(f"  ⚠️  Error during deduplication check: {e}")
            # Continue with save even if deduplication fails
        except Exception as e:
            print(f"  ⚠️  Unexpected error during deduplication: {e}")
            # Continue with save even if deduplication fails
    
    def _get_mode_friendly_name(self, mode: str) -> str:
        """Get user-friendly name for mode"""
        friendly_names = {
            "POC": "Proof of Concept",
            "PROD": "Production",
            "POC_TO_PROD": "POC to Production"
        }
        return friendly_names.get(mode, mode)
    
    def retrieve_schema(self, document_id: str) -> Optional[Dict]:
        """Retrieve schema from DynamoDB"""
        try:
            response = self.table.query(
                KeyConditionExpression='document_id = :doc_id',
                ExpressionAttributeValues={':doc_id': document_id}
            )
            
            if response['Items']:
                item = response['Items'][0]
                schema = json.loads(item.get('full_schema', '{}'))
                
                print(f"\n✅ Retrieved Schema:")
                print(f"  Mode: {item.get('mode', 'N/A')} ({item.get('mode_friendly', 'N/A')})")
                print(f"  Document ID: {document_id}")
                
                return schema
            return None
        
        except Exception as e:
            print(f"⚠️  Error retrieving schema: {e}")
            return None
    
    def list_schemas_by_client_and_mode(self, client_name: str, mode: str = None) -> List[Dict]:
        """List all schemas for a specific client, optionally filtered by mode"""
        try:
            normalized_mode = self.normalize_mode(mode) if mode else None
            
            if normalized_mode:
                print(f"\n📋 Schemas for {client_name} [{normalized_mode}]:")
                print("-" * 60)
                
                response = self.table.scan(
                    FilterExpression='client_name = :client AND #mode = :mode',
                    ExpressionAttributeNames={'#mode': 'mode'},
                    ExpressionAttributeValues={
                        ':client': client_name,
                        ':mode': normalized_mode
                    }
                )
            else:
                print(f"\n📋 All schemas for {client_name}:")
                print("-" * 60)
                
                response = self.table.scan(
                    FilterExpression='client_name = :client',
                    ExpressionAttributeValues={':client': client_name}
                )
            
            items = response.get('Items', [])
            
            if items:
                print(f"Found {len(items)} schema(s):\n")
                for idx, item in enumerate(items, 1):
                    print(f"{idx}. {item.get('project_title', 'N/A')}")
                    print(f"   Mode: {item.get('mode', 'N/A')} ({item.get('mode_friendly', 'N/A')})")
                    print(f"   ID: {item['document_id']}")
                    print(f"   Created: {item.get('created_date', 'N/A')}")
                    print(f"   Use Cases: {item.get('use_case_count', 0)}\n")
            
            return items
        
        except Exception as e:
            print(f"⚠️  Error listing schemas: {e}")
            return []
    
    def get_mode_statistics(self) -> Dict:
        """Get statistics about documents by mode"""
        try:
            print("\n📊 Document Statistics by Mode:")
            print("-" * 60)
            
            response = self.table.scan()
            items = response.get('Items', [])
            
            stats = {
                "POC": {"count": 0, "projects": []},
                "PROD": {"count": 0, "projects": []},
                "POC_TO_PROD": {"count": 0, "projects": []},
                "total": len(items)
            }
            
            for item in items:
                mode = item.get('mode', 'UNKNOWN')
                if mode in stats:
                    stats[mode]["count"] += 1
                    stats[mode]["projects"].append({
                        "company": item.get('client_name'),
                        "project": item.get('project_title'),
                        "document_id": item['document_id']
                    })
            
            for mode, data in stats.items():
                if mode != 'total':
                    print(f"\n{mode} ({self._get_mode_friendly_name(mode)}):")
                    print(f"  Count: {data['count']}")
                    if data['projects']:
                        print(f"  Projects:")
                        for proj in data['projects'][:5]:
                            print(f"    • {proj['company']} - {proj['project']}")
                        if len(data['projects']) > 5:
                            print(f"    ... and {len(data['projects']) - 5} more")
            
            print(f"\n{'='*60}")
            print(f"Total Documents: {stats['total']}")
            print(f"{'='*60}")
            
            return stats
        
        except Exception as e:
            print(f"⚠️  Error getting statistics: {e}")
            return {}


class PDFToSchemaConverter:
    """Convert PDF documents to dynamic JSON schema with proper metadata handling"""
    
    def __init__(self, model_id: str = None):
        """Initialize PDF converter with schema manager"""
        from app.core.config import Config
        config = Config()
        
        # Use config model_id if none provided
        self.model_id = model_id or config.MODEL_ID
        
        # Use explicit credentials for Bedrock client
        self.bedrock = boto3.client(
            'bedrock-runtime',
            region_name=config.BEDROCK_REGION,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN')
        )
        
        self.schema_manager = DynamicSchemaManager()
        print(f"✓ Initialized PDF Converter with model: {self.model_id}")
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        try:
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
            text_content = ""
            with open(pdf_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                print(f"  PDF pages: {len(pdf_reader.pages)}")
                
                for page_num, page in enumerate(pdf_reader.pages):
                    text = page.extract_text()
                    text_content += f"\n--- Page {page_num + 1} ---\n{text}"
            
            print(f"✓ Extracted {len(text_content)} characters from PDF")
            return text_content
        
        except Exception as e:
            print(f"❌ Error extracting PDF text: {e}")
            raise
    
    def get_poc_extraction_prompt(self, pdf_text: str) -> str:
        """Get Claude extraction prompt for POC documents"""
        return f"""Extract information from this POC document and return ONLY valid JSON.

REQUIRED STRUCTURE:
{{
  "metadata": {{
    "extraction_confidence": "high"
  }},
  "organization": {{
    "client_name": "Company Name",
    "vendor_name": "Vendor Name", 
    "project_title": "Project Title"
  }},
  "poc_objectives": {{
    "business_objective": "Business goal",
    "technical_objective": "Technical goal",
    "expected_outcome": "Expected result"
  }},
  "scope": {{
    "included": ["Item 1", "Item 2"],
    "excluded": ["Item 1"]
  }},
  "use_cases": [{{
    "name": "Use Case Name",
    "description": "Description",
    "validation_focus": "What to validate"
  }}],
  "technical_stack": [{{
    "component": "Component Name",
    "technology": "Technology Used",
    "purpose": "Purpose"
  }}],
  "aws_services": [{{
    "service": "AWS Service Name",
    "usage": "How it's used"
  }}],
  "success_metrics": [{{
    "metric": "Metric Name",
    "target": "Target Value"
  }}],
  "constraints": ["Constraint 1"],
  "assumptions": ["Assumption 1"]
}}

RULES:
- Extract actual values from the document
- If not found, use reasonable defaults
- ALL arrays must have at least 1 item
- Return ONLY the JSON, no markdown or explanations

Document:
{pdf_text[:4000]}

JSON:"""
    
    def get_prod_extraction_prompt(self, pdf_text: str) -> str:
        """Get Claude extraction prompt for PROD documents"""
        return f"""Extract information from this production document and return ONLY valid JSON.

REQUIRED STRUCTURE:
{{
  "metadata": {{
    "extraction_confidence": "high"
  }},
  "organization": {{
    "client_name": "Company Name",
    "vendor_name": "Vendor Name",
    "project_title": "Project Title"
  }},
  "business_objectives": ["Objective 1", "Objective 2"],
  "scope_of_work": {{
    "included": ["Item 1", "Item 2"],
    "excluded": ["Item 1"]
  }},
  "production_use_cases": [{{
    "name": "Use Case Name",
    "description": "Description",
    "business_impact": "Impact"
  }}],
  "timelines_and_deliverables": [{{
    "phase": "Phase Name",
    "deliverables": ["Deliverable 1"]
  }}],
  "success_criteria": ["Criteria 1", "Criteria 2"],
  "customer_dependencies": ["Dependency 1"],
  "customer_responsibilities": ["Responsibility 1"]
}}

RULES:
- Extract actual values from the document
- If not found, use reasonable defaults
- ALL arrays must have at least 1 item
- Return ONLY the JSON, no markdown or explanations

Document:
{pdf_text[:4000]}

JSON:"""
    
    def extract_structure_with_bedrock(self, pdf_text: str, mode: str) -> Dict:
        """Extract structured schema from PDF with mode-specific prompt"""
        try:
            if len(pdf_text) > 8000:
                pdf_text = pdf_text[:8000] + "\n... [content truncated] ..."
            
            normalized_mode = self.schema_manager.normalize_mode(mode)
            
            if normalized_mode == "POC":
                prompt = self.get_poc_extraction_prompt(pdf_text)
                print("  Using POC extraction prompt")
            else:
                prompt = self.get_prod_extraction_prompt(pdf_text)
                print("  Using PROD extraction prompt")
            
            # Use boto3 client instead of ChatBedrock
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 60000,
                    "temperature": 0.3,
                    "messages": [{"role": "user", "content": prompt}]
                })
            )
            
            response_body = json.loads(response['body'].read())
            response_text = response_body['content'][0]['text']
            
            json_str = self._extract_json_from_response(response_text)
            
            if json_str:
                try:
                    extracted_data = json.loads(json_str)
                    print(f"✓ Successfully extracted structure")
                    extracted_data = self._ensure_metadata_populated(extracted_data, normalized_mode)
                    return extracted_data
                    
                except json.JSONDecodeError as e:
                    print(f"⚠️  JSON parsing error: {e}")
                    print(f"   Error at position: {e.pos}")
                    
                    # Show context around error
                    if e.pos and len(json_str) > e.pos:
                        start = max(0, e.pos - 50)
                        end = min(len(json_str), e.pos + 50)
                        context = json_str[start:end]
                        print(f"   Context: ...{context}...")
                    
                    # Try to fix JSON
                    fixed_json = self._fix_json_errors(json_str)
                    if fixed_json:
                        try:
                            extracted_data = json.loads(fixed_json)
                            extracted_data = self._ensure_metadata_populated(extracted_data, normalized_mode)
                            print("✓ JSON fixed successfully")
                            return extracted_data
                        except json.JSONDecodeError as fix_error:
                            print(f"❌ Could not fix JSON: {fix_error}")
                            print(f"   Returning minimal schema as fallback")
                            return self._get_minimal_schema(normalized_mode)
                    else:
                        print("❌ JSON fix failed, returning minimal schema")
                        return self._get_minimal_schema(normalized_mode)
            else:
                print("⚠️  No JSON found in response")
                print(f"   Response preview: {response_text[:200]}...")
                return self._get_minimal_schema(normalized_mode)
        
        except Exception as e:
            print(f"❌ Error extracting structure: {e}")
            import traceback
            traceback.print_exc()
            return self._get_minimal_schema(normalized_mode)
    
    def _get_minimal_schema(self, mode: str) -> Dict:
        """Return a minimal valid schema when extraction fails"""
        print(f"   ⚠️  Using minimal fallback schema for {mode}")
        
        if mode == "POC":
            return {
                "metadata": {
                    "extraction_confidence": "low"
                },
                "organization": {
                    "client_name": "Unknown",
                    "vendor_name": "Unknown",
                    "project_title": "Unknown"
                },
                "poc_objectives": {
                    "business_objective": "To be determined",
                    "technical_objective": "To be determined",
                    "expected_outcome": "To be determined"
                },
                "scope": {
                    "included": ["To be determined"],
                    "excluded": ["To be determined"]
                },
                "use_cases": [{
                    "name": "Use Case 1",
                    "description": "To be determined",
                    "validation_focus": "To be determined"
                }],
                "technical_stack": [{
                    "component": "Component 1",
                    "technology": "To be determined",
                    "purpose": "To be determined"
                }],
                "aws_services": [{
                    "service": "AWS Service",
                    "usage": "To be determined"
                }],
                "success_metrics": [{
                    "metric": "Success Metric",
                    "target": "To be determined"
                }],
                "constraints": ["To be determined"],
                "assumptions": ["To be determined"]
            }
        else:  # PROD
            return {
                "metadata": {
                    "extraction_confidence": "low"
                },
                "organization": {
                    "client_name": "Unknown",
                    "vendor_name": "Unknown",
                    "project_title": "Unknown"
                },
                "business_objectives": ["To be determined"],
                "scope_of_work": {
                    "included": ["To be determined"],
                    "excluded": ["To be determined"]
                },
                "production_use_cases": [{
                    "name": "Use Case 1",
                    "description": "To be determined",
                    "business_impact": "To be determined"
                }],
                "timelines_and_deliverables": [{
                    "phase": "Phase 1",
                    "deliverables": ["To be determined"]
                }],
                "success_criteria": ["To be determined"],
                "customer_dependencies": ["To be determined"],
                "customer_responsibilities": ["To be determined"]
            }
    
    def _ensure_metadata_populated(self, data: Dict, mode: str) -> Dict:
        """✅ Ensure all metadata fields are properly populated"""
        
        if "metadata" not in data:
            data["metadata"] = {}
        
        metadata = data["metadata"]
        
        if not metadata.get("extraction_confidence"):
            if mode == "POC":
                has_use_cases = bool(data.get("use_cases"))
                has_technical_stack = bool(data.get("technical_stack"))
                has_objectives = bool(data.get("poc_objectives"))
            else:
                has_use_cases = bool(data.get("production_use_cases"))
                has_technical_stack = bool(data.get("technical_stack"))
                has_objectives = bool(data.get("business_objectives"))
            
            if has_use_cases and has_technical_stack and has_objectives:
                metadata["extraction_confidence"] = "high"
            elif has_use_cases or has_technical_stack:
                metadata["extraction_confidence"] = "medium"
            else:
                metadata["extraction_confidence"] = "low"
            
            print(f"  ✓ Set extraction_confidence: {metadata['extraction_confidence']}")
        
        if not metadata.get("mode"):
            metadata["mode"] = mode
        
        if not metadata.get("document_id"):
            metadata["document_id"] = str(uuid.uuid4())
        
        if not metadata.get("created_date"):
            metadata["created_date"] = datetime.now().isoformat()
        
        if not metadata.get("version"):
            metadata["version"] = "1.0"
        
        return data
    
    def _extract_json_from_response(self, response_text: str) -> Optional[str]:
        """Extract JSON from Claude's response with improved parsing"""
        
        # Debug: Print response preview
        print(f"   Response preview: {response_text[:300]}...")
        
        # Strategy 1: Try markdown JSON block first (most common)
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL | re.IGNORECASE)
        if json_match:
            print("   ✓ Found JSON in markdown block")
            return json_match.group(1)
        
        # Strategy 2: Try generic code block
        code_match = re.search(r'```\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if code_match:
            print("   ✓ Found JSON in code block")
            return code_match.group(1)
        
        # Strategy 3: Look for JSON object anywhere in response
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
        if json_match:
            print("   ✓ Found JSON object in response")
            return json_match.group(0)
        
        # Strategy 4: Find balanced JSON object manually
        json_start = response_text.find('{')
        if json_start >= 0:
            brace_count = 0
            in_string = False
            escape_next = False
            
            for i in range(json_start, len(response_text)):
                char = response_text[i]
                
                if escape_next:
                    escape_next = False
                    continue
                
                if char == '\\':
                    escape_next = True
                    continue
                
                if char == '"' and not escape_next:
                    in_string = not in_string
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            print("   ✓ Found balanced JSON object")
                            return response_text[json_start:i+1]
        
        print("   ❌ No JSON found with any strategy")
        return None
    
    def _fix_json_errors(self, json_str: str) -> Optional[str]:
        """Fix common JSON errors with improved handling"""
        try:
            # Remove control characters except newlines, tabs
            json_str = ''.join(char for char in json_str if ord(char) >= 32 or char in '\n\r\t')
            
            # Fix trailing commas before closing brackets/braces
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            
            # Fix missing commas between array/object elements
            json_str = re.sub(r'"\s*\n\s*"', '",\n"', json_str)
            json_str = re.sub(r'}\s*\n\s*{', '},\n{', json_str)
            json_str = re.sub(r']\s*\n\s*\[', '],\n[', json_str)
            
            # Fix unescaped newlines in strings
            json_str = re.sub(r':\s*"([^"]*)\n([^"]*)"', lambda m: f': "{m.group(1)}\\n{m.group(2)}"', json_str)
            
            # Try to parse and return if successful
            json.loads(json_str)
            return json_str
            
        except json.JSONDecodeError as e:
            print(f"   ⚠️  JSON fix attempt failed: {e}")
            
            # Last resort: try to extract valid JSON using regex patterns
            try:
                # Remove everything after the last valid closing brace
                last_brace = json_str.rfind('}')
                if last_brace > 0:
                    json_str = json_str[:last_brace+1]
                    json.loads(json_str)
                    return json_str
            except:
                pass
            
            return None
        except Exception as e:
            print(f"   ⚠️  Unexpected error in JSON fix: {e}")
            return None
    
    def validate_schema(self, data: Dict, mode: str) -> Tuple[bool, str]:
        """Validate extracted data against mode-specific schema"""
        normalized_mode = self.schema_manager.normalize_mode(mode)
        
        if "metadata" not in data:
            return False, "Missing required field: metadata"
        
        metadata = data["metadata"]
        
        if not metadata.get("document_id"):
            return False, "Missing document_id in metadata"
        
        if not metadata.get("extraction_confidence"):
            return False, "Missing extraction_confidence in metadata"
        
        if not metadata.get("mode"):
            return False, "Missing mode in metadata"
        
        if "organization" not in data:
            return False, "Missing required field: organization"
        
        if not data["organization"].get("client_name"):
            return False, "Missing client_name in organization"
        
        if normalized_mode == "POC":
            required_fields = ["poc_objectives", "use_cases", "scope"]
            for field in required_fields:
                if field not in data:
                    return False, f"Missing required POC field: {field}"
        else:
            required_fields = ["business_objectives", "production_use_cases", "scope_of_work"]
            for field in required_fields:
                if field not in data:
                    return False, f"Missing required PROD field: {field}"
        
        return True, f"✓ Schema validation passed for {normalized_mode} mode"
    
    def convert_pdf_to_schema(self, pdf_path: str, mode: str = "POC") -> Dict:
        """Complete pipeline: Extract PDF → Structure → Schema"""
        print("\n" + "="*60)
        print("📄 Starting PDF to Schema Conversion")
        print("="*60)
        
        normalized_mode = self.schema_manager.normalize_mode(mode)
        print(f"Mode: {normalized_mode}")
        
        print("\n[1/4] Extracting text from PDF...")
        pdf_text = self.extract_text_from_pdf(pdf_path)
        
        print("[2/4] Extracting structure with Claude...")
        extracted_data = self.extract_structure_with_bedrock(pdf_text, mode)
        
        print("[3/4] Merging with schema template...")
        schema_template = self.schema_manager.get_schema_template(mode)
        
        if "metadata" not in extracted_data:
            extracted_data["metadata"] = {}
        
        extracted_data["metadata"]["document_id"] = str(uuid.uuid4())
        extracted_data["metadata"]["created_date"] = datetime.now().isoformat()
        extracted_data["metadata"]["mode"] = normalized_mode
        
        complete_schema = self.schema_manager.merge_schemas(schema_template, extracted_data)
        print(f"✓ Schema merged successfully")
        
        print("[4/4] Validating schema...")
        is_valid, validation_msg = self.validate_schema(complete_schema, mode)
        print(f"{validation_msg}")
        
        return complete_schema
    
    def process_and_store(self, pdf_path: str, mode: str = "POC") -> Dict:
        """Convert PDF to schema and store in DynamoDB with automatic cleaning"""
        try:
            schema = self.convert_pdf_to_schema(pdf_path, mode)
            
            print("\n[Saving to DynamoDB...]")
            # ✅ save_to_dynamodb now automatically cleans the schema
            document_id = self.schema_manager.save_to_dynamodb(schema, mode)
            
            normalized_mode = self.schema_manager.normalize_mode(mode)
            
            if normalized_mode == "POC":
                use_case_count = len(schema.get("use_cases", []))
            else:
                use_case_count = len(schema.get("production_use_cases", []))
            
            result = {
                "success": True,
                "document_id": document_id,
                "mode": normalized_mode,
                "client_name": schema.get("organization", {}).get("client_name"),
                "project_title": schema.get("organization", {}).get("project_title"),
                "use_case_count": use_case_count,
                "empty_fields_removed": len(self.schema_manager.cleaner.empty_fields),
                "empty_objects_removed": self.schema_manager.cleaner.removed_count,
                "timestamp": datetime.now().isoformat()
            }
            
            print("\n" + "="*60)
            print("✅ Conversion + Cleaning Complete!")
            print("="*60)
            print(f"Document ID: {document_id}")
            print(f"Mode: {result['mode']}")
            print(f"Client: {result['client_name']}")
            print(f"Project: {result['project_title']}")
            print(f"Use Cases: {result['use_case_count']}")
            print(f"Empty fields removed: {result['empty_fields_removed']}")
            print(f"Empty objects removed: {result['empty_objects_removed']}")
            
            return result
        
        except Exception as e:
            print(f"❌ Error in process_and_store: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": str(e)}


class POCRetriever:
    """Retrieve schemas from rag-schema table"""
    
    def __init__(self, table_name: str = None, region: str = None):
        self.table_name = table_name or os.getenv(
            'DYNAMODB_TABLE_RAG_SCHEMA', 'rag-schema'
        )
        self.region = region or os.getenv('AWS_REGION', 'us-east-1')
        self.dynamodb = boto3.resource(
            'dynamodb', 
            region_name=self.region,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN')
        )
        self.table = self.dynamodb.Table(self.table_name)
        print(f"✓ Initialized Retriever with table: {self.table_name} ({self.region})")
    
    def normalize_mode(self, mode: str) -> str:
        """Normalize mode to standard format"""
        mode_mapping = {
            "poc": "POC",
            "production": "PROD",
            "prod": "PROD",
            "poc_to_prod": "POC_TO_PROD",
        }
        return mode_mapping.get(mode.lower(), mode.upper())
    
    def retrieve_by_three_params(self, company_name: str, project_title: str, mode: str) -> Optional[Dict]:
        """Retrieve schema by company name, project title, and mode"""
        try:
            normalized_mode = self.normalize_mode(mode)
            
            print(f"\n[Retriever] Querying rag-schema table...")
            print(f"  Company: {company_name}")
            print(f"  Project: {project_title}")
            print(f"  Mode: {normalized_mode}")
            
            response = self.table.scan(
                FilterExpression='client_name = :client AND project_title = :title AND #mode = :type',
                ExpressionAttributeNames={'#mode': 'mode'},
                ExpressionAttributeValues={
                    ':client': company_name,
                    ':title': project_title,
                    ':type': normalized_mode
                }
            )
            
            items = response.get('Items', [])
            
            if items:
                item = items[0]
                schema = json.loads(item.get('full_schema', '{}'))
                
                print(f"\n✅ Schema Retrieved:")
                print(f"  Document ID: {item['document_id']}")
                print(f"  Mode: {item.get('mode', 'N/A')}")
                print(f"  Use Cases: {item.get('use_case_count', 0)}")
                
                return schema
            else:
                print(f"\n⚠️  Schema not found")
                return None
        
        except Exception as e:
            print(f"❌ Error retrieving schema: {e}")
            import traceback
            traceback.print_exc()
            return None
