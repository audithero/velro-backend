"""
Production-Safe Debugging Utilities
Enterprise-grade debugging tools designed for safe production use.
"""
import json
import time
import hashlib
import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, asdict
from uuid import uuid4
from enum import Enum
import os
import sys
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)


class DebugLevel(Enum):
    """Debug levels for production safety."""
    SAFE = "safe"           # Safe for production - no sensitive data
    DETAILED = "detailed"   # Detailed info - development only
    SENSITIVE = "sensitive" # Sensitive data - never in production


@dataclass
class DebugEvent:
    """Represents a debug event for tracking."""
    id: str
    timestamp: datetime
    component: str
    event_type: str
    level: DebugLevel
    message: str
    metadata: Dict[str, Any]
    stack_trace: Optional[str]
    user_id: Optional[str]
    request_id: Optional[str]


@dataclass
class SystemHealth:
    """System health metrics."""
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    active_connections: int
    database_status: str
    cache_status: str
    external_services: Dict[str, str]
    error_rate: float
    response_time_avg: float


class ProductionDebugger:
    """Production-safe debugging and monitoring system."""
    
    def __init__(self):
        self.events: List[DebugEvent] = []
        self.max_events = 1000
        self.sensitive_patterns = {
            "password", "secret", "key", "token", "auth", "credential",
            "private", "confidential", "ssn", "credit_card", "api_key"
        }
        self.performance_metrics: Dict[str, List[float]] = {}
        self.error_patterns: Dict[str, int] = {}
        self.alerts: List[Dict[str, Any]] = []
        
    def log_event(self, component: str, event_type: str, message: str,
                  level: DebugLevel = DebugLevel.SAFE, metadata: Dict[str, Any] = None,
                  user_id: str = None, request_id: str = None, include_stack: bool = False):
        """Log a debug event with production safety checks."""
        
        # Production safety checks
        if settings.is_production() and level != DebugLevel.SAFE:
            # In production, only log safe events
            return
        
        # Sanitize metadata
        safe_metadata = self._sanitize_metadata(metadata or {})
        
        # Generate stack trace if requested and safe
        stack_trace = None
        if include_stack and (settings.debug or not settings.is_production()):
            import traceback
            stack_trace = traceback.format_stack()
        
        event = DebugEvent(
            id=str(uuid4()),
            timestamp=datetime.now(timezone.utc),
            component=component,
            event_type=event_type,
            level=level,
            message=self._sanitize_message(message),
            metadata=safe_metadata,
            stack_trace=stack_trace,
            user_id=user_id,
            request_id=request_id
        )
        
        self.events.append(event)
        self._cleanup_events()
        
        # Log to standard logger based on event type
        log_message = f"[{component}] {event_type}: {message}"
        if event_type.lower() in ["error", "exception", "critical"]:
            logger.error(log_message)
        elif event_type.lower() in ["warning", "warn"]:
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def _sanitize_message(self, message: str) -> str:
        """Sanitize message to remove sensitive information."""
        safe_message = message
        
        # Remove common sensitive patterns
        import re
        
        # Email addresses (partial)
        safe_message = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', 
                             '***EMAIL***', safe_message)
        
        # Tokens and keys
        safe_message = re.sub(r'\b[A-Za-z0-9]{20,}\b', '***TOKEN***', safe_message)
        
        # UUIDs (partial obfuscation)
        safe_message = re.sub(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
                             lambda m: m.group()[:8] + '-****-****-****-' + m.group()[-12:], 
                             safe_message, flags=re.IGNORECASE)
        
        return safe_message
    
    def _sanitize_metadata(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize metadata to remove sensitive information."""
        safe_metadata = {}
        
        for key, value in metadata.items():
            key_lower = key.lower()
            
            # Check if key contains sensitive patterns
            is_sensitive = any(pattern in key_lower for pattern in self.sensitive_patterns)
            
            if is_sensitive:
                safe_metadata[key] = "***REDACTED***"
            elif isinstance(value, (str, int, float, bool, type(None))):
                safe_metadata[key] = value
            elif isinstance(value, (list, tuple)):
                safe_metadata[key] = f"[{len(value)} items]"
            elif isinstance(value, dict):
                safe_metadata[key] = f"{{dict with {len(value)} keys}}"
            else:
                safe_metadata[key] = str(type(value).__name__)
        
        return safe_metadata
    
    def _cleanup_events(self):
        """Clean up old events to prevent memory issues."""
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
    
    def record_performance_metric(self, metric_name: str, value: float):
        """Record a performance metric."""
        if metric_name not in self.performance_metrics:
            self.performance_metrics[metric_name] = []
        
        self.performance_metrics[metric_name].append(value)
        
        # Keep only recent metrics (last 1000 per metric)
        if len(self.performance_metrics[metric_name]) > 1000:
            self.performance_metrics[metric_name] = self.performance_metrics[metric_name][-1000:]
    
    def record_error_pattern(self, error_type: str):
        """Record error patterns for analysis."""
        self.error_patterns[error_type] = self.error_patterns.get(error_type, 0) + 1
    
    def create_alert(self, alert_type: str, message: str, severity: str = "medium",
                    metadata: Dict[str, Any] = None):
        """Create a system alert."""
        alert = {
            "id": str(uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": alert_type,
            "message": message,
            "severity": severity,
            "metadata": self._sanitize_metadata(metadata or {}),
            "acknowledged": False
        }
        
        self.alerts.append(alert)
        
        # Log alert
        log_func = logger.critical if severity == "critical" else \
                  logger.error if severity == "high" else \
                  logger.warning if severity == "medium" else \
                  logger.info
        
        log_func(f"🚨 ALERT [{severity.upper()}] {alert_type}: {message}")
        
        # Keep only recent alerts
        if len(self.alerts) > 100:
            self.alerts = self.alerts[-100:]
    
    async def get_system_health(self) -> SystemHealth:
        """Get current system health metrics (production-safe)."""
        try:
            import psutil
            
            # Basic system metrics
            cpu_usage = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Network connections (count only)
            connections = len(psutil.net_connections())
            
        except ImportError:
            # Fallback if psutil not available
            cpu_usage = 0.0
            memory_usage = 0.0
            disk_usage = 0.0
            connections = 0
        except Exception:
            cpu_usage = 0.0
            memory_usage = 0.0
            disk_usage = 0.0
            connections = 0
        else:
            memory_usage = memory.percent
            disk_usage = disk.percent
        
        # Database status check
        database_status = await self._check_database_health()
        
        # Cache status (if applicable)
        cache_status = "unknown"
        
        # External services status
        external_services = await self._check_external_services()
        
        # Performance metrics
        error_rate = self._calculate_error_rate()
        response_time_avg = self._calculate_avg_response_time()
        
        return SystemHealth(
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            disk_usage=disk_usage,
            active_connections=connections,
            database_status=database_status,
            cache_status=cache_status,
            external_services=external_services,
            error_rate=error_rate,
            response_time_avg=response_time_avg
        )
    
    async def _check_database_health(self) -> str:
        """Check database connectivity and health."""
        try:
            from database import SupabaseClient
            db_client = SupabaseClient()
            
            if not db_client.is_available():
                return "unavailable"
            
            # Simple connectivity test
            result = db_client.client.table('users').select('id').limit(1).execute()
            return "healthy" if result else "degraded"
            
        except Exception as e:
            self.log_event(
                "system_health", "database_check_failed", 
                f"Database health check failed: {str(e)[:100]}",
                DebugLevel.SAFE
            )
            return "error"
    
    async def _check_external_services(self) -> Dict[str, str]:
        """Check external service health."""
        services = {}
        
        # Supabase API check
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.supabase_url}/rest/v1/")
                services["supabase"] = "healthy" if response.status_code == 200 else "degraded"
        except Exception:
            services["supabase"] = "error"
        
        # FAL.ai service check (without API key validation)
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get("https://fal.run/")
                services["fal_ai"] = "healthy" if response.status_code == 200 else "degraded"
        except Exception:
            services["fal_ai"] = "error"
        
        return services
    
    def _calculate_error_rate(self) -> float:
        """Calculate current error rate."""
        total_events = len([e for e in self.events if e.event_type in ["request", "api_call"]])
        error_events = len([e for e in self.events if e.event_type in ["error", "exception"]])
        
        if total_events == 0:
            return 0.0
        
        return (error_events / total_events) * 100
    
    def _calculate_avg_response_time(self) -> float:
        """Calculate average response time."""
        response_times = self.performance_metrics.get("response_time", [])
        
        if not response_times:
            return 0.0
        
        # Get recent response times (last 100)
        recent_times = response_times[-100:]
        return sum(recent_times) / len(recent_times)
    
    def get_recent_events(self, limit: int = 50, component: str = None, 
                         event_type: str = None) -> List[DebugEvent]:
        """Get recent debug events with filtering."""
        filtered_events = self.events
        
        if component:
            filtered_events = [e for e in filtered_events if e.component == component]
        
        if event_type:
            filtered_events = [e for e in filtered_events if e.event_type == event_type]
        
        # Sort by timestamp (newest first)
        sorted_events = sorted(filtered_events, key=lambda x: x.timestamp, reverse=True)
        return sorted_events[:limit]
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get error analysis summary."""
        error_events = [e for e in self.events if e.event_type in ["error", "exception"]]
        
        # Group by component
        by_component = {}
        for event in error_events:
            if event.component not in by_component:
                by_component[event.component] = []
            by_component[event.component].append(event)
        
        summary = {
            "total_errors": len(error_events),
            "error_rate": self._calculate_error_rate(),
            "by_component": {
                component: len(events) 
                for component, events in by_component.items()
            },
            "error_patterns": dict(self.error_patterns),
            "recent_errors": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "component": e.component,
                    "message": e.message[:100] + "..." if len(e.message) > 100 else e.message
                }
                for e in error_events[-10:]  # Last 10 errors
            ]
        }
        
        return summary
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance metrics summary."""
        summary = {}
        
        for metric_name, values in self.performance_metrics.items():
            if values:
                summary[metric_name] = {
                    "avg": sum(values) / len(values),
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                    "recent_avg": sum(values[-10:]) / len(values[-10:]) if len(values) >= 10 else sum(values) / len(values)
                }
        
        return summary
    
    def export_debug_data(self, include_metadata: bool = False) -> Dict[str, Any]:
        """Export debug data for analysis (production-safe)."""
        export_data = {
            "metadata": {
                "export_time": datetime.now(timezone.utc).isoformat(),
                "environment": settings.environment,
                "total_events": len(self.events),
                "total_alerts": len(self.alerts)
            },
            "error_summary": self.get_error_summary(),
            "performance_summary": self.get_performance_summary(),
            "alerts": self.alerts[-20:],  # Recent alerts only
            "recent_events": []
        }
        
        # Export recent events (safe data only)
        recent_events = self.get_recent_events(100)
        for event in recent_events:
            event_data = {
                "timestamp": event.timestamp.isoformat(),
                "component": event.component,
                "event_type": event.event_type,
                "level": event.level.value,
                "message": event.message
            }
            
            if include_metadata and not settings.is_production():
                event_data["metadata"] = event.metadata
            
            export_data["recent_events"].append(event_data)
        
        return export_data
    
    def reset_metrics(self):
        """Reset performance metrics and events (use with caution)."""
        if not settings.is_production():
            self.events.clear()
            self.performance_metrics.clear()
            self.error_patterns.clear()
            self.alerts.clear()
            self.log_event("system", "metrics_reset", "Debug metrics reset", DebugLevel.SAFE)


# Global production debugger instance
production_debugger = ProductionDebugger()


# Decorator for safe performance monitoring
def monitor_performance(metric_name: str):
    """Decorator to monitor function performance."""
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                production_debugger.record_performance_metric(metric_name, duration)
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                production_debugger.record_performance_metric(f"{metric_name}_error", duration)
                production_debugger.record_error_pattern(type(e).__name__)
                raise
        
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000
                production_debugger.record_performance_metric(metric_name, duration)
                return result
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                production_debugger.record_performance_metric(f"{metric_name}_error", duration)
                production_debugger.record_error_pattern(type(e).__name__)
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# Context manager for debug events
class debug_context:
    """Context manager for debug event tracking."""
    
    def __init__(self, component: str, event_type: str, message: str, 
                 level: DebugLevel = DebugLevel.SAFE):
        self.component = component
        self.event_type = event_type
        self.message = message
        self.level = level
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        production_debugger.log_event(
            self.component, f"{self.event_type}_start", 
            f"Starting {self.message}", self.level
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (time.time() - self.start_time) * 1000
        
        if exc_type:
            production_debugger.log_event(
                self.component, f"{self.event_type}_error", 
                f"{self.message} failed: {str(exc_val)[:100]}", 
                self.level
            )
            production_debugger.record_error_pattern(exc_type.__name__)
        else:
            production_debugger.log_event(
                self.component, f"{self.event_type}_complete", 
                f"Completed {self.message} in {duration:.2f}ms", 
                self.level
            )
        
        production_debugger.record_performance_metric(self.event_type, duration)