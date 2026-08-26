"""Backfill BU ownership on legacy SOW/account/project records.

The script is dry-run by default. Example:
  python scripts/backfill_business_units.py --business-unit GenAI --apply
"""

import argparse
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parents[1] / "config" / ".env")

BUSINESS_UNITS = {"GenAI", "Database Management", "Data Engineering", "Cloud", "MLOps"}


def scan_all(table):
    response = table.scan()
    items = response.get("Items", [])
    while response.get("LastEvaluatedKey"):
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        items.extend(response.get("Items", []))
    return items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--business-unit", required=True, choices=sorted(BUSINESS_UNITS))
    parser.add_argument("--apply", action="store_true", help="Write updates; otherwise only report")
    args = parser.parse_args()

    region = os.getenv("AWS_REGION", "us-east-1")
    resource = boto3.resource(
        "dynamodb",
        region_name=region,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        aws_session_token=os.getenv("AWS_SESSION_TOKEN"),
    )
    targets = [
        (resource.Table(os.getenv("DYNAMODB_TABLE_POC_DOCUMENTS", "agentic-poc")), ["document_id"]),
        (resource.Table(os.getenv("DYNAMODB_TABLE_ACCOUNTS", "agentic-sow-v2")), ["PK", "SK"]),
    ]

    total = 0
    for table, key_fields in targets:
        unassigned = [item for item in scan_all(table) if not item.get("business_unit")]
        print(f"{table.name}: {len(unassigned)} unassigned record(s)")
        total += len(unassigned)
        if args.apply:
            for item in unassigned:
                table.update_item(
                    Key={field: item[field] for field in key_fields},
                    UpdateExpression="SET business_unit = :bu",
                    ExpressionAttributeValues={":bu": args.business_unit},
                )
    print(f"{'Updated' if args.apply else 'Would update'} {total} record(s) to {args.business_unit}")


if __name__ == "__main__":
    main()
