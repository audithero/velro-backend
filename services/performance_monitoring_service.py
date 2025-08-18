"""
Enterprise Performance Monitoring Service
Implements real-time performance monitoring, alerting, and optimization recommendations
as specified in UUID Validation Standards for 81% performance improvement.
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import statistics
from collections import defaultdict, deque

from database import get_database
from utils.redis_cache_manager import enterprise_redis_cache
from utils.enterprise_db_pool import enterprise_pool_manager
from utils.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class PerformanceTier(Enum):
    """Performance classification tiers."""
    EXCELLENT = "excellent"      # Sub-25ms authorization
    GOOD = "good"               # 25-50ms authorization
    ACCEPTABLE = "acceptable"   # 50-100ms authorization
    NEEDS_OPTIMIZATION = "needs_optimization"  # >100ms authorization


@dataclass
class PerformanceTarget:
    """Performance target definition."""
    metric_name: str
    target_value: float
    warning_threshold: float
    critical_threshold: float
    unit: str
    comparison_operator: str = ">"
    description: str = ""


@dataclass
class PerformanceAlert:
    """Performance alert definition."""
    alert_id: str
    metric_name: str
    alert_level: AlertLevel
    current_value: float
    threshold_value: float
    message: str
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics snapshot."""
    timestamp: datetime
    authorization_performance: Dict[str, float]
    cache_performance: Dict[str, float]
    database_performance: Dict[str, float]
    system_health: Dict[str, Any]
    performance_tier: PerformanceTier
    recommendations: List[str]


class PerformanceMonitoringService:
    """
    Enterprise performance monitoring service with:
    - Real-time metrics collection
    - Automated alerting system
    - Performance optimization recommendations
    - Historical trend analysis
    - Predictive performance modeling
    """
    
    def __init__(self):
        self.metrics_history: deque = deque(maxlen=1000)  # Keep last 1000 measurements
        self.active_alerts: Dict[str, PerformanceAlert] = {}
        self.alert_callbacks: List[Callable] = []
        self.monitoring_enabled = True
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Performance targets as defined in UUID Validation Standards
        self.performance_targets = {
            "authorization_avg_response_time_ms": PerformanceTarget(
                "authorization_avg_response_time_ms", 75.0, 75.0, 100.0, "ms", ">",
                "Average authorization response time should be under 75ms"
            ),
            "authorization_p95_response_time_ms": PerformanceTarget(
                "authorization_p95_response_time_ms", 100.0, 150.0, 200.0, "ms", ">",
                "95th percentile authorization response time should be under 100ms"
            ),
            "cache_hit_rate_percent": PerformanceTarget(
                "cache_hit_rate_percent", 95.0, 90.0, 85.0, "%", "<",
                "Cache hit rate should be above 95%"
            ),
            "authorization_error_rate_percent": PerformanceTarget(
                "authorization_error_rate_percent", 2.0, 5.0, 10.0, "%", ">",
                "Authorization error rate should be below 2%"
            ),
            "concurrent_requests_capacity": PerformanceTarget(
                "concurrent_requests_capacity", 10000, 8000, 6000, "requests", "<",
                "System should handle 10,000+ concurrent requests"
            ),
            "database_connection_pool_utilization": PerformanceTarget(
                "database_connection_pool_utilization", 80.0, 80.0, 90.0, "%", ">",
                "Database connection pool utilization should be below 80%"
            )
        }
        
    async def initialize(self) -> None:
        """Initialize the performance monitoring service."""
        try:
            logger.info("🔄 Initializing Performance Monitoring Service")
            
            # Verify database performance thresholds are configured
            await self._ensure_performance_thresholds()
            
            # Start monitoring task
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            logger.info("✅ Performance Monitoring Service initialized")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Performance Monitoring Service: {e}")
            raise
    
    async def _ensure_performance_thresholds(self) -> None:
        """Ensure performance thresholds are configured in the database."""
        try:
            db = await get_database()
            
            for metric_name, target in self.performance_targets.items():
                # Check if threshold exists
                existing = await db.execute_query(
                    table="performance_thresholds",
                    operation="select",
                    filters={"metric_name": metric_name}
                )
                
                if not existing:
                    # Insert new threshold
                    await db.execute_query(
                        table="performance_thresholds",
                        operation="insert",
                        data={
                            "metric_name": metric_name,
                            "warning_threshold": target.warning_threshold,
                            "critical_threshold": target.critical_threshold,
                            "unit": target.unit,
                            "comparison_operator": target.comparison_operator,
                            "enabled": True
                        }
                    )
                    
        except Exception as e:
            logger.error(f"❌ Failed to configure performance thresholds: {e}")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop for continuous performance measurement."""
        while self.monitoring_enabled:
            try:
                # Collect comprehensive performance metrics
                metrics = await self.collect_comprehensive_metrics()
                
                # Store metrics history
                self.metrics_history.append(metrics)
                
                # Check for threshold violations
                await self._check_performance_thresholds(metrics)
                
                # Log performance metrics to database
                await self._log_performance_metrics(metrics)
                
                # Generate optimization recommendations
                recommendations = await self._generate_optimization_recommendations(metrics)
                if recommendations:
                    logger.info(f"💡 Performance Recommendations: {', '.join(recommendations[:3])}")
                
                # Wait for next monitoring cycle (every 30 seconds for real-time monitoring)
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Performance monitoring error: {e}")
                await asyncio.sleep(60)  # Back off on errors
    
    async def collect_comprehensive_metrics(self) -> PerformanceMetrics:
        """Collect comprehensive performance metrics from all subsystems."""
        timestamp = datetime.utcnow()
        
        try:
            # Authorization performance metrics
            auth_metrics = await self._collect_authorization_metrics()
            
            # Cache performance metrics
            cache_metrics = await self._collect_cache_metrics()
            
            # Database performance metrics
            db_metrics = await self._collect_database_metrics()
            
            # System health metrics
            system_metrics = await self._collect_system_health_metrics()
            
            # Determine overall performance tier
            performance_tier = self._calculate_performance_tier(auth_metrics, cache_metrics)
            
            # Generate recommendations
            recommendations = await self._generate_optimization_recommendations_from_metrics(
                auth_metrics, cache_metrics, db_metrics, system_metrics
            )
            
            return PerformanceMetrics(
                timestamp=timestamp,
                authorization_performance=auth_metrics,
                cache_performance=cache_metrics,
                database_performance=db_metrics,
                system_health=system_metrics,
                performance_tier=performance_tier,
                recommendations=recommendations
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to collect comprehensive metrics: {e}")
            return PerformanceMetrics(
                timestamp=timestamp,
                authorization_performance={},
                cache_performance={},
                database_performance={},
                system_health={"error": str(e)},
                performance_tier=PerformanceTier.NEEDS_OPTIMIZATION,
                recommendations=["Unable to collect metrics - investigate monitoring system"]
            )
    
    async def _collect_authorization_metrics(self) -> Dict[str, float]:
        """Collect authorization performance metrics."""
        try:
            db = await get_database()
            
            # Query recent authorization performance data
            recent_perfs = await db.execute_raw_query("""
                SELECT 
                    AVG(execution_time_ms) as avg_response_time,
                    PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY execution_time_ms) as p95_response_time,
                    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY execution_time_ms) as p99_response_time,
                    COUNT(*) as total_requests,
                    COUNT(*) FILTER (WHERE success = true) as successful_requests,
                    COUNT(*) FILTER (WHERE success = false) as failed_requests,
                    COUNT(*) FILTER (WHERE cache_hit = true) as cache_hits,
                    COUNT(*) FILTER (WHERE execution_time_ms > 100) as slow_queries
                FROM authorization_performance_realtime 
                WHERE created_at >= NOW() - INTERVAL '5 minutes'
            """)
            
            if recent_perfs:
                perf = recent_perfs[0]
                total_requests = perf.get("total_requests", 0)
                successful_requests = perf.get("successful_requests", 0)
                failed_requests = perf.get("failed_requests", 0)
                cache_hits = perf.get("cache_hits", 0)
                slow_queries = perf.get("slow_queries", 0)
                
                return {
                    "avg_response_time_ms": float(perf.get("avg_response_time", 0) or 0),
                    "p95_response_time_ms": float(perf.get("p95_response_time", 0) or 0),
                    "p99_response_time_ms": float(perf.get("p99_response_time", 0) or 0),
                    "total_requests": total_requests,
                    "success_rate_percent": (successful_requests / max(total_requests, 1)) * 100,
                    "error_rate_percent": (failed_requests / max(total_requests, 1)) * 100,
                    "cache_hit_rate_percent": (cache_hits / max(total_requests, 1)) * 100,
                    "slow_query_rate_percent": (slow_queries / max(total_requests, 1)) * 100,
                    "requests_per_second": total_requests / 300.0  # 5 minute window
                }
            
            return {
                "avg_response_time_ms": 0,
                "p95_response_time_ms": 0,
                "p99_response_time_ms": 0,
                "total_requests": 0,
                "success_rate_percent": 100,
                "error_rate_percent": 0,
                "cache_hit_rate_percent": 0,
                "slow_query_rate_percent": 0,
                "requests_per_second": 0
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to collect authorization metrics: {e}")
            return {}
    
    async def _collect_cache_metrics(self) -> Dict[str, float]:
        """Collect cache performance metrics."""
        try:
            cache_metrics = await enterprise_redis_cache.get_cache_metrics()
            
            aggregated_metrics = {
                "overall_hit_rate_percent": 0,
                "total_operations": 0,
                "total_hits": 0,
                "total_misses": 0,
                "total_errors": 0,
                "avg_response_time_ms": 0,
                "l1_cache_entries": 0,
                "circuit_breaker_failures": 0
            }
            
            total_ops = 0
            total_hits = 0
            total_response_time = 0
            
            for cache_name, metrics in cache_metrics.items():
                ops = metrics.get("total_operations", 0)
                hits = metrics.get("hits", 0)
                response_time = metrics.get("avg_response_time_ms", 0)
                
                total_ops += ops
                total_hits += hits
                total_response_time += response_time * ops
                
                aggregated_metrics["total_operations"] += ops
                aggregated_metrics["total_hits"] += hits
                aggregated_metrics["total_misses"] += metrics.get("misses", 0)
                aggregated_metrics["total_errors"] += metrics.get("errors", 0)
                aggregated_metrics["l1_cache_entries"] += metrics.get("l1_cache_size", 0)
                
                if metrics.get("circuit_breaker_state") == "open":
                    aggregated_metrics["circuit_breaker_failures"] += 1
            
            if total_ops > 0:
                aggregated_metrics["overall_hit_rate_percent"] = (total_hits / total_ops) * 100
                aggregated_metrics["avg_response_time_ms"] = total_response_time / total_ops
            
            return aggregated_metrics
            
        except Exception as e:
            logger.error(f"❌ Failed to collect cache metrics: {e}")
            return {}
    
    async def _collect_database_metrics(self) -> Dict[str, float]:
        """Collect database performance metrics."""
        try:
            pool_metrics = await enterprise_pool_manager.get_all_metrics()
            health_summary = await enterprise_pool_manager.get_health_summary()
            
            # Aggregate metrics across all pools
            total_connections = 0
            active_connections = 0
            total_queries = 0
            slow_queries = 0
            connection_errors = 0
            pool_exhaustion_events = 0
            
            avg_query_times = []
            
            for pool_name, metrics in pool_metrics.items():
                connections = metrics.get("connections", {})
                performance = metrics.get("performance", {})
                errors = metrics.get("errors", {})
                
                total_connections += connections.get("total", 0)
                active_connections += connections.get("active", 0)
                total_queries += performance.get("queries_executed", 0)
                slow_queries += performance.get("slow_queries", 0)
                connection_errors += errors.get("connection_errors", 0)
                pool_exhaustion_events += errors.get("pool_exhaustion_events", 0)
                
                if performance.get("avg_query_time_ms", 0) > 0:
                    avg_query_times.append(performance["avg_query_time_ms"])
            
            return {
                "connection_pool_utilization_percent": health_summary["connections"]["utilization_percent"],
                "total_connections": total_connections,
                "active_connections": active_connections,
                "total_queries": total_queries,
                "slow_query_rate_percent": (slow_queries / max(total_queries, 1)) * 100,
                "connection_error_rate": connection_errors / max(total_queries, 1),
                "pool_exhaustion_events": pool_exhaustion_events,
                "avg_query_time_ms": statistics.mean(avg_query_times) if avg_query_times else 0,
                "healthy_pools": health_summary["pools"]["healthy"],
                "total_pools": health_summary["pools"]["total"]
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to collect database metrics: {e}")
            return {}
    
    async def _collect_system_health_metrics(self) -> Dict[str, Any]:
        """Collect system health metrics."""
        try:
            import psutil
            
            # CPU and memory usage
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Network statistics
            network = psutil.net_io_counters()
            
            return {
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": memory.percent,
                "memory_available_mb": memory.available // 1024 // 1024,
                "disk_usage_percent": (disk.used / disk.total) * 100,
                "disk_free_gb": disk.free // 1024 // 1024 // 1024,
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv,
                "load_average": psutil.getloadavg()[0] if hasattr(psutil, 'getloadavg') else 0,
                "process_count": len(psutil.pids()),
                "uptime_seconds": time.time() - psutil.boot_time()
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to collect system health metrics: {e}")
            return {"error": str(e)}
    
    def _calculate_performance_tier(
        self, 
        auth_metrics: Dict[str, float], 
        cache_metrics: Dict[str, float]
    ) -> PerformanceTier:
        """Calculate overall performance tier based on key metrics."""
        try:
            avg_response = auth_metrics.get("avg_response_time_ms", 1000)
            p95_response = auth_metrics.get("p95_response_time_ms", 1000)
            cache_hit_rate = cache_metrics.get("overall_hit_rate_percent", 0)
            error_rate = auth_metrics.get("error_rate_percent", 100)
            
            # Excellent: Sub-25ms average, sub-50ms P95, >95% cache hits, <1% errors
            if (avg_response < 25 and p95_response < 50 and 
                cache_hit_rate > 95 and error_rate < 1):
                return PerformanceTier.EXCELLENT
            
            # Good: Sub-50ms average, sub-100ms P95, >90% cache hits, <2% errors
            elif (avg_response < 50 and p95_response < 100 and 
                  cache_hit_rate > 90 and error_rate < 2):
                return PerformanceTier.GOOD
            
            # Acceptable: Sub-100ms average, sub-200ms P95, >80% cache hits, <5% errors
            elif (avg_response < 100 and p95_response < 200 and 
                  cache_hit_rate > 80 and error_rate < 5):
                return PerformanceTier.ACCEPTABLE
            
            else:
                return PerformanceTier.NEEDS_OPTIMIZATION
                
        except Exception as e:
            logger.error(f"❌ Failed to calculate performance tier: {e}")
            return PerformanceTier.NEEDS_OPTIMIZATION
    
    async def _check_performance_thresholds(self, metrics: PerformanceMetrics) -> None:
        """Check performance metrics against thresholds and trigger alerts."""
        try:
            current_values = {
                "authorization_avg_response_time_ms": metrics.authorization_performance.get("avg_response_time_ms", 0),
                "authorization_p95_response_time_ms": metrics.authorization_performance.get("p95_response_time_ms", 0),
                "cache_hit_rate_percent": metrics.cache_performance.get("overall_hit_rate_percent", 0),
                "authorization_error_rate_percent": metrics.authorization_performance.get("error_rate_percent", 0),
                "database_connection_pool_utilization": metrics.database_performance.get("connection_pool_utilization_percent", 0)
            }
            
            for metric_name, current_value in current_values.items():
                if metric_name in self.performance_targets:
                    target = self.performance_targets[metric_name]
                    
                    # Check critical threshold
                    if self._exceeds_threshold(current_value, target.critical_threshold, target.comparison_operator):
                        await self._trigger_alert(
                            metric_name, AlertLevel.CRITICAL, current_value, 
                            target.critical_threshold, target.description
                        )
                    # Check warning threshold
                    elif self._exceeds_threshold(current_value, target.warning_threshold, target.comparison_operator):
                        await self._trigger_alert(
                            metric_name, AlertLevel.WARNING, current_value,
                            target.warning_threshold, target.description
                        )
                    else:
                        # Resolve any existing alerts for this metric
                        await self._resolve_alert(metric_name)
            
        except Exception as e:
            logger.error(f"❌ Failed to check performance thresholds: {e}")
    
    def _exceeds_threshold(self, current_value: float, threshold: float, operator: str) -> bool:
        """Check if current value exceeds threshold based on operator."""
        if operator == ">":
            return current_value > threshold
        elif operator == "<":
            return current_value < threshold
        elif operator == ">=":
            return current_value >= threshold
        elif operator == "<=":
            return current_value <= threshold
        elif operator == "=":
            return current_value == threshold
        return False
    
    async def _trigger_alert(
        self, 
        metric_name: str, 
        alert_level: AlertLevel, 
        current_value: float,
        threshold_value: float, 
        description: str
    ) -> None:
        """Trigger a performance alert."""
        try:
            alert_id = f"{metric_name}_{alert_level.value}_{int(time.time())}"
            
            alert = PerformanceAlert(
                alert_id=alert_id,
                metric_name=metric_name,
                alert_level=alert_level,
                current_value=current_value,
                threshold_value=threshold_value,
                message=f"{alert_level.value.upper()} Alert: {description}. Current: {current_value}, Threshold: {threshold_value}",
                triggered_at=datetime.utcnow(),
                metadata={
                    "performance_tier": self.metrics_history[-1].performance_tier.value if self.metrics_history else "unknown"
                }
            )
            
            # Check if similar alert already exists
            existing_alert_key = f"{metric_name}_{alert_level.value}"
            if existing_alert_key not in self.active_alerts:
                self.active_alerts[existing_alert_key] = alert
                
                # Log alert to database
                await self._log_alert_to_database(alert)
                
                # Notify alert callbacks
                await self._notify_alert_callbacks(alert)
                
                logger.warning(f"🚨 {alert.message}")
            
        except Exception as e:
            logger.error(f"❌ Failed to trigger alert: {e}")
    
    async def _resolve_alert(self, metric_name: str) -> None:
        """Resolve any active alerts for a metric."""
        try:
            resolved_alerts = []
            for key, alert in self.active_alerts.items():
                if alert.metric_name == metric_name:
                    alert.resolved_at = datetime.utcnow()
                    resolved_alerts.append(key)
                    
                    # Update database
                    await self._update_alert_in_database(alert)
                    
                    logger.info(f"✅ Resolved alert: {alert.message}")
            
            # Remove resolved alerts
            for key in resolved_alerts:
                del self.active_alerts[key]
                
        except Exception as e:
            logger.error(f"❌ Failed to resolve alert: {e}")
    
    async def _log_alert_to_database(self, alert: PerformanceAlert) -> None:
        """Log alert to database for tracking."""
        try:
            db = await get_database()
            await db.execute_query(
                table="performance_alerts",
                operation="insert",
                data={
                    "metric_name": alert.metric_name,
                    "alert_level": alert.alert_level.value,
                    "current_value": alert.current_value,
                    "threshold_value": alert.threshold_value,
                    "message": alert.message,
                    "alert_triggered_at": alert.triggered_at,
                    "escalation_level": 1
                }
            )
        except Exception as e:
            logger.error(f"❌ Failed to log alert to database: {e}")
    
    async def _update_alert_in_database(self, alert: PerformanceAlert) -> None:
        """Update alert resolution in database."""
        try:
            db = await get_database()
            await db.execute_query(
                table="performance_alerts",
                operation="update",
                filters={
                    "metric_name": alert.metric_name,
                    "alert_level": alert.alert_level.value,
                    "alert_resolved_at": None
                },
                data={
                    "alert_resolved_at": alert.resolved_at,
                    "resolution_time_minutes": int((alert.resolved_at - alert.triggered_at).total_seconds() / 60)
                }
            )
        except Exception as e:
            logger.error(f"❌ Failed to update alert in database: {e}")
    
    async def _notify_alert_callbacks(self, alert: PerformanceAlert) -> None:
        """Notify registered alert callbacks."""
        for callback in self.alert_callbacks:
            try:
                await callback(alert)
            except Exception as e:
                logger.error(f"❌ Alert callback failed: {e}")
    
    async def _log_performance_metrics(self, metrics: PerformanceMetrics) -> None:
        """Log performance metrics to database."""
        try:
            # This would typically be logged to a time-series database for efficient storage
            # For now, we'll use the existing authorization_performance_realtime table
            db = await get_database()
            
            await db.execute_query(
                table="authorization_performance_realtime",
                operation="insert",
                data={
                    "operation_type": "system_monitoring",
                    "resource_type": "system",
                    "execution_time_ms": metrics.authorization_performance.get("avg_response_time_ms", 0),
                    "cache_hit": metrics.cache_performance.get("overall_hit_rate_percent", 0) > 90,
                    "database_queries": metrics.database_performance.get("total_queries", 0),
                    "authorization_method": f"tier_{metrics.performance_tier.value}",
                    "success": metrics.authorization_performance.get("error_rate_percent", 0) < 5,
                    "memory_usage_kb": metrics.system_health.get("memory_available_mb", 0) * 1024,
                    "request_id": f"monitoring_{int(time.time())}"
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Failed to log performance metrics: {e}")
    
    async def _generate_optimization_recommendations(self, metrics: PerformanceMetrics) -> List[str]:
        """Generate optimization recommendations based on metrics."""
        return await self._generate_optimization_recommendations_from_metrics(
            metrics.authorization_performance,
            metrics.cache_performance, 
            metrics.database_performance,
            metrics.system_health
        )
    
    async def _generate_optimization_recommendations_from_metrics(
        self,
        auth_metrics: Dict[str, float],
        cache_metrics: Dict[str, float],
        db_metrics: Dict[str, float],
        system_metrics: Dict[str, Any]
    ) -> List[str]:
        """Generate specific optimization recommendations."""
        recommendations = []
        
        try:
            # Authorization performance recommendations
            avg_response = auth_metrics.get("avg_response_time_ms", 0)
            if avg_response > 100:
                recommendations.append("🚀 Authorization response time is high - consider adding more L1 cache")
            elif avg_response > 50:
                recommendations.append("⚡ Consider optimizing authorization queries with better indexing")
            
            # Cache performance recommendations  
            cache_hit_rate = cache_metrics.get("overall_hit_rate_percent", 0)
            if cache_hit_rate < 85:
                recommendations.append("📈 Cache hit rate is low - review TTL settings and cache warming strategies")
            elif cache_hit_rate < 95:
                recommendations.append("🎯 Optimize cache key patterns and invalidation strategies")
            
            # Database performance recommendations
            pool_utilization = db_metrics.get("connection_pool_utilization_percent", 0)
            if pool_utilization > 90:
                recommendations.append("🔧 Database connection pool utilization is high - consider increasing pool size")
            elif pool_utilization > 80:
                recommendations.append("📊 Monitor database connection pool - approaching capacity limits")
            
            slow_query_rate = db_metrics.get("slow_query_rate_percent", 0)
            if slow_query_rate > 10:
                recommendations.append("🐌 High slow query rate - review query optimization and indexing strategies")
            
            # System health recommendations
            cpu_usage = system_metrics.get("cpu_usage_percent", 0)
            memory_usage = system_metrics.get("memory_usage_percent", 0)
            
            if cpu_usage > 80:
                recommendations.append("🔥 High CPU usage - consider horizontal scaling or optimization")
            if memory_usage > 85:
                recommendations.append("💾 High memory usage - review memory allocation and garbage collection")
            
            # Error rate recommendations
            error_rate = auth_metrics.get("error_rate_percent", 0)
            if error_rate > 5:
                recommendations.append("❌ High error rate - investigate authorization failures and improve validation")
            
            # Performance tier-specific recommendations
            if len(recommendations) == 0:
                if avg_response < 25 and cache_hit_rate > 95:
                    recommendations.append("✅ Excellent performance - maintain current optimization strategies")
                elif avg_response < 75:
                    recommendations.append("✨ Good performance - consider fine-tuning for excellence tier")
                
        except Exception as e:
            logger.error(f"❌ Failed to generate recommendations: {e}")
            recommendations.append("🔍 Unable to generate recommendations - investigate monitoring system")
        
        return recommendations
    
    async def get_performance_analytics(self, time_window: timedelta = timedelta(hours=1)) -> Dict[str, Any]:
        """Get comprehensive performance analytics."""
        try:
            db = await get_database()
            
            # Get performance analytics from database function
            analytics = await db.execute_raw_query("""
                SELECT * FROM get_authorization_performance_analytics(%s)
            """, [str(time_window)])
            
            # Get current metrics
            current_metrics = await self.collect_comprehensive_metrics()
            
            # Calculate improvement metrics
            improvement_analysis = await self._calculate_performance_improvements()
            
            return {
                "current_performance": asdict(current_metrics),
                "analytics": analytics,
                "improvement_analysis": improvement_analysis,
                "active_alerts": [asdict(alert) for alert in self.active_alerts.values()],
                "recommendations": current_metrics.recommendations,
                "performance_targets": {
                    name: asdict(target) for name, target in self.performance_targets.items()
                },
                "monitoring_status": {
                    "enabled": self.monitoring_enabled,
                    "metrics_history_size": len(self.metrics_history),
                    "last_update": current_metrics.timestamp.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to get performance analytics: {e}")
            return {"error": str(e)}
    
    async def _calculate_performance_improvements(self) -> Dict[str, Any]:
        """Calculate performance improvements over time."""
        try:
            if len(self.metrics_history) < 10:
                return {"status": "insufficient_data", "message": "Need more data points for trend analysis"}
            
            # Get recent and older metrics for comparison
            recent_metrics = list(self.metrics_history)[-10:]  # Last 10 measurements
            older_metrics = list(self.metrics_history)[:10]    # First 10 measurements
            
            # Calculate averages
            recent_avg_response = statistics.mean([
                m.authorization_performance.get("avg_response_time_ms", 0) 
                for m in recent_metrics if m.authorization_performance.get("avg_response_time_ms", 0) > 0
            ])
            
            older_avg_response = statistics.mean([
                m.authorization_performance.get("avg_response_time_ms", 0)
                for m in older_metrics if m.authorization_performance.get("avg_response_time_ms", 0) > 0
            ])
            
            # Calculate improvement percentage
            if older_avg_response > 0:
                improvement_percent = ((older_avg_response - recent_avg_response) / older_avg_response) * 100
            else:
                improvement_percent = 0
            
            # Check if we've achieved the 81% improvement target
            target_achieved = improvement_percent >= 81
            
            return {
                "status": "sufficient_data",
                "improvement_percent": improvement_percent,
                "target_improvement_percent": 81,
                "target_achieved": target_achieved,
                "baseline_avg_response_ms": older_avg_response,
                "current_avg_response_ms": recent_avg_response,
                "measurement_period": {
                    "start": older_metrics[0].timestamp.isoformat() if older_metrics else None,
                    "end": recent_metrics[-1].timestamp.isoformat() if recent_metrics else None
                }
            }
            
        except Exception as e:
            logger.error(f"❌ Failed to calculate performance improvements: {e}")
            return {"status": "error", "message": str(e)}
    
    def register_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Register a callback for alert notifications."""
        self.alert_callbacks.append(callback)
    
    async def stop_monitoring(self) -> None:
        """Stop the performance monitoring service."""
        self.monitoring_enabled = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("🛑 Performance Monitoring Service stopped")


# Global instance
performance_monitoring_service = PerformanceMonitoringService()


# Convenience functions
async def get_current_performance_tier() -> PerformanceTier:
    """Get current performance tier."""
    if performance_monitoring_service.metrics_history:
        return performance_monitoring_service.metrics_history[-1].performance_tier
    return PerformanceTier.NEEDS_OPTIMIZATION


async def get_performance_dashboard() -> Dict[str, Any]:
    """Get comprehensive performance dashboard data."""
    return await performance_monitoring_service.get_performance_analytics()


async def check_performance_targets() -> Dict[str, bool]:
    """Check if all performance targets are being met."""
    analytics = await performance_monitoring_service.get_performance_analytics()
    current = analytics.get("current_performance", {})
    
    return {
        "sub_100ms_authorization": current.get("authorization_performance", {}).get("avg_response_time_ms", 1000) < 100,
        "95_percent_cache_hit": current.get("cache_performance", {}).get("overall_hit_rate_percent", 0) >= 95,
        "low_error_rate": current.get("authorization_performance", {}).get("error_rate_percent", 100) < 2,
        "healthy_pools": current.get("database_performance", {}).get("healthy_pools", 0) >= 4,
        "performance_tier_acceptable": current.get("performance_tier") in ["excellent", "good", "acceptable"]
    }