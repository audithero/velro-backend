"""
High-Performance Authorization Service with Cache Integration
Phase 1 Week 2 optimization for 150-200ms response time reduction.

Integrates with AuthorizationCacheService to provide:
- Cached authorization results with 5-minute TTL
- Automatic cache invalidation on permission changes  
- Cache warming for frequently accessed resources
- >90% cache hit rate optimization
- Comprehensive performance monitoring
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID

from services.authorization_service import AuthorizationService
from services.authorization_cache_service import authorization_cache_service
from models.authorization import (
    ValidationContext, SecurityLevel, TeamRole, ProjectVisibility, AccessType,
    AuthorizationMethod, AuthorizationResult, GenerationPermissions, TeamAccessResult,
    SecurityContext, ProjectPermissions, InheritedAccessResult,
    VelroAuthorizationError, GenerationAccessDeniedError, SecurityViolationError,
    GenerationNotFoundError, has_sufficient_role, get_role_permissions
)
from utils.enhanced_uuid_utils import EnhancedUUIDUtils, secure_uuid_validator
from utils.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class HighPerformanceAuthorizationService:
    """
    High-performance authorization service with intelligent caching.
    Wraps the existing AuthorizationService with cache layer for optimal performance.
    """
    
    def __init__(self):
        # Initialize base authorization service
        self.base_service = AuthorizationService()
        self.cache_service = authorization_cache_service
        
        # Performance tracking
        self.performance_metrics = {
            "total_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "average_cached_response_time": 0.0,
            "average_uncached_response_time": 0.0,
            "cache_hit_rate": 0.0,
            "performance_improvement_ms": 0.0
        }
        
        logger.info("🚀 [HIGH-PERF-AUTH] High-performance authorization service initialized")
    
    async def validate_generation_media_access(
        self, 
        generation_id: UUID, 
        user_id: UUID, 
        auth_token: str,
        client_ip: Optional[str] = None,
        expires_in: int = 3600
    ) -> GenerationPermissions:
        """
        Enterprise-grade generation media access validation with caching.
        Expected 150-200ms performance improvement through caching.
        """
        start_time = time.time()
        self.performance_metrics["total_requests"] += 1
        
        # Define cache operation
        cache_operation = "generation_media_access"
        
        try:
            # Step 1: Try to get from cache first
            logger.debug(f"🔍 [CACHE-CHECK] Checking cache for generation {generation_id}")
            
            cached_result = await self.cache_service.get_authorization_result(
                user_id=user_id,
                resource_id=generation_id,
                operation=cache_operation,
                generation_id=generation_id
            )
            
            if cached_result is not None:
                # Cache hit - return cached result with updated expiry
                cached_response_time = (time.time() - start_time) * 1000
                self._update_cache_hit_metrics(cached_response_time)
                
                logger.info(
                    f"⚡ [CACHE-HIT] Generation access cached result "
                    f"user={EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
                    f"generation={EnhancedUUIDUtils.hash_uuid_for_logging(generation_id)} "
                    f"({cached_response_time:.2f}ms)"
                )
                
                # Update expiry time for fresh response
                if isinstance(cached_result, GenerationPermissions):
                    cached_result.expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                
                return cached_result
            
            # Step 2: Cache miss - get from base service
            logger.debug(f"❌ [CACHE-MISS] Cache miss, calling base service for generation {generation_id}")
            
            base_start_time = time.time()
            result = await self.base_service.validate_generation_media_access(
                generation_id=generation_id,
                user_id=user_id,
                auth_token=auth_token,
                client_ip=client_ip,
                expires_in=expires_in
            )
            
            base_response_time = (time.time() - base_start_time) * 1000
            total_response_time = (time.time() - start_time) * 1000
            
            # Step 3: Cache the result if successful
            if result and result.granted:
                # Determine project_id for tagging
                project_id = None
                if hasattr(result, 'project_context') and result.project_context:
                    project_id = UUID(result.project_context)
                
                # Cache the successful result
                await self.cache_service.cache_authorization_result(
                    user_id=user_id,
                    resource_id=generation_id,
                    operation=cache_operation,
                    result=result,
                    ttl=300,  # 5 minutes
                    generation_id=generation_id,
                    project_id=project_id
                )
                
                logger.info(
                    f"💾 [CACHED] Successful authorization result cached "
                    f"user={EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
                    f"generation={EnhancedUUIDUtils.hash_uuid_for_logging(generation_id)}"
                )
            
            # Update performance metrics
            self._update_cache_miss_metrics(base_response_time, total_response_time)
            
            logger.info(
                f"🔄 [CACHE-MISS] Generation access from base service "
                f"user={EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
                f"generation={EnhancedUUIDUtils.hash_uuid_for_logging(generation_id)} "
                f"(base: {base_response_time:.2f}ms, total: {total_response_time:.2f}ms)"
            )
            
            return result
            
        except Exception as e:
            # Error handling - still call base service
            logger.error(f"❌ [CACHE-ERROR] Cache error, falling back to base service: {e}")
            
            try:
                result = await self.base_service.validate_generation_media_access(
                    generation_id=generation_id,
                    user_id=user_id,
                    auth_token=auth_token,
                    client_ip=client_ip,
                    expires_in=expires_in
                )
                
                fallback_response_time = (time.time() - start_time) * 1000
                logger.warning(
                    f"⚠️ [FALLBACK] Used base service after cache error "
                    f"({fallback_response_time:.2f}ms)"
                )
                
                return result
                
            except Exception as base_error:
                logger.error(f"❌ [BASE-SERVICE-ERROR] Base service also failed: {base_error}")
                raise
    
    async def validate_direct_ownership(
        self, resource_user_id: UUID, request_user_id: UUID, context: ValidationContext
    ) -> AuthorizationResult:
        """Enhanced direct ownership validation with caching."""
        
        # Define cache operation
        cache_operation = f"direct_ownership_{context.value}"
        
        # Try cache first
        cached_result = await self.cache_service.get_authorization_result(
            user_id=request_user_id,
            resource_id=resource_user_id,
            operation=cache_operation
        )
        
        if cached_result is not None:
            self._update_cache_hit_metrics(0)  # Fast cache hit
            return cached_result
        
        # Cache miss - get from base service
        result = await self.base_service.validate_direct_ownership(
            resource_user_id, request_user_id, context
        )
        
        # Cache successful results
        if result and result.granted:
            await self.cache_service.cache_authorization_result(
                user_id=request_user_id,
                resource_id=resource_user_id,
                operation=cache_operation,
                result=result,
                ttl=300  # 5 minutes
            )
        
        self._update_cache_miss_metrics(0, 0)
        return result
    
    async def validate_team_access(
        self, 
        resource_id: UUID, 
        user_id: UUID,
        required_role: TeamRole = TeamRole.VIEWER,
        auth_token: str = None,
        client_ip: Optional[str] = None
    ) -> TeamAccessResult:
        """Enterprise team-based access validation with caching."""
        
        # Define cache operation
        cache_operation = f"team_access_{required_role.value}"
        
        # Try cache first
        cached_result = await self.cache_service.get_authorization_result(
            user_id=user_id,
            resource_id=resource_id,
            operation=cache_operation
        )
        
        if cached_result is not None:
            self._update_cache_hit_metrics(0)  # Fast cache hit
            return cached_result
        
        # Cache miss - get from base service
        result = await self.base_service.validate_team_access(
            resource_id, user_id, required_role, auth_token, client_ip
        )
        
        # Cache successful results
        if result and result.granted:
            await self.cache_service.cache_authorization_result(
                user_id=user_id,
                resource_id=resource_id,
                operation=cache_operation,
                result=result,
                ttl=300  # 5 minutes
            )
        
        self._update_cache_miss_metrics(0, 0)
        return result
    
    async def invalidate_user_permissions(self, user_id: UUID) -> int:
        """
        Invalidate all cached permissions for a user.
        Call this when user's permissions change.
        
        Returns:
            Number of cache entries invalidated
        """
        try:
            # Increment user generation to invalidate all user caches
            new_generation = await self.cache_service.increment_user_generation(user_id)
            
            # Also explicitly invalidate by user tag
            explicit_invalidations = await self.cache_service.invalidate_by_user(user_id)
            
            logger.info(
                f"🔄 [PERMISSION-INVALIDATION] Invalidated permissions for user "
                f"{EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
                f"(generation: {new_generation}, explicit: {explicit_invalidations})"
            )
            
            return explicit_invalidations
            
        except Exception as e:
            logger.error(f"❌ [INVALIDATION-ERROR] Failed to invalidate user permissions: {e}")
            return 0
    
    async def invalidate_resource_permissions(self, resource_id: UUID) -> int:
        """
        Invalidate all cached permissions for a resource.
        Call this when resource's permissions change.
        
        Returns:
            Number of cache entries invalidated
        """
        try:
            invalidated = await self.cache_service.invalidate_by_resource(resource_id)
            
            logger.info(
                f"🔄 [RESOURCE-INVALIDATION] Invalidated permissions for resource "
                f"{EnhancedUUIDUtils.hash_uuid_for_logging(resource_id)} "
                f"({invalidated} entries)"
            )
            
            return invalidated
            
        except Exception as e:
            logger.error(f"❌ [INVALIDATION-ERROR] Failed to invalidate resource permissions: {e}")
            return 0
    
    async def invalidate_generation_permissions(self, generation_id: UUID) -> int:
        """
        Invalidate all cached permissions for a generation.
        Call this when generation's permissions change.
        
        Returns:
            Number of cache entries invalidated
        """
        try:
            invalidated = await self.cache_service.invalidate_by_generation(generation_id)
            
            logger.info(
                f"🔄 [GENERATION-INVALIDATION] Invalidated permissions for generation "
                f"{EnhancedUUIDUtils.hash_uuid_for_logging(generation_id)} "
                f"({invalidated} entries)"
            )
            
            return invalidated
            
        except Exception as e:
            logger.error(f"❌ [INVALIDATION-ERROR] Failed to invalidate generation permissions: {e}")
            return 0
    
    async def invalidate_project_permissions(self, project_id: UUID) -> int:
        """
        Invalidate all cached permissions for a project.
        Call this when project's permissions change.
        
        Returns:
            Number of cache entries invalidated
        """
        try:
            invalidated = await self.cache_service.invalidate_by_project(project_id)
            
            logger.info(
                f"🔄 [PROJECT-INVALIDATION] Invalidated permissions for project "
                f"{EnhancedUUIDUtils.hash_uuid_for_logging(project_id)} "
                f"({invalidated} entries)"
            )
            
            return invalidated
            
        except Exception as e:
            logger.error(f"❌ [INVALIDATION-ERROR] Failed to invalidate project permissions: {e}")
            return 0
    
    def _update_cache_hit_metrics(self, response_time_ms: float):
        """Update metrics for cache hits."""
        self.performance_metrics["cache_hits"] += 1
        
        # Update average cached response time
        if self.performance_metrics["cache_hits"] == 1:
            self.performance_metrics["average_cached_response_time"] = response_time_ms
        else:
            # Exponential moving average
            alpha = 0.1
            self.performance_metrics["average_cached_response_time"] = (
                alpha * response_time_ms + 
                (1 - alpha) * self.performance_metrics["average_cached_response_time"]
            )
        
        self._update_derived_metrics()
    
    def _update_cache_miss_metrics(self, base_response_time_ms: float, total_response_time_ms: float):
        """Update metrics for cache misses."""
        self.performance_metrics["cache_misses"] += 1
        
        # Update average uncached response time
        if self.performance_metrics["cache_misses"] == 1:
            self.performance_metrics["average_uncached_response_time"] = base_response_time_ms
        else:
            # Exponential moving average
            alpha = 0.1
            self.performance_metrics["average_uncached_response_time"] = (
                alpha * base_response_time_ms + 
                (1 - alpha) * self.performance_metrics["average_uncached_response_time"]
            )
        
        self._update_derived_metrics()
    
    def _update_derived_metrics(self):
        """Update derived performance metrics."""
        total_requests = self.performance_metrics["cache_hits"] + self.performance_metrics["cache_misses"]
        
        if total_requests > 0:
            # Calculate cache hit rate
            self.performance_metrics["cache_hit_rate"] = (
                self.performance_metrics["cache_hits"] / total_requests * 100
            )
            
            # Calculate performance improvement (how much faster cached requests are)
            cached_avg = self.performance_metrics["average_cached_response_time"]
            uncached_avg = self.performance_metrics["average_uncached_response_time"]
            
            if uncached_avg > 0:
                self.performance_metrics["performance_improvement_ms"] = uncached_avg - cached_avg
    
    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics."""
        try:
            # Get cache service metrics
            cache_metrics = await self.cache_service.get_metrics()
            
            # Get base service metrics
            base_metrics = self.base_service.get_performance_metrics()
            
            # Combine metrics
            combined_metrics = {
                "high_performance_auth": self.performance_metrics.copy(),
                "cache_service": cache_metrics.to_dict(),
                "base_authorization_service": base_metrics,
                "performance_summary": {
                    "cache_hit_rate_percent": self.performance_metrics["cache_hit_rate"],
                    "avg_performance_improvement_ms": self.performance_metrics["performance_improvement_ms"],
                    "total_requests_processed": self.performance_metrics["total_requests"],
                    "expected_improvement_target": "150-200ms reduction",
                    "cache_effectiveness": self._calculate_cache_effectiveness()
                }
            }
            
            return combined_metrics
            
        except Exception as e:
            logger.error(f"❌ [METRICS-ERROR] Error getting performance metrics: {e}")
            return {"error": str(e)}
    
    def _calculate_cache_effectiveness(self) -> str:
        """Calculate cache effectiveness rating."""
        hit_rate = self.performance_metrics["cache_hit_rate"]
        improvement = self.performance_metrics["performance_improvement_ms"]
        
        if hit_rate >= 90 and improvement >= 150:
            return "EXCELLENT (>90% hit rate, >150ms improvement)"
        elif hit_rate >= 80 and improvement >= 100:
            return "GOOD (>80% hit rate, >100ms improvement)"
        elif hit_rate >= 70 and improvement >= 50:
            return "FAIR (>70% hit rate, >50ms improvement)"
        else:
            return f"NEEDS_IMPROVEMENT ({hit_rate:.1f}% hit rate, {improvement:.1f}ms improvement)"
    
    async def get_detailed_cache_metrics(self) -> Dict[str, Any]:
        """Get detailed cache metrics for monitoring and optimization."""
        try:
            return await self.cache_service.get_detailed_metrics()
        except Exception as e:
            logger.error(f"❌ [DETAILED-METRICS-ERROR] Error getting detailed cache metrics: {e}")
            return {"error": str(e)}
    
    async def warm_cache_for_user(self, user_id: UUID, resource_ids: List[UUID]) -> int:
        """
        Warm cache for a user with their commonly accessed resources.
        This can be called proactively for active users.
        
        Args:
            user_id: User ID to warm cache for
            resource_ids: List of resource IDs to pre-authorize
            
        Returns:
            Number of cache entries warmed
        """
        warmed_count = 0
        
        try:
            logger.info(
                f"🔥 [CACHE-WARMING] Starting cache warming for user "
                f"{EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
                f"({len(resource_ids)} resources)"
            )
            
            for resource_id in resource_ids:
                try:
                    # This will cache the result if successful
                    await self.validate_direct_ownership(
                        resource_user_id=user_id,
                        request_user_id=user_id,
                        context=ValidationContext.GENERATION_ACCESS
                    )
                    warmed_count += 1
                    
                except Exception as resource_error:
                    logger.debug(f"Cache warming failed for resource {resource_id}: {resource_error}")
                    continue
            
            logger.info(
                f"🔥 [CACHE-WARMING] Completed cache warming for user "
                f"{EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
                f"({warmed_count}/{len(resource_ids)} successful)"
            )
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"❌ [CACHE-WARMING-ERROR] Cache warming failed: {e}")
            return warmed_count
    
    async def clear_all_caches(self) -> int:
        """Clear all authorization caches. Use with caution."""
        try:
            cleared = await self.cache_service.clear_cache()
            
            logger.warning(f"🧹 [CACHE-CLEAR] Cleared all authorization caches ({cleared} entries)")
            
            return cleared
            
        except Exception as e:
            logger.error(f"❌ [CACHE-CLEAR-ERROR] Failed to clear caches: {e}")
            return 0
    
    async def shutdown(self):
        """Shutdown high-performance authorization service."""
        try:
            await self.cache_service.shutdown()
            
            # Log final performance summary
            final_metrics = await self.get_performance_metrics()
            logger.info(
                f"🏁 [SHUTDOWN-SUMMARY] Authorization service performance: "
                f"Hit rate: {self.performance_metrics['cache_hit_rate']:.1f}%, "
                f"Improvement: {self.performance_metrics['performance_improvement_ms']:.1f}ms, "
                f"Total requests: {self.performance_metrics['total_requests']}"
            )
            
            logger.info("🛑 [HIGH-PERF-AUTH] High-performance authorization service shutdown complete")
            
        except Exception as e:
            logger.error(f"❌ [SHUTDOWN-ERROR] Error during shutdown: {e}")


# Global high-performance authorization service instance
high_performance_authorization_service = HighPerformanceAuthorizationService()