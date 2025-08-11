"""
Kong Health Monitoring Service for Velro AI Platform
Continuous monitoring, alerting, and performance tracking for Kong Gateway integration.
Date: August 6, 2025
Author: Kong Integration Specialist
"""
import asyncio
import logging
import time
import statistics
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from enum import Enum
import os
import json
import httpx
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class HealthMetric:
    """Health metric data point."""
    timestamp: float
    response_time_ms: int
    status_code: int
    success: bool
    error_message: Optional[str] = None


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class KongHealthMonitor:
    """Advanced health monitoring service for Kong Gateway."""
    
    def __init__(self):
        # Configuration
        self.kong_gateway_url = os.getenv('KONG_URL', 'https://kong-production.up.railway.app')
        self.kong_admin_url = os.getenv('KONG_ADMIN_URL', 'https://kong-production.up.railway.app')
        self.kong_api_key = os.getenv('KONG_API_KEY', 'velro-backend-key-2025-prod')
        
        # Monitoring configuration
        self.health_check_interval = int(os.getenv('KONG_HEALTH_CHECK_INTERVAL', '30'))
        self.performance_check_interval = int(os.getenv('KONG_PERFORMANCE_CHECK_INTERVAL', '60'))
        self.metrics_retention_hours = int(os.getenv('KONG_METRICS_RETENTION_HOURS', '24'))
        
        # Health thresholds
        self.response_time_warning_ms = int(os.getenv('KONG_RESPONSE_TIME_WARNING_MS', '5000'))
        self.response_time_critical_ms = int(os.getenv('KONG_RESPONSE_TIME_CRITICAL_MS', '10000'))
        self.error_rate_warning = float(os.getenv('KONG_ERROR_RATE_WARNING', '0.05'))  # 5%
        self.error_rate_critical = float(os.getenv('KONG_ERROR_RATE_CRITICAL', '0.10'))  # 10%
        
        # Health data storage
        self.health_metrics: List[HealthMetric] = []
        self.performance_data = {
            "response_times": [],
            "success_rates": [],
            "error_counts": {},
            "uptime_data": []
        }
        
        # Alert tracking
        self.active_alerts = {}
        self.alert_history = []
        
        # HTTP client
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            limits=httpx.Limits(max_keepalive_connections=5)
        )
        
        # Monitoring state
        self.monitoring_active = False
        self.last_health_check = None
        self.last_performance_check = None
        
        logger.info(f"🏥 Kong Health Monitor initialized")
        logger.info(f"🔗 Kong Gateway URL: {self.kong_gateway_url}")
        logger.info(f"⏱️ Health check interval: {self.health_check_interval}s")
        logger.info(f"📊 Performance check interval: {self.performance_check_interval}s")
        logger.info(f"⚠️ Response time warning: {self.response_time_warning_ms}ms")
        logger.info(f"🚨 Response time critical: {self.response_time_critical_ms}ms")
        
    async def start_monitoring(self):
        """Start continuous health and performance monitoring."""
        if self.monitoring_active:
            logger.warning("⚠️ Kong health monitoring already active")
            return
            
        self.monitoring_active = True
        logger.info("🚀 Starting Kong health monitoring")
        
        # Start concurrent monitoring tasks
        tasks = [
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._performance_check_loop()),
            asyncio.create_task(self._cleanup_old_metrics_loop())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except Exception as e:
            logger.error(f"❌ Kong health monitoring error: {e}")
            self.monitoring_active = False
            raise
            
    async def stop_monitoring(self):
        """Stop health monitoring."""
        self.monitoring_active = False
        logger.info("🛑 Kong health monitoring stopped")
        
    async def _health_check_loop(self):
        """Continuous health check loop."""
        while self.monitoring_active:
            try:
                await self.perform_health_check()
                await asyncio.sleep(self.health_check_interval)
            except Exception as e:
                logger.error(f"❌ Health check loop error: {e}")
                await asyncio.sleep(self.health_check_interval)
                
    async def _performance_check_loop(self):
        """Continuous performance monitoring loop."""
        while self.monitoring_active:
            try:
                await self.perform_performance_check()
                await asyncio.sleep(self.performance_check_interval)
            except Exception as e:
                logger.error(f"❌ Performance check loop error: {e}")
                await asyncio.sleep(self.performance_check_interval)
                
    async def _cleanup_old_metrics_loop(self):
        """Cleanup old metrics periodically."""
        while self.monitoring_active:
            try:
                await self._cleanup_old_metrics()
                await asyncio.sleep(3600)  # Run every hour
            except Exception as e:
                logger.error(f"❌ Metrics cleanup error: {e}")
                await asyncio.sleep(3600)
                
    async def perform_health_check(self) -> Dict[str, Any]:
        """Perform comprehensive Kong health check."""
        start_time = time.time()
        health_result = {
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {},
            "overall_status": "unknown"
        }
        
        try:
            # Test Kong status endpoint
            status_result = await self._check_kong_status()
            health_result["checks"]["status"] = status_result
            
            # Test Kong admin API
            admin_result = await self._check_kong_admin()
            health_result["checks"]["admin"] = admin_result
            
            # Test Kong proxy endpoint
            proxy_result = await self._check_kong_proxy()
            health_result["checks"]["proxy"] = proxy_result
            
            # Test route connectivity
            route_result = await self._check_kong_routes()
            health_result["checks"]["routes"] = route_result
            
            # Determine overall status
            all_checks = [status_result, admin_result, proxy_result, route_result]
            if all(check["status"] == "healthy" for check in all_checks):
                health_result["overall_status"] = "healthy"
            elif any(check["status"] == "critical" for check in all_checks):
                health_result["overall_status"] = "critical"
            else:
                health_result["overall_status"] = "degraded"
                
            # Record health metric
            response_time_ms = int((time.time() - start_time) * 1000)
            success = health_result["overall_status"] in ["healthy", "degraded"]
            
            metric = HealthMetric(
                timestamp=time.time(),
                response_time_ms=response_time_ms,
                status_code=200 if success else 500,
                success=success,
                error_message=None if success else "Health check failed"
            )
            
            await self._record_health_metric(metric)
            
            # Check for alerts
            await self._check_health_alerts(health_result)
            
            self.last_health_check = time.time()
            
        except Exception as e:
            logger.error(f"❌ Kong health check failed: {e}")
            
            # Record failed health metric
            response_time_ms = int((time.time() - start_time) * 1000)
            metric = HealthMetric(
                timestamp=time.time(),
                response_time_ms=response_time_ms,
                status_code=500,
                success=False,
                error_message=str(e)
            )
            
            await self._record_health_metric(metric)
            
            health_result.update({
                "overall_status": "critical",
                "error": str(e)
            })
            
        return health_result
        
    async def _check_kong_status(self) -> Dict[str, Any]:
        """Check Kong status endpoint."""
        try:
            response = await self.client.get(f"{self.kong_gateway_url}/status")
            
            if response.status_code == 200:
                status_data = response.json()
                return {
                    "status": "healthy",
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                    "database": status_data.get("database", {}),
                    "server": status_data.get("server", {}),
                    "version": status_data.get("version")
                }
            else:
                return {
                    "status": "unhealthy",
                    "status_code": response.status_code,
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000)
                }
                
        except Exception as e:
            return {
                "status": "critical",
                "error": str(e)
            }
            
    async def _check_kong_admin(self) -> Dict[str, Any]:
        """Check Kong admin API."""
        try:
            response = await self.client.get(f"{self.kong_admin_url}/services")
            
            if response.status_code == 200:
                services_data = response.json()
                return {
                    "status": "healthy",
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                    "services_count": len(services_data.get("data", []))
                }
            else:
                return {
                    "status": "unhealthy",
                    "status_code": response.status_code,
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000)
                }
                
        except Exception as e:
            return {
                "status": "critical",
                "error": str(e)
            }
            
    async def _check_kong_proxy(self) -> Dict[str, Any]:
        """Check Kong proxy functionality."""
        try:
            headers = {"X-API-Key": self.kong_api_key}
            response = await self.client.get(f"{self.kong_gateway_url}/health", headers=headers)
            
            if response.status_code == 200:
                return {
                    "status": "healthy",
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                    "authentication": "working"
                }
            elif response.status_code == 401:
                return {
                    "status": "critical",
                    "status_code": response.status_code,
                    "error": "Authentication failed - check API key"
                }
            else:
                return {
                    "status": "unhealthy",
                    "status_code": response.status_code,
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000)
                }
                
        except Exception as e:
            return {
                "status": "critical",
                "error": str(e)
            }
            
    async def _check_kong_routes(self) -> Dict[str, Any]:
        """Check Kong route accessibility."""
        try:
            # Test a sample route (flux-dev as it's lightweight)
            headers = {
                "X-API-Key": self.kong_api_key,
                "Content-Type": "application/json"
            }
            
            # Use a lightweight health check instead of actual generation
            test_url = f"{self.kong_gateway_url}/fal/flux-dev"
            response = await self.client.options(test_url, headers=headers)
            
            if response.status_code in [200, 204, 405]:  # OPTIONS might return 405
                return {
                    "status": "healthy",
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000),
                    "route_accessible": True
                }
            else:
                return {
                    "status": "unhealthy",
                    "status_code": response.status_code,
                    "response_time_ms": int(response.elapsed.total_seconds() * 1000)
                }
                
        except Exception as e:
            return {
                "status": "critical",
                "error": str(e)
            }
            
    async def _record_health_metric(self, metric: HealthMetric):
        """Record a health metric."""
        self.health_metrics.append(metric)
        
        # Log significant events
        if not metric.success:
            logger.warning(f"🚨 Kong health check failed: {metric.error_message}")
        elif metric.response_time_ms > self.response_time_warning_ms:
            logger.warning(f"⚠️ Kong slow response: {metric.response_time_ms}ms")
            
    async def perform_performance_check(self) -> Dict[str, Any]:
        """Analyze Kong performance metrics."""
        now = time.time()
        cutoff_time = now - (3600 * self.metrics_retention_hours)  # Last N hours
        
        # Filter recent metrics
        recent_metrics = [m for m in self.health_metrics if m.timestamp > cutoff_time]
        
        if not recent_metrics:
            return {
                "status": "no_data",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        # Calculate performance statistics
        response_times = [m.response_time_ms for m in recent_metrics]
        successful_requests = [m for m in recent_metrics if m.success]
        failed_requests = [m for m in recent_metrics if not m.success]
        
        total_requests = len(recent_metrics)
        success_rate = len(successful_requests) / total_requests if total_requests > 0 else 0
        error_rate = len(failed_requests) / total_requests if total_requests > 0 else 0
        
        performance_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "time_window_hours": self.metrics_retention_hours,
            "total_requests": total_requests,
            "successful_requests": len(successful_requests),
            "failed_requests": len(failed_requests),
            "success_rate": round(success_rate, 4),
            "error_rate": round(error_rate, 4),
            "response_time_stats": {
                "min_ms": min(response_times) if response_times else 0,
                "max_ms": max(response_times) if response_times else 0,
                "avg_ms": round(statistics.mean(response_times), 1) if response_times else 0,
                "median_ms": round(statistics.median(response_times), 1) if response_times else 0,
                "p95_ms": round(statistics.quantiles(response_times, n=20)[18], 1) if len(response_times) > 20 else 0,
                "p99_ms": round(statistics.quantiles(response_times, n=100)[98], 1) if len(response_times) > 100 else 0
            }
        }
        
        # Check performance alerts
        await self._check_performance_alerts(performance_data)
        
        # Update performance data cache
        self.performance_data.update({
            "last_performance_check": performance_data,
            "response_times": response_times[-100:],  # Keep last 100
            "success_rates": self.performance_data["success_rates"][-24:] + [success_rate],  # Keep last 24 hours
            "uptime_data": self.performance_data["uptime_data"][-24:] + [{"timestamp": now, "healthy": success_rate > 0.95}]
        })
        
        self.last_performance_check = time.time()
        return performance_data
        
    async def _check_health_alerts(self, health_result: Dict[str, Any]):
        """Check for health-based alerts."""
        overall_status = health_result.get("overall_status")
        
        # Critical status alert
        if overall_status == "critical":
            await self._create_alert(
                alert_id="kong_critical_status",
                level=AlertLevel.CRITICAL,
                message="Kong Gateway is in critical state",
                data=health_result
            )
        elif overall_status == "degraded":
            await self._create_alert(
                alert_id="kong_degraded_status",
                level=AlertLevel.WARNING,
                message="Kong Gateway performance is degraded",
                data=health_result
            )
        else:
            # Clear existing alerts if healthy
            await self._clear_alert("kong_critical_status")
            await self._clear_alert("kong_degraded_status")
            
    async def _check_performance_alerts(self, performance_data: Dict[str, Any]):
        """Check for performance-based alerts."""
        error_rate = performance_data.get("error_rate", 0)
        avg_response_time = performance_data.get("response_time_stats", {}).get("avg_ms", 0)
        
        # Error rate alerts
        if error_rate >= self.error_rate_critical:
            await self._create_alert(
                alert_id="kong_high_error_rate",
                level=AlertLevel.CRITICAL,
                message=f"Kong error rate is critically high: {error_rate:.2%}",
                data=performance_data
            )
        elif error_rate >= self.error_rate_warning:
            await self._create_alert(
                alert_id="kong_high_error_rate",
                level=AlertLevel.WARNING,
                message=f"Kong error rate is elevated: {error_rate:.2%}",
                data=performance_data
            )
        else:
            await self._clear_alert("kong_high_error_rate")
            
        # Response time alerts
        if avg_response_time >= self.response_time_critical_ms:
            await self._create_alert(
                alert_id="kong_slow_response",
                level=AlertLevel.CRITICAL,
                message=f"Kong response time is critically slow: {avg_response_time}ms",
                data=performance_data
            )
        elif avg_response_time >= self.response_time_warning_ms:
            await self._create_alert(
                alert_id="kong_slow_response",
                level=AlertLevel.WARNING,
                message=f"Kong response time is slow: {avg_response_time}ms",
                data=performance_data
            )
        else:
            await self._clear_alert("kong_slow_response")
            
    async def _create_alert(self, alert_id: str, level: AlertLevel, message: str, data: Dict[str, Any]):
        """Create or update an alert."""
        alert = {
            "id": alert_id,
            "level": level.value,
            "message": message,
            "data": data,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        if alert_id not in self.active_alerts:
            # New alert
            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert.copy())
            logger.error(f"🚨 ALERT [{level.value.upper()}]: {message}")
        else:
            # Update existing alert
            self.active_alerts[alert_id].update({
                "message": message,
                "data": data,
                "updated_at": datetime.utcnow().isoformat()
            })
            
    async def _clear_alert(self, alert_id: str):
        """Clear an active alert."""
        if alert_id in self.active_alerts:
            alert = self.active_alerts.pop(alert_id)
            alert["resolved_at"] = datetime.utcnow().isoformat()
            self.alert_history.append(alert)
            logger.info(f"✅ RESOLVED: Alert {alert_id} cleared")
            
    async def _cleanup_old_metrics(self):
        """Clean up old health metrics."""
        cutoff_time = time.time() - (3600 * self.metrics_retention_hours)
        
        initial_count = len(self.health_metrics)
        self.health_metrics = [m for m in self.health_metrics if m.timestamp > cutoff_time]
        
        cleaned_count = initial_count - len(self.health_metrics)
        if cleaned_count > 0:
            logger.debug(f"🧹 Cleaned up {cleaned_count} old health metrics")
            
        # Clean up alert history (keep last 100)
        if len(self.alert_history) > 100:
            self.alert_history = self.alert_history[-100:]
            
    async def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive health summary."""
        return {
            "monitoring_active": self.monitoring_active,
            "last_health_check": (
                datetime.fromtimestamp(self.last_health_check).isoformat() 
                if self.last_health_check else None
            ),
            "last_performance_check": (
                datetime.fromtimestamp(self.last_performance_check).isoformat() 
                if self.last_performance_check else None
            ),
            "metrics_count": len(self.health_metrics),
            "active_alerts": list(self.active_alerts.values()),
            "recent_performance": self.performance_data.get("last_performance_check"),
            "configuration": {
                "health_check_interval": self.health_check_interval,
                "performance_check_interval": self.performance_check_interval,
                "metrics_retention_hours": self.metrics_retention_hours,
                "response_time_warning_ms": self.response_time_warning_ms,
                "response_time_critical_ms": self.response_time_critical_ms,
                "error_rate_warning": self.error_rate_warning,
                "error_rate_critical": self.error_rate_critical
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    async def get_performance_metrics(self, hours: int = 1) -> Dict[str, Any]:
        """Get detailed performance metrics for specified time window."""
        cutoff_time = time.time() - (3600 * hours)
        recent_metrics = [m for m in self.health_metrics if m.timestamp > cutoff_time]
        
        if not recent_metrics:
            return {"error": "No metrics available for specified time window"}
            
        # Calculate detailed metrics
        response_times = [m.response_time_ms for m in recent_metrics]
        success_count = sum(1 for m in recent_metrics if m.success)
        total_count = len(recent_metrics)
        
        return {
            "time_window_hours": hours,
            "total_requests": total_count,
            "successful_requests": success_count,
            "failed_requests": total_count - success_count,
            "success_rate": success_count / total_count if total_count > 0 else 0,
            "response_times": {
                "min": min(response_times) if response_times else 0,
                "max": max(response_times) if response_times else 0,
                "avg": statistics.mean(response_times) if response_times else 0,
                "median": statistics.median(response_times) if response_times else 0
            },
            "error_analysis": self._analyze_errors(recent_metrics),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    def _analyze_errors(self, metrics: List[HealthMetric]) -> Dict[str, Any]:
        """Analyze error patterns in metrics."""
        failed_metrics = [m for m in metrics if not m.success]
        
        if not failed_metrics:
            return {"total_errors": 0}
            
        error_types = {}
        for metric in failed_metrics:
            error_msg = metric.error_message or "Unknown error"
            error_types[error_msg] = error_types.get(error_msg, 0) + 1
            
        return {
            "total_errors": len(failed_metrics),
            "error_types": error_types,
            "error_rate_trend": "increasing" if len(failed_metrics) > 0 else "stable"
        }
        
    async def __aenter__(self):
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop_monitoring()
        await self.client.aclose()


# Global health monitor instance
kong_health_monitor = KongHealthMonitor()