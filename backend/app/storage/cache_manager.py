"""
Caching Layer for Preview API Performance
"""
import json
import hashlib
import time
from typing import Dict, Any, Optional
import threading

# In-memory cache with TTL
cache_storage = {}
cache_lock = threading.Lock()

class CacheManager:
    def __init__(self, default_ttl=3600):  # 1 hour default
        self.default_ttl = default_ttl
    
    def _generate_key(self, data: Dict[str, Any]) -> str:
        """Generate cache key from data"""
        # Create deterministic hash from relevant data
        cache_data = {
            'company_name': data.get('company_name', ''),
            'project_name': data.get('project_name', ''),
            'mode': data.get('mode', ''),
            'objective': data.get('objective', '')
        }
        
        json_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(json_str.encode()).hexdigest()
    
    def get_research_cache(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Get cached company research"""
        key = f"research_{hashlib.md5(company_name.encode()).hexdigest()}"
        
        with cache_lock:
            if key in cache_storage:
                entry = cache_storage[key]
                if time.time() - entry['timestamp'] < entry['ttl']:
                    print(f"✓ Cache hit for company research: {company_name}")
                    return entry['data']
                else:
                    del cache_storage[key]
        
        return None
    
    def set_research_cache(self, company_name: str, data: Dict[str, Any], ttl: int = None):
        """Cache company research"""
        key = f"research_{hashlib.md5(company_name.encode()).hexdigest()}"
        ttl = ttl or self.default_ttl
        
        with cache_lock:
            cache_storage[key] = {
                'data': data,
                'timestamp': time.time(),
                'ttl': ttl
            }
        
        print(f"✓ Cached company research: {company_name}")
    
    def get_content_cache(self, metadata: Dict[str, Any], requirements: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Get cached content generation"""
        cache_data = {
            'company_name': metadata.get('company_name'),
            'project_title': metadata.get('project_title'),
            'mode': metadata.get('mode'),
            'requirements_hash': hashlib.md5(json.dumps(requirements, sort_keys=True).encode()).hexdigest()
        }
        
        key = f"content_{self._generate_key(cache_data)}"
        
        with cache_lock:
            if key in cache_storage:
                entry = cache_storage[key]
                if time.time() - entry['timestamp'] < entry['ttl']:
                    print(f"✓ Cache hit for content generation")
                    return entry['data']
                else:
                    del cache_storage[key]
        
        return None
    
    def set_content_cache(self, metadata: Dict[str, Any], requirements: Dict[str, Any], 
                         content: Dict[str, Any], ttl: int = None):
        """Cache generated content"""
        cache_data = {
            'company_name': metadata.get('company_name'),
            'project_title': metadata.get('project_title'),
            'mode': metadata.get('mode'),
            'requirements_hash': hashlib.md5(json.dumps(requirements, sort_keys=True).encode()).hexdigest()
        }
        
        key = f"content_{self._generate_key(cache_data)}"
        ttl = ttl or self.default_ttl
        
        with cache_lock:
            cache_storage[key] = {
                'data': content,
                'timestamp': time.time(),
                'ttl': ttl
            }
        
        print(f"✓ Cached content generation")
    
    def cleanup_expired(self):
        """Remove expired cache entries"""
        current_time = time.time()
        expired_keys = []
        
        with cache_lock:
            for key, entry in cache_storage.items():
                if current_time - entry['timestamp'] >= entry['ttl']:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del cache_storage[key]
        
        if expired_keys:
            print(f"✓ Cleaned up {len(expired_keys)} expired cache entries")

# Global cache instance
cache_manager = CacheManager()