"""
Cache Performance Monitor
Real-time monitoring and alerting for L1/L2/L3 cache performance.

Features:
- Real-time performance tracking for all cache levels
- Automated alerting for performance degradation
- Cache hit rate optimization recommendations  
- Performance analytics and trending
- Integration with Grafana dashboards
- Circuit breaker monitoring and management
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum
import statistics

from caching.multi_layer_cache_manager import MultiLayerCacheManager, CacheLevel, CacheOperation
from monitoring.performance import performance_tracker, PerformanceTarget
from monitoring.metrics import metrics_collector
from database import get_database

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Alert severity levels for cache performance issues."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class PerformanceThreshold(Enum):
    """Performance threshold configurations."""
    L1_TARGET_MS = 5.0          # L1 Memory Cache target
    L2_TARGET_MS = 20.0         # L2 Redis Cache target
    L3_TARGET_MS = 100.0        # L3 Database Cache target
    
    L1_HIT_RATE_TARGET = 95.0   # L1 hit rate target %
    L2_HIT_RATE_TARGET = 85.0   # L2 hit rate target %
    L3_HIT_RATE_TARGET = 70.0   # L3 hit rate target %
    
    OVERALL_HIT_RATE_TARGET = 90.0  # Overall hit rate target %
    AUTHORIZATION_TARGET_MS = 75.0   # Authorization target


@dataclass
class CacheAlert:
    """Cache performance alert."""
    alert_id: str
    level: AlertLevel
    cache_level: str
    metric_name: str
    current_value: float
    threshold_value: float
    message: str
    timestamp: datetime
    resolved: bool = False
    resolution_time: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert alert to dictionary."""
        return {
            "alert_id": self.alert_id,
            "level": self.level.value,
            "cache_level": self.cache_level,
            "metric_name": self.metric_name,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "resolved": self.resolved,
            "resolution_time": self.resolution_time.isoformat() if self.resolution_time else None
        }


@dataclass
class CachePerformanceSnapshot:
    """Point-in-time cache performance snapshot."""
    timestamp: datetime
    
    # Overall metrics
    overall_hit_rate: float
    overall_avg_response_time_ms: float
    total_requests: int
    successful_requests: int
    
    # L1 metrics
    l1_hit_rate: float
    l1_avg_response_time_ms: float
    l1_cache_size_mb: float
    l1_utilization_percent: float
    
    # L2 metrics
    l2_hit_rate: float
    l2_avg_response_time_ms: float
    l2_circuit_breaker_state: str
    l2_available: bool
    
    # L3 metrics
    l3_hit_rate: float
    l3_avg_response_time_ms: float
    l3_materialized_views_count: int
    
    # System metrics
    concurrent_operations: int
    memory_usage_mb: float
    cpu_usage_percent: float


class CachePerformanceAnalyzer:
    """Analyzes cache performance trends and provides optimization recommendations."""
    
    def __init__(self, window_size: int = 1000):
        self.window_size = window_size
        self.performance_history: deque = deque(maxlen=window_size)
        self.alert_history: List[CacheAlert] = []
        self.performance_trends: Dict[str, List[float]] = defaultdict(list)
    
    def add_snapshot(self, snapshot: CachePerformanceSnapshot):
        """Add performance snapshot for analysis."""
        self.performance_history.append(snapshot)
        
        # Update performance trends
        self.performance_trends['overall_hit_rate'].append(snapshot.overall_hit_rate)
        self.performance_trends['overall_response_time'].append(snapshot.overall_avg_response_time_ms)
        self.performance_trends['l1_hit_rate'].append(snapshot.l1_hit_rate)
        self.performance_trends['l2_hit_rate'].append(snapshot.l2_hit_rate)
        self.performance_trends['l3_hit_rate'].append(snapshot.l3_hit_rate)
        
        # Keep trend data manageable
        max_trend_points = 500
        for key in self.performance_trends:
            if len(self.performance_trends[key]) > max_trend_points:
                self.performance_trends[key] = self.performance_trends[key][-max_trend_points:]
    
    def analyze_performance_trends(self) -> Dict[str, Any]:
        """Analyze performance trends and identify issues."""
        if len(self.performance_history) < 10:
            return {"error": "Insufficient data for trend analysis"}
        
        # Calculate trend analysis for key metrics
        trends = {}
        
        for metric, values in self.performance_trends.items():
            if len(values) >= 10:
                recent_values = values[-10:]  # Last 10 data points
                older_values = values[-20:-10] if len(values) >= 20 else values[:-10]
                
                if older_values:
                    recent_avg = statistics.mean(recent_values)
                    older_avg = statistics.mean(older_values)
                    trend_direction = "improving" if recent_avg > older_avg else "degrading"
                    trend_magnitude = abs(recent_avg - older_avg)
                    
                    trends[metric] = {
                        "current_value": recent_values[-1],
                        "recent_average": recent_avg,
                        "previous_average": older_avg,
                        "trend_direction": trend_direction,
                        "trend_magnitude": trend_magnitude,
                        "stddev": statistics.stdev(recent_values) if len(recent_values) > 1 else 0
                    }
        
        # Identify performance issues
        issues = self._identify_performance_issues(trends)
        
        # Generate recommendations
        recommendations = self._generate_optimization_recommendations(trends, issues)
        
        return {
            "trends": trends,
            "issues": issues,
            "recommendations": recommendations,
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "data_points_analyzed": len(self.performance_history)
        }
    
    def _identify_performance_issues(self, trends: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify performance issues from trend analysis."""
        issues = []
        
        # Check overall hit rate degradation
        if 'overall_hit_rate' in trends:
            hit_rate_trend = trends['overall_hit_rate']
            if (hit_rate_trend['trend_direction'] == 'degrading' and 
                hit_rate_trend['current_value'] < PerformanceThreshold.OVERALL_HIT_RATE_TARGET.value):
                issues.append({
                    "type": "hit_rate_degradation",
                    "severity": "high",
                    "metric": "overall_hit_rate",
                    "current_value": hit_rate_trend['current_value'],
                    "target_value": PerformanceThreshold.OVERALL_HIT_RATE_TARGET.value,
                    "description": f"Overall cache hit rate degrading: {hit_rate_trend['current_value']:.1f}% vs target {PerformanceThreshold.OVERALL_HIT_RATE_TARGET.value}%"
                })
        
        # Check response time increases
        if 'overall_response_time' in trends:
            response_time_trend = trends['overall_response_time']
            if (response_time_trend['trend_direction'] == 'degrading' and
                response_time_trend['current_value'] > 100.0):  # 100ms threshold
                issues.append({
                    "type": "response_time_increase",
                    "severity": "medium",
                    "metric": "overall_response_time",
                    "current_value": response_time_trend['current_value'],
                    "target_value": 100.0,
                    "description": f"Response time increasing: {response_time_trend['current_value']:.1f}ms"
                })
        
        # Check individual cache level performance
        cache_levels = [
            ('l1_hit_rate', PerformanceThreshold.L1_HIT_RATE_TARGET.value, 'L1'),
            ('l2_hit_rate', PerformanceThreshold.L2_HIT_RATE_TARGET.value, 'L2'),
            ('l3_hit_rate', PerformanceThreshold.L3_HIT_RATE_TARGET.value, 'L3')
        ]
        
        for metric, target, level in cache_levels:
            if metric in trends:
                trend = trends[metric]
                if (trend['trend_direction'] == 'degrading' and 
                    trend['current_value'] < target):
                    issues.append({
                        "type": f"{level.lower()}_hit_rate_low",
                        "severity": "medium",
                        "metric": metric,
                        "current_value": trend['current_value'],
                        "target_value": target,
                        "description": f"{level} cache hit rate below target: {trend['current_value']:.1f}% vs {target}%"
                    })
        
        return issues
    
    def _generate_optimization_recommendations(self, trends: Dict[str, Any], 
                                             issues: List[Dict[str, Any]]) -> List[str]:
        """Generate cache optimization recommendations."""
        recommendations = []
        
        # Recommendations based on issues
        for issue in issues:
            if issue['type'] == 'hit_rate_degradation':
                recommendations.extend([
                    "Consider increasing L1 memory cache size to improve hit rates",
                    "Review cache warming strategies for frequently accessed data",
                    "Analyze access patterns to optimize cache key distribution"
                ])
            
            elif issue['type'] == 'response_time_increase':
                recommendations.extend([
                    "Investigate L1 cache eviction patterns and adjust eviction policy",
                    "Check Redis connection health and consider connection pool optimization",
                    "Review database query performance for L3 cache materialized views"
                ])
            
            elif 'l1_hit_rate_low' in issue['type']:
                recommendations.extend([
                    "Increase L1 memory cache allocation",
                    "Optimize L1 eviction policy (consider LRU vs LFU vs Hybrid)",
                    "Implement more aggressive cache warming for hot data"
                ])
            
            elif 'l2_hit_rate_low' in issue['type']:
                recommendations.extend([
                    "Check Redis memory limits and eviction policies",
                    "Review L2 cache TTL configurations",
                    "Consider Redis cluster setup for better distribution"
                ])
            
            elif 'l3_hit_rate_low' in issue['type']:
                recommendations.extend([
                    "Review materialized view refresh frequency",
                    "Optimize database indexes for cache queries",
                    "Consider partitioning strategy for large cache tables"
                ])
        
        # General recommendations based on trends
        if 'overall_hit_rate' in trends:
            hit_rate = trends['overall_hit_rate']['current_value']
            if hit_rate >= 95.0:
                recommendations.append("Excellent cache performance! Consider sharing configuration as best practice")
            elif hit_rate >= 90.0:
                recommendations.append("Good cache performance with room for optimization")
            elif hit_rate >= 80.0:
                recommendations.append("Cache performance needs improvement - review access patterns")
            else:
                recommendations.append("CRITICAL: Cache performance severely degraded - immediate optimization required")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for rec in recommendations:
            if rec not in seen:
                seen.add(rec)
                unique_recommendations.append(rec)
        
        return unique_recommendations


class CachePerformanceMonitor:
    """Real-time cache performance monitor with alerting and analytics."""
    
    def __init__(self, cache_manager: MultiLayerCacheManager, 
                 monitoring_interval_seconds: int = 30):
        self.cache_manager = cache_manager
        self.monitoring_interval = monitoring_interval_seconds
        
        # Performance analysis
        self.analyzer = CachePerformanceAnalyzer()
        
        # Alerting
        self.active_alerts: Dict[str, CacheAlert] = {}
        self.alert_callbacks: List[Callable[[CacheAlert], None]] = []
        
        # Monitoring state
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        
        # Performance thresholds
        self.thresholds = {
            'l1_response_time_ms': PerformanceThreshold.L1_TARGET_MS.value,
            'l2_response_time_ms': PerformanceThreshold.L2_TARGET_MS.value,
            'l3_response_time_ms': PerformanceThreshold.L3_TARGET_MS.value,
            'l1_hit_rate_percent': PerformanceThreshold.L1_HIT_RATE_TARGET.value,
            'l2_hit_rate_percent': PerformanceThreshold.L2_HIT_RATE_TARGET.value,
            'l3_hit_rate_percent': PerformanceThreshold.L3_HIT_RATE_TARGET.value,
            'overall_hit_rate_percent': PerformanceThreshold.OVERALL_HIT_RATE_TARGET.value,
            'authorization_response_time_ms': PerformanceThreshold.AUTHORIZATION_TARGET_MS.value
        }
    
    def add_alert_callback(self, callback: Callable[[CacheAlert], None]):
        """Add callback function for alert notifications."""
        self.alert_callbacks.append(callback)
    
    def start_monitoring(self):
        """Start real-time cache performance monitoring."""
        if self.monitoring_active:
            logger.warning("Cache performance monitoring already active")
            return
        
        self.monitoring_active = True
        try:
            loop = asyncio.get_running_loop()
            self.monitoring_task = loop.create_task(self._monitoring_loop())
            logger.info(f"Cache performance monitoring started (interval: {self.monitoring_interval}s)")
        except RuntimeError:
            logger.error("No event loop available for cache monitoring")
    
    def stop_monitoring(self):
        """Stop cache performance monitoring."""
        self.monitoring_active = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
        logger.info("Cache performance monitoring stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop."""
        try:
            while self.monitoring_active:
                await self._collect_performance_snapshot()
                await asyncio.sleep(self.monitoring_interval)
        except asyncio.CancelledError:
            logger.info("Cache monitoring loop cancelled")
        except Exception as e:
            logger.error(f"Cache monitoring loop error: {e}")
    
    async def _collect_performance_snapshot(self):
        """Collect and analyze current cache performance."""
        try:
            # Get comprehensive cache metrics
            cache_metrics = self.cache_manager.get_comprehensive_metrics()
            
            # Create performance snapshot
            snapshot = CachePerformanceSnapshot(
                timestamp=datetime.utcnow(),
                overall_hit_rate=cache_metrics["overall_performance"]["overall_hit_rate_percent"],
                overall_avg_response_time_ms=cache_metrics["overall_performance"]["weighted_avg_response_time_ms"],
                total_requests=cache_metrics["overall_performance"]["total_requests"],
                successful_requests=cache_metrics["overall_performance"]["total_hits"],
                
                l1_hit_rate=cache_metrics["cache_levels"]["L1_Memory"]["metrics"]["hit_rate"],
                l1_avg_response_time_ms=cache_metrics["cache_levels"]["L1_Memory"]["metrics"]["avg_response_time_ms"],
                l1_cache_size_mb=cache_metrics["cache_levels"]["L1_Memory"]["current_size_mb"],
                l1_utilization_percent=cache_metrics["cache_levels"]["L1_Memory"]["utilization_percent"],
                
                l2_hit_rate=cache_metrics["cache_levels"]["L2_Redis"]["metrics"]["hit_rate"],
                l2_avg_response_time_ms=cache_metrics["cache_levels"]["L2_Redis"]["metrics"]["avg_response_time_ms"],
                l2_circuit_breaker_state=cache_metrics["cache_levels"]["L2_Redis"]["circuit_breaker_state"],
                l2_available=cache_metrics["cache_levels"]["L2_Redis"]["redis_available"],
                
                l3_hit_rate=cache_metrics["cache_levels"]["L3_Database"]["metrics"]["hit_rate"],
                l3_avg_response_time_ms=cache_metrics["cache_levels"]["L3_Database"]["metrics"]["avg_response_time_ms"],
                l3_materialized_views_count=len(cache_metrics["cache_levels"]["L3_Database"]["materialized_views"]),
                
                concurrent_operations=0,  # Would be populated from system monitoring
                memory_usage_mb=0.0,      # Would be populated from system monitoring
                cpu_usage_percent=0.0     # Would be populated from system monitoring
            )
            
            # Add to analyzer
            self.analyzer.add_snapshot(snapshot)
            
            # Check for alerts
            await self._check_performance_alerts(snapshot)
            
            # Log performance metrics
            logger.debug(f"Cache performance snapshot: Hit rate {snapshot.overall_hit_rate:.1f}%, "
                        f"Response time {snapshot.overall_avg_response_time_ms:.2f}ms")
            
            # Store metrics in database for historical analysis
            await self._store_performance_metrics(snapshot)
            
        except Exception as e:
            logger.error(f"Error collecting cache performance snapshot: {e}")
    
    async def _check_performance_alerts(self, snapshot: CachePerformanceSnapshot):
        """Check performance thresholds and generate alerts."""
        current_alerts = {}
        
        # Check overall hit rate
        if snapshot.overall_hit_rate < self.thresholds['overall_hit_rate_percent']:
            alert_id = "overall_hit_rate_low"
            alert = CacheAlert(
                alert_id=alert_id,
                level=AlertLevel.WARNING if snapshot.overall_hit_rate >= 85.0 else AlertLevel.ERROR,
                cache_level="OVERALL",
                metric_name="hit_rate",
                current_value=snapshot.overall_hit_rate,
                threshold_value=self.thresholds['overall_hit_rate_percent'],
                message=f"Overall cache hit rate ({snapshot.overall_hit_rate:.1f}%) below target ({self.thresholds['overall_hit_rate_percent']}%)",
                timestamp=snapshot.timestamp
            )
            current_alerts[alert_id] = alert
        
        # Check overall response time
        if snapshot.overall_avg_response_time_ms > 100.0:  # 100ms threshold
            alert_id = "overall_response_time_high"
            alert = CacheAlert(
                alert_id=alert_id,
                level=AlertLevel.WARNING if snapshot.overall_avg_response_time_ms <= 150.0 else AlertLevel.ERROR,
                cache_level="OVERALL",
                metric_name="response_time",
                current_value=snapshot.overall_avg_response_time_ms,
                threshold_value=100.0,
                message=f"Overall response time ({snapshot.overall_avg_response_time_ms:.1f}ms) exceeds 100ms threshold",
                timestamp=snapshot.timestamp
            )
            current_alerts[alert_id] = alert
        
        # Check L1 cache performance
        if snapshot.l1_hit_rate < self.thresholds['l1_hit_rate_percent']:
            alert_id = "l1_hit_rate_low"
            alert = CacheAlert(
                alert_id=alert_id,
                level=AlertLevel.WARNING,
                cache_level="L1_MEMORY",
                metric_name="hit_rate",
                current_value=snapshot.l1_hit_rate,
                threshold_value=self.thresholds['l1_hit_rate_percent'],
                message=f"L1 cache hit rate ({snapshot.l1_hit_rate:.1f}%) below target ({self.thresholds['l1_hit_rate_percent']}%)",
                timestamp=snapshot.timestamp
            )
            current_alerts[alert_id] = alert
        
        # Check L1 response time
        if snapshot.l1_avg_response_time_ms > self.thresholds['l1_response_time_ms']:
            alert_id = "l1_response_time_high"
            alert = CacheAlert(
                alert_id=alert_id,
                level=AlertLevel.WARNING,
                cache_level="L1_MEMORY",
                metric_name="response_time",
                current_value=snapshot.l1_avg_response_time_ms,
                threshold_value=self.thresholds['l1_response_time_ms'],
                message=f"L1 cache response time ({snapshot.l1_avg_response_time_ms:.1f}ms) exceeds target ({self.thresholds['l1_response_time_ms']}ms)",
                timestamp=snapshot.timestamp
            )
            current_alerts[alert_id] = alert
        
        # Check L2 Redis availability and performance
        if not snapshot.l2_available:
            alert_id = "l2_redis_unavailable"
            alert = CacheAlert(
                alert_id=alert_id,
                level=AlertLevel.ERROR,
                cache_level="L2_REDIS",
                metric_name="availability",
                current_value=0.0,
                threshold_value=1.0,
                message="L2 Redis cache is unavailable",
                timestamp=snapshot.timestamp
            )
            current_alerts[alert_id] = alert
        
        elif snapshot.l2_circuit_breaker_state == "open":
            alert_id = "l2_circuit_breaker_open"
            alert = CacheAlert(
                alert_id=alert_id,
                level=AlertLevel.ERROR,
                cache_level="L2_REDIS",
                metric_name="circuit_breaker",
                current_value=1.0,
                threshold_value=0.0,
                message="L2 Redis circuit breaker is OPEN - operations suspended",
                timestamp=snapshot.timestamp
            )
            current_alerts[alert_id] = alert
        
        elif snapshot.l2_hit_rate < self.thresholds['l2_hit_rate_percent']:
            alert_id = "l2_hit_rate_low"
            alert = CacheAlert(
                alert_id=alert_id,
                level=AlertLevel.WARNING,
                cache_level="L2_REDIS",
                metric_name="hit_rate",
                current_value=snapshot.l2_hit_rate,
                threshold_value=self.thresholds['l2_hit_rate_percent'],
                message=f"L2 cache hit rate ({snapshot.l2_hit_rate:.1f}%) below target ({self.thresholds['l2_hit_rate_percent']}%)",
                timestamp=snapshot.timestamp
            )
            current_alerts[alert_id] = alert
        
        # Process new and resolved alerts
        await self._process_alerts(current_alerts)
    
    async def _process_alerts(self, current_alerts: Dict[str, CacheAlert]):
        """Process new and resolved alerts."""
        # Check for new alerts
        for alert_id, alert in current_alerts.items():
            if alert_id not in self.active_alerts:
                # New alert
                self.active_alerts[alert_id] = alert
                self.analyzer.alert_history.append(alert)
                
                # Trigger alert callbacks
                for callback in self.alert_callbacks:
                    try:
                        callback(alert)
                    except Exception as e:
                        logger.error(f"Alert callback error: {e}")
                
                logger.warning(f"CACHE ALERT: {alert.message}")
        
        # Check for resolved alerts
        resolved_alerts = []
        for alert_id, active_alert in self.active_alerts.items():
            if alert_id not in current_alerts:
                # Alert resolved
                active_alert.resolved = True
                active_alert.resolution_time = datetime.utcnow()
                resolved_alerts.append(alert_id)
                
                logger.info(f"CACHE ALERT RESOLVED: {active_alert.message}")
        
        # Remove resolved alerts
        for alert_id in resolved_alerts:
            del self.active_alerts[alert_id]
    
    async def _store_performance_metrics(self, snapshot: CachePerformanceSnapshot):
        """Store performance metrics in database for historical analysis."""
        try:
            db = await get_database()
            
            # Store cache performance data
            await db.execute_query(
                table="",
                operation="raw_query",
                query="""
                SELECT record_cache_performance(
                    'OVERALL',
                    'SNAPSHOT',
                    'performance_monitor',
                    %s,
                    true,
                    0,
                    null,
                    %s::jsonb
                )
                """,
                params=[
                    snapshot.overall_avg_response_time_ms,
                    json.dumps({
                        "overall_hit_rate": snapshot.overall_hit_rate,
                        "l1_hit_rate": snapshot.l1_hit_rate,
                        "l2_hit_rate": snapshot.l2_hit_rate,
                        "l3_hit_rate": snapshot.l3_hit_rate,
                        "l1_utilization_percent": snapshot.l1_utilization_percent,
                        "l2_circuit_breaker_state": snapshot.l2_circuit_breaker_state,
                        "l2_available": snapshot.l2_available,
                        "timestamp": snapshot.timestamp.isoformat()
                    })
                ]
            )
            
        except Exception as e:
            logger.error(f"Error storing cache performance metrics: {e}")
    
    def get_current_performance_status(self) -> Dict[str, Any]:
        """Get current cache performance status."""
        if not self.analyzer.performance_history:
            return {"error": "No performance data available"}
        
        latest_snapshot = self.analyzer.performance_history[-1]
        
        return {
            "current_performance": asdict(latest_snapshot),
            "active_alerts": [alert.to_dict() for alert in self.active_alerts.values()],
            "alert_count_by_level": {
                level.value: sum(1 for alert in self.active_alerts.values() if alert.level == level)
                for level in AlertLevel
            },
            "monitoring_active": self.monitoring_active,
            "last_update": latest_snapshot.timestamp.isoformat()
        }
    
    def get_performance_analysis(self) -> Dict[str, Any]:
        """Get comprehensive performance analysis and recommendations."""
        analysis = self.analyzer.analyze_performance_trends()
        
        # Add current alerts
        analysis["active_alerts"] = [alert.to_dict() for alert in self.active_alerts.values()]
        analysis["alert_history_count"] = len(self.analyzer.alert_history)
        
        # Add monitoring status
        analysis["monitoring_status"] = {
            "active": self.monitoring_active,
            "interval_seconds": self.monitoring_interval,
            "data_points": len(self.analyzer.performance_history),
            "thresholds": self.thresholds
        }
        
        return analysis
    
    def get_grafana_dashboard_config(self) -> Dict[str, Any]:
        """Generate Grafana dashboard configuration for cache monitoring."""
        return {
            "dashboard": {
                "title": "Velro Cache Performance Monitor",
                "tags": ["cache", "performance", "monitoring"],
                "panels": [
                    {
                        "title": "Overall Cache Hit Rate",
                        "type": "stat",
                        "targets": [
                            {
                                "expr": "cache_hit_rate_overall",
                                "legendFormat": "Hit Rate %"
                            }
                        ],
                        "thresholds": [
                            {"value": 0, "color": "red"},
                            {"value": 85, "color": "yellow"}, 
                            {"value": 90, "color": "green"}
                        ]
                    },
                    {
                        "title": "Cache Response Times by Level",
                        "type": "timeseries",
                        "targets": [
                            {"expr": "cache_response_time_l1", "legendFormat": "L1 Memory"},
                            {"expr": "cache_response_time_l2", "legendFormat": "L2 Redis"},
                            {"expr": "cache_response_time_l3", "legendFormat": "L3 Database"}
                        ]
                    },
                    {
                        "title": "Cache Hit Rates by Level",
                        "type": "timeseries",
                        "targets": [
                            {"expr": "cache_hit_rate_l1", "legendFormat": "L1 Hit Rate"},
                            {"expr": "cache_hit_rate_l2", "legendFormat": "L2 Hit Rate"},
                            {"expr": "cache_hit_rate_l3", "legendFormat": "L3 Hit Rate"}
                        ]
                    },
                    {
                        "title": "Active Cache Alerts",
                        "type": "table",
                        "targets": [
                            {"expr": "cache_alerts", "format": "table"}
                        ]
                    }
                ]
            }
        }


# Global cache performance monitor instance
cache_performance_monitor: Optional[CachePerformanceMonitor] = None


def get_cache_performance_monitor(cache_manager: MultiLayerCacheManager) -> CachePerformanceMonitor:
    """Get or create global cache performance monitor."""
    global cache_performance_monitor
    if cache_performance_monitor is None:
        cache_performance_monitor = CachePerformanceMonitor(cache_manager)
        
        # Add default alert callback (logging)
        def log_alert(alert: CacheAlert):
            level_map = {
                AlertLevel.INFO: logger.info,
                AlertLevel.WARNING: logger.warning,
                AlertLevel.ERROR: logger.error,
                AlertLevel.CRITICAL: logger.critical
            }
            log_func = level_map[alert.level]
            log_func(f"Cache Alert [{alert.level.value.upper()}]: {alert.message}")
        
        cache_performance_monitor.add_alert_callback(log_alert)
    
    return cache_performance_monitor


# Convenience functions for monitoring integration
async def start_cache_monitoring(cache_manager: MultiLayerCacheManager, 
                                interval_seconds: int = 30):
    """Start cache performance monitoring."""
    monitor = get_cache_performance_monitor(cache_manager)
    monitor.monitoring_interval = interval_seconds
    monitor.start_monitoring()
    logger.info("Cache performance monitoring started")


def stop_cache_monitoring():
    """Stop cache performance monitoring."""
    if cache_performance_monitor:
        cache_performance_monitor.stop_monitoring()
        logger.info("Cache performance monitoring stopped")


async def get_cache_performance_report() -> Dict[str, Any]:
    """Get comprehensive cache performance report."""
    if not cache_performance_monitor:
        return {"error": "Cache monitoring not initialized"}
    
    return cache_performance_monitor.get_performance_analysis()