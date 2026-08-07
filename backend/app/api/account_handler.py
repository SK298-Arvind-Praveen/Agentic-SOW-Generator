"""
Account Management Handler for SOW Generator
Handles account and project operations in DynamoDB (agentic-sow-v2 table)

STRUCTURE:
- Accounts: Customer accounts with metadata
- Projects: Projects within accounts
- SOWs: Linked to specific projects

DynamoDB Schema:
- Table: agentic-sow-v2
- Partition Key: PK (String)
- Sort Key: SK (String)

Access Patterns:
1. Get all accounts: PK = "ACCOUNT#", SK begins_with "ACCOUNT#"
2. Get account by ID: PK = "ACCOUNT#{account_id}", SK = "METADATA"
3. Get projects for account: PK = "ACCOUNT#{account_id}", SK begins_with "PROJECT#"
4. Get project by ID: PK = "PROJECT#{project_id}", SK = "METADATA"
5. Get SOWs for project: PK = "PROJECT#{project_id}", SK begins_with "SOW#"

GSIs Required:
1. GSI1: segment-created-index
   - PK: segment (String)
   - SK: created_at (String)
2. GSI2: priority-index
   - PK: priority (String)
   - SK: created_at (String)
3. GSI3: account-name-index
   - PK: account_name_lower (String)
   - SK: created_at (String)
"""

import boto3
import os
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any
from botocore.exceptions import ClientError
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")


class AccountHandler:
    """Handles account and project management in DynamoDB"""

    def __init__(self, table_name="agentic-sow-v2", region="us-east-1"):
        """Initialize DynamoDB handler"""
        self.table_name = table_name
        self.region = region

        # Initialize DynamoDB client with credentials from environment
        self.dynamodb = boto3.resource(
            'dynamodb',
            region_name=region,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN')
        )

        self.table = self.dynamodb.Table(table_name)
        print(f"✅ AccountHandler initialized with table: {table_name}")

    # ========================================================================
    # ACCOUNT OPERATIONS
    # ========================================================================

    def create_account(
        self,
        account_name: str,
        segment: str = "Others",
        priority: str = "P3",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new customer account

        Args:
            account_name: Name of the customer account
            segment: Business segment (Enterprise, Startup, Others)
            priority: Priority level (P1, P2, P3)
            metadata: Additional account metadata

        Returns:
            Created account data
        """
        account_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        account_data = {
            'PK': f'ACCOUNT#{account_id}',
            'SK': 'METADATA',
            'account_id': account_id,
            'account_name': account_name,
            'account_name_lower': account_name.lower(),
            'segment': segment,
            'priority': priority,
            'project_count': 0,
            'sow_count': 0,
            'demo_count': 0,
            'created_at': timestamp,
            'updated_at': timestamp,
            'status': 'active',
            'metadata': metadata or {}
        }

        try:
            self.table.put_item(Item=account_data)
            print(f"✅ Created account: {account_name} (ID: {account_id})")
            return account_data
        except ClientError as e:
            print(f"❌ Error creating account: {e}")
            raise

    def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        """Get account by ID"""
        try:
            response = self.table.get_item(
                Key={
                    'PK': f'ACCOUNT#{account_id}',
                    'SK': 'METADATA'
                }
            )
            return response.get('Item')
        except ClientError as e:
            print(f"❌ Error getting account: {e}")
            return None

    def list_accounts(
        self,
        segment: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        List all accounts with optional filters

        Args:
            segment: Filter by segment
            priority: Filter by priority
            limit: Maximum number of accounts to return

        Returns:
            List of accounts
        """
        try:
            # If filtering by segment, use GSI
            if segment:
                response = self.table.query(
                    IndexName='segment-created-index',
                    KeyConditionExpression='segment = :seg',
                    ExpressionAttributeValues={':seg': segment},
                    Limit=limit,
                    ScanIndexForward=False  # Most recent first
                )
            # If filtering by priority, use GSI
            elif priority:
                response = self.table.query(
                    IndexName='priority-index',
                    KeyConditionExpression='priority = :pri',
                    ExpressionAttributeValues={':pri': priority},
                    Limit=limit,
                    ScanIndexForward=False
                )
            # Otherwise, scan for all accounts
            else:
                response = self.table.scan(
                    FilterExpression='begins_with(PK, :pk) AND SK = :sk',
                    ExpressionAttributeValues={
                        ':pk': 'ACCOUNT#',
                        ':sk': 'METADATA'
                    },
                    Limit=limit
                )

            accounts = response.get('Items', [])
            print(f"✅ Retrieved {len(accounts)} accounts")
            return accounts
        except ClientError as e:
            print(f"❌ Error listing accounts: {e}")
            return []

    def update_account(
        self,
        account_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update account fields"""
        try:
            # Build update expression
            update_expr = "SET updated_at = :updated"
            expr_values = {':updated': datetime.now().isoformat()}

            for key, value in updates.items():
                if key not in ['PK', 'SK', 'account_id', 'created_at']:
                    update_expr += f", {key} = :{key}"
                    expr_values[f':{key}'] = value

            response = self.table.update_item(
                Key={
                    'PK': f'ACCOUNT#{account_id}',
                    'SK': 'METADATA'
                },
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ReturnValues='ALL_NEW'
            )

            print(f"✅ Updated account: {account_id}")
            return response.get('Attributes')
        except ClientError as e:
            print(f"❌ Error updating account: {e}")
            return None

    def delete_account(self, account_id: str) -> bool:
        """
        Delete an account (HARD DELETE - permanently removes from database)
        Also deletes all associated projects and SOWs
        """
        try:
            # 1. Get all projects for this account
            projects = self.list_projects_for_account(account_id, limit=1000)

            # 2. Delete all projects (which will delete their SOWs)
            for project in projects:
                project_id = project.get('project_id')
                if project_id:
                    self.delete_project(project_id)

            # 3. Delete the account metadata record
            self.table.delete_item(
                Key={
                    'PK': f'ACCOUNT#{account_id}',
                    'SK': 'METADATA'
                }
            )

            print(f"✅ Permanently deleted account: {account_id}")
            return True
        except ClientError as e:
            print(f"❌ Error deleting account: {e}")
            return False

    def get_account_statistics(self) -> Dict[str, Any]:
        """Get account statistics for dashboard"""
        try:
            accounts = self.list_accounts(limit=1000)

            total = len(accounts)
            with_projects = sum(1 for a in accounts if a.get('project_count', 0) > 0)
            without_projects = total - with_projects

            # Count by segment
            segments = {}
            for account in accounts:
                seg = account.get('segment', 'Others')
                segments[seg] = segments.get(seg, 0) + 1

            # Count by priority
            priorities = {}
            for account in accounts:
                pri = account.get('priority', 'P3')
                priorities[pri] = priorities.get(pri, 0) + 1

            return {
                'total': total,
                'with_projects': with_projects,
                'without_projects': without_projects,
                'by_segment': segments,
                'by_priority': priorities
            }
        except Exception as e:
            print(f"❌ Error getting statistics: {e}")
            return {
                'total': 0,
                'with_projects': 0,
                'without_projects': 0,
                'by_segment': {},
                'by_priority': {}
            }

    # ========================================================================
    # PROJECT OPERATIONS
    # ========================================================================

    def create_project(
        self,
        account_id: str,
        project_name: str,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new project within an account

        Args:
            account_id: Parent account ID
            project_name: Name of the project
            description: Project description
            metadata: Additional project metadata

        Returns:
            Created project data
        """
        project_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()

        project_data = {
            'PK': f'ACCOUNT#{account_id}',
            'SK': f'PROJECT#{project_id}',
            'project_id': project_id,
            'account_id': account_id,
            'project_name': project_name,
            'project_name_lower': project_name.lower(),
            'description': description,
            'sow_count': 0,
            'created_at': timestamp,
            'updated_at': timestamp,
            'status': 'active',
            'metadata': metadata or {}
        }

        # Also create a project metadata entry for direct access
        project_metadata = {
            **project_data,
            'PK': f'PROJECT#{project_id}',
            'SK': 'METADATA'
        }

        try:
            # Insert both entries
            self.table.put_item(Item=project_data)
            self.table.put_item(Item=project_metadata)

            # Increment project count on account
            self.table.update_item(
                Key={
                    'PK': f'ACCOUNT#{account_id}',
                    'SK': 'METADATA'
                },
                UpdateExpression='SET project_count = project_count + :inc, updated_at = :updated',
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':updated': timestamp
                }
            )

            print(f"✅ Created project: {project_name} (ID: {project_id}) in account: {account_id}")
            return project_data
        except ClientError as e:
            print(f"❌ Error creating project: {e}")
            raise

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get project by ID with enhanced debugging and account name"""
        try:
            from boto3.dynamodb.conditions import Attr

            print(f"🔍 Looking up project: {project_id}")
            
            # First try direct lookup via PROJECT# metadata entry
            print(f"   → Trying direct lookup: PK=PROJECT#{project_id}, SK=METADATA")
            response = self.table.get_item(
                Key={
                    'PK': f'PROJECT#{project_id}',
                    'SK': 'METADATA'
                }
            )

            project = None
            if 'Item' in response:
                print(f"   ✅ Found via direct lookup: {response['Item'].get('project_name')}")
                project = response['Item']
            else:
                # Fallback: Query using GSI or scan (for projects created before the fix)
                # This is less efficient but ensures backward compatibility
                print(f"   ⚠️  Project {project_id} not found via metadata, scanning...")
                response = self.table.scan(
                    FilterExpression=Attr('project_id').eq(project_id),
                    Limit=10  # Increased limit to see if there are multiple matches
                )

                items = response.get('Items', [])
                if items:
                    print(f"   ✅ Found {len(items)} item(s) via scan:")
                    for idx, item in enumerate(items):
                        print(f"      {idx+1}. {item.get('project_name')} (PK: {item.get('PK')}, SK: {item.get('SK')})")
                    project = items[0]
                else:
                    print(f"   ❌ Project {project_id} not found in database")
                    print(f"   💡 Tip: Check if project exists in account's project list")
                    return None
            
            # ✅ NEW: Fetch account name if project found
            if project:
                account_id = project.get('account_id')
                if account_id:
                    try:
                        account = self.get_account(account_id)
                        if account:
                            project['account_name'] = account.get('account_name', '')
                            print(f"   ✅ Added account name: {project['account_name']}")
                    except Exception as e:
                        print(f"   ⚠️  Could not fetch account name: {e}")
            
            return project
        except ClientError as e:
            print(f"❌ Error getting project: {e}")
            import traceback
            traceback.print_exc()
            return None

    def list_projects_for_account(
        self,
        account_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List all projects for an account with enhanced debugging"""
        try:
            print(f"🔍 Listing projects for account: {account_id}")
            response = self.table.query(
                KeyConditionExpression='PK = :pk AND begins_with(SK, :sk)',
                ExpressionAttributeValues={
                    ':pk': f'ACCOUNT#{account_id}',
                    ':sk': 'PROJECT#'
                },
                Limit=limit,
                ScanIndexForward=False  # Most recent first
            )

            projects = response.get('Items', [])
            print(f"✅ Retrieved {len(projects)} projects for account: {account_id}")

            if projects:
                print(f"   Projects found:")
                for idx, proj in enumerate(projects, 1):
                    print(f"      {idx}. {proj.get('project_name')} (ID: {proj.get('project_id')})")
            else:
                print(f"   ⚠️  No projects found for this account")

            return projects
        except ClientError as e:
            print(f"❌ Error listing projects: {e}")
            import traceback
            traceback.print_exc()
            return []

    def update_project(
        self,
        project_id: str,
        updates: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update project fields"""
        try:
            project = self.get_project(project_id)
            if not project:
                return None

            account_id = project.get('account_id')

            # Build update expression
            update_expr = "SET updated_at = :updated"
            expr_values = {':updated': datetime.now().isoformat()}

            for key, value in updates.items():
                if key not in ['PK', 'SK', 'project_id', 'account_id', 'created_at']:
                    update_expr += f", {key} = :{key}"
                    expr_values[f':{key}'] = value

            # Update both entries
            self.table.update_item(
                Key={
                    'PK': f'ACCOUNT#{account_id}',
                    'SK': f'PROJECT#{project_id}'
                },
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values
            )

            response = self.table.update_item(
                Key={
                    'PK': f'PROJECT#{project_id}',
                    'SK': 'METADATA'
                },
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ReturnValues='ALL_NEW'
            )

            print(f"✅ Updated project: {project_id}")
            return response.get('Attributes')
        except ClientError as e:
            print(f"❌ Error updating project: {e}")
            return None

    def delete_project(self, project_id: str) -> bool:
        """
        Delete a project (HARD DELETE - permanently removes from database)
        Also deletes all associated SOWs from DynamoDB, S3, and Google Drive
        """
        try:
            project = self.get_project(project_id)
            if not project:
                return False

            account_id = project.get('account_id')
            timestamp = datetime.now().isoformat()

            # 1. Get all SOWs for this project and delete them
            sows = self.list_sows_for_project(project_id, limit=1000)
            for sow in sows:
                sow_id = sow.get('sow_db_id') or sow.get('sow_id')
                if sow_id:
                    self.delete_sow(sow_id)

            # 2. Delete all project-related DynamoDB entries
            # Delete the ACCOUNT#xxx / PROJECT#xxx entry
            try:
                self.table.delete_item(
                    Key={
                        'PK': f'ACCOUNT#{account_id}',
                        'SK': f'PROJECT#{project_id}'
                    }
                )
            except Exception as e:
                print(f"⚠️  Could not delete project account link: {e}")

            # Delete the PROJECT#xxx / METADATA entry
            try:
                self.table.delete_item(
                    Key={
                        'PK': f'PROJECT#{project_id}',
                        'SK': 'METADATA'
                    }
                )
            except Exception as e:
                print(f"⚠️  Could not delete project metadata: {e}")

            # 3. Decrement project count on account (with safeguard)
            try:
                account_response = self.table.get_item(
                    Key={
                        'PK': f'ACCOUNT#{account_id}',
                        'SK': 'METADATA'
                    }
                )
                current_count = account_response.get('Item', {}).get('project_count', 0)

                if current_count > 0:
                    self.table.update_item(
                        Key={
                            'PK': f'ACCOUNT#{account_id}',
                            'SK': 'METADATA'
                        },
                        UpdateExpression='SET project_count = project_count - :dec, updated_at = :updated',
                        ExpressionAttributeValues={
                            ':dec': 1,
                            ':updated': timestamp
                        }
                    )
            except Exception as e:
                print(f"⚠️  Error updating account count: {e}")

            print(f"✅ Deleted project: {project_id}")
            return True
        except ClientError as e:
            print(f"❌ Error deleting project: {e}")
            return False

    # ========================================================================
    # SOW LINKING
    # ========================================================================

    def link_sow_to_project(
        self,
        project_id: str,
        sow_id: str,
        sow_data: Dict[str, Any]
    ) -> bool:
        """
        Link an SOW to a project

        Args:
            project_id: Target project ID
            sow_id: SOW identifier (from agentic-poc table)
            sow_data: SOW metadata

        Returns:
            Success status
        """
        try:
            project = self.get_project(project_id)
            if not project:
                print(f"❌ Project not found: {project_id}")
                return False

            account_id = project.get('account_id')
            timestamp = datetime.now().isoformat()

            # Create SOW link entry
            sow_link = {
                'PK': f'PROJECT#{project_id}',
                'SK': f'SOW#{sow_id}',
                'sow_id': sow_id,
                'project_id': project_id,
                'account_id': account_id,
                'linked_at': timestamp,
                **sow_data
            }

            self.table.put_item(Item=sow_link)

            # Increment SOW count on project (PROJECT#{project_id}#METADATA)
            self.table.update_item(
                Key={
                    'PK': f'PROJECT#{project_id}',
                    'SK': 'METADATA'
                },
                UpdateExpression='SET sow_count = sow_count + :inc, updated_at = :updated',
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':updated': timestamp
                }
            )

            # Increment SOW count on project entry under account (ACCOUNT#{account_id}#PROJECT#{project_id})
            self.table.update_item(
                Key={
                    'PK': f'ACCOUNT#{account_id}',
                    'SK': f'PROJECT#{project_id}'
                },
                UpdateExpression='SET sow_count = sow_count + :inc, updated_at = :updated',
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':updated': timestamp
                }
            )

            # Increment SOW count on account
            self.table.update_item(
                Key={
                    'PK': f'ACCOUNT#{account_id}',
                    'SK': 'METADATA'
                },
                UpdateExpression='SET sow_count = sow_count + :inc, updated_at = :updated',
                ExpressionAttributeValues={
                    ':inc': 1,
                    ':updated': timestamp
                }
            )

            print(f"✅ Linked SOW {sow_id} to project {project_id}")
            return True
        except ClientError as e:
            print(f"❌ Error linking SOW: {e}")
            return False

    def list_sows_for_project(
        self,
        project_id: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """List all SOWs for a project"""
        try:
            response = self.table.query(
                KeyConditionExpression='PK = :pk AND begins_with(SK, :sk)',
                ExpressionAttributeValues={
                    ':pk': f'PROJECT#{project_id}',
                    ':sk': 'SOW#'
                },
                Limit=limit,
                ScanIndexForward=False  # Most recent first
            )

            sows = response.get('Items', [])
            print(f"✅ Retrieved {len(sows)} SOWs for project: {project_id}")
            return sows
        except ClientError as e:
            print(f"❌ Error listing SOWs: {e}")
            return []

    def delete_sow(self, sow_id: str) -> bool:
        """
        Delete a SOW (HARD DELETE - permanently removes from DynamoDB, S3, and Google Drive)
        """
        try:
            from boto3.dynamodb.conditions import Key as DDBKey, Attr

            # 1. Find the SOW entry in agentic-sow-v2 using a query on the GSI or scan by sow_db_id.
            #    We query all SOW# items and filter — avoids full-table scan.
            response = self.table.scan(
                FilterExpression=Attr('SK').begins_with('SOW#') & (
                    Attr('sow_db_id').eq(sow_id) | Attr('sow_id').eq(sow_id)
                )
            )

            items = response.get('Items', [])
            if not items:
                print(f"⚠️  SOW {sow_id} not found in agentic-sow-v2")
                # Still try to delete from agentic-poc and S3
            else:
                sow = items[0]
                project_id = sow.get('PK', '').replace('PROJECT#', '')
                account_id = sow.get('account_id')
                timestamp = datetime.now().isoformat()

                # Delete the SOW link entry from agentic-sow-v2
                self.table.delete_item(
                    Key={
                        'PK': sow.get('PK'),
                        'SK': sow.get('SK')
                    }
                )
                print(f"✅ Deleted SOW from agentic-sow-v2: {sow_id}")

                # Decrement sow_count on PROJECT#/METADATA
                if project_id:
                    try:
                        self.table.update_item(
                            Key={
                                'PK': f'PROJECT#{project_id}',
                                'SK': 'METADATA'
                            },
                            UpdateExpression='SET sow_count = if_not_exists(sow_count, :zero) - :dec, updated_at = :updated',
                            ConditionExpression='sow_count > :zero',
                            ExpressionAttributeValues={
                                ':dec': 1,
                                ':zero': 0,
                                ':updated': timestamp
                            }
                        )
                    except Exception as e:
                        print(f"⚠️  Could not update project sow_count: {e}")

                    # Also decrement sow_count on ACCOUNT#/PROJECT# relationship item
                    if account_id:
                        try:
                            self.table.update_item(
                                Key={
                                    'PK': f'ACCOUNT#{account_id}',
                                    'SK': f'PROJECT#{project_id}'
                                },
                                UpdateExpression='SET sow_count = if_not_exists(sow_count, :zero) - :dec, updated_at = :updated',
                                ConditionExpression='sow_count > :zero',
                                ExpressionAttributeValues={
                                    ':dec': 1,
                                    ':zero': 0,
                                    ':updated': timestamp
                                }
                            )
                        except Exception as e:
                            print(f"⚠️  Could not update account/project sow_count: {e}")

                # Decrement sow_count on ACCOUNT#/METADATA
                if account_id:
                    try:
                        self.table.update_item(
                            Key={
                                'PK': f'ACCOUNT#{account_id}',
                                'SK': 'METADATA'
                            },
                            UpdateExpression='SET sow_count = if_not_exists(sow_count, :zero) - :dec, updated_at = :updated',
                            ConditionExpression='sow_count > :zero',
                            ExpressionAttributeValues={
                                ':dec': 1,
                                ':zero': 0,
                                ':updated': timestamp
                            }
                        )
                    except Exception as e:
                        print(f"⚠️  Could not update account sow_count: {e}")

            # 2. Delete from agentic-poc table (where actual SOW documents are stored)
            try:
                from app.db.dynamodb_handler_optimized import DynamoDBHandlerOptimized as DynamoDBHandler
                poc_handler = DynamoDBHandler()
                poc_response = poc_handler.table.get_item(
                    Key={'document_id': sow_id}
                )

                if 'Item' in poc_response:
                    poc_item = poc_response['Item']
                    s3_url = poc_item.get('s3_result', {}).get('s3_url', '')
                    drive_link = poc_item.get('drive_link', '')

                    # Delete from agentic-poc
                    poc_handler.table.delete_item(
                        Key={'document_id': sow_id}
                    )
                    print(f"✅ Deleted SOW from agentic-poc: {sow_id}")

                    # 3. Delete from S3
                    if s3_url:
                        try:
                            import boto3
                            s3_client = boto3.client(
                                's3',
                                region_name=os.getenv('AWS_REGION', 'us-east-1'),
                                aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
                                aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
                            )

                            # Extract bucket and key from S3 URL
                            # Format: https://bucket.s3.region.amazonaws.com/key or s3://bucket/key
                            if s3_url.startswith('s3://'):
                                parts = s3_url.replace('s3://', '').split('/', 1)
                                bucket = parts[0]
                                key = parts[1] if len(parts) > 1 else ''
                            else:
                                # Parse HTTPS URL
                                import re
                                match = re.search(r's3[.-]([^.]+)\.amazonaws\.com/(.+)', s3_url)
                                if match:
                                    bucket = os.getenv('S3_BUCKET_NAME', 'shellkode-sow-generator')
                                    key = match.group(2)
                                else:
                                    bucket = os.getenv('S3_BUCKET_NAME', 'shellkode-sow-generator')
                                    key = s3_url.split('/')[-1]

                            if bucket and key:
                                s3_client.delete_object(Bucket=bucket, Key=key)
                                print(f"✅ Deleted SOW from S3: s3://{bucket}/{key}")
                        except Exception as e:
                            print(f"⚠️  Could not delete from S3: {e}")

                    # 4. Delete from Google Drive (optional - requires Google API)
                    if drive_link:
                        print(f"⚠️  Google Drive file not deleted (manual deletion required): {drive_link}")
                        # Note: Implementing Google Drive deletion requires Google API credentials
                        # and additional setup. Skipping for now.

            except Exception as e:
                print(f"⚠️  Could not delete from agentic-poc or S3: {e}")

            print(f"✅ Permanently deleted SOW: {sow_id}")
            return True
        except ClientError as e:
            print(f"❌ Error deleting SOW: {e}")
            return False

    # ========================================================================
    # DRAFT MANAGEMENT (for preview/edit workflow)
    # ========================================================================

    def save_draft(
        self,
        project_id: str,
        draft_id: str,
        content: Dict[str, Any],
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Save a draft SOW (preview content) for later editing
        """
        try:
            timestamp = datetime.now().isoformat()

            draft_data = {
                'PK': f'PROJECT#{project_id}',
                'SK': f'DRAFT#{draft_id}',
                'draft_id': draft_id,
                'project_id': project_id,
                'content': content,
                'metadata': metadata,
                'status': 'draft',
                'created_at': timestamp,
                'updated_at': timestamp
            }

            self.table.put_item(Item=draft_data)
            print(f"✅ Saved draft: {draft_id} for project: {project_id}")
            return True
        except ClientError as e:
            print(f"❌ Error saving draft: {e}")
            return False

    def get_draft(self, project_id: str, draft_id: str) -> Optional[Dict[str, Any]]:
        """Get a draft SOW by ID"""
        try:
            response = self.table.get_item(
                Key={
                    'PK': f'PROJECT#{project_id}',
                    'SK': f'DRAFT#{draft_id}'
                }
            )
            return response.get('Item')
        except ClientError as e:
            print(f"❌ Error getting draft: {e}")
            return None

    def list_drafts_for_project(self, project_id: str) -> List[Dict[str, Any]]:
        """List all drafts for a project"""
        try:
            response = self.table.query(
                KeyConditionExpression='PK = :pk AND begins_with(SK, :sk)',
                ExpressionAttributeValues={
                    ':pk': f'PROJECT#{project_id}',
                    ':sk': 'DRAFT#'
                },
                ScanIndexForward=False  # Most recent first
            )
            drafts = response.get('Items', [])
            print(f"✅ Retrieved {len(drafts)} drafts for project: {project_id}")
            return drafts
        except ClientError as e:
            print(f"❌ Error listing drafts: {e}")
            return []

    def delete_draft(self, project_id: str, draft_id: str) -> bool:
        """Delete a draft"""
        try:
            self.table.delete_item(
                Key={
                    'PK': f'PROJECT#{project_id}',
                    'SK': f'DRAFT#{draft_id}'
                }
            )
            print(f"✅ Deleted draft: {draft_id}")
            return True
        except ClientError as e:
            print(f"❌ Error deleting draft: {e}")
            return False


# Convenience function for initialization
def get_account_handler() -> AccountHandler:
    """Get initialized account handler instance"""
    return AccountHandler()
