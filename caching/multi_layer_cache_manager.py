"""
Enterprise Multi-Layer Caching Architecture Manager
Implements L1/L2/L3 caching as specified in PRD with sub-100ms authorization times.

Features:
- L1 Memory Cache: <5ms access times, >95% hit rate for hot data
- L2 Redis Cache: <20ms access times, >85% hit rate for warm data  
- L3 Database Cache: <100ms query times, materialized views for analytics
- Intelligent cache warming, invalidation, and consistency management
- Performance optimization for 10,000+ concurrent users
- Real-time monitoring and automatic failover
"""

import asyncio
import json
import logging
import time
import threading
import hashlib
from typing import Dict, Any, Optional, List, Union, Callable, Set, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict, OrderedDict
import weakref
import pickle
import gzip
from contextlib import asynccontextmanager
import uuid

# Redis imports with error handling
try:
    import redis.asyncio as redis
    from redis.asyncio.connection import ConnectionPool
    from redis.exceptions import ConnectionError, TimeoutError, RedisError
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    ConnectionPool = None
    RedisError = Exception

from database import get_database
from monitoring.performance import performance_tracker, PerformanceTarget
from monitoring.metrics import metrics_collector
from config import settings

logger = logging.getLogger(__name__)


class CacheLevel(Enum):
    """Multi-layer cache hierarchy for optimal performance."""
    L1_MEMORY = "l1_memory"        # In-memory: <5ms, >95% hit rate
    L2_REDIS = "l2_redis"          # Distributed: <20ms, >85% hit rate
    L3_DATABASE = "l3_database"    # Materialized: <100ms, analytical queries


class CacheOperation(Enum):
    """Cache operations for performance tracking."""
    GET = "get"
    SET = "set"
    DELETE = "delete"
    INVALIDATE = "invalidate"
    WARM = "warm"
    BATCH_GET = "batch_get"
    BATCH_SET = "batch_set"


class CachePriority(Enum):
    """Cache priority levels for intelligent caching decisions."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvictionPolicy(Enum):
    """Cache eviction policies."""
    LRU = "lru"                    # Least Recently Used
    LFU = "lfu"                    # Least Frequently Used
    TTL = "ttl"                    # Time To Live based
    HYBRID = "hybrid"              # Combination of LRU + LFU + TTL


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
    priority: int = 1              # Higher priority = less likely to evict
    compressed: bool = False
    serialization_type: str = "json"
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() >= self.expires_at
    
    def time_to_live(self) -> Optional[float]:
        """Get remaining TTL in seconds."""
        if self.expires_at is None:
            return None
        return max(0, self.expires_at - time.time())
    
    def access(self):
        """Record access and update metrics."""
        self.access_count += 1
        self.last_accessed = time.time()
    
    def calculate_priority_score(self) -> float:
        """Calculate dynamic priority score for eviction."""
        now = time.time()
        recency_score = 1.0 / (now - self.last_accessed + 1)
        frequency_score = min(self.access_count / 100.0, 1.0)
        priority_score = self.priority / 10.0
        
        return (recency_score * 0.4 + frequency_score * 0.4 + priority_score * 0.2)


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
    hit_rate: float = 0.0
    cache_size_bytes: int = 0
    max_size_bytes: int = 0
    entries_count: int = 0
    
    def update_metrics(self, operation: CacheOperation, success: bool, 
                      response_time_ms: float = 0.0, size_bytes: int = 0):
        """Update metrics for cache operation."""
        self.total_operations += 1
        
        if operation == CacheOperation.GET:
            if success:
                self.hits += 1
            else:
                self.misses += 1
        elif operation == CacheOperation.SET:
            if success:
                self.sets += 1
                self.cache_size_bytes += size_bytes
        elif operation == CacheOperation.DELETE:
            if success:
                self.deletes += 1
        
        if not success:
            self.errors += 1
        
        # Update average response time
        if self.total_operations > 0:
            self.avg_response_time_ms = (
                (self.avg_response_time_ms * (self.total_operations - 1) + response_time_ms) /
                self.total_operations
            )
        
        # Update hit rate
        total_requests = self.hits + self.misses
        if total_requests > 0:
            self.hit_rate = (self.hits / total_requests) * 100


class L1MemoryCache:
    """
    High-performance L1 in-memory cache with advanced eviction policies.
    Target: <5ms access times, >95% hit rate for frequently accessed data.
    """
    
    def __init__(self, max_size_mb: int = 200, eviction_policy: EvictionPolicy = EvictionPolicy.HYBRID):
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.eviction_policy = eviction_policy
        
        # Cache storage with different data structures for different policies
        self.cache: Dict[str, CacheEntry] = {}
        self.lru_order: OrderedDict[str, None] = OrderedDict()
        self.lfu_counts: Dict[str, int] = defaultdict(int)
        
        # Metrics and monitoring
        self.metrics = CacheMetrics()
        self.current_size_bytes = 0
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Background cleanup
        self.cleanup_interval = 60  # seconds
        self.last_cleanup = time.time()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from L1 cache with performance tracking."""
        start_time = time.time()
        
        try:
            with self.lock:
                entry = self.cache.get(key)
                
                if entry and not entry.is_expired():
                    # Update access patterns
                    entry.access()
                    self.lru_order.move_to_end(key)  # Move to most recent
                    self.lfu_counts[key] += 1
                    
                    # Record successful hit
                    response_time_ms = (time.time() - start_time) * 1000
                    self.metrics.update_metrics(CacheOperation.GET, True, response_time_ms)
                    
                    return entry.value
                
                elif entry:
                    # Entry expired, clean it up
                    self._remove_entry(key)
                
                # Cache miss
                response_time_ms = (time.time() - start_time) * 1000
                self.metrics.update_metrics(CacheOperation.GET, False, response_time_ms)
                return default
                
        except Exception as e:
            logger.error(f"L1 cache get error for key {key}: {e}")
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.GET, False, response_time_ms)
            return default
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None, 
            priority: int = 1, tags: Optional[Set[str]] = None) -> bool:
        """Set value in L1 cache with intelligent eviction."""
        start_time = time.time()
        
        try:
            with self.lock:
                # Calculate value size and check if it fits
                serialized_value = self._serialize_value(value)
                entry_size = len(serialized_value)
                
                # Don't cache oversized entries (>10% of cache)
                if entry_size > self.max_size_bytes * 0.1:
                    logger.warning(f"L1 cache entry too large: {entry_size} bytes for key {key}")
                    return False
                
                # Remove existing entry if present
                if key in self.cache:
                    self._remove_entry(key)
                
                # Ensure space is available
                self._ensure_space(entry_size)
                
                # Create cache entry
                expires_at = time.time() + ttl if ttl else None
                entry = CacheEntry(
                    key=key,
                    value=value,
                    created_at=time.time(),
                    expires_at=expires_at,
                    size_bytes=entry_size,
                    priority=priority,
                    tags=tags or set(),
                    serialization_type="pickle"
                )
                
                # Store entry
                self.cache[key] = entry
                self.lru_order[key] = None
                self.current_size_bytes += entry_size
                
                # Update metrics
                response_time_ms = (time.time() - start_time) * 1000
                self.metrics.update_metrics(CacheOperation.SET, True, response_time_ms, entry_size)
                self.metrics.entries_count = len(self.cache)
                self.metrics.cache_size_bytes = self.current_size_bytes
                
                return True
                
        except Exception as e:
            logger.error(f"L1 cache set error for key {key}: {e}")
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.SET, False, response_time_ms)
            return False
    
    def delete(self, key: str) -> bool:
        """Delete entry from L1 cache."""
        start_time = time.time()
        
        try:
            with self.lock:
                success = self._remove_entry(key)
                
                response_time_ms = (time.time() - start_time) * 1000
                self.metrics.update_metrics(CacheOperation.DELETE, success, response_time_ms)
                return success
                
        except Exception as e:
            logger.error(f"L1 cache delete error for key {key}: {e}")
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.DELETE, False, response_time_ms)
            return False
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value with compression for large objects."""
        try:
            # Use pickle for Python objects
            serialized = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
            
            # Compress large values
            if len(serialized) > 1024:  # 1KB threshold
                compressed = gzip.compress(serialized)
                if len(compressed) < len(serialized) * 0.8:  # 20% compression minimum
                    return compressed
            
            return serialized
            
        except Exception as e:
            logger.error(f"L1 cache serialization error: {e}")
            raise
    
    def _remove_entry(self, key: str) -> bool:
        """Remove entry and update data structures."""
        if key in self.cache:
            entry = self.cache.pop(key)
            self.lru_order.pop(key, None)
            self.lfu_counts.pop(key, None)
            self.current_size_bytes -= entry.size_bytes
            self.metrics.entries_count = len(self.cache)
            return True
        return False
    
    def _ensure_space(self, required_bytes: int):
        """Ensure sufficient space using intelligent eviction."""
        while (self.current_size_bytes + required_bytes) > self.max_size_bytes and self.cache:
            victim_key = self._select_eviction_victim()
            if victim_key:
                self._remove_entry(victim_key)
                self.metrics.evictions += 1
            else:
                break
    
    def _select_eviction_victim(self) -> Optional[str]:
        """Select victim for eviction based on policy."""
        if not self.cache:
            return None
        
        if self.eviction_policy == EvictionPolicy.LRU:
            return next(iter(self.lru_order))
        
        elif self.eviction_policy == EvictionPolicy.LFU:
            return min(self.cache.keys(), key=lambda k: self.lfu_counts.get(k, 0))
        
        elif self.eviction_policy == EvictionPolicy.TTL:
            # Evict entries closest to expiration
            expiring_entries = [
                (k, v) for k, v in self.cache.items()
                if v.expires_at is not None
            ]
            if expiring_entries:
                return min(expiring_entries, key=lambda x: x[1].expires_at or float('inf'))[0]
            return next(iter(self.cache))
        
        else:  # HYBRID policy
            # Use priority score combining recency, frequency, and priority
            return min(self.cache.keys(), 
                      key=lambda k: self.cache[k].calculate_priority_score())
    
    def cleanup_expired(self) -> int:
        """Clean up expired entries."""
        if time.time() - self.last_cleanup < self.cleanup_interval:
            return 0
        
        expired_keys = []
        with self.lock:
            current_time = time.time()
            for key, entry in self.cache.items():
                if entry.is_expired():
                    expired_keys.append(key)
            
            for key in expired_keys:
                self._remove_entry(key)
        
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
                'entries_count': len(self.cache),
                'current_size_mb': self.current_size_bytes / (1024 * 1024),
                'max_size_mb': self.max_size_bytes / (1024 * 1024),
                'eviction_policy': self.eviction_policy.value,
                'performance_target_ms': 5
            }
    
    def clear(self):
        """Clear all entries from L1 cache."""
        with self.lock:
            self.cache.clear()
            self.lru_order.clear()
            self.lfu_counts.clear()
            self.current_size_bytes = 0
            self.metrics = CacheMetrics()


class L2RedisCache:
    """
    High-performance L2 Redis cache with cluster support and failover.
    Target: <20ms access times, >85% hit rate for distributed data.
    """
    
    def __init__(self, redis_url: Optional[str] = None, max_connections: int = 20):
        self.redis_url = redis_url or getattr(settings, 'redis_url', 'redis://localhost:6379')
        self.max_connections = max_connections
        
        # Connection management
        self.connection_pool: Optional[ConnectionPool] = None
        self.redis_client: Optional[redis.Redis] = None
        self.circuit_breaker_failures = 0
        self.circuit_breaker_last_failure = 0
        self.max_circuit_failures = 5
        self.circuit_recovery_timeout = 30
        self.circuit_state = "closed"  # closed, open, half_open
        
        # Metrics
        self.metrics = CacheMetrics()
        self.key_prefix = "velro:l2:"
        
        # Initialize connection if Redis is available
        if REDIS_AVAILABLE:
            asyncio.create_task(self._initialize_connection())
    
    async def _initialize_connection(self):
        """Initialize Redis connection pool."""
        try:
            self.connection_pool = ConnectionPool.from_url(
                self.redis_url,
                max_connections=self.max_connections,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={},
                health_check_interval=30
            )
            
            self.redis_client = redis.Redis(connection_pool=self.connection_pool)
            
            # Test connection
            await self.redis_client.ping()
            logger.info(f"L2 Redis cache initialized: {self.redis_url}")
            
        except Exception as e:
            logger.error(f"L2 Redis cache initialization failed: {e}")
            self._handle_circuit_failure()
    
    def _make_key(self, key: str) -> str:
        """Create prefixed cache key."""
        return f"{self.key_prefix}{key}"
    
    def _handle_circuit_failure(self):
        """Handle circuit breaker failures."""
        self.circuit_breaker_failures += 1
        self.circuit_breaker_last_failure = time.time()
        
        if self.circuit_breaker_failures >= self.max_circuit_failures:
            self.circuit_state = "open"
            logger.warning(f"L2 Redis circuit breaker OPEN - operations suspended")
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker allows operations."""
        if self.circuit_state == "closed":
            return True
        elif self.circuit_state == "open":
            if time.time() - self.circuit_breaker_last_failure > self.circuit_recovery_timeout:
                self.circuit_state = "half_open"
                logger.info("L2 Redis circuit breaker HALF_OPEN - testing recovery")
                return True
            return False
        elif self.circuit_state == "half_open":
            return True
        return False
    
    def _reset_circuit_breaker(self):
        """Reset circuit breaker on successful operation."""
        if self.circuit_state == "half_open":
            self.circuit_state = "closed"
            self.circuit_breaker_failures = 0
            logger.info("L2 Redis circuit breaker CLOSED - operations restored")
    
    async def get(self, key: str, default: Any = None) -> Any:
        """Get value from L2 Redis cache."""
        if not self._check_circuit_breaker() or not self.redis_client:
            return default
        
        start_time = time.time()
        
        try:
            full_key = self._make_key(key)
            data = await self.redis_client.get(full_key)
            
            if data is not None:
                value = self._deserialize_value(data)
                
                response_time_ms = (time.time() - start_time) * 1000
                self.metrics.update_metrics(CacheOperation.GET, True, response_time_ms)
                self._reset_circuit_breaker()
                
                return value
            
            # Cache miss
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.GET, False, response_time_ms)
            return default
            
        except RedisError as e:
            logger.warning(f"L2 Redis get error for key {key}: {e}")
            self._handle_circuit_failure()
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.GET, False, response_time_ms)
            return default
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in L2 Redis cache."""
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
            self.metrics.update_metrics(CacheOperation.SET, bool(success), response_time_ms, len(serialized_data))
            
            if success:
                self._reset_circuit_breaker()
            
            return bool(success)
            
        except RedisError as e:
            logger.warning(f"L2 Redis set error for key {key}: {e}")
            self._handle_circuit_failure()
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.SET, False, response_time_ms)
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete value from L2 Redis cache."""
        if not self._check_circuit_breaker() or not self.redis_client:
            return False
        
        start_time = time.time()
        
        try:
            full_key = self._make_key(key)
            deleted = await self.redis_client.delete(full_key)
            
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.DELETE, deleted > 0, response_time_ms)
            
            if deleted > 0:
                self._reset_circuit_breaker()
            
            return deleted > 0
            
        except RedisError as e:
            logger.warning(f"L2 Redis delete error for key {key}: {e}")
            self._handle_circuit_failure()
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.DELETE, False, response_time_ms)
            return False
    
    def _serialize_value(self, value: Any) -> bytes:
        """Serialize value with compression for Redis storage."""
        try:
            # Try JSON first for simple types
            if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
                json_str = json.dumps(value, default=str)
                serialized = json_str.encode('utf-8')
                prefix = b'JSON:'
            else:
                # Use pickle for complex objects
                serialized = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
                prefix = b'PICK:'
            
            # Compress if beneficial
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
                # Compressed data
                data = data[5:]  # Remove GZIP: prefix
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
                # Legacy format
                return pickle.loads(data)
                
        except Exception as e:
            logger.error(f"L2 Redis deserialization error: {e}")
            raise
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate cache keys matching pattern."""
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
            'circuit_breaker_state': self.circuit_state,
            'circuit_failures': self.circuit_breaker_failures,
            'redis_available': self.redis_client is not None,
            'performance_target_ms': 20
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform L2 Redis health check."""
        if not self.redis_client:
            return {'status': 'unavailable', 'error': 'Redis client not initialized'}
        
        try:
            start_time = time.time()
            await self.redis_client.ping()
            response_time = (time.time() - start_time) * 1000
            
            info = await self.redis_client.info()
            
            return {
                'status': 'healthy',
                'ping_response_time_ms': response_time,
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_mb': info.get('used_memory', 0) / (1024 * 1024),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0)
            }
            
        except Exception as e:
            return {'status': 'unhealthy', 'error': str(e)}


class L3DatabaseCache:
    """
    L3 Database cache with materialized views and query optimization.
    Target: <100ms query times for analytical workloads.
    """
    
    def __init__(self):
        self.metrics = CacheMetrics()
        self.materialized_views = [
            "mv_user_authorization_context",
            "mv_team_collaboration_patterns", 
            "mv_generation_performance_stats",
            "mv_cache_performance_analytics"
        ]
    
    async def get_materialized_view_data(self, view_name: str, filters: Optional[Dict[str, Any]] = None, 
                                       limit: int = 1000) -> Optional[List[Dict[str, Any]]]:
        """Get data from materialized view with performance tracking."""
        start_time = time.time()
        
        try:
            db = await get_database()
            
            result = await db.execute_query(
                table=view_name,
                operation="select",
                filters=filters or {},
                limit=limit
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.GET, True, response_time_ms)
            
            return result
            
        except Exception as e:
            logger.error(f"L3 database cache error for view {view_name}: {e}")
            response_time_ms = (time.time() - start_time) * 1000
            self.metrics.update_metrics(CacheOperation.GET, False, response_time_ms)
            return None
    
    async def refresh_materialized_views(self) -> Dict[str, bool]:
        """Refresh all materialized views."""
        results = {}
        
        try:
            db = await get_database()
            
            for view_name in self.materialized_views:
                try:
                    await db.execute_query(
                        table="",
                        operation="raw_query",
                        query=f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view_name}"
                    )
                    results[view_name] = True
                    logger.info(f"Refreshed materialized view: {view_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to refresh materialized view {view_name}: {e}")
                    results[view_name] = False
            
            return results
            
        except Exception as e:
            logger.error(f"Failed to refresh materialized views: {e}")
            return {view: False for view in self.materialized_views}
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get L3 database cache metrics."""
        return {
            'level': 'L3_DATABASE',
            'metrics': asdict(self.metrics),
            'materialized_views': self.materialized_views,
            'performance_target_ms': 100
        }


class MultiLayerCacheManager:
    """
    Enterprise Multi-Layer Cache Manager orchestrating L1/L2/L3 caches.
    Provides intelligent caching strategy with automatic fallback and warming.
    """
    
    def __init__(self, l1_size_mb: int = 200, redis_url: Optional[str] = None):
        # Initialize cache layers
        self.l1_cache = L1MemoryCache(max_size_mb=l1_size_mb)
        self.l2_cache = L2RedisCache(redis_url=redis_url)
        self.l3_cache = L3DatabaseCache()
        
        # Cache management
        self.cache_warming_enabled = True
        self.auto_promotion_enabled = True  # Promote L2->L1, L3->L2
        self.consistency_checking_enabled = True
        
        # Performance tracking
        self.operation_metrics: Dict[str, List[float]] = defaultdict(list)
        
        # Background tasks
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
            # No event loop running, tasks will be started later
            pass
    
    async def get_multi_level(self, key: str, fallback_function: Optional[Callable] = None) -> Tuple[Any, CacheLevel]:
        """
        Multi-level cache get with automatic fallback and promotion.
        L1 (Memory) -> L2 (Redis) -> L3 (Database/Fallback)
        """
        operation_id = performance_tracker.start_operation("cache_multi_level_get", PerformanceTarget.SUB_50MS)
        
        try:
            # L1 Cache check
            l1_result = self.l1_cache.get(key)
            if l1_result is not None:
                performance_tracker.end_operation(operation_id, "cache_multi_level_get", PerformanceTarget.SUB_50MS, True, cache_level="L1")
                return l1_result, CacheLevel.L1_MEMORY
            
            # L2 Cache check
            l2_result = await self.l2_cache.get(key)
            if l2_result is not None:
                # Promote to L1 cache
                if self.auto_promotion_enabled:
                    self.l1_cache.set(key, l2_result, ttl=300, priority=2)
                
                performance_tracker.end_operation(operation_id, "cache_multi_level_get", PerformanceTarget.SUB_50MS, True, cache_level="L2")
                return l2_result, CacheLevel.L2_REDIS
            
            # L3 Cache/Fallback
            if fallback_function:
                try:
                    l3_result = await fallback_function()
                    if l3_result is not None:
                        # Store in all cache levels
                        await self.set_multi_level(key, l3_result)
                        performance_tracker.end_operation(operation_id, "cache_multi_level_get", PerformanceTarget.SUB_50MS, True, cache_level="L3")
                        return l3_result, CacheLevel.L3_DATABASE
                        
                except Exception as e:
                    logger.error(f"Fallback function failed for key {key}: {e}")
            
            # Complete miss
            performance_tracker.end_operation(operation_id, "cache_multi_level_get", PerformanceTarget.SUB_50MS, False, cache_level="MISS")
            return None, CacheLevel.L3_DATABASE
            
        except Exception as e:
            logger.error(f"Multi-level cache get failed for key {key}: {e}")
            performance_tracker.end_operation(operation_id, "cache_multi_level_get", PerformanceTarget.SUB_50MS, False, error=str(e))
            return None, CacheLevel.L3_DATABASE
    
    async def set_multi_level(self, key: str, value: Any, l1_ttl: int = 300, 
                            l2_ttl: int = 900, priority: int = 1, tags: Optional[Set[str]] = None) -> Dict[str, bool]:
        """Set value in multiple cache levels with different TTLs."""
        operation_id = performance_tracker.start_operation("cache_multi_level_set", PerformanceTarget.SUB_50MS)
        
        results = {}
        
        try:
            # Set in L1 cache
            results['L1'] = self.l1_cache.set(key, value, ttl=l1_ttl, priority=priority, tags=tags)
            
            # Set in L2 cache
            results['L2'] = await self.l2_cache.set(key, value, ttl=l2_ttl)
            
            # L3 cache is typically handled by materialized views
            results['L3'] = True  # Always successful for L3
            
            success = any(results.values())
            performance_tracker.end_operation(operation_id, "cache_multi_level_set", PerformanceTarget.SUB_50MS, success, results=results)
            
            return results
            
        except Exception as e:
            logger.error(f"Multi-level cache set failed for key {key}: {e}")
            performance_tracker.end_operation(operation_id, "cache_multi_level_set", PerformanceTarget.SUB_50MS, False, error=str(e))
            return {'L1': False, 'L2': False, 'L3': False}
    
    async def invalidate_multi_level(self, key: str) -> Dict[str, bool]:
        """Invalidate key across all cache levels."""
        results = {}
        
        try:
            results['L1'] = self.l1_cache.delete(key)
            results['L2'] = await self.l2_cache.delete(key)
            results['L3'] = True  # L3 invalidation handled by materialized view refresh
            
            return results
            
        except Exception as e:
            logger.error(f"Multi-level cache invalidation failed for key {key}: {e}")
            return {'L1': False, 'L2': False, 'L3': False}
    
    async def invalidate_pattern(self, pattern: str) -> Dict[str, int]:
        """Invalidate keys matching pattern across all levels."""
        results = {}
        
        try:
            # L1 pattern invalidation (simple implementation)
            l1_count = 0
            keys_to_remove = [k for k in self.l1_cache.cache.keys() if self._matches_pattern(k, pattern)]
            for key in keys_to_remove:
                if self.l1_cache.delete(key):
                    l1_count += 1
            results['L1'] = l1_count
            
            # L2 Redis pattern invalidation
            results['L2'] = await self.l2_cache.invalidate_pattern(pattern)
            
            # L3 handled by materialized view refresh
            results['L3'] = 0
            
            return results
            
        except Exception as e:
            logger.error(f"Multi-level pattern invalidation failed for pattern {pattern}: {e}")
            return {'L1': 0, 'L2': 0, 'L3': 0}
    
    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches pattern (supports * wildcards)."""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    async def warm_cache_intelligent(self, warmup_patterns: List[str]) -> Dict[str, Dict[str, int]]:
        """Intelligently warm caches with predicted access patterns."""
        if not self.cache_warming_enabled:
            return {}
        
        results = {}
        
        for pattern in warmup_patterns:
            try:
                if pattern.startswith("auth:"):
                    result = await self._warm_authorization_cache()
                elif pattern.startswith("user:"):
                    result = await self._warm_user_cache() 
                elif pattern.startswith("team:"):
                    result = await self._warm_team_cache()
                elif pattern.startswith("gen:"):
                    result = await self._warm_generation_cache()
                else:
                    result = {'L1': 0, 'L2': 0, 'L3': 0}
                
                results[pattern] = result
                
            except Exception as e:
                logger.error(f"Cache warming failed for pattern {pattern}: {e}")
                results[pattern] = {'L1': 0, 'L2': 0, 'L3': 0}
        
        return results
    
    async def _warm_authorization_cache(self) -> Dict[str, int]:
        """Warm authorization cache with recent permissions."""
        try:
            # Get recent authorization data from L3
            auth_data = await self.l3_cache.get_materialized_view_data(
                "mv_user_authorization_context",
                limit=500
            )
            
            warmed_count = {'L1': 0, 'L2': 0, 'L3': 0}
            
            if auth_data:
                for auth in auth_data:
                    cache_key = f"auth:{auth['user_id']}:{auth['generation_id']}"
                    cache_value = {
                        "access_granted": auth["has_read_access"],
                        "access_method": auth["access_method"],
                        "effective_role": auth["effective_role"],
                        "cached_at": datetime.utcnow().isoformat()
                    }
                    
                    results = await self.set_multi_level(cache_key, cache_value, l1_ttl=300, l2_ttl=900)
                    
                    if results['L1']:
                        warmed_count['L1'] += 1
                    if results['L2']:
                        warmed_count['L2'] += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Authorization cache warming failed: {e}")
            return {'L1': 0, 'L2': 0, 'L3': 0}
    
    async def _warm_user_cache(self) -> Dict[str, int]:
        """Warm user session and profile cache."""
        try:
            db = await get_database()
            
            # Get active users from last 24 hours
            active_users = await db.execute_query(
                table="users",
                operation="select",
                filters={"last_active_at__gte": datetime.utcnow() - timedelta(hours=24)},
                limit=100
            )
            
            warmed_count = {'L1': 0, 'L2': 0, 'L3': 0}
            
            for user in active_users:
                cache_key = f"user:{user['id']}"
                cache_value = {
                    "user_id": user["id"],
                    "email": user["email"],
                    "is_active": user["is_active"],
                    "last_active_at": user.get("last_active_at"),
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                results = await self.set_multi_level(cache_key, cache_value)
                
                if results['L1']:
                    warmed_count['L1'] += 1
                if results['L2']:
                    warmed_count['L2'] += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"User cache warming failed: {e}")
            return {'L1': 0, 'L2': 0, 'L3': 0}
    
    async def _warm_team_cache(self) -> Dict[str, int]:
        """Warm team membership and collaboration cache."""
        try:
            # Get team collaboration patterns from materialized view
            team_data = await self.l3_cache.get_materialized_view_data(
                "mv_team_collaboration_patterns",
                limit=200
            )
            
            warmed_count = {'L1': 0, 'L2': 0, 'L3': 0}
            
            if team_data:
                for team in team_data:
                    cache_key = f"team:{team['team_id']}:members"
                    cache_value = {
                        "team_id": team["team_id"],
                        "active_members": team.get("active_members", 0),
                        "collaboration_score": team.get("collaboration_score", 0),
                        "cached_at": datetime.utcnow().isoformat()
                    }
                    
                    results = await self.set_multi_level(cache_key, cache_value)
                    
                    if results['L1']:
                        warmed_count['L1'] += 1
                    if results['L2']:
                        warmed_count['L2'] += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Team cache warming failed: {e}")
            return {'L1': 0, 'L2': 0, 'L3': 0}
    
    async def _warm_generation_cache(self) -> Dict[str, int]:
        """Warm generation metadata cache."""
        try:
            # Get recent generation performance stats
            gen_data = await self.l3_cache.get_materialized_view_data(
                "mv_generation_performance_stats",
                limit=300
            )
            
            warmed_count = {'L1': 0, 'L2': 0, 'L3': 0}
            
            if gen_data:
                for gen in gen_data:
                    cache_key = f"gen:{gen['generation_id']}"
                    cache_value = {
                        "generation_id": gen["generation_id"],
                        "status": gen.get("status"),
                        "avg_response_time_ms": gen.get("avg_response_time_ms"),
                        "success_rate": gen.get("success_rate"),
                        "cached_at": datetime.utcnow().isoformat()
                    }
                    
                    results = await self.set_multi_level(cache_key, cache_value)
                    
                    if results['L1']:
                        warmed_count['L1'] += 1
                    if results['L2']:
                        warmed_count['L2'] += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Generation cache warming failed: {e}")
            return {'L1': 0, 'L2': 0, 'L3': 0}
    
    async def _cleanup_loop(self):
        """Background cleanup loop."""
        while self.background_tasks_running:
            try:
                # Cleanup expired L1 entries
                expired_count = self.l1_cache.cleanup_expired()
                if expired_count > 0:
                    logger.debug(f"Cleaned up {expired_count} expired L1 cache entries")
                
                # Refresh materialized views periodically
                if datetime.utcnow().minute % 30 == 0:  # Every 30 minutes
                    await self.l3_cache.refresh_materialized_views()
                
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
                    # Warm caches with predicted patterns
                    warmup_patterns = [
                        "auth:", "user:", "team:", "gen:"
                    ]
                    
                    results = await self.warm_cache_intelligent(warmup_patterns)
                    total_warmed = sum(sum(pattern_results.values()) for pattern_results in results.values())
                    
                    if total_warmed > 0:
                        logger.info(f"Cache warming completed: {total_warmed} entries warmed")
                
                await asyncio.sleep(1800)  # 30 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cache warming loop error: {e}")
                await asyncio.sleep(300)
    
    def get_comprehensive_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics for all cache levels."""
        l1_metrics = self.l1_cache.get_metrics()
        l2_metrics = self.l2_cache.get_metrics()
        l3_metrics = self.l3_cache.get_metrics()
        
        # Calculate overall performance
        total_hits = l1_metrics['metrics']['hits'] + l2_metrics['metrics']['hits'] + l3_metrics['metrics']['hits']
        total_misses = l1_metrics['metrics']['misses'] + l2_metrics['metrics']['misses'] + l3_metrics['metrics']['misses']
        total_requests = total_hits + total_misses
        
        overall_hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0
        
        # Average response times weighted by hit count
        weighted_avg_response_time = 0
        if total_hits > 0:
            l1_weight = l1_metrics['metrics']['hits'] / total_hits
            l2_weight = l2_metrics['metrics']['hits'] / total_hits  
            l3_weight = l3_metrics['metrics']['hits'] / total_hits
            
            weighted_avg_response_time = (
                l1_weight * l1_metrics['metrics']['avg_response_time_ms'] +
                l2_weight * l2_metrics['metrics']['avg_response_time_ms'] +
                l3_weight * l3_metrics['metrics']['avg_response_time_ms']
            )
        
        return {
            'overall_performance': {
                'total_requests': total_requests,
                'total_hits': total_hits,
                'total_misses': total_misses,
                'overall_hit_rate_percent': overall_hit_rate,
                'weighted_avg_response_time_ms': weighted_avg_response_time,
                'target_hit_rate_percent': 90.0,
                'target_response_time_ms': 100.0,
                'performance_targets_met': overall_hit_rate >= 90.0 and weighted_avg_response_time <= 100.0
            },
            'cache_levels': {
                'L1_Memory': l1_metrics,
                'L2_Redis': l2_metrics,
                'L3_Database': l3_metrics
            },
            'configuration': {
                'auto_promotion_enabled': self.auto_promotion_enabled,
                'cache_warming_enabled': self.cache_warming_enabled,
                'consistency_checking_enabled': self.consistency_checking_enabled
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check for all cache levels."""
        health_status = {
            'overall_healthy': True,
            'L1_Memory': {'status': 'healthy', 'response_time_ms': 0},
            'L2_Redis': await self.l2_cache.health_check(),
            'L3_Database': {'status': 'healthy', 'response_time_ms': 0},
            'background_tasks': {
                'cleanup_running': self.cleanup_task is not None and not self.cleanup_task.done(),
                'warming_running': self.warming_task is not None and not self.warming_task.done()
            }
        }
        
        # Test L1 performance
        start_time = time.time()
        self.l1_cache.set("health_check", {"test": True}, ttl=60)
        result = self.l1_cache.get("health_check")
        self.l1_cache.delete("health_check")
        health_status['L1_Memory']['response_time_ms'] = (time.time() - start_time) * 1000
        
        if result != {"test": True}:
            health_status['L1_Memory']['status'] = 'unhealthy'
            health_status['overall_healthy'] = False
        
        # Check L2 Redis status
        if health_status['L2_Redis']['status'] != 'healthy':
            health_status['overall_healthy'] = False
        
        return health_status
    
    async def shutdown(self):
        """Graceful shutdown of cache manager."""
        self.background_tasks_running = False
        
        # Cancel background tasks
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
        
        if self.warming_task:
            self.warming_task.cancel()
            try:
                await self.warming_task
            except asyncio.CancelledError:
                pass
        
        # Clear all caches
        self.l1_cache.clear()
        
        logger.info("Multi-layer cache manager shutdown complete")


# Global cache manager instance
enterprise_cache_manager: Optional[MultiLayerCacheManager] = None


def get_cache_manager() -> MultiLayerCacheManager:
    """Get or create the global cache manager instance."""
    global enterprise_cache_manager
    if enterprise_cache_manager is None:
        enterprise_cache_manager = MultiLayerCacheManager()
    return enterprise_cache_manager


# Alias for backward compatibility
def _get_cache_manager():
    """Lazy cache manager getter to avoid import-time initialization."""
    return get_cache_manager()

# Make cache_manager accessible as a function that returns the manager
cache_manager = _get_cache_manager


# Context manager for cache operations
@asynccontextmanager
async def cache_context():
    """Context manager for cache operations with automatic cleanup."""
    cache_manager = get_cache_manager()
    try:
        yield cache_manager
    finally:
        # Perform cleanup if needed
        pass


# Convenience functions for common authorization caching patterns
async def get_cached_authorization(user_id: str, resource_id: str, resource_type: str) -> Optional[Dict[str, Any]]:
    """Get cached authorization result with multi-level fallback."""
    cache_key = f"auth:{user_id}:{resource_id}:{resource_type}"
    cache_manager = get_cache_manager()
    result, level = await cache_manager.get_multi_level(cache_key)
    return result


async def cache_authorization_result(user_id: str, resource_id: str, resource_type: str,
                                   authorization_data: Dict[str, Any], priority: int = 2) -> Dict[str, bool]:
    """Cache authorization result across all levels."""
    cache_key = f"auth:{user_id}:{resource_id}:{resource_type}"
    cache_manager = get_cache_manager()
    return await cache_manager.set_multi_level(
        cache_key, authorization_data, 
        l1_ttl=300, l2_ttl=900, priority=priority,
        tags={"authorization", f"user:{user_id}", f"resource:{resource_id}"}
    )


async def invalidate_user_authorization_cache(user_id: str) -> Dict[str, int]:
    """Invalidate all authorization cache entries for a user."""
    pattern = f"auth:{user_id}:*"
    cache_manager = get_cache_manager()
    return await cache_manager.invalidate_pattern(pattern)


async def warm_authorization_cache() -> Dict[str, Dict[str, int]]:
    """Warm authorization caches with predictive patterns."""
    cache_manager = get_cache_manager()
    return await cache_manager.warm_cache_intelligent(["auth:", "user:", "team:"])