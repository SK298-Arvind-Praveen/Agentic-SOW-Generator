"""
Preview Storage Configuration
Centralized settings for preview data management
"""

class PreviewConfig:
    """Configuration for preview storage and cleanup"""
    
    # Storage Limits
    MAX_PREVIEWS = 1000  # Maximum number of previews to keep
    MAX_MEMORY_MB = 500  # Maximum memory usage for previews (MB)
    
    # Retention Policy
    MAX_AGE_HOURS = 24  # How long to keep previews (hours)
    CLEANUP_INTERVAL_MINUTES = 30  # How often to run cleanup (minutes)
    
    # Cleanup Thresholds
    MEMORY_WARNING_THRESHOLD = 80  # Warn when memory usage exceeds this %
    PREVIEW_COUNT_WARNING_THRESHOLD = 0.9  # Warn when preview count exceeds this ratio
    
    # Emergency Cleanup
    EMERGENCY_CLEANUP_TARGET = 0.8  # Keep this ratio of max when doing emergency cleanup
    
    # Performance Settings
    ENABLE_AUTO_CLEANUP = True  # Enable automatic background cleanup
    ENABLE_STORAGE_MONITORING = True  # Enable storage statistics tracking
    
    @classmethod
    def get_config_summary(cls):
        """Get a summary of current configuration"""
        return {
            "storage_limits": {
                "max_previews": cls.MAX_PREVIEWS,
                "max_memory_mb": cls.MAX_MEMORY_MB
            },
            "retention_policy": {
                "max_age_hours": cls.MAX_AGE_HOURS,
                "cleanup_interval_minutes": cls.CLEANUP_INTERVAL_MINUTES
            },
            "thresholds": {
                "memory_warning_percent": cls.MEMORY_WARNING_THRESHOLD,
                "preview_count_warning_ratio": cls.PREVIEW_COUNT_WARNING_THRESHOLD
            },
            "features": {
                "auto_cleanup_enabled": cls.ENABLE_AUTO_CLEANUP,
                "storage_monitoring_enabled": cls.ENABLE_STORAGE_MONITORING
            }
        }

# Environment-specific overrides
import os

# Allow environment variable overrides
if os.getenv('PREVIEW_MAX_COUNT'):
    PreviewConfig.MAX_PREVIEWS = int(os.getenv('PREVIEW_MAX_COUNT'))

if os.getenv('PREVIEW_MAX_MEMORY_MB'):
    PreviewConfig.MAX_MEMORY_MB = int(os.getenv('PREVIEW_MAX_MEMORY_MB'))

if os.getenv('PREVIEW_MAX_AGE_HOURS'):
    PreviewConfig.MAX_AGE_HOURS = int(os.getenv('PREVIEW_MAX_AGE_HOURS'))

if os.getenv('PREVIEW_CLEANUP_INTERVAL_MINUTES'):
    PreviewConfig.CLEANUP_INTERVAL_MINUTES = int(os.getenv('PREVIEW_CLEANUP_INTERVAL_MINUTES'))

# Disable auto-cleanup in development if needed
if os.getenv('PREVIEW_DISABLE_AUTO_CLEANUP') == 'true':
    PreviewConfig.ENABLE_AUTO_CLEANUP = False