"""
Comprehensive Authorization Logging System
Provides structured logging, security audit trails, and performance monitoring for UUID authorization.
"""
import logging
import json
import asyncio
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass, asdict
import uuid
import hashlib
from pathlib import Path

from .exceptions import AuthorizationError, UUIDAuthorizationError, ErrorSeverity, ErrorCategory
from .uuid_utils import UUIDUtils


class LogLevel(Enum):
    """Custom log levels for authorization events."""
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    SECURITY = "SECURITY"
    AUDIT = "AUDIT"


class AuthEventType(Enum):
    """Types of authorization events to log."""
    ACCESS_GRANTED = "access_granted"
    ACCESS_DENIED = "access_denied"
    PERMISSION_CHECK = "permission_check"
    TOKEN_VALIDATION = "token_validation"
    OWNERSHIP_VERIFICATION = "ownership_verification"
    SECURITY_VIOLATION = "security_violation"
    RATE_LIMIT_HIT = "rate_limit_hit"
    SESSION_EVENT = "session_event"
    ADMIN_ACTION = "admin_action"
    SYSTEM_EVENT = "system_event"


@dataclass
class AuthLogContext:
    """Context information for authorization logging."""
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    action: Optional[str] = None
    permission_required: Optional[str] = None
    role: Optional[str] = None
    organization_id: Optional[str] = None
    team_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        if self.correlation_id is None:
            self.correlation_id = str(uuid.uuid4())


@dataclass
class AuthLogMetrics:
    """Performance and security metrics for authorization events."""
    processing_time_ms: Optional[float] = None
    database_queries: Optional[int] = None
    cache_hits: Optional[int] = None
    cache_misses: Optional[int] = None
    external_api_calls: Optional[int] = None
    retry_attempts: Optional[int] = None
    circuit_breaker_state: Optional[str] = None
    memory_usage_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None


class AuthorizationLogger:
    """
    Comprehensive logging system for authorization events with security audit trails.
    """
    
    def __init__(self, logger_name: str = "velro.auth"):
        self.logger = logging.getLogger(logger_name)
        self.security_logger = logging.getLogger(f"{logger_name}.security")
        self.audit_logger = logging.getLogger(f"{logger_name}.audit")
        self.performance_logger = logging.getLogger(f"{logger_name}.performance")
        
        # Configure loggers if not already configured
        self._configure_loggers()
        
        # Security monitoring state
        self.security_patterns = {
            'failed_attempts': {},
            'suspicious_ips': set(),
            'blocked_users': set(),
            'rate_limit_violations': {}
        }
        
        # Performance tracking
        self.performance_metrics = {
            'slow_queries': [],
            'cache_performance': {'hits': 0, 'misses': 0},
            'error_rates': {}
        }
    
    def _configure_loggers(self):
        """Configure loggers with appropriate handlers and formatters."""
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(correlation_id)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S UTC'
        )
        
        json_formatter = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S UTC'
        )
        
        # Configure main logger
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(detailed_formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # Configure security logger (for security events)
        if not self.security_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(json_formatter)
            self.security_logger.addHandler(handler)
            self.security_logger.setLevel(logging.WARNING)
        
        # Configure audit logger (for compliance)
        if not self.audit_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(json_formatter)
            self.audit_logger.addHandler(handler)
            self.audit_logger.setLevel(logging.INFO)
        
        # Configure performance logger
        if not self.performance_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(json_formatter)
            self.performance_logger.addHandler(handler)
            self.performance_logger.setLevel(logging.INFO)
    
    async def log_auth_event(
        self,
        event_type: AuthEventType,
        context: AuthLogContext,
        result: str,
        details: Optional[Dict[str, Any]] = None,
        metrics: Optional[AuthLogMetrics] = None,
        severity: LogLevel = LogLevel.INFO
    ):
        """
        Log an authorization event with full context and metrics.
        
        Args:
            event_type: Type of authorization event
            context: Context information about the event
            result: Result of the authorization check (granted/denied/error)
            details: Additional details about the event
            metrics: Performance metrics for the event
            severity: Severity level of the event
        """
        
        # Build comprehensive log entry
        log_entry = {
            'event_type': event_type.value,
            'result': result,
            'timestamp': context.timestamp.isoformat() if context.timestamp else datetime.now(timezone.utc).isoformat(),
            'context': asdict(context),
            'details': details or {},
            'metrics': asdict(metrics) if metrics else {},
            'severity': severity.value
        }
        
        # Add computed fields
        log_entry['user_hash'] = self._hash_sensitive_data(context.user_id) if context.user_id else None
        log_entry['ip_hash'] = self._hash_sensitive_data(context.client_ip) if context.client_ip else None
        log_entry['resource_hash'] = self._hash_sensitive_data(context.resource_id) if context.resource_id else None
        
        # Sanitize sensitive information for logging
        sanitized_entry = self._sanitize_log_entry(log_entry)
        
        # Log to appropriate logger based on event type and severity
        await self._route_log_message(event_type, sanitized_entry, severity)
        
        # Update security monitoring
        await self._update_security_monitoring(event_type, context, result, details)
        
        # Update performance metrics
        if metrics:
            await self._update_performance_metrics(metrics, context)
    
    async def log_access_granted(
        self,
        context: AuthLogContext,
        permission: str,
        details: Optional[Dict[str, Any]] = None,
        metrics: Optional[AuthLogMetrics] = None
    ):
        """Log successful access grant."""
        
        log_details = {
            'permission_granted': permission,
            'auth_method': details.get('auth_method', 'unknown') if details else 'unknown',
            'token_type': details.get('token_type', 'unknown') if details else 'unknown'
        }
        
        if details:
            log_details.update(details)
        
        await self.log_auth_event(
            AuthEventType.ACCESS_GRANTED,
            context,
            'granted',
            log_details,
            metrics,
            LogLevel.INFO
        )
    
    async def log_access_denied(
        self,
        context: AuthLogContext,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
        metrics: Optional[AuthLogMetrics] = None,
        is_security_violation: bool = False
    ):
        """Log access denial with reason."""
        
        log_details = {
            'denial_reason': reason,
            'is_security_violation': is_security_violation
        }
        
        if details:
            log_details.update(details)
        
        severity = LogLevel.SECURITY if is_security_violation else LogLevel.WARNING
        
        await self.log_auth_event(
            AuthEventType.ACCESS_DENIED,
            context,
            'denied',
            log_details,
            metrics,
            severity
        )
    
    async def log_ownership_check(
        self,
        context: AuthLogContext,
        owner_id: str,
        requested_by: str,
        result: bool,
        details: Optional[Dict[str, Any]] = None,
        metrics: Optional[AuthLogMetrics] = None
    ):
        """Log ownership verification check."""
        
        log_details = {
            'owner_id': owner_id,
            'requested_by': requested_by,
            'ownership_verified': result,
            'resource_access_pattern': self._analyze_access_pattern(context.resource_id, requested_by)
        }
        
        if details:
            log_details.update(details)
        
        result_str = 'verified' if result else 'failed'
        severity = LogLevel.INFO if result else LogLevel.WARNING
        
        await self.log_auth_event(
            AuthEventType.OWNERSHIP_VERIFICATION,
            context,
            result_str,
            log_details,
            metrics,
            severity
        )
    
    async def log_token_validation(
        self,
        context: AuthLogContext,
        token_type: str,
        validation_result: str,
        details: Optional[Dict[str, Any]] = None,
        metrics: Optional[AuthLogMetrics] = None
    ):
        """Log token validation events."""
        
        log_details = {
            'token_type': token_type,
            'validation_result': validation_result,
            'token_age': details.get('token_age') if details else None,
            'issuer': details.get('issuer') if details else None
        }
        
        if details:
            log_details.update({k: v for k, v in details.items() if k not in ['token', 'raw_token']})
        
        severity = LogLevel.INFO if validation_result == 'valid' else LogLevel.WARNING
        
        await self.log_auth_event(
            AuthEventType.TOKEN_VALIDATION,
            context,
            validation_result,
            log_details,
            metrics,
            severity
        )
    
    async def log_security_violation(
        self,
        context: AuthLogContext,
        violation_type: str,
        details: Optional[Dict[str, Any]] = None,
        threat_level: str = "medium"
    ):
        """Log security violations for monitoring and alerting."""
        
        log_details = {
            'violation_type': violation_type,
            'threat_level': threat_level,
            'automated_response': details.get('automated_response') if details else None,
            'investigation_required': details.get('investigation_required', True) if details else True
        }
        
        if details:
            log_details.update(details)
        
        await self.log_auth_event(
            AuthEventType.SECURITY_VIOLATION,
            context,
            'violation_detected',
            log_details,
            None,
            LogLevel.SECURITY
        )
        
        # Additional security alert logging
        await self._log_security_alert(context, violation_type, threat_level, log_details)
    
    async def log_performance_issue(
        self,
        context: AuthLogContext,
        issue_type: str,
        metrics: AuthLogMetrics,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log performance issues in authorization system."""
        
        log_details = {
            'issue_type': issue_type,
            'performance_impact': details.get('impact', 'unknown') if details else 'unknown',
            'optimization_suggestions': details.get('suggestions', []) if details else []
        }
        
        if details:
            log_details.update(details)
        
        await self.log_auth_event(
            AuthEventType.SYSTEM_EVENT,
            context,
            'performance_issue',
            log_details,
            metrics,
            LogLevel.WARNING
        )
    
    async def log_uuid_authorization_error(
        self,
        error: UUIDAuthorizationError,
        context: AuthLogContext,
        metrics: Optional[AuthLogMetrics] = None
    ):
        """Log UUID-specific authorization errors with detailed context."""
        
        log_details = {
            'uuid_value': error.uuid_value,
            'uuid_type': error.uuid_type,
            'ownership_check_failed': error.ownership_check_failed,
            'error_code': error.error_code,
            'uuid_validation': {
                'is_valid_format': UUIDUtils.is_valid_uuid_string(error.uuid_value) if error.uuid_value else False,
                'is_development_id': UUIDUtils.is_development_user_id(error.uuid_value) if error.uuid_value else False,
                'uuid_pattern_analysis': self._analyze_uuid_pattern(error.uuid_value) if error.uuid_value else {}
            }
        }
        
        # Determine if this is a potential security issue
        is_security_violation = self._is_uuid_security_violation(error, context)
        
        await self.log_access_denied(
            context,
            f"UUID authorization failed: {error.message}",
            log_details,
            metrics,
            is_security_violation
        )
    
    def _hash_sensitive_data(self, data: str) -> str:
        """Hash sensitive data for logging while preserving analytics capability."""
        if not data:
            return None
        return hashlib.sha256(data.encode()).hexdigest()[:16]  # First 16 chars for space efficiency
    
    def _sanitize_log_entry(self, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Remove or hash sensitive information from log entries."""
        
        sanitized = log_entry.copy()
        
        # Keys to remove completely
        sensitive_keys = ['password', 'token', 'secret', 'key', 'credential']
        
        # Keys to hash
        hash_keys = ['user_id', 'session_id', 'client_ip']
        
        def sanitize_recursive(obj, path=""):
            if isinstance(obj, dict):
                for key, value in list(obj.items()):
                    current_path = f"{path}.{key}" if path else key
                    
                    # Remove sensitive keys
                    if any(sensitive in key.lower() for sensitive in sensitive_keys):
                        obj[key] = "[REDACTED]"
                    # Hash specific keys
                    elif key in hash_keys and isinstance(value, str):
                        obj[f"{key}_hash"] = self._hash_sensitive_data(value)
                        obj[key] = "[HASHED]"
                    # Recursively sanitize nested objects
                    elif isinstance(value, (dict, list)):
                        sanitize_recursive(value, current_path)
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        sanitize_recursive(item, path)
        
        sanitize_recursive(sanitized)
        return sanitized
    
    async def _route_log_message(
        self,
        event_type: AuthEventType,
        log_entry: Dict[str, Any],
        severity: LogLevel
    ):
        """Route log messages to appropriate loggers."""
        
        # Format message
        message = json.dumps(log_entry, default=str)
        
        # Add correlation ID to logger context
        extra = {
            'correlation_id': log_entry.get('context', {}).get('correlation_id', 'unknown')
        }
        
        # Route to primary logger
        if severity == LogLevel.CRITICAL:
            self.logger.critical(message, extra=extra)
        elif severity == LogLevel.ERROR:
            self.logger.error(message, extra=extra)
        elif severity == LogLevel.WARNING:
            self.logger.warning(message, extra=extra)
        elif severity == LogLevel.INFO:
            self.logger.info(message, extra=extra)
        elif severity == LogLevel.DEBUG:
            self.logger.debug(message, extra=extra)
        
        # Route security events
        if severity == LogLevel.SECURITY or event_type == AuthEventType.SECURITY_VIOLATION:
            self.security_logger.critical(message, extra=extra)
        
        # Route audit events
        if event_type in [AuthEventType.ACCESS_GRANTED, AuthEventType.ACCESS_DENIED, AuthEventType.ADMIN_ACTION]:
            self.audit_logger.info(message, extra=extra)
        
        # Route performance events
        if log_entry.get('metrics') and any(log_entry['metrics'].values()):
            self.performance_logger.info(message, extra=extra)
    
    async def _update_security_monitoring(
        self,
        event_type: AuthEventType,
        context: AuthLogContext,
        result: str,
        details: Optional[Dict[str, Any]]
    ):
        """Update security monitoring patterns and triggers."""
        
        # Track failed attempts per user/IP
        if event_type == AuthEventType.ACCESS_DENIED:
            key = f"{context.user_id or 'unknown'}_{context.client_ip or 'unknown'}"
            if key not in self.security_patterns['failed_attempts']:
                self.security_patterns['failed_attempts'][key] = {
                    'count': 0,
                    'first_attempt': context.timestamp,
                    'last_attempt': context.timestamp
                }
            
            self.security_patterns['failed_attempts'][key]['count'] += 1
            self.security_patterns['failed_attempts'][key]['last_attempt'] = context.timestamp
            
            # Check for suspicious patterns
            attempts = self.security_patterns['failed_attempts'][key]
            if attempts['count'] >= 5:  # 5 failed attempts
                time_window = context.timestamp - attempts['first_attempt']
                if time_window.total_seconds() <= 300:  # Within 5 minutes
                    await self._trigger_security_alert("repeated_failed_attempts", context, attempts)
        
        # Track suspicious IPs
        if context.client_ip and details and details.get('is_security_violation'):
            self.security_patterns['suspicious_ips'].add(context.client_ip)
        
        # Track rate limiting violations
        if event_type == AuthEventType.RATE_LIMIT_HIT:
            if context.user_id not in self.security_patterns['rate_limit_violations']:
                self.security_patterns['rate_limit_violations'][context.user_id] = 0
            self.security_patterns['rate_limit_violations'][context.user_id] += 1
    
    async def _update_performance_metrics(
        self,
        metrics: AuthLogMetrics,
        context: AuthLogContext
    ):
        """Update performance metrics and trigger alerts for issues."""
        
        # Track cache performance
        if metrics.cache_hits is not None:
            self.performance_metrics['cache_performance']['hits'] += metrics.cache_hits
        if metrics.cache_misses is not None:
            self.performance_metrics['cache_performance']['misses'] += metrics.cache_misses
        
        # Track slow operations
        if metrics.processing_time_ms and metrics.processing_time_ms > 1000:  # > 1 second
            self.performance_metrics['slow_queries'].append({
                'timestamp': context.timestamp,
                'processing_time': metrics.processing_time_ms,
                'resource_type': context.resource_type,
                'action': context.action
            })
            
            # Keep only last 100 slow queries
            if len(self.performance_metrics['slow_queries']) > 100:
                self.performance_metrics['slow_queries'] = self.performance_metrics['slow_queries'][-100:]
    
    def _analyze_access_pattern(self, resource_id: Optional[str], user_id: str) -> Dict[str, Any]:
        """Analyze access patterns for security insights."""
        
        # This would implement pattern analysis in a production system
        # For now, return basic pattern info
        return {
            'access_frequency': 'normal',  # Would calculate from historical data
            'access_time_pattern': 'business_hours',  # Would analyze timing
            'geographic_pattern': 'consistent',  # Would analyze IP geolocation
            'device_pattern': 'consistent'  # Would analyze user agent patterns
        }
    
    def _analyze_uuid_pattern(self, uuid_value: str) -> Dict[str, Any]:
        """Analyze UUID patterns for security insights."""
        
        if not uuid_value or not UUIDUtils.is_valid_uuid_string(uuid_value):
            return {'pattern_type': 'invalid'}
        
        uuid_clean = uuid_value.replace('-', '').lower()
        
        # Check for suspicious patterns
        patterns = {
            'all_zeros': uuid_clean == '0' * 32,
            'all_ones': uuid_clean == 'f' * 32,
            'sequential': self._is_sequential_pattern(uuid_clean),
            'repeating': self._has_repeating_pattern(uuid_clean),
            'development_id': UUIDUtils.is_development_user_id(uuid_value)
        }
        
        return {
            'pattern_type': 'suspicious' if any(patterns.values()) else 'normal',
            'patterns_detected': [k for k, v in patterns.items() if v],
            'entropy_score': self._calculate_uuid_entropy(uuid_clean)
        }
    
    def _is_sequential_pattern(self, uuid_hex: str) -> bool:
        """Check if UUID contains sequential patterns."""
        # Look for sequences of 4 or more consecutive characters
        for i in range(len(uuid_hex) - 3):
            chars = uuid_hex[i:i+4]
            if all(ord(chars[j+1]) == ord(chars[j]) + 1 for j in range(3)):
                return True
        return False
    
    def _has_repeating_pattern(self, uuid_hex: str) -> bool:
        """Check if UUID has repeating patterns."""
        # Check for 4 or more repeating characters
        for i in range(len(uuid_hex) - 3):
            if len(set(uuid_hex[i:i+4])) <= 1:
                return True
        return False
    
    def _calculate_uuid_entropy(self, uuid_hex: str) -> float:
        """Calculate entropy score for UUID (0-1, higher is more random)."""
        if not uuid_hex:
            return 0.0
        
        # Calculate character frequency
        char_counts = {}
        for char in uuid_hex:
            char_counts[char] = char_counts.get(char, 0) + 1
        
        # Calculate entropy
        import math
        entropy = 0
        for count in char_counts.values():
            probability = count / len(uuid_hex)
            entropy -= probability * math.log2(probability)
        
        # Normalize to 0-1 scale (max entropy for hex is log2(16) = 4)
        return min(entropy / 4.0, 1.0)
    
    def _is_uuid_security_violation(
        self,
        error: UUIDAuthorizationError,
        context: AuthLogContext
    ) -> bool:
        """Determine if UUID authorization error represents a security violation."""
        
        # Check UUID pattern analysis
        if error.uuid_value:
            pattern_analysis = self._analyze_uuid_pattern(error.uuid_value)
            if pattern_analysis.get('pattern_type') == 'suspicious':
                return True
        
        # Check for repeated attempts
        key = f"{context.user_id}_{context.client_ip}"
        if key in self.security_patterns['failed_attempts']:
            attempts = self.security_patterns['failed_attempts'][key]
            if attempts['count'] >= 3:  # 3 or more recent attempts
                return True
        
        # Check if IP is already flagged as suspicious
        if context.client_ip in self.security_patterns['suspicious_ips']:
            return True
        
        return False
    
    async def _log_security_alert(
        self,
        context: AuthLogContext,
        violation_type: str,
        threat_level: str,
        details: Dict[str, Any]
    ):
        """Log security alerts for immediate attention."""
        
        alert_entry = {
            'alert_type': 'security_violation',
            'violation_type': violation_type,
            'threat_level': threat_level,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'context': asdict(context),
            'details': details,
            'requires_immediate_attention': threat_level in ['high', 'critical'],
            'recommended_actions': self._get_recommended_actions(violation_type, threat_level)
        }
        
        self.security_logger.critical(
            f"🚨 SECURITY ALERT: {violation_type} - {threat_level} threat level",
            extra={'alert_data': json.dumps(alert_entry, default=str)}
        )
    
    async def _trigger_security_alert(
        self,
        alert_type: str,
        context: AuthLogContext,
        alert_data: Dict[str, Any]
    ):
        """Trigger security alerts for suspicious patterns."""
        
        await self._log_security_alert(
            context,
            alert_type,
            'high',
            {
                'alert_data': alert_data,
                'pattern_detected': True,
                'automated_response_triggered': False  # Would implement automated responses
            }
        )
    
    def _get_recommended_actions(self, violation_type: str, threat_level: str) -> List[str]:
        """Get recommended actions for security violations."""
        
        base_actions = ['investigate_logs', 'monitor_user_activity']
        
        if threat_level in ['high', 'critical']:
            base_actions.extend(['alert_security_team', 'consider_account_suspension'])
        
        if violation_type == 'repeated_failed_attempts':
            base_actions.extend(['implement_rate_limiting', 'require_additional_auth'])
        elif violation_type == 'suspicious_uuid_patterns':
            base_actions.extend(['validate_resource_access', 'check_enumeration_attempts'])
        elif violation_type == 'token_manipulation':
            base_actions.extend(['invalidate_all_tokens', 'force_password_reset'])
        
        return base_actions


# Global logger instance
auth_logger = AuthorizationLogger()


# Convenience functions for common logging scenarios

async def log_generation_access_attempt(
    user_id: str,
    generation_id: str,
    result: str,
    request_context: Optional[Dict[str, Any]] = None,
    metrics: Optional[AuthLogMetrics] = None
):
    """Log generation access attempts."""
    
    context = AuthLogContext(
        user_id=user_id,
        resource_id=generation_id,
        resource_type="generation",
        action="access"
    )
    
    if request_context:
        context.client_ip = request_context.get('client_ip')
        context.user_agent = request_context.get('user_agent')
        context.request_path = request_context.get('request_path')
        context.request_method = request_context.get('request_method')
        context.session_id = request_context.get('session_id')
        context.request_id = request_context.get('request_id')
    
    if result == 'granted':
        await auth_logger.log_access_granted(context, 'generation_access', metrics=metrics)
    else:
        await auth_logger.log_access_denied(
            context,
            f"Generation access denied: {result}",
            metrics=metrics
        )


async def log_token_validation_attempt(
    user_id: Optional[str],
    token_type: str,
    validation_result: str,
    details: Optional[Dict[str, Any]] = None,
    metrics: Optional[AuthLogMetrics] = None
):
    """Log token validation attempts."""
    
    context = AuthLogContext(
        user_id=user_id,
        action="token_validation"
    )
    
    await auth_logger.log_token_validation(
        context,
        token_type,
        validation_result,
        details,
        metrics
    )


async def log_ownership_verification(
    user_id: str,
    resource_id: str,
    resource_type: str,
    owner_id: str,
    verification_result: bool,
    details: Optional[Dict[str, Any]] = None,
    metrics: Optional[AuthLogMetrics] = None
):
    """Log ownership verification checks."""
    
    context = AuthLogContext(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        action="ownership_check"
    )
    
    await auth_logger.log_ownership_check(
        context,
        owner_id,
        user_id,
        verification_result,
        details,
        metrics
    )


async def log_security_incident(
    user_id: Optional[str],
    violation_type: str,
    details: Optional[Dict[str, Any]] = None,
    threat_level: str = "medium",
    request_context: Optional[Dict[str, Any]] = None
):
    """Log security incidents."""
    
    context = AuthLogContext(
        user_id=user_id,
        action="security_incident"
    )
    
    if request_context:
        context.client_ip = request_context.get('client_ip')
        context.user_agent = request_context.get('user_agent')
        context.request_path = request_context.get('request_path')
        context.request_method = request_context.get('request_method')
    
    await auth_logger.log_security_violation(
        context,
        violation_type,
        details,
        threat_level
    )