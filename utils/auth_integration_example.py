"""
High-Performance Authorization Integration with L1 Memory Cache

This module demonstrates how to integrate the OptimizedCacheManager
with existing Velro authorization endpoints to achieve <5ms cache hits
and >95% cache hit rates.

Example Usage:
    from utils.auth_integration_example import OptimizedAuthMiddleware
    
    # In FastAPI router
    @router.get("/generations/{generation_id}/media")
    async def get_generation_media(
        generation_id: UUID,
        current_user: User = Depends(get_current_user),
        auth_middleware: OptimizedAuthMiddleware = Depends(get_optimized_auth)
    ):
        # This will use cached authorization if available
        permissions = await auth_middleware.check_generation_access(
            generation_id, current_user.id
        )
        if not permissions.granted:
            raise HTTPException(status_code=403, detail="Access denied")
        
        return {"media_urls": permissions.media_urls}
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID
from functools import wraps
from contextlib import asynccontextmanager

from fastapi import APIRouter, HTTPException, Request, Depends, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer

from models.user import UserResponse
from middleware.auth import get_current_user
from utils.optimized_cache_manager import (
    OptimizedCacheManager, 
    OptimizedCacheConfig, 
    get_cache_manager
)
from models.authorization import (
    ValidationContext, SecurityLevel, TeamRole, AccessType,
    AuthorizationMethod, GenerationPermissions,
    VelroAuthorizationError, GenerationAccessDeniedError
)
from services.authorization_service import authorization_service
from utils.enhanced_uuid_utils import secure_uuid_validator
from utils.exceptions import (
    GenerationAccessDeniedError, ProjectAccessDeniedError, 
    UUIDAuthorizationError, TokenValidationError
)
from utils.auth_logger import log_security_incident
from utils.circuit_breaker import CircuitBreakerError

logger = logging.getLogger(__name__)


class OptimizedAuthMiddleware:
    """
    High-performance authorization middleware with L1 memory caching.
    
    Provides drop-in replacements for authorization checks with intelligent
    caching to achieve sub-5ms response times for repeated requests.
    """
    
    def __init__(self, cache_manager: Optional[OptimizedCacheManager] = None):
        self.cache_manager = cache_manager or get_cache_manager()
        self.fallback_auth_service = authorization_service
        
        # Performance tracking
        self.performance_stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'average_response_time_ms': 0.0,
            'fastest_response_ms': float('inf'),
            'slowest_response_ms': 0.0
        }
    
    async def check_generation_access_cached(
        self,
        generation_id: UUID,
        user_id: UUID,
        auth_token: str,
        required_access: AccessType = AccessType.READ,
        client_ip: Optional[str] = None,
        force_refresh: bool = False
    ) -> GenerationPermissions:
        """
        High-performance generation access check with caching.
        
        Returns cached permissions in <5ms if available, otherwise performs
        full authorization check and caches the result.
        """
        start_time = time.time()
        self.performance_stats['total_requests'] += 1
        
        try:
            # Step 1: Try cache first (unless forced refresh)
            if not force_refresh:
                cached_permissions, cache_hit = self.cache_manager.get_generation_access(
                    str(generation_id), str(user_id)
                )
                
                if cache_hit and cached_permissions:
                    # Validate cached permissions are still valid
                    if self._is_cached_permission_valid(cached_permissions):
                        response_time_ms = (time.time() - start_time) * 1000
                        self._update_performance_stats(response_time_ms, cache_hit=True)
                        
                        logger.debug(
                            f"⚡ [CACHE-HIT] Generation access {generation_id} for user {user_id} "
                            f"returned in {response_time_ms:.2f}ms"
                        )
                        
                        return self._deserialize_cached_permissions(
                            cached_permissions, generation_id, user_id
                        )
            
            # Step 2: Cache miss - perform full authorization
            logger.debug(f"🔍 [CACHE-MISS] Full authorization check for {generation_id}")
            
            permissions = await self.fallback_auth_service.validate_generation_media_access(
                generation_id=generation_id,
                user_id=user_id,
                auth_token=auth_token,
                client_ip=client_ip,
                expires_in=3600
            )
            
            # Step 3: Cache successful authorization
            if permissions.granted:
                await self._cache_generation_permissions(
                    generation_id, user_id, permissions
                )
            
            response_time_ms = (time.time() - start_time) * 1000
            self._update_performance_stats(response_time_ms, cache_hit=False)
            
            return permissions
            
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            self._update_performance_stats(response_time_ms, cache_hit=False)
            
            logger.error(f"❌ [AUTH-MIDDLEWARE] Authorization failed: {e}")
            raise
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for monitoring."""
        cache_stats = self.cache_manager.get_stats()
        
        return {
            # Middleware performance
            'middleware_stats': self.performance_stats.copy(),
            
            # Cache performance
            'cache_stats': cache_stats,
            
            # Combined metrics
            'combined_hit_rate_percent': (
                self.performance_stats['cache_hits'] / 
                max(1, self.performance_stats['total_requests'])
            ) * 100,
            
            # Performance targets
            'performance_targets': {
                'target_access_time_ms': cache_stats['target_access_time_ms'],
                'target_hit_rate_percent': cache_stats['target_hit_rate_percent'],
                'meeting_access_time_target': (
                    self.performance_stats['average_response_time_ms'] <= 
                    cache_stats['target_access_time_ms']
                ),
                'meeting_hit_rate_target': (
                    cache_stats['hit_rate_percent'] >= 
                    cache_stats['target_hit_rate_percent']
                )
            },
            
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def _cache_generation_permissions(
        self, generation_id: UUID, user_id: UUID, permissions: GenerationPermissions
    ) -> bool:
        """Cache generation permissions for future requests."""
        try:
            cached_data = {
                'granted': permissions.granted,
                'access_method': permissions.access_method.value,
                'can_view': permissions.can_view,
                'can_edit': permissions.can_edit,
                'can_delete': permissions.can_delete,
                'can_download': permissions.can_download,
                'can_share': permissions.can_share,
                'security_level': permissions.security_level.value,
                'team_context': str(permissions.team_context) if permissions.team_context else None,
                'project_context': str(permissions.project_context) if permissions.project_context else None,
                'media_urls': permissions.media_urls or [],
                'expires_at': permissions.expires_at.isoformat() if permissions.expires_at else None,
                'cached_at': datetime.utcnow().isoformat()
            }
            
            return self.cache_manager.set_generation_access(
                str(generation_id),
                str(user_id),
                cached_data,
                ttl=self.cache_manager.config.auth_ttl_seconds
            )
            
        except Exception as e:
            logger.error(f"❌ [CACHE-STORE] Failed to cache permissions: {e}")
            return False
    
    def _is_cached_permission_valid(self, cached_data: Dict[str, Any]) -> bool:
        """Validate cached permission data is still current."""
        try:
            # Check expiration
            expires_at_str = cached_data.get('expires_at')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                if datetime.utcnow() >= expires_at:
                    return False
            
            # Check required fields
            required_fields = ['granted', 'access_method', 'can_view']
            return all(field in cached_data for field in required_fields)
            
        except Exception:
            return False
    
    def _deserialize_cached_permissions(
        self, cached_data: Dict[str, Any], generation_id: UUID, user_id: UUID
    ) -> GenerationPermissions:
        """Convert cached data back to GenerationPermissions object."""
        try:
            expires_at = None
            expires_at_str = cached_data.get('expires_at')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            
            return GenerationPermissions(
                generation_id=generation_id,
                user_id=user_id,
                granted=cached_data['granted'],
                access_method=AuthorizationMethod(cached_data['access_method']),
                can_view=cached_data['can_view'],
                can_edit=cached_data['can_edit'],
                can_delete=cached_data['can_delete'],
                can_download=cached_data['can_download'],
                can_share=cached_data['can_share'],
                can_create_child=cached_data.get('can_create_child', False),
                team_context=UUID(cached_data['team_context']) if cached_data.get('team_context') else None,
                project_context=UUID(cached_data['project_context']) if cached_data.get('project_context') else None,
                security_level=SecurityLevel(cached_data['security_level']),
                expires_at=expires_at,
                media_urls=cached_data.get('media_urls', []),
                audit_trail=[{
                    'method': 'cache_hit',
                    'timestamp': datetime.utcnow().isoformat(),
                    'cached_at': cached_data.get('cached_at')
                }]
            )
            
        except Exception as e:
            logger.error(f"❌ [DESERIALIZE] Failed to deserialize cached permissions: {e}")
            raise
    
    def _update_performance_stats(self, response_time_ms: float, cache_hit: bool) -> None:
        """Update performance statistics."""
        if cache_hit:
            self.performance_stats['cache_hits'] += 1
        else:
            self.performance_stats['cache_misses'] += 1
        
        # Update response time statistics
        self.performance_stats['fastest_response_ms'] = min(
            self.performance_stats['fastest_response_ms'], response_time_ms
        )
        self.performance_stats['slowest_response_ms'] = max(
            self.performance_stats['slowest_response_ms'], response_time_ms
        )
        
        # Update average (exponential moving average)
        if self.performance_stats['average_response_time_ms'] == 0:
            self.performance_stats['average_response_time_ms'] = response_time_ms
        else:
            alpha = 0.1  # Weight for new values
            self.performance_stats['average_response_time_ms'] = (
                alpha * response_time_ms + 
                (1 - alpha) * self.performance_stats['average_response_time_ms']
            )


# Dependency for FastAPI integration
async def get_optimized_auth_middleware() -> OptimizedAuthMiddleware:
    """FastAPI dependency for optimized authorization middleware."""
    return OptimizedAuthMiddleware()


# Example router showing integration patterns
auth_example_router = APIRouter(prefix="/api/v1/examples", tags=["optimized-auth-examples"])


@auth_example_router.get("/generations/{generation_id}/media-optimized")
async def get_generation_media_optimized(
    generation_id: UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    auth_middleware: OptimizedAuthMiddleware = Depends(get_optimized_auth_middleware)
):
    """
    Example endpoint with optimized authorization caching.
    Demonstrates <5ms cache hit performance for repeated requests.
    """
    try:
        # Extract auth token
        auth_token = request.headers.get("Authorization", "").replace("Bearer ", "")
        
        # High-performance authorization check with caching
        permissions = await auth_middleware.check_generation_access_cached(
            generation_id=generation_id,
            user_id=current_user.id,
            auth_token=auth_token,
            required_access=AccessType.READ,
            client_ip=request.client.host
        )
        
        if not permissions.granted:
            raise HTTPException(status_code=403, detail="Access denied to this generation")
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "generation_id": str(generation_id),
                "user_id": str(current_user.id),
                "permissions": {
                    "can_view": permissions.can_view,
                    "can_edit": permissions.can_edit,
                    "can_delete": permissions.can_delete,
                    "can_download": permissions.can_download,
                    "can_share": permissions.can_share
                },
                "media_urls": permissions.media_urls,
                "access_method": permissions.access_method.value,
                "expires_at": permissions.expires_at.isoformat() if permissions.expires_at else None,
                "cache_info": {
                    "cached_response": len(permissions.audit_trail) > 0 and 
                                     permissions.audit_trail[0].get("method") == "cache_hit"
                }
            }
        )
        
    except GenerationAccessDeniedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        logger.error(f"❌ [OPTIMIZED-ENDPOINT] Error: {e}")
        raise HTTPException(status_code=500, detail="Authorization service error")


@auth_example_router.get("/auth/performance-stats")
async def get_auth_performance_stats(
    auth_middleware: OptimizedAuthMiddleware = Depends(get_optimized_auth_middleware)
):
    """Get authorization performance statistics and cache metrics."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content=auth_middleware.get_performance_stats()
    )


@auth_example_router.post("/auth/cache/invalidate/user/{user_id}")
async def invalidate_user_cache(
    user_id: UUID,
    auth_middleware: OptimizedAuthMiddleware = Depends(get_optimized_auth_middleware),
    current_user: UserResponse = Depends(get_current_user)
):
    """Invalidate cache for a specific user (admin or self only)."""
    # Check if user can invalidate this cache
    if current_user.id != user_id and not hasattr(current_user, 'is_admin'):
        raise HTTPException(status_code=403, detail="Can only invalidate your own cache")
    
    try:
        invalidated_count = auth_middleware.cache_manager.invalidate_user_data(str(user_id))
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "user_id": str(user_id),
                "invalidated_entries": invalidated_count,
                "message": f"Invalidated {invalidated_count} cached authorization entries"
            }
        )
        
    except Exception as e:
        logger.error(f"❌ [CACHE-INVALIDATE] Error: {e}")
        raise HTTPException(status_code=500, detail="Cache invalidation failed")


# Legacy endpoint for comparison
@auth_example_router.get("/generation/{generation_id}")
async def get_generation_with_auth(
    generation_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Example endpoint showing comprehensive generation access authorization.
    """
    try:
        # Use the auth system to authorize access
        auth_result = await authorize_generation_access(
            user_id=str(current_user.id),
            generation_id=generation_id,
            action="read",
            request=request
        )
        
        # If we get here, access is authorized
        logger.info(
            f"✅ [API] Generation access authorized for user {current_user.id}",
            extra={
                'generation_id': generation_id,
                'processing_time_ms': auth_result.get('processing_time_ms'),
                'correlation_id': getattr(request.state, 'request_id', 'unknown')
            }
        )
        
        # Proceed with actual generation retrieval
        # This would be your actual business logic
        generation_data = {
            'id': generation_id,
            'user_id': str(current_user.id),
            'title': 'Example Generation',
            'status': 'completed',
            'auth_info': auth_result
        }
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'success': True,
                'data': generation_data,
                'authorization': auth_result
            }
        )
        
    except GenerationAccessDeniedError as e:
        # Handle generation-specific access denied errors
        logger.warning(
            f"🚫 [API] Generation access denied for user {current_user.id}: {e.message}",
            extra={
                'generation_id': generation_id,
                'error_code': e.error_code,
                'correlation_id': e.correlation_id
            }
        )
        
        return await handle_auth_error(
            e, 
            user_id=str(current_user.id), 
            resource_id=generation_id, 
            resource_type="generation",
            request=request
        )
    
    except CircuitBreakerError as e:
        # Handle circuit breaker errors
        logger.error(
            f"🔥 [API] Circuit breaker error for generation access: {e}",
            extra={
                'generation_id': generation_id,
                'circuit_name': e.circuit_name,
                'circuit_state': e.state.value
            }
        )
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                'error': True,
                'message': 'Service temporarily unavailable. Please try again later.',
                'error_type': 'circuit_breaker',
                'correlation_id': getattr(request.state, 'request_id', 'unknown')
            }
        )
    
    except Exception as e:
        # Handle unexpected errors
        logger.error(
            f"❌ [API] Unexpected error in generation access: {e}",
            extra={
                'generation_id': generation_id,
                'user_id': str(current_user.id),
                'error_type': type(e).__name__
            }
        )
        
        return await handle_auth_error(
            e,
            user_id=str(current_user.id),
            resource_id=generation_id,
            resource_type="generation",
            request=request
        )


@auth_example_router.get("/project/{project_id}/generations")
async def get_project_generations_with_auth(
    project_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Example endpoint showing project access authorization.
    """
    try:
        # Authorize project access first
        project_auth = await authorize_project_access(
            user_id=str(current_user.id),
            project_id=project_id,
            action="read",
            request=request
        )
        
        # Proceed with business logic
        project_data = {
            'project_id': project_id,
            'user_id': str(current_user.id),
            'generations': [],  # Would fetch actual generations
            'auth_info': project_auth
        }
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'success': True,
                'data': project_data,
                'authorization': project_auth
            }
        )
        
    except ProjectAccessDeniedError as e:
        return await handle_auth_error(
            e,
            user_id=str(current_user.id),
            resource_id=project_id,
            resource_type="project",
            request=request
        )
    
    except Exception as e:
        return await handle_auth_error(
            e,
            user_id=str(current_user.id),
            resource_id=project_id,
            resource_type="project",
            request=request
        )


@auth_example_router.post("/token/validate")
async def validate_token_endpoint(
    request: Request,
    token: str,
    token_type: str = "access"
):
    """
    Example endpoint showing token validation.
    """
    try:
        validation_result = await validate_auth_token(
            token=token,
            token_type=token_type,
            request=request
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'success': True,
                'valid': validation_result.get('valid', False),
                'user_info': {
                    'user_id': validation_result.get('user_id'),
                    'email': validation_result.get('email'),
                    'role': validation_result.get('role')
                } if validation_result.get('valid') else None
            }
        )
        
    except TokenValidationError as e:
        return await handle_auth_error(
            e,
            request=request
        )
    
    except Exception as e:
        return await handle_auth_error(
            e,
            request=request
        )


@auth_example_router.get("/system/health")
async def get_auth_system_health_endpoint():
    """
    Example endpoint showing system health monitoring.
    """
    try:
        health_status = await auth_system.check_system_health()
        
        status_code = status.HTTP_200_OK if health_status['healthy'] else status.HTTP_503_SERVICE_UNAVAILABLE
        
        return JSONResponse(
            status_code=status_code,
            content={
                'success': health_status['healthy'],
                'health': health_status
            }
        )
        
    except Exception as e:
        logger.error(f"❌ [API] Error checking auth system health: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                'success': False,
                'error': 'Failed to check system health',
                'message': str(e)
            }
        )


@auth_example_router.get("/system/metrics")
async def get_auth_system_metrics_endpoint():
    """
    Example endpoint showing system metrics.
    """
    try:
        metrics = await auth_system.get_system_metrics()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'success': True,
                'metrics': metrics
            }
        )
        
    except Exception as e:
        logger.error(f"❌ [API] Error getting auth system metrics: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                'success': False,
                'error': 'Failed to get system metrics',
                'message': str(e)
            }
        )


@auth_example_router.post("/system/reset")
async def reset_auth_system_endpoint(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Example endpoint showing system reset (admin only).
    """
    try:
        # Check if user is admin
        if current_user.role != 'admin':
            await log_security_incident(
                user_id=str(current_user.id),
                violation_type='unauthorized_admin_access',
                details={
                    'attempted_endpoint': '/system/reset',
                    'user_role': current_user.role
                },
                threat_level='medium',
                request_context={
                    'client_ip': request.client.host,
                    'user_agent': request.headers.get('user-agent')
                }
            )
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        await auth_system.reset_system_state()
        
        logger.info(
            f"🔄 [API] Auth system reset by admin user {current_user.id}",
            extra={
                'admin_user_id': str(current_user.id),
                'admin_email': current_user.email
            }
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                'success': True,
                'message': 'Authorization system reset successfully',
                'timestamp': auth_system.system_metrics
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        return await handle_auth_error(
            e,
            user_id=str(current_user.id),
            request=request
        )


# Middleware integration example
class AuthSystemMiddleware:
    """
    Example middleware showing how to integrate the auth system.
    """
    
    def __init__(self, app):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            # Add request ID for correlation
            import uuid
            request_id = str(uuid.uuid4())
            scope["state"] = scope.get("state", {})
            scope["state"]["request_id"] = request_id
            
            # Add custom headers
            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append([b"x-request-id", request_id.encode()])
                    headers.append([b"x-auth-system", b"velro-uuid-auth-v1"])
                    message["headers"] = headers
                await send(message)
            
            await self.app(scope, receive, send_with_headers)
        else:
            await self.app(scope, receive, send)


# Dependency injection examples

def require_generation_access(generation_id: str):
    """
    Dependency factory for requiring generation access.
    """
    async def check_access(
        request: Request,
        current_user: UserResponse = Depends(get_current_user)
    ):
        try:
            auth_result = await authorize_generation_access(
                user_id=str(current_user.id),
                generation_id=generation_id,
                action="read",
                request=request
            )
            return auth_result
        except Exception as e:
            # Convert to HTTPException for FastAPI
            if isinstance(e, GenerationAccessDeniedError):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=e.user_message
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authorization check failed"
                )
    
    return check_access


def require_project_access(project_id: str, action: str = "read"):
    """
    Dependency factory for requiring project access.
    """
    async def check_access(
        request: Request,
        current_user: UserResponse = Depends(get_current_user)
    ):
        try:
            auth_result = await authorize_project_access(
                user_id=str(current_user.id),
                project_id=project_id,
                action=action,
                request=request
            )
            return auth_result
        except Exception as e:
            if isinstance(e, ProjectAccessDeniedError):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=e.user_message
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authorization check failed"
                )
    
    return check_access


# Example usage with dependency
@auth_example_router.get("/generation/{generation_id}/secure")
async def get_generation_with_dependency(
    generation_id: str,
    auth_result = Depends(require_generation_access)
):
    """
    Example showing dependency-based authorization.
    """
    return {
        'success': True,
        'generation_id': generation_id,
        'authorized': True,
        'auth_info': auth_result
    }


# Configuration examples
def create_production_auth_config() -> AuthSystemConfig:
    """
    Create production-ready auth system configuration.
    """
    return AuthSystemConfig(
        enable_circuit_breakers=True,
        enable_detailed_logging=True,
        enable_security_monitoring=True,
        enable_performance_monitoring=True,
        enable_fallback_strategies=True,
        database_timeout=5.0,  # Shorter timeout for production
        external_auth_timeout=10.0,
        token_validation_timeout=3.0,
        max_failed_attempts_per_minute=20,  # Higher threshold for production
        max_failed_attempts_per_hour=200,
        security_violation_threshold=10,
        slow_operation_threshold_ms=500.0,  # Lower threshold for production
        cache_ttl_seconds=600,
        metrics_retention_hours=48
    )


def create_development_auth_config() -> AuthSystemConfig:
    """
    Create development-friendly auth system configuration.
    """
    return AuthSystemConfig(
        enable_circuit_breakers=False,  # Disabled for easier debugging
        enable_detailed_logging=True,
        enable_security_monitoring=False,  # Less strict in development
        enable_performance_monitoring=True,
        enable_fallback_strategies=False,
        database_timeout=30.0,  # Longer timeout for debugging
        external_auth_timeout=30.0,
        token_validation_timeout=10.0,
        max_failed_attempts_per_minute=100,  # More lenient
        max_failed_attempts_per_hour=1000,
        security_violation_threshold=50,
        slow_operation_threshold_ms=2000.0,  # Higher threshold
        cache_ttl_seconds=60,  # Shorter cache for development
        metrics_retention_hours=24
    )


# Integration with FastAPI app
def setup_auth_system_for_app(app, config: Optional[AuthSystemConfig] = None):
    """
    Setup the authorization system for a FastAPI app.
    """
    # Configure the global auth system
    if config:
        global auth_system
        auth_system = UUIDAuthorizationSystem(config)
    
    # Add middleware
    app.add_middleware(AuthSystemMiddleware)
    
    # Add exception handlers
    @app.exception_handler(GenerationAccessDeniedError)
    async def generation_access_denied_handler(request: Request, exc: GenerationAccessDeniedError):
        return await handle_auth_error(
            exc,
            resource_id=exc.generation_id,
            resource_type="generation",
            request=request
        )
    
    @app.exception_handler(ProjectAccessDeniedError)
    async def project_access_denied_handler(request: Request, exc: ProjectAccessDeniedError):
        return await handle_auth_error(
            exc,
            resource_id=exc.project_id,
            resource_type="project",
            request=request
        )
    
    @app.exception_handler(UUIDAuthorizationError)
    async def uuid_auth_error_handler(request: Request, exc: UUIDAuthorizationError):
        return await handle_auth_error(
            exc,
            resource_id=exc.uuid_value,
            resource_type=exc.uuid_type,
            request=request
        )
    
    @app.exception_handler(CircuitBreakerError)
    async def circuit_breaker_error_handler(request: Request, exc: CircuitBreakerError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                'error': True,
                'message': 'Service temporarily unavailable due to system protection.',
                'error_type': 'circuit_breaker',
                'circuit_name': exc.circuit_name,
                'retry_after': 60
            }
        )
    
    # Add startup event to initialize auth system
    @app.on_event("startup")
    async def startup_auth_system():
        logger.info("🚀 [STARTUP] Initializing authorization system")
        health = await auth_system.check_system_health()
        logger.info(f"✅ [STARTUP] Auth system health: {health['healthy']}")
    
    # Add shutdown event to cleanup
    @app.on_event("shutdown")
    async def shutdown_auth_system():
        logger.info("🔄 [SHUTDOWN] Cleaning up authorization system")
        await auth_system.reset_system_state()
        logger.info("✅ [SHUTDOWN] Auth system cleanup complete")
    
    logger.info("✅ [SETUP] Authorization system setup complete")