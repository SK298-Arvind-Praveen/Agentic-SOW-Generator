"""
RAG Data Diagnostic Tool & STRICT Enhanced Retriever
Production-grade fuzzy logic with safety thresholds
"""

import json
import os
import boto3
from typing import Optional, Dict, List, Tuple
from difflib import SequenceMatcher
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")


# ============================================================
# Utility
# ============================================================

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ============================================================
# Diagnostic Tool
# ============================================================

class RAGDataDiagnostic:

    def __init__(self, table_name=None, region=None):
        from app.core.config import Config
        config = Config()
        
        table_name = table_name or config.DYNAMODB_TABLE_RAG
        region = region or config.DYNAMODB_REGION
        
        self.table = boto3.resource(
            'dynamodb', 
            region_name=region,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN')
        ).Table(table_name)

    def list_all_records(self) -> List[Dict]:
        print("\n" + "="*80)
        print("📊 ALL RECORDS IN RAG-SCHEMA")
        print("="*80)

        response = self.table.scan()
        items = response.get("Items", [])

        for i, item in enumerate(items, 1):
            print(f"{i}. {item.get('client_name')} | {item.get('project_title')} | {item.get('mode')}")

        return items

    def check_exact_match(self, company, project, mode):
        response = self.table.scan(
            FilterExpression='client_name = :c AND project_title = :p AND #m = :m',
            ExpressionAttributeNames={'#m': 'mode'},
            ExpressionAttributeValues={
                ':c': company,
                ':p': project,
                ':m': mode
            }
        )

        if response.get("Items"):
            return True, response["Items"][0]

        return False, None


# ============================================================
# STRICT ENHANCED RETRIEVER
# ============================================================

class EnhancedPOCRetriever:

    def __init__(self, table_name='rag-schema', region='us-east-1'):
        self.table = boto3.resource(
            'dynamodb', 
            region_name=region,
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            aws_session_token=os.getenv('AWS_SESSION_TOKEN')
        ).Table(table_name)
        self.diagnostic = RAGDataDiagnostic(table_name, region)

    def normalize_mode(self, mode: str) -> str:
        return {
            "poc": "POC",
            "prod": "PROD",
            "production": "PROD",
            "poc_to_prod": "POC_TO_PROD"
        }.get(mode.lower(), mode.upper())

    def retrieve_by_three_params(self, company_name, project_title, mode, use_fuzzy=True):

        normalized_mode = self.normalize_mode(mode)

        print("\n" + "="*80)
        print("🔍 STRICT RAG RETRIEVAL")
        print("="*80)
        print(f"Company: {company_name}")
        print(f"Project: {project_title}")
        print(f"Mode   : {normalized_mode}")

        # ===================================================
        # STRATEGY 1 — EXACT MATCH
        # ===================================================
        print("\n[1] EXACT MATCH")

        response = self.table.scan(
            FilterExpression='client_name = :c AND project_title = :p AND #m = :m',
            ExpressionAttributeNames={'#m': 'mode'},
            ExpressionAttributeValues={
                ':c': company_name,
                ':p': project_title,
                ':m': normalized_mode
            }
        )

        if response.get("Items"):
            print("✅ Exact match found")
            return json.loads(response["Items"][0]["full_schema"])

        print("❌ Exact match not found")

        if not use_fuzzy:
            return None

        # ===================================================
        # STRATEGY 2 — STRICT FUZZY
        # ===================================================
        print("\n[2] STRICT FUZZY MATCH")

        response = self.table.scan(
            FilterExpression='#m = :m',
            ExpressionAttributeNames={'#m': 'mode'},
            ExpressionAttributeValues={':m': normalized_mode}
        )

        best_item = None
        best_score = 0

        for item in response.get("Items", []):

            company_score = similarity(company_name, item.get("client_name",""))
            project_score = similarity(project_title, item.get("project_title",""))

            final_score = (company_score * 0.6) + (project_score * 0.4)

            print(f"""
Candidate:
  DB Company : {item.get("client_name")}
  DB Project : {item.get("project_title")}
  Company Score: {company_score:.2f}
  Project Score: {project_score:.2f}
  Final Score  : {final_score:.2f}
""")

            # HARD FILTER
            if company_score >= 0.85 and project_score >= 0.75 and final_score >= 0.80:
                if final_score > best_score:
                    best_score = final_score
                    best_item = item

        if best_item:
            print(f"✅ FUZZY MATCH ACCEPTED (Score {best_score:.2f})")
            return json.loads(best_item["full_schema"])

        print("❌ No fuzzy candidate passed quality gate")

        # ===================================================
        # FAILURE
        # ===================================================
        print("\n⚠️ NO RAG DATA FOUND")
        return None


# ============================================================
# Diagnostic CLI Helpers
# ============================================================

def diagnose_rag_issue(company, project, mode):

    diag = RAGDataDiagnostic()

    print("\n[STEP 1] Listing all records")
    records = diag.list_all_records()

    if not records:
        print("❌ Table empty")
        return

    print("\n[STEP 2] Exact match check")
    found, _ = diag.check_exact_match(company, project, mode)

    if found:
        print("✅ Exact match exists in DB")
        return

    print("\n[STEP 3] Fuzzy evaluation (manual review)")
    retriever = EnhancedPOCRetriever()
    retriever.retrieve_by_three_params(company, project, mode)


def test_enhanced_retriever(company, project, mode):

    retriever = EnhancedPOCRetriever()
    schema = retriever.retrieve_by_three_params(company, project, mode)

    if schema:
        print("\n✅ RETRIEVAL SUCCESS")
    else:
        print("\n❌ RETRIEVAL FAILED")


# ============================================================
# Main CLI
# ============================================================

if __name__ == "__main__":

    import sys

    print("\nRAG STRICT DIAGNOSTIC TOOL")

    if len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        company = input("Company: ")
        project = input("Project: ")
        mode = input("Mode: ")
        diagnose_rag_issue(company, project, mode)

    elif len(sys.argv) > 1 and sys.argv[1] == "test":
        company = input("Company: ")
        project = input("Project: ")
        mode = input("Mode: ")
        test_enhanced_retriever(company, project, mode)

    else:
        print("\nUsage:")
        print(" python rag_diagnostic.py diagnose")
        print(" python rag_diagnostic.py test")
