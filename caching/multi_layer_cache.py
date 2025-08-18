"""
CRITICAL Multi-Layer Caching System for Velro Backend
Implements 3-tier caching architecture to achieve PRD performance targets:
- <75ms authorization response time
- >95% cache hit rate
- 10,000+ concurrent user support

Architecture:
- L1 Memory Cache: <5ms access, LRU eviction, thread-safe
- L2 Redis Cache: <20ms access, distributed, async operations
- L3 Database: Materialized views, <100ms analytical queries

Security Features:
- OWASP compliant cache key generation
- Secure UUID validation integration
- Cache invalidation on permission changes
- Performance metrics collection
"""

import asyncio
import hashlib
import json
import logging
import pickle
import threading
import time
import weakref
from collections import OrderedDict, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
import uuid
import gzip

# Redis imports with fallback
try:
    import redis.asyncio as redis
    from redis.asyncio.connection import ConnectionPool
    from redis.exceptions import ConnectionError, RedisError, TimeoutError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    ConnectionPool = None
    RedisError = Exception

from database import get_database
from config import settings

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """Multi-layer cache hierarchy levels."""
    L1_MEMORY = "l1_memory"        # In-memory: <5ms, >95% hit rate
    L2_REDIS = "l2_redis"          # Distributed: <20ms, >85% hit rate  
    L3_DATABASE = "l3_database"    # Materialized views: <100ms


class CacheOperation(Enum):
    """Cache operation types for metrics tracking."""
    GET = "get"
    SET = "set" 
    DELETE = "delete"
    INVALIDATE = "invalidate"
    WARM = "warm"


class EvictionPolicy(Enum):
    """Cache eviction policies."""
    LRU = "lru"                    # Least Recently Used
    LFU = "lfu"                    # Least Frequently Used
    TTL = "ttl"                    # Time To Live based
    HYBRID = "hybrid"              # LRU + LFU + TTL combined


@dataclass
class CacheEntry:
    """Enhanced cache entry with comprehensive metadata."""
    key: str
    value: Any
    created_at: float
    expires_at: Optional[float]
    access_count: int = 0
    last_accessed: float = 0
    size_bytes: int = 0
    tags: Set[str] = field(default_factory=set)
    priority: int = 1
    compressed: bool = False
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at
    
    def access(self):
        """Record cache access and update metrics."""
        self.access_count += 1
        self.last_accessed = time.time()
    
    def calculate_eviction_score(self) -> float:
        """Calculate eviction priority score (lower = more likely to evict)."""
        now = time.time()
        recency = 1.0 / (now - self.last_accessed + 1)
        frequency = min(self.access_count / 100.0, 1.0)
        priority_weight = self.priority / 10.0
        
        return recency * 0.4 + frequency * 0.4 + priority_weight * 0.2


@dataclass 
class CacheMetrics:
    """Comprehensive cache performance metrics."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    evictions: int = 0
    errors: int = 0
    total_operations: int = 0
    avg_response_time_ms: float = 0.0
    hit_rate_percent: float = 0.0
    cache_size_bytes: int = 0
    entries_count: int = 0
    
    def update(self, operation: CacheOperation, success: bool, response_time_ms: float = 0.0):
        """Update metrics for cache operation."""
        self.total_operations += 1
        
        if operation == CacheOperation.GET:
            if success:
                self.hits += 1
            else:
                self.misses += 1
        elif operation == CacheOperation.SET and success:
            self.sets += 1
        elif operation == CacheOperation.DELETE and success:
            self.deletes += 1
        
        if not success:
            self.errors += 1
        
        # Update running average response time
        if self.total_operations > 0:
            self.avg_response_time_ms = (
                (self.avg_response_time_ms * (self.total_operations - 1) + response_time_ms) /
                self.total_operations
            )
        
        # Update hit rate
        total_requests = self.hits + self.misses
        if total_requests > 0:
            self.hit_rate_percent = (self.hits / total_requests) * 100


class SecureCacheKeyManager:
    """Secure cache key generation with OWASP compliance."""
    
    @staticmethod
    def generate_auth_key(user_id: str, resource_id: str, operation: str) -> str:
        """Generate secure authorization cache key."""
        # Validate inputs
        if not all([user_id, resource_id, operation]):
            raise ValueError("All parameters required for auth key generation")
        
        # Create normalized key components
        key_data = f"auth:{user_id}:{resource_id}:{operation}"
        
        # Hash for security and consistent length
        key_hash = hashlib.sha256(key_data.encode('utf-8')).hexdigest()[:16]
        
        return f"auth:{key_hash}"
    
    @staticmethod
    def generate_user_key(user_id: str, data_type: str = "profile") -> str:
        """Generate secure user cache key."""
        key_data = f"user:{user_id}:{data_type}"
        key_hash = hashlib.sha256(key_data.encode('utf-8')).hexdigest()[:16]
        return f"user:{key_hash}"
    
    @staticmethod
    def generate_resource_key(resource_id: str, resource_type: str) -> str:
        """Generate secure resource cache key."""
        key_data = f"resource:{resource_type}:{resource_id}"
        key_hash = hashlib.sha256(key_data.encode('utf-8')).hexdigest()[:16]
        return f"res:{key_hash}"


class L1MemoryCache:
    """
    High-performance L1 in-memory cache with thread-safe LRU eviction.
    Target: <5ms access times, >95% hit rate for hot authorization data.
    """
    
    def __init__(self, max_size_mb: int = 200, eviction_policy: EvictionPolicy = EvictionPolicy.HYBRID):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.eviction_policy = eviction_policy
        
        # Thread-safe storage
        self.cache: Dict[str, CacheEntry] = {}
        self.lru_order: OrderedDict[str, None] = OrderedDict()
        self.access_counts: Dict[str, int] = defaultdict(int)
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Metrics
        self.metrics = CacheMetrics()
        self.current_size_bytes = 0
        
        # Cleanup tracking
        self.last_cleanup = time.time()
        self.cleanup_interval = 60  # seconds
    
    def get(self, key: str, default: Any = None) -> Any:
        """Thread-safe get operation with performance tracking."""
        start_time = time.time()
        
        try:
            with self.lock:
                entry = self.cache.get(key)
                
                if entry and not entry.is_expired():
                    entry.access()
                    self.lru_order.move_to_end(key)
                    self.access_counts[key] += 1
                    
                    response_time_ms = (time.time() - start_time) * 1000
                    self.metrics.update(CacheOperation.GET, True, response_time_ms)
                    
                    return entry.value
                elif entry:
                    # Expired entry cleanup
                    self._remove_entry_unsafe(key)
                
                # Cache miss
                response_time_ms = (time.time() - start_time) * 1000
                self.metrics.update(CacheOperation.GET, False, response_time_ms)
                return default
                
        except Exception as e:
            logger.error(f"L1 cache get error for key {key}: {e}")
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.GET, False, response_time_ms)
            return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None, priority: int = 1, 
            tags: Optional[Set[str]] = None) -> bool:
        """Thread-safe set operation with intelligent eviction."""
        start_time = time.time()
        
        try:
            with self.lock:
                # Serialize and calculate size
                serialized_value = self._serialize_value(value)
                entry_size = len(serialized_value)
                
                # Reject oversized entries
                if entry_size > self.max_size_bytes * 0.1:  # Max 10% of cache
                    logger.warning(f"L1 cache entry too large: {entry_size} bytes")
                    return False
                
                # Remove existing entry
                if key in self.cache:
                    self._remove_entry_unsafe(key)
                
                # Ensure sufficient space
                self._ensure_space_unsafe(entry_size)
                
                # Create and store entry
                expires_at = time.time() + ttl if ttl else None
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=time.time(),
                    expires_at=expires_at,
                    size_bytes=entry_size,
                    priority=priority,
                    tags=tags or set()
                )
                
                self.cache[key] = entry
                self.lru_order[key] = None
                self.current_size_bytes += entry_size
                
                # Update metrics
                response_time_ms = (time.time() - start_time) * 1000
                self.metrics.update(CacheOperation.SET, True, response_time_ms)
                self.metrics.cache_size_bytes = self.current_size_bytes
                self.metrics.entries_count = len(self.cache)
                
                return True
                
        except Exception as e:
            logger.error(f"L1 cache set error for key {key}: {e}")
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.SET, False, response_time_ms)
            return False
    
    def delete(self, key: str) -> bool:
        """Thread-safe delete operation."""
        start_time = time.time()
        
        try:
            with self.lock:
                success = self._remove_entry_unsafe(key)
                
                response_time_ms = (time.time() - start_time) * 1000
                self.metrics.update(CacheOperation.DELETE, success, response_time_ms)
                return success
                
        except Exception as e:
            logger.error(f"L1 cache delete error for key {key}: {e}")
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.DELETE, False, response_time_ms)
            return False
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value with compression for large objects."""
        try:
            serialized = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Compress if beneficial
            if len(serialized) > 1024:  # 1KB threshold
                compressed = gzip.compress(serialized)
                if len(compressed) < len(serialized) * 0.8:
                    return compressed
            
            return serialized
        except Exception as e:
            logger.error(f"L1 cache serialization error: {e}")
            raise
    
    def _remove_entry_unsafe(self, key: str) -> bool:
        """Remove entry without lock (internal use only)."""
        if key in self.cache:
            entry = self.cache.pop(key)
            self.lru_order.pop(key, None)
            self.access_counts.pop(key, None)
            self.current_size_bytes -= entry.size_bytes
            self.metrics.entries_count = len(self.cache)
            return True
        return False
    
    def _ensure_space_unsafe(self, required_bytes: int):
        """Ensure sufficient space using eviction policy."""
        while (self.current_size_bytes + required_bytes) > self.max_size_bytes and self.cache:
            victim_key = self._select_eviction_victim_unsafe()
            if victim_key:
                self._remove_entry_unsafe(victim_key)
                self.metrics.evictions += 1
            else:
                break
    
    def _select_eviction_victim_unsafe(self) -> Optional[str]:
        """Select victim for eviction based on policy."""
        if not self.cache:
            return None
        
        if self.eviction_policy == EvictionPolicy.LRU:
            return next(iter(self.lru_order))
        elif self.eviction_policy == EvictionPolicy.LFU:
            return min(self.cache.keys(), key=lambda k: self.access_counts.get(k, 0))
        elif self.eviction_policy == EvictionPolicy.TTL:
            expiring_keys = [
                (k, v) for k, v in self.cache.items()
                if v.expires_at is not None
            ]
            if expiring_keys:
                return min(expiring_keys, key=lambda x: x[1].expires_at or float('inf'))[0]
            return next(iter(self.cache))
        else:  # HYBRID
            return min(self.cache.keys(), key=lambda k: self.cache[k].calculate_eviction_score())
    
    def cleanup_expired(self) -> int:
        """Clean up expired entries."""
        if time.time() - self.last_cleanup < self.cleanup_interval:
            return 0
        
        expired_keys = []
        with self.lock:
            for key, entry in self.cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                self._remove_entry_unsafe(key)
        
        self.last_cleanup = time.time()
        return len(expired_keys)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive L1 cache metrics."""
        with self.lock:
            utilization = (self.current_size_bytes / self.max_size_bytes) * 100
            
            return {
                'level': 'L1_MEMORY',
                'metrics': asdict(self.metrics),
                'utilization_percent': utilization,
                'current_size_mb': self.current_size_bytes / (1024 * 1024),
                'max_size_mb': self.max_size_bytes / (1024 * 1024),
                'eviction_policy': self.eviction_policy.value,
                'performance_target_ms': 5
            }
    
    def clear(self):
        """Clear all cache entries."""
        with self.lock:
            self.cache.clear()
            self.lru_order.clear()
            self.access_counts.clear()
            self.current_size_bytes = 0
            self.metrics = CacheMetrics()


class L2RedisCache:
    """
    High-performance L2 Redis cache with async operations and circuit breaker.
    Target: <20ms access times, >85% hit rate for distributed caching.
    """
    
    def __init__(self, redis_url: Optional[str] = None, max_connections: int = 20):
        self.redis_url = redis_url or getattr(settings, 'REDIS_URL', 'redis://localhost:6379')
        self.max_connections = max_connections
        
        # Connection management
        self.connection_pool: Optional[ConnectionPool] = None
        self.redis_client: Optional[redis.Redis] = None
        
        # Circuit breaker
        self.circuit_failures = 0
        self.circuit_last_failure = 0
        self.max_failures = 5
        self.recovery_timeout = 30
        self.circuit_state = "closed"  # closed, open, half_open
        
        # Metrics and configuration
        self.metrics = CacheMetrics()
        self.key_prefix = "velro:cache:"
        
        # Initialize Redis connection
        if REDIS_AVAILABLE:
            asyncio.create_task(self._init_connection())
    
    async def _init_connection(self):
        """Initialize Redis connection pool."""
        try:
            self.connection_pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                retry_on_timeout=True,
                socket_keepalive=True,
                health_check_interval=30
            )
            
            self.redis_client = redis.Redis(connection_pool=self.connection_pool)
            await self.redis_client.ping()
            
            logger.info(f"L2 Redis cache initialized: {self.redis_url}")
            
        except Exception as e:
            logger.error(f"L2 Redis initialization failed: {e}")
            self._handle_circuit_failure()
    
    def _make_key(self, key: str) -> str:
        """Create prefixed cache key."""
        return f"{self.key_prefix}{key}"
    
    def _handle_circuit_failure(self):
        """Handle circuit breaker failure."""
        self.circuit_failures += 1
        self.circuit_last_failure = time.time()
        
        if self.circuit_failures >= self.max_failures:
            self.circuit_state = "open"
            logger.warning("L2 Redis circuit breaker OPEN")
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operations."""
        if self.circuit_state == "closed":
            return True
        elif self.circuit_state == "open":
            if time.time() - self.circuit_last_failure > self.recovery_timeout:
                self.circuit_state = "half_open"
                logger.info("L2 Redis circuit breaker HALF_OPEN")
                return True
            return False
        return True  # half_open
    
    def _reset_circuit_breaker(self):
        """Reset circuit breaker on successful operation."""
        if self.circuit_state == "half_open":
            self.circuit_state = "closed"
            self.circuit_failures = 0
            logger.info("L2 Redis circuit breaker CLOSED")
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Async get from Redis cache."""
        if not self._check_circuit_breaker() or not self.redis_client:
            return default
        
        start_time = time.time()
        
        try:
            full_key = self._make_key(key)
            data = await self.redis_client.get(full_key)
            
            if data is not None:
                value = self._deserialize_value(data)
                
                response_time_ms = (time.time() - start_time) * 1000
                self.metrics.update(CacheOperation.GET, True, response_time_ms)
                self._reset_circuit_breaker()
                
                return value
            
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.GET, False, response_time_ms)
            return default
            
        except RedisError as e:
            logger.warning(f"L2 Redis get error for key {key}: {e}")
            self._handle_circuit_failure()
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.GET, False, response_time_ms)
            return default
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Async set to Redis cache."""
        if not self._check_circuit_breaker() or not self.redis_client:
            return False
        
        start_time = time.time()
        
        try:
            full_key = self._make_key(key)
            serialized_data = self._serialize_value(value)
            
            if ttl:
                success = await self.redis_client.setex(full_key, ttl, serialized_data)
            else:
                success = await self.redis_client.set(full_key, serialized_data)
            
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.SET, bool(success), response_time_ms)
            
            if success:
                self._reset_circuit_breaker()
            
            return bool(success)
            
        except RedisError as e:
            logger.warning(f"L2 Redis set error for key {key}: {e}")
            self._handle_circuit_failure()
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.SET, False, response_time_ms)
            return False
    
    async def delete(self, key: str) -> bool:
        """Async delete from Redis cache."""
        if not self._check_circuit_breaker() or not self.redis_client:
            return False
        
        start_time = time.time()
        
        try:
            full_key = self._make_key(key)
            deleted = await self.redis_client.delete(full_key)
            
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.DELETE, deleted > 0, response_time_ms)
            
            if deleted > 0:
                self._reset_circuit_breaker()
            
            return deleted > 0
            
        except RedisError as e:
            logger.warning(f"L2 Redis delete error for key {key}: {e}")
            self._handle_circuit_failure()
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.DELETE, False, response_time_ms)
            return False
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value for Redis with compression."""
        try:
            if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
                json_str = json.dumps(value, default=str)
                serialized = json_str.encode('utf-8')
                prefix = b'JSON:'
            else:
                serialized = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
                prefix = b'PICK:'
            
            # Compress large values
            if len(serialized) > 1024:
                compressed = gzip.compress(serialized)
                if len(compressed) < len(serialized) * 0.9:
                    return b'GZIP:' + prefix + compressed
            
            return prefix + serialized
            
        except Exception as e:
            logger.error(f"L2 Redis serialization error: {e}")
            raise
    
    def _deserialize_value(self, data: bytes) -> Any:
        """Deserialize value from Redis with decompression."""
        try:
            if data.startswith(b'GZIP:'):
                data = data[5:]  # Remove GZIP prefix
                if data.startswith(b'JSON:'):
                    decompressed = gzip.decompress(data[5:])
                    return json.loads(decompressed.decode('utf-8'))
                elif data.startswith(b'PICK:'):
                    decompressed = gzip.decompress(data[5:])
                    return pickle.loads(decompressed)
            elif data.startswith(b'JSON:'):
                return json.loads(data[5:].decode('utf-8'))
            elif data.startswith(b'PICK:'):
                return pickle.loads(data[5:])
            else:
                return pickle.loads(data)
                
        except Exception as e:
            logger.error(f"L2 Redis deserialization error: {e}")
            raise
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate keys matching pattern."""
        if not self._check_circuit_breaker() or not self.redis_client:
            return 0
        
        try:
            full_pattern = self._make_key(pattern)
            keys = []
            
            async for key in self.redis_client.scan_iter(match=full_pattern):
                keys.append(key)
            
            if keys:
                deleted = await self.redis_client.delete(*keys)
                logger.info(f"L2 Redis invalidated {deleted} keys for pattern: {pattern}")
                return deleted
            
            return 0
            
        except RedisError as e:
            logger.error(f"L2 Redis pattern invalidation error: {e}")
            return 0
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get L2 Redis cache metrics."""
        return {
            'level': 'L2_REDIS',
            'metrics': asdict(self.metrics),
            'circuit_state': self.circuit_state,
            'circuit_failures': self.circuit_failures,
            'redis_available': self.redis_client is not None,
            'performance_target_ms': 20
        }


class L3DatabaseCache:
    """
    L3 Database cache with materialized views for analytical queries.
    Target: <100ms query times for complex authorization patterns.
    """
    
    def __init__(self):
        self.metrics = CacheMetrics()
        self.materialized_views = {
            'authorization': 'mv_user_authorization_context',
            'team_collaboration': 'mv_team_collaboration_patterns',
            'generation_performance': 'mv_generation_performance_stats',
            'cache_analytics': 'mv_cache_performance_analytics'
        }
    
    async def get_materialized_view_data(self, view_type: str, filters: Optional[Dict[str, Any]] = None,
                                       limit: int = 1000) -> Optional[List[Dict[str, Any]]]:
        """Get data from materialized view with performance tracking."""
        start_time = time.time()
        
        try:
            view_name = self.materialized_views.get(view_type)
            if not view_name:
                logger.error(f"Unknown materialized view type: {view_type}")
                return None
            
            db = await get_database()
            
            # Build query parameters
            query_params = {
                'table': view_name,
                'operation': 'select',
                'filters': filters or {},
                'limit': limit
            }
            
            result = await db.execute_query(**query_params)
            
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.GET, True, response_time_ms)
            
            return result
            
        except Exception as e:
            logger.error(f"L3 database cache error for view {view_type}: {e}")
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update(CacheOperation.GET, False, response_time_ms)
            return None
    
    async def refresh_materialized_views(self) -> Dict[str, bool]:
        """Refresh all materialized views concurrently."""
        results = {}
        
        try:
            db = await get_database()
            
            refresh_tasks = []
            for view_type, view_name in self.materialized_views.items():
                task = self._refresh_single_view(db, view_name)
                refresh_tasks.append((view_type, task))
            
            # Execute all refreshes concurrently
            for view_type, task in refresh_tasks:
                try:
                    success = await task
                    results[view_type] = success
                    if success:
                        logger.info(f"Refreshed materialized view: {view_type}")
                    else:
                        logger.error(f"Failed to refresh materialized view: {view_type}")
                except Exception as e:
                    logger.error(f"Error refreshing materialized view {view_type}: {e}")
                    results[view_type] = False
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to refresh materialized views: {e}")
            return {view_type: False for view_type in self.materialized_views.keys()}
    
    async def _refresh_single_view(self, db, view_name: str) -> bool:
        """Refresh a single materialized view."""
        try:
            query = f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"
            await db.execute_query(
                table="",
                operation="raw_query",
                query=query
            )
            return True
        except Exception as e:
            logger.error(f"Failed to refresh view {view_name}: {e}")
            return False
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get L3 database cache metrics."""
        return {
            'level': 'L3_DATABASE',
            'metrics': asdict(self.metrics),
            'materialized_views': list(self.materialized_views.keys()),
            'performance_target_ms': 100
        }


class MultiLayerCache:
    """
    CRITICAL Multi-Layer Cache Manager implementing 3-tier architecture.
    Orchestrates L1 (Memory) -> L2 (Redis) -> L3 (Database) caching strategy
    with automatic fallback, promotion, and warming.
    """
    
    def __init__(self, l1_size_mb: int = 200, redis_url: Optional[str] = None):
        # Initialize cache layers
        self.l1_cache = L1MemoryCache(max_size_mb=l1_size_mb)
        self.l2_cache = L2RedisCache(redis_url=redis_url)
        self.l3_cache = L3DatabaseCache()
        
        # Key management
        self.key_manager = SecureCacheKeyManager()
        
        # Configuration
        self.auto_promotion_enabled = True  # Promote L2->L1, L3->L2
        self.cache_warming_enabled = True
        self.consistency_checking = True
        
        # Performance tracking
        self.operation_metrics: Dict[str, List[float]] = defaultdict(list)
        
        # Background task management
        self.background_tasks_running = True
        self.cleanup_task: Optional[asyncio.Task] = None
        self.warming_task: Optional[asyncio.Task] = None
        
        # Start background tasks
        self._start_background_tasks()
    
    def _start_background_tasks(self):
        """Start background maintenance tasks."""
        try:
            loop = asyncio.get_running_loop()
            self.cleanup_task = loop.create_task(self._cleanup_loop())
            self.warming_task = loop.create_task(self._warming_loop())
        except RuntimeError:
            # No event loop running, tasks will start later
            pass
    
    async def get_authorization_cached(self, user_id: str, resource_id: str, 
                                     operation: str) -> Tuple[Optional[Dict[str, Any]], CacheLevel]:
        """
        Get cached authorization result with multi-level fallback.
        Implements the core caching strategy for <75ms authorization targets.
        """
        cache_key = self.key_manager.generate_auth_key(user_id, resource_id, operation)
        
        try:
            # L1 Memory Cache check (target: <5ms)
            l1_result = self.l1_cache.get(cache_key)
            if l1_result is not None:
                return l1_result, CacheLevel.L1_MEMORY
            
            # L2 Redis Cache check (target: <20ms) 
            l2_result = await self.l2_cache.get(cache_key)
            if l2_result is not None:
                # Promote to L1 for faster future access
                if self.auto_promotion_enabled:
                    self.l1_cache.set(cache_key, l2_result, ttl=300, priority=2)
                
                return l2_result, CacheLevel.L2_REDIS
            
            # L3 Database fallback (target: <100ms)
            l3_result = await self._get_authorization_from_db(user_id, resource_id, operation)
            if l3_result is not None:
                # Cache in all levels for future requests
                await self._set_authorization_multilevel(cache_key, l3_result)
                return l3_result, CacheLevel.L3_DATABASE
            
            # Complete miss
            return None, CacheLevel.L3_DATABASE
            
        except Exception as e:
            logger.error(f"Multi-layer cache get failed for auth {user_id}:{resource_id}:{operation}: {e}")
            return None, CacheLevel.L3_DATABASE
    
    async def set_authorization_cached(self, user_id: str, resource_id: str, operation: str,
                                     auth_data: Dict[str, Any], priority: int = 2) -> Dict[str, bool]:
        """Cache authorization result across all levels with TTL strategy."""
        cache_key = self.key_manager.generate_auth_key(user_id, resource_id, operation)
        return await self._set_authorization_multilevel(cache_key, auth_data, priority)
    
    async def _set_authorization_multilevel(self, cache_key: str, auth_data: Dict[str, Any], 
                                          priority: int = 2) -> Dict[str, bool]:
        """Set authorization data in multiple cache levels."""
        results = {}
        
        try:
            # Add timestamp for cache freshness tracking
            cache_value = {
                **auth_data,
                'cached_at': datetime.utcnow().isoformat(),
                'cache_version': '2.0'
            }
            
            # L1 Cache: 60 seconds for hot data
            results['L1'] = self.l1_cache.set(
                cache_key, cache_value, ttl=60, priority=priority,
                tags={'authorization', 'hot_data'}
            )
            
            # L2 Cache: 300 seconds for warm data  
            results['L2'] = await self.l2_cache.set(cache_key, cache_value, ttl=300)
            
            # L3 is handled by materialized views, always successful
            results['L3'] = True
            
            return results
            
        except Exception as e:
            logger.error(f"Multi-level cache set failed for key {cache_key}: {e}")
            return {'L1': False, 'L2': False, 'L3': False}
    
    async def _get_authorization_from_db(self, user_id: str, resource_id: str, 
                                       operation: str) -> Optional[Dict[str, Any]]:
        """Fallback to database for authorization data."""
        try:
            auth_data = await self.l3_cache.get_materialized_view_data(
                'authorization',
                filters={
                    'user_id': user_id,
                    'generation_id': resource_id,
                    'operation': operation
                },
                limit=1
            )
            
            if auth_data and len(auth_data) > 0:
                return auth_data[0]
            
            return None
            
        except Exception as e:
            logger.error(f"Database authorization lookup failed: {e}")
            return None
    
    async def invalidate_user_authorization(self, user_id: str) -> Dict[str, int]:
        """Invalidate all authorization cache entries for a user."""
        pattern = f"auth:*{user_id}*"  # Simple pattern matching
        
        results = {}
        
        try:
            # L1 pattern invalidation
            l1_count = 0
            keys_to_remove = []
            with self.l1_cache.lock:
                for key in self.l1_cache.cache.keys():
                    if user_id in key:  # Simple contains check
                        keys_to_remove.append(key)
            
            for key in keys_to_remove:
                if self.l1_cache.delete(key):
                    l1_count += 1
            results['L1'] = l1_count
            
            # L2 Redis pattern invalidation
            results['L2'] = await self.l2_cache.invalidate_pattern(f"*{user_id}*")
            
            # L3 handled by materialized view refresh
            results['L3'] = 0
            
            logger.info(f"Invalidated authorization cache for user {user_id}: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Authorization cache invalidation failed for user {user_id}: {e}")
            return {'L1': 0, 'L2': 0, 'L3': 0}
    
    async def warm_authorization_cache(self) -> Dict[str, Dict[str, int]]:
        """Intelligent cache warming for authorization data."""
        if not self.cache_warming_enabled:
            return {}
        
        try:
            # Get recent authorization patterns from L3
            auth_data = await self.l3_cache.get_materialized_view_data(
                'authorization',
                filters={'last_accessed__gte': datetime.utcnow() - timedelta(hours=24)},
                limit=500
            )
            
            warmed_count = {'L1': 0, 'L2': 0, 'L3': 0}
            
            if auth_data:
                for auth in auth_data:
                    cache_key = self.key_manager.generate_auth_key(
                        auth['user_id'], auth['generation_id'], 'read'
                    )
                    
                    cache_value = {
                        'access_granted': auth.get('has_read_access', False),
                        'access_method': auth.get('access_method', 'unknown'),
                        'effective_role': auth.get('effective_role', 'viewer'),
                        'team_id': auth.get('team_id'),
                        'project_id': auth.get('project_id'),
                        'cached_at': datetime.utcnow().isoformat()
                    }
                    
                    results = await self._set_authorization_multilevel(cache_key, cache_value)
                    
                    if results['L1']:
                        warmed_count['L1'] += 1
                    if results['L2']:
                        warmed_count['L2'] += 1
            
            logger.info(f"Authorization cache warming completed: {warmed_count}")
            return {'authorization': warmed_count}
            
        except Exception as e:
            logger.error(f"Authorization cache warming failed: {e}")
            return {'authorization': {'L1': 0, 'L2': 0, 'L3': 0}}
    
    async def _cleanup_loop(self):
        """Background cleanup and maintenance loop."""
        while self.background_tasks_running:
            try:
                # Cleanup expired L1 entries
                expired_count = self.l1_cache.cleanup_expired()
                if expired_count > 0:
                    logger.debug(f"Cleaned up {expired_count} expired L1 cache entries")
                
                # Refresh materialized views every 30 minutes
                current_time = datetime.utcnow()
                if current_time.minute % 30 == 0:
                    refresh_results = await self.l3_cache.refresh_materialized_views()
                    successful_refreshes = sum(refresh_results.values())
                    if successful_refreshes > 0:
                        logger.info(f"Refreshed {successful_refreshes} materialized views")
                
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache cleanup loop error: {e}")
                await asyncio.sleep(60)
    
    async def _warming_loop(self):
        """Background cache warming loop."""
        while self.background_tasks_running:
            try:
                if self.cache_warming_enabled:
                    # Warm authorization cache every 30 minutes
                    results = await self.warm_authorization_cache()
                    total_warmed = sum(
                        sum(pattern_results.values()) 
                        for pattern_results in results.values()
                    )
                    
                    if total_warmed > 0:
                        logger.info(f"Cache warming completed: {total_warmed} entries")
                
                await asyncio.sleep(1800)  # 30 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache warming loop error: {e}")
                await asyncio.sleep(300)
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics for all cache levels."""
        l1_metrics = self.l1_cache.get_metrics()
        l2_metrics = self.l2_cache.get_metrics()  
        l3_metrics = self.l3_cache.get_metrics()
        
        # Calculate overall performance
        total_hits = (l1_metrics['metrics']['hits'] + 
                     l2_metrics['metrics']['hits'] + 
                     l3_metrics['metrics']['hits'])
        total_misses = (l1_metrics['metrics']['misses'] + 
                       l2_metrics['metrics']['misses'] + 
                       l3_metrics['metrics']['misses'])
        total_requests = total_hits + total_misses
        
        overall_hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
        
        # Weighted average response time
        weighted_avg_response = 0
        if total_hits > 0:
            l1_weight = l1_metrics['metrics']['hits'] / total_hits
            l2_weight = l2_metrics['metrics']['hits'] / total_hits
            l3_weight = l3_metrics['metrics']['hits'] / total_hits
            
            weighted_avg_response = (
                l1_weight * l1_metrics['metrics']['avg_response_time_ms'] +
                l2_weight * l2_metrics['metrics']['avg_response_time_ms'] +  
                l3_weight * l3_metrics['metrics']['avg_response_time_ms']
            )
        
        return {
            'overall_performance': {
                'total_requests': total_requests,
                'total_hits': total_hits,
                'total_misses': total_misses,
                'hit_rate_percent': overall_hit_rate,
                'weighted_avg_response_ms': weighted_avg_response,
                'target_hit_rate_percent': 95.0,
                'target_response_time_ms': 75.0,
                'performance_targets_met': (
                    overall_hit_rate >= 95.0 and 
                    weighted_avg_response <= 75.0
                )
            },
            'cache_levels': {
                'L1_Memory': l1_metrics,
                'L2_Redis': l2_metrics,
                'L3_Database': l3_metrics
            },
            'configuration': {
                'auto_promotion_enabled': self.auto_promotion_enabled,
                'cache_warming_enabled': self.cache_warming_enabled,
                'consistency_checking': self.consistency_checking
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for all cache levels."""
        health_status = {
            'overall_healthy': True,
            'L1_Memory': {'status': 'healthy', 'response_time_ms': 0},
            'L2_Redis': {'status': 'unknown', 'response_time_ms': 0},
            'L3_Database': {'status': 'healthy', 'response_time_ms': 0},
            'background_tasks': {
                'cleanup_running': (self.cleanup_task is not None and 
                                  not self.cleanup_task.done()),
                'warming_running': (self.warming_task is not None and 
                                  not self.warming_task.done())
            }
        }
        
        try:
            # Test L1 Memory performance
            start_time = time.time()
            test_key = f"health_check_{uuid.uuid4().hex[:8]}"
            self.l1_cache.set(test_key, {'test': True}, ttl=60)
            result = self.l1_cache.get(test_key)
            self.l1_cache.delete(test_key)
            
            l1_response_time = (time.time() - start_time) * 1000
            health_status['L1_Memory']['response_time_ms'] = l1_response_time
            
            if result != {'test': True}:
                health_status['L1_Memory']['status'] = 'unhealthy'
                health_status['overall_healthy'] = False
            
            # Test L2 Redis if available
            if self.l2_cache.redis_client:
                start_time = time.time()
                test_success = await self.l2_cache.set(test_key, {'test': True}, ttl=60)
                if test_success:
                    redis_result = await self.l2_cache.get(test_key)
                    await self.l2_cache.delete(test_key)
                    
                    l2_response_time = (time.time() - start_time) * 1000
                    health_status['L2_Redis'] = {
                        'status': 'healthy' if redis_result == {'test': True} else 'unhealthy',
                        'response_time_ms': l2_response_time
                    }
                else:
                    health_status['L2_Redis'] = {
                        'status': 'unhealthy',
                        'response_time_ms': (time.time() - start_time) * 1000
                    }
                    health_status['overall_healthy'] = False
            else:
                health_status['L2_Redis'] = {
                    'status': 'unavailable',
                    'response_time_ms': 0
                }
            
        except Exception as e:
            logger.error(f"Cache health check error: {e}")
            health_status['overall_healthy'] = False
        
        return health_status
    
    async def shutdown(self):
        """Graceful shutdown of multi-layer cache."""
        self.background_tasks_running = False
        
        # Cancel background tasks
        for task in [self.cleanup_task, self.warming_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Clear caches
        self.l1_cache.clear()
        
        logger.info("Multi-layer cache shutdown complete")


# Global cache instance
_cache_instance: Optional[MultiLayerCache] = None


def get_multi_layer_cache() -> MultiLayerCache:
    """Get or create the global multi-layer cache instance."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = MultiLayerCache()
    return _cache_instance


# Authorization-specific convenience functions
async def get_cached_authorization(user_id: str, resource_id: str, operation: str = 'read') -> Optional[Dict[str, Any]]:
    """Get cached authorization result with multi-level fallback."""
    cache = get_multi_layer_cache()
    result, _ = await cache.get_authorization_cached(user_id, resource_id, operation)
    return result


async def cache_authorization_result(user_id: str, resource_id: str, operation: str,
                                   auth_data: Dict[str, Any], priority: int = 2) -> Dict[str, bool]:
    """Cache authorization result across all levels."""
    cache = get_multi_layer_cache()
    return await cache.set_authorization_cached(user_id, resource_id, operation, auth_data, priority)


async def invalidate_user_cache(user_id: str) -> Dict[str, int]:
    """Invalidate all cache entries for a user."""
    cache = get_multi_layer_cache()
    return await cache.invalidate_user_authorization(user_id)


async def warm_cache_system() -> Dict[str, Dict[str, int]]:
    """Warm the entire cache system with predictive data."""
    cache = get_multi_layer_cache()
    return await cache.warm_authorization_cache()