"""
Setup script for agentic-sow-v2 DynamoDB table
Creates the table with proper schema and GSIs if it doesn't exist
"""

import boto3
import os
from pathlib import Path
from dotenv import load_dotenv
from botocore.exceptions import ClientError

load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")


def create_table():
    """Create the agentic-sow-v2 table with proper schema"""

    dynamodb = boto3.client(
        'dynamodb',
        region_name=os.getenv('AWS_REGION', 'us-east-1'),
        aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
        aws_session_token=os.getenv('AWS_SESSION_TOKEN')
    )

    table_name = 'agentic-sow-v2'

    try:
        # Check if table exists
        try:
            response = dynamodb.describe_table(TableName=table_name)
            print(f"✅ Table '{table_name}' already exists")
            print(f"   Status: {response['Table']['TableStatus']}")
            return
        except ClientError as e:
            if e.response['Error']['Code'] != 'ResourceNotFoundException':
                raise
            print(f"📋 Table '{table_name}' does not exist. Creating...")

        # Create table
        response = dynamodb.create_table(
            TableName=table_name,
            KeySchema=[
                {'AttributeName': 'PK', 'KeyType': 'HASH'},   # Partition key
                {'AttributeName': 'SK', 'KeyType': 'RANGE'}   # Sort key
            ],
            AttributeDefinitions=[
                {'AttributeName': 'PK', 'AttributeType': 'S'},
                {'AttributeName': 'SK', 'AttributeType': 'S'},
                {'AttributeName': 'segment', 'AttributeType': 'S'},
                {'AttributeName': 'priority', 'AttributeType': 'S'},
                {'AttributeName': 'account_name_lower', 'AttributeType': 'S'},
                {'AttributeName': 'created_at', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'segment-created-index',
                    'KeySchema': [
                        {'AttributeName': 'segment', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'priority-index',
                    'KeySchema': [
                        {'AttributeName': 'priority', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'account-name-index',
                    'KeySchema': [
                        {'AttributeName': 'account_name_lower', 'KeyType': 'HASH'},
                        {'AttributeName': 'created_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ],
            BillingMode='PROVISIONED',
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            },
            Tags=[
                {'Key': 'Application', 'Value': 'SOW-Generator'},
                {'Key': 'Environment', 'Value': 'Production'},
                {'Key': 'Version', 'Value': 'v2'}
            ]
        )

        print(f"✅ Table '{table_name}' creation initiated")
        print(f"   Status: {response['TableDescription']['TableStatus']}")
        print(f"\n⏳ Waiting for table to become active...")

        # Wait for table to be created
        waiter = dynamodb.get_waiter('table_exists')
        waiter.wait(
            TableName=table_name,
            WaiterConfig={'Delay': 5, 'MaxAttempts': 25}
        )

        print(f"✅ Table '{table_name}' is now ACTIVE")
        print(f"\n📊 Table Structure:")
        print(f"   Primary Key: PK (HASH), SK (RANGE)")
        print(f"   GSI 1: segment-created-index")
        print(f"   GSI 2: priority-index")
        print(f"   GSI 3: account-name-index")

    except ClientError as e:
        print(f"❌ Error creating table: {e}")
        raise
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise


def seed_sample_data():
    """Seed sample accounts for testing"""
    from app.api.account_handler import AccountHandler

    handler = AccountHandler()

    print(f"\n📝 Seeding sample data...")

    sample_accounts = [
        {
            'account_name': 'AU small finance bank',
            'segment': 'Enterprise',
            'priority': 'P1',
            'metadata': {'industry': 'Finance', 'size': 'Small'}
        },
        {
            'account_name': 'Aavas',
            'segment': 'Enterprise',
            'priority': 'P2',
            'metadata': {'industry': 'Housing Finance'}
        },
        {
            'account_name': 'Airman Aeronautics',
            'segment': 'Startup',
            'priority': 'P3',
            'metadata': {'industry': 'Aerospace'}
        },
        {
            'account_name': 'AllCargo',
            'segment': 'Enterprise',
            'priority': 'P2',
            'metadata': {'industry': 'Logistics'}
        },
        {
            'account_name': 'AltiusHub',
            'segment': 'Startup',
            'priority': 'P2',
            'metadata': {'industry': 'Technology'}
        },
        {
            'account_name': 'Ambak IDP',
            'segment': 'Others',
            'priority': 'P2',
            'metadata': {'industry': 'Technology'}
        },
        {
            'account_name': 'Apollo Tyres',
            'segment': 'Enterprise',
            'priority': 'P2',
            'metadata': {'industry': 'Manufacturing'}
        }
    ]

    created_count = 0
    for account_data in sample_accounts:
        try:
            handler.create_account(**account_data)
            created_count += 1
        except Exception as e:
            print(f"⚠️ Error creating account '{account_data['account_name']}': {e}")

    print(f"✅ Seeded {created_count}/{len(sample_accounts)} sample accounts")


def main():
    """Main setup function"""
    print("="*70)
    print("DynamoDB Table Setup - agentic-sow-v2")
    print("="*70)

    # Create table
    create_table()

    # Ask if user wants to seed sample data
    print("\n" + "="*70)
    response = input("Do you want to seed sample account data? (y/n): ")
    if response.lower() in ['y', 'yes']:
        seed_sample_data()

    print("\n" + "="*70)
    print("✅ Setup complete!")
    print("="*70)


if __name__ == '__main__':
    main()
