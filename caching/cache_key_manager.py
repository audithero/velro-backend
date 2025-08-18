"""
Optimized Cache Key Manager for Multi-Layer Caching
Provides hierarchical key structures, optimal patterns, and namespace management.

Features:
- Hierarchical key structures for efficient invalidation
- Namespace management and collision prevention
- TTL optimization based on data type and access patterns
- Key compression and optimization
- Tag-based grouping for bulk operations
- Performance-optimized key generation <1ms
"""

import hashlib
import json
import time
from typing import Dict, Any, List, Optional, Set, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from uuid import UUID

import logging

logger = logging.getLogger(__name__)


class KeyType(Enum):
    """Cache key types with different characteristics."""
    AUTHORIZATION = "auth"          # High priority, medium TTL
    USER_SESSION = "session"        # High priority, short TTL
    USER_PROFILE = "profile"        # Medium priority, long TTL
    GENERATION_METADATA = "gen"     # High priority, medium TTL
    TEAM_MEMBERSHIP = "team"        # Medium priority, medium TTL
    PROJECT_ACCESS = "project"      # Medium priority, long TTL
    SYSTEM_CONFIG = "config"        # Low priority, very long TTL
    TEMPORARY = "temp"              # Low priority, very short TTL
    ANALYTICS = "analytics"         # Low priority, long TTL


class AccessPattern(Enum):
    """Cache access patterns for TTL optimization."""
    HOT = "hot"                     # Very frequent access (>100/min)
    WARM = "warm"                   # Regular access (10-100/min)
    COLD = "cold"                   # Infrequent access (<10/min)
    BURST = "burst"                 # Burst access patterns
    PREDICTABLE = "predictable"     # Predictable access times


@dataclass
class KeyMetadata:
    """Metadata for cache key optimization."""
    key_type: KeyType
    access_pattern: AccessPattern
    priority: int                   # 1-10, higher = more important
    estimated_size_bytes: int = 0
    tags: Set[str] = field(default_factory=set)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = 0
    access_count: int = 0
    compression_enabled: bool = True
    
    def update_access(self):
        """Update access statistics."""
        self.last_accessed = time.time()
        self.access_count += 1


@dataclass
class TTLConfiguration:
    """TTL configuration for different key types and patterns."""
    l1_ttl: int                     # L1 Memory cache TTL (seconds)
    l2_ttl: int                     # L2 Redis cache TTL (seconds)
    l3_ttl: Optional[int] = None    # L3 Database cache TTL (seconds)
    adaptive: bool = False          # Enable adaptive TTL based on access patterns


class CacheKeyManager:
    """
    High-performance cache key manager with hierarchical structures
    and intelligent TTL management.
    """
    
    def __init__(self):
        self.namespace_prefix = "velro:v2"
        self.key_metadata: Dict[str, KeyMetadata] = {}
        self.key_statistics: Dict[str, Dict[str, Any]] = {}
        
        # TTL configurations optimized for different patterns
        self.ttl_configs = {
            KeyType.AUTHORIZATION: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=300, l2_ttl=900, adaptive=True),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=600, l2_ttl=1800, adaptive=True),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=300, l2_ttl=3600, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=180, l2_ttl=600, adaptive=True),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=900, l2_ttl=3600, adaptive=False)
            },
            KeyType.USER_SESSION: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=600, l2_ttl=3600, adaptive=True),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=1200, l2_ttl=7200, adaptive=True),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=300, l2_ttl=1800, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=300, l2_ttl=1800, adaptive=True),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=False)
            },
            KeyType.USER_PROFILE: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=True),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=3600, l2_ttl=14400, adaptive=True),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=900, l2_ttl=3600, adaptive=True),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=7200, l2_ttl=28800, adaptive=False)
            },
            KeyType.GENERATION_METADATA: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=600, l2_ttl=1800, adaptive=True),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=1200, l2_ttl=3600, adaptive=True),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=300, l2_ttl=1800, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=300, l2_ttl=900, adaptive=True),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=False)
            },
            KeyType.TEAM_MEMBERSHIP: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=1200, l2_ttl=3600, adaptive=True),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=True),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=900, l2_ttl=3600, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=600, l2_ttl=1800, adaptive=True),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=3600, l2_ttl=14400, adaptive=False)
            },
            KeyType.PROJECT_ACCESS: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=True),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=3600, l2_ttl=14400, adaptive=True),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=900, l2_ttl=3600, adaptive=True),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=7200, l2_ttl=28800, adaptive=False)
            },
            KeyType.SYSTEM_CONFIG: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=3600, l2_ttl=14400, adaptive=False),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=7200, l2_ttl=28800, adaptive=False),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=3600, l2_ttl=14400, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=False),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=14400, l2_ttl=86400, adaptive=False)
            },
            KeyType.TEMPORARY: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=60, l2_ttl=300, adaptive=True),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=120, l2_ttl=600, adaptive=True),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=60, l2_ttl=300, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=30, l2_ttl=120, adaptive=True),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=300, l2_ttl=1800, adaptive=False)
            },
            KeyType.ANALYTICS: {
                AccessPattern.HOT: TTLConfiguration(l1_ttl=1800, l2_ttl=7200, adaptive=False),
                AccessPattern.WARM: TTLConfiguration(l1_ttl=3600, l2_ttl=14400, adaptive=False),
                AccessPattern.COLD: TTLConfiguration(l1_ttl=7200, l2_ttl=28800, adaptive=False),
                AccessPattern.BURST: TTLConfiguration(l1_ttl=900, l2_ttl=3600, adaptive=False),
                AccessPattern.PREDICTABLE: TTLConfiguration(l1_ttl=14400, l2_ttl=86400, adaptive=False)
            }
        }
    
    def generate_hierarchical_key(self, key_type: KeyType, 
                                 components: List[str],
                                 access_pattern: AccessPattern = AccessPattern.WARM,
                                 priority: int = 5,
                                 tags: Optional[Set[str]] = None) -> Tuple[str, KeyMetadata]:
        """
        Generate hierarchical cache key with metadata.
        
        Key format: {namespace}:{type}:{component1}:{component2}:...
        Examples:
        - velro:v2:auth:user:123:gen:456:read
        - velro:v2:session:user:123:active
        - velro:v2:profile:user:123:settings
        """
        # Validate and sanitize components
        sanitized_components = []
        for component in components:
            if isinstance(component, UUID):
                sanitized_components.append(str(component))
            elif isinstance(component, (int, float)):
                sanitized_components.append(str(component))
            elif isinstance(component, str):
                # Remove potentially problematic characters
                sanitized = component.replace(':', '_').replace(' ', '_').strip()
                sanitized_components.append(sanitized)
            else:
                sanitized_components.append(str(component))
        
        # Build hierarchical key
        key_parts = [
            self.namespace_prefix,
            key_type.value
        ] + sanitized_components
        
        cache_key = ':'.join(key_parts)
        
        # Create metadata
        metadata = KeyMetadata(
            key_type=key_type,
            access_pattern=access_pattern,
            priority=priority,
            tags=tags or set(),
            compression_enabled=len(cache_key) > 100  # Enable compression for longer keys
        )
        
        # Store metadata
        self.key_metadata[cache_key] = metadata
        
        return cache_key, metadata
    
    def generate_authorization_key(self, user_id: Union[str, UUID], 
                                  resource_id: Union[str, UUID],
                                  resource_type: str,
                                  operation: str = "read",
                                  access_pattern: AccessPattern = AccessPattern.HOT) -> Tuple[str, KeyMetadata]:
        """Generate optimized authorization cache key."""
        components = [
            "user", str(user_id),
            resource_type, str(resource_id),
            operation
        ]
        
        tags = {
            "authorization",
            f"user:{user_id}",
            f"{resource_type}:{resource_id}",
            f"operation:{operation}"
        }
        
        return self.generate_hierarchical_key(
            KeyType.AUTHORIZATION,
            components,
            access_pattern=access_pattern,
            priority=8,  # High priority for authorization
            tags=tags
        )
    
    def generate_user_session_key(self, user_id: Union[str, UUID],
                                 session_type: str = "active",
                                 access_pattern: AccessPattern = AccessPattern.HOT) -> Tuple[str, KeyMetadata]:
        """Generate user session cache key."""
        components = [
            "user", str(user_id),
            session_type
        ]
        
        tags = {
            "session",
            f"user:{user_id}",
            f"session_type:{session_type}"
        }
        
        return self.generate_hierarchical_key(
            KeyType.USER_SESSION,
            components,
            access_pattern=access_pattern,
            priority=7,
            tags=tags
        )
    
    def generate_generation_key(self, generation_id: Union[str, UUID],
                               metadata_type: str = "metadata",
                               access_pattern: AccessPattern = AccessPattern.WARM) -> Tuple[str, KeyMetadata]:
        """Generate generation metadata cache key."""
        components = [
            "generation", str(generation_id),
            metadata_type
        ]
        
        tags = {
            "generation",
            f"generation:{generation_id}",
            f"metadata_type:{metadata_type}"
        }
        
        return self.generate_hierarchical_key(
            KeyType.GENERATION_METADATA,
            components,
            access_pattern=access_pattern,
            priority=6,
            tags=tags
        )
    
    def generate_team_key(self, team_id: Union[str, UUID],
                         user_id: Union[str, UUID],
                         data_type: str = "membership",
                         access_pattern: AccessPattern = AccessPattern.WARM) -> Tuple[str, KeyMetadata]:
        """Generate team-related cache key."""
        components = [
            "team", str(team_id),
            "user", str(user_id),
            data_type
        ]
        
        tags = {
            "team",
            f"team:{team_id}",
            f"user:{user_id}",
            f"data_type:{data_type}"
        }
        
        return self.generate_hierarchical_key(
            KeyType.TEAM_MEMBERSHIP,
            components,
            access_pattern=access_pattern,
            priority=5,
            tags=tags
        )
    
    def generate_user_profile_key(self, user_id: Union[str, UUID],
                                 profile_type: str = "basic",
                                 access_pattern: AccessPattern = AccessPattern.WARM) -> Tuple[str, KeyMetadata]:
        """Generate user profile cache key."""
        components = [
            "user", str(user_id),
            profile_type
        ]
        
        tags = {
            "profile",
            f"user:{user_id}",
            f"profile_type:{profile_type}"
        }
        
        return self.generate_hierarchical_key(
            KeyType.USER_PROFILE,
            components,
            access_pattern=access_pattern,
            priority=4,
            tags=tags
        )
    
    def get_optimal_ttl(self, cache_key: str) -> TTLConfiguration:
        """Get optimal TTL configuration for cache key."""
        metadata = self.key_metadata.get(cache_key)
        if not metadata:
            # Default configuration for unknown keys
            return TTLConfiguration(l1_ttl=300, l2_ttl=900, adaptive=False)
        
        ttl_config = self.ttl_configs.get(metadata.key_type, {}).get(
            metadata.access_pattern,
            TTLConfiguration(l1_ttl=300, l2_ttl=900, adaptive=False)
        )
        
        # Apply adaptive TTL adjustment if enabled
        if ttl_config.adaptive:
            ttl_config = self._apply_adaptive_ttl(cache_key, ttl_config, metadata)
        
        return ttl_config
    
    def _apply_adaptive_ttl(self, cache_key: str, 
                           base_config: TTLConfiguration,
                           metadata: KeyMetadata) -> TTLConfiguration:
        """Apply adaptive TTL based on access patterns."""
        now = time.time()
        
        # Calculate access frequency (accesses per minute)
        time_since_created = max(1, now - metadata.created_at)
        access_frequency = (metadata.access_count / time_since_created) * 60
        
        # Calculate recency factor
        time_since_last_access = now - metadata.last_accessed if metadata.last_accessed > 0 else time_since_created
        recency_factor = max(0.1, 1.0 - (time_since_last_access / 3600))  # 1 hour decay
        
        # Adaptive multipliers
        frequency_multiplier = 1.0
        if access_frequency > 100:          # Very hot
            frequency_multiplier = 1.5
        elif access_frequency > 50:        # Hot
            frequency_multiplier = 1.3
        elif access_frequency > 10:        # Warm
            frequency_multiplier = 1.0
        elif access_frequency > 1:         # Cool
            frequency_multiplier = 0.8
        else:                               # Cold
            frequency_multiplier = 0.6
        
        # Apply adaptive adjustments
        adaptive_l1_ttl = int(base_config.l1_ttl * frequency_multiplier * recency_factor)
        adaptive_l2_ttl = int(base_config.l2_ttl * frequency_multiplier * recency_factor)
        
        # Ensure minimum TTL values
        adaptive_l1_ttl = max(60, adaptive_l1_ttl)    # Minimum 1 minute
        adaptive_l2_ttl = max(300, adaptive_l2_ttl)   # Minimum 5 minutes
        
        return TTLConfiguration(
            l1_ttl=adaptive_l1_ttl,
            l2_ttl=adaptive_l2_ttl,
            l3_ttl=base_config.l3_ttl,
            adaptive=True
        )
    
    def update_key_access(self, cache_key: str):
        """Update access statistics for cache key."""
        metadata = self.key_metadata.get(cache_key)
        if metadata:
            metadata.update_access()
            
            # Update statistics
            if cache_key not in self.key_statistics:
                self.key_statistics[cache_key] = {
                    "total_accesses": 0,
                    "last_access_frequency": 0.0,
                    "access_pattern_changes": 0
                }
            
            stats = self.key_statistics[cache_key]
            stats["total_accesses"] += 1
            stats["last_access_frequency"] = self._calculate_access_frequency(metadata)
    
    def _calculate_access_frequency(self, metadata: KeyMetadata) -> float:
        """Calculate current access frequency for key."""
        now = time.time()
        time_window = now - metadata.created_at
        if time_window <= 0:
            return 0.0
        
        return (metadata.access_count / time_window) * 60  # Accesses per minute
    
    def get_keys_by_pattern(self, pattern: str) -> List[str]:
        """Get all cache keys matching a pattern."""
        import fnmatch
        return [key for key in self.key_metadata.keys() 
                if fnmatch.fnmatch(key, pattern)]
    
    def get_keys_by_tag(self, tag: str) -> List[str]:
        """Get all cache keys with specific tag."""
        matching_keys = []
        for key, metadata in self.key_metadata.items():
            if tag in metadata.tags:
                matching_keys.append(key)
        return matching_keys
    
    def get_keys_by_type(self, key_type: KeyType) -> List[str]:
        """Get all cache keys of specific type."""
        matching_keys = []
        for key, metadata in self.key_metadata.items():
            if metadata.key_type == key_type:
                matching_keys.append(key)
        return matching_keys
    
    def generate_invalidation_patterns(self, entity_type: str, entity_id: Union[str, UUID]) -> List[str]:
        """Generate cache invalidation patterns for entity changes."""
        entity_id_str = str(entity_id)
        patterns = []
        
        if entity_type == "user":
            patterns.extend([
                f"{self.namespace_prefix}:*:user:{entity_id_str}:*",
                f"{self.namespace_prefix}:auth:user:{entity_id_str}:*",
                f"{self.namespace_prefix}:session:user:{entity_id_str}:*",
                f"{self.namespace_prefix}:profile:user:{entity_id_str}:*",
                f"{self.namespace_prefix}:team:*:user:{entity_id_str}:*"
            ])
        
        elif entity_type == "generation":
            patterns.extend([
                f"{self.namespace_prefix}:*:*:generation:{entity_id_str}:*",
                f"{self.namespace_prefix}:gen:generation:{entity_id_str}:*",
                f"{self.namespace_prefix}:auth:*:generation:{entity_id_str}:*"
            ])
        
        elif entity_type == "team":
            patterns.extend([
                f"{self.namespace_prefix}:team:team:{entity_id_str}:*",
                f"{self.namespace_prefix}:auth:*:team:{entity_id_str}:*",
                f"{self.namespace_prefix}:*:*:team:{entity_id_str}:*"
            ])
        
        elif entity_type == "project":
            patterns.extend([
                f"{self.namespace_prefix}:project:project:{entity_id_str}:*",
                f"{self.namespace_prefix}:auth:*:project:{entity_id_str}:*"
            ])
        
        return patterns
    
    def compress_key(self, cache_key: str) -> str:
        """Compress cache key for storage efficiency."""
        if len(cache_key) <= 100:  # Don't compress short keys
            return cache_key
        
        # Use hash for very long keys
        if len(cache_key) > 250:
            key_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:16]
            # Keep prefix and use hash for the rest
            parts = cache_key.split(':', 3)
            if len(parts) >= 3:
                return f"{parts[0]}:{parts[1]}:{parts[2]}:hash:{key_hash}"
            else:
                return f"{self.namespace_prefix}:compressed:{key_hash}"
        
        return cache_key
    
    def get_key_statistics(self) -> Dict[str, Any]:
        """Get cache key usage statistics."""
        total_keys = len(self.key_metadata)
        if total_keys == 0:
            return {"total_keys": 0}
        
        # Group by key type
        type_counts = {}
        access_pattern_counts = {}
        priority_distribution = {}
        
        for key, metadata in self.key_metadata.items():
            # Type counts
            type_name = metadata.key_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1
            
            # Access pattern counts
            pattern_name = metadata.access_pattern.value
            access_pattern_counts[pattern_name] = access_pattern_counts.get(pattern_name, 0) + 1
            
            # Priority distribution
            priority = metadata.priority
            priority_distribution[priority] = priority_distribution.get(priority, 0) + 1
        
        # Calculate average access frequency
        total_access_frequency = 0
        keys_with_access = 0
        for metadata in self.key_metadata.values():
            if metadata.access_count > 0:
                frequency = self._calculate_access_frequency(metadata)
                total_access_frequency += frequency
                keys_with_access += 1
        
        avg_access_frequency = total_access_frequency / keys_with_access if keys_with_access > 0 else 0
        
        return {
            "total_keys": total_keys,
            "type_distribution": type_counts,
            "access_pattern_distribution": access_pattern_counts,
            "priority_distribution": priority_distribution,
            "average_access_frequency": avg_access_frequency,
            "keys_with_access_data": keys_with_access,
            "compression_enabled_keys": sum(1 for m in self.key_metadata.values() if m.compression_enabled),
            "namespace_prefix": self.namespace_prefix,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    def cleanup_expired_metadata(self, max_age_hours: int = 24):
        """Clean up metadata for keys that haven't been accessed recently."""
        cutoff_time = time.time() - (max_age_hours * 3600)
        expired_keys = []
        
        for key, metadata in self.key_metadata.items():
            if metadata.last_accessed > 0 and metadata.last_accessed < cutoff_time:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.key_metadata[key]
            if key in self.key_statistics:
                del self.key_statistics[key]
        
        logger.info(f"Cleaned up metadata for {len(expired_keys)} expired cache keys")
        return len(expired_keys)


# Global cache key manager instance
cache_key_manager: Optional[CacheKeyManager] = None


def get_cache_key_manager() -> CacheKeyManager:
    """Get or create global cache key manager instance."""
    global cache_key_manager
    if cache_key_manager is None:
        cache_key_manager = CacheKeyManager()
    return cache_key_manager


# Convenience functions for common key patterns
def generate_auth_key(user_id: Union[str, UUID], 
                     resource_id: Union[str, UUID],
                     resource_type: str,
                     operation: str = "read") -> Tuple[str, KeyMetadata]:
    """Generate authorization cache key."""
    manager = get_cache_key_manager()
    return manager.generate_authorization_key(user_id, resource_id, resource_type, operation)


def generate_session_key(user_id: Union[str, UUID], 
                        session_type: str = "active") -> Tuple[str, KeyMetadata]:
    """Generate user session cache key."""
    manager = get_cache_key_manager()
    return manager.generate_user_session_key(user_id, session_type)


def get_optimal_ttl_for_key(cache_key: str) -> TTLConfiguration:
    """Get optimal TTL configuration for cache key."""
    manager = get_cache_key_manager()
    return manager.get_optimal_ttl(cache_key)


def update_key_access_stats(cache_key: str):
    """Update access statistics for cache key."""
    manager = get_cache_key_manager()
    manager.update_key_access(cache_key)


def generate_invalidation_patterns_for_entity(entity_type: str, 
                                            entity_id: Union[str, UUID]) -> List[str]:
    """Generate invalidation patterns for entity."""
    manager = get_cache_key_manager()
    return manager.generate_invalidation_patterns(entity_type, entity_id)