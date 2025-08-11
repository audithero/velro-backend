"""
Enhanced Authorization Cache Service
Integrates multi-layer caching with authorization service for sub-100ms performance.

Features:
- L1/L2/L3 cache integration with authorization service
- Sub-75ms authorization response times
- >95% cache hit rate for authorization operations
- Intelligent cache warming for authorization patterns
- Cache invalidation on user/team/generation changes
- Performance monitoring and optimization
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, Optional, List, Tuple, Set
from datetime import datetime, timedelta
from uuid import UUID
from dataclasses import dataclass, asdict

from caching.multi_layer_cache_manager import (
    MultiLayerCacheManager, get_cache_manager, CacheLevel,
    get_cached_authorization, cache_authorization_result,
    invalidate_user_authorization_cache
)
from monitoring.cache_performance_monitor import (
    get_cache_performance_monitor, start_cache_monitoring
)
from monitoring.performance import performance_tracker, PerformanceTarget
from services.authorization_service import AuthorizationService
from models.authorization import (
    ValidationContext, AuthorizationResult, GenerationPermissions,
    TeamAccessResult, AuthorizationMethod, TeamRole, ProjectVisibility
)
from utils.enhanced_uuid_utils import secure_uuid_validator
from database import get_database

logger = logging.getLogger(__name__)


@dataclass
class CachedAuthorizationResult:
    """Cached authorization result with metadata."""
    authorized: bool
    method: str
    role: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    cached_at: str = None
    expires_at: str = None
    cache_level: Optional[str] = None
    response_time_ms: Optional[float] = None
    
    def to_generation_permissions(self) -> GenerationPermissions:
        """Convert to GenerationPermissions object."""
        return GenerationPermissions(
            can_read=self.authorized,
            can_edit=self.authorized and self.role in ['editor', 'admin', 'owner'],
            can_delete=self.authorized and self.role in ['admin', 'owner'],
            can_download=self.authorized,
            can_share=self.authorized and self.role in ['contributor', 'editor', 'admin', 'owner'],
            audit_trail=[{
                "method": self.method,
                "result": self.authorized,
                "cached_at": self.cached_at,
                "cache_level": self.cache_level,
                "timestamp": datetime.utcnow().isoformat()
            }]
        )
    
    def to_team_access_result(self) -> TeamAccessResult:
        """Convert to TeamAccessResult object."""
        return TeamAccessResult(
            granted=self.authorized,
            role=TeamRole(self.role) if self.role else TeamRole.NONE,
            team_id=UUID(self.team_id) if self.team_id else None,
            project_id=UUID(self.project_id) if self.project_id else None,
            access_method=AuthorizationMethod.CACHED_RESULT,
            cached_result=True,
            checked_methods=["cache_lookup"]
        )


class EnhancedAuthorizationCacheService:
    """
    Enhanced authorization service with L1/L2/L3 caching integration.
    Provides sub-100ms authorization with >90% cache hit rates.
    """
    
    def __init__(self):
        # Core services
        self.authorization_service = AuthorizationService()
        self.cache_manager = get_cache_manager()
        
        # Performance monitoring
        self.performance_monitor = get_cache_performance_monitor(self.cache_manager)
        
        # Cache configuration
        self.cache_config = {
            # Authorization cache TTLs (seconds)
            "direct_ownership_ttl": 900,        # 15 minutes (stable)
            "team_membership_ttl": 600,         # 10 minutes (semi-stable)
            "generation_access_ttl": 300,       # 5 minutes (dynamic)
            "user_profile_ttl": 1800,           # 30 minutes (stable)
            "project_visibility_ttl": 1200,     # 20 minutes (semi-stable)
            
            # Cache warming configuration
            "warm_recent_users_count": 100,
            "warm_recent_generations_count": 500,
            "warm_active_teams_count": 50,
            
            # Performance targets
            "target_response_time_ms": 75.0,
            "target_hit_rate_percent": 95.0
        }
        
        # Performance tracking
        self.metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "avg_response_time_ms": 0.0,
            "authorization_success_rate": 0.0
        }
        
        # Start cache monitoring
        asyncio.create_task(self._initialize_monitoring())
    
    async def _initialize_monitoring(self):
        """Initialize cache performance monitoring."""
        try:
            await start_cache_monitoring(self.cache_manager, interval_seconds=30)
            logger.info("Enhanced authorization cache service monitoring initialized")
        except Exception as e:
            logger.error(f"Failed to initialize cache monitoring: {e}")
    
    async def validate_generation_media_access_cached(
        self,
        generation_id: UUID,
        user_id: UUID,
        auth_token: str,
        client_ip: Optional[str] = None,
        expires_in: int = 3600
    ) -> GenerationPermissions:
        """
        Cached generation media access validation with sub-75ms target.
        L1 -> L2 -> L3 -> Authorization Service fallback.
        """
        operation_id = performance_tracker.start_operation(
            "cached_generation_media_access", 
            PerformanceTarget.SUB_50MS
        )
        
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        try:
            # Generate cache key for authorization
            cache_key = f"auth:generation:{user_id}:{generation_id}:media_access"
            
            # Multi-level cache lookup with fallback
            async def authorization_fallback():
                logger.debug(f"Cache miss - performing full authorization for {generation_id}")
                
                # Call original authorization service
                result = await self.authorization_service.validate_generation_media_access(
                    generation_id, user_id, auth_token, client_ip, expires_in
                )
                
                # Convert to cacheable format
                cached_result = CachedAuthorizationResult(
                    authorized=result.can_read,
                    method="generation_media_access",
                    role="owner" if result.can_delete else "viewer" if result.can_read else "none",
                    cached_at=datetime.utcnow().isoformat(),
                    expires_at=(datetime.utcnow() + timedelta(seconds=self.cache_config["generation_access_ttl"])).isoformat(),
                    response_time_ms=(time.time() - start_time) * 1000
                )
                
                return cached_result
            
            # Get from multi-level cache with fallback
            cached_result, cache_level = await self.cache_manager.get_multi_level(
                cache_key, authorization_fallback
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            if cached_result and cache_level != CacheLevel.L3_DATABASE:
                self.metrics["cache_hits"] += 1
                logger.debug(f"Authorization cache hit ({cache_level.value}): {response_time_ms:.2f}ms")
            else:
                self.metrics["cache_misses"] += 1
                
                # Cache the result for future requests
                if cached_result:
                    await self.cache_manager.set_multi_level(
                        cache_key,
                        cached_result,
                        l1_ttl=min(300, self.cache_config["generation_access_ttl"]),
                        l2_ttl=self.cache_config["generation_access_ttl"],
                        priority=3,  # High priority for authorization data
                        tags={"authorization", f"user:{user_id}", f"generation:{generation_id}"}
                    )
                
                logger.debug(f"Authorization cache miss: {response_time_ms:.2f}ms")
            
            # Update metrics
            self._update_performance_metrics(response_time_ms, cached_result is not None)
            
            # Track performance
            performance_tracker.end_operation(
                operation_id, "cached_generation_media_access",
                PerformanceTarget.SUB_50MS, True,
                cache_level=cache_level.value if cache_level else "miss",
                response_time_ms=response_time_ms
            )
            
            # Convert cached result to GenerationPermissions
            if cached_result:
                cached_result.cache_level = cache_level.value if cache_level else None
                cached_result.response_time_ms = response_time_ms
                return cached_result.to_generation_permissions()
            else:
                # Return default denied permissions
                return GenerationPermissions(
                    can_read=False,
                    can_edit=False,
                    can_delete=False,
                    can_download=False,
                    can_share=False,
                    audit_trail=[{
                        "method": "cached_validation_failed",
                        "result": False,
                        "response_time_ms": response_time_ms,
                        "timestamp": datetime.utcnow().isoformat()
                    }]
                )
        
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Cached authorization validation failed: {e}")
            
            performance_tracker.end_operation(
                operation_id, "cached_generation_media_access",
                PerformanceTarget.SUB_50MS, False,
                error=str(e), response_time_ms=response_time_ms
            )
            
            # Fallback to non-cached authorization
            try:
                return await self.authorization_service.validate_generation_media_access(
                    generation_id, user_id, auth_token, client_ip, expires_in
                )
            except Exception as fallback_error:
                logger.error(f"Fallback authorization also failed: {fallback_error}")
                raise
    
    async def validate_team_access_cached(
        self,
        resource_id: UUID,
        user_id: UUID,
        required_role: TeamRole = TeamRole.VIEWER,
        auth_token: str = None,
        client_ip: Optional[str] = None
    ) -> TeamAccessResult:
        """
        Cached team access validation with performance optimization.
        """
        operation_id = performance_tracker.start_operation(
            "cached_team_access", 
            PerformanceTarget.SUB_50MS
        )
        
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        try:
            # Generate cache key
            cache_key = f"auth:team:{user_id}:{resource_id}:{required_role.value}"
            
            async def team_access_fallback():
                logger.debug(f"Team access cache miss - performing full validation for {resource_id}")
                
                # Call original authorization service
                result = await self.authorization_service.validate_team_access(
                    resource_id, user_id, required_role, auth_token, client_ip
                )
                
                # Convert to cacheable format
                cached_result = CachedAuthorizationResult(
                    authorized=result.granted,
                    method=result.access_method.value if result.access_method else "team_validation",
                    role=result.role.value if result.role else "none",
                    team_id=str(result.team_id) if result.team_id else None,
                    project_id=str(result.project_id) if result.project_id else None,
                    cached_at=datetime.utcnow().isoformat(),
                    expires_at=(datetime.utcnow() + timedelta(seconds=self.cache_config["team_membership_ttl"])).isoformat(),
                    response_time_ms=(time.time() - start_time) * 1000
                )
                
                return cached_result
            
            # Get from cache with fallback
            cached_result, cache_level = await self.cache_manager.get_multi_level(
                cache_key, team_access_fallback
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            if cached_result and cache_level != CacheLevel.L3_DATABASE:
                self.metrics["cache_hits"] += 1
            else:
                self.metrics["cache_misses"] += 1
                
                # Cache the result
                if cached_result:
                    await self.cache_manager.set_multi_level(
                        cache_key,
                        cached_result,
                        l1_ttl=min(300, self.cache_config["team_membership_ttl"]),
                        l2_ttl=self.cache_config["team_membership_ttl"],
                        priority=2,
                        tags={"authorization", "team", f"user:{user_id}", f"resource:{resource_id}"}
                    )
            
            # Update metrics
            self._update_performance_metrics(response_time_ms, cached_result is not None)
            
            performance_tracker.end_operation(
                operation_id, "cached_team_access",
                PerformanceTarget.SUB_50MS, True,
                cache_level=cache_level.value if cache_level else "miss",
                response_time_ms=response_time_ms
            )
            
            # Convert to TeamAccessResult
            if cached_result:
                cached_result.cache_level = cache_level.value if cache_level else None
                cached_result.response_time_ms = response_time_ms
                return cached_result.to_team_access_result()
            else:
                return TeamAccessResult(
                    granted=False,
                    role=TeamRole.NONE,
                    denial_reason="cache_validation_failed"
                )
        
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Cached team access validation failed: {e}")
            
            performance_tracker.end_operation(
                operation_id, "cached_team_access",
                PerformanceTarget.SUB_50MS, False,
                error=str(e), response_time_ms=response_time_ms
            )
            
            # Fallback to non-cached validation
            return await self.authorization_service.validate_team_access(
                resource_id, user_id, required_role, auth_token, client_ip
            )
    
    async def validate_direct_ownership_cached(
        self,
        resource_owner_id: UUID,
        user_id: UUID,
        context: ValidationContext
    ) -> AuthorizationResult:
        """
        Cached direct ownership validation with high performance.
        """
        start_time = time.time()
        
        # Generate cache key for ownership
        cache_key = f"auth:ownership:{user_id}:{resource_owner_id}:{context.value}"
        
        async def ownership_fallback():
            result = await self.authorization_service.validate_direct_ownership(
                resource_owner_id, user_id, context
            )
            
            return CachedAuthorizationResult(
                authorized=result.granted,
                method="direct_ownership",
                cached_at=datetime.utcnow().isoformat(),
                expires_at=(datetime.utcnow() + timedelta(seconds=self.cache_config["direct_ownership_ttl"])).isoformat()
            )
        
        cached_result, cache_level = await self.cache_manager.get_multi_level(
            cache_key, ownership_fallback
        )
        
        response_time_ms = (time.time() - start_time) * 1000
        
        if cached_result and cache_level != CacheLevel.L3_DATABASE:
            # Cache the result with long TTL (ownership is stable)
            await self.cache_manager.set_multi_level(
                cache_key,
                cached_result,
                l1_ttl=self.cache_config["direct_ownership_ttl"],
                l2_ttl=self.cache_config["direct_ownership_ttl"],
                priority=1,  # Highest priority
                tags={"authorization", "ownership", f"user:{user_id}"}
            )
        
        return AuthorizationResult(
            granted=cached_result.authorized if cached_result else False,
            method=AuthorizationMethod.DIRECT_OWNERSHIP,
            security_level=SecurityLevel.HIGH,
            response_time_ms=response_time_ms
        )
    
    async def warm_authorization_caches(self) -> Dict[str, int]:
        """
        Intelligent cache warming for authorization patterns.
        Warms caches based on recent user activity and access patterns.
        """
        logger.info("Starting intelligent authorization cache warming")
        
        warming_results = {
            "user_profiles": 0,
            "recent_authorizations": 0,
            "team_memberships": 0,
            "generation_access": 0,
            "total_warmed": 0
        }
        
        try:
            db = await get_database()
            
            # Warm recent user authorizations
            recent_users = await db.execute_query(
                table="users",
                operation="select",
                filters={
                    "is_active": True,
                    "last_active_at__gte": datetime.utcnow() - timedelta(hours=24)
                },
                limit=self.cache_config["warm_recent_users_count"]
            )
            
            for user in recent_users:
                user_id = user["id"]
                
                # Warm user profile cache
                profile_key = f"auth:user_profile:{user_id}"
                profile_data = {
                    "user_id": user_id,
                    "email": user["email"],
                    "is_active": user["is_active"],
                    "last_active_at": user.get("last_active_at"),
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                await self.cache_manager.set_multi_level(
                    profile_key, profile_data,
                    l1_ttl=self.cache_config["user_profile_ttl"],
                    l2_ttl=self.cache_config["user_profile_ttl"],
                    priority=1,
                    tags={"authorization", "user_profile", f"user:{user_id}"}
                )
                warming_results["user_profiles"] += 1
            
            # Warm recent generation authorizations
            recent_generations = await db.execute_query(
                table="generations",
                operation="select",
                filters={
                    "status": "completed",
                    "created_at__gte": datetime.utcnow() - timedelta(hours=48)
                },
                limit=self.cache_config["warm_recent_generations_count"],
                order_by="created_at DESC"
            )
            
            for generation in recent_generations:
                gen_id = generation["id"]
                user_id = generation["user_id"]
                
                # Warm generation access cache
                access_key = f"auth:generation:{user_id}:{gen_id}:media_access"
                access_data = CachedAuthorizationResult(
                    authorized=True,  # Owner has access
                    method="direct_ownership",
                    role="owner",
                    cached_at=datetime.utcnow().isoformat(),
                    expires_at=(datetime.utcnow() + timedelta(seconds=self.cache_config["generation_access_ttl"])).isoformat()
                )
                
                await self.cache_manager.set_multi_level(
                    access_key, access_data,
                    l1_ttl=self.cache_config["generation_access_ttl"],
                    l2_ttl=self.cache_config["generation_access_ttl"],
                    priority=3,
                    tags={"authorization", f"user:{user_id}", f"generation:{gen_id}"}
                )
                warming_results["generation_access"] += 1
            
            # Warm active team memberships
            active_teams = await db.execute_query(
                table="teams",
                operation="select",
                filters={"is_active": True},
                limit=self.cache_config["warm_active_teams_count"],
                order_by="updated_at DESC"
            )
            
            for team in active_teams:
                team_id = team["id"]
                
                # Get team members
                team_members = await db.execute_query(
                    table="team_members",
                    operation="select",
                    filters={"team_id": team_id, "is_active": True}
                )
                
                for member in team_members:
                    user_id = member["user_id"]
                    role = member["role"]
                    
                    # Warm team membership cache
                    membership_key = f"auth:team_member:{user_id}:{team_id}"
                    membership_data = {
                        "user_id": user_id,
                        "team_id": team_id,
                        "role": role,
                        "is_active": member["is_active"],
                        "joined_at": member.get("joined_at"),
                        "cached_at": datetime.utcnow().isoformat()
                    }
                    
                    await self.cache_manager.set_multi_level(
                        membership_key, membership_data,
                        l1_ttl=self.cache_config["team_membership_ttl"],
                        l2_ttl=self.cache_config["team_membership_ttl"],
                        priority=2,
                        tags={"authorization", "team", f"user:{user_id}", f"team:{team_id}"}
                    )
                    warming_results["team_memberships"] += 1
            
            # Calculate total
            warming_results["total_warmed"] = sum(
                count for key, count in warming_results.items() 
                if key != "total_warmed"
            )
            
            logger.info(f"Authorization cache warming completed: {warming_results['total_warmed']} entries warmed")
            return warming_results
            
        except Exception as e:
            logger.error(f"Authorization cache warming failed: {e}")
            return warming_results
    
    async def invalidate_user_authorization_cache(self, user_id: UUID) -> Dict[str, int]:
        """
        Invalidate all authorization cache entries for a specific user.
        Called when user permissions change.
        """
        logger.info(f"Invalidating authorization cache for user: {user_id}")
        
        patterns_to_invalidate = [
            f"auth:*:{user_id}:*",      # User as subject
            f"auth:*:*:{user_id}:*",    # User as object
            f"auth:user_profile:{user_id}",
            f"auth:team_member:{user_id}:*",
            f"auth:ownership:{user_id}:*"
        ]
        
        total_invalidated = 0
        results = {}
        
        for pattern in patterns_to_invalidate:
            try:
                invalidated = await self.cache_manager.invalidate_pattern(pattern)
                results[pattern] = invalidated["L1"] + invalidated["L2"] + invalidated["L3"]
                total_invalidated += results[pattern]
            except Exception as e:
                logger.error(f"Failed to invalidate pattern {pattern}: {e}")
                results[pattern] = 0
        
        logger.info(f"Invalidated {total_invalidated} cache entries for user {user_id}")
        return results
    
    async def invalidate_generation_authorization_cache(self, generation_id: UUID) -> Dict[str, int]:
        """
        Invalidate all authorization cache entries for a specific generation.
        Called when generation permissions change.
        """
        logger.info(f"Invalidating authorization cache for generation: {generation_id}")
        
        patterns_to_invalidate = [
            f"auth:generation:*:{generation_id}:*",
            f"auth:team:*:{generation_id}:*"
        ]
        
        total_invalidated = 0
        results = {}
        
        for pattern in patterns_to_invalidate:
            try:
                invalidated = await self.cache_manager.invalidate_pattern(pattern)
                results[pattern] = invalidated["L1"] + invalidated["L2"] + invalidated["L3"]
                total_invalidated += results[pattern]
            except Exception as e:
                logger.error(f"Failed to invalidate pattern {pattern}: {e}")
                results[pattern] = 0
        
        logger.info(f"Invalidated {total_invalidated} cache entries for generation {generation_id}")
        return results
    
    def _update_performance_metrics(self, response_time_ms: float, success: bool):
        """Update internal performance metrics."""
        # Update average response time
        total_requests = self.metrics["total_requests"]
        if total_requests > 0:
            current_avg = self.metrics["avg_response_time_ms"]
            self.metrics["avg_response_time_ms"] = (
                (current_avg * (total_requests - 1) + response_time_ms) / total_requests
            )
        
        # Update success rate
        if success:
            self.metrics["authorization_success_rate"] = (
                (self.metrics["authorization_success_rate"] * (total_requests - 1) + 1.0) / total_requests
            )
        else:
            self.metrics["authorization_success_rate"] = (
                (self.metrics["authorization_success_rate"] * (total_requests - 1) + 0.0) / total_requests
            )
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        hit_rate = 0.0
        if self.metrics["total_requests"] > 0:
            hit_rate = (self.metrics["cache_hits"] / self.metrics["total_requests"]) * 100
        
        return {
            "authorization_cache_metrics": {
                "total_requests": self.metrics["total_requests"],
                "cache_hits": self.metrics["cache_hits"],
                "cache_misses": self.metrics["cache_misses"],
                "hit_rate_percent": hit_rate,
                "avg_response_time_ms": self.metrics["avg_response_time_ms"],
                "authorization_success_rate": self.metrics["authorization_success_rate"] * 100,
                "performance_targets": {
                    "target_response_time_ms": self.cache_config["target_response_time_ms"],
                    "target_hit_rate_percent": self.cache_config["target_hit_rate_percent"],
                    "response_time_target_met": self.metrics["avg_response_time_ms"] <= self.cache_config["target_response_time_ms"],
                    "hit_rate_target_met": hit_rate >= self.cache_config["target_hit_rate_percent"]
                }
            },
            "cache_manager_metrics": self.cache_manager.get_comprehensive_metrics(),
            "cache_configuration": self.cache_config
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for cached authorization service."""
        try:
            # Test authorization cache performance
            test_user_id = UUID("00000000-0000-0000-0000-000000000001")
            test_gen_id = UUID("00000000-0000-0000-0000-000000000002")
            
            start_time = time.time()
            
            # Test cache operations
            test_key = f"health_check:{test_user_id}:{test_gen_id}"
            test_data = CachedAuthorizationResult(
                authorized=True,
                method="health_check",
                cached_at=datetime.utcnow().isoformat()
            )
            
            # Test set operation
            set_result = await self.cache_manager.set_multi_level(test_key, test_data)
            
            # Test get operation
            get_result, cache_level = await self.cache_manager.get_multi_level(test_key)
            
            # Test invalidation
            invalidate_result = await self.cache_manager.invalidate_multi_level(test_key)
            
            response_time_ms = (time.time() - start_time) * 1000
            
            # Get cache health
            cache_health = await self.cache_manager.health_check()
            
            health_status = {
                "status": "healthy" if all([
                    any(set_result.values()),
                    get_result is not None,
                    any(invalidate_result.values()),
                    cache_health["overall_healthy"]
                ]) else "unhealthy",
                "response_time_ms": response_time_ms,
                "cache_operations_test": {
                    "set_success": any(set_result.values()),
                    "get_success": get_result is not None,
                    "invalidate_success": any(invalidate_result.values())
                },
                "cache_health": cache_health,
                "performance_metrics": self.get_performance_metrics(),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return health_status
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }


# Global enhanced authorization cache service instance
enhanced_auth_cache_service: Optional[EnhancedAuthorizationCacheService] = None


def get_enhanced_authorization_cache_service() -> EnhancedAuthorizationCacheService:
    """Get or create the global enhanced authorization cache service."""
    global enhanced_auth_cache_service
    if enhanced_auth_cache_service is None:
        enhanced_auth_cache_service = EnhancedAuthorizationCacheService()
    return enhanced_auth_cache_service


# Convenience functions for cached authorization operations
async def validate_cached_generation_access(generation_id: UUID, user_id: UUID, 
                                           auth_token: str) -> GenerationPermissions:
    """Validate generation access with caching."""
    service = get_enhanced_authorization_cache_service()
    return await service.validate_generation_media_access_cached(
        generation_id, user_id, auth_token
    )


async def validate_cached_team_access(resource_id: UUID, user_id: UUID, 
                                    required_role: TeamRole = TeamRole.VIEWER) -> TeamAccessResult:
    """Validate team access with caching."""
    service = get_enhanced_authorization_cache_service()
    return await service.validate_team_access_cached(resource_id, user_id, required_role)


async def warm_authorization_caches() -> Dict[str, int]:
    """Warm authorization caches with intelligent patterns."""
    service = get_enhanced_authorization_cache_service()
    return await service.warm_authorization_caches()


async def invalidate_user_cache(user_id: UUID) -> Dict[str, int]:
    """Invalidate all cache entries for a user."""
    service = get_enhanced_authorization_cache_service()
    return await service.invalidate_user_authorization_cache(user_id)


async def get_authorization_cache_metrics() -> Dict[str, Any]:
    """Get comprehensive authorization cache performance metrics."""
    service = get_enhanced_authorization_cache_service()
    return service.get_performance_metrics()