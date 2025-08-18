"""
Monitoring and Metrics Router
Provides comprehensive monitoring endpoints for Prometheus scraping and health checks.
"""

import time
import psutil
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Response, BackgroundTasks
from pydantic import BaseModel
import asyncio

from monitoring.metrics import metrics_collector
from monitoring.logger import app_logger, security_logger, performance_logger, EventType
from monitoring.siem_integration import siem_integration
from monitoring.enterprise_monitoring_integration import (
    enterprise_monitoring_integration,
    get_monitoring_status,
    get_business_dashboard
)
from monitoring.circuit_breaker_integration import enterprise_circuit_breaker_manager
from monitoring.deep_health_check_system import deep_health_check_system
from monitoring.distributed_tracing_system import distributed_tracing_system
from monitoring.intelligent_alerting_system import intelligent_alerting_system
from caching.redis_cache import authorization_cache, user_session_cache, permission_cache
from services.authorization_service import authorization_service
from utils.performance_monitor import performance_monitor
from database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/monitoring", tags=["monitoring"])


class HealthStatus(BaseModel):
    """Health check response model."""
    status: str
    timestamp: str
    version: str
    uptime_seconds: float
    components: Dict[str, Dict[str, Any]]


class MetricsResponse(BaseModel):
    """Metrics endpoint response."""
    authorization: Dict[str, Any]
    cache: Dict[str, Any]
    security: Dict[str, Any]
    performance: Dict[str, Any]
    system: Dict[str, Any]


@router.get("/metrics", 
           summary="Prometheus Metrics Endpoint",
           description="Returns Prometheus-formatted metrics for scraping")
async def get_prometheus_metrics():
    """
    Prometheus metrics endpoint for comprehensive system monitoring.
    Returns metrics in Prometheus format for scraping.
    """
    try:
        # Update real-time metrics before export
        await _update_realtime_metrics()
        
        # Get Prometheus-formatted output
        metrics_output = metrics_collector.get_metrics_output()
        content_type = metrics_collector.get_metrics_content_type()
        
        return Response(
            content=metrics_output,
            media_type=content_type
        )
        
    except Exception as e:
        logger.error(f"Failed to generate metrics: {e}")
        raise HTTPException(status_code=500, detail="Metrics generation failed")


@router.get("/health", response_model=HealthStatus,
           summary="Comprehensive Health Check",
           description="Returns detailed health status of all system components")
async def health_check():
    """
    Comprehensive health check endpoint for monitoring and alerting.
    Checks all critical system components and dependencies.
    """
    start_time = time.time()
    
    try:
        # Get system uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        
        components = {}
        overall_status = "healthy"
        
        # Database health check
        db_health = await _check_database_health()
        components["database"] = db_health
        if db_health["status"] != "healthy":
            overall_status = "degraded"
        
        # Cache health check
        cache_health = await _check_cache_health()
        components["cache"] = cache_health
        if cache_health["status"] != "healthy":
            overall_status = "degraded"
        
        # Authorization service health
        auth_health = await _check_authorization_health()
        components["authorization"] = auth_health
        if auth_health["status"] != "healthy":
            overall_status = "degraded"
        
        # SIEM integration health
        siem_health = await _check_siem_health()
        components["siem"] = siem_health
        if siem_health["status"] != "healthy":
            overall_status = "degraded"
        
        # System resource health
        system_health = await _check_system_health()
        components["system"] = system_health
        if system_health["status"] != "healthy":
            overall_status = "degraded"
        
        # Log health check result
        duration_ms = (time.time() - start_time) * 1000
        
        if overall_status == "healthy":
            app_logger.info(
                f"Health check passed in {duration_ms:.2f}ms",
                event_type=EventType.SYSTEM,
                duration_ms=duration_ms,
                components=list(components.keys())
            )
        else:
            app_logger.warning(
                f"Health check failed - status: {overall_status}",
                event_type=EventType.SYSTEM,
                duration_ms=duration_ms,
                failed_components=[
                    name for name, comp in components.items() 
                    if comp["status"] != "healthy"
                ]
            )
        
        return HealthStatus(
            status=overall_status,
            timestamp=datetime.now(timezone.utc).isoformat(),
            version="1.0.0",
            uptime_seconds=uptime_seconds,
            components=components
        )
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthStatus(
            status="unhealthy",
            timestamp=datetime.now(timezone.utc).isoformat(),
            version="1.0.0",
            uptime_seconds=0,
            components={"error": {"status": "error", "message": str(e)}}
        )


@router.get("/metrics/detailed", response_model=MetricsResponse,
           summary="Detailed Metrics",
           description="Returns detailed metrics for all system components")
async def get_detailed_metrics():
    """
    Get detailed metrics for all system components.
    Used for custom monitoring and analysis.
    """
    try:
        # Update metrics
        await _update_realtime_metrics()
        
        # Collect metrics from all components
        authorization_metrics = authorization_service.get_performance_metrics()
        cache_metrics = {
            "authorization": authorization_cache.get_stats(),
            "user_session": user_session_cache.get_stats(),
            "permission": permission_cache.get_stats()
        }
        security_metrics = security_logger.get_violation_summary()
        performance_metrics = performance_logger.get_performance_summary()
        system_metrics = await _get_system_metrics()
        
        return MetricsResponse(
            authorization=authorization_metrics,
            cache=cache_metrics,
            security=security_metrics,
            performance=performance_metrics,
            system=system_metrics
        )
        
    except Exception as e:
        logger.error(f"Failed to collect detailed metrics: {e}")
        raise HTTPException(status_code=500, detail="Metrics collection failed")


@router.get("/performance/summary",
           summary="Performance Summary",
           description="Returns performance summary and SLA compliance")
async def get_performance_summary():
    """Get performance summary with SLA compliance metrics."""
    
    try:
        # Get performance statistics
        auth_metrics = authorization_service.get_performance_metrics()
        perf_summary = performance_logger.get_performance_summary()
        
        # Calculate SLA compliance
        avg_response_time = auth_metrics.get("average_response_time", 0)
        sla_compliance = 100.0 if avg_response_time < 100 else max(0, 100 - ((avg_response_time - 100) / 10))
        
        # Get cache performance
        cache_stats = authorization_cache.get_stats()
        cache_hit_rate = cache_stats.get("hit_rate_percent", 0)
        
        return {
            "performance_summary": {
                "sla_compliance_percent": round(sla_compliance, 2),
                "average_response_time_ms": avg_response_time,
                "cache_hit_rate_percent": cache_hit_rate,
                "total_requests": auth_metrics.get("authorization_requests", 0),
                "success_rate_percent": 100 - (auth_metrics.get("authorization_failures", 0) / max(1, auth_metrics.get("authorization_requests", 1)) * 100)
            },
            "targets": {
                "response_time_target_ms": 100,
                "cache_hit_rate_target_percent": 95,
                "sla_compliance_target_percent": 99.9
            },
            "detailed_performance": perf_summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get performance summary: {e}")
        raise HTTPException(status_code=500, detail="Performance summary generation failed")


@router.get("/security/violations",
           summary="Security Violations",
           description="Returns recent security violations and threat indicators")
async def get_security_violations():
    """Get security violations and threat indicators."""
    
    try:
        # Get security violation summary
        violation_summary = security_logger.get_violation_summary()
        
        # Get recent security events from SIEM
        siem_stats = siem_integration.get_statistics()
        
        # Get recent security logs
        recent_events = security_logger.get_recent_events(limit=50, event_type=EventType.SECURITY_VIOLATION)
        
        return {
            "violation_summary": violation_summary,
            "siem_integration": {
                "status": "active" if siem_stats.get("running", False) else "inactive",
                "events_sent": siem_stats.get("events_sent", 0),
                "events_failed": siem_stats.get("events_failed", 0),
                "last_successful_send": siem_stats.get("last_successful_send")
            },
            "recent_violations": recent_events,
            "threat_level": _calculate_threat_level(violation_summary),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get security violations: {e}")
        raise HTTPException(status_code=500, detail="Security violations retrieval failed")


@router.post("/cache/invalidate/{cache_type}",
            summary="Cache Invalidation",
            description="Invalidate cache entries by type or tag")
async def invalidate_cache(cache_type: str, tag: Optional[str] = None):
    """Invalidate cache entries for maintenance or security purposes."""
    
    try:
        if cache_type == "authorization":
            cache = authorization_cache
        elif cache_type == "user_session":
            cache = user_session_cache
        elif cache_type == "permission":
            cache = permission_cache
        else:
            raise HTTPException(status_code=400, detail="Invalid cache type")
        
        if tag:
            invalidated = cache.invalidate_by_tag(tag)
        else:
            cache.clear_all()
            invalidated = "all"
        
        # Log cache invalidation for security audit
        security_logger.info(
            f"Cache invalidation requested: {cache_type} (tag: {tag})",
            event_type=EventType.AUDIT,
            cache_type=cache_type,
            tag=tag,
            invalidated_count=invalidated
        )
        
        return {
            "status": "success",
            "cache_type": cache_type,
            "tag": tag,
            "invalidated_entries": invalidated,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")
        raise HTTPException(status_code=500, detail="Cache invalidation failed")


@router.get("/logs/recent",
           summary="Recent Log Events",
           description="Get recent log events for debugging and monitoring")
async def get_recent_logs(
    limit: int = 100,
    level: Optional[str] = None,
    event_type: Optional[str] = None
):
    """Get recent log events for debugging and monitoring."""
    
    try:
        # Get recent events from different loggers
        app_events = app_logger.get_recent_events(limit=limit//3)
        security_events = security_logger.get_recent_events(limit=limit//3)
        performance_events = performance_logger.get_recent_events(limit=limit//3)
        
        all_events = app_events + security_events + performance_events
        
        # Filter by level if specified
        if level:
            all_events = [e for e in all_events if e.get("level") == level.upper()]
        
        # Filter by event type if specified
        if event_type:
            all_events = [e for e in all_events if e.get("event_type") == event_type]
        
        # Sort by timestamp (most recent first)
        all_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        
        return {
            "events": all_events[:limit],
            "total_events": len(all_events),
            "filters_applied": {
                "level": level,
                "event_type": event_type,
                "limit": limit
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get recent logs: {e}")
        raise HTTPException(status_code=500, detail="Log retrieval failed")


# Background task for updating real-time metrics
async def _update_realtime_metrics():
    """Update real-time metrics for Prometheus export."""
    
    try:
        # Update system metrics
        cpu_percent = psutil.cpu_percent()
        memory = psutil.virtual_memory()
        
        metrics_collector.performance_metrics.update_system_metrics(
            memory_bytes=memory.used,
            cpu_percent=cpu_percent
        )
        
        # Update cache metrics
        for cache_name, cache in [
            ("authorization", authorization_cache),
            ("user_session", user_session_cache),
            ("permission", permission_cache)
        ]:
            stats = cache.get_stats()
            
            # Calculate cache size (approximate)
            cache_size = stats.get("memory_cache_entries", 0) * 1024  # Rough estimate
            entries_count = stats.get("memory_cache_entries", 0)
            
            metrics_collector.cache_metrics.update_cache_size(
                cache_name, cache_size, entries_count
            )
        
        # Update Redis metrics if available
        redis_info = authorization_cache.redis_client.info()
        metrics_collector.cache_metrics.update_redis_metrics(
            active_connections=redis_info.get("connected_clients", 0),
            memory_used=redis_info.get("used_memory", 0),
            memory_peak=redis_info.get("used_memory_peak", 0)
        )
        
    except Exception as e:
        logger.error(f"Failed to update real-time metrics: {e}")


async def _check_database_health() -> Dict[str, Any]:
    """Check database connectivity and performance."""
    start_time = time.time()
    
    try:
        db = await get_database()
        
        # Simple health check query
        result = await db.execute_query(
            table="information_schema.tables",
            operation="count",
            filters={"table_schema": "public"}
        )
        
        duration_ms = (time.time() - start_time) * 1000
        
        return {
            "status": "healthy",
            "response_time_ms": round(duration_ms, 2),
            "table_count": len(result) if result else 0,
            "last_check": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        return {
            "status": "unhealthy",
            "response_time_ms": round(duration_ms, 2),
            "error": str(e),
            "last_check": datetime.now(timezone.utc).isoformat()
        }


async def _check_cache_health() -> Dict[str, Any]:
    """Check Redis cache connectivity and performance."""
    
    try:
        health = authorization_cache.health_check()
        return health
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "last_check": datetime.now(timezone.utc).isoformat()
        }


async def _check_authorization_health() -> Dict[str, Any]:
    """Check authorization service health."""
    
    try:
        metrics = authorization_service.get_performance_metrics()
        avg_response_time = metrics.get("average_response_time", 0)
        
        status = "healthy"
        if avg_response_time > 500:  # > 500ms
            status = "degraded"
        elif avg_response_time > 1000:  # > 1s
            status = "unhealthy"
        
        return {
            "status": status,
            "average_response_time_ms": avg_response_time,
            "total_requests": metrics.get("authorization_requests", 0),
            "cache_hits": metrics.get("cache_hits", 0),
            "cache_misses": metrics.get("cache_misses", 0),
            "last_check": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "last_check": datetime.now(timezone.utc).isoformat()
        }


async def _check_siem_health() -> Dict[str, Any]:
    """Check SIEM integration health."""
    
    try:
        stats = siem_integration.get_statistics()
        
        status = "healthy"
        if not stats.get("running", False):
            status = "stopped"
        elif stats.get("connection_errors", 0) > 10:
            status = "degraded"
        
        return {
            "status": status,
            "running": stats.get("running", False),
            "events_sent": stats.get("events_sent", 0),
            "events_failed": stats.get("events_failed", 0),
            "connection_errors": stats.get("connection_errors", 0),
            "last_successful_send": stats.get("last_successful_send"),
            "buffer_size": stats.get("buffer_size", 0)
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "last_check": datetime.now(timezone.utc).isoformat()
        }


async def _check_system_health() -> Dict[str, Any]:
    """Check system resource health."""
    
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        
        # Load average (Unix-like systems only)
        try:
            load_avg = psutil.getloadavg()
        except AttributeError:
            load_avg = None
        
        # Determine overall status
        status = "healthy"
        if cpu_percent > 90 or memory_percent > 90 or disk_percent > 90:
            status = "critical"
        elif cpu_percent > 75 or memory_percent > 75 or disk_percent > 80:
            status = "degraded"
        
        return {
            "status": status,
            "cpu_percent": round(cpu_percent, 1),
            "memory_percent": round(memory_percent, 1),
            "disk_percent": round(disk_percent, 1),
            "load_average": load_avg,
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "disk_total_gb": round(disk.total / (1024**3), 2),
            "disk_used_gb": round(disk.used / (1024**3), 2),
            "last_check": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "last_check": datetime.now(timezone.utc).isoformat()
        }


async def _get_system_metrics() -> Dict[str, Any]:
    """Get detailed system metrics."""
    
    try:
        return {
            "cpu": {
                "percent": psutil.cpu_percent(interval=1),
                "count": psutil.cpu_count(),
                "count_logical": psutil.cpu_count(logical=True)
            },
            "memory": {
                "total": psutil.virtual_memory().total,
                "used": psutil.virtual_memory().used,
                "percent": psutil.virtual_memory().percent
            },
            "disk": {
                "total": psutil.disk_usage('/').total,
                "used": psutil.disk_usage('/').used,
                "percent": (psutil.disk_usage('/').used / psutil.disk_usage('/').total) * 100
            },
            "network": dict(psutil.net_io_counters()._asdict()),
            "boot_time": psutil.boot_time(),
            "process_count": len(psutil.pids())
        }
        
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        return {"error": str(e)}


def _calculate_threat_level(violations: Dict[str, int]) -> str:
    """Calculate overall threat level based on violations."""
    
    total_violations = sum(violations.values())
    
    if total_violations == 0:
        return "low"
    elif total_violations < 10:
        return "medium"
    elif total_violations < 50:
        return "high"
    else:
        return "critical"


# Enterprise Monitoring Endpoints

@router.get("/enterprise/status",
           summary="Enterprise Monitoring Status",
           description="Get comprehensive status of all enterprise monitoring systems")
async def get_enterprise_monitoring_status():
    """Get comprehensive status of all enterprise monitoring systems."""
    try:
        return await get_monitoring_status()
    except Exception as e:
        logger.error(f"Failed to get enterprise monitoring status: {e}")
        raise HTTPException(status_code=500, detail="Enterprise monitoring status retrieval failed")


@router.get("/enterprise/dashboard",
           summary="Business Intelligence Dashboard",
           description="Get business intelligence data for executive dashboard")
async def get_enterprise_dashboard():
    """Get business intelligence data for executive dashboard."""
    try:
        return await get_business_dashboard()
    except Exception as e:
        logger.error(f"Failed to get business dashboard: {e}")
        raise HTTPException(status_code=500, detail="Business dashboard retrieval failed")


@router.get("/circuit-breakers",
           summary="Circuit Breaker Status",
           description="Get status of all circuit breakers")
async def get_circuit_breaker_status():
    """Get status of all circuit breakers."""
    try:
        return await enterprise_circuit_breaker_manager.get_system_health_report()
    except Exception as e:
        logger.error(f"Failed to get circuit breaker status: {e}")
        raise HTTPException(status_code=500, detail="Circuit breaker status retrieval failed")


@router.post("/circuit-breakers/{service_name}/recover",
            summary="Trigger Service Recovery",
            description="Manually trigger recovery for a specific service")
async def trigger_service_recovery(service_name: str):
    """Manually trigger recovery for a specific service."""
    try:
        success = await enterprise_circuit_breaker_manager.trigger_manual_recovery(service_name)
        
        if success:
            return {
                "status": "success",
                "message": f"Recovery triggered for {service_name}",
                "service": service_name,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=400, detail=f"Failed to trigger recovery for {service_name}")
            
    except Exception as e:
        logger.error(f"Failed to trigger service recovery: {e}")
        raise HTTPException(status_code=500, detail="Service recovery trigger failed")


@router.get("/health/deep",
           summary="Deep Health Check",
           description="Get deep health check results for all dependencies")
async def get_deep_health_check():
    """Get deep health check results for all dependencies."""
    try:
        return await deep_health_check_system.get_health_report()
    except Exception as e:
        logger.error(f"Failed to get deep health check: {e}")
        raise HTTPException(status_code=500, detail="Deep health check retrieval failed")


@router.post("/health/check/{component}",
            summary="Force Health Check",
            description="Force immediate health check for a specific component")
async def force_health_check(component: str = None):
    """Force immediate health check for component(s)."""
    try:
        return await deep_health_check_system.force_health_check(component)
    except Exception as e:
        logger.error(f"Failed to force health check: {e}")
        raise HTTPException(status_code=500, detail="Forced health check failed")


@router.get("/tracing/active",
           summary="Active Traces",
           description="Get summary of active distributed traces")
async def get_active_traces():
    """Get summary of active distributed traces."""
    try:
        return distributed_tracing_system.get_active_traces_summary()
    except Exception as e:
        logger.error(f"Failed to get active traces: {e}")
        raise HTTPException(status_code=500, detail="Active traces retrieval failed")


@router.get("/tracing/trace/{trace_id}",
           summary="Trace Details",
           description="Get detailed information about a specific trace")
async def get_trace_details(trace_id: str):
    """Get detailed information about a specific trace."""
    try:
        trace_details = distributed_tracing_system.get_trace_details(trace_id)
        
        if trace_details:
            return trace_details
        else:
            raise HTTPException(status_code=404, detail=f"Trace {trace_id} not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get trace details: {e}")
        raise HTTPException(status_code=500, detail="Trace details retrieval failed")


@router.get("/tracing/insights",
           summary="Performance Insights",
           description="Get performance insights from trace analysis")
async def get_performance_insights():
    """Get performance insights from trace analysis."""
    try:
        return distributed_tracing_system.get_performance_insights()
    except Exception as e:
        logger.error(f"Failed to get performance insights: {e}")
        raise HTTPException(status_code=500, detail="Performance insights retrieval failed")


@router.get("/alerts/active",
           summary="Active Alerts",
           description="Get all active alerts")
async def get_active_alerts():
    """Get all active alerts."""
    try:
        active_alerts = intelligent_alerting_system.get_active_alerts()
        return {
            "alerts": [alert.to_dict() for alert in active_alerts],
            "count": len(active_alerts),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to get active alerts: {e}")
        raise HTTPException(status_code=500, detail="Active alerts retrieval failed")


@router.get("/alerts/summary",
           summary="Alert Summary",
           description="Get alert summary statistics")
async def get_alert_summary():
    """Get alert summary statistics."""
    try:
        return intelligent_alerting_system.get_alert_summary()
    except Exception as e:
        logger.error(f"Failed to get alert summary: {e}")
        raise HTTPException(status_code=500, detail="Alert summary retrieval failed")


@router.post("/alerts/{alert_id}/acknowledge",
            summary="Acknowledge Alert",
            description="Acknowledge a specific alert")
async def acknowledge_alert(alert_id: str, acknowledged_by: str = "api_user"):
    """Acknowledge a specific alert."""
    try:
        success = await intelligent_alerting_system.acknowledge_alert(alert_id, acknowledged_by)
        
        if success:
            return {
                "status": "success",
                "message": f"Alert {alert_id} acknowledged",
                "alert_id": alert_id,
                "acknowledged_by": acknowledged_by,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert: {e}")
        raise HTTPException(status_code=500, detail="Alert acknowledgment failed")


@router.post("/alerts/{alert_id}/resolve",
            summary="Resolve Alert",
            description="Resolve a specific alert")
async def resolve_alert(alert_id: str):
    """Resolve a specific alert."""
    try:
        success = await intelligent_alerting_system.resolve_alert(alert_id)
        
        if success:
            return {
                "status": "success",
                "message": f"Alert {alert_id} resolved",
                "alert_id": alert_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert: {e}")
        raise HTTPException(status_code=500, detail="Alert resolution failed")


@router.post("/tracing/sampling-rate",
            summary="Update Trace Sampling Rate",
            description="Update the distributed tracing sampling rate")
async def update_sampling_rate(sampling_rate: float):
    """Update the distributed tracing sampling rate."""
    try:
        if not 0.0 <= sampling_rate <= 1.0:
            raise HTTPException(status_code=400, detail="Sampling rate must be between 0.0 and 1.0")
        
        distributed_tracing_system.set_sampling_rate(sampling_rate)
        
        return {
            "status": "success",
            "message": f"Sampling rate updated to {sampling_rate * 100}%",
            "sampling_rate": sampling_rate,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update sampling rate: {e}")
        raise HTTPException(status_code=500, detail="Sampling rate update failed")


@router.post("/enterprise/start",
            summary="Start Enterprise Monitoring",
            description="Start the complete enterprise monitoring system")
async def start_enterprise_monitoring():
    """Start the complete enterprise monitoring system."""
    try:
        if enterprise_monitoring_integration.integration_started:
            return {
                "status": "already_started",
                "message": "Enterprise monitoring is already running",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        await enterprise_monitoring_integration.start_monitoring_integration()
        
        return {
            "status": "success",
            "message": "Enterprise monitoring system started successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to start enterprise monitoring: {e}")
        raise HTTPException(status_code=500, detail="Enterprise monitoring startup failed")


@router.post("/enterprise/stop",
            summary="Stop Enterprise Monitoring",
            description="Stop the enterprise monitoring system")
async def stop_enterprise_monitoring():
    """Stop the enterprise monitoring system."""
    try:
        if not enterprise_monitoring_integration.integration_started:
            return {
                "status": "already_stopped",
                "message": "Enterprise monitoring is not running",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        await enterprise_monitoring_integration.stop_monitoring_integration()
        
        return {
            "status": "success",
            "message": "Enterprise monitoring system stopped successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to stop enterprise monitoring: {e}")
        raise HTTPException(status_code=500, detail="Enterprise monitoring shutdown failed")


@router.get("/enterprise/config",
           summary="Get Monitoring Configuration",
           description="Get current monitoring integration configuration")
async def get_monitoring_configuration():
    """Get current monitoring integration configuration."""
    try:
        return enterprise_monitoring_integration.get_integration_config()
    except Exception as e:
        logger.error(f"Failed to get monitoring configuration: {e}")
        raise HTTPException(status_code=500, detail="Monitoring configuration retrieval failed")


@router.put("/enterprise/config",
           summary="Update Monitoring Configuration",
           description="Update monitoring integration configuration")
async def update_monitoring_configuration(config: Dict[str, Any]):
    """Update monitoring integration configuration."""
    try:
        await enterprise_monitoring_integration.update_integration_config(config)
        
        return {
            "status": "success",
            "message": "Monitoring configuration updated successfully",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to update monitoring configuration: {e}")
        raise HTTPException(status_code=500, detail="Monitoring configuration update failed")