#!/usr/bin/env python3
"""
List all editable sections for a preview with enhanced information
"""

import requests
import json
from typing import Dict, List

def list_editable_sections(preview_id: str, base_url: str = "http://localhost:9000"):
    """Get and display all editable sections for a preview"""
    
    sections_url = f"{base_url}/api/preview/{preview_id}/sections"
    
    print(f"🔍 Editable Sections for Preview: {preview_id}")
    print("=" * 80)
    
    try:
        response = requests.get(sections_url)
        
        if response.status_code != 200:
            print(f"❌ Failed to get sections: {response.status_code}")
            if response.status_code == 404:
                print("   Preview not found or may have expired")
            else:
                print(f"   Response: {response.text}")
            return False
        
        data = response.json()
        
        if not data.get('success'):
            print(f"❌ API Error: {data.get('error', 'Unknown error')}")
            return False
        
        sections = data.get('sections', [])
        categories = data.get('sections_by_category', {})
        mode = data.get('mode', 'Unknown')
        
        print(f"📋 Document Mode: {mode}")
        print(f"📊 Total Sections: {len(sections)}")
        print(f"🏷️  Categories: {', '.join(categories.keys())}")
        
        # Display by category
        for category, cat_sections in categories.items():
            print(f"\n📁 {category.upper()} ({len(cat_sections)} sections)")
            print("-" * 60)
            
            for i, section in enumerate(cat_sections, 1):
                key = section.get('key', 'unknown')
                title = section.get('title', key.replace('_', ' ').title())
                preview = section.get('content_preview', 'No preview available')
                content_type = section.get('content_type', 'unknown')
                content_length = section.get('content_length', 0)
                
                print(f"{i:2d}. {title}")
                print(f"    🔑 Key: {key}")
                print(f"    📄 Type: {content_type} ({content_length} chars)")
                print(f"    👀 Preview: {preview}")
                print()
        
        # Show usage example
        usage = data.get('usage', {})
        example = usage.get('example', {})
        
        print("=" * 80)
        print("📝 HOW TO EDIT SECTIONS")
        print("=" * 80)
        
        print(f"API Endpoint: POST {base_url}/api/edit")
        print("Content-Type: application/json")
        print()
        print("Example Request Body:")
        print(json.dumps(example, indent=2))
        
        print("\n💡 Tips:")
        print("   • Use the 'key' field as the section identifier")
        print("   • You can select multiple sections in 'selected_sections' array")
        print("   • Be specific in your 'user_input' about what changes you want")
        
        # Show popular sections
        popular_sections = [s for s in sections if s.get('category') in ['financial', 'scope', 'technical']]
        if popular_sections:
            print(f"\n🔥 Most Commonly Edited Sections:")
            for section in popular_sections[:5]:
                print(f"   • {section.get('key')} - {section.get('title')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def quick_section_list(preview_id: str, base_url: str = "http://localhost:9000"):
    """Get a quick list of section keys only"""
    
    sections_url = f"{base_url}/api/preview/{preview_id}/sections"
    
    try:
        response = requests.get(sections_url)
        
        if response.status_code == 200:
            data = response.json()
            sections = data.get('sections', [])
            
            print(f"📋 Quick Section Keys for {preview_id}:")
            print("-" * 50)
            
            for i, section in enumerate(sections, 1):
                key = section.get('key', 'unknown')
                title = section.get('title', key.replace('_', ' ').title())
                category = section.get('category', 'other')
                
                print(f"{i:2d}. {key:<30} ({category}) - {title}")
            
            return [s.get('key') for s in sections]
        
        return []
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return []

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python list_editable_sections.py <preview_id>           # Detailed view")
        print("  python list_editable_sections.py <preview_id> --quick   # Quick keys only")
        print()
        print("Example:")
        print("  python list_editable_sections.py PREVIEW_20260209_001354_85de798d")
        sys.exit(1)
    
    preview_id = sys.argv[1]
    quick_mode = len(sys.argv) > 2 and sys.argv[2] == '--quick'
    
    if quick_mode:
        section_keys = quick_section_list(preview_id)
        if section_keys:
            print(f"\n✅ Found {len(section_keys)} editable sections")
        else:
            print("❌ No sections found or error occurred")
    else:
        success = list_editable_sections(preview_id)
        if success:
            print("\n✅ Section information retrieved successfully")
        else:
            print("\n❌ Failed to retrieve section information")