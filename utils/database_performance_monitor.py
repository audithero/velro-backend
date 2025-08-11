"""
Database Performance Monitoring and Alerting System
Monitors <20ms query performance targets and provides real-time alerts for degradation.
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
from collections import deque, defaultdict

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class PerformanceThreshold(Enum):
    """Performance threshold definitions."""
    AUTH_QUERY_MS = 20.0          # <20ms for auth queries
    GENERAL_QUERY_MS = 50.0       # <50ms for general queries  
    CACHE_HIT_RATE = 90.0         # >90% cache hit rate
    ERROR_RATE = 5.0              # <5% error rate
    CONNECTION_POOL_UTIL = 80.0   # <80% pool utilization


@dataclass
class PerformanceMetric:
    """Individual performance metric data point."""
    timestamp: datetime
    metric_name: str
    value: float
    context: Dict[str, Any] = field(default_factory=dict)
    query_type: str = "general"
    execution_time_ms: float = 0.0
    success: bool = True


@dataclass
class AlertRule:
    """Performance alert rule definition."""
    name: str
    metric_name: str
    threshold: float
    comparison: str  # "gt", "lt", "eq"
    alert_level: AlertLevel
    window_minutes: int = 5
    min_samples: int = 3
    enabled: bool = True
    callback: Optional[Callable] = None


@dataclass
class PerformanceAlert:
    """Performance alert instance."""
    rule_name: str
    alert_level: AlertLevel
    message: str
    metric_value: float
    threshold: float
    timestamp: datetime
    context: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class DatabasePerformanceMonitor:
    """
    Comprehensive database performance monitoring system.
    
    Features:
    - Real-time query performance tracking
    - Configurable alerting rules with thresholds
    - Performance trend analysis
    - Circuit breaker integration
    - Automatic performance reporting
    - Integration with external monitoring systems
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Performance data storage
        self.metrics_buffer = deque(maxlen=10000)  # Keep last 10k metrics
        self.metrics_by_type = defaultdict(lambda: deque(maxlen=1000))
        
        # Alert system
        self.alert_rules = []
        self.active_alerts = {}
        self.alert_history = deque(maxlen=1000)
        self.alert_callbacks = []
        
        # Performance statistics
        self.performance_stats = {
            "total_queries": 0,
            "auth_queries": 0,
            "general_queries": 0,
            "cache_hits": 0,
            "errors": 0,
            "avg_auth_time_ms": 0.0,
            "avg_general_time_ms": 0.0,
            "avg_cache_hit_rate": 0.0,
            "performance_targets_met": True,
            "last_updated": datetime.utcnow()
        }
        
        # Monitoring state
        self.monitoring_active = False
        self.monitoring_task = None
        self.lock = threading.RLock()
        
        # Initialize default alert rules
        self._initialize_default_rules()
        
        logger.info("🔍 [PERF_MON] Database Performance Monitor initialized")
    
    def _initialize_default_rules(self):
        """Initialize default performance alert rules."""
        default_rules = [
            AlertRule(
                name="auth_query_performance",
                metric_name="auth_query_time_ms",
                threshold=PerformanceThreshold.AUTH_QUERY_MS.value,
                comparison="gt",
                alert_level=AlertLevel.WARNING,
                window_minutes=2,
                min_samples=3
            ),
            AlertRule(
                name="general_query_performance", 
                metric_name="general_query_time_ms",
                threshold=PerformanceThreshold.GENERAL_QUERY_MS.value,
                comparison="gt",
                alert_level=AlertLevel.WARNING,
                window_minutes=5,
                min_samples=5
            ),
            AlertRule(
                name="cache_hit_rate",
                metric_name="cache_hit_rate",
                threshold=PerformanceThreshold.CACHE_HIT_RATE.value,
                comparison="lt",
                alert_level=AlertLevel.CRITICAL,
                window_minutes=10,
                min_samples=10
            ),
            AlertRule(
                name="error_rate",
                metric_name="error_rate",
                threshold=PerformanceThreshold.ERROR_RATE.value,
                comparison="gt",
                alert_level=AlertLevel.CRITICAL,
                window_minutes=5,
                min_samples=5
            ),
            AlertRule(
                name="extreme_auth_latency",
                metric_name="auth_query_time_ms",
                threshold=100.0,  # >100ms is extreme for auth
                comparison="gt",
                alert_level=AlertLevel.EMERGENCY,
                window_minutes=1,
                min_samples=1
            )
        ]
        
        self.alert_rules.extend(default_rules)
        logger.info(f"✅ [PERF_MON] Initialized {len(default_rules)} default alert rules")
    
    async def start_monitoring(self):
        """Start the performance monitoring system."""
        if self.monitoring_active:
            logger.warning("⚠️ [PERF_MON] Monitoring already active")
            return
        
        try:
            self.monitoring_active = True
            
            # Start monitoring tasks
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            logger.info("🚀 [PERF_MON] Performance monitoring started")
            
        except Exception as e:
            logger.error(f"❌ [PERF_MON] Failed to start monitoring: {e}")
            self.monitoring_active = False
            raise
    
    async def stop_monitoring(self):
        """Stop the performance monitoring system."""
        if not self.monitoring_active:
            return
        
        try:
            self.monitoring_active = False
            
            if self.monitoring_task:
                self.monitoring_task.cancel()
                try:
                    await self.monitoring_task
                except asyncio.CancelledError:
                    pass
            
            logger.info("🔄 [PERF_MON] Performance monitoring stopped")
            
        except Exception as e:
            logger.error(f"❌ [PERF_MON] Error stopping monitoring: {e}")
    
    def record_query_performance(
        self,
        query_type: str,
        execution_time_ms: float,
        success: bool = True,
        context: Optional[Dict[str, Any]] = None,
        cache_hit: bool = False
    ):
        """Record a database query performance metric."""
        try:
            with self.lock:
                metric = PerformanceMetric(
                    timestamp=datetime.utcnow(),
                    metric_name=f"{query_type}_query_time_ms",
                    value=execution_time_ms,
                    context=context or {},
                    query_type=query_type,
                    execution_time_ms=execution_time_ms,
                    success=success
                )
                
                # Store metric
                self.metrics_buffer.append(metric)
                self.metrics_by_type[query_type].append(metric)
                
                # Update statistics
                self._update_performance_stats(metric, cache_hit)
                
                # Check alert rules
                self._check_alert_rules(metric)
                
                # Log slow queries
                if query_type == "auth" and execution_time_ms > 20:
                    logger.warning(f"🐌 [PERF_MON] Slow auth query: {execution_time_ms:.1f}ms (target: <20ms)")
                elif query_type == "general" and execution_time_ms > 50:
                    logger.warning(f"🐌 [PERF_MON] Slow general query: {execution_time_ms:.1f}ms (target: <50ms)")
                
        except Exception as e:
            logger.error(f"❌ [PERF_MON] Error recording performance metric: {e}")
    
    def record_cache_performance(self, cache_hit: bool, lookup_time_ms: float = 0.0):
        """Record cache performance metric."""
        try:
            metric = PerformanceMetric(
                timestamp=datetime.utcnow(),
                metric_name="cache_lookup_time_ms",
                value=lookup_time_ms,
                context={"cache_hit": cache_hit}
            )
            
            with self.lock:
                self.metrics_buffer.append(metric)
                self.performance_stats["total_queries"] += 1
                
                if cache_hit:
                    self.performance_stats["cache_hits"] += 1
                
                # Update cache hit rate
                if self.performance_stats["total_queries"] > 0:
                    hit_rate = (self.performance_stats["cache_hits"] / self.performance_stats["total_queries"]) * 100
                    self.performance_stats["avg_cache_hit_rate"] = hit_rate
                    
                    # Check cache hit rate alert
                    cache_metric = PerformanceMetric(
                        timestamp=datetime.utcnow(),
                        metric_name="cache_hit_rate",
                        value=hit_rate
                    )
                    self._check_alert_rules(cache_metric)
                
        except Exception as e:
            logger.error(f"❌ [PERF_MON] Error recording cache metric: {e}")
    
    def record_connection_pool_metrics(self, pool_name: str, active: int, total: int, wait_time_ms: float = 0.0):
        """Record connection pool performance metrics."""
        try:
            utilization = (active / total * 100) if total > 0 else 0
            
            metrics = [
                PerformanceMetric(
                    timestamp=datetime.utcnow(),
                    metric_name="connection_pool_utilization",
                    value=utilization,
                    context={"pool_name": pool_name, "active": active, "total": total}
                ),
                PerformanceMetric(
                    timestamp=datetime.utcnow(),
                    metric_name="connection_wait_time_ms",
                    value=wait_time_ms,
                    context={"pool_name": pool_name}
                )
            ]
            
            with self.lock:
                for metric in metrics:
                    self.metrics_buffer.append(metric)
                    self._check_alert_rules(metric)
                
        except Exception as e:
            logger.error(f"❌ [PERF_MON] Error recording pool metrics: {e}")
    
    def _update_performance_stats(self, metric: PerformanceMetric, cache_hit: bool = False):
        """Update aggregated performance statistics."""
        self.performance_stats["total_queries"] += 1
        
        if cache_hit:
            self.performance_stats["cache_hits"] += 1
        
        if not metric.success:
            self.performance_stats["errors"] += 1
        
        if metric.query_type == "auth":
            self.performance_stats["auth_queries"] += 1
            # Update rolling average
            current_avg = self.performance_stats["avg_auth_time_ms"]
            auth_count = self.performance_stats["auth_queries"]
            self.performance_stats["avg_auth_time_ms"] = (
                (current_avg * (auth_count - 1) + metric.execution_time_ms) / auth_count
            )
        else:
            self.performance_stats["general_queries"] += 1
            # Update rolling average
            current_avg = self.performance_stats["avg_general_time_ms"]
            general_count = self.performance_stats["general_queries"]
            self.performance_stats["avg_general_time_ms"] = (
                (current_avg * (general_count - 1) + metric.execution_time_ms) / general_count
            )
        
        # Update cache hit rate
        if self.performance_stats["total_queries"] > 0:
            self.performance_stats["avg_cache_hit_rate"] = (
                self.performance_stats["cache_hits"] / self.performance_stats["total_queries"] * 100
            )
        
        # Check overall performance targets
        auth_ok = self.performance_stats["avg_auth_time_ms"] <= 20.0
        general_ok = self.performance_stats["avg_general_time_ms"] <= 50.0
        cache_ok = self.performance_stats["avg_cache_hit_rate"] >= 90.0
        error_rate = (self.performance_stats["errors"] / max(self.performance_stats["total_queries"], 1)) * 100
        error_ok = error_rate <= 5.0
        
        self.performance_stats["performance_targets_met"] = auth_ok and general_ok and cache_ok and error_ok
        self.performance_stats["last_updated"] = datetime.utcnow()
    
    def _check_alert_rules(self, metric: PerformanceMetric):
        """Check if metric violates any alert rules."""
        current_time = datetime.utcnow()
        
        for rule in self.alert_rules:
            if not rule.enabled or rule.metric_name != metric.metric_name:
                continue
            
            try:
                # Get recent metrics for this rule
                window_start = current_time - timedelta(minutes=rule.window_minutes)
                recent_metrics = [
                    m for m in self.metrics_buffer 
                    if m.metric_name == rule.metric_name 
                    and m.timestamp >= window_start
                ]
                
                if len(recent_metrics) < rule.min_samples:
                    continue
                
                # Calculate average value in window
                avg_value = sum(m.value for m in recent_metrics) / len(recent_metrics)
                
                # Check threshold violation
                violation = False
                if rule.comparison == "gt" and avg_value > rule.threshold:
                    violation = True
                elif rule.comparison == "lt" and avg_value < rule.threshold:
                    violation = True
                elif rule.comparison == "eq" and abs(avg_value - rule.threshold) < 0.01:
                    violation = True
                
                if violation:
                    self._trigger_alert(rule, avg_value, metric)
                else:
                    self._resolve_alert(rule.name)
                
            except Exception as e:
                logger.error(f"❌ [PERF_MON] Error checking alert rule {rule.name}: {e}")
    
    def _trigger_alert(self, rule: AlertRule, value: float, metric: PerformanceMetric):
        """Trigger a performance alert."""
        alert_key = rule.name
        
        # Check if alert is already active (prevent spam)
        if alert_key in self.active_alerts and not self.active_alerts[alert_key].resolved:
            return
        
        # Create alert
        alert = PerformanceAlert(
            rule_name=rule.name,
            alert_level=rule.alert_level,
            message=self._generate_alert_message(rule, value),
            metric_value=value,
            threshold=rule.threshold,
            timestamp=datetime.utcnow(),
            context=metric.context
        )
        
        # Store alert
        self.active_alerts[alert_key] = alert
        self.alert_history.append(alert)
        
        # Log alert
        level_emoji = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.CRITICAL: "🚨",
            AlertLevel.EMERGENCY: "🔥"
        }
        
        logger.log(
            self._get_log_level(rule.alert_level),
            f"{level_emoji.get(rule.alert_level, '🔔')} [PERF_ALERT] {alert.message}"
        )
        
        # Execute callback if defined
        if rule.callback:
            try:
                rule.callback(alert)
            except Exception as e:
                logger.error(f"❌ [PERF_MON] Alert callback error: {e}")
        
        # Execute registered alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"❌ [PERF_MON] Alert callback error: {e}")
    
    def _resolve_alert(self, rule_name: str):
        """Resolve an active alert."""
        if rule_name in self.active_alerts and not self.active_alerts[rule_name].resolved:
            alert = self.active_alerts[rule_name]
            alert.resolved = True
            alert.resolved_at = datetime.utcnow()
            
            logger.info(f"✅ [PERF_ALERT] RESOLVED: {rule_name}")
    
    def _generate_alert_message(self, rule: AlertRule, value: float) -> str:
        """Generate alert message text."""
        comparison_text = {
            "gt": "exceeded",
            "lt": "below",
            "eq": "equals"
        }
        
        return (
            f"{rule.name.replace('_', ' ').title()}: "
            f"{value:.2f} {comparison_text.get(rule.comparison, 'violates')} "
            f"threshold of {rule.threshold:.2f}"
        )
    
    def _get_log_level(self, alert_level: AlertLevel) -> int:
        """Convert alert level to logging level."""
        mapping = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.CRITICAL: logging.ERROR,
            AlertLevel.EMERGENCY: logging.CRITICAL
        }
        return mapping.get(alert_level, logging.WARNING)
    
    async def _monitoring_loop(self):
        """Main monitoring loop for periodic checks and reporting."""
        while self.monitoring_active:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Generate periodic performance report
                await self._generate_periodic_report()
                
                # Cleanup old metrics
                self._cleanup_old_metrics()
                
                # Check system health
                await self._system_health_check()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [PERF_MON] Monitoring loop error: {e}")
    
    async def _generate_periodic_report(self):
        """Generate periodic performance report."""
        try:
            with self.lock:
                stats = self.performance_stats.copy()
            
            # Log performance summary every 5 minutes
            if datetime.utcnow().minute % 5 == 0:
                logger.info(
                    f"📊 [PERF_REPORT] "
                    f"Queries: {stats['total_queries']}, "
                    f"Auth Avg: {stats['avg_auth_time_ms']:.1f}ms, "
                    f"General Avg: {stats['avg_general_time_ms']:.1f}ms, "
                    f"Cache Hit: {stats['avg_cache_hit_rate']:.1f}%, "
                    f"Targets Met: {'✅' if stats['performance_targets_met'] else '❌'}"
                )
        
        except Exception as e:
            logger.error(f"❌ [PERF_MON] Report generation error: {e}")
    
    def _cleanup_old_metrics(self):
        """Clean up old metrics to prevent memory growth."""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            # Clean main buffer (already limited by maxlen)
            # Clean type-specific buffers
            for query_type in self.metrics_by_type:
                buffer = self.metrics_by_type[query_type]
                # Remove old metrics
                while buffer and buffer[0].timestamp < cutoff_time:
                    buffer.popleft()
        
        except Exception as e:
            logger.error(f"❌ [PERF_MON] Cleanup error: {e}")
    
    async def _system_health_check(self):
        """Perform system health check and trigger alerts if needed."""
        try:
            # Check if we're receiving metrics (system is active)
            recent_metrics = [
                m for m in self.metrics_buffer
                if m.timestamp >= datetime.utcnow() - timedelta(minutes=5)
            ]
            
            if len(recent_metrics) == 0 and self.performance_stats["total_queries"] > 0:
                logger.warning("⚠️ [PERF_MON] No recent metrics - system may be inactive")
        
        except Exception as e:
            logger.error(f"❌ [PERF_MON] Health check error: {e}")
    
    def add_alert_rule(self, rule: AlertRule):
        """Add a custom alert rule."""
        self.alert_rules.append(rule)
        logger.info(f"✅ [PERF_MON] Added alert rule: {rule.name}")
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]):
        """Add a callback function to be called when alerts are triggered."""
        self.alert_callbacks.append(callback)
        logger.info("✅ [PERF_MON] Added alert callback")
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        with self.lock:
            return {
                "monitoring_status": "active" if self.monitoring_active else "inactive",
                "performance_stats": self.performance_stats.copy(),
                "active_alerts": {
                    name: {
                        "level": alert.alert_level.value,
                        "message": alert.message,
                        "timestamp": alert.timestamp.isoformat(),
                        "resolved": alert.resolved
                    }
                    for name, alert in self.active_alerts.items()
                },
                "alert_rules": [
                    {
                        "name": rule.name,
                        "metric": rule.metric_name,
                        "threshold": rule.threshold,
                        "enabled": rule.enabled
                    }
                    for rule in self.alert_rules
                ],
                "recent_metrics_count": len(self.metrics_buffer),
                "last_updated": datetime.utcnow().isoformat()
            }
    
    def get_performance_trends(self, hours: int = 1) -> Dict[str, List[Dict[str, Any]]]:
        """Get performance trends over specified time period."""
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)
        
        trends = defaultdict(list)
        
        for metric in self.metrics_buffer:
            if metric.timestamp >= cutoff_time:
                trends[metric.metric_name].append({
                    "timestamp": metric.timestamp.isoformat(),
                    "value": metric.value,
                    "success": metric.success
                })
        
        return dict(trends)


# Global monitor instance
performance_monitor = DatabasePerformanceMonitor()


# Convenience functions for easy integration
def record_query(query_type: str, execution_time_ms: float, success: bool = True, context: Dict[str, Any] = None, cache_hit: bool = False):
    """Record a database query performance metric."""
    performance_monitor.record_query_performance(query_type, execution_time_ms, success, context, cache_hit)


def record_cache_hit(lookup_time_ms: float = 0.0):
    """Record a cache hit."""
    performance_monitor.record_cache_performance(True, lookup_time_ms)


def record_cache_miss(lookup_time_ms: float = 0.0):
    """Record a cache miss."""
    performance_monitor.record_cache_performance(False, lookup_time_ms)


async def start_performance_monitoring():
    """Start the global performance monitoring system."""
    await performance_monitor.start_monitoring()


async def stop_performance_monitoring():
    """Stop the global performance monitoring system."""
    await performance_monitor.stop_monitoring()


def get_performance_summary():
    """Get current performance summary."""
    return performance_monitor.get_performance_summary()