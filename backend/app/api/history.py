"""
View document history from DynamoDB
Filter by: Customer, Author, Project, or All Documents
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

_backend_root = str(Path(__file__).resolve().parents[2])
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from app.db.dynamodb_handler_optimized import DynamoDBHandlerOptimized as DynamoDBHandler

load_dotenv(Path(__file__).resolve().parents[2] / "config" / ".env")

def view_history():
    """View document history with filtering options"""
    try:
        print("\n" + "="*60)
        print("📋 Document History Viewer")
        print("="*60)
        
        # Initialize DynamoDB handler
        handler = DynamoDBHandler()
        
        # Show filter options
        print("\n📌 Filter Options:")
        print("1. Filter by Customer Name")
        print("2. Filter by Author Name")
        print("3. Filter by Project Name")
        print("4. View All Documents")
        print("5. Back to Main Menu")
        
        choice = input("\n📌 Select filter option (1-5): ").strip()
        
        if choice == "1":
            # Filter by Customer
            print("\n" + "-"*60)
            customer_name = input("Enter Customer Name: ").strip()
            
            if not customer_name:
                print("❌ Error: Customer name cannot be empty")
                return
            
            print(f"\n⏳ Searching DynamoDB for customer '{customer_name}'...")
            results = handler.query_by_customer(customer_name)
            
            if results:
                print(f"\n✅ Results for customer '{customer_name}':")
                print(f"✅ Found {len(results)} document(s):\n")
            else:
                print(f"\n📭 No documents found for customer: {customer_name}")
        
        elif choice == "2":
            # Filter by Author
            print("\n" + "-"*60)
            author_name = input("Enter Author Name: ").strip()
            
            if not author_name:
                print("❌ Error: Author name cannot be empty")
                return
            
            print(f"\n⏳ Searching DynamoDB for author '{author_name}'...")
            results = handler.query_by_author(author_name)
            
            if results:
                print(f"\n✅ Results for author '{author_name}':")
                print(f"✅ Found {len(results)} document(s):\n")
            else:
                print(f"\n📭 No documents found for author: {author_name}")
        
        elif choice == "3":
            # Filter by Project
            print("\n" + "-"*60)
            project_name = input("Enter Project Name: ").strip()
            
            if not project_name:
                print("❌ Error: Project name cannot be empty")
                return
            
            print(f"\n⏳ Searching DynamoDB for project '{project_name}'...")
            results = handler.query_by_project(project_name)
            
            if results:
                print(f"\n✅ Results for project '{project_name}':")
                print(f"✅ Found {len(results)} document(s):\n")
            else:
                print(f"\n📭 No documents found for project: {project_name}")
        
        elif choice == "4":
            # View all documents
            print("\n" + "-"*60)
            print("\n⏳ Fetching all documents from DynamoDB...")
            results = handler.list_all_documents(limit=100)
            
            if results:
                print(f"\n✅ All Documents:")
                print(f"✅ Found {len(results)} document(s):\n")
            else:
                print(f"\n📭 No documents found in database")
        
        elif choice == "5":
            print("\n👈 Returning to main menu...")
            return
        
        else:
            print("❌ Invalid choice. Please select 1-5.")
            return
        
        # Display detailed information if results found
        if results:
            print("\n" + "="*160)
            print("📄 Detailed Document Information:")
            print("="*160)
            
            for idx, doc in enumerate(results, 1):
                print(f"\n📌 Document {idx}:")
                print(f"   Document ID: {doc.get('document_id', 'N/A')}")
                print(f"   Customer: {doc.get('customer_name', 'N/A')}")
                print(f"   Author: {doc.get('author_name', 'N/A')}")
                print(f"   Project: {doc.get('project_name', 'N/A')}")
                print(f"   Date: {doc.get('document_date', 'N/A')}")
                print(f"   Timestamp: {doc.get('timestamp', 'N/A')}")
                
                s3_url = doc.get('s3_url', 'N/A')
                if s3_url and s3_url != 'N/A':
                    print(f"   S3 Link: {s3_url[:100]}...")
                else:
                    print(f"   S3 Link: N/A")
            
            print("\n" + "="*160)
        
        # Show summary
        print("\n" + "="*60)
        print("📊 Summary:")
        print("="*60)
        if results:
            print(f"✅ Total documents found: {len(results)}")
        else:
            print(f"📭 No documents match your search criteria")
        print("="*60)
            
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    view_history()
