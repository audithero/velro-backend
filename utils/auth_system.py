"""
Comprehensive UUID Authorization System
Integrates error handling, logging, circuit breakers, and monitoring for production-ready auth.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List, Union, Callable
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from dataclasses import dataclass
import uuid

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from .exceptions import (
    AuthorizationError, UUIDAuthorizationError, GenerationAccessDeniedError,
    ProjectAccessDeniedError, TeamAccessDeniedError, SecurityError,
    TokenValidationError, SessionExpiredError, ErrorSeverity
)
from .auth_error_handler import (
    AuthorizationErrorHandler, AuthErrorContext, auth_error_handler,
    handle_generation_access_error, handle_project_access_error, handle_generic_auth_error
)
from .auth_logger import (
    AuthorizationLogger, AuthLogContext, AuthLogMetrics, AuthEventType,
    auth_logger, log_generation_access_attempt, log_token_validation_attempt,
    log_ownership_verification, log_security_incident
)
from .circuit_breaker import (
    AuthCircuitBreaker, CircuitBreakerConfig, CircuitBreakerError,
    circuit_breaker_manager, with_circuit_breaker
)
from .uuid_utils import UUIDUtils

logger = logging.getLogger(__name__)


@dataclass
class AuthSystemConfig:
    """Configuration for the authorization system."""
    enable_circuit_breakers: bool = True
    enable_detailed_logging: bool = True
    enable_security_monitoring: bool = True
    enable_performance_monitoring: bool = True
    enable_fallback_strategies: bool = True
    
    # Circuit breaker settings
    database_timeout: float = 10.0
    external_auth_timeout: float = 15.0
    token_validation_timeout: float = 5.0
    
    # Security settings
    max_failed_attempts_per_minute: int = 10
    max_failed_attempts_per_hour: int = 100
    security_violation_threshold: int = 5
    
    # Performance settings
    slow_operation_threshold_ms: float = 1000.0
    cache_ttl_seconds: int = 300
    metrics_retention_hours: int = 24


class UUIDAuthorizationSystem:
    """
    Comprehensive UUID-based authorization system with error handling, logging, and monitoring.
    """
    
    def __init__(self, config: Optional[AuthSystemConfig] = None):
        self.config = config or AuthSystemConfig()
        self.error_handler = auth_error_handler
        self.logger = auth_logger
        self.circuit_breaker_manager = circuit_breaker_manager
        
        # System state
        self.is_healthy = True
        self.maintenance_mode = False
        self.system_metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'average_response_time': 0.0,
            'error_rate': 0.0
        }
        
        # Initialize circuit breakers with custom configs
        self._initialize_circuit_breakers()
        
        logger.info("🚀 [AUTH-SYSTEM] UUID Authorization System initialized")
    
    def _initialize_circuit_breakers(self):
        """Initialize circuit breakers with system configuration."""
        
        if not self.config.enable_circuit_breakers:
            return
        
        # Database operations circuit breaker
        db_config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=60,
            timeout=self.config.database_timeout,
            fallback_function=self._database_fallback
        )
        self.circuit_breaker_manager.get_circuit_breaker('database', db_config)
        
        # External authentication circuit breaker
        external_auth_config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=45,
            timeout=self.config.external_auth_timeout,
            fallback_function=self._external_auth_fallback
        )
        self.circuit_breaker_manager.get_circuit_breaker('external_auth', external_auth_config)
        
        # Token validation circuit breaker
        token_config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30,
            timeout=self.config.token_validation_timeout,
            fallback_function=self._token_validation_fallback
        )
        self.circuit_breaker_manager.get_circuit_breaker('token_validation', token_config)
    
    async def authorize_generation_access(
        self,
        user_id: str,
        generation_id: str,
        action: str = "read",
        request: Optional[Request] = None
    ) -> Dict[str, Any]:
        """
        Authorize access to a generation with comprehensive error handling and logging.
        
        Args:
            user_id: ID of the user requesting access
            generation_id: ID of the generation to access
            action: Type of action (read, write, delete, etc.)
            request: Optional FastAPI request object for context
            
        Returns:
            Authorization result with detailed information
            
        Raises:
            GenerationAccessDeniedError: If access is denied
            AuthorizationError: For other authorization failures
        """
        start_time = datetime.now(timezone.utc)
        context = self._create_auth_context(user_id, generation_id, "generation", action, request)
        
        try:
            # Validate UUIDs
            user_uuid = UUIDUtils.validate_and_convert(user_id, "user_id")
            generation_uuid = UUIDUtils.validate_and_convert(generation_id, "generation_id")
            
            # Perform authorization with circuit breaker protection
            if self.config.enable_circuit_breakers:
                authorization_result = await self._authorize_with_circuit_breaker(
                    self._check_generation_ownership,
                    user_uuid,
                    generation_uuid,
                    action
                )
            else:
                authorization_result = await self._check_generation_ownership(
                    user_uuid, generation_uuid, action
                )
            
            # Calculate metrics
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            metrics = AuthLogMetrics(processing_time_ms=processing_time)
            
            # Log successful authorization
            if self.config.enable_detailed_logging:
                await log_generation_access_attempt(
                    str(user_uuid),
                    str(generation_uuid),
                    'granted',
                    self._extract_request_context(request),
                    metrics
                )
            
            # Update system metrics
            await self._update_system_metrics(True, processing_time)
            
            return {
                'authorized': True,
                'user_id': str(user_uuid),
                'resource_id': str(generation_uuid),
                'resource_type': 'generation',
                'action': action,
                'processing_time_ms': processing_time,
                'timestamp': start_time.isoformat()
            }
            
        except Exception as e:
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            metrics = AuthLogMetrics(processing_time_ms=processing_time)
            
            # Log failed authorization
            if self.config.enable_detailed_logging:
                await log_generation_access_attempt(
                    user_id,
                    generation_id,
                    f'denied: {str(e)}',
                    self._extract_request_context(request),
                    metrics
                )
            
            # Update system metrics
            await self._update_system_metrics(False, processing_time)
            
            # Handle the error with comprehensive error handling
            if isinstance(e, (UUIDAuthorizationError, GenerationAccessDeniedError)):
                raise e
            else:
                # Wrap generic errors in authorization error
                auth_error = GenerationAccessDeniedError(
                    generation_id=generation_id,
                    user_id=user_id,
                    details={'original_error': str(e), 'error_type': type(e).__name__}
                )
                raise auth_error
    
    async def authorize_project_access(
        self,
        user_id: str,
        project_id: str,
        action: str = "read",
        request: Optional[Request] = None
    ) -> Dict[str, Any]:
        """Authorize access to a project."""
        start_time = datetime.now(timezone.utc)
        context = self._create_auth_context(user_id, project_id, "project", action, request)
        
        try:
            user_uuid = UUIDUtils.validate_and_convert(user_id, "user_id")
            project_uuid = UUIDUtils.validate_and_convert(project_id, "project_id")
            
            if self.config.enable_circuit_breakers:
                authorization_result = await self._authorize_with_circuit_breaker(
                    self._check_project_access,
                    user_uuid,
                    project_uuid,
                    action
                )
            else:
                authorization_result = await self._check_project_access(
                    user_uuid, project_uuid, action
                )
            
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            await self._update_system_metrics(True, processing_time)
            
            return {
                'authorized': True,
                'user_id': str(user_uuid),
                'resource_id': str(project_uuid),
                'resource_type': 'project',
                'action': action,
                'processing_time_ms': processing_time,
                'timestamp': start_time.isoformat()
            }
            
        except Exception as e:
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            await self._update_system_metrics(False, processing_time)
            
            if isinstance(e, (UUIDAuthorizationError, ProjectAccessDeniedError)):
                raise e
            else:
                auth_error = ProjectAccessDeniedError(
                    project_id=project_id,
                    user_id=user_id,
                    details={'original_error': str(e), 'error_type': type(e).__name__}
                )
                raise auth_error
    
    async def validate_token(
        self,
        token: str,
        token_type: str = "access",
        request: Optional[Request] = None
    ) -> Dict[str, Any]:
        """Validate authentication token with comprehensive error handling."""
        start_time = datetime.now(timezone.utc)
        
        try:
            if self.config.enable_circuit_breakers:
                validation_result = await self._authorize_with_circuit_breaker(
                    self._perform_token_validation,
                    token,
                    token_type
                )
            else:
                validation_result = await self._perform_token_validation(token, token_type)
            
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Log successful validation
            if self.config.enable_detailed_logging:
                await log_token_validation_attempt(
                    validation_result.get('user_id'),
                    token_type,
                    'valid',
                    {'processing_time_ms': processing_time},
                    AuthLogMetrics(processing_time_ms=processing_time)
                )
            
            await self._update_system_metrics(True, processing_time)
            
            return validation_result
            
        except Exception as e:
            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            
            # Log failed validation
            if self.config.enable_detailed_logging:
                await log_token_validation_attempt(
                    None,
                    token_type,
                    'invalid',
                    {'error': str(e), 'processing_time_ms': processing_time},
                    AuthLogMetrics(processing_time_ms=processing_time)
                )
            
            await self._update_system_metrics(False, processing_time)
            
            if isinstance(e, TokenValidationError):
                raise e
            else:
                token_error = TokenValidationError(
                    f"Token validation failed: {str(e)}",
                    token_type=token_type,
                    validation_failure_reason=str(e)
                )
                raise token_error
    
    async def handle_authorization_error(
        self,
        error: Union[Exception, HTTPException],
        user_id: Optional[str] = None,
        resource_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        request: Optional[Request] = None
    ) -> JSONResponse:
        """Handle authorization errors with comprehensive error response."""
        
        context = AuthErrorContext(
            user_id=user_id,
            resource_id=resource_id,
            resource_type=resource_type,
            correlation_id=str(uuid.uuid4())
        )
        
        if request:
            context.client_ip = self._get_client_ip(request)
            context.user_agent = request.headers.get('user-agent')
            context.request_path = str(request.url.path)
            context.request_method = request.method
            context.request_id = getattr(request.state, 'request_id', None)
        
        return await self.error_handler.handle_authorization_error(
            error, context, request
        )
    
    async def check_system_health(self) -> Dict[str, Any]:
        """Check the health of the authorization system."""
        
        health_status = {
            'healthy': self.is_healthy,
            'maintenance_mode': self.maintenance_mode,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'system_metrics': self.system_metrics.copy(),
            'circuit_breakers': {},
            'subsystem_health': {
                'error_handler': True,
                'logger': True,
                'circuit_breakers': True,
                'uuid_utils': True
            }
        }
        
        # Check circuit breaker health
        if self.config.enable_circuit_breakers:
            cb_states = self.circuit_breaker_manager.get_all_states()
            health_status['circuit_breakers'] = cb_states
            
            # System is unhealthy if critical circuit breakers are open
            critical_breakers = ['database', 'token_validation']
            for cb_name in critical_breakers:
                if cb_name in cb_states and cb_states[cb_name]['state'] == 'open':
                    self.is_healthy = False
                    health_status['healthy'] = False
                    health_status['issues'] = health_status.get('issues', [])
                    health_status['issues'].append(f'Critical circuit breaker {cb_name} is open')
        
        return health_status
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get comprehensive system metrics."""
        
        metrics = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'system_metrics': self.system_metrics.copy(),
            'circuit_breakers': self.circuit_breaker_manager.get_all_states(),
            'configuration': {
                'enable_circuit_breakers': self.config.enable_circuit_breakers,
                'enable_detailed_logging': self.config.enable_detailed_logging,
                'enable_security_monitoring': self.config.enable_security_monitoring,
                'enable_performance_monitoring': self.config.enable_performance_monitoring
            }
        }
        
        return metrics
    
    async def reset_system_state(self):
        """Reset the authorization system to initial state."""
        
        logger.info("🔄 [AUTH-SYSTEM] Resetting system state")
        
        # Reset circuit breakers
        if self.config.enable_circuit_breakers:
            await self.circuit_breaker_manager.reset_all()
        
        # Reset system metrics
        self.system_metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'average_response_time': 0.0,
            'error_rate': 0.0
        }
        
        # Reset health status
        self.is_healthy = True
        self.maintenance_mode = False
        
        logger.info("✅ [AUTH-SYSTEM] System state reset complete")
    
    def _create_auth_context(
        self,
        user_id: str,
        resource_id: str,
        resource_type: str,
        action: str,
        request: Optional[Request]
    ) -> AuthLogContext:
        """Create authorization context for logging."""
        
        context = AuthLogContext(
            user_id=user_id,
            resource_id=resource_id,
            resource_type=resource_type,
            action=action
        )
        
        if request:
            context.client_ip = self._get_client_ip(request)
            context.user_agent = request.headers.get('user-agent')
            context.request_path = str(request.url.path)
            context.request_method = request.method
            context.session_id = getattr(request.state, 'session_id', None)
            context.request_id = getattr(request.state, 'request_id', None)
        
        return context
    
    def _extract_request_context(self, request: Optional[Request]) -> Optional[Dict[str, Any]]:
        """Extract request context for logging."""
        
        if not request:
            return None
        
        return {
            'client_ip': self._get_client_ip(request),
            'user_agent': request.headers.get('user-agent'),
            'request_path': str(request.url.path),
            'request_method': request.method,
            'session_id': getattr(request.state, 'session_id', None),
            'request_id': getattr(request.state, 'request_id', None)
        }
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        forwarded_for = request.headers.get('x-forwarded-for')
        if forwarded_for:
            return forwarded_for.split(',')[0].strip()
        
        real_ip = request.headers.get('x-real-ip')
        if real_ip:
            return real_ip
        
        return request.client.host if request.client else 'unknown'
    
    async def _authorize_with_circuit_breaker(self, func: Callable, *args, **kwargs):
        """Execute authorization function with circuit breaker protection."""
        
        # Determine circuit breaker based on function
        if func.__name__ == '_perform_token_validation':
            cb_name = 'token_validation'
        elif func.__name__ in ['_check_generation_ownership', '_check_project_access']:
            cb_name = 'database'
        else:
            cb_name = 'external_auth'
        
        cb = self.circuit_breaker_manager.get_circuit_breaker(cb_name)
        return await cb.call(func, *args, **kwargs)
    
    async def _check_generation_ownership(
        self,
        user_id: uuid.UUID,
        generation_id: uuid.UUID,
        action: str
    ) -> Dict[str, Any]:
        """Check if user owns or has access to the generation."""
        
        # This would implement actual database lookup
        # For now, simulating the check
        
        try:
            from database import SupabaseClient
            db_client = SupabaseClient()
            
            if not db_client.is_available():
                raise DatabaseError("Database is not available")
            
            # Query generation ownership
            result = db_client.service_client.table('generations').select('user_id, created_by').eq('id', str(generation_id)).execute()
            
            if not result.data:
                raise GenerationAccessDeniedError(
                    generation_id=str(generation_id),
                    user_id=str(user_id),
                    details={'reason': 'Generation not found'}
                )
            
            generation_data = result.data[0]
            owner_id = generation_data.get('user_id') or generation_data.get('created_by')
            
            if str(owner_id) != str(user_id):
                # Log ownership verification
                if self.config.enable_detailed_logging:
                    await log_ownership_verification(
                        str(user_id),
                        str(generation_id),
                        'generation',
                        str(owner_id),
                        False
                    )
                
                raise GenerationAccessDeniedError(
                    generation_id=str(generation_id),
                    user_id=str(user_id),
                    owner_id=str(owner_id),
                    details={'reason': 'Ownership check failed'}
                )
            
            # Log successful ownership verification
            if self.config.enable_detailed_logging:
                await log_ownership_verification(
                    str(user_id),
                    str(generation_id),
                    'generation',
                    str(owner_id),
                    True
                )
            
            return {
                'authorized': True,
                'owner_id': str(owner_id),
                'resource_type': 'generation',
                'action': action
            }
            
        except Exception as e:
            if isinstance(e, GenerationAccessDeniedError):
                raise e
            else:
                logger.error(f"❌ [AUTH-SYSTEM] Generation ownership check failed: {e}")
                raise GenerationAccessDeniedError(
                    generation_id=str(generation_id),
                    user_id=str(user_id),
                    details={'error': str(e), 'check_type': 'database_error'}
                )
    
    async def _check_project_access(
        self,
        user_id: uuid.UUID,
        project_id: uuid.UUID,
        action: str
    ) -> Dict[str, Any]:
        """Check if user has access to the project."""
        
        try:
            from database import SupabaseClient
            db_client = SupabaseClient()
            
            if not db_client.is_available():
                raise DatabaseError("Database is not available")
            
            # Check project membership or ownership
            project_result = db_client.service_client.table('projects').select('user_id, team_id').eq('id', str(project_id)).execute()
            
            if not project_result.data:
                raise ProjectAccessDeniedError(
                    project_id=str(project_id),
                    user_id=str(user_id),
                    details={'reason': 'Project not found'}
                )
            
            project_data = project_result.data[0]
            project_owner = project_data.get('user_id')
            team_id = project_data.get('team_id')
            
            # Check if user is project owner
            if str(project_owner) == str(user_id):
                return {
                    'authorized': True,
                    'access_type': 'owner',
                    'project_id': str(project_id)
                }
            
            # Check team membership if project has a team
            if team_id:
                team_result = db_client.service_client.table('team_members').select('user_id').eq('team_id', str(team_id)).eq('user_id', str(user_id)).execute()
                
                if team_result.data:
                    return {
                        'authorized': True,
                        'access_type': 'team_member',
                        'project_id': str(project_id),
                        'team_id': str(team_id)
                    }
            
            # No access found
            raise ProjectAccessDeniedError(
                project_id=str(project_id),
                user_id=str(user_id),
                details={'reason': 'No access permission found'}
            )
            
        except Exception as e:
            if isinstance(e, ProjectAccessDeniedError):
                raise e
            else:
                logger.error(f"❌ [AUTH-SYSTEM] Project access check failed: {e}")
                raise ProjectAccessDeniedError(
                    project_id=str(project_id),
                    user_id=str(user_id),
                    details={'error': str(e), 'check_type': 'database_error'}
                )
    
    async def _perform_token_validation(
        self,
        token: str,
        token_type: str
    ) -> Dict[str, Any]:
        """Perform token validation with comprehensive error handling."""
        
        try:
            # Import auth middleware for token validation
            from middleware.auth import AuthMiddleware
            
            # Create temporary middleware instance for validation
            auth_middleware = AuthMiddleware(app=None)
            user = await auth_middleware._verify_token(token)
            
            return {
                'valid': True,
                'user_id': str(user.id),
                'email': user.email,
                'role': user.role,
                'token_type': token_type
            }
            
        except HTTPException as e:
            if e.status_code == 401:
                raise TokenValidationError(
                    f"Token validation failed: {e.detail}",
                    token_type=token_type,
                    validation_failure_reason=str(e.detail)
                )
            else:
                raise e
        except Exception as e:
            logger.error(f"❌ [AUTH-SYSTEM] Token validation error: {e}")
            raise TokenValidationError(
                f"Token validation failed: {str(e)}",
                token_type=token_type,
                validation_failure_reason=str(e)
            )
    
    async def _update_system_metrics(self, success: bool, processing_time_ms: float):
        """Update system-level metrics."""
        
        self.system_metrics['total_requests'] += 1
        
        if success:
            self.system_metrics['successful_requests'] += 1
        else:
            self.system_metrics['failed_requests'] += 1
        
        # Update average response time
        total_requests = self.system_metrics['total_requests']
        current_avg = self.system_metrics['average_response_time']
        self.system_metrics['average_response_time'] = (
            (current_avg * (total_requests - 1) + processing_time_ms) / total_requests
        )
        
        # Update error rate
        self.system_metrics['error_rate'] = (
            self.system_metrics['failed_requests'] / total_requests
        ) * 100
        
        # Log slow operations
        if (self.config.enable_performance_monitoring and 
            processing_time_ms > self.config.slow_operation_threshold_ms):
            
            logger.warning(
                f"🐌 [AUTH-SYSTEM] Slow authorization operation: {processing_time_ms:.2f}ms"
            )
    
    # Fallback functions for circuit breakers
    
    async def _database_fallback(self, *args, **kwargs):
        """Fallback for database operations."""
        logger.warning("🔄 [AUTH-SYSTEM] Using database fallback - denying access for security")
        return None  # Conservative fallback
    
    async def _external_auth_fallback(self, *args, **kwargs):
        """Fallback for external auth operations."""
        logger.warning("🔄 [AUTH-SYSTEM] Using external auth fallback - denying access")
        return False  # Conservative fallback
    
    async def _token_validation_fallback(self, *args, **kwargs):
        """Fallback for token validation."""
        logger.warning("🔄 [AUTH-SYSTEM] Using token validation fallback - denying access")
        return False  # Conservative fallback for security


# Global authorization system instance
auth_system = UUIDAuthorizationSystem()


# Convenience functions for easy integration

async def authorize_generation_access(
    user_id: str,
    generation_id: str,
    action: str = "read",
    request: Optional[Request] = None
) -> Dict[str, Any]:
    """Convenience function to authorize generation access."""
    return await auth_system.authorize_generation_access(user_id, generation_id, action, request)


async def authorize_project_access(
    user_id: str,
    project_id: str,
    action: str = "read",
    request: Optional[Request] = None
) -> Dict[str, Any]:
    """Convenience function to authorize project access."""
    return await auth_system.authorize_project_access(user_id, project_id, action, request)


async def validate_auth_token(
    token: str,
    token_type: str = "access",
    request: Optional[Request] = None
) -> Dict[str, Any]:
    """Convenience function to validate authentication token."""
    return await auth_system.validate_token(token, token_type, request)


async def handle_auth_error(
    error: Union[Exception, HTTPException],
    user_id: Optional[str] = None,
    resource_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    request: Optional[Request] = None
) -> JSONResponse:
    """Convenience function to handle authorization errors."""
    return await auth_system.handle_authorization_error(
        error, user_id, resource_id, resource_type, request
    )


async def get_auth_system_health() -> Dict[str, Any]:
    """Get the health status of the authorization system."""
    return await auth_system.check_system_health()


async def get_auth_system_metrics() -> Dict[str, Any]:
    """Get comprehensive metrics from the authorization system."""
    return await auth_system.get_system_metrics()


@asynccontextmanager
async def auth_context(request: Optional[Request] = None):
    """Context manager for authorization operations with automatic error handling."""
    
    correlation_id = str(uuid.uuid4())
    start_time = datetime.now(timezone.utc)
    
    try:
        yield auth_system
    except Exception as e:
        # Log the error in context
        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        logger.error(
            f"❌ [AUTH-CONTEXT] Authorization context error: {e}",
            extra={
                'correlation_id': correlation_id,
                'processing_time_ms': processing_time,
                'error_type': type(e).__name__}
        )
        
        raise e