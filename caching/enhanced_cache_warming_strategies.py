"""
Enhanced Cache Warming Strategies
Optimized warming strategies for authorization, user data, and generations to achieve >95% hit rates.

Features:
- Authorization-specific warming patterns  
- User behavior-based predictive warming
- Generation access pattern optimization
- Team collaboration cache warming
- Real-time warming trigger integration
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
from enum import Enum
from uuid import UUID

from caching.optimized_cache_manager import (
    OptimizedCacheManager, get_optimized_cache_manager, UserAccessContext
)
from caching.intelligent_cache_warming_service import (
    WarmingPriority, WarmingStrategy, get_intelligent_warming_service
)
from caching.cache_key_manager import KeyType, AccessPattern
from database import get_database

logger = logging.getLogger(__name__)


class WarmingTrigger(Enum):
    """Cache warming trigger types."""
    USER_LOGIN = "user_login"
    GENERATION_CREATED = "generation_created"
    TEAM_ACCESS = "team_access"
    API_REQUEST_PATTERN = "api_request_pattern"
    SCHEDULED = "scheduled"
    SYSTEM_STARTUP = "system_startup"


class DataAccessPattern(Enum):
    """Data access pattern types for warming optimization."""
    SEQUENTIAL = "sequential"      # User accesses related data in sequence
    BURST = "burst"               # Multiple quick accesses
    PERIODIC = "periodic"         # Regular time-based access
    COLLABORATIVE = "collaborative"  # Team-based access patterns


@dataclass
class WarmingStrategy:
    """Enhanced cache warming strategy configuration."""
    name: str
    trigger: WarmingTrigger
    data_pattern: DataAccessPattern
    priority: WarmingPriority
    warmup_depth: int = 3         # How many related items to warm
    prediction_window_minutes: int = 15  # How far ahead to predict
    success_rate_threshold: float = 0.8   # Minimum success rate to continue
    enabled: bool = True


@dataclass
class UserWarmingContext:
    """User-specific warming context with behavior analysis."""
    user_id: str
    login_patterns: List[float] = field(default_factory=list)  # Login times
    resource_access_sequence: deque = field(default_factory=lambda: deque(maxlen=100))
    team_collaborations: Set[str] = field(default_factory=set)
    generation_patterns: Dict[str, int] = field(default_factory=dict)
    last_warming: float = 0.0
    warming_effectiveness: float = 0.0  # 0-1 score


class EnhancedCacheWarmingStrategies:
    """
    Enhanced cache warming strategies with behavior analysis and predictive warming.
    """
    
    def __init__(self, optimized_cache_manager: Optional[OptimizedCacheManager] = None):
        self.cache_manager = optimized_cache_manager or get_optimized_cache_manager()
        self.warming_service = get_intelligent_warming_service()
        
        # User warming contexts
        self.user_warming_contexts: Dict[str, UserWarmingContext] = {}
        
        # Warming strategies
        self.warming_strategies = {
            "user_login_warming": WarmingStrategy(
                name="user_login_warming",
                trigger=WarmingTrigger.USER_LOGIN,
                data_pattern=DataAccessPattern.SEQUENTIAL,
                priority=WarmingPriority.HIGH,
                warmup_depth=5,
                prediction_window_minutes=30
            ),
            "generation_creation_warming": WarmingStrategy(
                name="generation_creation_warming", 
                trigger=WarmingTrigger.GENERATION_CREATED,
                data_pattern=DataAccessPattern.BURST,
                priority=WarmingPriority.HIGH,
                warmup_depth=3,
                prediction_window_minutes=5
            ),
            "team_collaboration_warming": WarmingStrategy(
                name="team_collaboration_warming",
                trigger=WarmingTrigger.TEAM_ACCESS,
                data_pattern=DataAccessPattern.COLLABORATIVE,
                priority=WarmingPriority.MEDIUM,
                warmup_depth=4,
                prediction_window_minutes=20
            ),
            "api_pattern_warming": WarmingStrategy(
                name="api_pattern_warming",
                trigger=WarmingTrigger.API_REQUEST_PATTERN,
                data_pattern=DataAccessPattern.PERIODIC,
                priority=WarmingPriority.LOW,
                warmup_depth=2,
                prediction_window_minutes=10
            )
        }
        
        # Warming effectiveness tracking
        self.warming_metrics = {
            "total_warming_operations": 0,
            "successful_warming_predictions": 0,
            "warming_hit_rate": 0.0,
            "strategy_effectiveness": defaultdict(float)
        }
        
        # Background warming active
        self.warming_active = False
        self.warming_tasks: List[asyncio.Task] = []
    
    async def start_enhanced_warming(self):
        """Start enhanced cache warming strategies."""
        if self.warming_active:
            logger.warning("Enhanced warming already active")
            return
        
        self.warming_active = True
        logger.info("Starting enhanced cache warming strategies")
        
        # Start background warming loops
        loop = asyncio.get_event_loop()
        
        self.warming_tasks.extend([
            loop.create_task(self._user_behavior_analysis_loop()),
            loop.create_task(self._predictive_warming_loop()),
            loop.create_task(self._warming_effectiveness_tracking_loop())
        ])
        
        logger.info("Enhanced cache warming strategies started")
    
    async def stop_enhanced_warming(self):
        """Stop enhanced cache warming strategies."""
        self.warming_active = False
        
        for task in self.warming_tasks:
            task.cancel()
        
        if self.warming_tasks:
            await asyncio.gather(*self.warming_tasks, return_exceptions=True)
        
        logger.info("Enhanced cache warming strategies stopped")
    
    async def trigger_user_login_warming(self, user_id: str) -> Dict[str, Any]:
        """
        Trigger comprehensive warming when user logs in.
        Warms user profile, recent generations, team data, and authorization context.
        """
        logger.info(f"Triggering login warming for user {user_id}")
        start_time = time.time()
        
        warming_results = {
            "user_profile": 0,
            "user_sessions": 0, 
            "recent_generations": 0,
            "team_memberships": 0,
            "authorization_context": 0,
            "predictive_resources": 0,
            "total_items_warmed": 0
        }
        
        try:
            # Get or create user warming context
            if user_id not in self.user_warming_contexts:
                self.user_warming_contexts[user_id] = UserWarmingContext(user_id=user_id)
            
            context = self.user_warming_contexts[user_id]
            context.login_patterns.append(time.time())
            
            # Create user access context
            user_context = UserAccessContext(
                user_id=user_id,
                session_type="login",
                access_frequency=50.0,  # High frequency for login warming
                last_access=time.time()
            )
            
            # 1. Warm user profile and session data
            profile_count = await self._warm_user_profile_data(user_id, user_context)
            warming_results["user_profile"] = profile_count
            
            session_count = await self._warm_user_session_data(user_id, user_context)
            warming_results["user_sessions"] = session_count
            
            # 2. Warm recent generations
            gen_count = await self._warm_user_recent_generations(user_id, user_context)
            warming_results["recent_generations"] = gen_count
            
            # 3. Warm team memberships and collaboration data
            team_count = await self._warm_user_team_data(user_id, user_context)
            warming_results["team_memberships"] = team_count
            
            # 4. Warm authorization context
            auth_count = await self._warm_user_authorization_context(user_id, user_context)
            warming_results["authorization_context"] = auth_count
            
            # 5. Predictive warming based on user patterns
            pred_count = await self._warm_predicted_user_resources(user_id, context, user_context)
            warming_results["predictive_resources"] = pred_count
            
            # Calculate totals
            warming_results["total_items_warmed"] = sum(
                count for key, count in warming_results.items() 
                if key != "total_items_warmed"
            )
            
            # Update context
            context.last_warming = time.time()
            
            execution_time = (time.time() - start_time) * 1000
            logger.info(f"Login warming completed for user {user_id}: "
                       f"{warming_results['total_items_warmed']} items in {execution_time:.1f}ms")
            
            # Track warming effectiveness
            self.warming_metrics["total_warming_operations"] += 1
            
            return warming_results
            
        except Exception as e:
            logger.error(f"Login warming failed for user {user_id}: {e}")
            return warming_results
    
    async def trigger_generation_creation_warming(self, generation_id: str, user_id: str) -> Dict[str, Any]:
        """
        Trigger warming when generation is created.
        Warms generation metadata, related resources, and authorization data.
        """
        logger.info(f"Triggering generation creation warming for gen {generation_id}")
        
        warming_results = {
            "generation_metadata": 0,
            "authorization_data": 0,
            "related_generations": 0,
            "user_context": 0,
            "total_items_warmed": 0
        }
        
        try:
            user_context = UserAccessContext(
                user_id=user_id,
                session_type="generation_creation",
                access_frequency=100.0  # Very high for new generation
            )
            
            # 1. Warm generation metadata
            gen_key = f"gen:{generation_id}:metadata"
            gen_data = await self._fetch_generation_metadata(generation_id)
            
            if gen_data:
                await self.cache_manager.set_cached_with_optimization(
                    gen_key, gen_data, user_context, priority=3
                )
                warming_results["generation_metadata"] = 1
            
            # 2. Warm authorization for generation access
            auth_key = f"auth:user:{user_id}:gen:{generation_id}:read"
            auth_data = {
                "user_id": user_id,
                "generation_id": generation_id,
                "authorized": True,
                "method": "direct_ownership",
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.cache_manager.set_cached_with_optimization(
                auth_key, auth_data, user_context, priority=3
            )
            warming_results["authorization_data"] = 1
            
            # 3. Warm related generations (user's recent generations)
            related_count = await self._warm_related_generations(user_id, generation_id, user_context)
            warming_results["related_generations"] = related_count
            
            # 4. Update user context
            if user_id in self.user_warming_contexts:
                context = self.user_warming_contexts[user_id]
                context.generation_patterns[generation_id] = int(time.time())
                context.resource_access_sequence.append(f"gen:{generation_id}")
                warming_results["user_context"] = 1
            
            warming_results["total_items_warmed"] = sum(
                count for key, count in warming_results.items()
                if key != "total_items_warmed"
            )
            
            logger.info(f"Generation creation warming completed: {warming_results['total_items_warmed']} items")
            return warming_results
            
        except Exception as e:
            logger.error(f"Generation creation warming failed: {e}")
            return warming_results
    
    async def trigger_team_collaboration_warming(self, team_id: str, user_id: str) -> Dict[str, Any]:
        """
        Trigger warming for team collaboration patterns.
        Warms team member data, shared resources, and collaboration context.
        """
        logger.info(f"Triggering team collaboration warming for team {team_id}, user {user_id}")
        
        warming_results = {
            "team_members": 0,
            "shared_resources": 0,
            "collaboration_context": 0,
            "member_authorization": 0,
            "total_items_warmed": 0
        }
        
        try:
            user_context = UserAccessContext(
                user_id=user_id,
                session_type="team_collaboration",
                access_frequency=30.0
            )
            
            # 1. Warm team member data
            members_count = await self._warm_team_member_data(team_id, user_context)
            warming_results["team_members"] = members_count
            
            # 2. Warm shared team resources
            resources_count = await self._warm_team_shared_resources(team_id, user_context)
            warming_results["shared_resources"] = resources_count
            
            # 3. Warm collaboration context
            collab_key = f"team:{team_id}:collaboration:context"
            collab_data = await self._fetch_team_collaboration_context(team_id)
            
            if collab_data:
                await self.cache_manager.set_cached_with_optimization(
                    collab_key, collab_data, user_context, priority=2
                )
                warming_results["collaboration_context"] = 1
            
            # 4. Warm member authorization data
            auth_count = await self._warm_team_member_authorization(team_id, user_id, user_context)
            warming_results["member_authorization"] = auth_count
            
            # 5. Update user warming context
            if user_id in self.user_warming_contexts:
                self.user_warming_contexts[user_id].team_collaborations.add(team_id)
            
            warming_results["total_items_warmed"] = sum(
                count for key, count in warming_results.items()
                if key != "total_items_warmed"
            )
            
            logger.info(f"Team collaboration warming completed: {warming_results['total_items_warmed']} items")
            return warming_results
            
        except Exception as e:
            logger.error(f"Team collaboration warming failed: {e}")
            return warming_results
    
    # Individual warming method implementations
    
    async def _warm_user_profile_data(self, user_id: str, user_context: UserAccessContext) -> int:
        """Warm user profile and settings data."""
        try:
            db = await get_database()
            
            user_data = await db.execute_query(
                table="users",
                operation="select",
                filters={"id": user_id},
                single=True
            )
            
            if not user_data:
                return 0
            
            # Warm user profile
            profile_key = f"user:{user_id}:profile"
            profile_data = {
                "user_id": user_id,
                "email": user_data.get("email"),
                "username": user_data.get("username"),
                "is_active": user_data.get("is_active"),
                "created_at": user_data.get("created_at"),
                "last_active_at": user_data.get("last_active_at"),
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.cache_manager.set_cached_with_optimization(
                profile_key, profile_data, user_context, priority=2
            )
            
            return 1
            
        except Exception as e:
            logger.error(f"Failed to warm user profile data for {user_id}: {e}")
            return 0
    
    async def _warm_user_session_data(self, user_id: str, user_context: UserAccessContext) -> int:
        """Warm user session data."""
        try:
            session_key = f"session:user:{user_id}:active"
            session_data = {
                "user_id": user_id,
                "session_start": time.time(),
                "session_type": user_context.session_type,
                "access_frequency": user_context.access_frequency,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.cache_manager.set_cached_with_optimization(
                session_key, session_data, user_context, priority=3
            )
            
            return 1
            
        except Exception as e:
            logger.error(f"Failed to warm user session data for {user_id}: {e}")
            return 0
    
    async def _warm_user_recent_generations(self, user_id: str, user_context: UserAccessContext) -> int:
        """Warm user's recent generation data."""
        try:
            db = await get_database()
            
            recent_generations = await db.execute_query(
                table="generations",
                operation="select",
                filters={
                    "user_id": user_id,
                    "created_at__gte": datetime.utcnow() - timedelta(days=7)
                },
                limit=20,
                order_by="created_at DESC"
            )
            
            warmed_count = 0
            for gen in recent_generations:
                gen_id = gen["id"]
                gen_key = f"gen:{gen_id}:metadata"
                gen_data = {
                    "generation_id": gen_id,
                    "user_id": user_id,
                    "status": gen["status"],
                    "created_at": gen["created_at"],
                    "updated_at": gen.get("updated_at"),
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                await self.cache_manager.set_cached_with_optimization(
                    gen_key, gen_data, user_context, priority=2
                )
                warmed_count += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Failed to warm recent generations for {user_id}: {e}")
            return 0
    
    async def _warm_user_team_data(self, user_id: str, user_context: UserAccessContext) -> int:
        """Warm user's team membership data."""
        try:
            db = await get_database()
            
            team_memberships = await db.execute_query(
                table="team_members",
                operation="select",
                filters={"user_id": user_id, "is_active": True}
            )
            
            warmed_count = 0
            for membership in team_memberships:
                team_id = membership["team_id"]
                team_key = f"team:{team_id}:member:{user_id}"
                team_data = {
                    "user_id": user_id,
                    "team_id": team_id,
                    "role": membership["role"],
                    "joined_at": membership.get("joined_at"),
                    "is_active": membership["is_active"],
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                await self.cache_manager.set_cached_with_optimization(
                    team_key, team_data, user_context, priority=2
                )
                warmed_count += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Failed to warm team data for {user_id}: {e}")
            return 0
    
    async def _warm_user_authorization_context(self, user_id: str, user_context: UserAccessContext) -> int:
        """Warm user's authorization context."""
        try:
            # Warm general authorization context
            auth_key = f"auth:user:{user_id}:context"
            auth_data = {
                "user_id": user_id,
                "roles": ["member"],  # Would be fetched from role system
                "permissions": ["read", "write"],  # Would be fetched from permission system
                "is_active": True,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.cache_manager.set_cached_with_optimization(
                auth_key, auth_data, user_context, priority=3
            )
            
            return 1
            
        except Exception as e:
            logger.error(f"Failed to warm authorization context for {user_id}: {e}")
            return 0
    
    async def _warm_predicted_user_resources(self, user_id: str, context: UserWarmingContext,
                                           user_context: UserAccessContext) -> int:
        """Warm resources predicted based on user behavior patterns."""
        try:
            warmed_count = 0
            
            # Analyze recent access sequence for patterns
            recent_resources = list(context.resource_access_sequence)[-10:]  # Last 10 accesses
            
            for resource in recent_resources:
                # Predict related resources
                related_resources = self._predict_related_resources(resource, user_id)
                
                for related_resource in related_resources[:3]:  # Limit to 3 predictions per resource
                    # Check if already cached
                    cached_value, _ = await self.cache_manager.get_cached_with_optimization(
                        related_resource, user_context=user_context
                    )
                    
                    if cached_value[0] is None:  # Not cached
                        # Fetch and cache predictively
                        resource_data = await self._fetch_resource_for_warming(related_resource)
                        if resource_data:
                            await self.cache_manager.set_cached_with_optimization(
                                related_resource, resource_data, user_context, priority=1
                            )
                            warmed_count += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Failed to warm predicted resources for {user_id}: {e}")
            return 0
    
    async def _warm_related_generations(self, user_id: str, generation_id: str, 
                                      user_context: UserAccessContext) -> int:
        """Warm generations related to the newly created one."""
        try:
            db = await get_database()
            
            # Get user's other recent generations
            related_generations = await db.execute_query(
                table="generations",
                operation="select",
                filters={
                    "user_id": user_id,
                    "id__ne": generation_id,
                    "created_at__gte": datetime.utcnow() - timedelta(days=3)
                },
                limit=5,
                order_by="created_at DESC"
            )
            
            warmed_count = 0
            for gen in related_generations:
                gen_id = gen["id"]
                
                # Warm authorization for related generation
                auth_key = f"auth:user:{user_id}:gen:{gen_id}:read"
                auth_data = {
                    "user_id": user_id,
                    "generation_id": gen_id,
                    "authorized": True,
                    "method": "direct_ownership",
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                await self.cache_manager.set_cached_with_optimization(
                    auth_key, auth_data, user_context, priority=2
                )
                warmed_count += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Failed to warm related generations: {e}")
            return 0
    
    async def _warm_team_member_data(self, team_id: str, user_context: UserAccessContext) -> int:
        """Warm team member data."""
        try:
            db = await get_database()
            
            team_members = await db.execute_query(
                table="team_members",
                operation="select", 
                filters={"team_id": team_id, "is_active": True},
                limit=20
            )
            
            warmed_count = 0
            for member in team_members:
                member_user_id = member["user_id"]
                member_key = f"team:{team_id}:member:{member_user_id}"
                member_data = {
                    "user_id": member_user_id,
                    "team_id": team_id,
                    "role": member["role"],
                    "is_active": member["is_active"],
                    "cached_at": datetime.utcnow().isoformat()
                }
                
                await self.cache_manager.set_cached_with_optimization(
                    member_key, member_data, user_context, priority=2
                )
                warmed_count += 1
            
            return warmed_count
            
        except Exception as e:
            logger.error(f"Failed to warm team member data for {team_id}: {e}")
            return 0
    
    async def _warm_team_shared_resources(self, team_id: str, user_context: UserAccessContext) -> int:
        """Warm team shared resources."""
        try:
            # This would integrate with actual team resource system
            # For now, create placeholder team resource data
            resources_key = f"team:{team_id}:shared_resources"
            resources_data = {
                "team_id": team_id,
                "shared_generations": [],
                "shared_projects": [],
                "resource_count": 0,
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.cache_manager.set_cached_with_optimization(
                resources_key, resources_data, user_context, priority=1
            )
            
            return 1
            
        except Exception as e:
            logger.error(f"Failed to warm team shared resources for {team_id}: {e}")
            return 0
    
    async def _warm_team_member_authorization(self, team_id: str, user_id: str,
                                            user_context: UserAccessContext) -> int:
        """Warm team member authorization data."""
        try:
            auth_key = f"auth:team:{team_id}:member:{user_id}"
            auth_data = {
                "user_id": user_id,
                "team_id": team_id,
                "authorized": True,
                "role": "member",  # Would be fetched from actual role
                "permissions": ["read", "write"],
                "cached_at": datetime.utcnow().isoformat()
            }
            
            await self.cache_manager.set_cached_with_optimization(
                auth_key, auth_data, user_context, priority=2
            )
            
            return 1
            
        except Exception as e:
            logger.error(f"Failed to warm team member authorization: {e}")
            return 0
    
    # Background optimization loops
    
    async def _user_behavior_analysis_loop(self):
        """Background loop for analyzing user behavior patterns."""
        while self.warming_active:
            try:
                current_time = time.time()
                
                # Analyze user patterns and update contexts
                for user_id, context in self.user_warming_contexts.items():
                    # Analyze login patterns
                    if len(context.login_patterns) >= 5:
                        self._analyze_user_login_patterns(context)
                    
                    # Update warming effectiveness
                    if current_time - context.last_warming > 3600:  # 1 hour
                        context.warming_effectiveness *= 0.9  # Decay over time
                
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"User behavior analysis loop error: {e}")
                await asyncio.sleep(60)
    
    async def _predictive_warming_loop(self):
        """Background loop for predictive warming."""
        while self.warming_active:
            try:
                # Predict and warm resources for active users
                current_time = time.time()
                
                for user_id, context in self.user_warming_contexts.items():
                    if current_time - context.last_warming < 1800:  # Recently warmed (30 min)
                        continue
                    
                    # Predict user's next access
                    if self._should_predict_user_access(context):
                        await self._execute_predictive_warming_for_user(user_id, context)
                
                await asyncio.sleep(600)  # 10 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Predictive warming loop error: {e}")
                await asyncio.sleep(120)
    
    async def _warming_effectiveness_tracking_loop(self):
        """Background loop for tracking warming effectiveness."""
        while self.warming_active:
            try:
                # Calculate warming effectiveness metrics
                total_operations = self.warming_metrics["total_warming_operations"]
                successful_predictions = self.warming_metrics["successful_warming_predictions"]
                
                if total_operations > 0:
                    self.warming_metrics["warming_hit_rate"] = successful_predictions / total_operations
                
                # Log effectiveness metrics
                if total_operations > 0 and total_operations % 10 == 0:
                    logger.info(f"Warming effectiveness: {self.warming_metrics['warming_hit_rate']:.2%} "
                               f"({successful_predictions}/{total_operations} successful)")
                
                await asyncio.sleep(900)  # 15 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Warming effectiveness tracking loop error: {e}")
                await asyncio.sleep(180)
    
    # Helper methods
    
    def _analyze_user_login_patterns(self, context: UserWarmingContext):
        """Analyze user login patterns for prediction."""
        if len(context.login_patterns) < 3:
            return
        
        recent_logins = context.login_patterns[-10:]  # Last 10 logins
        
        # Calculate average time between logins
        intervals = []
        for i in range(1, len(recent_logins)):
            intervals.append(recent_logins[i] - recent_logins[i-1])
        
        if intervals:
            avg_interval = sum(intervals) / len(intervals)
            # Predict next login time
            predicted_next_login = recent_logins[-1] + avg_interval
            # Store prediction logic here
    
    def _should_predict_user_access(self, context: UserWarmingContext) -> bool:
        """Determine if we should predict user access for warming."""
        current_time = time.time()
        
        # Predict if user has regular patterns and hasn't been warmed recently
        return (len(context.resource_access_sequence) >= 5 and
                current_time - context.last_warming > 1800 and  # 30 minutes
                context.warming_effectiveness > 0.3)  # Reasonable effectiveness
    
    async def _execute_predictive_warming_for_user(self, user_id: str, context: UserWarmingContext):
        """Execute predictive warming for a specific user."""
        try:
            user_context = UserAccessContext(
                user_id=user_id,
                session_type="predictive",
                access_frequency=10.0
            )
            
            # Predict and warm most likely resources
            predicted_resources = self._predict_user_next_resources(context)
            
            warmed_count = 0
            for resource_key in predicted_resources[:5]:  # Limit to 5 predictions
                resource_data = await self._fetch_resource_for_warming(resource_key)
                if resource_data:
                    await self.cache_manager.set_cached_with_optimization(
                        resource_key, resource_data, user_context, priority=1
                    )
                    warmed_count += 1
            
            if warmed_count > 0:
                logger.debug(f"Predictive warming: warmed {warmed_count} resources for user {user_id}")
            
        except Exception as e:
            logger.error(f"Predictive warming failed for user {user_id}: {e}")
    
    def _predict_user_next_resources(self, context: UserWarmingContext) -> List[str]:
        """Predict next resources user will access."""
        predictions = []
        
        # Analyze recent access sequence
        recent_resources = list(context.resource_access_sequence)[-5:]
        
        for resource in recent_resources:
            related = self._predict_related_resources(resource, context.user_id)
            predictions.extend(related[:2])  # Top 2 predictions per resource
        
        return list(set(predictions))  # Remove duplicates
    
    def _predict_related_resources(self, resource_key: str, user_id: str) -> List[str]:
        """Predict related resources based on resource key."""
        predictions = []
        
        if "gen:" in resource_key:
            gen_id = resource_key.split(":")[1]
            predictions.extend([
                f"auth:user:{user_id}:gen:{gen_id}:read",
                f"gen:{gen_id}:image_url",
                f"gen:{gen_id}:settings"
            ])
        elif "user:" in resource_key:
            predictions.extend([
                f"session:user:{user_id}:active",
                f"auth:user:{user_id}:context"
            ])
        elif "team:" in resource_key:
            team_id = resource_key.split(":")[1]
            predictions.extend([
                f"team:{team_id}:shared_resources",
                f"auth:team:{team_id}:member:{user_id}"
            ])
        
        return predictions
    
    # Data fetching methods
    
    async def _fetch_generation_metadata(self, generation_id: str) -> Optional[Dict[str, Any]]:
        """Fetch generation metadata for warming."""
        try:
            db = await get_database()
            gen_data = await db.execute_query(
                table="generations",
                operation="select",
                filters={"id": generation_id},
                single=True
            )
            
            if gen_data:
                return {
                    "generation_id": generation_id,
                    "user_id": gen_data.get("user_id"),
                    "status": gen_data.get("status"),
                    "created_at": gen_data.get("created_at"),
                    "warmed_at": datetime.utcnow().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch generation metadata for {generation_id}: {e}")
            return None
    
    async def _fetch_team_collaboration_context(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Fetch team collaboration context."""
        try:
            db = await get_database()
            team_data = await db.execute_query(
                table="teams",
                operation="select",
                filters={"id": team_id},
                single=True
            )
            
            if team_data:
                return {
                    "team_id": team_id,
                    "name": team_data.get("name"),
                    "is_active": team_data.get("is_active"),
                    "created_at": team_data.get("created_at"),
                    "warmed_at": datetime.utcnow().isoformat()
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to fetch team collaboration context for {team_id}: {e}")
            return None
    
    async def _fetch_resource_for_warming(self, resource_key: str) -> Optional[Dict[str, Any]]:
        """Fetch generic resource data for warming."""
        # This would implement specific fetching logic based on resource key type
        return {
            "resource_key": resource_key,
            "warmed_at": datetime.utcnow().isoformat(),
            "data": f"warmed_data_for_{resource_key}"
        }
    
    def get_warming_statistics(self) -> Dict[str, Any]:
        """Get comprehensive warming statistics."""
        return {
            "warming_metrics": self.warming_metrics,
            "user_contexts_count": len(self.user_warming_contexts),
            "active_strategies": {
                name: strategy.enabled 
                for name, strategy in self.warming_strategies.items()
            },
            "strategy_effectiveness": dict(self.warming_metrics["strategy_effectiveness"]),
            "warming_active": self.warming_active
        }


# Global enhanced warming strategies instance
enhanced_warming_strategies: Optional[EnhancedCacheWarmingStrategies] = None


def get_enhanced_warming_strategies() -> EnhancedCacheWarmingStrategies:
    """Get or create global enhanced warming strategies."""
    global enhanced_warming_strategies
    if enhanced_warming_strategies is None:
        enhanced_warming_strategies = EnhancedCacheWarmingStrategies()
    return enhanced_warming_strategies


# Convenience functions for triggering warming
async def trigger_user_login_cache_warming(user_id: str) -> Dict[str, Any]:
    """Trigger comprehensive cache warming when user logs in."""
    strategies = get_enhanced_warming_strategies()
    return await strategies.trigger_user_login_warming(user_id)


async def trigger_generation_cache_warming(generation_id: str, user_id: str) -> Dict[str, Any]:
    """Trigger cache warming when generation is created."""
    strategies = get_enhanced_warming_strategies()
    return await strategies.trigger_generation_creation_warming(generation_id, user_id)


async def trigger_team_cache_warming(team_id: str, user_id: str) -> Dict[str, Any]:
    """Trigger cache warming for team collaboration."""
    strategies = get_enhanced_warming_strategies()
    return await strategies.trigger_team_collaboration_warming(team_id, user_id)


async def start_enhanced_cache_warming():
    """Start enhanced cache warming strategies."""
    strategies = get_enhanced_warming_strategies()
    await strategies.start_enhanced_warming()


async def stop_enhanced_cache_warming():
    """Stop enhanced cache warming strategies."""
    if enhanced_warming_strategies:
        await enhanced_warming_strategies.stop_enhanced_warming()


def get_warming_effectiveness_report() -> Dict[str, Any]:
    """Get comprehensive warming effectiveness report."""
    if not enhanced_warming_strategies:
        return {"error": "Enhanced warming strategies not initialized"}
    
    return enhanced_warming_strategies.get_warming_statistics()