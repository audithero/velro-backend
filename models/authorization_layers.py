"""
Authorization Layers Models and Enums
Comprehensive data models and enumerations for the 10-layer authorization system.

This module provides:
1. Layer type definitions and configurations
2. Security threat assessment models
3. Anomaly detection type definitions
4. Performance optimization models
5. Audit logging structures
6. Emergency recovery system models

OWASP Compliance:
- A01 (Broken Access Control): Comprehensive authorization models
- A03 (Injection): Input validation and sanitization models
- A04 (Insecure Design): Secure design patterns and threat modeling
- A09 (Security Logging Failures): Comprehensive audit models
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Union, Set
from uuid import UUID
import json


# ============================================================================
# CORE AUTHORIZATION LAYER TYPES
# ============================================================================

class AuthorizationLayerType(str, Enum):
    """
    Comprehensive 10-layer authorization system types.
    Each layer provides specific security validation with defined performance targets.
    """
    # Existing layers (1-3) - Already implemented
    BASIC_UUID_VALIDATION = "basic_uuid_validation"
    RBAC_PERMISSION_CHECK = "rbac_permission_check"
    RESOURCE_OWNERSHIP_VALIDATION = "resource_ownership_validation"
    
    # New layers (4-10) - PRD compliance requirements
    SECURITY_CONTEXT_VALIDATION = "security_context_validation"
    GENERATION_INHERITANCE_VALIDATION = "generation_inheritance_validation"
    MEDIA_ACCESS_AUTHORIZATION = "media_access_authorization"
    PERFORMANCE_OPTIMIZATION_LAYER = "performance_optimization_layer"
    AUDIT_SECURITY_LOGGING_LAYER = "audit_security_logging_layer"
    EMERGENCY_RECOVERY_SYSTEMS = "emergency_recovery_systems"
    ADVANCED_RATE_LIMITING_ANOMALY_DETECTION = "advanced_rate_limiting_anomaly_detection"


@dataclass
class LayerConfiguration:
    """Configuration for individual authorization layer."""
    layer_type: AuthorizationLayerType
    enabled: bool = True
    max_execution_time_ms: float = 10.0
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    failure_mode: str = "fail_secure"  # "fail_secure" or "fail_open"
    critical: bool = False
    dependencies: List[AuthorizationLayerType] = field(default_factory=list)
    configuration: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# SECURITY THREAT ASSESSMENT
# ============================================================================

class SecurityThreatLevel(str, Enum):
    """Security threat assessment levels with corresponding actions."""
    GREEN = "green"      # Normal operation - proceed
    YELLOW = "yellow"    # Minor anomaly - proceed with caution
    ORANGE = "orange"    # Significant threat - enhanced monitoring
    RED = "red"         # Critical threat - block immediately


class ThreatCategory(str, Enum):
    """Categories of security threats."""
    AUTHENTICATION_ABUSE = "authentication_abuse"
    AUTHORIZATION_BYPASS = "authorization_bypass"
    INJECTION_ATTACK = "injection_attack"
    RATE_LIMIT_ABUSE = "rate_limit_abuse"
    GEOGRAPHIC_ANOMALY = "geographic_anomaly"
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DATA_EXFILTRATION = "data_exfiltration"
    SYSTEM_COMPROMISE = "system_compromise"


class AnomalyType(str, Enum):
    """Specific types of security anomalies detected."""
    # Rate limiting anomalies
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    REQUEST_SPIKE_DETECTED = "request_spike_detected"
    BURST_PATTERN_DETECTED = "burst_pattern_detected"
    
    # Geographic anomalies
    SUSPICIOUS_IP_PATTERN = "suspicious_ip_pattern"
    UNUSUAL_LOCATION_ACCESS = "unusual_location_access"
    GEOGRAPHIC_ANOMALY = "geographic_anomaly"
    VPN_TOR_DETECTED = "vpn_tor_detected"
    
    # User agent anomalies
    UNUSUAL_USER_AGENT = "unusual_user_agent"
    BOT_PATTERN_DETECTED = "bot_pattern_detected"
    AUTOMATION_DETECTED = "automation_detected"
    
    # Behavioral anomalies
    PRIVILEGE_ESCALATION_ATTEMPT = "privilege_escalation_attempt"
    UNUSUAL_ACCESS_PATTERN = "unusual_access_pattern"
    TIME_BASED_ANOMALY = "time_based_anomaly"
    
    # Attack patterns
    BRUTE_FORCE_DETECTED = "brute_force_detected"
    SQL_INJECTION_ATTEMPT = "sql_injection_attempt"
    XSS_ATTEMPT = "xss_attempt"
    CSRF_ATTEMPT = "csrf_attempt"
    
    # System anomalies
    SYSTEM_RESOURCE_ABUSE = "system_resource_abuse"
    API_ABUSE_DETECTED = "api_abuse_detected"


@dataclass
class ThreatIndicator:
    """Individual threat indicator with metadata."""
    indicator_type: AnomalyType
    severity: SecurityThreatLevel
    confidence: float  # 0.0 to 1.0
    timestamp: datetime
    description: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    mitigations_applied: List[str] = field(default_factory=list)


@dataclass
class ThreatAssessment:
    """Comprehensive threat assessment result."""
    overall_threat_level: SecurityThreatLevel
    threat_score: float  # 0.0 to 100.0
    indicators: List[ThreatIndicator]
    assessment_time: datetime
    risk_categories: List[ThreatCategory]
    recommended_actions: List[str]
    automated_mitigations: List[str]


# ============================================================================
# LAYER EXECUTION RESULTS
# ============================================================================

@dataclass
class LayerResult:
    """Result from individual authorization layer execution."""
    layer_type: AuthorizationLayerType
    success: bool
    execution_time_ms: float
    threat_level: SecurityThreatLevel = SecurityThreatLevel.GREEN
    anomalies: List[AnomalyType] = field(default_factory=list)
    cache_hit: bool = False
    cache_key: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_details: Optional[str] = None
    performance_metrics: Dict[str, float] = field(default_factory=dict)
    security_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LayerExecutionChain:
    """Complete execution chain for authorization layers."""
    request_id: str
    user_id: UUID
    resource_id: Optional[UUID]
    access_type: str
    start_time: datetime
    end_time: Optional[datetime] = None
    layer_results: List[LayerResult] = field(default_factory=list)
    final_decision: Optional[bool] = None
    total_execution_time_ms: Optional[float] = None
    overall_threat_level: SecurityThreatLevel = SecurityThreatLevel.GREEN
    failed_layers: List[AuthorizationLayerType] = field(default_factory=list)
    emergency_mode_activated: bool = False
    performance_target_met: bool = True


# ============================================================================
# SECURITY CONTEXT MODELS
# ============================================================================

@dataclass
class GeolocationData:
    """Geographic location data for security analysis."""
    country_code: str
    country_name: str
    region: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None
    is_vpn: bool = False
    is_tor: bool = False
    is_proxy: bool = False
    confidence: float = 1.0


@dataclass
class UserAgentAnalysis:
    """User agent analysis results."""
    browser_family: Optional[str]
    browser_version: Optional[str]
    operating_system: Optional[str]
    device_type: str  # desktop, mobile, tablet, bot
    is_bot: bool
    is_mobile: bool
    is_automation_tool: bool
    risk_score: float  # 0.0 to 1.0
    unusual_patterns: List[str] = field(default_factory=list)


@dataclass
class BehavioralPattern:
    """User behavioral pattern analysis."""
    user_id: UUID
    typical_access_times: List[int]  # Hours of day (0-23)
    typical_locations: List[str]     # Country codes
    typical_user_agents: List[str]   # User agent hashes
    typical_resources: List[str]     # Resource types accessed
    request_frequency_pattern: Dict[str, float]
    anomaly_threshold: float = 0.7
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SecurityContextData:
    """Comprehensive security context for request validation."""
    ip_address: str
    user_agent: str
    request_timestamp: datetime
    geolocation: Optional[GeolocationData] = None
    user_agent_analysis: Optional[UserAgentAnalysis] = None
    behavioral_pattern: Optional[BehavioralPattern] = None
    session_data: Dict[str, Any] = field(default_factory=dict)
    request_headers: Dict[str, str] = field(default_factory=dict)
    previous_requests: List[Dict[str, Any]] = field(default_factory=list)
    risk_score: float = 0.0
    security_flags: List[str] = field(default_factory=list)


# ============================================================================
# GENERATION INHERITANCE MODELS
# ============================================================================

@dataclass
class GenerationInheritanceNode:
    """Single node in generation inheritance tree."""
    generation_id: UUID
    parent_id: Optional[UUID]
    children_ids: List[UUID]
    owner_id: UUID
    permissions: List[str]
    access_restrictions: Dict[str, Any]
    created_at: datetime
    depth_level: int


@dataclass
class InheritancePermission:
    """Permission that can be inherited through generation chain."""
    permission_name: str
    permission_type: str  # read, write, delete, share, admin
    granted_by: UUID  # User who granted the permission
    granted_at: datetime
    expires_at: Optional[datetime] = None
    conditions: Dict[str, Any] = field(default_factory=dict)
    inheritable: bool = True
    max_inheritance_depth: int = 10


@dataclass
class GenerationInheritanceChain:
    """Complete generation inheritance chain validation data."""
    target_generation_id: UUID
    inheritance_path: List[GenerationInheritanceNode]
    effective_permissions: List[InheritancePermission]
    access_restrictions: Dict[str, Any]
    inheritance_depth: int
    max_depth_exceeded: bool
    circular_reference_detected: bool
    validation_timestamp: datetime = field(default_factory=datetime.utcnow)


# ============================================================================
# MEDIA ACCESS AUTHORIZATION MODELS
# ============================================================================

@dataclass
class MediaResourceMetadata:
    """Metadata for media resource access control."""
    resource_id: UUID
    resource_type: str  # image, video, audio, document
    storage_location: str
    file_size_bytes: int
    mime_type: str
    owner_id: UUID
    visibility_level: str
    encryption_status: bool
    access_control_list: List[UUID] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed_at: Optional[datetime] = None


@dataclass
class MediaAccessToken:
    """Signed token for secure media access."""
    token_id: str
    resource_id: UUID
    user_id: UUID
    access_type: str  # read, write, delete
    issued_at: datetime
    expires_at: datetime
    signature: str
    permissions: List[str]
    access_conditions: Dict[str, Any] = field(default_factory=dict)
    usage_tracking: bool = True
    ip_restrictions: List[str] = field(default_factory=list)
    
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.utcnow() > self.expires_at
    
    def time_until_expiry(self) -> timedelta:
        """Get time until token expires."""
        return self.expires_at - datetime.utcnow()


@dataclass
class SignedURLRequest:
    """Request for signed URL generation."""
    resource_id: UUID
    user_id: UUID
    access_type: str
    expires_in_seconds: int = 3600
    ip_restrictions: List[str] = field(default_factory=list)
    usage_limit: Optional[int] = None
    callback_url: Optional[str] = None


# ============================================================================
# PERFORMANCE OPTIMIZATION MODELS
# ============================================================================

class CacheLevel(str, Enum):
    """Multi-level cache hierarchy."""
    L1_MEMORY = "l1_memory"      # In-process memory cache
    L2_REDIS = "l2_redis"        # Redis cache
    L3_DATABASE = "l3_database"  # Database materialized views


@dataclass
class CacheMetrics:
    """Performance metrics for cache operations."""
    cache_level: CacheLevel
    hit_count: int = 0
    miss_count: int = 0
    hit_ratio: float = 0.0
    average_response_time_ms: float = 0.0
    cache_size_bytes: int = 0
    eviction_count: int = 0
    last_updated: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""
    operation_type: str
    total_execution_time_ms: float
    layer_execution_times: Dict[str, float]
    cache_performance: Dict[CacheLevel, CacheMetrics]
    database_query_count: int = 0
    database_query_time_ms: float = 0.0
    external_api_calls: int = 0
    external_api_time_ms: float = 0.0
    memory_usage_bytes: int = 0
    cpu_usage_percent: float = 0.0


@dataclass
class PerformanceOptimizationConfig:
    """Configuration for performance optimization layer."""
    l1_cache_size_limit: int = 1000  # Number of entries
    l1_cache_ttl_seconds: int = 60
    l2_cache_ttl_seconds: int = 300
    l3_cache_enabled: bool = True
    query_optimization_enabled: bool = True
    connection_pooling_enabled: bool = True
    max_concurrent_operations: int = 100
    performance_target_ms: float = 100.0
    cache_warming_enabled: bool = True


# ============================================================================
# AUDIT AND LOGGING MODELS
# ============================================================================

class AuditEventType(str, Enum):
    """Types of events that can be audited."""
    AUTHORIZATION_DECISION = "authorization_decision"
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    SECURITY_VIOLATION = "security_violation"
    ANOMALY_DETECTED = "anomaly_detected"
    EMERGENCY_MODE_ACTIVATED = "emergency_mode_activated"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SYSTEM_ERROR = "system_error"
    CONFIGURATION_CHANGE = "configuration_change"
    USER_ACTION = "user_action"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditLogEntry:
    """Individual audit log entry."""
    audit_id: str
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: datetime
    user_id: Optional[UUID]
    resource_id: Optional[UUID]
    ip_address: Optional[str]
    user_agent: Optional[str]
    action_performed: str
    outcome: str  # success, failure, partial
    threat_level: SecurityThreatLevel
    layer_results: List[Dict[str, Any]]
    performance_metrics: Dict[str, float]
    security_context: Dict[str, Any]
    error_details: Optional[str] = None
    remediation_actions: List[str] = field(default_factory=list)
    correlation_id: Optional[str] = None


@dataclass
class SIEMIntegrationConfig:
    """Configuration for SIEM integration."""
    enabled: bool = True
    siem_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    batch_size: int = 100
    flush_interval_seconds: int = 60
    retention_days: int = 90
    alert_thresholds: Dict[str, int] = field(default_factory=dict)
    correlation_rules: List[Dict[str, Any]] = field(default_factory=list)


# ============================================================================
# EMERGENCY RECOVERY MODELS
# ============================================================================

class EmergencyMode(str, Enum):
    """Emergency operation modes."""
    NORMAL = "normal"
    DEGRADED = "degraded"
    EMERGENCY = "emergency"
    LOCKDOWN = "lockdown"


class RecoveryStrategy(str, Enum):
    """Recovery strategies for system failures."""
    FAIL_SECURE = "fail_secure"
    FAIL_OPEN = "fail_open"
    GRACEFUL_DEGRADATION = "graceful_degradation"
    EMERGENCY_BYPASS = "emergency_bypass"


@dataclass
class CircuitBreakerState:
    """State of circuit breaker for service protection."""
    service_name: str
    state: str  # closed, open, half_open
    failure_count: int = 0
    failure_threshold: int = 5
    recovery_timeout_seconds: int = 30
    last_failure_time: Optional[datetime] = None
    success_count: int = 0
    half_open_success_threshold: int = 3


@dataclass
class EmergencyConfiguration:
    """Configuration for emergency recovery systems."""
    emergency_mode: EmergencyMode = EmergencyMode.NORMAL
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.FAIL_SECURE
    circuit_breakers: Dict[str, CircuitBreakerState] = field(default_factory=dict)
    emergency_contacts: List[str] = field(default_factory=list)
    automated_recovery_enabled: bool = True
    manual_override_required: bool = False
    emergency_access_users: List[UUID] = field(default_factory=list)
    lockdown_duration_minutes: int = 30


@dataclass
class SystemHealthMetrics:
    """System health metrics for emergency decision making."""
    database_health: float  # 0.0 to 1.0
    cache_health: float
    external_services_health: float
    cpu_usage_percent: float
    memory_usage_percent: float
    disk_usage_percent: float
    network_latency_ms: float
    error_rate_percent: float
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def overall_health_score(self) -> float:
        """Calculate overall health score."""
        weights = {
            'database': 0.3,
            'cache': 0.2,
            'external': 0.2,
            'cpu': 0.1,
            'memory': 0.1,
            'disk': 0.05,
            'network': 0.05
        }
        
        score = (
            self.database_health * weights['database'] +
            self.cache_health * weights['cache'] +
            self.external_services_health * weights['external'] +
            (1 - self.cpu_usage_percent / 100) * weights['cpu'] +
            (1 - self.memory_usage_percent / 100) * weights['memory'] +
            (1 - self.disk_usage_percent / 100) * weights['disk'] +
            (1 - min(self.network_latency_ms / 1000, 1.0)) * weights['network']
        )
        
        # Factor in error rate
        error_penalty = min(self.error_rate_percent / 100, 0.5)
        return max(score - error_penalty, 0.0)


# ============================================================================
# RATE LIMITING AND ANOMALY DETECTION MODELS
# ============================================================================

@dataclass
class RateLimitRule:
    """Individual rate limiting rule."""
    rule_id: str
    dimension: str  # user, ip, resource, endpoint
    limit: int
    window_seconds: int
    burst_allowance: int = 0
    adaptive: bool = False
    priority: int = 1
    enabled: bool = True
    exemptions: List[str] = field(default_factory=list)


@dataclass
class RateLimitState:
    """Current state for rate limiting tracking."""
    rule_id: str
    identifier: str  # The key being rate limited
    current_count: int
    window_start_time: datetime
    burst_used: int = 0
    violations: int = 0
    last_violation_time: Optional[datetime] = None
    adaptive_multiplier: float = 1.0


@dataclass
class AnomalyDetectionRule:
    """Rule for anomaly detection."""
    rule_id: str
    rule_name: str
    anomaly_type: AnomalyType
    detection_algorithm: str  # statistical, ml, rule_based
    threshold: float
    sensitivity: str  # low, medium, high
    enabled: bool = True
    false_positive_rate: float = 0.05
    confidence_threshold: float = 0.8
    conditions: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnomalyDetectionResult:
    """Result of anomaly detection analysis."""
    rule_id: str
    anomaly_detected: bool
    anomaly_type: AnomalyType
    confidence_score: float
    severity: SecurityThreatLevel
    detection_time: datetime
    affected_entity: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    recommended_actions: List[str] = field(default_factory=list)
    false_positive_likelihood: float = 0.0


# ============================================================================
# COMPREHENSIVE AUTHORIZATION RESULT
# ============================================================================

@dataclass
class ComprehensiveAuthorizationResult:
    """Final result of comprehensive 10-layer authorization."""
    authorized: bool
    request_id: str
    user_id: UUID
    resource_id: Optional[UUID]
    access_type: str
    decision_time: datetime
    execution_chain: LayerExecutionChain
    threat_assessment: ThreatAssessment
    performance_metrics: PerformanceMetrics
    audit_log_entry: AuditLogEntry
    media_access_token: Optional[MediaAccessToken] = None
    emergency_mode_used: bool = False
    degraded_mode_used: bool = False
    rate_limit_applied: bool = False
    anomalies_detected: List[AnomalyDetectionResult] = field(default_factory=list)
    
    def to_json(self) -> str:
        """Convert to JSON representation."""
        return json.dumps(self, default=str, indent=2)
    
    def get_security_summary(self) -> Dict[str, Any]:
        """Get security-focused summary."""
        return {
            'authorized': self.authorized,
            'threat_level': self.threat_assessment.overall_threat_level,
            'threat_score': self.threat_assessment.threat_score,
            'anomalies_count': len(self.anomalies_detected),
            'emergency_mode': self.emergency_mode_used,
            'performance_target_met': self.performance_metrics.total_execution_time_ms < 100
        }


# ============================================================================
# CONFIGURATION AND MANAGEMENT MODELS
# ============================================================================

@dataclass
class AuthorizationSystemConfiguration:
    """Overall configuration for the authorization system."""
    layers: List[LayerConfiguration]
    performance_config: PerformanceOptimizationConfig
    audit_config: SIEMIntegrationConfig
    emergency_config: EmergencyConfiguration
    rate_limit_rules: List[RateLimitRule]
    anomaly_detection_rules: List[AnomalyDetectionRule]
    system_health_thresholds: Dict[str, float] = field(default_factory=dict)
    feature_flags: Dict[str, bool] = field(default_factory=dict)
    
    @classmethod
    def get_default_configuration(cls) -> 'AuthorizationSystemConfiguration':
        """Get default system configuration."""
        layers = [
            LayerConfiguration(
                layer_type=AuthorizationLayerType.ADVANCED_RATE_LIMITING_ANOMALY_DETECTION,
                critical=True,
                max_execution_time_ms=5.0
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.PERFORMANCE_OPTIMIZATION_LAYER,
                max_execution_time_ms=2.0
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.SECURITY_CONTEXT_VALIDATION,
                max_execution_time_ms=10.0
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.BASIC_UUID_VALIDATION,
                critical=True,
                max_execution_time_ms=5.0
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.RBAC_PERMISSION_CHECK,
                critical=True,
                max_execution_time_ms=10.0
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.RESOURCE_OWNERSHIP_VALIDATION,
                max_execution_time_ms=15.0
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.GENERATION_INHERITANCE_VALIDATION,
                max_execution_time_ms=20.0
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.MEDIA_ACCESS_AUTHORIZATION,
                max_execution_time_ms=15.0
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.AUDIT_SECURITY_LOGGING_LAYER,
                max_execution_time_ms=5.0,
                failure_mode="fail_open"  # Don't block on logging failures
            ),
            LayerConfiguration(
                layer_type=AuthorizationLayerType.EMERGENCY_RECOVERY_SYSTEMS,
                max_execution_time_ms=10.0,
                failure_mode="fail_secure"
            )
        ]
        
        return cls(
            layers=layers,
            performance_config=PerformanceOptimizationConfig(),
            audit_config=SIEMIntegrationConfig(),
            emergency_config=EmergencyConfiguration(),
            rate_limit_rules=[],
            anomaly_detection_rules=[],
            system_health_thresholds={
                'database_health': 0.9,
                'cache_health': 0.8,
                'external_services_health': 0.7,
                'overall_health': 0.8
            },
            feature_flags={
                'enable_geolocation': True,
                'enable_behavioral_analysis': True,
                'enable_ml_anomaly_detection': False,  # Disabled by default
                'enable_adaptive_rate_limiting': True,
                'enable_emergency_bypass': True
            }
        )


# ============================================================================
# VALIDATION HELPERS
# ============================================================================

def validate_security_threat_level(threat_level: SecurityThreatLevel) -> bool:
    """Validate security threat level enum value."""
    return threat_level in SecurityThreatLevel


def validate_layer_configuration(config: LayerConfiguration) -> List[str]:
    """Validate layer configuration and return list of validation errors."""
    errors = []
    
    if config.max_execution_time_ms <= 0:
        errors.append("max_execution_time_ms must be positive")
    
    if config.max_execution_time_ms > 100:
        errors.append("max_execution_time_ms should not exceed 100ms for performance")
    
    if config.cache_ttl_seconds < 0:
        errors.append("cache_ttl_seconds cannot be negative")
    
    if config.failure_mode not in ["fail_secure", "fail_open"]:
        errors.append("failure_mode must be 'fail_secure' or 'fail_open'")
    
    return errors


def validate_rate_limit_rule(rule: RateLimitRule) -> List[str]:
    """Validate rate limit rule and return list of validation errors."""
    errors = []
    
    if rule.limit <= 0:
        errors.append("limit must be positive")
    
    if rule.window_seconds <= 0:
        errors.append("window_seconds must be positive")
    
    if rule.burst_allowance < 0:
        errors.append("burst_allowance cannot be negative")
    
    if rule.priority < 1 or rule.priority > 10:
        errors.append("priority must be between 1 and 10")
    
    return errors