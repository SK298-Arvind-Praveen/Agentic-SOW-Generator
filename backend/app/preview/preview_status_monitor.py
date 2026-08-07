#!/usr/bin/env python3
"""
Real-time preview status monitor
Shows the 5-phase status progression in real-time
"""

import requests
import time
import json
from datetime import datetime

def monitor_preview_status(preview_id, base_url="http://localhost:5000"):
    """Monitor a preview's status in real-time"""
    
    status_url = f"{base_url}/api/preview/status/{preview_id}"
    
    print(f"🔍 Monitoring Preview: {preview_id}")
    print(f"📡 Status URL: {status_url}")
    print("=" * 80)
    
    seen_statuses = set()
    last_status = None
    start_time = datetime.now()
    
    while True:
        try:
            response = requests.get(status_url, timeout=5)
            
            if response.status_code != 200:
                print(f"❌ Status check failed: {response.status_code}")
                break
            
            data = response.json()
            current_status = data.get('status')
            progress = data.get('progress', 0)
            current_step = data.get('current_step', 'Unknown')
            
            # Only print when status changes
            if current_status != last_status:
                timestamp = datetime.now().strftime("%H:%M:%S")
                elapsed = (datetime.now() - start_time).total_seconds()
                
                # Status change indicator
                if current_status not in seen_statuses:
                    print(f"🔄 [{timestamp}] +{elapsed:.1f}s - NEW STATUS: {current_status.upper()}")
                    seen_statuses.add(current_status)
                else:
                    print(f"🔄 [{timestamp}] +{elapsed:.1f}s - Status: {current_status}")
                
                print(f"   📊 Progress: {progress}%")
                print(f"   📝 Step: {current_step}")
                
                # Show status progression
                status_order = ["initializing", "researching", "analyzing", "generating", "finalizing", "ready", "failed"]
                current_index = status_order.index(current_status) if current_status in status_order else -1
                
                if current_index >= 0:
                    progress_bar = ""
                    for i, status in enumerate(status_order[:6]):  # Exclude 'failed'
                        if i < current_index:
                            progress_bar += "✅ "
                        elif i == current_index:
                            progress_bar += "🔄 "
                        else:
                            progress_bar += "⏳ "
                    print(f"   🚀 Progress: {progress_bar}")
                
                print("-" * 80)
                last_status = current_status
            
            # Check if complete or failed
            if data.get('is_complete'):
                print(f"🎉 COMPLETED! Preview generation finished successfully")
                
                # Show final content info
                content = data.get('content', {})
                if isinstance(content, dict):
                    print(f"📄 Generated {len(content)} content sections")
                    if content:
                        print(f"📝 Sections: {', '.join(list(content.keys())[:5])}")
                
                print(f"⏱️  Total time: {(datetime.now() - start_time).total_seconds():.1f} seconds")
                break
                
            elif data.get('has_error'):
                error_msg = data.get('error', 'Unknown error')
                print(f"❌ FAILED! Error: {error_msg}")
                print(f"⏱️  Failed after: {(datetime.now() - start_time).total_seconds():.1f} seconds")
                break
            
            time.sleep(0.5)  # Poll every 500ms for real-time feel
            
        except KeyboardInterrupt:
            print(f"\n⏹️  Monitoring stopped by user")
            break
        except Exception as e:
            print(f"❌ Error monitoring status: {e}")
            time.sleep(1)

def start_preview_and_monitor():
    """Start a new preview and monitor it"""
    
    base_url = "http://localhost:5000"
    preview_url = f"{base_url}/api/preview"
    
    # Test data
    test_data = {
        'mode': 'POC',
        'company_name': 'Monitor Test Company',
        'author_name': 'Monitor Test Author', 
        'project_name': 'Monitor Test Project',
        'objective': 'Testing real-time status monitoring',
        'fast_mode': 'true'
    }
    
    print("🚀 Starting new preview for monitoring...")
    
    try:
        response = requests.post(preview_url, data=test_data, timeout=10)
        
        if response.status_code != 202:
            print(f"❌ Failed to start preview: {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        result = response.json()
        preview_id = result.get('preview_id')
        
        if not preview_id:
            print("❌ No preview_id received")
            return
        
        print(f"✅ Preview started: {preview_id}")
        print()
        
        # Start monitoring
        monitor_preview_status(preview_id, base_url)
        
    except Exception as e:
        print(f"❌ Error starting preview: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Monitor existing preview
        preview_id = sys.argv[1]
        monitor_preview_status(preview_id)
    else:
        # Start new preview and monitor
        start_preview_and_monitor()