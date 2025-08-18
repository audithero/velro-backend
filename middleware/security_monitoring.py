"""
Security Monitoring Middleware
Integrates real-time security monitoring and audit logging with the existing security infrastructure.
"""

import time
import json
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

# Import security monitoring system
try:
    from security.security_monitoring_system import (
        security_monitor,
        SecurityEvent,
        SecurityEventType,
        SecuritySeverity
    )
    from monitoring.metrics import metrics_collector
except ImportError:
    # Fallback for testing
    security_monitor = None
    metrics_collector = None

logger = logging.getLogger(__name__)


class SecurityMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Security monitoring middleware that integrates with the comprehensive
    security monitoring system to provide real-time threat detection,
    audit logging, and incident response.
    """
    
    def __init__(self, app, enable_blocking: bool = True, enable_audit_logging: bool = True):
        super().__init__(app)
        self.enable_blocking = enable_blocking
        self.enable_audit_logging = enable_audit_logging
        self.monitoring_enabled = security_monitor is not None
        
        # Initialize monitoring if available
        if self.monitoring_enabled and not hasattr(security_monitor, '_initialized'):
            asyncio.create_task(self._initialize_monitoring())
        
        logger.info("🛡️ Security Monitoring Middleware initialized")
    
    async def _initialize_monitoring(self):
        """Initialize security monitoring system."""
        try:
            await security_monitor.start_monitoring()
            security_monitor._initialized = True
            logger.info("✅ Security monitoring system started")
        except Exception as e:
            logger.error(f"❌ Failed to start security monitoring: {e}")
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Main middleware processing with security monitoring integration."""
        start_time = time.time()
        
        try:
            # Skip monitoring for health checks and metrics endpoints
            if self._should_skip_monitoring(request.url.path):
                return await call_next(request)
            
            # Pre-request security analysis
            security_events = await self._analyze_request_security(request)
            
            # Check for blocking conditions
            if self.enable_blocking and security_events:
                block_response = await self._evaluate_blocking(request, security_events)
                if block_response:
                    return block_response
            
            # Add security context to request state
            self._add_security_context(request, security_events)
            
            # Process request
            response = await call_next(request)
            
            # Post-request security analysis
            await self._analyze_response_security(request, response, security_events)
            
            # Record successful request metrics
            processing_time = time.time() - start_time
            await self._record_request_metrics(request, response, processing_time, security_events)
            
            return response
            
        except HTTPException as e:
            # Handle security-related HTTP exceptions
            return await self._handle_security_exception(request, e, start_time)
            
        except Exception as e:
            # Handle unexpected errors with security logging
            logger.error(f"❌ Security monitoring error: {e}")
            return await self._handle_unexpected_error(request, e, start_time)
    
    def _should_skip_monitoring(self, path: str) -> bool:
        """Check if path should be skipped from security monitoring."""
        skip_paths = {
            '/health', '/healthz', '/ping', '/status',
            '/metrics', '/prometheus',
            '/favicon.ico', '/robots.txt'
        }
        return path in skip_paths
    
    async def _analyze_request_security(self, request: Request) -> list:
        """Analyze request for security threats."""
        if not self.monitoring_enabled:
            return []
        
        try:
            # Use security monitoring system for analysis
            security_events = await security_monitor.analyze_request(request)
            
            # Log detected security events
            if security_events:
                logger.warning(f"⚠️ Security threats detected: {len(security_events)} events")
                for event in security_events:
                    logger.warning(f"  - {event.event_type.value}: {event.description}")
            
            return security_events
            
        except Exception as e:
            logger.error(f"❌ Error in security analysis: {e}")
            return []
    
    async def _evaluate_blocking(self, request: Request, security_events: list) -> Optional[Response]:
        """Evaluate if request should be blocked based on security events."""
        if not security_events:
            return None
        
        # Check for critical threats that should be immediately blocked
        critical_events = [
            event for event in security_events 
            if event.severity >= SecuritySeverity.HIGH
        ]
        
        if critical_events:
            client_ip = self._get_client_ip(request)
            
            # Auto-block IP for critical threats
            if security_monitor:
                try:
                    await security_monitor.block_ip(
                        client_ip,
                        f"Critical security threat detected: {critical_events[0].event_type.value}",
                        duration_hours=24
                    )
                except Exception as e:
                    logger.error(f"❌ Failed to block IP: {e}")
            
            # Return blocked response
            return JSONResponse(
                status_code=403,
                content={
                    "error": "Access blocked due to security violation",
                    "request_id": self._generate_request_id(),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Check if IP is already blocked
        if security_monitor:
            try:
                client_ip = self._get_client_ip(request)
                is_blocked = await security_monitor.check_ip_blocked(client_ip)
                if is_blocked:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": "Access temporarily restricted",
                            "request_id": self._generate_request_id(),
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
            except Exception as e:
                logger.error(f"❌ Error checking blocked IP: {e}")
        
        return None
    
    def _add_security_context(self, request: Request, security_events: list):
        """Add security context to request state."""
        # Add security events to request state for downstream use
        request.state.security_events = security_events
        request.state.security_threat_level = self._calculate_threat_level(security_events)
        request.state.security_monitoring_enabled = self.monitoring_enabled
    
    def _calculate_threat_level(self, security_events: list) -> str:
        """Calculate overall threat level from security events."""
        if not security_events:
            return "none"
        
        max_severity = max(event.severity for event in security_events)
        
        if max_severity >= SecuritySeverity.CRITICAL:
            return "critical"
        elif max_severity >= SecuritySeverity.HIGH:
            return "high"
        elif max_severity >= SecuritySeverity.MEDIUM:
            return "medium"
        else:
            return "low"
    
    async def _analyze_response_security(self, request: Request, response: Response, 
                                       security_events: list):
        """Analyze response for additional security insights."""
        if not self.monitoring_enabled:
            return
        
        try:
            # Check for suspicious response patterns
            response_security_events = []
            
            # Detect potential data leakage in error responses
            if response.status_code >= 400 and hasattr(response, 'body'):
                if self._contains_sensitive_data_patterns(str(response.body)):
                    event = SecurityEvent(
                        event_id=security_monitor._generate_event_id(),
                        event_type=SecurityEventType.DATA_EXFILTRATION_ATTEMPT,
                        severity=SecuritySeverity.HIGH,
                        timestamp=datetime.now(timezone.utc),
                        source_ip=self._get_client_ip(request),
                        user_id=getattr(request.state, 'user_id', None),
                        session_id=getattr(request.state, 'session_id', None),
                        endpoint=str(request.url.path),
                        method=request.method,
                        user_agent=request.headers.get('user-agent', ''),
                        request_id=request.headers.get('x-request-id', ''),
                        description=f"Potential data leakage in error response (status: {response.status_code})",
                        metadata={
                            'response_status': response.status_code,
                            'response_size': len(str(response.body)) if hasattr(response, 'body') else 0
                        }
                    )
                    response_security_events.append(event)
            
            # Add response security events to monitoring queue
            if response_security_events:
                for event in response_security_events:
                    security_monitor.event_queue.append(event)
            
        except Exception as e:
            logger.error(f"❌ Error in response security analysis: {e}")
    
    def _contains_sensitive_data_patterns(self, content: str) -> bool:
        """Check if content contains sensitive data patterns."""
        import re
        
        sensitive_patterns = [
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',  # Email
            r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b',  # Credit card
            r'\b\d{3}-\d{2}-\d{4}\b',  # SSN
            r'password["\s:=]+[^"\s,}]+',  # Password in responses
            r'api[_-]?key["\s:=]+[^"\s,}]+',  # API keys
            r'secret["\s:=]+[^"\s,}]+',  # Secrets
        ]
        
        for pattern in sensitive_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        return False
    
    async def _record_request_metrics(self, request: Request, response: Response, 
                                    processing_time: float, security_events: list):
        """Record request metrics including security context."""
        if not metrics_collector:
            return
        
        try:
            # Record standard performance metrics
            if hasattr(metrics_collector, 'performance_metrics'):
                metrics_collector.performance_metrics.record_request(
                    method=request.method,
                    endpoint=str(request.url.path),
                    status_code=response.status_code,
                    duration_seconds=processing_time
                )
            
            # Record security metrics
            if hasattr(metrics_collector, 'security_metrics'):
                # Record authentication metrics for auth endpoints
                if '/auth/' in str(request.url.path):
                    user_agent = request.headers.get('user-agent', '')[:100]
                    result = 'success' if response.status_code < 400 else 'failure'
                    
                    metrics_collector.security_metrics.record_auth_attempt(
                        result=result,
                        method=request.method,
                        user_agent=user_agent
                    )
                    
                    # Record failed login if applicable
                    if result == 'failure' and response.status_code == 401:
                        client_ip = self._get_client_ip(request)
                        user_id = getattr(request.state, 'user_id', 'unknown')
                        
                        metrics_collector.security_metrics.record_failed_login(
                            reason='invalid_credentials',
                            source_ip=client_ip,
                            user_id=user_id
                        )
                
                # Record security violations
                for event in security_events:
                    metrics_collector.security_metrics.record_security_violation(
                        violation_type=event.event_type.value,
                        severity=event.severity.name.lower(),
                        source_ip=event.source_ip
                    )
            
        except Exception as e:
            logger.error(f"❌ Error recording security metrics: {e}")
    
    async def _handle_security_exception(self, request: Request, exception: HTTPException, 
                                       start_time: float) -> Response:
        """Handle security-related HTTP exceptions."""
        processing_time = time.time() - start_time
        
        # Log security exception
        client_ip = self._get_client_ip(request)
        logger.warning(
            f"🚨 Security exception: {exception.status_code} - {exception.detail} "
            f"| IP: {client_ip} | Path: {request.url.path}"
        )
        
        # Record security metrics
        if self.monitoring_enabled and security_monitor:
            try:
                # Create security event for the exception
                event = SecurityEvent(
                    event_id=security_monitor._generate_event_id(),
                    event_type=self._map_status_code_to_security_event(exception.status_code),
                    severity=self._map_status_code_to_severity(exception.status_code),
                    timestamp=datetime.now(timezone.utc),
                    source_ip=client_ip,
                    user_id=getattr(request.state, 'user_id', None),
                    session_id=getattr(request.state, 'session_id', None),
                    endpoint=str(request.url.path),
                    method=request.method,
                    user_agent=request.headers.get('user-agent', ''),
                    request_id=request.headers.get('x-request-id', ''),
                    description=f"HTTP {exception.status_code}: {exception.detail}",
                    metadata={
                        'status_code': exception.status_code,
                        'processing_time': processing_time
                    }
                )
                security_monitor.event_queue.append(event)
                
            except Exception as e:
                logger.error(f"❌ Error creating security event for exception: {e}")
        
        # Return secure error response
        return JSONResponse(
            status_code=exception.status_code,
            content={
                "error": self._get_secure_error_message(exception.status_code),
                "request_id": self._generate_request_id(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
    
    async def _handle_unexpected_error(self, request: Request, error: Exception, 
                                     start_time: float) -> Response:
        """Handle unexpected errors with security logging."""
        processing_time = time.time() - start_time
        client_ip = self._get_client_ip(request)
        
        # Log unexpected error
        logger.error(
            f"❌ Unexpected error in security monitoring: {type(error).__name__}: {error} "
            f"| IP: {client_ip} | Path: {request.url.path}"
        )
        
        # Create security event for unexpected error
        if self.monitoring_enabled and security_monitor:
            try:
                event = SecurityEvent(
                    event_id=security_monitor._generate_event_id(),
                    event_type=SecurityEventType.ANOMALOUS_BEHAVIOR,
                    severity=SecuritySeverity.MEDIUM,
                    timestamp=datetime.now(timezone.utc),
                    source_ip=client_ip,
                    user_id=getattr(request.state, 'user_id', None),
                    session_id=getattr(request.state, 'session_id', None),
                    endpoint=str(request.url.path),
                    method=request.method,
                    user_agent=request.headers.get('user-agent', ''),
                    request_id=request.headers.get('x-request-id', ''),
                    description=f"Unexpected error: {type(error).__name__}",
                    metadata={
                        'error_type': type(error).__name__,
                        'processing_time': processing_time
                    }
                )
                security_monitor.event_queue.append(event)
                
            except Exception as e:
                logger.error(f"❌ Error creating security event for unexpected error: {e}")
        
        # Return generic error response (no information disclosure)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "request_id": self._generate_request_id(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )
    
    def _map_status_code_to_security_event(self, status_code: int) -> SecurityEventType:
        """Map HTTP status code to security event type."""
        mapping = {
            400: SecurityEventType.INPUT_VALIDATION_FAILURE,
            401: SecurityEventType.AUTHENTICATION_FAILURE,
            403: SecurityEventType.AUTHORIZATION_VIOLATION,
            429: SecurityEventType.RATE_LIMIT_VIOLATION,
        }
        return mapping.get(status_code, SecurityEventType.ANOMALOUS_BEHAVIOR)
    
    def _map_status_code_to_severity(self, status_code: int) -> SecuritySeverity:
        """Map HTTP status code to security severity."""
        if status_code == 401:
            return SecuritySeverity.MEDIUM
        elif status_code == 403:
            return SecuritySeverity.HIGH
        elif status_code == 429:
            return SecuritySeverity.MEDIUM
        else:
            return SecuritySeverity.LOW
    
    def _get_secure_error_message(self, status_code: int) -> str:
        """Get secure error message without information disclosure."""
        messages = {
            400: "Bad request",
            401: "Authentication required",
            403: "Access forbidden", 
            404: "Resource not found",
            405: "Method not allowed",
            429: "Too many requests",
            500: "Internal server error",
        }
        return messages.get(status_code, "Request failed")
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request with proxy support."""
        # Check forwarded headers (for reverse proxies)
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else 'unknown'
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID for tracking."""
        import secrets
        return secrets.token_urlsafe(12)


# Security monitoring integration helpers
class SecurityMonitoringIntegration:
    """Helper class for integrating security monitoring into existing systems."""
    
    @staticmethod
    async def log_user_action(user_id: str, action: str, resource: str, 
                            source_ip: str, success: bool, metadata: Dict[str, Any]):
        """Log user actions for audit trail."""
        if security_monitor and security_monitor.audit_logger:
            try:
                await security_monitor.audit_logger.log_data_access(
                    user_id=user_id,
                    resource=resource,
                    action=action,
                    source_ip=source_ip,
                    success=success,
                    metadata=metadata
                )
            except Exception as e:
                logger.error(f"❌ Error logging user action: {e}")
    
    @staticmethod
    async def log_admin_action(admin_user_id: str, action: str, target: str,
                             source_ip: str, metadata: Dict[str, Any]):
        """Log administrative actions."""
        if security_monitor and security_monitor.audit_logger:
            try:
                await security_monitor.audit_logger.log_admin_action(
                    admin_user_id=admin_user_id,
                    action=action,
                    target=target,
                    source_ip=source_ip,
                    metadata=metadata
                )
            except Exception as e:
                logger.error(f"❌ Error logging admin action: {e}")
    
    @staticmethod
    async def create_security_alert(event_type: SecurityEventType, severity: SecuritySeverity,
                                  description: str, source_ip: str, user_id: Optional[str],
                                  metadata: Dict[str, Any]):
        """Create custom security alert."""
        if security_monitor:
            try:
                event = SecurityEvent(
                    event_id=security_monitor._generate_event_id(),
                    event_type=event_type,
                    severity=severity,
                    timestamp=datetime.now(timezone.utc),
                    source_ip=source_ip,
                    user_id=user_id,
                    session_id=None,
                    endpoint='',
                    method='',
                    user_agent='',
                    request_id='',
                    description=description,
                    metadata=metadata
                )
                security_monitor.event_queue.append(event)
            except Exception as e:
                logger.error(f"❌ Error creating security alert: {e}")
    
    @staticmethod
    def get_security_context(request: Request) -> Dict[str, Any]:
        """Get security context from request."""
        return {
            'security_events': getattr(request.state, 'security_events', []),
            'threat_level': getattr(request.state, 'security_threat_level', 'none'),
            'monitoring_enabled': getattr(request.state, 'security_monitoring_enabled', False)
        }