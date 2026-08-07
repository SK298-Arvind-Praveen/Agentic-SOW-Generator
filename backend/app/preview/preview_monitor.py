#!/usr/bin/env python3
"""
Preview Storage Monitor
Real-time monitoring of preview storage usage and health
"""

import requests
import time
import json
from datetime import datetime

def get_storage_stats(base_url="http://localhost:5000"):
    """Get storage statistics from the API"""
    try:
        response = requests.get(f"{base_url}/api/preview/storage/stats")
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"HTTP {response.status_code}: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

def format_storage_display(data):
    """Format storage data for display"""
    if "error" in data:
        return f"❌ Error: {data['error']}"
    
    stats = data.get("storage_stats", {})
    health = data.get("health_status", "unknown")
    warnings = data.get("warnings", [])
    config = data.get("configuration", {})
    
    # Health status emoji
    health_emoji = {
        "healthy": "✅",
        "warning": "⚠️",
        "critical": "🚨"
    }.get(health, "❓")
    
    output = []
    output.append(f"{health_emoji} Storage Health: {health.upper()}")
    output.append(f"📊 Previews: {stats.get('total_previews', 0)}/{stats.get('max_previews', 0)}")
    output.append(f"💾 Memory: {stats.get('memory_usage_mb', 0)}MB/{stats.get('max_memory_mb', 0)}MB ({stats.get('memory_usage_percent', 0)}%)")
    
    if warnings:
        output.append("⚠️  Warnings:")
        for warning in warnings:
            output.append(f"   • {warning}")
    
    # Configuration summary
    retention = config.get("retention_policy", {})
    output.append(f"🕒 Retention: {retention.get('max_age_hours', 'N/A')} hours")
    output.append(f"🔄 Cleanup: Every {retention.get('cleanup_interval_minutes', 'N/A')} minutes")
    
    return "\n".join(output)

def monitor_continuous(interval_seconds=60):
    """Continuously monitor storage"""
    print("🔍 Preview Storage Monitor")
    print("=" * 50)
    print("Press Ctrl+C to stop\n")
    
    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}]")
            
            data = get_storage_stats()
            display = format_storage_display(data)
            print(display)
            
            print("-" * 50)
            time.sleep(interval_seconds)
            
    except KeyboardInterrupt:
        print("\n👋 Monitoring stopped")

def show_current_status():
    """Show current status once"""
    print("📊 Current Preview Storage Status")
    print("=" * 50)
    
    data = get_storage_stats()
    display = format_storage_display(data)
    print(display)
    
    # Show detailed configuration
    if "configuration" in data:
        config = data["configuration"]
        print("\n⚙️  Configuration Details:")
        print(json.dumps(config, indent=2))

def simulate_load_test():
    """Simulate storage load for testing"""
    print("🧪 Storage Load Test Simulation")
    print("This would create test previews to verify cleanup behavior")
    print("(Implementation would require direct access to preview_handler)")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "monitor":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
            monitor_continuous(interval)
        elif command == "status":
            show_current_status()
        elif command == "test":
            simulate_load_test()
        else:
            print("Usage: python preview_monitor.py [monitor|status|test] [interval_seconds]")
    else:
        show_current_status()