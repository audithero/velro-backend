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
            
            if isinstance(e, (UUIDAuthorizationError, ProjectAccessDeniedError)):\n                raise e\n            else:\n                auth_error = ProjectAccessDeniedError(\n                    project_id=project_id,\n                    user_id=user_id,\n                    details={'original_error': str(e), 'error_type': type(e).__name__}\n                )\n                raise auth_error\n    \n    async def validate_token(\n        self,\n        token: str,\n        token_type: str = "access",\n        request: Optional[Request] = None\n    ) -> Dict[str, Any]:\n        """Validate authentication token with comprehensive error handling."""\n        start_time = datetime.now(timezone.utc)\n        \n        try:\n            if self.config.enable_circuit_breakers:\n                validation_result = await self._authorize_with_circuit_breaker(\n                    self._perform_token_validation,\n                    token,\n                    token_type\n                )\n            else:\n                validation_result = await self._perform_token_validation(token, token_type)\n            \n            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000\n            \n            # Log successful validation\n            if self.config.enable_detailed_logging:\n                await log_token_validation_attempt(\n                    validation_result.get('user_id'),\n                    token_type,\n                    'valid',\n                    {'processing_time_ms': processing_time},\n                    AuthLogMetrics(processing_time_ms=processing_time)\n                )\n            \n            await self._update_system_metrics(True, processing_time)\n            \n            return validation_result\n            \n        except Exception as e:\n            processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000\n            \n            # Log failed validation\n            if self.config.enable_detailed_logging:\n                await log_token_validation_attempt(\n                    None,\n                    token_type,\n                    'invalid',\n                    {'error': str(e), 'processing_time_ms': processing_time},\n                    AuthLogMetrics(processing_time_ms=processing_time)\n                )\n            \n            await self._update_system_metrics(False, processing_time)\n            \n            if isinstance(e, TokenValidationError):\n                raise e\n            else:\n                token_error = TokenValidationError(\n                    f"Token validation failed: {str(e)}",\n                    token_type=token_type,\n                    validation_failure_reason=str(e)\n                )\n                raise token_error\n    \n    async def handle_authorization_error(\n        self,\n        error: Union[Exception, HTTPException],\n        user_id: Optional[str] = None,\n        resource_id: Optional[str] = None,\n        resource_type: Optional[str] = None,\n        request: Optional[Request] = None\n    ) -> JSONResponse:\n        """Handle authorization errors with comprehensive error response."""\n        \n        context = AuthErrorContext(\n            user_id=user_id,\n            resource_id=resource_id,\n            resource_type=resource_type,\n            correlation_id=str(uuid.uuid4())\n        )\n        \n        if request:\n            context.client_ip = self._get_client_ip(request)\n            context.user_agent = request.headers.get('user-agent')\n            context.request_path = str(request.url.path)\n            context.request_method = request.method\n            context.request_id = getattr(request.state, 'request_id', None)\n        \n        return await self.error_handler.handle_authorization_error(\n            error, context, request\n        )\n    \n    async def check_system_health(self) -> Dict[str, Any]:\n        """Check the health of the authorization system."""\n        \n        health_status = {\n            'healthy': self.is_healthy,\n            'maintenance_mode': self.maintenance_mode,\n            'timestamp': datetime.now(timezone.utc).isoformat(),\n            'system_metrics': self.system_metrics.copy(),\n            'circuit_breakers': {},\n            'subsystem_health': {\n                'error_handler': True,\n                'logger': True,\n                'circuit_breakers': True,\n                'uuid_utils': True\n            }\n        }\n        \n        # Check circuit breaker health\n        if self.config.enable_circuit_breakers:\n            cb_states = self.circuit_breaker_manager.get_all_states()\n            health_status['circuit_breakers'] = cb_states\n            \n            # System is unhealthy if critical circuit breakers are open\n            critical_breakers = ['database', 'token_validation']\n            for cb_name in critical_breakers:\n                if cb_name in cb_states and cb_states[cb_name]['state'] == 'open':\n                    self.is_healthy = False\n                    health_status['healthy'] = False\n                    health_status['issues'] = health_status.get('issues', [])\n                    health_status['issues'].append(f'Critical circuit breaker {cb_name} is open')\n        \n        return health_status\n    \n    async def get_system_metrics(self) -> Dict[str, Any]:\n        """Get comprehensive system metrics."""\n        \n        metrics = {\n            'timestamp': datetime.now(timezone.utc).isoformat(),\n            'system_metrics': self.system_metrics.copy(),\n            'circuit_breakers': self.circuit_breaker_manager.get_all_states(),\n            'configuration': {\n                'enable_circuit_breakers': self.config.enable_circuit_breakers,\n                'enable_detailed_logging': self.config.enable_detailed_logging,\n                'enable_security_monitoring': self.config.enable_security_monitoring,\n                'enable_performance_monitoring': self.config.enable_performance_monitoring\n            }\n        }\n        \n        return metrics\n    \n    async def reset_system_state(self):\n        """Reset the authorization system to initial state."""\n        \n        logger.info("🔄 [AUTH-SYSTEM] Resetting system state")\n        \n        # Reset circuit breakers\n        if self.config.enable_circuit_breakers:\n            await self.circuit_breaker_manager.reset_all()\n        \n        # Reset system metrics\n        self.system_metrics = {\n            'total_requests': 0,\n            'successful_requests': 0,\n            'failed_requests': 0,\n            'average_response_time': 0.0,\n            'error_rate': 0.0\n        }\n        \n        # Reset health status\n        self.is_healthy = True\n        self.maintenance_mode = False\n        \n        logger.info("✅ [AUTH-SYSTEM] System state reset complete")\n    \n    def _create_auth_context(\n        self,\n        user_id: str,\n        resource_id: str,\n        resource_type: str,\n        action: str,\n        request: Optional[Request]\n    ) -> AuthLogContext:\n        """Create authorization context for logging."""\n        \n        context = AuthLogContext(\n            user_id=user_id,\n            resource_id=resource_id,\n            resource_type=resource_type,\n            action=action\n        )\n        \n        if request:\n            context.client_ip = self._get_client_ip(request)\n            context.user_agent = request.headers.get('user-agent')\n            context.request_path = str(request.url.path)\n            context.request_method = request.method\n            context.session_id = getattr(request.state, 'session_id', None)\n            context.request_id = getattr(request.state, 'request_id', None)\n        \n        return context\n    \n    def _extract_request_context(self, request: Optional[Request]) -> Optional[Dict[str, Any]]:\n        """Extract request context for logging."""\n        \n        if not request:\n            return None\n        \n        return {\n            'client_ip': self._get_client_ip(request),\n            'user_agent': request.headers.get('user-agent'),\n            'request_path': str(request.url.path),\n            'request_method': request.method,\n            'session_id': getattr(request.state, 'session_id', None),\n            'request_id': getattr(request.state, 'request_id', None)\n        }\n    \n    def _get_client_ip(self, request: Request) -> str:\n        """Extract client IP from request."""\n        forwarded_for = request.headers.get('x-forwarded-for')\n        if forwarded_for:\n            return forwarded_for.split(',')[0].strip()\n        \n        real_ip = request.headers.get('x-real-ip')\n        if real_ip:\n            return real_ip\n        \n        return request.client.host if request.client else 'unknown'\n    \n    async def _authorize_with_circuit_breaker(self, func: Callable, *args, **kwargs):\n        """Execute authorization function with circuit breaker protection."""\n        \n        # Determine circuit breaker based on function\n        if func.__name__ == '_perform_token_validation':\n            cb_name = 'token_validation'\n        elif func.__name__ in ['_check_generation_ownership', '_check_project_access']:\n            cb_name = 'database'\n        else:\n            cb_name = 'external_auth'\n        \n        cb = self.circuit_breaker_manager.get_circuit_breaker(cb_name)\n        return await cb.call(func, *args, **kwargs)\n    \n    async def _check_generation_ownership(\n        self,\n        user_id: uuid.UUID,\n        generation_id: uuid.UUID,\n        action: str\n    ) -> Dict[str, Any]:\n        """Check if user owns or has access to the generation."""\n        \n        # This would implement actual database lookup\n        # For now, simulating the check\n        \n        try:\n            from database import SupabaseClient\n            db_client = SupabaseClient()\n            \n            if not db_client.is_available():\n                raise DatabaseError("Database is not available")\n            \n            # Query generation ownership\n            result = db_client.service_client.table('generations').select('user_id, created_by').eq('id', str(generation_id)).execute()\n            \n            if not result.data:\n                raise GenerationAccessDeniedError(\n                    generation_id=str(generation_id),\n                    user_id=str(user_id),\n                    details={'reason': 'Generation not found'}\n                )\n            \n            generation_data = result.data[0]\n            owner_id = generation_data.get('user_id') or generation_data.get('created_by')\n            \n            if str(owner_id) != str(user_id):\n                # Log ownership verification\n                if self.config.enable_detailed_logging:\n                    await log_ownership_verification(\n                        str(user_id),\n                        str(generation_id),\n                        'generation',\n                        str(owner_id),\n                        False\n                    )\n                \n                raise GenerationAccessDeniedError(\n                    generation_id=str(generation_id),\n                    user_id=str(user_id),\n                    owner_id=str(owner_id),\n                    details={'reason': 'Ownership check failed'}\n                )\n            \n            # Log successful ownership verification\n            if self.config.enable_detailed_logging:\n                await log_ownership_verification(\n                    str(user_id),\n                    str(generation_id),\n                    'generation',\n                    str(owner_id),\n                    True\n                )\n            \n            return {\n                'authorized': True,\n                'owner_id': str(owner_id),\n                'resource_type': 'generation',\n                'action': action\n            }\n            \n        except Exception as e:\n            if isinstance(e, GenerationAccessDeniedError):\n                raise e\n            else:\n                logger.error(f"❌ [AUTH-SYSTEM] Generation ownership check failed: {e}")\n                raise GenerationAccessDeniedError(\n                    generation_id=str(generation_id),\n                    user_id=str(user_id),\n                    details={'error': str(e), 'check_type': 'database_error'}\n                )\n    \n    async def _check_project_access(\n        self,\n        user_id: uuid.UUID,\n        project_id: uuid.UUID,\n        action: str\n    ) -> Dict[str, Any]:\n        """Check if user has access to the project."""\n        \n        try:\n            from database import SupabaseClient\n            db_client = SupabaseClient()\n            \n            if not db_client.is_available():\n                raise DatabaseError("Database is not available")\n            \n            # Check project membership or ownership\n            project_result = db_client.service_client.table('projects').select('user_id, team_id').eq('id', str(project_id)).execute()\n            \n            if not project_result.data:\n                raise ProjectAccessDeniedError(\n                    project_id=str(project_id),\n                    user_id=str(user_id),\n                    details={'reason': 'Project not found'}\n                )\n            \n            project_data = project_result.data[0]\n            project_owner = project_data.get('user_id')\n            team_id = project_data.get('team_id')\n            \n            # Check if user is project owner\n            if str(project_owner) == str(user_id):\n                return {\n                    'authorized': True,\n                    'access_type': 'owner',\n                    'project_id': str(project_id)\n                }\n            \n            # Check team membership if project has a team\n            if team_id:\n                team_result = db_client.service_client.table('team_members').select('user_id').eq('team_id', str(team_id)).eq('user_id', str(user_id)).execute()\n                \n                if team_result.data:\n                    return {\n                        'authorized': True,\n                        'access_type': 'team_member',\n                        'project_id': str(project_id),\n                        'team_id': str(team_id)\n                    }\n            \n            # No access found\n            raise ProjectAccessDeniedError(\n                project_id=str(project_id),\n                user_id=str(user_id),\n                details={'reason': 'No access permission found'}\n            )\n            \n        except Exception as e:\n            if isinstance(e, ProjectAccessDeniedError):\n                raise e\n            else:\n                logger.error(f"❌ [AUTH-SYSTEM] Project access check failed: {e}")\n                raise ProjectAccessDeniedError(\n                    project_id=str(project_id),\n                    user_id=str(user_id),\n                    details={'error': str(e), 'check_type': 'database_error'}\n                )\n    \n    async def _perform_token_validation(\n        self,\n        token: str,\n        token_type: str\n    ) -> Dict[str, Any]:\n        """Perform token validation with comprehensive error handling."""\n        \n        try:\n            # Import auth middleware for token validation\n            from middleware.auth import AuthMiddleware\n            \n            # Create temporary middleware instance for validation\n            auth_middleware = AuthMiddleware(app=None)\n            user = await auth_middleware._verify_token(token)\n            \n            return {\n                'valid': True,\n                'user_id': str(user.id),\n                'email': user.email,\n                'role': user.role,\n                'token_type': token_type\n            }\n            \n        except HTTPException as e:\n            if e.status_code == 401:\n                raise TokenValidationError(\n                    f"Token validation failed: {e.detail}",\n                    token_type=token_type,\n                    validation_failure_reason=str(e.detail)\n                )\n            else:\n                raise e\n        except Exception as e:\n            logger.error(f"❌ [AUTH-SYSTEM] Token validation error: {e}")\n            raise TokenValidationError(\n                f"Token validation failed: {str(e)}",\n                token_type=token_type,\n                validation_failure_reason=str(e)\n            )\n    \n    async def _update_system_metrics(self, success: bool, processing_time_ms: float):\n        """Update system-level metrics."""\n        \n        self.system_metrics['total_requests'] += 1\n        \n        if success:\n            self.system_metrics['successful_requests'] += 1\n        else:\n            self.system_metrics['failed_requests'] += 1\n        \n        # Update average response time\n        total_requests = self.system_metrics['total_requests']\n        current_avg = self.system_metrics['average_response_time']\n        self.system_metrics['average_response_time'] = (\n            (current_avg * (total_requests - 1) + processing_time_ms) / total_requests\n        )\n        \n        # Update error rate\n        self.system_metrics['error_rate'] = (\n            self.system_metrics['failed_requests'] / total_requests\n        ) * 100\n        \n        # Log slow operations\n        if (self.config.enable_performance_monitoring and \n            processing_time_ms > self.config.slow_operation_threshold_ms):\n            \n            logger.warning(\n                f"🐌 [AUTH-SYSTEM] Slow authorization operation: {processing_time_ms:.2f}ms"\n            )\n    \n    # Fallback functions for circuit breakers\n    \n    async def _database_fallback(self, *args, **kwargs):\n        """Fallback for database operations."""\n        logger.warning("🔄 [AUTH-SYSTEM] Using database fallback - denying access for security")\n        return None  # Conservative fallback\n    \n    async def _external_auth_fallback(self, *args, **kwargs):\n        """Fallback for external auth operations."""\n        logger.warning("🔄 [AUTH-SYSTEM] Using external auth fallback - denying access")\n        return False  # Conservative fallback\n    \n    async def _token_validation_fallback(self, *args, **kwargs):\n        """Fallback for token validation."""\n        logger.warning("🔄 [AUTH-SYSTEM] Using token validation fallback - denying access")\n        return False  # Conservative fallback for security\n\n\n# Global authorization system instance\nauth_system = UUIDAuthorizationSystem()\n\n\n# Convenience functions for easy integration\n\nasync def authorize_generation_access(\n    user_id: str,\n    generation_id: str,\n    action: str = "read",\n    request: Optional[Request] = None\n) -> Dict[str, Any]:\n    """Convenience function to authorize generation access."""\n    return await auth_system.authorize_generation_access(user_id, generation_id, action, request)\n\n\nasync def authorize_project_access(\n    user_id: str,\n    project_id: str,\n    action: str = "read",\n    request: Optional[Request] = None\n) -> Dict[str, Any]:\n    """Convenience function to authorize project access."""\n    return await auth_system.authorize_project_access(user_id, project_id, action, request)\n\n\nasync def validate_auth_token(\n    token: str,\n    token_type: str = "access",\n    request: Optional[Request] = None\n) -> Dict[str, Any]:\n    """Convenience function to validate authentication token."""\n    return await auth_system.validate_token(token, token_type, request)\n\n\nasync def handle_auth_error(\n    error: Union[Exception, HTTPException],\n    user_id: Optional[str] = None,\n    resource_id: Optional[str] = None,\n    resource_type: Optional[str] = None,\n    request: Optional[Request] = None\n) -> JSONResponse:\n    """Convenience function to handle authorization errors."""\n    return await auth_system.handle_authorization_error(\n        error, user_id, resource_id, resource_type, request\n    )\n\n\nasync def get_auth_system_health() -> Dict[str, Any]:\n    """Get the health status of the authorization system."""\n    return await auth_system.check_system_health()\n\n\nasync def get_auth_system_metrics() -> Dict[str, Any]:\n    """Get comprehensive metrics from the authorization system."""\n    return await auth_system.get_system_metrics()\n\n\n@asynccontextmanager\nasync def auth_context(request: Optional[Request] = None):\n    """Context manager for authorization operations with automatic error handling."""\n    \n    correlation_id = str(uuid.uuid4())\n    start_time = datetime.now(timezone.utc)\n    \n    try:\n        yield auth_system\n    except Exception as e:\n        # Log the error in context\n        processing_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000\n        \n        logger.error(\n            f"❌ [AUTH-CONTEXT] Authorization context error: {e}",\n            extra={\n                'correlation_id': correlation_id,\n                'processing_time_ms': processing_time,\n                'error_type': type(e).__name__\n            }\n        )\n        \n        raise e