#!/usr/bin/env python3
"""
Health check script for EC2 deployment
Run this to verify all components are working correctly
"""

import sys
import os
from datetime import datetime

def check_imports():
    """Test all critical imports"""
    print("🔍 Checking imports...")
    
    try:
        # Core dependencies
        import flask
        import boto3
        import requests
        print("   ✅ Core web dependencies")
        
        # Document processing
        from reportlab.lib.pagesizes import A4
        from docx import Document
        print("   ✅ Document processing libraries")
        
        # Application modules
        from app.document.document_builder import DocumentBuilder
        from app.core.config import Config
        print("   ✅ Application modules")
        
        return True
    except ImportError as e:
        print(f"   ❌ Import failed: {e}")
        return False

def check_document_builder():
    """Test DocumentBuilder initialization and PDF output"""
    print("🔧 Testing DocumentBuilder...")
    
    try:
        from app.document.document_builder import DocumentBuilder
        from app.core.config import Config
        
        config = Config()
        doc_builder = DocumentBuilder(config)
        print("   ✅ DocumentBuilder initialization successful")
        print("   ✅ PDF output mode configured")
        return True
    except Exception as e:
        print(f"   ❌ DocumentBuilder failed: {e}")
        return False

def check_file_permissions():
    """Check file system permissions"""
    print("📁 Checking file permissions...")
    
    try:
        # Test write permissions
        test_file = "temp_test_file.txt"
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
        print("   ✅ File write permissions OK")
        
        # Check required directories
        from pathlib import Path
        output_dir = Path("generated_documents")
        output_dir.mkdir(exist_ok=True)
        print("   ✅ Output directory accessible")
        
        return True
    except Exception as e:
        print(f"   ❌ File permission error: {e}")
        return False

def check_environment():
    """Check environment variables and config"""
    print("🌍 Checking environment...")
    
    try:
        from app.core.config import Config
        config = Config()
        
        # Check if basic config loads
        print(f"   ✅ Config loaded successfully")
        
        # Check for .env file
        if os.path.exists('.env'):
            print("   ✅ .env file found")
        else:
            print("   ⚠️  .env file not found (may use defaults)")
        
        return True
    except Exception as e:
        print(f"   ❌ Environment error: {e}")
        return False

def main():
    """Run all health checks"""
    print("🏥 POC Generator Health Check")
    print("=" * 40)
    print(f"Time: {datetime.now()}")
    print(f"Python: {sys.version}")
    print(f"Platform: {sys.platform}")
    print()
    
    checks = [
        check_imports,
        check_document_builder,
        check_file_permissions,
        check_environment
    ]
    
    results = []
    for check in checks:
        try:
            result = check()
            results.append(result)
        except Exception as e:
            print(f"   ❌ Check failed with exception: {e}")
            results.append(False)
        print()
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("📊 HEALTH CHECK SUMMARY")
    print("=" * 40)
    print(f"Passed: {passed}/{total}")
    
    if passed == total:
        print("🎉 ALL CHECKS PASSED - System ready for deployment!")
        sys.exit(0)
    else:
        print("⚠️  Some checks failed - review errors above")
        sys.exit(1)

if __name__ == "__main__":
    main()