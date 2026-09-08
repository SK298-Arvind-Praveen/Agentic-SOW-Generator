"""
DynamoDB Handler - PRODUCTION OPTIMIZED with Query Operations + VERSION MANAGEMENT
✅ Uses Query instead of Scan for better performance
✅ Auto-increment versions per PROJECT + MODE
✅ Separate versioning: POC v1, v2, v3 → PROD v1, v2, v3
✅ Company grouping with project versions
✅ Includes task_id tracking
✅ Google Drive link support

REQUIRED GSIs:
--------------
Table: agentic-poc
1. GSI: customer-index
   - Partition Key: customer_name_lower (String)
   - Sort Key: timestamp (String)

2. GSI: author-index
   - Partition Key: author_name_lower (String)
   - Sort Key: timestamp (String)

3. GSI: project-index
   - Partition Key: project_name_lower (String)
   - Sort Key: timestamp (String)

4. GSI: mode-index
   - Partition Key: mode (String)
   - Sort Key: timestamp (String)

5. GSI: task-index
   - Partition Key: task_id (String)
   - Sort Key: timestamp (String)
"""

import boto3
import os
import uuid
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Optional
from botocore.exceptions import ClientError

load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")


class DynamoDBHandlerOptimized:
    """Production-optimized DynamoDB handler with VERSION MANAGEMENT"""

    def __init__(self, table_name=None, region=None):
        """Initialize DynamoDB handler with explicit credentials from environment"""
        self.table_name = table_name or os.getenv(
            'DYNAMODB_TABLE_POC_DOCUMENTS', 'agentic-poc'
        )
        self.region = region or os.getenv('AWS_REGION', 'us-east-1')

        try:
            # Explicitly use environment variables
            self.dynamodb = boto3.resource(
                'dynamodb',
                region_name=self.region,
                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
                aws_session_token=os.getenv('AWS_SESSION_TOKEN')
            )
            self.table = self.dynamodb.Table(self.table_name)
            print(f"✓ Configured DynamoDB table: {self.table_name} ({self.region})")
        except Exception as e:
            print(f"❌ Failed to connect to DynamoDB: {e}")
            raise

    def generate_document_id(self):
        """Generate unique document ID"""
        return f"DOC_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

    def get_document_by_id(self, document_id: str):
        """Fetch the newest row for a document id without assuming a sort key."""
        try:
            response = self.table.query(
                KeyConditionExpression='document_id = :document_id',
                ExpressionAttributeValues={':document_id': str(document_id)},
                ScanIndexForward=False,
                Limit=1,
            )
            items = response.get('Items', [])
            return items[0] if items else None
        except ClientError:
            response = self.table.scan(
                FilterExpression='document_id = :document_id',
                ExpressionAttributeValues={':document_id': str(document_id)},
                Limit=100,
            )
            items = response.get('Items', [])
            return sorted(items, key=lambda item: str(item.get('timestamp') or ''), reverse=True)[0] if items else None

    def get_next_version(self, company_name: str, project_name: str, mode: str) -> str:
        """
        ✅ VERSION MANAGEMENT: Get next version number for a project + mode combination
        
        Args:
            company_name: Customer name
            project_name: Project name
            mode: POC, PROD, or POC_TO_PROD
            
        Returns:
            str: Next version (e.g., "v1", "v2", "v3")
        """
        try:
            company_name_lower = company_name.lower().strip()
            project_name_lower = project_name.lower().strip()
            mode_upper = mode.upper()

            print(f"\n🔢 Calculating next version...")
            print(f"   Company: {company_name}")
            print(f"   Project: {project_name}")
            print(f"   Mode: {mode_upper}")

            # Query existing documents for this project + mode
            try:
                response = self.table.query(
                    IndexName='project-index',
                    KeyConditionExpression='project_name_lower = :pn',
                    FilterExpression='customer_name_lower = :cn AND #mode = :m',
                    ExpressionAttributeNames={'#mode': 'mode'},
                    ExpressionAttributeValues={
                        ':pn': project_name_lower,
                        ':cn': company_name_lower,
                        ':m': mode_upper
                    }
                )
                items = response.get('Items', [])
                
            except ClientError as e:
                # Fallback to scan if GSI doesn't exist
                print(f"   ⚠️  Using scan fallback...")
                response = self.table.scan(
                    FilterExpression='project_name_lower = :pn AND customer_name_lower = :cn AND #mode = :m',
                    ExpressionAttributeNames={'#mode': 'mode'},
                    ExpressionAttributeValues={
                        ':pn': project_name_lower,
                        ':cn': company_name_lower,
                        ':m': mode_upper
                    }
                )
                items = response.get('Items', [])

            # Extract version numbers
            versions = []
            for item in items:
                version_str = item.get('version', 'v1')
                # Extract number from "v1", "v2", etc.
                try:
                    if version_str.startswith('v'):
                        version_num = int(version_str[1:])
                        versions.append(version_num)
                except (ValueError, IndexError):
                    continue

            # Calculate next version
            if versions:
                max_version = max(versions)
                next_version = f"v{max_version + 1}"
            else:
                next_version = "v1"

            print(f"   ✓ Existing versions: {sorted(versions) if versions else 'None'}")
            print(f"   ✓ Next version: {next_version}")

            return next_version

        except Exception as e:
            print(f"   ❌ Error calculating version: {e}")
            # Default to v1 on error
            return "v1"

    def validate_required_fields(self, metadata, s3_url):
        """Validate that all essential fields are present"""
        required_fields = {
            'company_name': 'Customer Name',
            'author_name': 'Author Name',
            'document_date': 'Date'
        }

        missing_fields = []

        for field, display_name in required_fields.items():
            value = metadata.get(field)
            if value is None:
                missing_fields.append(f"{display_name} ({field})")
            else:
                value_str = str(value).strip()
                if not value_str or value_str == "Unknown" or value_str == "None":
                    missing_fields.append(f"{display_name} ({field})")

        if s3_url is None:
            missing_fields.append("S3 URL (is None)")
        else:
            s3_str = str(s3_url).strip()
            if not s3_str:
                missing_fields.append("S3 URL (empty)")

        if missing_fields:
            error_msg = f"Missing required fields: {', '.join(missing_fields)}"
            return False, missing_fields, error_msg

        return True, [], ""

    def find_similar_documents(self, company_name, project_name, owner_email=None):
        """
        ✅ OPTIMIZED: Find documents using Query on customer-index GSI

        Args:
            company_name: Customer name
            project_name: Project name

        Returns:
            list: Documents matching criteria, sorted by timestamp (newest first)
        """
        try:
            # Normalize: lowercase + strip + remove extra spaces
            company_name_lower = str(company_name).lower().strip()
            company_name_lower = ' '.join(company_name_lower.split())

            project_name_lower = str(project_name).lower().strip()
            project_name_lower = ' '.join(project_name_lower.split())

            print(f"\n🔍 Querying for similar documents (using customer-index GSI)...")
            print(f"   Customer (normalized): {company_name_lower}")
            print(f"   Project (normalized): {project_name_lower}")

            # ✅ QUERY on customer-index GSI (much faster than scan)
            response = self.table.query(
                IndexName='customer-index',
                KeyConditionExpression='customer_name_lower = :cn',
                ExpressionAttributeValues={
                    ':cn': company_name_lower
                },
                ScanIndexForward=False  # Sort by timestamp descending (newest first)
            )

            all_customer_docs = response.get('Items', [])
            print(f"   📊 Documents for customer: {len(all_customer_docs)}")

            # Filter by project name
            matching_items = []
            for item in all_customer_docs:
                stored_project = str(item.get('project_name', '')).lower().strip()
                stored_project = ' '.join(stored_project.split())

                same_owner = (
                    not owner_email
                    or str(item.get('owner_email', '')).casefold().strip()
                    == str(owner_email).casefold().strip()
                )
                if stored_project == project_name_lower and same_owner:
                    matching_items.append(item)
                    print(f"   ✓ Match: {item.get('customer_name')} / {item.get('project_name')} ({item.get('timestamp')})")

            print(f"   Found {len(matching_items)} similar document(s)")

            return matching_items

        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                print(f"⚠️  GSI 'customer-index' not found - falling back to scan")
                return self._find_similar_documents_fallback(company_name, project_name, owner_email)
            else:
                print(f"❌ Error querying documents: {e}")
                return []
        except Exception as e:
            print(f"❌ Error finding similar documents: {e}")
            import traceback
            traceback.print_exc()
            return []

    def _find_similar_documents_fallback(self, company_name, project_name, owner_email=None):
        """Fallback to scan if GSI doesn't exist"""
        try:
            company_name_lower = str(company_name).lower().strip()
            company_name_lower = ' '.join(company_name_lower.split())

            project_name_lower = str(project_name).lower().strip()
            project_name_lower = ' '.join(project_name_lower.split())

            print(f"   Using SCAN (slower) - consider creating GSI for production")

            response = self.table.scan()
            all_items = response.get('Items', [])

            matching_items = []
            for item in all_items:
                stored_company = str(item.get('customer_name', '')).lower().strip()
                stored_company = ' '.join(stored_company.split())

                stored_project = str(item.get('project_name', '')).lower().strip()
                stored_project = ' '.join(stored_project.split())

                same_owner = (
                    not owner_email
                    or str(item.get('owner_email', '')).casefold().strip()
                    == str(owner_email).casefold().strip()
                )
                if stored_company == company_name_lower and stored_project == project_name_lower and same_owner:
                    matching_items.append(item)

            matching_items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return matching_items

        except Exception as e:
            print(f"❌ Fallback scan failed: {e}")
            return []

    def delete_old_duplicates(self, similar_docs, keep_count=2):
        """
        Delete documents older than the LAST 'keep_count'

        Args:
            similar_docs: List of similar documents (sorted by timestamp desc)
            keep_count: How many to keep (default: 2)

        Returns:
            dict: Deletion results
        """
        try:
            if len(similar_docs) <= keep_count:
                print(f"\n✓ Only {len(similar_docs)} document(s) found - no deletion needed")
                return {
                    "deleted_count": 0,
                    "deleted_ids": [],
                    "kept_count": len(similar_docs),
                    "action": "NO_ACTION_NEEDED"
                }

            docs_to_keep = similar_docs[:keep_count]
            docs_to_delete = similar_docs[keep_count:]

            print(f"\n🗑️  DEDUPLICATION CLEANUP")
            print(f"   Total: {len(similar_docs)} | Keep: {keep_count} | Delete: {len(docs_to_delete)}")

            deleted_ids = []

            for i, doc in enumerate(docs_to_delete, 1):
                try:
                    doc_id = doc.get('document_id')
                    timestamp = doc.get('timestamp')

                    # DELETE from DynamoDB
                    self.table.delete_item(
                        Key={
                            'document_id': doc_id,
                            'timestamp': timestamp
                        }
                    )

                    deleted_ids.append(doc_id)
                    print(f"   {i}. ✓ Deleted: {timestamp[:19]}")

                except Exception as e:
                    print(f"   {i}. ❌ Failed: {e}")

            print(f"✅ Cleanup complete: Deleted {len(deleted_ids)}, Kept {keep_count}")

            return {
                "deleted_count": len(deleted_ids),
                "deleted_ids": deleted_ids,
                "kept_count": keep_count,
                "action": "CLEANUP_PERFORMED"
            }

        except Exception as e:
            print(f"❌ Cleanup error: {e}")
            return {
                "deleted_count": 0,
                "deleted_ids": [],
                "error": str(e),
                "action": "CLEANUP_FAILED"
            }

    def save_document_metadata(self, metadata, s3_url, s3_result=None, drive_link=None, 
                              keep_duplicates=2, task_id=None, auto_version=True, 
                              account_id=None, project_id=None):
        """
        ✅ ENHANCED: Save document metadata WITH auto-versioning per project + mode
        
        Args:
            metadata: Document metadata dict
            s3_url: S3 URL of document
            s3_result: S3 upload result
            drive_link: Google Drive link (optional)
            keep_duplicates: Number of similar docs to keep (default: 2)
            task_id: Task/Job ID from the API (optional)
            auto_version: Auto-calculate version (default: True)
            account_id: Account ID from agentic-sow-v2 (optional)
            project_id: Project ID from agentic-sow-v2 (optional)
            
        Returns:
            dict: Save result with version info
        """
        try:
            print(f"\n📋 DynamoDB Save (WITH VERSIONING) - Validating inputs...")

            # Validate required fields
            is_valid, missing_fields, error_msg = self.validate_required_fields(metadata, s3_url)

            if not is_valid:
                print(f"❌ Validation Failed: {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "missing_fields": missing_fields
                }

            # Extract and clean fields
            company_name = str(metadata.get("company_name", "Unknown Company")).strip()
            author_name = str(metadata.get("author_name", "Unknown Author")).strip()
            project_name = str(metadata.get("project_title") or metadata.get("project_name", "Not Specified")).strip()
            document_date = str(metadata.get("document_date", datetime.now().strftime("%d %B %Y"))).strip()
            mode = str(metadata.get("mode", "UNKNOWN")).upper()
            s3_url_str = str(s3_url).strip()

            # Create lowercase versions for GSI queries
            company_name_lower = company_name.lower()
            author_name_lower = author_name.lower()
            project_name_lower = project_name.lower()

            print(f"   ✓ Customer: {company_name}")
            print(f"   ✓ Project: {project_name}")
            print(f"   ✓ Mode: {mode}")
            if task_id:
                print(f"   ✓ Task ID: {task_id}")
            if drive_link:
                print(f"   ✓ Drive Link: {drive_link[:50]}...")

            # ✅ AUTO-VERSION: Calculate next version for this project + mode
            if auto_version:
                version = self.get_next_version(company_name, project_name, mode)
            else:
                version = metadata.get('version', 'v1')

            # Every generated version is part of the audit/history view. Older
            # versions must never be treated as disposable duplicates merely
            # because company and project names match.
            similar_docs = self.find_similar_documents(
                company_name,
                project_name,
                owner_email=metadata.get('owner_email'),
            )
            cleanup_result = None

            # Save new document
            document_id = self.generate_document_id()
            timestamp = datetime.now().isoformat()

            item = {
                "document_id": document_id,
                "timestamp": timestamp,
                # Original case for display
                "customer_name": company_name,
                "author_name": author_name,
                "project_name": project_name,
                "document_date": document_date,
                "s3_url": s3_url_str,
                # Lowercase for GSI queries
                "customer_name_lower": company_name_lower,
                "author_name_lower": author_name_lower,
                "project_name_lower": project_name_lower,
                # Mode and version
                "mode": mode,
                "version": version,  # ✅ VERSION FIELD
                "business_unit": metadata.get("business_unit"),
                "owner_email": metadata.get("owner_email"),
                "owner_name": metadata.get("owner_name"),
            }
            if metadata.get("total_tokens") is not None:
                item["total_tokens"] = int(metadata.get("total_tokens") or 0)
            if metadata.get("token_usage"):
                item["token_usage"] = metadata["token_usage"]
            if metadata.get("aws_pricing"):
                item["aws_pricing"] = metadata["aws_pricing"]
            if metadata.get("source_documents"):
                item["source_documents"] = metadata["source_documents"]
            if metadata.get("source_scope_id"):
                item["source_scope_id"] = str(metadata["source_scope_id"])
            if metadata.get("parent_document_id"):
                item["parent_document_id"] = str(metadata["parent_document_id"])
            if metadata.get("refinement_instructions"):
                item["refinement_instructions"] = str(metadata["refinement_instructions"])
            if isinstance(metadata.get("selected_sow_sections"), list):
                item["selected_sow_sections"] = [
                    str(value) for value in metadata["selected_sow_sections"]
                ]

            # ✅ NEW: Add account_id and project_id if provided
            if account_id:
                item["account_id"] = account_id
                print(f"   ✓ Account ID: {account_id}")
            if project_id:
                item["project_id"] = project_id
                print(f"   ✓ Project ID: {project_id}")

            # Add optional fields
            if task_id:
                item["task_id"] = task_id
            if drive_link:
                item["drive_link"] = drive_link
            if s3_result and 'file_size' in s3_result:
                item["file_size"] = s3_result['file_size']

            print(f"\n💾 Saving to DynamoDB with version: {version}")
            response = self.table.put_item(Item=item)

            print(f"✅ Document saved: {document_id}")
            print(f"   📦 Version: {version}")
            if drive_link:
                print(f"   📎 With Drive Link: {drive_link[:60]}...")

            return {
                "success": True,
                "document_id": document_id,
                "timestamp": timestamp,
                "task_id": task_id,
                "s3_url": s3_url_str,
                "drive_link": drive_link,
                "customer_name": company_name,
                "author_name": author_name,
                "project_name": project_name,
                "document_date": document_date,
                "mode": mode,
                "version": version,  # ✅ Return version
                "business_unit": metadata.get("business_unit"),
                "owner_email": metadata.get("owner_email"),
                "owner_name": metadata.get("owner_name"),
                "total_tokens": item.get("total_tokens"),
                "token_usage": item.get("token_usage"),
                "deduplication": {
                    "similar_found": len(similar_docs),
                    "kept_count": len(similar_docs) + 1,
                    "cleanup_performed": False,
                    "cleanup_result": cleanup_result
                },
                "response": response
            }

        except Exception as e:
            print(f"❌ Save failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }

    def get_companies_grouped(self, limit=1000, business_unit=None, owner_email=None):
        """
        ✅ NEW: Get all documents grouped by company with project versions
        
        Returns:
            dict: {
                "TCS": {
                    "document_count": 5,
                    "projects": {
                        "E-commerce": {
                            "POC": ["v1", "v2"],
                            "PROD": ["v1"]
                        }
                    }
                }
            }
        """
        try:
            print(f"\n📊 Getting companies grouped by projects and versions...")
            
            # Get all documents
            response = self.table.scan(Limit=limit)
            items = response.get('Items', [])
            while response.get('LastEvaluatedKey') and len(items) < limit:
                response = self.table.scan(
                    Limit=limit - len(items),
                    ExclusiveStartKey=response['LastEvaluatedKey'],
                )
                items.extend(response.get('Items', []))
            
            # Continue scanning if there's more data
            while 'LastEvaluatedKey' in response and len(items) < limit:
                response = self.table.scan(
                    ExclusiveStartKey=response['LastEvaluatedKey'],
                    Limit=limit - len(items)
                )
                items.extend(response.get('Items', []))

            print(f"   📄 Processing {len(items)} documents...")
            if owner_email:
                owner_email = str(owner_email).casefold().strip()
                items = [
                    item for item in items
                    if str(item.get('owner_email', '')).casefold().strip() == owner_email
                ]
            elif business_unit:
                items = [item for item in items if item.get('business_unit') == business_unit]

            # Group by company -> project -> mode -> versions
            grouped = {}
            
            for item in items:
                company = item.get('customer_name', 'Unknown')
                project = item.get('project_name', 'Unknown Project')
                mode = item.get('mode', 'UNKNOWN')
                version = item.get('version', 'v1')
                
                # Initialize company if not exists
                if company not in grouped:
                    grouped[company] = {
                        'company_name': company,
                        'document_count': 0,
                        'projects': {}
                    }
                
                # Initialize project if not exists
                if project not in grouped[company]['projects']:
                    grouped[company]['projects'][project] = {
                        'project_name': project,
                        'POC': [],
                        'PROD': [],
                        'POC_TO_PROD': []
                    }
                
                # Add version to the appropriate mode
                mode_versions = grouped[company]['projects'][project][mode]
                if isinstance(mode_versions, list):
                    # Upgrade legacy in-memory shape to the documented
                    # version -> document list response used by the dashboard.
                    mode_versions = {}
                    grouped[company]['projects'][project][mode] = mode_versions
                mode_versions.setdefault(version, []).append(item)
                
                # Increment document count
                grouped[company]['document_count'] += 1

            # Sort versions for each project/mode
            for company in grouped.values():
                for project in company['projects'].values():
                    for mode in ['POC', 'PROD', 'POC_TO_PROD']:
                        if project[mode]:
                            project[mode] = dict(sorted(
                                project[mode].items(),
                                key=lambda entry: int(entry[0][1:]) if entry[0][1:].isdigit() else 0,
                            ))

            print(f"   ✓ Grouped into {len(grouped)} companies")
            
            return grouped

        except Exception as e:
            print(f"❌ Grouping failed: {e}")
            import traceback
            traceback.print_exc()
            return {}

    def get_company_documents(self, company_name: str, project_name: str = None,
                             mode: str = None, version: str = None, limit=100,
                             business_unit=None, owner_email=None):
        """
        ✅ NEW: Get documents for a company with optional filters
        
        Args:
            company_name: Company name (required)
            project_name: Filter by project (optional)
            mode: Filter by mode (optional)
            version: Filter by version (optional)
            limit: Max results
            
        Returns:
            dict: Matching documents grouped by project, mode, and version
        """
        try:
            company_name_lower = company_name.lower().strip()
            
            print(f"\n🔍 Querying company documents...")
            print(f"   Company: {company_name}")
            if project_name:
                print(f"   Project: {project_name}")
            if mode:
                print(f"   Mode: {mode}")
            if version:
                print(f"   Version: {version}")

            # Query using customer-index GSI
            try:
                query_kwargs = dict(
                    IndexName='customer-index',
                    KeyConditionExpression='customer_name_lower = :cn',
                    ExpressionAttributeValues={
                        ':cn': company_name_lower
                    },
                    Limit=limit,
                    ScanIndexForward=False
                )
                response = self.table.query(**query_kwargs)
                items = response.get('Items', [])
                while response.get('LastEvaluatedKey') and len(items) < limit:
                    response = self.table.query(**{
                        **query_kwargs,
                        'ExclusiveStartKey': response['LastEvaluatedKey'],
                        'Limit': limit - len(items),
                    })
                    items.extend(response.get('Items', []))
                
            except ClientError as e:
                # Fallback to scan
                print(f"   ⚠️  Using scan fallback...")
                scan_kwargs = dict(
                    FilterExpression='customer_name_lower = :cn',
                    ExpressionAttributeValues={':cn': company_name_lower},
                    Limit=limit
                )
                response = self.table.scan(**scan_kwargs)
                items = response.get('Items', [])
                while response.get('LastEvaluatedKey') and len(items) < limit:
                    response = self.table.scan(**{
                        **scan_kwargs,
                        'ExclusiveStartKey': response['LastEvaluatedKey'],
                        'Limit': limit - len(items),
                    })
                    items.extend(response.get('Items', []))

            # Apply filters
            filtered_items = sorted(
                items,
                key=lambda item: str(item.get('timestamp') or item.get('created_at') or ''),
                reverse=True,
            )
            if owner_email:
                owner_email = str(owner_email).casefold().strip()
                filtered_items = [
                    item for item in filtered_items
                    if str(item.get('owner_email', '')).casefold().strip() == owner_email
                ]
            elif business_unit:
                filtered_items = [
                    item for item in filtered_items
                    if item.get('business_unit') == business_unit
                ]
            
            if project_name:
                project_name_lower = project_name.lower().strip()
                filtered_items = [
                    item for item in filtered_items 
                    if item.get('project_name_lower') == project_name_lower
                ]
            
            if mode:
                mode_upper = mode.upper()
                filtered_items = [
                    item for item in filtered_items 
                    if item.get('mode') == mode_upper
                ]
            
            if version:
                filtered_items = [
                    item for item in filtered_items 
                    if item.get('version') == version
                ]

            print(f"   ✓ Found {len(filtered_items)} documents")

            # Group by project -> mode -> version
            grouped_docs = {}
            
            for item in filtered_items:
                project = item.get('project_name', 'Unknown Project')
                doc_mode = item.get('mode', 'UNKNOWN')
                doc_version = item.get('version', 'v1')
                
                if project not in grouped_docs:
                    grouped_docs[project] = {}
                
                if doc_mode not in grouped_docs[project]:
                    grouped_docs[project][doc_mode] = {}
                
                if doc_version not in grouped_docs[project][doc_mode]:
                    grouped_docs[project][doc_mode][doc_version] = []
                
                grouped_docs[project][doc_mode][doc_version].append(item)

            return {
                'company_name': company_name,
                'total_documents': len(filtered_items),
                'projects': grouped_docs,
                'filters_applied': {
                    'project': project_name,
                    'mode': mode,
                    'version': version
                }
            }

        except Exception as e:
            print(f"❌ Query failed: {e}")
            import traceback
            traceback.print_exc()
            return {
                'company_name': company_name,
                'total_documents': 0,
                'projects': {},
                'error': str(e)
            }

    # ============================================================
    # EXISTING QUERY METHODS (UNCHANGED)
    # ============================================================

    def query_by_task_id(self, task_id):
        """Query document by task_id using GSI"""
        try:
            print(f"\n🔍 Querying by task_id: '{task_id}' (using task-index GSI)")
            try:
                response = self.table.query(
                    IndexName='task-index',
                    KeyConditionExpression='task_id = :tid',
                    ExpressionAttributeValues={':tid': task_id},
                    Limit=1
                )
                items = response.get('Items', [])
                if items:
                    print(f"✓ Found document for task_id: {task_id}")
                    return items[0]
                else:
                    print(f"⚠️  No document found for task_id: {task_id}")
                    return None
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"⚠️  GSI 'task-index' not found - falling back to scan")
                    response = self.table.scan(
                        FilterExpression='task_id = :tid',
                        ExpressionAttributeValues={':tid': task_id},
                        Limit=1
                    )
                    items = response.get('Items', [])
                    return items[0] if items else None
                raise
        except Exception as e:
            print(f"❌ Query by task_id failed: {e}")
            return None

    def query_by_customer(self, customer_name, limit=100):
        """Query documents by customer using GSI"""
        try:
            customer_name_lower = customer_name.lower().strip()
            print(f"\n🔍 Querying customer: '{customer_name}' (using customer-index GSI)")
            try:
                response = self.table.query(
                    IndexName='customer-index',
                    KeyConditionExpression='customer_name_lower = :cn',
                    ExpressionAttributeValues={':cn': customer_name_lower},
                    Limit=limit,
                    ScanIndexForward=False
                )
                items = response.get('Items', [])
                print(f"✓ Found {len(items)} documents")
                return items
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"⚠️  GSI not found - falling back to scan")
                    response = self.table.scan(
                        FilterExpression='customer_name_lower = :cn',
                        ExpressionAttributeValues={':cn': customer_name_lower},
                        Limit=limit
                    )
                    return response.get('Items', [])
                raise
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []

    def query_by_author(self, author_name, limit=100):
        """Query documents by author using GSI"""
        try:
            author_name_lower = author_name.lower().strip()
            print(f"\n🔍 Querying author: '{author_name}' (using author-index GSI)")
            try:
                response = self.table.query(
                    IndexName='author-index',
                    KeyConditionExpression='author_name_lower = :an',
                    ExpressionAttributeValues={':an': author_name_lower},
                    Limit=limit,
                    ScanIndexForward=False
                )
                items = response.get('Items', [])
                print(f"✓ Found {len(items)} documents")
                return items
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"⚠️  GSI not found - falling back to scan")
                    response = self.table.scan(
                        FilterExpression='author_name_lower = :an',
                        ExpressionAttributeValues={':an': author_name_lower},
                        Limit=limit
                    )
                    return response.get('Items', [])
                raise
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []

    def query_by_project(self, project_name, limit=100):
        """Query documents by project using GSI"""
        try:
            project_name_lower = project_name.lower().strip()
            print(f"\n🔍 Querying project: '{project_name}' (using project-index GSI)")
            try:
                response = self.table.query(
                    IndexName='project-index',
                    KeyConditionExpression='project_name_lower = :pn',
                    ExpressionAttributeValues={':pn': project_name_lower},
                    Limit=limit,
                    ScanIndexForward=False
                )
                items = response.get('Items', [])
                print(f"✓ Found {len(items)} documents")
                return items
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"⚠️  GSI not found - falling back to scan")
                    response = self.table.scan(
                        FilterExpression='project_name_lower = :pn',
                        ExpressionAttributeValues={':pn': project_name_lower},
                        Limit=limit
                    )
                    return response.get('Items', [])
                raise
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []

    def query_by_mode(self, mode, limit=100):
        """Query documents by mode using GSI"""
        try:
            print(f"\n🔍 Querying mode: '{mode}' (using mode-index GSI)")
            try:
                response = self.table.query(
                    IndexName='mode-index',
                    KeyConditionExpression='#mode = :m',
                    ExpressionAttributeNames={'#mode': 'mode'},
                    ExpressionAttributeValues={':m': mode.upper()},
                    Limit=limit,
                    ScanIndexForward=False
                )
                items = response.get('Items', [])
                print(f"✓ Found {len(items)} documents")
                return items
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"⚠️  GSI not found - falling back to scan")
                    response = self.table.scan(
                        FilterExpression='#mode = :m',
                        ExpressionAttributeNames={'#mode': 'mode'},
                        ExpressionAttributeValues={':m': mode.upper()},
                        Limit=limit
                    )
                    return response.get('Items', [])
                raise
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []

    def list_all_documents(self, limit=100):
        """List all documents with version info"""
        try:
            print(f"\n📋 Listing documents (limit: {limit})")
            response = self.table.scan(Limit=limit)
            items = response.get('Items', [])

            formatted_items = []
            for item in items:
                formatted_items.append({
                    'document_id': item.get('document_id'),
                    'task_id': item.get('task_id'),
                    'customer_name': item.get('customer_name'),
                    'author_name': item.get('author_name'),
                    'project_name': item.get('project_name'),
                    'document_date': item.get('document_date'),
                    's3_url': item.get('s3_url'),
                    'drive_link': item.get('drive_link'),
                    'timestamp': item.get('timestamp'),
                    'mode': item.get('mode', 'UNKNOWN'),
                    'version': item.get('version', 'v1'),  # ✅ Include version
                    'business_unit': item.get('business_unit'),
                    'owner_email': item.get('owner_email'),
                    'owner_name': item.get('owner_name'),
                    'total_tokens': item.get('total_tokens'),
                    'token_usage': item.get('token_usage'),
                    'project_id': item.get('project_id'),
                    'account_id': item.get('account_id'),
                    'source_documents': item.get('source_documents', []),
                    'source_scope_id': item.get('source_scope_id'),
                    'parent_document_id': item.get('parent_document_id'),
                    'selected_sow_sections': item.get('selected_sow_sections'),
                })

            return sorted(
                formatted_items,
                key=lambda item: str(item.get('timestamp') or item.get('document_date') or ''),
                reverse=True,
            )
        except Exception as e:
            print(f"❌ List failed: {e}")
            return []

    def delete_document(self, document_id, timestamp):
        """Delete a document record"""
        try:
            self.table.delete_item(
                Key={
                    'document_id': document_id,
                    'timestamp': timestamp
                }
            )
            print(f"✓ Document deleted: {document_id}")
            return True
        except Exception as e:
            print(f"❌ Delete failed: {e}")
            return False


# ============================================================
# RAG SCHEMA HANDLER (Unchanged)
# ============================================================

class RAGSchemaHandlerOptimized:
    """Optimized handler for rag-schema table"""

    def __init__(self, table_name=None, region=None):
        self.table_name = table_name or os.getenv(
            'DYNAMODB_TABLE_RAG_SCHEMA', 'rag-schema'
        )
        self.region = region or os.getenv('AWS_REGION', 'us-east-1')
        # Explicitly use environment variables
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=self.region,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN')
        )
        self.table = self.dynamodb.Table(self.table_name)

    def query_by_client_and_mode(self, client_name, mode, limit=10):
        """Query by client and mode using GSI"""
        try:
            client_name_lower = client_name.lower().strip()
            print(f"\n🔍 Querying RAG schema: client='{client_name}', mode='{mode}'")
            try:
                response = self.table.query(
                    IndexName='client-project-mode-index',
                    KeyConditionExpression='client_name_lower = :cn AND #mode = :m',
                    ExpressionAttributeNames={'#mode': 'mode'},
                    ExpressionAttributeValues={
                        ':cn': client_name_lower,
                        ':m': mode.upper()
                    },
                    Limit=limit
                )
                items = response.get('Items', [])
                print(f"✓ Found {len(items)} schemas")
                return items
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"⚠️  GSI not found - falling back to scan")
                    response = self.table.scan(
                        FilterExpression='client_name_lower = :cn AND #mode = :m',
                        ExpressionAttributeNames={'#mode': 'mode'},
                        ExpressionAttributeValues={
                            ':cn': client_name_lower,
                            ':m': mode.upper()
                        },
                        Limit=limit
                    )
                    return response.get('Items', [])
                raise
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []

    def query_by_mode(self, mode, limit=100):
        """Query all schemas by mode using GSI"""
        try:
            print(f"\n🔍 Querying RAG schemas by mode: '{mode}'")
            try:
                response = self.table.query(
                    IndexName='mode-index',
                    KeyConditionExpression='#mode = :m',
                    ExpressionAttributeNames={'#mode': 'mode'},
                    ExpressionAttributeValues={':m': mode.upper()},
                    Limit=limit,
                    ScanIndexForward=False
                )
                items = response.get('Items', [])
                print(f"✓ Found {len(items)} schemas")
                return items
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    print(f"⚠️  GSI not found - falling back to scan")
                    response = self.table.scan(
                        FilterExpression='#mode = :m',
                        ExpressionAttributeNames={'#mode': 'mode'},
                        ExpressionAttributeValues={':m': mode.upper()},
                        Limit=limit
                    )
                    return response.get('Items', [])
                raise
        except Exception as e:
            print(f"❌ Query failed: {e}")
            return []


# ============================================================
# Convenience Functions
# ============================================================

def save_to_dynamodb_optimized(metadata, s3_url, s3_result=None, drive_link=None,
                               table_name=None, region=None,
                               keep_duplicates=2, task_id=None, auto_version=True,
                               account_id=None, project_id=None):
    """
    ✅ ENHANCED: Save function with auto-versioning per project + mode

    Args:
        metadata: Document metadata dict
        s3_url: S3 URL of document
        s3_result: S3 upload result
        drive_link: Google Drive link (optional)
        table_name: DynamoDB table name
        region: AWS region
        keep_duplicates: Number of similar docs to keep
        task_id: Task/Job ID (optional)
        auto_version: Auto-calculate version (default: True)
        account_id: Account ID from agentic-sow-v2 (optional)
        project_id: Project ID from agentic-sow-v2 (optional)
    """
    try:
        handler = DynamoDBHandlerOptimized(table_name=table_name, region=region)
        result = handler.save_document_metadata(
            metadata, 
            s3_url, 
            s3_result, 
            drive_link=drive_link,
            keep_duplicates=keep_duplicates, 
            task_id=task_id,
            auto_version=auto_version,  # ✅ Pass through auto_version
            account_id=account_id,  # ✅ NEW: Pass account_id
            project_id=project_id  # ✅ NEW: Pass project_id
        )
        return result
    except Exception as e:
        print(f"❌ Save failed: {e}")
        return {"success": False, "error": str(e)}
