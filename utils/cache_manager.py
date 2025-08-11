"""
Ultra-High Performance Cache Manager for <100ms Authorization Targets
Advanced caching manager optimized for API response and database query performance.
Implements multi-layer caching with sub-100ms response time targets for authorization.

Key Performance Optimizations:
- L1 Memory Cache: <5ms access, >98% hit rate for hot authorization data
- L2 Session Cache: <20ms access, >90% hit rate for warm data
- L3 Persistent Cache: <100ms access with TTL management
- Circuit breaker protection for resilience
- Real-time performance monitoring and alerting

Production Performance Targets:
- Authorization queries: <100ms average response time
- Cache hit rate: >95% for frequently accessed auth data
- Memory utilization: <300MB with intelligent eviction
- Error rate: <0.1% with circuit breaker protection
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import json
import weakref
from collections import defaultdict, OrderedDict

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CacheLevel(Enum):
    """Cache levels for different performance requirements."""
    L1_MEMORY = "l1_memory"        # Ultra-fast in-memory cache (100ms TTL)
    L2_SESSION = "l2_session"      # Session-based cache (5min TTL)  
    L3_PERSISTENT = "l3_persistent" # Persistent cache (1hr TTL)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit broken, bypass cache
    HALF_OPEN = "half_open" # Testing if circuit can be closed


@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    data: Any
    timestamp: float
    ttl: float
    access_count: int = 0
    last_accessed: float = 0
    size_bytes: int = 0


@dataclass 
class CircuitBreakerConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 3


class CircuitBreaker:
    """Circuit breaker for cache operations."""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        
    def record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info("🔧 [CIRCUIT-BREAKER] Circuit closed - operations restored")
    
    def record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(f"⚠️ [CIRCUIT-BREAKER] Circuit opened - {self.failure_count} failures")
    
    def can_execute(self) -> bool:
        """Check if operation can be executed."""
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.config.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info("🔄 [CIRCUIT-BREAKER] Circuit half-open - testing recovery")
                return True
            return False
        else:  # HALF_OPEN
            return True


class PerformanceOptimizedCache:
    """High-performance multi-layer cache with circuit breaker."""
    
    def __init__(self, max_size_mb: float = 100):
        self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        self.current_size_bytes = 0
        
        # Multi-layer caches with different TTLs
        self.l1_cache: OrderedDict[str, CacheEntry] = OrderedDict()  # LRU for L1
        self.l2_cache: Dict[str, CacheEntry] = {}
        self.l3_cache: Dict[str, CacheEntry] = {}
        
        # Performance metrics for <100ms target monitoring
        self.metrics = {
            'hits': defaultdict(int),
            'misses': defaultdict(int),
            'evictions': defaultdict(int),
            'errors': defaultdict(int),
            'response_times_ms': defaultdict(list),
            'slow_operations': defaultdict(int),  # Operations >100ms
            'total_operations': 0,
            'auth_cache_hits': 0,  # Specific to authorization
            'auth_cache_misses': 0
        }
        
        # Circuit breaker for cache operations
        self.circuit_breaker = CircuitBreaker(CircuitBreakerConfig())
        
        # Background cleanup task
        self._cleanup_task = None
        # CRITICAL FIX: Defer cleanup task start
        self._cleanup_task = None
        self._try_start_cleanup_task()
    
    def _try_start_cleanup_task(self):
        """Try to start the background cleanup task if event loop is available."""
        try:
            # CRITICAL FIX: Only create task if event loop is running
            loop = asyncio.get_running_loop()
            if self._cleanup_task is None:
                self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        except RuntimeError:
            # No event loop running, defer task creation
            pass
    
    async def _cleanup_loop(self):
        """Background cleanup loop."""
        while True:
            try:
                await asyncio.sleep(60)  # Cleanup every minute
                await self._cleanup_expired_entries()
                await self._enforce_size_limits()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ [CACHE] Cleanup error: {e}")
    
    def _get_cache_for_level(self, level: CacheLevel) -> Dict[str, CacheEntry]:
        """Get cache dictionary for specified level."""
        if level == CacheLevel.L1_MEMORY:
            return self.l1_cache
        elif level == CacheLevel.L2_SESSION:
            return self.l2_cache
        else:
            return self.l3_cache
    
    def _get_ttl_for_level(self, level: CacheLevel) -> float:
        """Get optimized TTL for cache level targeting <100ms performance."""
        if level == CacheLevel.L1_MEMORY:
            return 300  # 5 minutes for hot auth data (was 60)
        elif level == CacheLevel.L2_SESSION:
            return 900  # 15 minutes for warm auth data (was 300)
        else:
            return 3600  # 1 hour for persistent data
    
    def _generate_cache_key(self, key: str, level: CacheLevel) -> str:
        """Generate cache key with level prefix."""
        level_prefix = level.value
        return f"{level_prefix}:{hashlib.md5(key.encode()).hexdigest()}"
    
    def _estimate_size(self, data: Any) -> int:
        """Estimate data size in bytes."""
        try:
            return len(json.dumps(data, default=str).encode('utf-8'))
        except:
            return 1024  # Default estimate
    
    async def get(
        self, 
        key: str, 
        level: CacheLevel = CacheLevel.L2_SESSION,
        default: Any = None
    ) -> Any:
        """Get value from cache with <100ms performance monitoring."""
        start_time = time.perf_counter()
        
        if not self.circuit_breaker.can_execute():
            self.metrics['misses'][level.value] += 1
            return default
        
        try:
            cache_key = self._generate_cache_key(key, level)
            cache_dict = self._get_cache_for_level(level)
            self.metrics['total_operations'] += 1
            
            if cache_key in cache_dict:
                entry = cache_dict[cache_key] 
                
                # Check if entry is expired
                if time.time() - entry.timestamp <= entry.ttl:
                    # Update access metrics
                    entry.access_count += 1
                    entry.last_accessed = time.time()
                    
                    # Move to front for LRU (L1 only)
                    if level == CacheLevel.L1_MEMORY:
                        self.l1_cache.move_to_end(cache_key)
                    
                    # Record performance metrics
                    response_time_ms = (time.perf_counter() - start_time) * 1000
                    self.metrics['response_times_ms'][level.value].append(response_time_ms)
                    
                    # Track auth-specific metrics
                    if 'auth:' in key or 'user:' in key or 'permission:' in key:
                        self.metrics['auth_cache_hits'] += 1
                    
                    # Alert on slow operations
                    if response_time_ms > 100.0:
                        self.metrics['slow_operations'][level.value] += 1
                        logger.warning(f"⚠️ [CACHE] Slow cache get: {response_time_ms:.2f}ms for {key[:50]}")
                    
                    # Keep only last 1000 response times for memory efficiency
                    if len(self.metrics['response_times_ms'][level.value]) > 1000:
                        self.metrics['response_times_ms'][level.value].pop(0)
                    
                    self.metrics['hits'][level.value] += 1
                    self.circuit_breaker.record_success()
                    
                    logger.debug(f"💾 [CACHE] Hit L{level.value[-1]} ({response_time_ms:.1f}ms) for key: {key[:50]}")
                    return entry.data
                else:
                    # Entry expired, remove it
                    self._remove_entry(cache_key, level)
            
            # Track auth-specific misses
            if 'auth:' in key or 'user:' in key or 'permission:' in key:
                self.metrics['auth_cache_misses'] += 1
            
            self.metrics['misses'][level.value] += 1
            return default
            
        except Exception as e:
            logger.error(f"❌ [CACHE] Get error for key {key}: {e}")
            self.circuit_breaker.record_failure()
            self.metrics['errors'][level.value] += 1
            return default
    
    async def set(
        self, 
        key: str, 
        value: Any, 
        level: CacheLevel = CacheLevel.L2_SESSION,
        ttl: Optional[float] = None
    ) -> bool:
        """Set value in cache with size management."""
        if not self.circuit_breaker.can_execute():
            return False
        
        try:
            cache_key = self._generate_cache_key(key, level)
            cache_dict = self._get_cache_for_level(level)
            
            # Calculate TTL
            if ttl is None:
                ttl = self._get_ttl_for_level(level)
            
            # Estimate size
            size_bytes = self._estimate_size(value)
            
            # Check size limits
            if size_bytes > self.max_size_bytes * 0.1:  # Single entry can't exceed 10% of cache
                logger.warning(f"⚠️ [CACHE] Entry too large for key {key}: {size_bytes} bytes")
                return False
            
            # Remove old entry if exists
            if cache_key in cache_dict:
                self._remove_entry(cache_key, level)
            
            # Create new entry
            entry = CacheEntry(
                data=value,
                timestamp=time.time(),
                ttl=ttl,
                size_bytes=size_bytes
            )
            
            # Add to cache
            cache_dict[cache_key] = entry
            self.current_size_bytes += size_bytes
            
            # Enforce size limits
            await self._enforce_size_limits()
            
            self.circuit_breaker.record_success()
            logger.debug(f"💾 [CACHE] Set L{level.value[-1]} for key: {key[:50]} ({size_bytes} bytes)")
            return True
            
        except Exception as e:
            logger.error(f"❌ [CACHE] Set error for key {key}: {e}")
            self.circuit_breaker.record_failure()
            self.metrics['errors'][level.value] += 1
            return False
    
    def _remove_entry(self, cache_key: str, level: CacheLevel):
        """Remove entry from cache."""
        cache_dict = self._get_cache_for_level(level)
        if cache_key in cache_dict:
            entry = cache_dict[cache_key]
            self.current_size_bytes -= entry.size_bytes
            del cache_dict[cache_key]
            self.metrics['evictions'][level.value] += 1
    
    async def _cleanup_expired_entries(self):
        """Remove expired entries from all cache levels."""
        current_time = time.time()
        expired_keys = []
        
        # Check all cache levels
        for level in CacheLevel:
            cache_dict = self._get_cache_for_level(level)
            for cache_key, entry in cache_dict.items():
                if current_time - entry.timestamp > entry.ttl:
                    expired_keys.append((cache_key, level))
        
        # Remove expired entries
        for cache_key, level in expired_keys:
            self._remove_entry(cache_key, level)
        
        if expired_keys:
            logger.debug(f"🧹 [CACHE] Cleaned {len(expired_keys)} expired entries")
    
    async def _enforce_size_limits(self):
        """Enforce cache size limits using LRU eviction."""
        while self.current_size_bytes > self.max_size_bytes:
            # Evict from L1 first (LRU)
            if self.l1_cache:
                cache_key = next(iter(self.l1_cache))  # Oldest entry
                self._remove_entry(cache_key, CacheLevel.L1_MEMORY)
                continue
            
            # Then evict from L2 (least accessed)
            if self.l2_cache:
                least_accessed = min(
                    self.l2_cache.items(),
                    key=lambda x: x[1].last_accessed or x[1].timestamp
                )
                self._remove_entry(least_accessed[0], CacheLevel.L2_SESSION)
                continue
            
            # Finally evict from L3 (oldest)
            if self.l3_cache:
                oldest = min(
                    self.l3_cache.items(),
                    key=lambda x: x[1].timestamp
                )
                self._remove_entry(oldest[0], CacheLevel.L3_PERSISTENT)
                continue
            
            break  # No more entries to evict
    
    async def invalidate(self, key: str, level: Optional[CacheLevel] = None):
        """Invalidate cache entry(s)."""
        if level:
            # Invalidate specific level
            cache_key = self._generate_cache_key(key, level)
            self._remove_entry(cache_key, level)
        else:
            # Invalidate all levels
            for cache_level in CacheLevel:
                cache_key = self._generate_cache_key(key, cache_level)
                self._remove_entry(cache_key, cache_level)
    
    async def invalidate_pattern(self, pattern: str):
        """Invalidate all keys matching pattern."""
        # This is a simplified pattern matching - in production, consider using Redis with pattern support
        pattern_hash = hashlib.md5(pattern.encode()).hexdigest()[:8]
        
        keys_to_remove = []
        for level in CacheLevel:
            cache_dict = self._get_cache_for_level(level)
            for cache_key in cache_dict.keys():
                if pattern_hash in cache_key:
                    keys_to_remove.append((cache_key, level))
        
        for cache_key, level in keys_to_remove:
            self._remove_entry(cache_key, level)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive cache performance metrics for <100ms optimization."""
        total_hits = sum(self.metrics['hits'].values())
        total_misses = sum(self.metrics['misses'].values())
        total_requests = total_hits + total_misses
        
        hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
        
        # Calculate average response times per level
        avg_response_times = {}
        for level in ['l1_memory', 'l2_session', 'l3_persistent']:
            times = self.metrics['response_times_ms'][level]
            avg_response_times[level] = round(sum(times) / len(times), 2) if times else 0
        
        # Authorization-specific metrics
        auth_total_requests = self.metrics['auth_cache_hits'] + self.metrics['auth_cache_misses']
        auth_hit_rate = (self.metrics['auth_cache_hits'] / auth_total_requests * 100) if auth_total_requests > 0 else 0
        
        # Performance target assessment
        overall_avg_response_time = sum(avg_response_times.values()) / len([t for t in avg_response_times.values() if t > 0]) if any(avg_response_times.values()) else 0
        performance_target_met = overall_avg_response_time < 100.0 and hit_rate > 95.0
        
        return {
            'performance_summary': {
                'hit_rate_percent': round(hit_rate, 2),
                'avg_response_time_ms': round(overall_avg_response_time, 2),
                'performance_target_met': performance_target_met,
                'target_response_time_ms': 100.0,
                'target_hit_rate_percent': 95.0
            },
            'authorization_metrics': {
                'auth_hit_rate_percent': round(auth_hit_rate, 2),
                'auth_cache_hits': self.metrics['auth_cache_hits'],
                'auth_cache_misses': self.metrics['auth_cache_misses'],
                'auth_total_requests': auth_total_requests
            },
            'response_time_analysis': {
                'avg_response_times_ms': avg_response_times,
                'slow_operations_count': dict(self.metrics['slow_operations']),
                'total_operations': self.metrics['total_operations']
            },
            'cache_utilization': {
                'total_requests': total_requests,
                'total_hits': total_hits,
                'total_misses': total_misses,
                'cache_size_mb': round(self.current_size_bytes / (1024 * 1024), 2),
                'max_size_mb': round(self.max_size_bytes / (1024 * 1024), 2),
                'utilization_percent': round((self.current_size_bytes / self.max_size_bytes) * 100, 2),
                'entries_count': {
                    'l1': len(self.l1_cache),
                    'l2': len(self.l2_cache), 
                    'l3': len(self.l3_cache)
                }
            },
            'circuit_breaker_state': self.circuit_breaker.state.value,
            'metrics_by_level': {
                level: {
                    'hits': self.metrics['hits'][level],
                    'misses': self.metrics['misses'][level],
                    'evictions': self.metrics['evictions'][level],
                    'errors': self.metrics['errors'][level],
                    'avg_response_time_ms': avg_response_times.get(level, 0),
                    'slow_operations': self.metrics['slow_operations'][level]
                }
                for level in ['l1_memory', 'l2_session', 'l3_persistent']
            }
        }
    
    async def clear(self, level: Optional[CacheLevel] = None):
        """Clear cache entries."""
        if level:
            cache_dict = self._get_cache_for_level(level)
            # Calculate size to subtract
            size_to_subtract = sum(entry.size_bytes for entry in cache_dict.values())
            cache_dict.clear()
            self.current_size_bytes -= size_to_subtract
        else:
            # Clear all levels
            self.l1_cache.clear()
            self.l2_cache.clear()
            self.l3_cache.clear()
            self.current_size_bytes = 0
    
    async def shutdown(self):
        """Shutdown cache manager."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        await self.clear()
        logger.info("🛑 [CACHE] Cache manager shutdown complete")


# Decorator for caching function results
def cached(
    level: CacheLevel = CacheLevel.L2_SESSION,
    ttl: Optional[float] = None,
    key_generator: Optional[Callable] = None
):
    """Decorator for caching function results."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key
            if key_generator:
                cache_key = key_generator(*args, **kwargs)
            else:
                # Default key generation
                key_parts = [func.__name__]
                key_parts.extend(str(arg) for arg in args)
                key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
                cache_key = "|".join(key_parts)
            
            # Try to get from cache
            cached_result = await cache_manager.get(cache_key, level)
            if cached_result is not None:
                return cached_result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache_manager.set(cache_key, result, level, ttl)
            return result
        
        return wrapper
    return decorator


# Global cache manager instance
# CRITICAL FIX: Defer cache manager initialization to avoid event loop issues at import time
cache_manager = None

def get_cache_manager():
    """Get or create the cache manager instance."""
    global cache_manager
    if cache_manager is None:
        cache_manager = PerformanceOptimizedCache(max_size_mb=100)
    return cache_manager


class CacheManager:
    """Compatibility wrapper for authorization service."""
    
    def __init__(self):
        self._cache = get_cache_manager()
    
    async def get(self, key: str, default=None):
        """Get value from cache."""
        return await self._cache.get(key, CacheLevel.L2_SESSION, default)
    
    async def set(self, key: str, value: Any, ttl: int = 3600):
        """Set value in cache."""
        return await self._cache.set(key, value, CacheLevel.L2_SESSION, ttl)
    
    async def delete(self, key: str):
        """Delete value from cache."""
        await self._cache.invalidate(key)
    
    def get_metrics(self):
        """Get cache metrics."""
        return self._cache.get_metrics()


# Authorization-specific cache convenience functions for <100ms targets
async def cache_authorization_result(user_id: str, resource_id: str, resource_type: str, 
                                   auth_data: Dict[str, Any], ttl_seconds: int = 900) -> bool:
    """Cache authorization result for fast retrieval (<100ms target)."""
    cache_key = f"auth:{user_id}:{resource_type}:{resource_id}"
    cache = get_cache_manager()
    
    # Cache in L1 (5 min) and L2 (15 min) for optimal performance
    l1_success = await cache.set(cache_key, auth_data, CacheLevel.L1_MEMORY, ttl=300)
    l2_success = await cache.set(cache_key, auth_data, CacheLevel.L2_SESSION, ttl=ttl_seconds)
    
    return l1_success or l2_success

async def get_cached_authorization(user_id: str, resource_id: str, resource_type: str) -> Optional[Dict[str, Any]]:
    """Get cached authorization result with L1->L2->L3 fallback (<100ms target)."""
    cache_key = f"auth:{user_id}:{resource_type}:{resource_id}"
    cache = get_cache_manager()
    
    # Try L1 first (fastest)
    result = await cache.get(cache_key, CacheLevel.L1_MEMORY)
    if result is not None:
        return result
    
    # Try L2 second
    result = await cache.get(cache_key, CacheLevel.L2_SESSION)
    if result is not None:
        # Promote to L1 for next access
        await cache.set(cache_key, result, CacheLevel.L1_MEMORY, ttl=300)
        return result
    
    # Cache miss
    return None

async def invalidate_user_authorization_cache(user_id: str):
    """Invalidate all authorization cache entries for a user."""
    cache = get_cache_manager()
    pattern = f"auth:{user_id}:*"
    await cache.invalidate_pattern(pattern)

async def cache_user_session(user_id: str, session_data: Dict[str, Any], ttl_seconds: int = 1800):
    """Cache user session data for fast authentication (<100ms target)."""
    cache_key = f"user:session:{user_id}"
    cache = get_cache_manager()
    
    # Cache session data in L1 and L2
    await cache.set(cache_key, session_data, CacheLevel.L1_MEMORY, ttl=300)
    await cache.set(cache_key, session_data, CacheLevel.L2_SESSION, ttl=ttl_seconds)

async def get_cached_user_session(user_id: str) -> Optional[Dict[str, Any]]:
    """Get cached user session with fast retrieval (<100ms target)."""
    cache_key = f"user:session:{user_id}"
    cache = get_cache_manager()
    
    # Try L1 first
    result = await cache.get(cache_key, CacheLevel.L1_MEMORY)
    if result is not None:
        return result
    
    # Try L2
    result = await cache.get(cache_key, CacheLevel.L2_SESSION)
    if result is not None:
        # Promote to L1
        await cache.set(cache_key, result, CacheLevel.L1_MEMORY, ttl=300)
        return result
    
    return None

async def cache_team_permissions(team_id: str, permissions_data: Dict[str, Any], ttl_seconds: int = 1200):
    """Cache team permissions for fast authorization checks (<100ms target)."""
    cache_key = f"team:permissions:{team_id}"
    cache = get_cache_manager()
    
    # Cache in L2 and L3 (team permissions don't change frequently)
    await cache.set(cache_key, permissions_data, CacheLevel.L2_SESSION, ttl=600)
    await cache.set(cache_key, permissions_data, CacheLevel.L3_PERSISTENT, ttl=ttl_seconds)

async def get_cache_performance_report() -> Dict[str, Any]:
    """Get comprehensive cache performance report for optimization analysis."""
    cache = get_cache_manager()
    metrics = cache.get_metrics()
    
    # Add performance recommendations
    recommendations = []
    
    perf_summary = metrics['performance_summary']
    if not perf_summary['performance_target_met']:
        if perf_summary['hit_rate_percent'] < 95.0:
            recommendations.append("Increase cache TTL values to improve hit rate")
        if perf_summary['avg_response_time_ms'] > 100.0:
            recommendations.append("Consider increasing L1 cache size or optimizing data structures")
    
    if metrics['cache_utilization']['utilization_percent'] > 80:
        recommendations.append("Cache utilization high - consider increasing max cache size")
    
    auth_metrics = metrics['authorization_metrics']
    if auth_metrics['auth_hit_rate_percent'] < 90.0 and auth_metrics['auth_total_requests'] > 100:
        recommendations.append("Authorization cache hit rate below optimal - review TTL settings")
    
    metrics['performance_recommendations'] = recommendations
    return metrics

# Global cache manager instance for authorization service compatibility
cache_manager = None