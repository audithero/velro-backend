"""
Enterprise Redis Cache Manager
Implements multi-level caching with intelligent invalidation, connection pooling,
and performance monitoring as specified in UUID Validation Standards.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import hashlib
import pickle
from contextlib import asynccontextmanager

import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import ConnectionError, TimeoutError, RedisError

from database import get_database
from utils.performance_monitor import performance_monitor

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """Multi-level cache hierarchy for optimal performance."""
    L1_MEMORY = "l1_memory"        # In-memory cache: 5min TTL, 98% hit rate target
    L2_REDIS = "l2_redis"          # Redis cache: 15min TTL, 85% hit rate target
    L3_DATABASE = "l3_database"    # Database cache: 1hr TTL, 70% hit rate target


class CacheOperation(Enum):
    """Cache operation types for metrics tracking."""
    GET = "get"
    SET = "set"
    DELETE = "delete"
    INVALIDATE = "invalidate"
    WARM = "warm"


@dataclass
class CacheMetrics:
    """Cache performance metrics for monitoring."""
    hits: int = 0
    misses: int = 0
    errors: int = 0
    total_operations: int = 0
    avg_response_time_ms: float = 0.0
    cache_size_bytes: int = 0
    evictions: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0


@dataclass
class RedisPoolConfig:
    """Redis connection pool configuration."""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    max_connections: int = 20
    min_idle_connections: int = 5
    connection_timeout: int = 5
    socket_timeout: int = 3
    socket_keepalive: bool = True
    socket_keepalive_options: Dict[int, int] = None
    retry_on_timeout: bool = True
    health_check_interval: int = 30


class EnterpriseRedisCacheManager:
    """
    Enterprise-grade Redis cache manager with:
    - Multi-level caching (L1: Memory, L2: Redis, L3: Database)
    - Connection pooling with health monitoring
    - Intelligent cache warming and invalidation
    - Performance metrics and alerting
    - Circuit breaker pattern for resilience
    """
    
    def __init__(self):
        self.pools: Dict[str, ConnectionPool] = {}
        self.clients: Dict[str, redis.Redis] = {}
        self.metrics: Dict[str, CacheMetrics] = {}
        self.l1_cache: Dict[str, Tuple[Any, float]] = {}  # In-memory L1 cache
        self.circuit_breaker_state = "closed"  # closed, open, half_open
        self.circuit_breaker_failures = 0
        self.circuit_breaker_last_failure = 0
        self.max_circuit_failures = 5
        self.circuit_recovery_timeout = 30
        
        # Performance monitoring
        self.performance_tracker = performance_monitor
        
    async def initialize_pools(self) -> None:
        """Initialize Redis connection pools from database configuration."""
        try:
            db = await get_database()
            
            # Get Redis configurations from database
            configs = await db.execute_query(
                table="redis_cache_config",
                operation="select",
                filters={"enabled": True}
            )
            
            for config in configs:
                pool_config = RedisPoolConfig(
                    host=config.get("redis_host", "localhost"),
                    port=config.get("redis_port", 6379),
                    db=config.get("redis_db", 0),
                    max_connections=config.get("max_connections", 20),
                    connection_timeout=config.get("connection_timeout_ms", 5000) / 1000,
                    socket_timeout=config.get("read_timeout_ms", 3000) / 1000
                )
                
                await self._create_pool(config["cache_name"], pool_config)
                
            logger.info("✅ Redis cache pools initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Redis pools: {e}")
            raise
    
    async def _create_pool(self, pool_name: str, config: RedisPoolConfig) -> None:
        """Create a Redis connection pool with health monitoring."""
        try:
            # Create connection pool
            pool = ConnectionPool(
                host=config.host,
                port=config.port,
                db=config.db,
                max_connections=config.max_connections,
                socket_timeout=config.socket_timeout,
                socket_connect_timeout=config.connection_timeout,
                socket_keepalive=config.socket_keepalive,
                retry_on_timeout=config.retry_on_timeout,
                health_check_interval=config.health_check_interval
            )
            
            # Create Redis client
            client = redis.Redis(connection_pool=pool, decode_responses=False)
            
            # Test connection
            await client.ping()
            
            self.pools[pool_name] = pool
            self.clients[pool_name] = client
            self.metrics[pool_name] = CacheMetrics()
            
            logger.info(f"✅ Redis pool '{pool_name}' created successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to create Redis pool '{pool_name}': {e}")
            self._handle_circuit_breaker_failure()
            raise
    
    def _handle_circuit_breaker_failure(self) -> None:
        """Handle circuit breaker failures for Redis operations."""
        self.circuit_breaker_failures += 1
        self.circuit_breaker_last_failure = time.time()
        
        if self.circuit_breaker_failures >= self.max_circuit_failures:
            self.circuit_breaker_state = "open"
            logger.warning(f"🚨 Circuit breaker OPEN - Redis operations suspended for {self.circuit_recovery_timeout}s")
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operations."""
        if self.circuit_breaker_state == "closed":
            return True
        elif self.circuit_breaker_state == "open":
            if time.time() - self.circuit_breaker_last_failure > self.circuit_recovery_timeout:
                self.circuit_breaker_state = "half_open"
                logger.info("🔄 Circuit breaker HALF_OPEN - Testing Redis connectivity")
                return True
            return False
        elif self.circuit_breaker_state == "half_open":
            return True
        return False
    
    def _reset_circuit_breaker(self) -> None:
        """Reset circuit breaker on successful operation."""
        if self.circuit_breaker_state == "half_open":
            self.circuit_breaker_state = "closed"
            self.circuit_breaker_failures = 0
            logger.info("✅ Circuit breaker CLOSED - Redis operations restored")
    
    async def get_multi_level(
        self, 
        key: str, 
        cache_name: str = "authorization_cache",
        fallback_function: Optional[Callable] = None
    ) -> Tuple[Any, CacheLevel]:
        """
        Multi-level cache get with automatic fallback:
        L1 (Memory) -> L2 (Redis) -> L3 (Database/Fallback)
        """
        start_time = time.time()
        
        try:
            # L1 Cache check (Memory)
            l1_result = self._get_l1_cache(key)
            if l1_result is not None:
                self._record_cache_hit(cache_name, CacheLevel.L1_MEMORY, start_time)
                return l1_result, CacheLevel.L1_MEMORY
            
            # L2 Cache check (Redis)
            if self._check_circuit_breaker():
                try:
                    l2_result = await self._get_l2_cache(key, cache_name)
                    if l2_result is not None:
                        # Promote to L1 cache
                        self._set_l1_cache(key, l2_result, ttl=300)  # 5 min L1 TTL
                        self._record_cache_hit(cache_name, CacheLevel.L2_REDIS, start_time)
                        self._reset_circuit_breaker()
                        return l2_result, CacheLevel.L2_REDIS
                        
                except RedisError as e:
                    logger.warning(f"⚠️ Redis L2 cache error: {e}")
                    self._handle_circuit_breaker_failure()
            
            # L3 Cache/Fallback
            if fallback_function:
                try:
                    l3_result = await fallback_function()
                    if l3_result is not None:
                        # Store in all cache levels
                        await self._store_in_all_caches(key, l3_result, cache_name)
                        self._record_cache_miss(cache_name, start_time)
                        return l3_result, CacheLevel.L3_DATABASE
                        
                except Exception as e:
                    logger.error(f"❌ Fallback function failed: {e}")
            
            # Cache miss - no data found
            self._record_cache_miss(cache_name, start_time)
            return None, CacheLevel.L3_DATABASE
            
        except Exception as e:
            logger.error(f"❌ Multi-level cache get failed for key '{key}': {e}")
            self.metrics[cache_name].errors += 1
            return None, CacheLevel.L3_DATABASE
    
    async def set_multi_level(
        self,
        key: str,
        value: Any,
        cache_name: str = "authorization_cache",
        l1_ttl: int = 300,    # 5 minutes
        l2_ttl: int = 900,    # 15 minutes
        l3_ttl: int = 3600    # 1 hour
    ) -> bool:
        """Set value in multiple cache levels with different TTLs."""
        try:
            success_count = 0
            
            # L1 Cache (Memory)
            if self._set_l1_cache(key, value, l1_ttl):
                success_count += 1
            
            # L2 Cache (Redis)
            if self._check_circuit_breaker():
                try:
                    if await self._set_l2_cache(key, value, cache_name, l2_ttl):
                        success_count += 1
                        self._reset_circuit_breaker()
                except RedisError as e:
                    logger.warning(f"⚠️ Redis L2 cache set error: {e}")
                    self._handle_circuit_breaker_failure()
            
            # L3 Cache (Database) - if configured
            # This would be handled by materialized views and database-level caching
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"❌ Multi-level cache set failed for key '{key}': {e}")
            return False
    
    def _get_l1_cache(self, key: str) -> Optional[Any]:
        """Get value from L1 in-memory cache."""
        if key in self.l1_cache:
            value, expires_at = self.l1_cache[key]
            if time.time() < expires_at:
                return value
            else:
                # Expired - remove from cache
                del self.l1_cache[key]
        return None
    
    def _set_l1_cache(self, key: str, value: Any, ttl: int) -> bool:
        """Set value in L1 in-memory cache."""
        try:
            expires_at = time.time() + ttl
            self.l1_cache[key] = (value, expires_at)
            return True
        except Exception as e:
            logger.error(f"❌ L1 cache set error: {e}")
            return False
    
    async def _get_l2_cache(self, key: str, cache_name: str) -> Optional[Any]:
        """Get value from L2 Redis cache."""
        if cache_name not in self.clients:
            return None
            
        try:
            client = self.clients[cache_name]
            data = await client.get(key)
            if data:
                # Try JSON first, then pickle for complex objects
                try:
                    return json.loads(data.decode('utf-8'))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return pickle.loads(data)
            return None
            
        except Exception as e:
            logger.error(f"❌ L2 cache get error: {e}")
            raise RedisError(f"L2 cache get failed: {e}")
    
    async def _set_l2_cache(self, key: str, value: Any, cache_name: str, ttl: int) -> bool:
        """Set value in L2 Redis cache."""
        if cache_name not in self.clients:
            return False
            
        try:
            client = self.clients[cache_name]
            
            # Serialize data (JSON for simple types, pickle for complex)
            try:
                data = json.dumps(value, default=str).encode('utf-8')
            except (TypeError, ValueError):
                data = pickle.dumps(value)
            
            await client.setex(key, ttl, data)
            return True
            
        except Exception as e:
            logger.error(f"❌ L2 cache set error: {e}")
            raise RedisError(f"L2 cache set failed: {e}")
    
    async def _store_in_all_caches(self, key: str, value: Any, cache_name: str) -> None:
        """Store value in all available cache levels."""
        await self.set_multi_level(key, value, cache_name)
    
    def _record_cache_hit(self, cache_name: str, level: CacheLevel, start_time: float) -> None:
        """Record cache hit metrics."""
        if cache_name in self.metrics:
            metrics = self.metrics[cache_name]
            metrics.hits += 1
            metrics.total_operations += 1
            
            response_time = (time.time() - start_time) * 1000
            metrics.avg_response_time_ms = (
                (metrics.avg_response_time_ms * (metrics.total_operations - 1) + response_time) /
                metrics.total_operations
            )
    
    def _record_cache_miss(self, cache_name: str, start_time: float) -> None:
        """Record cache miss metrics."""
        if cache_name in self.metrics:
            metrics = self.metrics[cache_name]
            metrics.misses += 1
            metrics.total_operations += 1
            
            response_time = (time.time() - start_time) * 1000
            metrics.avg_response_time_ms = (
                (metrics.avg_response_time_ms * (metrics.total_operations - 1) + response_time) /
                metrics.total_operations
            )
    
    async def invalidate_pattern(
        self, 
        pattern: str, 
        cache_name: str = "authorization_cache"
    ) -> int:
        """Invalidate cache keys matching a pattern."""
        try:
            invalidated_count = 0
            
            # L1 Cache invalidation
            keys_to_remove = [k for k in self.l1_cache.keys() if self._matches_pattern(k, pattern)]
            for key in keys_to_remove:
                del self.l1_cache[key]
                invalidated_count += 1
            
            # L2 Cache invalidation (Redis)
            if self._check_circuit_breaker() and cache_name in self.clients:
                try:
                    client = self.clients[cache_name]
                    redis_keys = await client.keys(pattern)
                    if redis_keys:
                        deleted = await client.delete(*redis_keys)
                        invalidated_count += deleted
                        self._reset_circuit_breaker()
                        
                except RedisError as e:
                    logger.warning(f"⚠️ Redis pattern invalidation error: {e}")
                    self._handle_circuit_breaker_failure()
            
            if invalidated_count > 0:
                logger.info(f"🗑️ Invalidated {invalidated_count} cache entries for pattern: {pattern}")
            
            return invalidated_count
            
        except Exception as e:
            logger.error(f"❌ Cache pattern invalidation failed: {e}")
            return 0
    
    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches Redis-style pattern."""
        import fnmatch
        return fnmatch.fnmatch(key, pattern.replace('*', '*'))
    
    async def warm_cache_patterns(self, cache_name: str = "authorization_cache") -> Dict[str, int]:
        """Warm cache with predefined patterns from database configuration."""
        try:
            db = await get_database()
            
            # Get cache warming patterns
            patterns = await db.execute_query(
                table="cache_warming_patterns",
                operation="select",
                filters={"cache_name": cache_name, "enabled": True},
                order_by="priority ASC"
            )
            
            warming_results = {}
            
            for pattern in patterns:
                try:
                    warmed_count = await self._warm_pattern(
                        pattern["key_pattern"],
                        pattern["warm_batch_size"],
                        cache_name
                    )
                    warming_results[pattern["pattern_name"]] = warmed_count
                    
                    # Update warming statistics
                    await db.execute_query(
                        table="cache_warming_patterns",
                        operation="update",
                        filters={"id": pattern["id"]},
                        data={"last_warmed": datetime.utcnow()}
                    )
                    
                except Exception as e:
                    logger.error(f"❌ Cache warming failed for pattern '{pattern['pattern_name']}': {e}")
                    warming_results[pattern["pattern_name"]] = 0
            
            total_warmed = sum(warming_results.values())
            logger.info(f"🔥 Cache warming completed: {total_warmed} entries warmed")
            
            return warming_results
            
        except Exception as e:
            logger.error(f"❌ Cache warming failed: {e}")
            return {}
    
    async def _warm_pattern(self, key_pattern: str, batch_size: int, cache_name: str) -> int:
        """Warm cache for a specific pattern."""
        # This would implement specific warming logic based on the pattern
        # For example, pre-loading user permissions, team memberships, etc.
        
        if key_pattern.startswith("perm:"):
            return await self._warm_permission_cache(batch_size, cache_name)
        elif key_pattern.startswith("team:"):
            return await self._warm_team_cache(batch_size, cache_name)
        elif key_pattern.startswith("gen:"):
            return await self._warm_generation_cache(batch_size, cache_name)
        
        return 0
    
    async def _warm_permission_cache(self, batch_size: int, cache_name: str) -> int:
        """Warm authorization permission cache."""
        try:
            db = await get_database()
            
            # Get recent authorization context from materialized view
            recent_authorizations = await db.execute_query(
                table="mv_user_authorization_context",
                operation="select",
                limit=batch_size,
                order_by="created_at DESC"
            )
            
            warmed_count = 0
            for auth in recent_authorizations:
                cache_key = f"perm:{auth['user_id']}:{auth['generation_id']}"
                cache_value = {
                    "access_granted": auth["has_read_access"],
                    "access_method": auth["access_method"],
                    "effective_role": auth["effective_role"],
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                if await self.set_multi_level(cache_key, cache_value, cache_name):
                    warmed_count += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"❌ Permission cache warming failed: {e}")
            return 0
    
    async def _warm_team_cache(self, batch_size: int, cache_name: str) -> int:
        """Warm team membership cache."""
        try:
            db = await get_database()
            
            # Get active team memberships
            team_memberships = await db.execute_query(
                table="team_members",
                operation="select",
                filters={"is_active": True},
                limit=batch_size,
                order_by="joined_at DESC"
            )
            
            warmed_count = 0
            for membership in team_memberships:
                cache_key = f"team:{membership['user_id']}:{membership['team_id']}"
                cache_value = {
                    "team_id": membership["team_id"],
                    "role": membership["role"],
                    "is_active": membership["is_active"],
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                if await self.set_multi_level(cache_key, cache_value, cache_name):
                    warmed_count += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"❌ Team cache warming failed: {e}")
            return 0
    
    async def _warm_generation_cache(self, batch_size: int, cache_name: str) -> int:
        """Warm generation metadata cache."""
        try:
            db = await get_database()
            
            # Get recent completed generations
            generations = await db.execute_query(
                table="generations",
                operation="select",
                filters={"status": "completed"},
                limit=batch_size,
                order_by="created_at DESC"
            )
            
            warmed_count = 0
            for gen in generations:
                cache_key = f"gen:{gen['id']}"
                cache_value = {
                    "generation_id": gen["id"],
                    "user_id": gen["user_id"],
                    "project_id": gen["project_id"],
                    "status": gen["status"],
                    "output_urls": gen.get("output_urls"),
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                if await self.set_multi_level(cache_key, cache_value, cache_name):
                    warmed_count += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"❌ Generation cache warming failed: {e}")
            return 0
    
    async def get_cache_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get comprehensive cache performance metrics."""
        metrics_summary = {}
        
        for cache_name, metrics in self.metrics.items():
            metrics_summary[cache_name] = {
                "hit_rate_percent": metrics.hit_rate,
                "total_operations": metrics.total_operations,
                "hits": metrics.hits,
                "misses": metrics.misses,
                "errors": metrics.errors,
                "avg_response_time_ms": metrics.avg_response_time_ms,
                "cache_size_bytes": metrics.cache_size_bytes,
                "evictions": metrics.evictions,
                "circuit_breaker_state": self.circuit_breaker_state,
                "l1_cache_size": len(self.l1_cache)
            }
        
        return metrics_summary
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for all cache levels."""
        health_status = {
            "overall_healthy": True,
            "l1_cache": {
                "status": "healthy",
                "entries": len(self.l1_cache),
                "memory_usage_estimate": len(str(self.l1_cache))
            },
            "l2_redis": {},
            "circuit_breaker": {
                "state": self.circuit_breaker_state,
                "failures": self.circuit_breaker_failures
            },
            "performance": await self.get_cache_metrics()
        }
        
        # Check Redis health
        for cache_name, client in self.clients.items():
            try:
                start_time = time.time()
                await client.ping()
                response_time = (time.time() - start_time) * 1000
                
                info = await client.info()
                
                health_status["l2_redis"][cache_name] = {
                    "status": "healthy",
                    "ping_response_time_ms": response_time,
                    "connected_clients": info.get("connected_clients", 0),
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0)
                }
                
            except Exception as e:
                health_status["overall_healthy"] = False
                health_status["l2_redis"][cache_name] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        
        return health_status
    
    async def cleanup_expired_entries(self) -> Dict[str, int]:
        """Clean up expired cache entries."""
        cleanup_results = {}
        
        # L1 Cache cleanup
        current_time = time.time()
        expired_l1_keys = [
            key for key, (_, expires_at) in self.l1_cache.items()
            if current_time >= expires_at
        ]
        
        for key in expired_l1_keys:
            del self.l1_cache[key]
        
        cleanup_results["l1_expired_entries"] = len(expired_l1_keys)
        
        # L2 Redis cleanup is handled automatically by Redis TTL
        cleanup_results["l2_redis_cleanup"] = "automatic_ttl"
        
        if expired_l1_keys:
            logger.info(f"🧹 Cleaned up {len(expired_l1_keys)} expired L1 cache entries")
        
        return cleanup_results
    
    async def close_all_connections(self) -> None:
        """Close all Redis connections gracefully."""
        try:
            for cache_name, client in self.clients.items():
                await client.close()
                logger.info(f"✅ Closed Redis client for '{cache_name}'")
            
            for pool_name, pool in self.pools.items():
                await pool.disconnect()
                logger.info(f"✅ Disconnected Redis pool '{pool_name}'")
            
            self.clients.clear()
            self.pools.clear()
            
        except Exception as e:
            logger.error(f"❌ Error closing Redis connections: {e}")


# Global instance
enterprise_redis_cache = EnterpriseRedisCacheManager()


# Context manager for automatic connection management
@asynccontextmanager
async def redis_cache_context():
    """Context manager for Redis cache operations."""
    try:
        await enterprise_redis_cache.initialize_pools()
        yield enterprise_redis_cache
    finally:
        await enterprise_redis_cache.close_all_connections()


# Convenience functions for common operations
async def get_cached_authorization(user_id: str, resource_id: str, resource_type: str) -> Optional[Dict[str, Any]]:
    """Get cached authorization result."""
    cache_key = f"perm:{user_id}:{resource_id}:{resource_type}"
    result, _ = await enterprise_redis_cache.get_multi_level(cache_key)
    return result


async def cache_authorization_result(
    user_id: str, 
    resource_id: str, 
    resource_type: str,
    authorization_data: Dict[str, Any]
) -> bool:
    """Cache authorization result with multi-level storage."""
    cache_key = f"perm:{user_id}:{resource_id}:{resource_type}"
    return await enterprise_redis_cache.set_multi_level(cache_key, authorization_data)


async def invalidate_user_cache(user_id: str) -> int:
    """Invalidate all cache entries for a specific user."""
    pattern = f"*{user_id}*"
    return await enterprise_redis_cache.invalidate_pattern(pattern)


async def warm_authorization_cache() -> Dict[str, int]:
    """Warm the authorization cache with recent data."""
    return await enterprise_redis_cache.warm_cache_patterns("authorization_cache")