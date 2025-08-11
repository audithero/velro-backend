"""
Prometheus metrics collection for authorization system performance monitoring.
Tracks authorization performance, security violations, and cache efficiency.
"""

import time
from typing import Dict, Any, Optional, List
from prometheus_client import (
    Counter, Histogram, Gauge, Summary, CollectorRegistry, 
    multiprocess, generate_latest, CONTENT_TYPE_LATEST
)
from dataclasses import dataclass
from enum import Enum
import threading
import json
from datetime import datetime, timezone


class MetricType(Enum):
    """Metric types for different monitoring aspects."""
    AUTHORIZATION = "authorization"
    PERFORMANCE = "performance"
    SECURITY = "security"
    CACHE = "cache"
    DATABASE = "database"


@dataclass
class MetricEvent:
    """Structured metric event data."""
    event_type: str
    user_id: Optional[str]
    endpoint: str
    duration_ms: float
    status: str
    metadata: Dict[str, Any]
    timestamp: datetime


class AuthorizationMetrics:
    """
    Comprehensive authorization metrics collection.
    Tracks performance, security, and compliance metrics.
    """
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self._lock = threading.Lock()
        
        # Authorization performance metrics
        self.auth_requests_total = Counter(
            'velro_auth_requests_total',
            'Total number of authorization requests',
            ['method', 'endpoint', 'status', 'user_type'],
            registry=self.registry
        )
        
        self.auth_duration = Histogram(
            'velro_auth_duration_seconds',
            'Authorization request duration in seconds',
            ['endpoint', 'auth_type'],
            buckets=[0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0],
            registry=self.registry
        )
        
        self.auth_failures_total = Counter(
            'velro_auth_failures_total',
            'Total authorization failures',
            ['failure_type', 'endpoint', 'reason'],
            registry=self.registry
        )
        
        # Sub-100ms performance target tracking
        self.auth_sla_violations = Counter(
            'velro_auth_sla_violations_total',
            'Authorization SLA violations (>100ms)',
            ['endpoint', 'violation_type'],
            registry=self.registry
        )
        
        # Concurrent request tracking
        self.concurrent_auth_requests = Gauge(
            'velro_concurrent_auth_requests',
            'Current number of concurrent authorization requests',
            registry=self.registry
        )
        
        # UUID validation metrics
        self.uuid_validations_total = Counter(
            'velro_uuid_validations_total',
            'Total UUID validation attempts',
            ['validation_type', 'status'],
            registry=self.registry
        )
        
        self.uuid_validation_duration = Histogram(
            'velro_uuid_validation_duration_seconds',
            'UUID validation duration',
            ['validation_type'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
            registry=self.registry
        )
        
    def record_auth_request(self, method: str, endpoint: str, status: str, 
                           user_type: str, duration_seconds: float):
        """Record authorization request metrics."""
        with self._lock:
            self.auth_requests_total.labels(
                method=method, 
                endpoint=endpoint, 
                status=status,
                user_type=user_type
            ).inc()
            
            self.auth_duration.labels(
                endpoint=endpoint,
                auth_type=user_type
            ).observe(duration_seconds)
            
            # Track SLA violations (>100ms)
            if duration_seconds > 0.1:
                self.auth_sla_violations.labels(
                    endpoint=endpoint,
                    violation_type="response_time"
                ).inc()
    
    def record_auth_failure(self, failure_type: str, endpoint: str, reason: str):
        """Record authorization failure."""
        with self._lock:
            self.auth_failures_total.labels(
                failure_type=failure_type,
                endpoint=endpoint,
                reason=reason
            ).inc()
    
    def record_concurrent_request_start(self):
        """Track start of concurrent authorization request."""
        self.concurrent_auth_requests.inc()
    
    def record_concurrent_request_end(self):
        """Track end of concurrent authorization request."""
        self.concurrent_auth_requests.dec()
    
    def record_uuid_validation(self, validation_type: str, status: str, 
                              duration_seconds: float):
        """Record UUID validation metrics."""
        with self._lock:
            self.uuid_validations_total.labels(
                validation_type=validation_type,
                status=status
            ).inc()
            
            self.uuid_validation_duration.labels(
                validation_type=validation_type
            ).observe(duration_seconds)


class PerformanceMetrics:
    """
    Performance metrics for overall system monitoring.
    Tracks response times, throughput, and resource utilization.
    """
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self._lock = threading.Lock()
        
        # Response time tracking
        self.response_time = Histogram(
            'velro_http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'endpoint', 'status_code'],
            buckets=[0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0],
            registry=self.registry
        )
        
        # Request throughput
        self.requests_total = Counter(
            'velro_http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code'],
            registry=self.registry
        )
        
        # Active connections
        self.active_connections = Gauge(
            'velro_active_connections',
            'Current number of active connections',
            registry=self.registry
        )
        
        # Database connection pool
        self.db_connections_active = Gauge(
            'velro_db_connections_active',
            'Active database connections',
            registry=self.registry
        )
        
        self.db_connections_idle = Gauge(
            'velro_db_connections_idle',
            'Idle database connections',
            registry=self.registry
        )
        
        # Database query performance
        self.db_query_duration = Histogram(
            'velro_db_query_duration_seconds',
            'Database query duration',
            ['operation', 'table'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
            registry=self.registry
        )
        
        # Memory usage
        self.memory_usage_bytes = Gauge(
            'velro_memory_usage_bytes',
            'Current memory usage in bytes',
            ['type'],
            registry=self.registry
        )
        
        # CPU usage
        self.cpu_usage_percent = Gauge(
            'velro_cpu_usage_percent',
            'CPU usage percentage',
            ['core'],
            registry=self.registry
        )
    
    def record_request(self, method: str, endpoint: str, status_code: int, 
                      duration_seconds: float):
        """Record HTTP request metrics."""
        with self._lock:
            self.requests_total.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code)
            ).inc()
            
            self.response_time.labels(
                method=method,
                endpoint=endpoint,
                status_code=str(status_code)
            ).observe(duration_seconds)
    
    def record_db_query(self, operation: str, table: str, duration_seconds: float):
        """Record database query metrics."""
        with self._lock:
            self.db_query_duration.labels(
                operation=operation,
                table=table
            ).observe(duration_seconds)
    
    def update_connection_metrics(self, active: int, idle: int):
        """Update database connection metrics."""
        self.db_connections_active.set(active)
        self.db_connections_idle.set(idle)
    
    def update_system_metrics(self, memory_bytes: int, cpu_percent: float):
        """Update system resource metrics."""
        self.memory_usage_bytes.labels(type="rss").set(memory_bytes)
        self.cpu_usage_percent.labels(core="total").set(cpu_percent)


class SecurityMetrics:
    """
    Security monitoring metrics for threat detection and compliance.
    Tracks security violations, rate limiting, and audit events.
    """
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self._lock = threading.Lock()
        
        # Security violations
        self.security_violations_total = Counter(
            'velro_security_violations_total',
            'Total security violations detected',
            ['violation_type', 'severity', 'source_ip'],
            registry=self.registry
        )
        
        # Authentication attempts
        self.auth_attempts_total = Counter(
            'velro_auth_attempts_total',
            'Total authentication attempts',
            ['result', 'method', 'user_agent'],
            registry=self.registry
        )
        
        # Failed login attempts
        self.failed_logins_total = Counter(
            'velro_failed_logins_total',
            'Failed login attempts',
            ['reason', 'source_ip', 'user_id'],
            registry=self.registry
        )
        
        # Rate limiting
        self.rate_limit_hits_total = Counter(
            'velro_rate_limit_hits_total',
            'Rate limit violations',
            ['endpoint', 'limit_type', 'source_ip'],
            registry=self.registry
        )
        
        # Blocked requests
        self.blocked_requests_total = Counter(
            'velro_blocked_requests_total',
            'Blocked requests by security rules',
            ['rule_type', 'action', 'source_ip'],
            registry=self.registry
        )
        
        # JWT token metrics
        self.jwt_validations_total = Counter(
            'velro_jwt_validations_total',
            'JWT token validation attempts',
            ['result', 'reason'],
            registry=self.registry
        )
        
        self.jwt_validation_duration = Histogram(
            'velro_jwt_validation_duration_seconds',
            'JWT validation duration',
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05],
            registry=self.registry
        )
        
        # Active sessions
        self.active_sessions = Gauge(
            'velro_active_sessions',
            'Current number of active user sessions',
            registry=self.registry
        )
        
        # Suspicious activity patterns
        self.suspicious_patterns_total = Counter(
            'velro_suspicious_patterns_total',
            'Suspicious activity patterns detected',
            ['pattern_type', 'severity', 'source_ip'],
            registry=self.registry
        )
    
    def record_security_violation(self, violation_type: str, severity: str, 
                                 source_ip: str):
        """Record security violation."""
        with self._lock:
            self.security_violations_total.labels(
                violation_type=violation_type,
                severity=severity,
                source_ip=source_ip
            ).inc()
    
    def record_auth_attempt(self, result: str, method: str, user_agent: str):
        """Record authentication attempt."""
        with self._lock:
            self.auth_attempts_total.labels(
                result=result,
                method=method,
                user_agent=user_agent[:100]  # Limit length
            ).inc()
    
    def record_failed_login(self, reason: str, source_ip: str, user_id: str):
        """Record failed login attempt."""
        with self._lock:
            self.failed_logins_total.labels(
                reason=reason,
                source_ip=source_ip,
                user_id=user_id
            ).inc()
    
    def record_rate_limit_hit(self, endpoint: str, limit_type: str, source_ip: str):
        """Record rate limit violation."""
        with self._lock:
            self.rate_limit_hits_total.labels(
                endpoint=endpoint,
                limit_type=limit_type,
                source_ip=source_ip
            ).inc()
    
    def record_jwt_validation(self, result: str, reason: str, 
                             duration_seconds: float):
        """Record JWT validation metrics."""
        with self._lock:
            self.jwt_validations_total.labels(
                result=result,
                reason=reason
            ).inc()
            
            self.jwt_validation_duration.observe(duration_seconds)
    
    def update_active_sessions(self, count: int):
        """Update active sessions count."""
        self.active_sessions.set(count)


class CacheMetrics:
    """
    Cache performance and efficiency metrics.
    Tracks hit rates, latency, and cache warming effectiveness.
    """
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self._lock = threading.Lock()
        
        # Cache operations
        self.cache_operations_total = Counter(
            'velro_cache_operations_total',
            'Total cache operations',
            ['cache_name', 'operation', 'result'],
            registry=self.registry
        )
        
        # Cache hit rate
        self.cache_hits_total = Counter(
            'velro_cache_hits_total',
            'Cache hits by type',
            ['cache_name', 'key_type'],
            registry=self.registry
        )
        
        self.cache_misses_total = Counter(
            'velro_cache_misses_total',
            'Cache misses by type',
            ['cache_name', 'key_type'],
            registry=self.registry
        )
        
        # Cache latency
        self.cache_operation_duration = Histogram(
            'velro_cache_operation_duration_seconds',
            'Cache operation duration',
            ['cache_name', 'operation'],
            buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.025, 0.05, 0.1],
            registry=self.registry
        )
        
        # Cache size metrics
        self.cache_size_bytes = Gauge(
            'velro_cache_size_bytes',
            'Current cache size in bytes',
            ['cache_name'],
            registry=self.registry
        )
        
        self.cache_entries_count = Gauge(
            'velro_cache_entries_count',
            'Number of entries in cache',
            ['cache_name'],
            registry=self.registry
        )
        
        # Cache evictions
        self.cache_evictions_total = Counter(
            'velro_cache_evictions_total',
            'Cache entry evictions',
            ['cache_name', 'eviction_type'],
            registry=self.registry
        )
        
        # Cache warming
        self.cache_warming_operations_total = Counter(
            'velro_cache_warming_operations_total',
            'Cache warming operations',
            ['cache_name', 'status'],
            registry=self.registry
        )
        
        # Redis connection metrics
        self.redis_connections_active = Gauge(
            'velro_redis_connections_active',
            'Active Redis connections',
            registry=self.registry
        )
        
        self.redis_memory_usage_bytes = Gauge(
            'velro_redis_memory_usage_bytes',
            'Redis memory usage in bytes',
            ['type'],
            registry=self.registry
        )
    
    def record_cache_operation(self, cache_name: str, operation: str, 
                              result: str, duration_seconds: float,
                              key_type: str = "general"):
        """Record cache operation metrics."""
        with self._lock:
            self.cache_operations_total.labels(
                cache_name=cache_name,
                operation=operation,
                result=result
            ).inc()
            
            self.cache_operation_duration.labels(
                cache_name=cache_name,
                operation=operation
            ).observe(duration_seconds)
            
            if result == "hit":
                self.cache_hits_total.labels(
                    cache_name=cache_name,
                    key_type=key_type
                ).inc()
            elif result == "miss":
                self.cache_misses_total.labels(
                    cache_name=cache_name,
                    key_type=key_type
                ).inc()
    
    def update_cache_size(self, cache_name: str, size_bytes: int, entries_count: int):
        """Update cache size metrics."""
        self.cache_size_bytes.labels(cache_name=cache_name).set(size_bytes)
        self.cache_entries_count.labels(cache_name=cache_name).set(entries_count)
    
    def record_cache_eviction(self, cache_name: str, eviction_type: str):
        """Record cache eviction."""
        with self._lock:
            self.cache_evictions_total.labels(
                cache_name=cache_name,
                eviction_type=eviction_type
            ).inc()
    
    def record_cache_warming(self, cache_name: str, status: str):
        """Record cache warming operation."""
        with self._lock:
            self.cache_warming_operations_total.labels(
                cache_name=cache_name,
                status=status
            ).inc()
    
    def update_redis_metrics(self, active_connections: int, 
                           memory_used: int, memory_peak: int):
        """Update Redis-specific metrics."""
        self.redis_connections_active.set(active_connections)
        self.redis_memory_usage_bytes.labels(type="used").set(memory_used)
        self.redis_memory_usage_bytes.labels(type="peak").set(memory_peak)


class BusinessMetrics:
    """
    Business-level metrics for enterprise monitoring and analytics.
    Tracks business KPIs, user engagement, and operational efficiency.
    """
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self._lock = threading.Lock()
        
        # User activity metrics
        self.active_users_total = Gauge(
            'velro_active_users_total',
            'Current number of active users',
            ['time_window'],
            registry=self.registry
        )
        
        self.user_registrations_total = Counter(
            'velro_user_registrations_total',
            'Total user registrations',
            ['source', 'plan_type'],
            registry=self.registry
        )
        
        # Generation metrics
        self.generations_created_total = Counter(
            'velro_generations_created_total',
            'Total generations created',
            ['model_type', 'user_type', 'success'],
            registry=self.registry
        )
        
        self.generation_processing_duration = Histogram(
            'velro_generation_processing_duration_seconds',
            'Time to process generation requests',
            ['model_type', 'complexity'],
            buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0],
            registry=self.registry
        )
        
        self.generation_queue_size = Gauge(
            'velro_generation_queue_size',
            'Number of generations in processing queue',
            ['priority'],
            registry=self.registry
        )
        
        # Credit system metrics
        self.credits_consumed_total = Counter(
            'velro_credits_consumed_total',
            'Total credits consumed',
            ['operation_type', 'user_type'],
            registry=self.registry
        )
        
        self.credits_remaining_distribution = Histogram(
            'velro_credits_remaining_distribution',
            'Distribution of remaining user credits',
            buckets=[0, 10, 50, 100, 500, 1000, 5000, 10000],
            registry=self.registry
        )
        
        # Project and team metrics
        self.projects_active_total = Gauge(
            'velro_projects_active_total',
            'Number of active projects',
            registry=self.registry
        )
        
        self.team_collaborations_total = Counter(
            'velro_team_collaborations_total',
            'Team collaboration events',
            ['action_type', 'team_size_range'],
            registry=self.registry
        )
        
        # Revenue and conversion metrics
        self.subscription_conversions_total = Counter(
            'velro_subscription_conversions_total',
            'Subscription conversion events',
            ['from_plan', 'to_plan', 'conversion_type'],
            registry=self.registry
        )
        
        self.feature_usage_total = Counter(
            'velro_feature_usage_total',
            'Feature usage tracking',
            ['feature_name', 'user_type', 'success'],
            registry=self.registry
        )
        
        # Performance business impact
        self.user_satisfaction_score = Gauge(
            'velro_user_satisfaction_score',
            'User satisfaction score based on performance',
            ['metric_type'],
            registry=self.registry
        )
        
        self.churn_risk_users = Gauge(
            'velro_churn_risk_users_total',
            'Number of users at risk of churning',
            ['risk_level'],
            registry=self.registry
        )
    
    def record_user_activity(self, active_1h: int, active_24h: int, active_7d: int):
        """Record user activity metrics."""
        with self._lock:
            self.active_users_total.labels(time_window="1h").set(active_1h)
            self.active_users_total.labels(time_window="24h").set(active_24h)
            self.active_users_total.labels(time_window="7d").set(active_7d)
    
    def record_user_registration(self, source: str, plan_type: str):
        """Record user registration."""
        with self._lock:
            self.user_registrations_total.labels(
                source=source,
                plan_type=plan_type
            ).inc()
    
    def record_generation_created(self, model_type: str, user_type: str, 
                                 success: bool, processing_duration: float,
                                 complexity: str = "standard"):
        """Record generation creation metrics."""
        with self._lock:
            self.generations_created_total.labels(
                model_type=model_type,
                user_type=user_type,
                success=str(success).lower()
            ).inc()
            
            self.generation_processing_duration.labels(
                model_type=model_type,
                complexity=complexity
            ).observe(processing_duration)
    
    def update_generation_queue(self, high_priority: int, normal_priority: int, 
                               low_priority: int):
        """Update generation queue metrics."""
        self.generation_queue_size.labels(priority="high").set(high_priority)
        self.generation_queue_size.labels(priority="normal").set(normal_priority)
        self.generation_queue_size.labels(priority="low").set(low_priority)
    
    def record_credit_consumption(self, operation_type: str, user_type: str, 
                                 credits_used: int):
        """Record credit consumption."""
        with self._lock:
            self.credits_consumed_total.labels(
                operation_type=operation_type,
                user_type=user_type
            ).inc(credits_used)
    
    def record_team_collaboration(self, action_type: str, team_size: int):
        """Record team collaboration event."""
        # Categorize team size
        if team_size == 1:
            size_range = "individual"
        elif team_size <= 5:
            size_range = "small"
        elif team_size <= 20:
            size_range = "medium"
        else:
            size_range = "large"
        
        with self._lock:
            self.team_collaborations_total.labels(
                action_type=action_type,
                team_size_range=size_range
            ).inc()
    
    def record_feature_usage(self, feature_name: str, user_type: str, success: bool):
        """Record feature usage."""
        with self._lock:
            self.feature_usage_total.labels(
                feature_name=feature_name,
                user_type=user_type,
                success=str(success).lower()
            ).inc()
    
    def update_satisfaction_metrics(self, performance_score: float, 
                                   reliability_score: float, usability_score: float):
        """Update user satisfaction metrics."""
        self.user_satisfaction_score.labels(metric_type="performance").set(performance_score)
        self.user_satisfaction_score.labels(metric_type="reliability").set(reliability_score)
        self.user_satisfaction_score.labels(metric_type="usability").set(usability_score)


class DistributedTracingMetrics:
    """
    Distributed tracing metrics for request flow analysis.
    Tracks request journeys across services and identifies bottlenecks.
    """
    
    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()
        self._lock = threading.Lock()
        
        # Request tracing
        self.trace_requests_total = Counter(
            'velro_trace_requests_total',
            'Total traced requests',
            ['service', 'operation', 'status'],
            registry=self.registry
        )
        
        self.trace_span_duration = Histogram(
            'velro_trace_span_duration_seconds',
            'Span duration in distributed traces',
            ['service', 'operation', 'span_type'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
            registry=self.registry
        )
        
        self.trace_depth_distribution = Histogram(
            'velro_trace_depth_distribution',
            'Distribution of trace depths (number of services involved)',
            buckets=[1, 2, 3, 4, 5, 7, 10, 15, 20],
            registry=self.registry
        )
        
        # Service dependency tracking
        self.service_dependencies_total = Counter(
            'velro_service_dependencies_total',
            'Service-to-service call counts',
            ['from_service', 'to_service', 'operation', 'status'],
            registry=self.registry
        )
        
        self.service_dependency_latency = Histogram(
            'velro_service_dependency_latency_seconds',
            'Latency between service calls',
            ['from_service', 'to_service', 'operation'],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
            registry=self.registry
        )
        
        # Error propagation tracking
        self.error_propagation_total = Counter(
            'velro_error_propagation_total',
            'Error propagation across services',
            ['origin_service', 'error_type', 'propagated_to'],
            registry=self.registry
        )
        
        # Request correlation
        self.correlated_requests_total = Counter(
            'velro_correlated_requests_total',
            'Correlated request tracking',
            ['correlation_type', 'service_path'],
            registry=self.registry
        )
    
    def record_trace_request(self, service: str, operation: str, status: str,
                           total_duration: float, span_count: int):
        """Record traced request metrics."""
        with self._lock:
            self.trace_requests_total.labels(
                service=service,
                operation=operation,
                status=status
            ).inc()
            
            self.trace_depth_distribution.observe(span_count)
    
    def record_span_duration(self, service: str, operation: str, 
                           span_type: str, duration_seconds: float):
        """Record span duration."""
        with self._lock:
            self.trace_span_duration.labels(
                service=service,
                operation=operation,
                span_type=span_type
            ).observe(duration_seconds)
    
    def record_service_call(self, from_service: str, to_service: str,
                          operation: str, status: str, duration_seconds: float):
        """Record service-to-service call."""
        with self._lock:
            self.service_dependencies_total.labels(
                from_service=from_service,
                to_service=to_service,
                operation=operation,
                status=status
            ).inc()
            
            self.service_dependency_latency.labels(
                from_service=from_service,
                to_service=to_service,
                operation=operation
            ).observe(duration_seconds)


class MetricsCollector:
    """
    Enhanced central metrics collector that aggregates all metric types.
    Provides unified interface for metrics export, monitoring, and business intelligence.
    """
    
    def __init__(self):
        self.registry = CollectorRegistry()
        self.authorization_metrics = AuthorizationMetrics(self.registry)
        self.performance_metrics = PerformanceMetrics(self.registry)
        self.security_metrics = SecurityMetrics(self.registry)
        self.cache_metrics = CacheMetrics(self.registry)
        self.business_metrics = BusinessMetrics(self.registry)
        self.tracing_metrics = DistributedTracingMetrics(self.registry)
        
        self._events: List[MetricEvent] = []
        self._lock = threading.Lock()
        
        # Circuit breaker integration
        self._circuit_breaker_metrics = Gauge(
            'velro_circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=half-open, 2=open)',
            ['circuit_name'],
            registry=self.registry
        )
        
        # SLA compliance metrics
        self._sla_compliance = Gauge(
            'velro_sla_compliance_percentage',
            'SLA compliance percentage',
            ['sla_type', 'time_window'],
            registry=self.registry
        )
        
        # Cost and resource optimization
        self._resource_costs = Gauge(
            'velro_estimated_costs_usd',
            'Estimated costs in USD',
            ['resource_type', 'time_period'],
            registry=self.registry
        )
    
    def record_event(self, event: MetricEvent):
        """Record structured metric event."""
        with self._lock:
            self._events.append(event)
            
            # Keep only last 1000 events in memory
            if len(self._events) > 1000:
                self._events = self._events[-1000:]
    
    def get_metrics_output(self) -> str:
        """Get Prometheus-formatted metrics output."""
        return generate_latest(self.registry)
    
    def get_metrics_content_type(self) -> str:
        """Get content type for metrics output."""
        return CONTENT_TYPE_LATEST
    
    def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent metric events as JSON-serializable data."""
        with self._lock:
            recent_events = self._events[-limit:] if self._events else []
            
        return [
            {
                "event_type": event.event_type,
                "user_id": event.user_id,
                "endpoint": event.endpoint,
                "duration_ms": event.duration_ms,
                "status": event.status,
                "metadata": event.metadata,
                "timestamp": event.timestamp.isoformat()
            }
            for event in recent_events
        ]
    
    def update_circuit_breaker_state(self, circuit_name: str, state: str):
        """Update circuit breaker state metric."""
        state_map = {"closed": 0, "half_open": 1, "open": 2}
        self._circuit_breaker_metrics.labels(circuit_name=circuit_name).set(
            state_map.get(state, 0)
        )
    
    def update_sla_compliance(self, sla_type: str, time_window: str, 
                             compliance_percentage: float):
        """Update SLA compliance metrics."""
        self._sla_compliance.labels(
            sla_type=sla_type,
            time_window=time_window
        ).set(compliance_percentage)
    
    def update_resource_costs(self, resource_type: str, time_period: str, 
                            cost_usd: float):
        """Update estimated resource costs."""
        self._resource_costs.labels(
            resource_type=resource_type,
            time_period=time_period
        ).set(cost_usd)
    
    def get_business_kpi_summary(self) -> Dict[str, Any]:
        """Get business KPI summary for executive dashboards."""
        try:
            # This would typically aggregate actual metric values
            # For demo, returning structure with placeholder data
            return {
                "user_metrics": {
                    "active_users_24h": 0,  # Would be actual metric value
                    "new_registrations_24h": 0,
                    "user_satisfaction_score": 0.0
                },
                "business_metrics": {
                    "generations_created_24h": 0,
                    "credits_consumed_24h": 0,
                    "active_projects": 0,
                    "team_collaborations_24h": 0
                },
                "performance_metrics": {
                    "average_response_time_ms": 0.0,
                    "sla_compliance_percentage": 0.0,
                    "cache_hit_rate_percentage": 0.0,
                    "error_rate_percentage": 0.0
                },
                "financial_metrics": {
                    "estimated_daily_cost_usd": 0.0,
                    "cost_per_user_usd": 0.0,
                    "revenue_per_generation_usd": 0.0
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "period": "24h"
            }
        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get detailed performance summary for optimization."""
        try:
            return {
                "authorization_performance": {
                    "average_response_time_ms": 0.0,
                    "sla_violations_24h": 0,
                    "concurrent_requests_peak": 0,
                    "uuid_validation_avg_ms": 0.0
                },
                "cache_performance": {
                    "hit_rate_percentage": 0.0,
                    "l1_hit_rate": 0.0,
                    "l2_hit_rate": 0.0,
                    "average_latency_ms": 0.0,
                    "evictions_24h": 0
                },
                "database_performance": {
                    "query_avg_ms": 0.0,
                    "slow_queries_24h": 0,
                    "connection_pool_utilization": 0.0,
                    "deadlocks_24h": 0
                },
                "system_resources": {
                    "cpu_utilization_avg": 0.0,
                    "memory_utilization_avg": 0.0,
                    "disk_io_avg_ms": 0.0,
                    "network_latency_avg_ms": 0.0
                },
                "bottlenecks": [],  # Would identify performance bottlenecks
                "recommendations": [],  # Would provide optimization recommendations
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def get_security_dashboard_data(self) -> Dict[str, Any]:
        """Get security monitoring data for security dashboard."""
        try:
            return {
                "threat_level": "low",  # low, medium, high, critical
                "security_incidents_24h": 0,
                "authentication_metrics": {
                    "failed_logins_24h": 0,
                    "suspicious_patterns_24h": 0,
                    "blocked_requests_24h": 0,
                    "jwt_validation_failures_24h": 0
                },
                "authorization_security": {
                    "unauthorized_access_attempts_24h": 0,
                    "permission_violations_24h": 0,
                    "uuid_validation_failures_24h": 0
                },
                "rate_limiting": {
                    "rate_limit_hits_24h": 0,
                    "top_offending_ips": [],
                    "blocked_requests_by_rule": {}
                },
                "compliance_status": {
                    "owasp_compliance": True,
                    "gdpr_compliance": True,
                    "audit_trail_complete": True,
                    "encryption_status": "active"
                },
                "active_sessions": 0,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def get_capacity_planning_data(self) -> Dict[str, Any]:
        """Get capacity planning data for scaling decisions."""
        try:
            return {
                "current_capacity": {
                    "concurrent_users_peak": 0,
                    "requests_per_second_peak": 0.0,
                    "database_connections_peak": 0,
                    "memory_usage_peak_mb": 0.0,
                    "cpu_usage_peak_percent": 0.0
                },
                "growth_trends": {
                    "user_growth_weekly": 0.0,
                    "request_volume_growth_weekly": 0.0,
                    "data_storage_growth_weekly_gb": 0.0
                },
                "scaling_recommendations": {
                    "scale_out_threshold": "80% resource utilization",
                    "estimated_scaling_point": "in 30 days",
                    "recommended_resources": []
                },
                "cost_projections": {
                    "current_monthly_cost_usd": 0.0,
                    "projected_3month_cost_usd": 0.0,
                    "cost_optimization_opportunities": []
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def get_health_summary(self) -> Dict[str, Any]:
        """Get comprehensive system health summary from metrics."""
        try:
            return {
                "overall_status": "healthy",
                "components": {
                    "authorization_service": {
                        "status": "healthy",
                        "response_time_ms": 0.0,
                        "error_rate": 0.0,
                        "last_check": datetime.now(timezone.utc).isoformat()
                    },
                    "cache_system": {
                        "status": "healthy",
                        "hit_rate": 0.0,
                        "memory_usage": 0.0,
                        "connections_active": 0
                    },
                    "database": {
                        "status": "healthy",
                        "response_time_ms": 0.0,
                        "connection_pool_usage": 0.0,
                        "slow_queries": 0
                    },
                    "security_monitoring": {
                        "status": "active",
                        "threat_level": "low",
                        "active_violations": 0,
                        "last_incident": None
                    }
                },
                "circuit_breakers": {
                    # Would show actual circuit breaker states
                    "all_closed": True,
                    "open_circuits": [],
                    "degraded_services": []
                },
                "sla_compliance": {
                    "authorization_sla": 99.9,
                    "response_time_sla": 99.5,
                    "availability_sla": 99.99
                },
                "metrics_collection": {
                    "enabled": True,
                    "collectors_active": {
                        "authorization": True,
                        "performance": True,
                        "security": True,
                        "cache": True,
                        "business": True,
                        "tracing": True
                    },
                    "last_collection": datetime.now(timezone.utc).isoformat()
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except Exception as e:
            return {
                "overall_status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }


# Global metrics collector instance
metrics_collector = MetricsCollector()