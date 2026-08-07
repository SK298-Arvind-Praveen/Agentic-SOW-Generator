"""
Script to retroactively link existing documents to projects
This fixes documents that were generated before the auto-linking feature was added
"""

import sys
import boto3
import os
from pathlib import Path
from dotenv import load_dotenv

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.api.account_handler import AccountHandler

load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")

def link_documents_to_project():
    """Link existing Allcargo documents to the project"""
    
    # Initialize handlers
    account_handler = AccountHandler()
    
    # Project details from the UI
    project_id = "27b73a1c-4ef2-43dd-8b4c-bb883f694ee4"
    company_name = "Allcargo"
    project_name = "Container Utilization and Demand Forecasting"
    
    # Document IDs from the agentic-poc table (from API response)
    documents = [
        {
            "sow_id": "DOC_20260515_182843_cde3932f",
            "version": "v4",
            "mode": "POC",
            "author_name": "Bakrudeen",
            "drive_link": "https://drive.google.com/file/d/19cDC6nB7eeLlaZOLJr7zQi8-73jS_w4l/view",
            "s3_url": "https://agentic-sow-files.s3.amazonaws.com/POC/2026-05-15_182810_POC_ewgzor2k.docx",
            "document_date": "15 May 2026",
            "timestamp": "2026-05-15T18:28:43.970745"
        },
        {
            "sow_id": "DOC_20260515_204040_3f8419db",
            "version": "v5",
            "mode": "POC",
            "author_name": "Bakrudeen",
            "drive_link": "https://drive.google.com/file/d/1loMcrcgysKsaZBuIyfB5R0fWYg-6umRu/view",
            "s3_url": "https://agentic-sow-files.s3.amazonaws.com/POC/2026-05-15_204024_POC_62sxt0xg.docx",
            "document_date": "15 May 2026",
            "timestamp": "2026-05-15T20:40:40.615591"
        },
        {
            "sow_id": "DOC_20260515_204110_ee6872b9",
            "version": "v6",
            "mode": "POC",
            "author_name": "Bakrudeen",
            "drive_link": "https://drive.google.com/file/d/1xCiOrqB4yZA8gVqAYvCS8GFHyKwrymru/view",
            "s3_url": "https://agentic-sow-files.s3.amazonaws.com/POC/2026-05-15_204056_POC_20ug6tq1.docx",
            "document_date": "15 May 2026",
            "timestamp": "2026-05-15T20:41:10.279783"
        }
    ]
    
    print(f"\n{'='*70}")
    print(f"🔗 Linking Existing Documents to Project")
    print(f"{'='*70}")
    print(f"Project ID: {project_id}")
    print(f"Company: {company_name}")
    print(f"Project: {project_name}")
    print(f"Documents to link: {len(documents)}")
    print()
    
    # Link each document
    success_count = 0
    for doc in documents:
        sow_id = doc["sow_id"]
        version = doc["version"]
        
        print(f"📄 Linking document {version} (ID: {sow_id})...")
        
        sow_data = {
            'mode': doc['mode'],
            'customer_name': company_name,
            'project_name': project_name,
            'author_name': doc['author_name'],
            'drive_link': doc['drive_link'],
            's3_url': doc['s3_url'],
            'sow_db_id': sow_id,
            'document_date': doc['document_date'],
            'created_at': doc['timestamp'],
            'version': version
        }
        
        try:
            result = account_handler.link_sow_to_project(project_id, sow_id, sow_data)
            if result:
                success_count += 1
                print(f"   ✅ Successfully linked {version}")
            else:
                print(f"   ❌ Failed to link {version}")
        except Exception as e:
            print(f"   ❌ Error linking {version}: {e}")
    
    print()
    print(f"{'='*70}")
    print(f"✅ Linking Complete: {success_count}/{len(documents)} documents linked")
    print(f"{'='*70}")
    print()
    
    # Verify the links
    print("🔍 Verifying links...")
    sows = account_handler.list_sows_for_project(project_id)
    print(f"✅ Project now has {len(sows)} linked SOW(s)")
    
    if sows:
        print("\n📋 Linked SOWs:")
        for idx, sow in enumerate(sows, 1):
            print(f"   {idx}. {sow.get('version', 'N/A')} - {sow.get('sow_id', 'N/A')}")

if __name__ == "__main__":
    link_documents_to_project()
