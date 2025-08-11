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
        
    except GenerationAccessDeniedError as e:\n        # Handle generation-specific access denied errors\n        logger.warning(\n            f"🚫 [API] Generation access denied for user {current_user.id}: {e.message}",\n            extra={\n                'generation_id': generation_id,\n                'error_code': e.error_code,\n                'correlation_id': e.correlation_id\n            }\n        )\n        \n        return await handle_auth_error(\n            e, \n            user_id=str(current_user.id), \n            resource_id=generation_id, \n            resource_type="generation",\n            request=request\n        )\n    \n    except CircuitBreakerError as e:\n        # Handle circuit breaker errors\n        logger.error(\n            f"🔥 [API] Circuit breaker error for generation access: {e}",\n            extra={\n                'generation_id': generation_id,\n                'circuit_name': e.circuit_name,\n                'circuit_state': e.state.value\n            }\n        )\n        \n        return JSONResponse(\n            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,\n            content={\n                'error': True,\n                'message': 'Service temporarily unavailable. Please try again later.',\n                'error_type': 'circuit_breaker',\n                'correlation_id': getattr(request.state, 'request_id', 'unknown')\n            }\n        )\n    \n    except Exception as e:\n        # Handle unexpected errors\n        logger.error(\n            f"❌ [API] Unexpected error in generation access: {e}",\n            extra={\n                'generation_id': generation_id,\n                'user_id': str(current_user.id),\n                'error_type': type(e).__name__\n            }\n        )\n        \n        return await handle_auth_error(\n            e,\n            user_id=str(current_user.id),\n            resource_id=generation_id,\n            resource_type="generation",\n            request=request\n        )\n\n\n@auth_example_router.get("/project/{project_id}/generations")\nasync def get_project_generations_with_auth(\n    project_id: str,\n    request: Request,\n    current_user: UserResponse = Depends(get_current_user)\n):\n    """\n    Example endpoint showing project access authorization.\n    """\n    try:\n        # Authorize project access first\n        project_auth = await authorize_project_access(\n            user_id=str(current_user.id),\n            project_id=project_id,\n            action="read",\n            request=request\n        )\n        \n        # Proceed with business logic\n        project_data = {\n            'project_id': project_id,\n            'user_id': str(current_user.id),\n            'generations': [],  # Would fetch actual generations\n            'auth_info': project_auth\n        }\n        \n        return JSONResponse(\n            status_code=status.HTTP_200_OK,\n            content={\n                'success': True,\n                'data': project_data,\n                'authorization': project_auth\n            }\n        )\n        \n    except ProjectAccessDeniedError as e:\n        return await handle_auth_error(\n            e,\n            user_id=str(current_user.id),\n            resource_id=project_id,\n            resource_type="project",\n            request=request\n        )\n    \n    except Exception as e:\n        return await handle_auth_error(\n            e,\n            user_id=str(current_user.id),\n            resource_id=project_id,\n            resource_type="project",\n            request=request\n        )\n\n\n@auth_example_router.post("/token/validate")\nasync def validate_token_endpoint(\n    request: Request,\n    token: str,\n    token_type: str = "access"\n):\n    """\n    Example endpoint showing token validation.\n    """\n    try:\n        validation_result = await validate_auth_token(\n            token=token,\n            token_type=token_type,\n            request=request\n        )\n        \n        return JSONResponse(\n            status_code=status.HTTP_200_OK,\n            content={\n                'success': True,\n                'valid': validation_result.get('valid', False),\n                'user_info': {\n                    'user_id': validation_result.get('user_id'),\n                    'email': validation_result.get('email'),\n                    'role': validation_result.get('role')\n                } if validation_result.get('valid') else None\n            }\n        )\n        \n    except TokenValidationError as e:\n        return await handle_auth_error(\n            e,\n            request=request\n        )\n    \n    except Exception as e:\n        return await handle_auth_error(\n            e,\n            request=request\n        )\n\n\n@auth_example_router.get("/system/health")\nasync def get_auth_system_health_endpoint():\n    """\n    Example endpoint showing system health monitoring.\n    """\n    try:\n        health_status = await auth_system.check_system_health()\n        \n        status_code = status.HTTP_200_OK if health_status['healthy'] else status.HTTP_503_SERVICE_UNAVAILABLE\n        \n        return JSONResponse(\n            status_code=status_code,\n            content={\n                'success': health_status['healthy'],\n                'health': health_status\n            }\n        )\n        \n    except Exception as e:\n        logger.error(f"❌ [API] Error checking auth system health: {e}")\n        return JSONResponse(\n            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,\n            content={\n                'success': False,\n                'error': 'Failed to check system health',\n                'message': str(e)\n            }\n        )\n\n\n@auth_example_router.get("/system/metrics")\nasync def get_auth_system_metrics_endpoint():\n    """\n    Example endpoint showing system metrics.\n    """\n    try:\n        metrics = await auth_system.get_system_metrics()\n        \n        return JSONResponse(\n            status_code=status.HTTP_200_OK,\n            content={\n                'success': True,\n                'metrics': metrics\n            }\n        )\n        \n    except Exception as e:\n        logger.error(f"❌ [API] Error getting auth system metrics: {e}")\n        return JSONResponse(\n            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,\n            content={\n                'success': False,\n                'error': 'Failed to get system metrics',\n                'message': str(e)\n            }\n        )\n\n\n@auth_example_router.post("/system/reset")\nasync def reset_auth_system_endpoint(\n    request: Request,\n    current_user: UserResponse = Depends(get_current_user)\n):\n    """\n    Example endpoint showing system reset (admin only).\n    """\n    try:\n        # Check if user is admin\n        if current_user.role != 'admin':\n            await log_security_incident(\n                user_id=str(current_user.id),\n                violation_type='unauthorized_admin_access',\n                details={\n                    'attempted_endpoint': '/system/reset',\n                    'user_role': current_user.role\n                },\n                threat_level='medium',\n                request_context={\n                    'client_ip': request.client.host,\n                    'user_agent': request.headers.get('user-agent')\n                }\n            )\n            \n            raise HTTPException(\n                status_code=status.HTTP_403_FORBIDDEN,\n                detail="Admin access required"\n            )\n        \n        await auth_system.reset_system_state()\n        \n        logger.info(\n            f"🔄 [API] Auth system reset by admin user {current_user.id}",\n            extra={\n                'admin_user_id': str(current_user.id),\n                'admin_email': current_user.email\n            }\n        )\n        \n        return JSONResponse(\n            status_code=status.HTTP_200_OK,\n            content={\n                'success': True,\n                'message': 'Authorization system reset successfully',\n                'timestamp': auth_system.system_metrics\n            }\n        )\n        \n    except HTTPException:\n        raise\n    except Exception as e:\n        return await handle_auth_error(\n            e,\n            user_id=str(current_user.id),\n            request=request\n        )\n\n\n# Middleware integration example\nclass AuthSystemMiddleware:\n    """\n    Example middleware showing how to integrate the auth system.\n    """\n    \n    def __init__(self, app):\n        self.app = app\n    \n    async def __call__(self, scope, receive, send):\n        if scope["type"] == "http":\n            # Add request ID for correlation\n            import uuid\n            request_id = str(uuid.uuid4())\n            scope["state"] = scope.get("state", {})\n            scope["state"]["request_id"] = request_id\n            \n            # Add custom headers\n            async def send_with_headers(message):\n                if message["type"] == "http.response.start":\n                    headers = list(message.get("headers", []))\n                    headers.append([b"x-request-id", request_id.encode()])\n                    headers.append([b"x-auth-system", b"velro-uuid-auth-v1"])\n                    message["headers"] = headers\n                await send(message)\n            \n            await self.app(scope, receive, send_with_headers)\n        else:\n            await self.app(scope, receive, send)\n\n\n# Dependency injection examples\n\ndef require_generation_access(generation_id: str):\n    """\n    Dependency factory for requiring generation access.\n    """\n    async def check_access(\n        request: Request,\n        current_user: UserResponse = Depends(get_current_user)\n    ):\n        try:\n            auth_result = await authorize_generation_access(\n                user_id=str(current_user.id),\n                generation_id=generation_id,\n                action="read",\n                request=request\n            )\n            return auth_result\n        except Exception as e:\n            # Convert to HTTPException for FastAPI\n            if isinstance(e, GenerationAccessDeniedError):\n                raise HTTPException(\n                    status_code=status.HTTP_403_FORBIDDEN,\n                    detail=e.user_message\n                )\n            else:\n                raise HTTPException(\n                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,\n                    detail="Authorization check failed"\n                )\n    \n    return check_access\n\n\ndef require_project_access(project_id: str, action: str = "read"):\n    """\n    Dependency factory for requiring project access.\n    """\n    async def check_access(\n        request: Request,\n        current_user: UserResponse = Depends(get_current_user)\n    ):\n        try:\n            auth_result = await authorize_project_access(\n                user_id=str(current_user.id),\n                project_id=project_id,\n                action=action,\n                request=request\n            )\n            return auth_result\n        except Exception as e:\n            if isinstance(e, ProjectAccessDeniedError):\n                raise HTTPException(\n                    status_code=status.HTTP_403_FORBIDDEN,\n                    detail=e.user_message\n                )\n            else:\n                raise HTTPException(\n                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,\n                    detail="Authorization check failed"\n                )\n    \n    return check_access\n\n\n# Example usage with dependency\n@auth_example_router.get("/generation/{generation_id}/secure")\nasync def get_generation_with_dependency(\n    generation_id: str,\n    auth_result = Depends(require_generation_access)\n):\n    """\n    Example showing dependency-based authorization.\n    """\n    return {\n        'success': True,\n        'generation_id': generation_id,\n        'authorized': True,\n        'auth_info': auth_result\n    }\n\n\n# Configuration examples\ndef create_production_auth_config() -> AuthSystemConfig:\n    """\n    Create production-ready auth system configuration.\n    """\n    return AuthSystemConfig(\n        enable_circuit_breakers=True,\n        enable_detailed_logging=True,\n        enable_security_monitoring=True,\n        enable_performance_monitoring=True,\n        enable_fallback_strategies=True,\n        database_timeout=5.0,  # Shorter timeout for production\n        external_auth_timeout=10.0,\n        token_validation_timeout=3.0,\n        max_failed_attempts_per_minute=20,  # Higher threshold for production\n        max_failed_attempts_per_hour=200,\n        security_violation_threshold=10,\n        slow_operation_threshold_ms=500.0,  # Lower threshold for production\n        cache_ttl_seconds=600,\n        metrics_retention_hours=48\n    )\n\n\ndef create_development_auth_config() -> AuthSystemConfig:\n    """\n    Create development-friendly auth system configuration.\n    """\n    return AuthSystemConfig(\n        enable_circuit_breakers=False,  # Disabled for easier debugging\n        enable_detailed_logging=True,\n        enable_security_monitoring=False,  # Less strict in development\n        enable_performance_monitoring=True,\n        enable_fallback_strategies=False,\n        database_timeout=30.0,  # Longer timeout for debugging\n        external_auth_timeout=30.0,\n        token_validation_timeout=10.0,\n        max_failed_attempts_per_minute=100,  # More lenient\n        max_failed_attempts_per_hour=1000,\n        security_violation_threshold=50,\n        slow_operation_threshold_ms=2000.0,  # Higher threshold\n        cache_ttl_seconds=60,  # Shorter cache for development\n        metrics_retention_hours=24\n    )\n\n\n# Integration with FastAPI app\ndef setup_auth_system_for_app(app, config: Optional[AuthSystemConfig] = None):\n    """\n    Setup the authorization system for a FastAPI app.\n    """\n    # Configure the global auth system\n    if config:\n        global auth_system\n        auth_system = UUIDAuthorizationSystem(config)\n    \n    # Add middleware\n    app.add_middleware(AuthSystemMiddleware)\n    \n    # Add exception handlers\n    @app.exception_handler(GenerationAccessDeniedError)\n    async def generation_access_denied_handler(request: Request, exc: GenerationAccessDeniedError):\n        return await handle_auth_error(\n            exc,\n            resource_id=exc.generation_id,\n            resource_type="generation",\n            request=request\n        )\n    \n    @app.exception_handler(ProjectAccessDeniedError)\n    async def project_access_denied_handler(request: Request, exc: ProjectAccessDeniedError):\n        return await handle_auth_error(\n            exc,\n            resource_id=exc.project_id,\n            resource_type="project",\n            request=request\n        )\n    \n    @app.exception_handler(UUIDAuthorizationError)\n    async def uuid_auth_error_handler(request: Request, exc: UUIDAuthorizationError):\n        return await handle_auth_error(\n            exc,\n            resource_id=exc.uuid_value,\n            resource_type=exc.uuid_type,\n            request=request\n        )\n    \n    @app.exception_handler(CircuitBreakerError)\n    async def circuit_breaker_error_handler(request: Request, exc: CircuitBreakerError):\n        return JSONResponse(\n            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,\n            content={\n                'error': True,\n                'message': 'Service temporarily unavailable due to system protection.',\n                'error_type': 'circuit_breaker',\n                'circuit_name': exc.circuit_name,\n                'retry_after': 60\n            }\n        )\n    \n    # Add startup event to initialize auth system\n    @app.on_event("startup")\n    async def startup_auth_system():\n        logger.info("🚀 [STARTUP] Initializing authorization system")\n        health = await auth_system.check_system_health()\n        logger.info(f"✅ [STARTUP] Auth system health: {health['healthy']}")\n    \n    # Add shutdown event to cleanup\n    @app.on_event("shutdown")\n    async def shutdown_auth_system():\n        logger.info("🔄 [SHUTDOWN] Cleaning up authorization system")\n        await auth_system.reset_system_state()\n        logger.info("✅ [SHUTDOWN] Auth system cleanup complete")\n    \n    logger.info("✅ [SETUP] Authorization system setup complete")