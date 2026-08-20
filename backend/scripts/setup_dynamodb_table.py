"""Provision the AWS storage resources required by the SOW generator.

All resource names and the AWS region come from backend/config/.env, so the
same code can be used with a sandbox account or a separate AWS account.
"""

import os
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")


def aws_client_kwargs():
    """Return the explicit credentials used by the application."""
    kwargs = {
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "aws_session_token": os.getenv("AWS_SESSION_TOKEN"),
    }
    return kwargs


def table_definitions():
    """Return DynamoDB definitions for all application tables."""
    accounts_table = os.getenv("DYNAMODB_TABLE_ACCOUNTS", "agentic-sow-v2")
    documents_table = os.getenv("DYNAMODB_TABLE_POC_DOCUMENTS", "agentic-poc")
    rag_table = os.getenv("DYNAMODB_TABLE_RAG_SCHEMA", "rag-schema")

    return [
        {
            "TableName": accounts_table,
            "KeySchema": [
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "segment", "AttributeType": "S"},
                {"AttributeName": "priority", "AttributeType": "S"},
                {"AttributeName": "account_name_lower", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "segment-created-index",
                    "KeySchema": [
                        {"AttributeName": "segment", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "priority-index",
                    "KeySchema": [
                        {"AttributeName": "priority", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "account-name-index",
                    "KeySchema": [
                        {"AttributeName": "account_name_lower", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        },
        {
            "TableName": documents_table,
            "KeySchema": [
                {"AttributeName": "document_id", "KeyType": "HASH"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "document_id", "AttributeType": "S"},
                {"AttributeName": "customer_name_lower", "AttributeType": "S"},
                {"AttributeName": "author_name_lower", "AttributeType": "S"},
                {"AttributeName": "project_name_lower", "AttributeType": "S"},
                {"AttributeName": "mode", "AttributeType": "S"},
                {"AttributeName": "task_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "customer-index",
                    "KeySchema": [
                        {"AttributeName": "customer_name_lower", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "author-index",
                    "KeySchema": [
                        {"AttributeName": "author_name_lower", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "project-index",
                    "KeySchema": [
                        {"AttributeName": "project_name_lower", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "mode-index",
                    "KeySchema": [
                        {"AttributeName": "mode", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "task-index",
                    "KeySchema": [
                        {"AttributeName": "task_id", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        },
        {
            "TableName": rag_table,
            "KeySchema": [
                {"AttributeName": "document_id", "KeyType": "HASH"},
            ],
            "AttributeDefinitions": [
                {"AttributeName": "document_id", "AttributeType": "S"},
                {"AttributeName": "client_name_lower", "AttributeType": "S"},
                {"AttributeName": "mode", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            "GlobalSecondaryIndexes": [
                {
                    "IndexName": "client-project-mode-index",
                    "KeySchema": [
                        {"AttributeName": "client_name_lower", "KeyType": "HASH"},
                        {"AttributeName": "mode", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "mode-index",
                    "KeySchema": [
                        {"AttributeName": "mode", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
        },
    ]


def create_tables():
    """Create any missing DynamoDB tables and wait until they are active."""
    region = os.getenv("AWS_REGION", "us-east-1")
    dynamodb = boto3.client(
        "dynamodb", region_name=region, **aws_client_kwargs()
    )

    for definition in table_definitions():
        table_name = definition["TableName"]
        try:
            response = dynamodb.describe_table(TableName=table_name)
            status = response["Table"]["TableStatus"]
            print(f"✅ DynamoDB table '{table_name}' already exists ({status})")
            continue
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "ResourceNotFoundException":
                raise

        print(f"📋 Creating DynamoDB table '{table_name}' in {region}...")
        dynamodb.create_table(
            **definition,
            BillingMode="PAY_PER_REQUEST",
            Tags=[
                {"Key": "Application", "Value": "SOW-Generator"},
                {"Key": "ManagedBy", "Value": "setup_dynamodb_table.py"},
            ],
        )
        dynamodb.get_waiter("table_exists").wait(
            TableName=table_name,
            WaiterConfig={"Delay": 5, "MaxAttempts": 25},
        )
        print(f"✅ DynamoDB table '{table_name}' is ACTIVE")


def create_s3_bucket():
    """Create or validate the bucket used for generated documents."""
    region = os.getenv("AWS_REGION", "us-east-1")
    bucket_name = os.getenv("S3_BUCKET_NAME", "agentic-sow-files")
    s3 = boto3.client("s3", region_name=region, **aws_client_kwargs())

    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"✅ S3 bucket '{bucket_name}' is accessible")
        return
    except ClientError as exc:
        code = str(exc.response.get("Error", {}).get("Code", ""))
        if code in {"403", "AccessDenied"}:
            raise RuntimeError(
                f"S3 bucket '{bucket_name}' belongs to another account or is not "
                "accessible. Set S3_BUCKET_NAME to a globally unique bucket name "
                "for the current account."
            ) from exc
        if code not in {"404", "NoSuchBucket", "NotFound"}:
            raise

    create_args = {"Bucket": bucket_name}
    if region != "us-east-1":
        create_args["CreateBucketConfiguration"] = {
            "LocationConstraint": region
        }
    s3.create_bucket(**create_args)
    s3.put_public_access_block(
        Bucket=bucket_name,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    print(f"✅ S3 bucket '{bucket_name}' created in {region}")


def seed_sample_data():
    """Optionally seed a single account for a smoke test."""
    from app.api.account_handler import AccountHandler

    AccountHandler().create_account(
        account_name="Example Account",
        segment="Others",
        priority="P3",
        metadata={"purpose": "SOW Generator smoke test"},
    )
    print("✅ Seeded Example Account")


def main():
    region = os.getenv("AWS_REGION", "us-east-1")
    print("=" * 70)
    print(f"SOW Generator AWS Resource Setup ({region})")
    print("=" * 70)

    create_tables()
    create_s3_bucket()

    response = input("Do you want to seed a sample account? (y/n): ")
    if response.lower() in {"y", "yes"}:
        seed_sample_data()

    print("\n✅ AWS resource setup complete")


if __name__ == "__main__":
    main()
