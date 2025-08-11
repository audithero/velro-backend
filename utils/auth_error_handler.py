"""
Comprehensive Authorization Error Handler for UUID-based resources.
Provides detailed error handling, logging, and recovery patterns for authorization failures.
"""
import logging
import json
import hashlib
import asyncio
from typing import Optional, Dict, Any, List, Union, Callable, Type
from datetime import datetime, timezone, timedelta
from enum import Enum
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from .exceptions import (
    AuthorizationError, UUIDAuthorizationError, GenerationAccessDeniedError,
    ProjectAccessDeniedError, TeamAccessDeniedError, SecurityError,
    CircuitBreakerError, ErrorSeverity, ErrorCategory
)
from .uuid_utils import UUIDUtils

logger = logging.getLogger(__name__)


class AuthErrorType(Enum):
    """Types of authorization errors for categorization."""
    OWNERSHIP_VIOLATION = "ownership_violation"
    INSUFFICIENT_PERMISSIONS = "insufficient_permissions"
    RESOURCE_NOT_FOUND = "resource_not_found"
    TOKEN_INVALID = "token_invalid"
    SESSION_EXPIRED = "session_expired"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXCEEDED = "quota_exceeded"
    SECURITY_VIOLATION = "security_violation"


class RecoveryStrategy(Enum):
    """Recovery strategies for authorization failures."""
    RETRY_WITH_REFRESH = "retry_with_refresh"
    REDIRECT_TO_LOGIN = "redirect_to_login"
    REQUEST_PERMISSIONS = "request_permissions"
    FALLBACK_TO_PUBLIC = "fallback_to_public"
    CIRCUIT_BREAKER = "circuit_breaker"
    NO_RECOVERY = "no_recovery"


@dataclass
class AuthErrorContext:
    """Context information for authorization errors."""
    user_id: Optional[str] = None
    resource_id: Optional[str] = None
    resource_type: Optional[str] = None
    action: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_path: Optional[str] = None
    request_method: Optional[str] = None
    correlation_id: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)


@dataclass
class AuthErrorMetrics:
    """Metrics for authorization error tracking."""
    error_count: int = 0
    first_occurrence: Optional[datetime] = None
    last_occurrence: Optional[datetime] = None
    user_agents: List[str] = None
    ip_addresses: List[str] = None
    recovery_attempts: int = 0
    successful_recoveries: int = 0
    
    def __post_init__(self):
        if self.user_agents is None:
            self.user_agents = []
        if self.ip_addresses is None:
            self.ip_addresses = []


class AuthorizationErrorHandler:
    """
    Comprehensive authorization error handler with logging, monitoring, and recovery.
    """
    
    def __init__(self):
        self.error_metrics: Dict[str, AuthErrorMetrics] = {}
        self.circuit_breaker_state: Dict[str, bool] = {}
        self.recovery_handlers: Dict[AuthErrorType, Callable] = {
            AuthErrorType.OWNERSHIP_VIOLATION: self._handle_ownership_violation,
            AuthErrorType.INSUFFICIENT_PERMISSIONS: self._handle_insufficient_permissions,
            AuthErrorType.RESOURCE_NOT_FOUND: self._handle_resource_not_found,
            AuthErrorType.TOKEN_INVALID: self._handle_token_invalid,
            AuthErrorType.SESSION_EXPIRED: self._handle_session_expired,
            AuthErrorType.RATE_LIMITED: self._handle_rate_limited,
            AuthErrorType.QUOTA_EXCEEDED: self._handle_quota_exceeded,
            AuthErrorType.SECURITY_VIOLATION: self._handle_security_violation,
        }
        
        # Security monitoring thresholds
        self.security_thresholds = {
            'max_failed_attempts_per_minute': 10,
            'max_failed_attempts_per_hour': 100,
            'suspicious_pattern_threshold': 5,
            'circuit_breaker_threshold': 50
        }
    
    async def handle_authorization_error(
        self,
        error: Union[AuthorizationError, HTTPException, Exception],
        context: AuthErrorContext,
        request: Optional[Request] = None
    ) -> JSONResponse:
        """
        Main entry point for handling authorization errors.
        
        Args:
            error: The authorization error that occurred
            context: Context information about the error
            request: Optional FastAPI request object
            
        Returns:
            JSONResponse with appropriate error information
        """
        try:
            # Determine error type and categorize
            error_type = self._categorize_error(error)
            
            # Log the error with full context
            await self._log_authorization_error(error, error_type, context, request)
            
            # Update error metrics
            await self._update_error_metrics(error_type, context)
            
            # Check for security violations
            security_violation = await self._check_security_violations(error_type, context)
            if security_violation:
                await self._handle_security_violation(error, context)
            
            # Attempt recovery if appropriate
            recovery_result = await self._attempt_recovery(error, error_type, context)
            
            # Generate appropriate response
            response = await self._generate_error_response(
                error, error_type, context, recovery_result
            )
            
            return response
            
        except Exception as handler_error:
            logger.error(
                f"❌ [AUTH-ERROR-HANDLER] Error in authorization error handler: {handler_error}",
                extra={'correlation_id': context.correlation_id}
            )
            # Fallback to basic error response
            return self._generate_fallback_response(error, context)
    
    def _categorize_error(self, error: Union[Exception, HTTPException]) -> AuthErrorType:
        """Categorize the type of authorization error."""
        
        if isinstance(error, GenerationAccessDeniedError):
            return AuthErrorType.OWNERSHIP_VIOLATION
        elif isinstance(error, (ProjectAccessDeniedError, TeamAccessDeniedError)):
            return AuthErrorType.OWNERSHIP_VIOLATION
        elif isinstance(error, UUIDAuthorizationError):
            if error.ownership_check_failed:
                return AuthErrorType.OWNERSHIP_VIOLATION
            else:
                return AuthErrorType.INSUFFICIENT_PERMISSIONS
        elif isinstance(error, SecurityError):
            return AuthErrorType.SECURITY_VIOLATION
        elif isinstance(error, HTTPException):
            if error.status_code == 401:
                return AuthErrorType.TOKEN_INVALID
            elif error.status_code == 403:
                error_detail = str(error.detail).lower()
                if 'generation' in error_detail and 'access denied' in error_detail:
                    return AuthErrorType.OWNERSHIP_VIOLATION
                elif 'insufficient' in error_detail:
                    return AuthErrorType.INSUFFICIENT_PERMISSIONS
                else:
                    return AuthErrorType.OWNERSHIP_VIOLATION
            elif error.status_code == 404:
                return AuthErrorType.RESOURCE_NOT_FOUND
            elif error.status_code == 429:
                return AuthErrorType.RATE_LIMITED
            else:
                return AuthErrorType.INSUFFICIENT_PERMISSIONS
        else:
            error_message = str(error).lower()
            if 'access denied' in error_message or 'permission' in error_message:
                return AuthErrorType.OWNERSHIP_VIOLATION
            elif 'not found' in error_message:
                return AuthErrorType.RESOURCE_NOT_FOUND
            elif 'token' in error_message or 'auth' in error_message:
                return AuthErrorType.TOKEN_INVALID
            else:
                return AuthErrorType.INSUFFICIENT_PERMISSIONS
    
    async def _log_authorization_error(
        self,
        error: Union[Exception, HTTPException],
        error_type: AuthErrorType,
        context: AuthErrorContext,
        request: Optional[Request] = None
    ):
        """Log authorization error with structured data."""
        
        # Prepare comprehensive log data
        log_data = {
            'event': 'authorization_error',
            'error_type': error_type.value,
            'error_class': error.__class__.__name__,
            'error_message': str(error),
            'context': asdict(context),
            'severity': self._get_error_severity(error_type),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Add error-specific details
        if isinstance(error, UUIDAuthorizationError):
            log_data.update({
                'uuid_value': error.uuid_value,
                'uuid_type': error.uuid_type,
                'ownership_check_failed': error.ownership_check_failed,
                'error_code': error.error_code
            })
        elif isinstance(error, HTTPException):
            log_data.update({
                'status_code': error.status_code,
                'detail': error.detail
            })
        
        # Add request details if available
        if request:
            log_data.update({
                'request_method': request.method,
                'request_path': str(request.url.path),
                'request_query': str(request.url.query) if request.url.query else None,
                'user_agent': request.headers.get('user-agent'),
                'client_ip': self._get_client_ip(request),
                'request_id': getattr(request.state, 'request_id', None)
            })
        
        # Log with appropriate level based on severity
        severity = self._get_error_severity(error_type)
        if severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
            logger.error(f"🚨 [AUTH-ERROR] {error_type.value}: {log_data}")
        else:
            logger.warning(f"⚠️ [AUTH-ERROR] {error_type.value}: {log_data}")
        
        # Additional security event logging for sensitive errors
        if error_type == AuthErrorType.SECURITY_VIOLATION:
            await self._log_security_event(error, context, log_data)
    
    async def _log_security_event(
        self,
        error: Exception,
        context: AuthErrorContext,
        log_data: Dict[str, Any]
    ):
        """Log security events for monitoring and alerting."""
        
        security_event = {
            'event_type': 'security_violation',
            'threat_level': 'high',
            'details': log_data,
            'response_actions': ['logged', 'monitored'],
            'requires_investigation': True
        }
        
        logger.critical(f"🔒 [SECURITY-EVENT] Authorization security violation: {security_event}")
        
        # In production, this would integrate with SIEM systems
        # await self._send_to_siem(security_event)
        # await self._trigger_alerts(security_event)
    
    async def _update_error_metrics(self, error_type: AuthErrorType, context: AuthErrorContext):
        """Update error metrics for monitoring and analysis."""
        
        metric_key = f"{error_type.value}_{context.user_id}_{context.client_ip}"
        
        if metric_key not in self.error_metrics:
            self.error_metrics[metric_key] = AuthErrorMetrics()
        
        metrics = self.error_metrics[metric_key]
        metrics.error_count += 1
        metrics.last_occurrence = context.timestamp
        
        if metrics.first_occurrence is None:
            metrics.first_occurrence = context.timestamp
        
        # Track unique user agents and IPs
        if context.user_agent and context.user_agent not in metrics.user_agents:
            metrics.user_agents.append(context.user_agent)
        if context.client_ip and context.client_ip not in metrics.ip_addresses:
            metrics.ip_addresses.append(context.client_ip)
        
        # Check for suspicious patterns
        await self._analyze_error_patterns(error_type, context, metrics)
    
    async def _analyze_error_patterns(
        self,
        error_type: AuthErrorType,
        context: AuthErrorContext,
        metrics: AuthErrorMetrics
    ):
        """Analyze error patterns for security and operational insights."""
        
        # Check for rapid successive failures
        if metrics.error_count >= self.security_thresholds['max_failed_attempts_per_minute']:
            time_window = timedelta(minutes=1)
            if (context.timestamp - metrics.first_occurrence) <= time_window:
                logger.warning(
                    f"🚨 [AUTH-PATTERN] Rapid authorization failures detected: "
                    f"{metrics.error_count} failures in {time_window}",
                    extra={
                        'user_id': context.user_id,
                        'client_ip': context.client_ip,
                        'error_type': error_type.value
                    }
                )
        
        # Check for distributed attacks
        if len(metrics.ip_addresses) >= self.security_thresholds['suspicious_pattern_threshold']:
            logger.warning(
                f"🚨 [AUTH-PATTERN] Distributed authorization failures: "
                f"{len(metrics.ip_addresses)} unique IPs",
                extra={
                    'user_id': context.user_id,
                    'error_type': error_type.value,
                    'ip_addresses': metrics.ip_addresses[:10]  # Log first 10 IPs
                }
            )
        
        # Check for circuit breaker activation
        if metrics.error_count >= self.security_thresholds['circuit_breaker_threshold']:
            service_key = f"{error_type.value}_{context.resource_type}"
            if not self.circuit_breaker_state.get(service_key, False):
                self.circuit_breaker_state[service_key] = True
                logger.critical(
                    f"🔥 [CIRCUIT-BREAKER] Activated for {service_key} due to {metrics.error_count} failures",
                    extra={'error_type': error_type.value, 'resource_type': context.resource_type}
                )
    
    async def _check_security_violations(
        self,
        error_type: AuthErrorType,
        context: AuthErrorContext
    ) -> bool:
        """Check if the error indicates a security violation."""
        
        # Direct security violations
        if error_type == AuthErrorType.SECURITY_VIOLATION:
            return True
        
        # Pattern-based security violation detection
        metric_key = f"{error_type.value}_{context.user_id}_{context.client_ip}"
        metrics = self.error_metrics.get(metric_key)
        
        if metrics:
            # Too many failures in short time
            if metrics.error_count >= self.security_thresholds['max_failed_attempts_per_minute']:
                time_window = timedelta(minutes=1)
                if (context.timestamp - metrics.first_occurrence) <= time_window:
                    return True
            
            # Too many failures from single source
            if metrics.error_count >= self.security_thresholds['max_failed_attempts_per_hour']:
                time_window = timedelta(hours=1)
                if (context.timestamp - metrics.first_occurrence) <= time_window:
                    return True
        
        # UUID-specific security checks
        if context.resource_id:
            # Check for UUID enumeration attempts
            if self._is_uuid_enumeration_attempt(context.resource_id):
                return True
        
        return False
    
    def _is_uuid_enumeration_attempt(self, resource_id: str) -> bool:
        """Detect potential UUID enumeration attempts."""
        
        # Check for sequential UUID patterns (potential enumeration)
        if UUIDUtils.is_valid_uuid_string(resource_id):
            uuid_hex = resource_id.replace('-', '')
            
            # Check for suspicious patterns
            suspicious_patterns = [
                '00000000000000000000000000000000',  # All zeros
                'ffffffffffffffffffffffffffffffff',  # All F's
                '12345678123456781234567812345678',  # Sequential patterns
                '00000000000000000000000000000001',  # Incremental
            ]
            
            for pattern in suspicious_patterns:
                if uuid_hex.lower().startswith(pattern[:20]):  # Check first 20 chars
                    return True
        
        return False
    
    async def _attempt_recovery(
        self,
        error: Exception,
        error_type: AuthErrorType,
        context: AuthErrorContext
    ) -> Optional[Dict[str, Any]]:
        """Attempt to recover from the authorization error."""
        
        # Get recovery handler for error type
        handler = self.recovery_handlers.get(error_type)
        if not handler:
            return None
        
        try:
            # Update recovery attempt metrics
            metric_key = f"{error_type.value}_{context.user_id}_{context.client_ip}"
            if metric_key in self.error_metrics:
                self.error_metrics[metric_key].recovery_attempts += 1
            
            # Attempt recovery
            recovery_result = await handler(error, context)
            
            # Update successful recovery metrics
            if recovery_result and recovery_result.get('success'):
                if metric_key in self.error_metrics:
                    self.error_metrics[metric_key].successful_recoveries += 1
            
            return recovery_result
            
        except Exception as recovery_error:
            logger.error(
                f"❌ [AUTH-RECOVERY] Recovery attempt failed for {error_type.value}: {recovery_error}",
                extra={'correlation_id': context.correlation_id}
            )
            return None
    
    # Recovery handlers for different error types
    
    async def _handle_ownership_violation(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> Dict[str, Any]:
        """Handle ownership violation errors."""
        
        return {
            'success': False,
            'strategy': RecoveryStrategy.NO_RECOVERY.value,
            'user_action': 'contact_owner',
            'message': 'This resource belongs to another user. Contact the owner for access.',
            'support_info': {
                'resource_type': context.resource_type,
                'resource_id': context.resource_id,
                'can_request_access': True
            }
        }
    
    async def _handle_insufficient_permissions(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> Dict[str, Any]:
        """Handle insufficient permission errors."""
        
        return {
            'success': False,
            'strategy': RecoveryStrategy.REQUEST_PERMISSIONS.value,
            'user_action': 'request_permissions',
            'message': 'You don\\'t have sufficient permissions. Request access from an administrator.',
            'support_info': {
                'required_permissions': getattr(error, 'required_permission', 'unknown'),
                'current_role': context.user_id,  # Would need to fetch actual role
                'can_request_upgrade': True
            }
        }
    
    async def _handle_resource_not_found(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> Dict[str, Any]:
        """Handle resource not found errors."""
        
        return {
            'success': False,
            'strategy': RecoveryStrategy.NO_RECOVERY.value,
            'user_action': 'check_resource_id',
            'message': 'The requested resource was not found. Please check the ID and try again.',
            'support_info': {
                'resource_type': context.resource_type,
                'resource_id': context.resource_id,
                'suggestions': ['Check for typos in the ID', 'Verify the resource exists', 'Contact support if issue persists']
            }
        }
    
    async def _handle_token_invalid(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> Dict[str, Any]:
        """Handle invalid token errors."""
        
        return {
            'success': False,
            'strategy': RecoveryStrategy.REDIRECT_TO_LOGIN.value,
            'user_action': 'login_again',
            'message': 'Your authentication token is invalid. Please log in again.',
            'support_info': {
                'login_url': '/auth/login',
                'auto_redirect': True,
                'preserve_redirect': True
            }
        }
    
    async def _handle_session_expired(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> Dict[str, Any]:
        """Handle session expired errors."""
        
        return {
            'success': False,
            'strategy': RecoveryStrategy.RETRY_WITH_REFRESH.value,
            'user_action': 'refresh_session',
            'message': 'Your session has expired. Attempting to refresh...',
            'support_info': {
                'auto_refresh': True,
                'refresh_endpoint': '/auth/refresh',
                'fallback_login': '/auth/login'
            }
        }
    
    async def _handle_rate_limited(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> Dict[str, Any]:
        """Handle rate limit errors."""
        
        return {
            'success': False,
            'strategy': RecoveryStrategy.NO_RECOVERY.value,
            'user_action': 'wait_and_retry',
            'message': 'Too many requests. Please wait before trying again.',
            'support_info': {
                'retry_after': 60,  # Would be extracted from error
                'rate_limit_info': 'Standard rate limits apply',
                'upgrade_available': True
            }
        }
    
    async def _handle_quota_exceeded(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> Dict[str, Any]:
        """Handle quota exceeded errors."""
        
        return {
            'success': False,
            'strategy': RecoveryStrategy.NO_RECOVERY.value,
            'user_action': 'upgrade_plan',
            'message': 'Usage quota exceeded. Please upgrade your plan or wait for quota reset.',
            'support_info': {
                'current_usage': getattr(error, 'current_usage', 'unknown'),
                'quota_limit': getattr(error, 'limit', 'unknown'),
                'reset_time': 'Next billing cycle',
                'upgrade_url': '/billing/upgrade'
            }
        }
    
    async def _handle_security_violation(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> Dict[str, Any]:
        """Handle security violation errors."""
        
        return {
            'success': False,
            'strategy': RecoveryStrategy.NO_RECOVERY.value,
            'user_action': 'contact_support',
            'message': 'A security violation was detected. This incident has been logged.',
            'support_info': {
                'incident_id': context.correlation_id,
                'support_contact': 'security@velro.ai',
                'investigation_required': True
            }
        }
    
    async def _generate_error_response(
        self,
        error: Exception,
        error_type: AuthErrorType,
        context: AuthErrorContext,
        recovery_result: Optional[Dict[str, Any]] = None
    ) -> JSONResponse:
        """Generate appropriate error response."""
        
        # Determine HTTP status code
        status_code = self._get_http_status_code(error, error_type)
        
        # Base response structure
        response_data = {
            'error': True,
            'error_type': error_type.value,
            'message': self._get_user_friendly_message(error, error_type),
            'correlation_id': context.correlation_id,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Add development information in non-production
        try:
            from config import settings
            if not settings.is_production():
                response_data['debug'] = {
                    'error_class': error.__class__.__name__,
                    'error_message': str(error),
                    'context': asdict(context)
                }
        except:
            pass
        
        # Add recovery information if available
        if recovery_result:
            response_data['recovery'] = recovery_result
        
        # Add specific error details for certain types
        if isinstance(error, UUIDAuthorizationError):
            response_data.update({
                'resource_type': error.resource_type,
                'error_code': error.error_code
            })
        elif isinstance(error, HTTPException):
            response_data['status_code'] = error.status_code
        
        # Add security headers
        headers = self._get_security_headers()
        
        return JSONResponse(
            status_code=status_code,
            content=response_data,
            headers=headers
        )
    
    def _generate_fallback_response(
        self,
        error: Exception,
        context: AuthErrorContext
    ) -> JSONResponse:
        """Generate fallback response when main handler fails."""
        
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                'error': True,
                'message': 'An authorization error occurred.',
                'correlation_id': context.correlation_id,
                'timestamp': datetime.now(timezone.utc).isoformat()
            },
            headers=self._get_security_headers()
        )
    
    def _get_error_severity(self, error_type: AuthErrorType) -> ErrorSeverity:
        """Get severity level for error type."""
        
        severity_map = {
            AuthErrorType.SECURITY_VIOLATION: ErrorSeverity.CRITICAL,
            AuthErrorType.OWNERSHIP_VIOLATION: ErrorSeverity.HIGH,
            AuthErrorType.TOKEN_INVALID: ErrorSeverity.HIGH,
            AuthErrorType.INSUFFICIENT_PERMISSIONS: ErrorSeverity.MEDIUM,
            AuthErrorType.SESSION_EXPIRED: ErrorSeverity.MEDIUM,
            AuthErrorType.RESOURCE_NOT_FOUND: ErrorSeverity.MEDIUM,
            AuthErrorType.RATE_LIMITED: ErrorSeverity.LOW,
            AuthErrorType.QUOTA_EXCEEDED: ErrorSeverity.LOW
        }
        
        return severity_map.get(error_type, ErrorSeverity.MEDIUM)
    
    def _get_http_status_code(self, error: Exception, error_type: AuthErrorType) -> int:
        """Get appropriate HTTP status code for error."""
        
        if isinstance(error, HTTPException):
            return error.status_code
        
        status_map = {
            AuthErrorType.TOKEN_INVALID: status.HTTP_401_UNAUTHORIZED,
            AuthErrorType.SESSION_EXPIRED: status.HTTP_401_UNAUTHORIZED,
            AuthErrorType.OWNERSHIP_VIOLATION: status.HTTP_403_FORBIDDEN,
            AuthErrorType.INSUFFICIENT_PERMISSIONS: status.HTTP_403_FORBIDDEN,
            AuthErrorType.RESOURCE_NOT_FOUND: status.HTTP_404_NOT_FOUND,
            AuthErrorType.RATE_LIMITED: status.HTTP_429_TOO_MANY_REQUESTS,
            AuthErrorType.QUOTA_EXCEEDED: status.HTTP_402_PAYMENT_REQUIRED,
            AuthErrorType.SECURITY_VIOLATION: status.HTTP_403_FORBIDDEN
        }
        
        return status_map.get(error_type, status.HTTP_403_FORBIDDEN)
    
    def _get_user_friendly_message(self, error: Exception, error_type: AuthErrorType) -> str:
        """Get user-friendly error message."""
        
        # Try to get message from error object first
        if hasattr(error, 'user_message'):
            return error.user_message
        
        # Default messages by error type
        message_map = {
            AuthErrorType.OWNERSHIP_VIOLATION: "Access denied. You don't have permission to access this resource.",
            AuthErrorType.INSUFFICIENT_PERMISSIONS: "Access denied. You don't have sufficient permissions.",
            AuthErrorType.RESOURCE_NOT_FOUND: "The requested resource was not found.",
            AuthErrorType.TOKEN_INVALID: "Authentication failed. Please log in again.",
            AuthErrorType.SESSION_EXPIRED: "Your session has expired. Please log in again.",
            AuthErrorType.RATE_LIMITED: "Too many requests. Please wait before trying again.",
            AuthErrorType.QUOTA_EXCEEDED: "Usage quota exceeded. Please upgrade your plan.",
            AuthErrorType.SECURITY_VIOLATION: "Access denied due to security policy."
        }
        
        return message_map.get(error_type, "Access denied.")
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check forwarded headers
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else 'unknown'
    
    def _get_security_headers(self) -> Dict[str, str]:
        """Get security headers for error responses."""
        return {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }


# Global error handler instance
auth_error_handler = AuthorizationErrorHandler()


# Convenience functions for common use cases

async def handle_generation_access_error(
    generation_id: str,
    user_id: Optional[str] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """Handle generation access denied errors."""
    
    error = GenerationAccessDeniedError(
        generation_id=generation_id,
        user_id=user_id
    )
    
    context = AuthErrorContext(
        user_id=user_id,
        resource_id=generation_id,
        resource_type="generation",
        action="access",
        correlation_id=str(error.correlation_id)
    )
    
    if request:
        context.client_ip = auth_error_handler._get_client_ip(request)
        context.user_agent = request.headers.get('user-agent')
        context.request_path = str(request.url.path)
        context.request_method = request.method
    
    return await auth_error_handler.handle_authorization_error(error, context, request)


async def handle_project_access_error(
    project_id: str,
    user_id: Optional[str] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """Handle project access denied errors."""
    
    error = ProjectAccessDeniedError(
        project_id=project_id,
        user_id=user_id
    )
    
    context = AuthErrorContext(
        user_id=user_id,
        resource_id=project_id,
        resource_type="project",
        action="access",
        correlation_id=str(error.correlation_id)
    )
    
    if request:
        context.client_ip = auth_error_handler._get_client_ip(request)
        context.user_agent = request.headers.get('user-agent')
        context.request_path = str(request.url.path)
        context.request_method = request.method
    
    return await auth_error_handler.handle_authorization_error(error, context, request)


async def handle_generic_auth_error(
    error: Union[Exception, HTTPException],
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """Handle generic authorization errors."""
    
    context = AuthErrorContext(
        user_id=user_id,
        resource_id=resource_id,
        resource_type=resource_type,
        action="access"
    )
    
    if request:
        context.client_ip = auth_error_handler._get_client_ip(request)
        context.user_agent = request.headers.get('user-agent')
        context.request_path = str(request.url.path)
        context.request_method = request.method
        context.correlation_id = getattr(request.state, 'request_id', str(uuid.uuid4()))
    
    return await auth_error_handler.handle_authorization_error(error, context, request)