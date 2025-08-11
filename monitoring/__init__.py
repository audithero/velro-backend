"""
Comprehensive monitoring infrastructure for UUID authorization system.
Provides Prometheus metrics, logging, and performance tracking.
"""

from .metrics import (
    AuthorizationMetrics,
    PerformanceMetrics,
    SecurityMetrics,
    CacheMetrics
)
from .logger import (
    StructuredLogger,
    AuditLogger,
    SecurityLogger
)
from .performance import (
    PerformanceTracker,
    ResponseTimeMonitor,
    ConcurrencyMonitor
)
# Alerts module not yet implemented
# from .alerts import (
#     AlertManager,
#     SecurityAlerts,
#     PerformanceAlerts
# )

# Temporary placeholders for missing alert classes
class AlertManager:
    """Placeholder for alert manager."""
    pass

class SecurityAlerts:
    """Placeholder for security alerts."""
    pass

class PerformanceAlerts:
    """Placeholder for performance alerts."""
    pass

__all__ = [
    'AuthorizationMetrics',
    'PerformanceMetrics', 
    'SecurityMetrics',
    'CacheMetrics',
    'StructuredLogger',
    'AuditLogger',
    'SecurityLogger',
    'PerformanceTracker',
    'ResponseTimeMonitor',
    'ConcurrencyMonitor',
    'AlertManager',
    'SecurityAlerts',
    'PerformanceAlerts'
]