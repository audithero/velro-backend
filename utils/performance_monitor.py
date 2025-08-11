"""
Performance monitoring utilities for comprehensive system observation.
Real-time metrics collection and analysis for Velro API.
Enterprise-grade monitoring for UUID authorization system performance.
"""
import asyncio
import time
import psutil
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from collections import defaultdict, deque
import json
import os

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot."""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_usage_percent: float
    active_connections: int
    request_count: int
    error_count: int
    avg_response_time: float
    slow_queries_count: int
    credit_operations_per_minute: int
    generation_success_rate: float


class PerformanceMonitor:
    """Real-time performance monitoring system."""
    
    def __init__(self, metrics_retention_minutes: int = 60):
        self.metrics_retention = metrics_retention_minutes
        self.metrics_history: deque = deque(maxlen=metrics_retention_minutes)
        self.request_times: deque = deque(maxlen=1000)  # Last 1000 requests
        self.error_counts = defaultdict(int)
        self.credit_operations = deque(maxlen=1000)
        self.generation_results = deque(maxlen=1000)
        self.active_connections = 0
        self.slow_query_threshold = 2.0  # seconds
        self.slow_queries = deque(maxlen=100)
        
        # Start background monitoring
        self._monitoring_task = None
        
    async def start_monitoring(self, interval_seconds: int = 60):
        """Start background performance monitoring."""
        if self._monitoring_task:
            return
            
        logger.info("🚀 [PERF-MONITOR] Starting performance monitoring")
        self._monitoring_task = asyncio.create_task(
            self._monitoring_loop(interval_seconds)
        )
    
    async def stop_monitoring(self):
        """Stop background monitoring."""
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            logger.info("🛑 [PERF-MONITOR] Performance monitoring stopped")
    
    async def _monitoring_loop(self, interval_seconds: int):
        """Background monitoring loop."""
        while True:
            try:
                metrics = await self.collect_metrics()
                self.metrics_history.append(metrics)
                
                # Log significant changes
                await self._analyze_metrics(metrics)
                
                # Save metrics to file (non-production only)
                if not os.getenv("RAILWAY_ENVIRONMENT"):
                    await self._save_metrics_to_file(metrics)
                
            except Exception as e:
                logger.error(f"❌ [PERF-MONITOR] Error in monitoring loop: {e}")
            
            await asyncio.sleep(interval_seconds)
    
    async def collect_metrics(self) -> PerformanceMetrics:
        """Collect current performance metrics."""
        try:
            # System metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Application metrics
            request_count = len(self.request_times)
            error_count = sum(self.error_counts.values())
            
            # Calculate average response time
            if self.request_times:
                avg_response_time = sum(self.request_times) / len(self.request_times)
            else:
                avg_response_time = 0.0
            
            # Credit operations per minute
            now = datetime.utcnow()
            one_minute_ago = now - timedelta(minutes=1)
            recent_credit_ops = sum(
                1 for op_time in self.credit_operations 
                if op_time > one_minute_ago
            )
            
            # Generation success rate
            if self.generation_results:
                successful = sum(1 for result in self.generation_results if result)
                success_rate = (successful / len(self.generation_results)) * 100
            else:
                success_rate = 100.0
            
            return PerformanceMetrics(
                timestamp=now.isoformat(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                disk_usage_percent=disk.percent,
                active_connections=self.active_connections,
                request_count=request_count,
                error_count=error_count,
                avg_response_time=avg_response_time,
                slow_queries_count=len(self.slow_queries),
                credit_operations_per_minute=recent_credit_ops,
                generation_success_rate=success_rate
            )
            
        except Exception as e:
            logger.error(f"❌ [PERF-MONITOR] Error collecting metrics: {e}")
            # Return minimal metrics on error
            return PerformanceMetrics(
                timestamp=datetime.utcnow().isoformat(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                disk_usage_percent=0.0,
                active_connections=0,
                request_count=0,
                error_count=0,
                avg_response_time=0.0,
                slow_queries_count=0,
                credit_operations_per_minute=0,
                generation_success_rate=100.0
            )
    
    async def _analyze_metrics(self, metrics: PerformanceMetrics):
        """Analyze metrics and log alerts."""
        # CPU usage alert
        if metrics.cpu_percent > 80:
            logger.warning(f"⚠️ [PERF-MONITOR] High CPU usage: {metrics.cpu_percent:.1f}%")
        
        # Memory usage alert
        if metrics.memory_percent > 85:
            logger.warning(f"⚠️ [PERF-MONITOR] High memory usage: {metrics.memory_percent:.1f}%")
        
        # Disk usage alert
        if metrics.disk_usage_percent > 90:
            logger.warning(f"⚠️ [PERF-MONITOR] High disk usage: {metrics.disk_usage_percent:.1f}%")
        
        # Response time alert
        if metrics.avg_response_time > 3.0:
            logger.warning(f"⚠️ [PERF-MONITOR] Slow response times: {metrics.avg_response_time:.2f}s avg")
        
        # Error rate alert
        if metrics.request_count > 0:
            error_rate = (metrics.error_count / metrics.request_count) * 100
            if error_rate > 10:
                logger.warning(f"⚠️ [PERF-MONITOR] High error rate: {error_rate:.1f}%")
        
        # Generation success rate alert
        if metrics.generation_success_rate < 90:
            logger.warning(f"⚠️ [PERF-MONITOR] Low generation success rate: {metrics.generation_success_rate:.1f}%")
    
    async def _save_metrics_to_file(self, metrics: PerformanceMetrics):
        """Save metrics to file for analysis."""
        try:
            os.makedirs("logs", exist_ok=True)
            
            # Append to daily metrics file
            date_str = datetime.utcnow().strftime("%Y-%m-%d")
            filename = f"logs/performance_metrics_{date_str}.jsonl"
            
            with open(filename, "a") as f:
                f.write(json.dumps(asdict(metrics)) + "\n")
                
        except Exception as e:
            logger.error(f"❌ [PERF-MONITOR] Error saving metrics: {e}")
    
    def record_request(self, response_time: float, status_code: int):
        """Record API request metrics."""
        self.request_times.append(response_time)
        
        if status_code >= 400:
            self.error_counts[status_code] += 1
    
    def record_credit_operation(self):
        """Record credit operation timestamp."""
        self.credit_operations.append(datetime.utcnow())
    
    def record_generation_result(self, success: bool):
        """Record generation result."""
        self.generation_results.append(success)
    
    def record_slow_query(self, query: str, duration: float, details: Dict[str, Any] = None):
        """Record slow database query."""
        if duration > self.slow_query_threshold:
            self.slow_queries.append({
                'query': query[:200],  # Truncate long queries
                'duration': duration,
                'timestamp': datetime.utcnow().isoformat(),
                'details': details or {}
            })
    
    def increment_connections(self):
        """Increment active connection count."""
        self.active_connections += 1
    
    def decrement_connections(self):
        """Decrement active connection count."""
        self.active_connections = max(0, self.active_connections - 1)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics as dict."""
        if not self.metrics_history:
            return {}
        
        latest = self.metrics_history[-1]
        return asdict(latest)
    
    def get_metrics_history(self, minutes: int = 15) -> List[Dict[str, Any]]:
        """Get metrics history for specified duration."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)
        
        filtered_metrics = [
            asdict(metric) for metric in self.metrics_history
            if datetime.fromisoformat(metric.timestamp.replace('Z', '+00:00')) > cutoff_time
        ]
        
        return filtered_metrics
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary."""
        if not self.metrics_history:
            return {"status": "no_data", "message": "No metrics available yet"}
        
        latest = self.metrics_history[-1]
        
        # Calculate trends
        if len(self.metrics_history) >= 2:
            previous = self.metrics_history[-2]
            cpu_trend = latest.cpu_percent - previous.cpu_percent
            memory_trend = latest.memory_percent - previous.memory_percent
            response_time_trend = latest.avg_response_time - previous.avg_response_time
        else:
            cpu_trend = memory_trend = response_time_trend = 0.0
        
        return {
            "current_metrics": asdict(latest),
            "trends": {
                "cpu_trend": cpu_trend,
                "memory_trend": memory_trend,
                "response_time_trend": response_time_trend
            },
            "alerts": self._get_current_alerts(latest),
            "slow_queries": list(self.slow_queries)[-5:],  # Last 5 slow queries
            "status": "healthy" if self._is_system_healthy(latest) else "degraded"
        }
    
    def _get_current_alerts(self, metrics: PerformanceMetrics) -> List[str]:
        """Get current system alerts."""
        alerts = []
        
        if metrics.cpu_percent > 80:
            alerts.append(f"High CPU usage: {metrics.cpu_percent:.1f}%")
        
        if metrics.memory_percent > 85:
            alerts.append(f"High memory usage: {metrics.memory_percent:.1f}%")
        
        if metrics.avg_response_time > 3.0:
            alerts.append(f"Slow response times: {metrics.avg_response_time:.2f}s")
        
        if metrics.generation_success_rate < 90:
            alerts.append(f"Low generation success rate: {metrics.generation_success_rate:.1f}%")
        
        return alerts
    
    def _is_system_healthy(self, metrics: PerformanceMetrics) -> bool:
        """Determine if system is healthy based on metrics."""
        return (
            metrics.cpu_percent < 80 and
            metrics.memory_percent < 85 and
            metrics.avg_response_time < 3.0 and
            metrics.generation_success_rate > 90
        )


# Authorization-specific performance metrics
@dataclass
class AuthorizationMetrics:
    """Authorization system performance metrics."""
    permission_checks_per_minute: int
    avg_permission_check_time_ms: float
    cache_hit_rate_percent: float
    team_lookup_time_ms: float
    rls_query_time_ms: float
    failed_authorization_count: int
    security_violations_count: int

class AuthorizationPerformanceMonitor(PerformanceMonitor):
    """Enhanced performance monitor with authorization-specific metrics."""
    
    def __init__(self, metrics_retention_minutes: int = 60):
        super().__init__(metrics_retention_minutes)
        self.permission_checks = deque(maxlen=10000)
        self.cache_operations = deque(maxlen=1000) 
        self.team_lookups = deque(maxlen=1000)
        self.rls_queries = deque(maxlen=1000)
        self.security_violations = deque(maxlen=100)
        
    def record_permission_check(self, response_time_ms: float, cache_hit: bool, success: bool):
        """Record authorization permission check."""
        timestamp = datetime.utcnow()
        self.permission_checks.append({
            'timestamp': timestamp,
            'response_time_ms': response_time_ms,
            'cache_hit': cache_hit,
            'success': success
        })
        
        # Alert on slow permission checks
        if response_time_ms > 100:  # 100ms threshold
            logger.warning(f"⚠️ [AUTH-PERF] Slow permission check: {response_time_ms:.1f}ms")
            
    def record_cache_operation(self, operation_type: str, hit: bool, response_time_ms: float = 0):
        """Record cache operation metrics."""
        self.cache_operations.append({
            'timestamp': datetime.utcnow(),
            'operation': operation_type,
            'hit': hit,
            'response_time_ms': response_time_ms
        })
        
    def record_team_lookup(self, user_id: str, response_time_ms: float, team_count: int):
        """Record team lookup performance."""
        self.team_lookups.append({
            'timestamp': datetime.utcnow(),
            'user_id': user_id[:8],  # Only store prefix for privacy
            'response_time_ms': response_time_ms,
            'team_count': team_count
        })
        
    def record_rls_query(self, query_type: str, response_time_ms: float, rows_examined: int = 0):
        """Record RLS query performance."""
        self.rls_queries.append({
            'timestamp': datetime.utcnow(),
            'query_type': query_type,
            'response_time_ms': response_time_ms,
            'rows_examined': rows_examined
        })
        
        # Alert on slow RLS queries
        if response_time_ms > 50:  # 50ms threshold for RLS
            logger.warning(f"⚠️ [RLS-PERF] Slow RLS query ({query_type}): {response_time_ms:.1f}ms")
            
    def record_security_violation(self, violation_type: str, user_id: str, resource_type: str):
        """Record security violation."""
        self.security_violations.append({
            'timestamp': datetime.utcnow(),
            'violation_type': violation_type,
            'user_id': user_id[:8],  # Only store prefix for privacy
            'resource_type': resource_type
        })
        
        logger.error(f"🚨 [SECURITY] Violation detected: {violation_type} by user {user_id[:8]}")
        
    async def collect_authorization_metrics(self) -> AuthorizationMetrics:
        """Collect authorization-specific metrics."""
        now = datetime.utcnow()
        one_minute_ago = now - timedelta(minutes=1)
        
        # Permission checks per minute
        recent_permission_checks = [
            check for check in self.permission_checks
            if check['timestamp'] > one_minute_ago
        ]
        
        permission_checks_per_minute = len(recent_permission_checks)
        
        # Average permission check time
        if recent_permission_checks:
            avg_permission_time = sum(
                check['response_time_ms'] for check in recent_permission_checks
            ) / len(recent_permission_checks)
        else:
            avg_permission_time = 0.0
            
        # Cache hit rate
        recent_cache_ops = [
            op for op in self.cache_operations
            if op['timestamp'] > one_minute_ago
        ]
        
        if recent_cache_ops:
            cache_hits = sum(1 for op in recent_cache_ops if op['hit'])
            cache_hit_rate = (cache_hits / len(recent_cache_ops)) * 100
        else:
            cache_hit_rate = 100.0
            
        # Team lookup performance
        recent_team_lookups = [
            lookup for lookup in self.team_lookups
            if lookup['timestamp'] > one_minute_ago
        ]
        
        if recent_team_lookups:
            avg_team_lookup_time = sum(
                lookup['response_time_ms'] for lookup in recent_team_lookups
            ) / len(recent_team_lookups)
        else:
            avg_team_lookup_time = 0.0
            
        # RLS query performance
        recent_rls_queries = [
            query for query in self.rls_queries
            if query['timestamp'] > one_minute_ago
        ]
        
        if recent_rls_queries:
            avg_rls_time = sum(
                query['response_time_ms'] for query in recent_rls_queries
            ) / len(recent_rls_queries)
        else:
            avg_rls_time = 0.0
            
        # Failed authorizations
        failed_auths = sum(
            1 for check in recent_permission_checks
            if not check['success']
        )
        
        # Security violations
        recent_violations = len([
            v for v in self.security_violations
            if v['timestamp'] > one_minute_ago
        ])
        
        return AuthorizationMetrics(
            permission_checks_per_minute=permission_checks_per_minute,
            avg_permission_check_time_ms=avg_permission_time,
            cache_hit_rate_percent=cache_hit_rate,
            team_lookup_time_ms=avg_team_lookup_time,
            rls_query_time_ms=avg_rls_time,
            failed_authorization_count=failed_auths,
            security_violations_count=recent_violations
        )
        
    async def get_authorization_dashboard(self) -> Dict[str, Any]:
        """Get comprehensive authorization performance dashboard."""
        auth_metrics = await self.collect_authorization_metrics()
        base_metrics = await self.collect_metrics()
        
        # Performance status
        performance_status = "healthy"
        alerts = []
        
        if auth_metrics.avg_permission_check_time_ms > 100:
            performance_status = "degraded"
            alerts.append("Slow authorization responses")
            
        if auth_metrics.cache_hit_rate_percent < 80:
            performance_status = "degraded"
            alerts.append("Low cache hit rate")
            
        if auth_metrics.security_violations_count > 0:
            performance_status = "alert"
            alerts.append(f"{auth_metrics.security_violations_count} security violations detected")
            
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "performance_status": performance_status,
            "authorization_metrics": asdict(auth_metrics),
            "system_metrics": asdict(base_metrics),
            "alerts": alerts,
            "recommendations": self._get_performance_recommendations(auth_metrics)
        }
        
    def _get_performance_recommendations(self, auth_metrics: AuthorizationMetrics) -> List[str]:
        """Generate performance recommendations."""
        recommendations = []
        
        if auth_metrics.avg_permission_check_time_ms > 50:
            recommendations.append(
                "Consider adding more database indexes or optimizing RLS policies"
            )
            
        if auth_metrics.cache_hit_rate_percent < 85:
            recommendations.append(
                "Increase cache TTL or implement cache warming strategies"
            )
            
        if auth_metrics.permission_checks_per_minute > 1000:
            recommendations.append(
                "High authorization load detected - consider horizontal scaling"
            )
            
        if auth_metrics.failed_authorization_count > auth_metrics.permission_checks_per_minute * 0.05:
            recommendations.append(
                "High authorization failure rate - review permissions configuration"
            )
            
        if not recommendations:
            recommendations.append("Authorization system performance is optimal")
            
        return recommendations

# Global performance monitor instance
performance_monitor = AuthorizationPerformanceMonitor()

# Enterprise monitoring functions for external integration
async def get_real_time_metrics() -> Dict[str, Any]:
    """Get real-time performance metrics for external monitoring."""
    return await performance_monitor.get_authorization_dashboard()

async def check_system_health() -> Dict[str, Any]:
    """Comprehensive system health check."""
    dashboard = await performance_monitor.get_authorization_dashboard()
    
    health_score = 100
    critical_issues = []
    
    # Reduce score based on performance issues
    auth_metrics = dashboard["authorization_metrics"]
    
    if auth_metrics["avg_permission_check_time_ms"] > 200:
        health_score -= 30
        critical_issues.append("Critical: Authorization response time > 200ms")
    elif auth_metrics["avg_permission_check_time_ms"] > 100:
        health_score -= 15
        
    if auth_metrics["cache_hit_rate_percent"] < 70:
        health_score -= 20
        critical_issues.append("Critical: Cache hit rate < 70%")
        
    if auth_metrics["security_violations_count"] > 0:
        health_score -= 25
        critical_issues.append(f"Security: {auth_metrics['security_violations_count']} violations")
        
    system_metrics = dashboard["system_metrics"]
    if system_metrics["cpu_percent"] > 90:
        health_score -= 20
        critical_issues.append("Critical: CPU usage > 90%")
        
    if system_metrics["memory_percent"] > 90:
        health_score -= 20
        critical_issues.append("Critical: Memory usage > 90%")
        
    return {
        "health_score": max(0, health_score),
        "status": "healthy" if health_score >= 80 else "degraded" if health_score >= 50 else "critical",
        "critical_issues": critical_issues,
        "dashboard": dashboard,
        "timestamp": datetime.utcnow().isoformat()
    }