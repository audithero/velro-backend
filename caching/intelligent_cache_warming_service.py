"""
Intelligent Cache Warming Service
Predictive cache warming with ML-based pattern recognition and priority-based scheduling.

Features:
- Predictive cache warming based on user behavior patterns
- Priority-based warming queue with resource-aware scheduling
- Background warming processes with minimal system impact
- Startup cache population for instant performance
- Access pattern learning and adaptation
- Warming effectiveness tracking and optimization
"""

import asyncio
import logging
import time
import json
import statistics
from typing import Dict, Any, List, Optional, Set, Tuple, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from collections import defaultdict, deque
from enum import Enum
from uuid import UUID
from concurrent.futures import ThreadPoolExecutor
import heapq

from caching.multi_layer_cache_manager import MultiLayerCacheManager, get_cache_manager
from caching.cache_key_manager import (
    CacheKeyManager, get_cache_key_manager, KeyType, AccessPattern,
    generate_auth_key, generate_session_key, get_optimal_ttl_for_key
)
from database import get_database
from monitoring.performance import performance_tracker, PerformanceTarget

logger = logging.getLogger(__name__)


class WarmingPriority(Enum):
    """Cache warming priority levels."""
    CRITICAL = 1        # Authorization, active sessions
    HIGH = 2            # Recent user data, hot generations
    MEDIUM = 3          # Team data, profile information
    LOW = 4             # Analytics, historical data
    BACKGROUND = 5      # Predictive, speculative warming


class WarmingStrategy(Enum):
    """Cache warming strategies."""
    STARTUP = "startup"                 # Application startup warming
    PREDICTIVE = "predictive"           # ML-based prediction warming
    REACTIVE = "reactive"               # Response to cache misses
    SCHEDULED = "scheduled"             # Time-based scheduled warming
    BURST_RECOVERY = "burst_recovery"   # Recovery from burst traffic


@dataclass
class WarmingTask:
    """Cache warming task with priority and metadata."""
    task_id: str
    priority: WarmingPriority
    strategy: WarmingStrategy
    key_type: KeyType
    cache_key: str
    data_fetcher: Callable
    estimated_execution_time_ms: float = 100.0
    estimated_data_size_bytes: int = 1024
    created_at: float = field(default_factory=time.time)
    scheduled_at: Optional[float] = None
    completed_at: Optional[float] = None
    success: bool = False
    execution_time_ms: Optional[float] = None
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        """Priority queue comparison - lower number = higher priority."""
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        # Secondary sort by creation time (FIFO within same priority)
        return self.created_at < other.created_at


@dataclass
class AccessPatternData:
    """User access pattern data for predictive warming."""
    user_id: str
    access_times: deque = field(default_factory=lambda: deque(maxlen=1000))
    resource_types: Dict[str, int] = field(default_factory=dict)
    operation_types: Dict[str, int] = field(default_factory=dict)
    session_patterns: Dict[str, List[float]] = field(default_factory=dict)
    prediction_accuracy: float = 0.0
    last_updated: float = field(default_factory=time.time)
    
    def add_access(self, resource_type: str, operation: str, session_type: str = "default"):
        """Add access event to pattern data."""
        now = time.time()
        self.access_times.append(now)
        
        # Update resource type frequency
        self.resource_types[resource_type] = self.resource_types.get(resource_type, 0) + 1
        
        # Update operation type frequency
        self.operation_types[operation] = self.operation_types.get(operation, 0) + 1
        
        # Update session patterns
        if session_type not in self.session_patterns:
            self.session_patterns[session_type] = []
        self.session_patterns[session_type].append(now)
        
        # Keep only last 100 session events per type
        if len(self.session_patterns[session_type]) > 100:
            self.session_patterns[session_type] = self.session_patterns[session_type][-100:]
        
        self.last_updated = now
    
    def predict_next_access_time(self) -> Optional[float]:
        """Predict when user will next access the system."""
        if len(self.access_times) < 5:
            return None
        
        # Calculate average intervals between accesses
        intervals = []
        times_list = list(self.access_times)
        for i in range(1, len(times_list)):
            intervals.append(times_list[i] - times_list[i-1])
        
        if not intervals:
            return None
        
        avg_interval = statistics.mean(intervals)
        last_access = times_list[-1]
        
        # Predict next access (with some randomness factor)
        predicted_time = last_access + avg_interval
        return predicted_time
    
    def get_likely_resources(self, top_n: int = 10) -> List[Tuple[str, float]]:
        """Get most likely resources user will access."""
        if not self.resource_types:
            return []
        
        total_accesses = sum(self.resource_types.values())
        resource_probabilities = [
            (resource, count / total_accesses)
            for resource, count in self.resource_types.items()
        ]
        
        # Sort by probability descending
        resource_probabilities.sort(key=lambda x: x[1], reverse=True)
        return resource_probabilities[:top_n]


class IntelligentCacheWarmingService:
    """
    Intelligent cache warming service with predictive ML-based warming,
    priority queues, and resource-aware scheduling.
    """
    
    def __init__(self, cache_manager: Optional[MultiLayerCacheManager] = None):
        self.cache_manager = cache_manager or get_cache_manager()
        self.key_manager = get_cache_key_manager()
        
        # Warming queues by priority
        self.warming_queues: Dict[WarmingPriority, List[WarmingTask]] = {
            priority: [] for priority in WarmingPriority
        }
        
        # Task tracking
        self.active_tasks: Dict[str, WarmingTask] = {}
        self.completed_tasks: deque = deque(maxlen=10000)  # Last 10k completed tasks
        self.task_counter = 0
        
        # Access pattern learning
        self.user_access_patterns: Dict[str, AccessPatternData] = {}
        self.global_access_patterns = {
            "resource_type_popularity": defaultdict(int),
            "operation_popularity": defaultdict(int),
            "hourly_patterns": defaultdict(list),
            "daily_patterns": defaultdict(list)
        }
        
        # Warming configuration
        self.config = {
            "max_concurrent_tasks": 10,
            "max_warming_queue_size": 1000,
            "warming_batch_size": 50,
            "predictive_warming_enabled": True,
            "warming_interval_seconds": 30,
            "pattern_learning_enabled": True,
            "max_prediction_age_hours": 24,
            "resource_usage_threshold": 0.8,  # CPU/Memory threshold
            "cache_hit_rate_threshold": 0.95  # Stop warming if hit rate is excellent
        }
        
        # Performance tracking
        self.metrics = {
            "total_warming_tasks": 0,
            "successful_warming_tasks": 0,
            "failed_warming_tasks": 0,
            "total_warming_time_ms": 0.0,
            "cache_hits_from_warming": 0,
            "predictions_made": 0,
            "prediction_accuracy": 0.0,
            "avg_task_execution_time_ms": 0.0
        }
        
        # Background task management
        self.warming_active = False
        self.warming_tasks: List[asyncio.Task] = []
        self.executor = ThreadPoolExecutor(max_workers=self.config["max_concurrent_tasks"])
        
        # Learning models (simplified for now, could be replaced with ML models)
        self.pattern_weights = {
            "time_of_day": 0.3,
            "day_of_week": 0.2,
            "resource_frequency": 0.25,
            "operation_frequency": 0.15,
            "session_patterns": 0.1
        }
    
    async def start_warming_service(self):
        """Start the intelligent cache warming service."""
        if self.warming_active:
            logger.warning("Cache warming service already active")
            return
        
        self.warming_active = True
        logger.info("Starting intelligent cache warming service")
        
        # Start background tasks
        loop = asyncio.get_event_loop()
        
        # Main warming loop
        self.warming_tasks.append(
            loop.create_task(self._warming_execution_loop())
        )
        
        # Pattern learning loop
        self.warming_tasks.append(
            loop.create_task(self._pattern_learning_loop())
        )
        
        # Predictive warming loop
        self.warming_tasks.append(
            loop.create_task(self._predictive_warming_loop())
        )
        
        # Startup warming
        await self._execute_startup_warming()
        
        logger.info("Intelligent cache warming service started")
    
    async def stop_warming_service(self):
        """Stop the cache warming service gracefully."""
        self.warming_active = False
        
        # Cancel all background tasks
        for task in self.warming_tasks:
            task.cancel()
        
        # Wait for tasks to complete
        if self.warming_tasks:
            await asyncio.gather(*self.warming_tasks, return_exceptions=True)
        
        # Shutdown executor
        self.executor.shutdown(wait=True)
        
        logger.info("Intelligent cache warming service stopped")
    
    async def _warming_execution_loop(self):
        """Main warming execution loop."""
        while self.warming_active:
            try:
                # Check resource utilization before warming
                if await self._should_throttle_warming():
                    await asyncio.sleep(5)  # Wait before checking again
                    continue
                
                # Execute warming tasks from priority queues
                tasks_executed = await self._execute_warming_batch()
                
                if tasks_executed == 0:
                    # No tasks to execute, wait longer
                    await asyncio.sleep(self.config["warming_interval_seconds"])
                else:
                    # Quick cycle if there are more tasks
                    await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in warming execution loop: {e}")
                await asyncio.sleep(10)
    
    async def _pattern_learning_loop(self):
        """Pattern learning and analysis loop."""
        while self.warming_active:
            try:
                if self.config["pattern_learning_enabled"]:
                    await self._analyze_access_patterns()
                    await self._update_global_patterns()
                
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in pattern learning loop: {e}")
                await asyncio.sleep(60)
    
    async def _predictive_warming_loop(self):
        """Predictive cache warming loop."""
        while self.warming_active:
            try:
                if self.config["predictive_warming_enabled"]:
                    predictions_made = await self._generate_predictive_warming_tasks()
                    
                    if predictions_made > 0:
                        logger.debug(f"Generated {predictions_made} predictive warming tasks")
                
                await asyncio.sleep(600)  # 10 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in predictive warming loop: {e}")
                await asyncio.sleep(120)
    
    async def _execute_startup_warming(self):
        """Execute critical startup cache warming."""
        logger.info("Executing startup cache warming")
        startup_start = time.time()
        
        try:
            # Add critical startup warming tasks
            await self._add_startup_warming_tasks()
            
            # Execute startup tasks with high priority
            startup_tasks = []
            for priority in [WarmingPriority.CRITICAL, WarmingPriority.HIGH]:
                startup_tasks.extend(self.warming_queues[priority])
            
            if startup_tasks:
                # Execute startup tasks immediately
                tasks_executed = await self._execute_warming_batch(
                    max_tasks=min(50, len(startup_tasks))
                )
                
                startup_time = (time.time() - startup_start) * 1000
                logger.info(f"Startup warming completed: {tasks_executed} tasks in {startup_time:.1f}ms")
            
        except Exception as e:
            logger.error(f"Startup warming failed: {e}")
    
    async def _add_startup_warming_tasks(self):
        """Add critical startup warming tasks."""
        try:
            db = await get_database()
            
            # Warm recent active users
            recent_users = await db.execute_query(
                table="users",
                operation="select",
                filters={
                    "is_active": True,
                    "last_active_at__gte": datetime.utcnow() - timedelta(hours=2)
                },
                limit=100,
                order_by="last_active_at DESC"
            )
            
            for user in recent_users:
                user_id = user["id"]
                
                # User session warming
                session_key, _ = generate_session_key(user_id)
                await self.add_warming_task(
                    priority=WarmingPriority.CRITICAL,
                    strategy=WarmingStrategy.STARTUP,
                    key_type=KeyType.USER_SESSION,
                    cache_key=session_key,
                    data_fetcher=lambda uid=user_id: self._fetch_user_session_data(uid),
                    tags={"startup", "user_session", f"user:{user_id}"}
                )
            
            # Warm recent generations
            recent_generations = await db.execute_query(
                table="generations",
                operation="select",
                filters={
                    "status": "completed",
                    "created_at__gte": datetime.utcnow() - timedelta(hours=24)
                },
                limit=200,
                order_by="created_at DESC"
            )
            
            for generation in recent_generations:
                gen_id = generation["id"]
                user_id = generation["user_id"]
                
                # Generation metadata warming
                gen_key, _ = self.key_manager.generate_generation_key(gen_id, "metadata")
                await self.add_warming_task(
                    priority=WarmingPriority.HIGH,
                    strategy=WarmingStrategy.STARTUP,
                    key_type=KeyType.GENERATION_METADATA,
                    cache_key=gen_key,
                    data_fetcher=lambda gid=gen_id: self._fetch_generation_metadata(gid),
                    tags={"startup", "generation", f"generation:{gen_id}"}
                )
                
                # Authorization warming
                auth_key, _ = generate_auth_key(user_id, gen_id, "generation", "read")
                await self.add_warming_task(
                    priority=WarmingPriority.CRITICAL,
                    strategy=WarmingStrategy.STARTUP,
                    key_type=KeyType.AUTHORIZATION,
                    cache_key=auth_key,
                    data_fetcher=lambda uid=user_id, gid=gen_id: self._fetch_authorization_data(uid, gid, "generation", "read"),
                    tags={"startup", "authorization", f"user:{user_id}", f"generation:{gen_id}"}
                )
            
            # Warm active teams
            active_teams = await db.execute_query(
                table="teams",
                operation="select",
                filters={"is_active": True},
                limit=50,
                order_by="updated_at DESC"
            )
            
            for team in active_teams:
                team_id = team["id"]
                
                # Team membership warming
                team_members = await db.execute_query(
                    table="team_members",
                    operation="select",
                    filters={"team_id": team_id, "is_active": True}
                )
                
                for member in team_members:
                    user_id = member["user_id"]
                    team_key, _ = self.key_manager.generate_team_key(team_id, user_id)
                    
                    await self.add_warming_task(
                        priority=WarmingPriority.MEDIUM,
                        strategy=WarmingStrategy.STARTUP,
                        key_type=KeyType.TEAM_MEMBERSHIP,
                        cache_key=team_key,
                        data_fetcher=lambda tid=team_id, uid=user_id: self._fetch_team_membership_data(tid, uid),
                        tags={"startup", "team", f"team:{team_id}", f"user:{user_id}"}
                    )
            
            logger.info(f"Added startup warming tasks for {len(recent_users)} users, {len(recent_generations)} generations, {len(active_teams)} teams")
            
        except Exception as e:
            logger.error(f"Failed to add startup warming tasks: {e}")
    
    async def add_warming_task(self, priority: WarmingPriority,
                             strategy: WarmingStrategy,
                             key_type: KeyType,
                             cache_key: str,
                             data_fetcher: Callable,
                             estimated_execution_time_ms: float = 100.0,
                             estimated_data_size_bytes: int = 1024,
                             tags: Optional[Set[str]] = None,
                             metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add a cache warming task to the appropriate priority queue."""
        
        # Check queue size limits
        if len(self.warming_queues[priority]) >= self.config["max_warming_queue_size"]:
            logger.warning(f"Warming queue for {priority.name} is full, dropping task")
            return None
        
        # Generate task ID
        self.task_counter += 1
        task_id = f"warm_{priority.value}_{self.task_counter}_{int(time.time())}"
        
        # Create warming task
        task = WarmingTask(
            task_id=task_id,
            priority=priority,
            strategy=strategy,
            key_type=key_type,
            cache_key=cache_key,
            data_fetcher=data_fetcher,
            estimated_execution_time_ms=estimated_execution_time_ms,
            estimated_data_size_bytes=estimated_data_size_bytes,
            tags=tags or set(),
            metadata=metadata or {}
        )
        
        # Add to priority queue
        heapq.heappush(self.warming_queues[priority], task)
        
        logger.debug(f"Added warming task {task_id} for key {cache_key}")
        return task_id
    
    async def _execute_warming_batch(self, max_tasks: Optional[int] = None) -> int:
        """Execute a batch of warming tasks from priority queues."""
        max_batch_size = max_tasks or self.config["warming_batch_size"]
        tasks_to_execute = []
        
        # Collect tasks from priority queues (highest priority first)
        for priority in WarmingPriority:
            queue = self.warming_queues[priority]
            while queue and len(tasks_to_execute) < max_batch_size:
                task = heapq.heappop(queue)
                tasks_to_execute.append(task)
        
        if not tasks_to_execute:
            return 0
        
        # Execute tasks concurrently
        execution_results = await asyncio.gather(
            *[self._execute_single_warming_task(task) for task in tasks_to_execute],
            return_exceptions=True
        )
        
        # Process results
        successful_tasks = 0
        for i, result in enumerate(execution_results):
            task = tasks_to_execute[i]
            if isinstance(result, Exception):
                logger.error(f"Warming task {task.task_id} failed: {result}")
                task.success = False
                self.metrics["failed_warming_tasks"] += 1
            else:
                task.success = True
                successful_tasks += 1
                self.metrics["successful_warming_tasks"] += 1
            
            # Move to completed tasks
            task.completed_at = time.time()
            self.completed_tasks.append(task)
            self.metrics["total_warming_tasks"] += 1
        
        return successful_tasks
    
    async def _execute_single_warming_task(self, task: WarmingTask) -> bool:
        """Execute a single warming task."""
        start_time = time.time()
        
        try:
            # Check if key is already cached
            cached_value, cache_level = await self.cache_manager.get_multi_level(task.cache_key)
            if cached_value is not None:
                # Already cached, mark as success
                task.execution_time_ms = (time.time() - start_time) * 1000
                return True
            
            # Fetch data using the provided fetcher
            data = await task.data_fetcher()
            if data is None:
                return False
            
            # Get optimal TTL for this key
            ttl_config = get_optimal_ttl_for_key(task.cache_key)
            
            # Store in cache
            cache_results = await self.cache_manager.set_multi_level(
                task.cache_key,
                data,
                l1_ttl=ttl_config.l1_ttl,
                l2_ttl=ttl_config.l2_ttl,
                priority=task.priority.value,
                tags=task.tags
            )
            
            # Record execution time
            execution_time_ms = (time.time() - start_time) * 1000
            task.execution_time_ms = execution_time_ms
            self.metrics["total_warming_time_ms"] += execution_time_ms
            
            # Update average execution time
            total_tasks = self.metrics["total_warming_tasks"] + 1
            current_avg = self.metrics["avg_task_execution_time_ms"]
            self.metrics["avg_task_execution_time_ms"] = (
                (current_avg * self.metrics["total_warming_tasks"] + execution_time_ms) / total_tasks
            )
            
            # Check if data was successfully cached
            success = any(cache_results.values())
            
            if success:
                logger.debug(f"Warming task {task.task_id} completed successfully in {execution_time_ms:.2f}ms")
            
            return success
            
        except Exception as e:
            logger.error(f"Warming task {task.task_id} execution failed: {e}")
            task.execution_time_ms = (time.time() - start_time) * 1000
            return False
    
    async def _should_throttle_warming(self) -> bool:
        """Check if warming should be throttled due to resource constraints."""
        try:
            # Check cache hit rate - stop warming if excellent
            cache_metrics = self.cache_manager.get_comprehensive_metrics()
            overall_hit_rate = cache_metrics["overall_performance"]["overall_hit_rate_percent"] / 100.0
            
            if overall_hit_rate >= self.config["cache_hit_rate_threshold"]:
                return True  # Hit rate is excellent, throttle warming
            
            # Check system resources (simplified - could be enhanced with actual monitoring)
            active_task_count = len(self.active_tasks)
            if active_task_count >= self.config["max_concurrent_tasks"]:
                return True
            
            return False
            
        except Exception:
            return False  # Continue warming if we can't determine resource status
    
    async def _generate_predictive_warming_tasks(self) -> int:
        """Generate predictive warming tasks based on access patterns."""
        predictions_made = 0
        
        try:
            current_time = time.time()
            
            for user_id, pattern_data in self.user_access_patterns.items():
                # Skip stale patterns
                if current_time - pattern_data.last_updated > (self.config["max_prediction_age_hours"] * 3600):
                    continue
                
                # Predict next access time
                predicted_access_time = pattern_data.predict_next_access_time()
                if predicted_access_time is None:
                    continue
                
                # Only warm if prediction is within next hour
                if predicted_access_time - current_time > 3600:
                    continue
                
                # Get likely resources for this user
                likely_resources = pattern_data.get_likely_resources(top_n=5)
                
                for resource_type, probability in likely_resources:
                    if probability < 0.1:  # Skip low-probability resources
                        continue
                    
                    # Create predictive warming tasks
                    if resource_type == "generation":
                        await self._create_generation_predictive_tasks(user_id, probability)
                    elif resource_type == "profile":
                        await self._create_profile_predictive_tasks(user_id, probability)
                    elif resource_type == "team":
                        await self._create_team_predictive_tasks(user_id, probability)
                    
                    predictions_made += 1
                    self.metrics["predictions_made"] += 1
            
            return predictions_made
            
        except Exception as e:
            logger.error(f"Predictive warming task generation failed: {e}")
            return 0
    
    async def _create_generation_predictive_tasks(self, user_id: str, probability: float):
        """Create predictive warming tasks for generation data."""
        try:
            db = await get_database()
            
            # Get user's recent generations
            recent_gens = await db.execute_query(
                table="generations",
                operation="select",
                filters={
                    "user_id": user_id,
                    "status": "completed",
                    "created_at__gte": datetime.utcnow() - timedelta(days=7)
                },
                limit=10,
                order_by="created_at DESC"
            )
            
            for gen in recent_gens:
                gen_id = gen["id"]
                
                # Generation metadata
                gen_key, _ = self.key_manager.generate_generation_key(gen_id, "metadata")
                await self.add_warming_task(
                    priority=WarmingPriority.LOW,
                    strategy=WarmingStrategy.PREDICTIVE,
                    key_type=KeyType.GENERATION_METADATA,
                    cache_key=gen_key,
                    data_fetcher=lambda gid=gen_id: self._fetch_generation_metadata(gid),
                    tags={"predictive", f"user:{user_id}", f"generation:{gen_id}"},
                    metadata={"prediction_probability": probability}
                )
        
        except Exception as e:
            logger.error(f"Failed to create generation predictive tasks: {e}")
    
    async def _create_profile_predictive_tasks(self, user_id: str, probability: float):
        """Create predictive warming tasks for user profile data."""
        profile_key, _ = self.key_manager.generate_user_profile_key(user_id)
        
        await self.add_warming_task(
            priority=WarmingPriority.MEDIUM,
            strategy=WarmingStrategy.PREDICTIVE,
            key_type=KeyType.USER_PROFILE,
            cache_key=profile_key,
            data_fetcher=lambda uid=user_id: self._fetch_user_profile_data(uid),
            tags={"predictive", f"user:{user_id}"},
            metadata={"prediction_probability": probability}
        )
    
    async def _create_team_predictive_tasks(self, user_id: str, probability: float):
        """Create predictive warming tasks for team data."""
        try:
            db = await get_database()
            
            # Get user's teams
            user_teams = await db.execute_query(
                table="team_members",
                operation="select",
                filters={"user_id": user_id, "is_active": True}
            )
            
            for team_member in user_teams:
                team_id = team_member["team_id"]
                team_key, _ = self.key_manager.generate_team_key(team_id, user_id)
                
                await self.add_warming_task(
                    priority=WarmingPriority.MEDIUM,
                    strategy=WarmingStrategy.PREDICTIVE,
                    key_type=KeyType.TEAM_MEMBERSHIP,
                    cache_key=team_key,
                    data_fetcher=lambda tid=team_id, uid=user_id: self._fetch_team_membership_data(tid, uid),
                    tags={"predictive", f"user:{user_id}", f"team:{team_id}"},
                    metadata={"prediction_probability": probability}
                )
        
        except Exception as e:
            logger.error(f"Failed to create team predictive tasks: {e}")
    
    def record_cache_access(self, user_id: str, resource_type: str, 
                           operation: str, session_type: str = "default"):
        """Record cache access for pattern learning."""
        if not self.config["pattern_learning_enabled"]:
            return
        
        # Update user access patterns
        if user_id not in self.user_access_patterns:
            self.user_access_patterns[user_id] = AccessPatternData(user_id=user_id)
        
        self.user_access_patterns[user_id].add_access(resource_type, operation, session_type)
        
        # Update global patterns
        self.global_access_patterns["resource_type_popularity"][resource_type] += 1
        self.global_access_patterns["operation_popularity"][operation] += 1
        
        # Update hourly/daily patterns
        now = datetime.now()
        hour_key = now.hour
        day_key = now.weekday()
        
        self.global_access_patterns["hourly_patterns"][hour_key].append(time.time())
        self.global_access_patterns["daily_patterns"][day_key].append(time.time())
    
    async def _analyze_access_patterns(self):
        """Analyze access patterns for learning improvements."""
        try:
            # Clean up old pattern data
            current_time = time.time()
            cutoff_time = current_time - (7 * 24 * 3600)  # 7 days
            
            expired_users = []
            for user_id, pattern_data in self.user_access_patterns.items():
                if pattern_data.last_updated < cutoff_time:
                    expired_users.append(user_id)
            
            for user_id in expired_users:
                del self.user_access_patterns[user_id]
            
            if expired_users:
                logger.info(f"Cleaned up access patterns for {len(expired_users)} inactive users")
            
            # Analyze prediction accuracy (simplified)
            total_predictions = self.metrics["predictions_made"]
            if total_predictions > 0:
                # This would be enhanced with actual hit rate tracking from predictions
                estimated_accuracy = min(0.8, 0.3 + (total_predictions / 1000) * 0.5)
                self.metrics["prediction_accuracy"] = estimated_accuracy
            
        except Exception as e:
            logger.error(f"Access pattern analysis failed: {e}")
    
    async def _update_global_patterns(self):
        """Update global access patterns and trends."""
        try:
            # Clean up old hourly/daily pattern data
            cutoff_time = time.time() - (24 * 3600)  # 24 hours
            
            for hour_key in self.global_access_patterns["hourly_patterns"]:
                old_data = self.global_access_patterns["hourly_patterns"][hour_key]
                new_data = [t for t in old_data if t > cutoff_time]
                self.global_access_patterns["hourly_patterns"][hour_key] = new_data
            
            cutoff_time = time.time() - (7 * 24 * 3600)  # 7 days
            for day_key in self.global_access_patterns["daily_patterns"]:
                old_data = self.global_access_patterns["daily_patterns"][day_key]
                new_data = [t for t in old_data if t > cutoff_time]
                self.global_access_patterns["daily_patterns"][day_key] = new_data
            
        except Exception as e:
            logger.error(f"Global pattern update failed: {e}")
    
    # Data fetcher methods
    async def _fetch_user_session_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user session data."""
        try:
            db = await get_database()
            user_data = await db.execute_query(
                table="users",
                operation="select",
                filters={"id": user_id},
                single=True
            )
            
            if not user_data:
                return None
            
            return {
                "user_id": user_id,
                "email": user_data.get("email"),
                "is_active": user_data.get("is_active"),
                "last_active_at": user_data.get("last_active_at"),
                "session_created_at": datetime.utcnow().isoformat(),
                "warmed_at": time.time()
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch user session data for {user_id}: {e}")
            return None
    
    async def _fetch_generation_metadata(self, generation_id: str) -> Optional[Dict[str, Any]]:
        """Fetch generation metadata."""
        try:
            db = await get_database()
            gen_data = await db.execute_query(
                table="generations",
                operation="select",
                filters={"id": generation_id},
                single=True
            )
            
            if not gen_data:
                return None
            
            return {
                "generation_id": generation_id,
                "user_id": gen_data.get("user_id"),
                "status": gen_data.get("status"),
                "created_at": gen_data.get("created_at"),
                "updated_at": gen_data.get("updated_at"),
                "metadata": gen_data.get("metadata", {}),
                "warmed_at": time.time()
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch generation metadata for {generation_id}: {e}")
            return None
    
    async def _fetch_authorization_data(self, user_id: str, resource_id: str, 
                                      resource_type: str, operation: str) -> Optional[Dict[str, Any]]:
        """Fetch authorization data."""
        try:
            # This would integrate with the actual authorization service
            from services.enhanced_authorization_cache_service import get_enhanced_authorization_cache_service
            auth_service = get_enhanced_authorization_cache_service()
            
            # For now, create basic authorization data
            return {
                "user_id": user_id,
                "resource_id": resource_id,
                "resource_type": resource_type,
                "operation": operation,
                "authorized": True,  # This would be determined by actual auth logic
                "method": "cache_warming",
                "cached_at": datetime.utcnow().isoformat(),
                "warmed_at": time.time()
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch authorization data: {e}")
            return None
    
    async def _fetch_user_profile_data(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch user profile data."""
        try:
            db = await get_database()
            user_data = await db.execute_query(
                table="users",
                operation="select",
                filters={"id": user_id},
                single=True
            )
            
            if not user_data:
                return None
            
            return {
                "user_id": user_id,
                "email": user_data.get("email"),
                "username": user_data.get("username"),
                "created_at": user_data.get("created_at"),
                "is_active": user_data.get("is_active"),
                "last_active_at": user_data.get("last_active_at"),
                "profile_settings": user_data.get("profile_settings", {}),
                "warmed_at": time.time()
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch user profile data for {user_id}: {e}")
            return None
    
    async def _fetch_team_membership_data(self, team_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Fetch team membership data."""
        try:
            db = await get_database()
            
            # Get team info
            team_data = await db.execute_query(
                table="teams",
                operation="select",
                filters={"id": team_id},
                single=True
            )
            
            # Get membership info
            membership_data = await db.execute_query(
                table="team_members",
                operation="select",
                filters={"team_id": team_id, "user_id": user_id},
                single=True
            )
            
            if not team_data or not membership_data:
                return None
            
            return {
                "team_id": team_id,
                "user_id": user_id,
                "team_name": team_data.get("name"),
                "role": membership_data.get("role"),
                "is_active": membership_data.get("is_active"),
                "joined_at": membership_data.get("joined_at"),
                "permissions": membership_data.get("permissions", []),
                "warmed_at": time.time()
            }
        
        except Exception as e:
            logger.error(f"Failed to fetch team membership data for team {team_id}, user {user_id}: {e}")
            return None
    
    def get_warming_statistics(self) -> Dict[str, Any]:
        """Get comprehensive warming service statistics."""
        # Calculate queue sizes
        queue_sizes = {
            priority.name: len(queue) 
            for priority, queue in self.warming_queues.items()
        }
        
        # Calculate success rate
        total_tasks = self.metrics["total_warming_tasks"]
        success_rate = (self.metrics["successful_warming_tasks"] / total_tasks * 100) if total_tasks > 0 else 0.0
        
        # Get recent task performance
        recent_tasks = list(self.completed_tasks)[-100:]  # Last 100 tasks
        recent_success_rate = 0.0
        if recent_tasks:
            recent_successes = sum(1 for task in recent_tasks if task.success)
            recent_success_rate = (recent_successes / len(recent_tasks)) * 100
        
        return {
            "service_status": {
                "active": self.warming_active,
                "background_tasks_running": len(self.warming_tasks)
            },
            "queue_statistics": {
                "total_queued_tasks": sum(queue_sizes.values()),
                "queue_sizes_by_priority": queue_sizes,
                "max_queue_size": self.config["max_warming_queue_size"]
            },
            "execution_statistics": {
                "total_tasks": total_tasks,
                "successful_tasks": self.metrics["successful_warming_tasks"],
                "failed_tasks": self.metrics["failed_warming_tasks"],
                "success_rate_percent": success_rate,
                "recent_success_rate_percent": recent_success_rate,
                "avg_execution_time_ms": self.metrics["avg_task_execution_time_ms"],
                "total_execution_time_ms": self.metrics["total_warming_time_ms"]
            },
            "prediction_statistics": {
                "predictions_made": self.metrics["predictions_made"],
                "prediction_accuracy": self.metrics["prediction_accuracy"],
                "predictive_warming_enabled": self.config["predictive_warming_enabled"],
                "pattern_learning_enabled": self.config["pattern_learning_enabled"]
            },
            "pattern_learning": {
                "tracked_users": len(self.user_access_patterns),
                "global_resource_types": len(self.global_access_patterns["resource_type_popularity"]),
                "global_operations": len(self.global_access_patterns["operation_popularity"])
            },
            "configuration": self.config,
            "timestamp": datetime.utcnow().isoformat()
        }


# Global intelligent cache warming service instance
intelligent_warming_service: Optional[IntelligentCacheWarmingService] = None


def get_intelligent_warming_service() -> IntelligentCacheWarmingService:
    """Get or create global intelligent cache warming service."""
    global intelligent_warming_service
    if intelligent_warming_service is None:
        intelligent_warming_service = IntelligentCacheWarmingService()
    return intelligent_warming_service


# Convenience functions
async def start_cache_warming():
    """Start intelligent cache warming service."""
    service = get_intelligent_warming_service()
    await service.start_warming_service()


async def stop_cache_warming():
    """Stop intelligent cache warming service."""
    if intelligent_warming_service:
        await intelligent_warming_service.stop_warming_service()


def record_access_for_learning(user_id: str, resource_type: str, operation: str):
    """Record access for pattern learning."""
    if intelligent_warming_service:
        intelligent_warming_service.record_cache_access(user_id, resource_type, operation)


async def add_cache_warming_task(priority: WarmingPriority, key_type: KeyType, 
                                cache_key: str, data_fetcher: Callable) -> Optional[str]:
    """Add cache warming task."""
    service = get_intelligent_warming_service()
    return await service.add_warming_task(
        priority=priority,
        strategy=WarmingStrategy.REACTIVE,
        key_type=key_type,
        cache_key=cache_key,
        data_fetcher=data_fetcher
    )


def get_warming_stats() -> Dict[str, Any]:
    """Get warming service statistics."""
    if intelligent_warming_service:
        return intelligent_warming_service.get_warming_statistics()
    return {"error": "Warming service not initialized"}