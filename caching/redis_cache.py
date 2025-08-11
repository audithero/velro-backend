"""
Redis-based caching system for authorization and performance optimization.
Provides multi-level caching with intelligent cache warming and invalidation.
"""

import redis
import json
import pickle
import hashlib
import time
import logging
from typing import Any, Dict, List, Optional, Union, Callable, Set
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import asyncio
import threading
from contextlib import contextmanager
from enum import Enum

from monitoring.metrics import metrics_collector
from config import settings

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """Cache level enumeration for multi-tier caching."""
    L1_MEMORY = "l1_memory"
    L2_REDIS = "l2_redis"
    L3_DATABASE = "l3_database"


@dataclass
class CacheEntry:
    """Structured cache entry with metadata."""
    key: str
    value: Any
    created_at: datetime
    expires_at: Optional[datetime]
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    tags: Set[str] = None
    cache_level: CacheLevel = CacheLevel.L2_REDIS
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = set()
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def time_to_live(self) -> Optional[int]:
        """Get remaining TTL in seconds."""
        if self.expires_at is None:
            return None
        delta = self.expires_at - datetime.utcnow()
        return max(0, int(delta.total_seconds()))
    
    def access(self):
        """Record access to this cache entry."""
        self.access_count += 1
        self.last_accessed = datetime.utcnow()


class RedisCache:
    """
    High-performance Redis cache with monitoring and optimization.
    Supports compression, serialization, and intelligent key management.
    """
    
    def __init__(self, 
                 redis_url: Optional[str] = None,
                 key_prefix: str = "velro:",
                 default_ttl: int = 3600,
                 max_connections: int = 20,
                 compression_enabled: bool = True):
        
        self.redis_url = redis_url or settings.redis_url or "redis://localhost:6379"
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.compression_enabled = compression_enabled
        
        # Redis connection with connection pooling
        self.connection_pool = redis.ConnectionPool.from_url(
            self.redis_url,
            max_connections=max_connections,
            retry_on_timeout=True,
            socket_keepalive=True,
            socket_keepalive_options={}
        )
        
        self.redis_client = redis.Redis(connection_pool=self.connection_pool)
        
        # Local memory cache for frequently accessed items
        self._memory_cache: Dict[str, CacheEntry] = {}
        self._memory_cache_lock = threading.Lock()
        self._memory_cache_max_size = 1000
        
        # Performance tracking
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'errors': 0
        }
        self._stats_lock = threading.Lock()
        
        # Health check
        self._test_connection()
    
    def _test_connection(self):
        """Test Redis connection on initialization."""
        try:
            self.redis_client.ping()
            logger.info(f"✅ Redis cache connected to {self.redis_url}")
        except Exception as e:
            logger.error(f"❌ Redis cache connection failed: {e}")
            raise ConnectionError(f"Failed to connect to Redis: {e}")
    
    def _make_key(self, key: str) -> str:
        """Create prefixed cache key."""
        return f"{self.key_prefix}{key}"
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value with optional compression."""
        try:
            # Use pickle for Python objects
            serialized = pickle.dumps(value)
            
            # Apply compression if enabled and beneficial
            if self.compression_enabled and len(serialized) > 1024:
                import gzip
                compressed = gzip.compress(serialized)
                if len(compressed) < len(serialized) * 0.9:  # 10% savings minimum
                    return b'GZIP:' + compressed
            
            return b'RAW:' + serialized
            
        except Exception as e:
            logger.error(f"Serialization failed for key: {e}")
            raise
    
    def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize value with decompression support."""
        try:
            if data.startswith(b'GZIP:'):
                import gzip
                decompressed = gzip.decompress(data[5:])
                return pickle.loads(decompressed)
            elif data.startswith(b'RAW:'):
                return pickle.loads(data[4:])
            else:
                # Legacy format
                return pickle.loads(data)
                
        except Exception as e:
            logger.error(f"Deserialization failed: {e}")
            raise
    
    def _update_stats(self, operation: str):
        """Update operation statistics."""
        with self._stats_lock:
            if operation in self._stats:
                self._stats[operation] += 1
    
    def _check_memory_cache(self, key: str) -> Optional[Any]:
        """Check L1 memory cache."""
        with self._memory_cache_lock:
            entry = self._memory_cache.get(key)
            if entry and not entry.is_expired():
                entry.access()
                return entry.value
            elif entry:
                # Remove expired entry
                del self._memory_cache[key]
        return None
    
    def _set_memory_cache(self, key: str, value: Any, ttl: Optional[int] = None):
        """Set value in L1 memory cache."""
        with self._memory_cache_lock:
            # Evict oldest entries if cache is full
            if len(self._memory_cache) >= self._memory_cache_max_size:
                oldest_key = min(self._memory_cache.keys(), 
                               key=lambda k: self._memory_cache[k].created_at)
                del self._memory_cache[oldest_key]
            
            expires_at = None
            if ttl:
                expires_at = datetime.utcnow() + timedelta(seconds=ttl)
            
            self._memory_cache[key] = CacheEntry(
                key=key,
                value=value,
                created_at=datetime.utcnow(),
                expires_at=expires_at,
                cache_level=CacheLevel.L1_MEMORY
            )
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get value from cache with multi-level checking.
        First checks L1 memory cache, then L2 Redis cache.
        """
        full_key = self._make_key(key)
        start_time = time.time()
        
        try:
            # Check L1 memory cache first
            memory_value = self._check_memory_cache(key)
            if memory_value is not None:
                duration = time.time() - start_time
                metrics_collector.cache_metrics.record_cache_operation(
                    "authorization", "get", "hit", duration, "memory"
                )
                self._update_stats('hits')
                return memory_value
            
            # Check L2 Redis cache
            redis_data = self.redis_client.get(full_key)
            if redis_data is not None:
                value = self._deserialize_value(redis_data)
                
                # Store in memory cache for faster future access
                self._set_memory_cache(key, value)
                
                duration = time.time() - start_time
                metrics_collector.cache_metrics.record_cache_operation(
                    "authorization", "get", "hit", duration, "redis"
                )
                self._update_stats('hits')
                return value
            
            # Cache miss
            duration = time.time() - start_time
            metrics_collector.cache_metrics.record_cache_operation(
                "authorization", "get", "miss", duration
            )
            self._update_stats('misses')
            return default
            
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            self._update_stats('errors')
            return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None, 
            tags: Optional[Set[str]] = None) -> bool:
        """
        Set value in cache with TTL and tag support.
        Stores in both memory and Redis caches.
        """
        full_key = self._make_key(key)
        start_time = time.time()
        ttl = ttl or self.default_ttl
        
        try:
            # Serialize value
            serialized_value = self._serialize_value(value)
            
            # Set in Redis with TTL
            success = self.redis_client.setex(full_key, ttl, serialized_value)
            
            if success:
                # Set in memory cache
                self._set_memory_cache(key, value, ttl)
                
                # Store tags for invalidation
                if tags:
                    self._store_tags(key, tags)
                
                duration = time.time() - start_time
                metrics_collector.cache_metrics.record_cache_operation(
                    "authorization", "set", "success", duration
                )
                self._update_stats('sets')
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            self._update_stats('errors')
            return False
    
    def delete(self, key: str) -> bool:
        """Delete value from all cache levels."""
        full_key = self._make_key(key)
        start_time = time.time()
        
        try:
            # Remove from memory cache
            with self._memory_cache_lock:
                self._memory_cache.pop(key, None)
            
            # Remove from Redis
            deleted = self.redis_client.delete(full_key)
            
            # Clean up tags
            self._remove_tags(key)
            
            duration = time.time() - start_time
            metrics_collector.cache_metrics.record_cache_operation(
                "authorization", "delete", "success", duration
            )
            self._update_stats('deletes')
            return deleted > 0
            
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            self._update_stats('errors')
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            full_key = self._make_key(key)
            return self.redis_client.exists(full_key) > 0
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    def ttl(self, key: str) -> int:
        """Get TTL for key in seconds."""
        try:
            full_key = self._make_key(key)
            return self.redis_client.ttl(full_key)
        except Exception as e:
            logger.error(f"Cache TTL error for key {key}: {e}")
            return -1
    
    def expire(self, key: str, ttl: int) -> bool:
        """Set new TTL for existing key."""
        try:
            full_key = self._make_key(key)
            return self.redis_client.expire(full_key, ttl)
        except Exception as e:
            logger.error(f"Cache expire error for key {key}: {e}")
            return False
    
    def _store_tags(self, key: str, tags: Set[str]):
        """Store tags for cache invalidation."""
        try:
            for tag in tags:
                tag_key = self._make_key(f"tag:{tag}")
                self.redis_client.sadd(tag_key, key)
                self.redis_client.expire(tag_key, self.default_ttl * 2)  # Tags live longer
        except Exception as e:
            logger.error(f"Error storing tags for key {key}: {e}")
    
    def _remove_tags(self, key: str):
        """Remove key from all tag sets."""
        try:
            # This is expensive, but needed for cleanup
            # In production, consider using a different approach
            tag_pattern = self._make_key("tag:*")
            for tag_key in self.redis_client.scan_iter(match=tag_pattern):
                self.redis_client.srem(tag_key, key)
        except Exception as e:
            logger.error(f"Error removing tags for key {key}: {e}")
    
    def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all cache entries with specified tag."""
        try:
            tag_key = self._make_key(f"tag:{tag}")
            keys_to_delete = list(self.redis_client.smembers(tag_key))
            
            if keys_to_delete:
                # Delete the actual cache entries
                full_keys = [self._make_key(key.decode() if isinstance(key, bytes) else key) 
                           for key in keys_to_delete]
                deleted = self.redis_client.delete(*full_keys)
                
                # Remove from memory cache
                with self._memory_cache_lock:
                    for key in keys_to_delete:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        self._memory_cache.pop(key_str, None)
                
                # Delete the tag set
                self.redis_client.delete(tag_key)
                
                logger.info(f"Invalidated {deleted} cache entries with tag '{tag}'")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Error invalidating cache by tag {tag}: {e}")
            return 0
    
    def clear_all(self) -> bool:
        """Clear all cache entries with the current prefix."""
        try:
            pattern = f"{self.key_prefix}*"
            keys = list(self.redis_client.scan_iter(match=pattern))
            
            if keys:
                deleted = self.redis_client.delete(*keys)
                logger.info(f"Cleared {deleted} cache entries")
            
            # Clear memory cache
            with self._memory_cache_lock:
                self._memory_cache.clear()
            
            return True
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        try:
            with self._stats_lock:
                stats = self._stats.copy()
            
            # Calculate hit rate
            total_operations = stats['hits'] + stats['misses']
            hit_rate = (stats['hits'] / total_operations * 100) if total_operations > 0 else 0
            
            # Redis info
            redis_info = self.redis_client.info()
            
            # Memory cache info
            with self._memory_cache_lock:
                memory_cache_size = len(self._memory_cache)
            
            return {
                'operations': stats,
                'hit_rate_percent': round(hit_rate, 2),
                'memory_cache_entries': memory_cache_size,
                'redis_info': {
                    'used_memory': redis_info.get('used_memory', 0),
                    'connected_clients': redis_info.get('connected_clients', 0),
                    'total_commands_processed': redis_info.get('total_commands_processed', 0),
                    'keyspace_hits': redis_info.get('keyspace_hits', 0),
                    'keyspace_misses': redis_info.get('keyspace_misses', 0)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e)}
    
    def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check."""
        try:
            start_time = time.time()
            
            # Test basic operations
            test_key = "health_check_test"
            test_value = {"timestamp": time.time(), "test": True}
            
            # Test set
            set_success = self.set(test_key, test_value, ttl=60)
            
            # Test get
            retrieved_value = self.get(test_key)
            get_success = retrieved_value == test_value
            
            # Test delete
            delete_success = self.delete(test_key)
            
            # Check Redis connection
            ping_success = self.redis_client.ping()
            
            # Calculate response time
            response_time = (time.time() - start_time) * 1000  # ms
            
            # Get memory usage
            info = self.redis_client.info()
            
            health_status = {
                'status': 'healthy' if all([set_success, get_success, delete_success, ping_success]) else 'unhealthy',
                'response_time_ms': round(response_time, 2),
                'operations_test': {
                    'set': set_success,
                    'get': get_success,
                    'delete': delete_success,
                    'ping': ping_success
                },
                'redis_info': {
                    'used_memory_mb': round(info.get('used_memory', 0) / (1024 * 1024), 2),
                    'connected_clients': info.get('connected_clients', 0),
                    'uptime_seconds': info.get('uptime_in_seconds', 0)
                },
                'timestamp': datetime.utcnow().isoformat()
            }
            
            return health_status
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }
    
    @contextmanager
    def pipeline(self):
        """Context manager for Redis pipeline operations."""
        pipe = self.redis_client.pipeline()
        try:
            yield pipe
            pipe.execute()
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            raise
        finally:
            pipe.reset()
    
    def close(self):
        """Close Redis connection."""
        try:
            self.connection_pool.disconnect()
            logger.info("Redis cache connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")


class AuthorizationCache(RedisCache):
    """
    Specialized cache for authorization data with optimized patterns.
    Provides user permissions, role caching, and session management.
    """
    
    def __init__(self, **kwargs):
        super().__init__(key_prefix="auth:", default_ttl=1800, **kwargs)  # 30 minutes
    
    def cache_user_permissions(self, user_id: str, permissions: List[str], 
                              ttl: int = 1800) -> bool:
        """Cache user permissions with role-based tags."""
        key = f"user_permissions:{user_id}"
        tags = {"user_permissions", f"user:{user_id}"}
        return self.set(key, permissions, ttl=ttl, tags=tags)
    
    def get_user_permissions(self, user_id: str) -> Optional[List[str]]:
        """Get cached user permissions."""
        key = f"user_permissions:{user_id}"
        return self.get(key)
    
    def cache_role_permissions(self, role: str, permissions: List[str], 
                              ttl: int = 3600) -> bool:
        """Cache role permissions (longer TTL as roles change less frequently)."""
        key = f"role_permissions:{role}"
        tags = {"role_permissions", f"role:{role}"}
        return self.set(key, permissions, ttl=ttl, tags=tags)
    
    def get_role_permissions(self, role: str) -> Optional[List[str]]:
        """Get cached role permissions."""
        key = f"role_permissions:{role}"
        return self.get(key)
    
    def cache_authorization_result(self, user_id: str, resource: str, 
                                  action: str, result: bool, ttl: int = 300) -> bool:
        """Cache specific authorization result (shorter TTL for security)."""
        key = f"authz_result:{user_id}:{resource}:{action}"
        tags = {"authz_results", f"user:{user_id}", f"resource:{resource}"}
        return self.set(key, result, ttl=ttl, tags=tags)
    
    def get_authorization_result(self, user_id: str, resource: str, 
                               action: str) -> Optional[bool]:
        """Get cached authorization result."""
        key = f"authz_result:{user_id}:{resource}:{action}"
        return self.get(key)
    
    def invalidate_user_cache(self, user_id: str) -> int:
        """Invalidate all cache entries for a specific user."""
        return self.invalidate_by_tag(f"user:{user_id}")
    
    def invalidate_role_cache(self, role: str) -> int:
        """Invalidate all cache entries for a specific role."""
        return self.invalidate_by_tag(f"role:{role}")
    
    def invalidate_resource_cache(self, resource: str) -> int:
        """Invalidate all cache entries for a specific resource."""
        return self.invalidate_by_tag(f"resource:{resource}")


class UserSessionCache(RedisCache):
    """
    Specialized cache for user session data with session management.
    Handles JWT tokens, session state, and user presence tracking.
    """
    
    def __init__(self, **kwargs):
        super().__init__(key_prefix="session:", default_ttl=7200, **kwargs)  # 2 hours
    
    def cache_user_session(self, user_id: str, session_data: Dict[str, Any], 
                          ttl: int = 7200) -> bool:
        """Cache user session data."""
        key = f"user_session:{user_id}"
        tags = {"user_sessions", f"user:{user_id}"}
        return self.set(key, session_data, ttl=ttl, tags=tags)
    
    def get_user_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get cached user session data."""
        key = f"user_session:{user_id}"
        return self.get(key)
    
    def cache_jwt_token(self, token_hash: str, user_id: str, expires_at: datetime) -> bool:
        """Cache JWT token with expiration tracking."""
        key = f"jwt_token:{token_hash}"
        ttl = int((expires_at - datetime.utcnow()).total_seconds())
        if ttl <= 0:
            return False
        
        token_data = {
            "user_id": user_id,
            "expires_at": expires_at.isoformat(),
            "cached_at": datetime.utcnow().isoformat()
        }
        tags = {"jwt_tokens", f"user:{user_id}"}
        return self.set(key, token_data, ttl=ttl, tags=tags)
    
    def get_jwt_token_data(self, token_hash: str) -> Optional[Dict[str, Any]]:
        """Get cached JWT token data."""
        key = f"jwt_token:{token_hash}"
        return self.get(key)
    
    def invalidate_jwt_token(self, token_hash: str) -> bool:
        """Invalidate specific JWT token."""
        key = f"jwt_token:{token_hash}"
        return self.delete(key)
    
    def invalidate_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a specific user."""
        return self.invalidate_by_tag(f"user:{user_id}")
    
    def track_user_activity(self, user_id: str, activity: str, 
                           metadata: Dict[str, Any] = None) -> bool:
        """Track user activity for session management."""
        key = f"user_activity:{user_id}"
        activity_data = {
            "activity": activity,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }
        return self.set(key, activity_data, ttl=3600)  # 1 hour
    
    def get_user_activity(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get last user activity."""
        key = f"user_activity:{user_id}"
        return self.get(key)


class PermissionCache(RedisCache):
    """
    Specialized cache for permission and access control data.
    Optimized for high-frequency permission checks with pre-computed results.
    """
    
    def __init__(self, **kwargs):
        super().__init__(key_prefix="perm:", default_ttl=3600, **kwargs)  # 1 hour
    
    def cache_permission_matrix(self, user_id: str, resource_permissions: Dict[str, List[str]], 
                               ttl: int = 3600) -> bool:
        """Cache complete permission matrix for user."""
        key = f"permission_matrix:{user_id}"
        tags = {"permission_matrices", f"user:{user_id}"}
        return self.set(key, resource_permissions, ttl=ttl, tags=tags)
    
    def get_permission_matrix(self, user_id: str) -> Optional[Dict[str, List[str]]]:
        """Get cached permission matrix."""
        key = f"permission_matrix:{user_id}"
        return self.get(key)
    
    def cache_resource_access_list(self, resource: str, user_actions: Dict[str, List[str]], 
                                  ttl: int = 1800) -> bool:
        """Cache resource access control list."""
        key = f"resource_acl:{resource}"
        tags = {"resource_acls", f"resource:{resource}"}
        return self.set(key, user_actions, ttl=ttl, tags=tags)
    
    def get_resource_access_list(self, resource: str) -> Optional[Dict[str, List[str]]]:
        """Get cached resource ACL."""
        key = f"resource_acl:{resource}"
        return self.get(key)
    
    def cache_frequently_checked_permissions(self, permission_results: Dict[str, bool], 
                                           ttl: int = 300) -> bool:
        """Cache frequently checked permission results for fast lookup."""
        key = "frequent_permissions"
        return self.set(key, permission_results, ttl=ttl)
    
    def get_frequently_checked_permissions(self) -> Optional[Dict[str, bool]]:
        """Get cached frequent permissions."""
        key = "frequent_permissions"
        return self.get(key)
    
    def invalidate_resource_permissions(self, resource: str) -> int:
        """Invalidate all permission caches for a resource."""
        return self.invalidate_by_tag(f"resource:{resource}")


# Global cache instances - lazy initialization to avoid import-time Redis connection
authorization_cache = None
user_session_cache = None
permission_cache = None

def get_authorization_cache():
    """Get or create the authorization cache instance."""
    global authorization_cache
    if authorization_cache is None:
        authorization_cache = AuthorizationCache()
    return authorization_cache

def get_user_session_cache():
    """Get or create the user session cache instance."""
    global user_session_cache
    if user_session_cache is None:
        user_session_cache = UserSessionCache()
    return user_session_cache

def get_permission_cache():
    """Get or create the permission cache instance."""
    global permission_cache
    if permission_cache is None:
        permission_cache = PermissionCache()
    return permission_cache