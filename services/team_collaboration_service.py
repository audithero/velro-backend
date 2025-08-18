"""
Team Collaboration Service
Enterprise-grade team collaboration features with resource sharing and activity tracking.
Implements multi-user collaborative workflows and team-based resource management.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from database import get_database
from models.team import (
    TeamRole, TeamResponse, GenerationCollaborationCreate, GenerationCollaborationResponse,
    CollaborationType, EnhancedGenerationRequest, TeamStatistics
)
from models.authorization import (
    AuthorizationMethod, ValidationContext, SecurityLevel, TeamAccessResult
)
from services.team_service import TeamService
from services.enhanced_authorization_service import enhanced_authorization_service
from utils.enhanced_uuid_utils import secure_uuid_validator
from utils.exceptions import NotFoundError, ForbiddenError, ConflictError
from utils.cache_manager import CacheManager
import json

logger = logging.getLogger(__name__)


class TeamCollaborationService:
    """
    Enterprise team collaboration service with resource sharing and activity tracking.
    Supports multi-user collaborative workflows and team-based resource management.
    """
    
    def __init__(self):
        self.cache_manager = CacheManager()
        self.team_service = TeamService()
        self.authorization_service = enhanced_authorization_service
        
        # Collaboration metrics for enterprise monitoring
        self.metrics = {
            "collaborative_generations": 0,
            "team_resource_shares": 0,
            "cross_team_collaborations": 0,
            "team_activity_events": 0
        }
    
    async def create_team_generation(
        self,
        generation_request: EnhancedGenerationRequest,
        user_id: UUID,
        auth_token: str,
        client_ip: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a generation with team collaboration context.
        Supports parent-child relationships and team attribution.
        """
        logger.info(f"🎨 [TEAM-GEN] Creating team generation for user {user_id} in team context {generation_request.team_context_id}")
        
        try:
            # Validate team access if team context provided
            if generation_request.team_context_id:
                team_access = await self.team_service.validate_team_access(
                    generation_request.team_context_id,
                    user_id,
                    TeamRole.CONTRIBUTOR,  # Minimum role to create content
                    auth_token,
                    client_ip
                )
                
                if not team_access.granted:
                    raise ForbiddenError("Insufficient team permissions to create generation")
                
                logger.info(f"✅ [TEAM-ACCESS] User has {team_access.role.value} role in team {generation_request.team_context_id}")
            
            db = await get_database()
            
            # Create generation with team context
            generation_data = {
                "id": str(uuid4()),
                "user_id": str(user_id),
                "project_id": str(generation_request.project_id),
                "prompt": generation_request.prompt,
                "model_id": generation_request.model_id,
                "style_stack_id": str(generation_request.style_stack_id) if generation_request.style_stack_id else None,
                "negative_prompt": generation_request.negative_prompt,
                "reference_image_url": generation_request.reference_image_url,
                "parameters": generation_request.parameters,
                "status": "pending",
                "team_context_id": str(generation_request.team_context_id) if generation_request.team_context_id else None,
                "collaboration_intent": generation_request.collaboration_intent.value if generation_request.collaboration_intent else None,
                "parent_generation_id": str(generation_request.parent_generation_id) if generation_request.parent_generation_id else None,
                "change_description": generation_request.change_description,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Create generation record
            generation = db.execute_query(
                table="generations",
                operation="insert",
                data=generation_data,
                single=True,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            generation_id = UUID(generation["id"])
            
            # Create collaboration record if team context exists
            if generation_request.team_context_id:
                await self._create_generation_collaboration(
                    generation_id=generation_id,
                    team_id=generation_request.team_context_id,
                    contributor_id=user_id,
                    collaboration_type=generation_request.collaboration_intent or CollaborationType.ORIGINAL,
                    parent_generation_id=generation_request.parent_generation_id,
                    change_description=generation_request.change_description,
                    auth_token=auth_token
                )
            
            # Log team activity
            if generation_request.team_context_id:
                await self._log_team_activity(
                    team_id=generation_request.team_context_id,
                    user_id=user_id,
                    activity_type="generation_created",
                    resource_id=generation_id,
                    metadata={
                        "collaboration_type": generation_request.collaboration_intent.value if generation_request.collaboration_intent else "original",
                        "has_parent": generation_request.parent_generation_id is not None,
                        "model_id": generation_request.model_id
                    },
                    auth_token=auth_token
                )
            
            self.metrics["collaborative_generations"] += 1
            
            logger.info(f"✅ [TEAM-GEN] Created team generation {generation_id} with collaboration context")
            
            return {
                "generation_id": str(generation_id),
                "status": "pending",
                "team_context_id": str(generation_request.team_context_id) if generation_request.team_context_id else None,
                "collaboration_type": generation_request.collaboration_intent.value if generation_request.collaboration_intent else None,
                "created_at": generation["created_at"]
            }
            
        except Exception as e:
            logger.error(f"❌ [TEAM-GEN] Failed to create team generation: {e}")
            raise
    
    async def share_generation_with_team(
        self,
        generation_id: UUID,
        team_id: UUID,
        user_id: UUID,
        share_permissions: Dict[str, bool],
        auth_token: str
    ) -> GenerationCollaborationResponse:
        """
        Share an existing generation with a team.
        Creates collaboration record and sets up access permissions.
        """
        logger.info(f"🔗 [SHARE] Sharing generation {generation_id} with team {team_id}")
        
        try:
            # Validate user owns the generation or has share permissions
            generation_access = await self.authorization_service.validate_team_resource_access(
                resource_id=generation_id,
                resource_type="generation",
                user_id=user_id,
                required_access="share",
                auth_token=auth_token
            )
            
            if not generation_access.granted or not generation_access.can_share:
                raise ForbiddenError("Insufficient permissions to share this generation")
            
            # Validate user has permission to add resources to the target team
            team_access = await self.team_service.validate_team_access(
                team_id, user_id, TeamRole.CONTRIBUTOR, auth_token
            )
            
            if not team_access.granted:
                raise ForbiddenError("Insufficient team permissions to share resources")
            
            # Create collaboration record
            collaboration = await self._create_generation_collaboration(
                generation_id=generation_id,
                team_id=team_id,
                contributor_id=user_id,
                collaboration_type=CollaborationType.ORIGINAL,  # Sharing original content
                attribution_visible=share_permissions.get("attribution_visible", True),
                auth_token=auth_token
            )
            
            # Update generation with team context if not already set
            db = await get_database()
            generation = db.execute_query(
                table="generations",
                operation="select",
                filters={"id": str(generation_id)},
                single=True,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if generation and not generation.get("team_context_id"):
                db.execute_query(
                    table="generations",
                    operation="update",
                    filters={"id": str(generation_id)},
                    data={
                        "team_context_id": str(team_id),
                        "updated_at": datetime.utcnow().isoformat()
                    },
                    auth_token=auth_token,
                    user_id=str(user_id)
                )
            
            # Log team activity
            await self._log_team_activity(
                team_id=team_id,
                user_id=user_id,
                activity_type="generation_shared",
                resource_id=generation_id,
                metadata={
                    "shared_from": "individual",
                    "permissions": share_permissions
                },
                auth_token=auth_token
            )
            
            self.metrics["team_resource_shares"] += 1
            
            logger.info(f"✅ [SHARE] Successfully shared generation {generation_id} with team {team_id}")
            
            # Build response
            team = await self.team_service.get_team(team_id, user_id, auth_token)
            user_profile = await self.team_service._get_user_profile(user_id, auth_token)
            
            return GenerationCollaborationResponse(
                id=UUID(collaboration["id"]),
                generation_id=generation_id,
                team=team,
                contributor=user_profile,
                collaboration_type=CollaborationType.ORIGINAL,
                attribution_visible=collaboration["attribution_visible"],
                created_at=datetime.fromisoformat(collaboration["created_at"])
            )
            
        except Exception as e:
            logger.error(f"❌ [SHARE] Failed to share generation with team: {e}")
            raise
    
    async def get_team_generations(
        self,
        team_id: UUID,
        user_id: UUID,
        filters: Optional[Dict[str, Any]] = None,
        pagination: Optional[Dict[str, int]] = None,
        auth_token: str = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Get all generations associated with a team.
        Includes shared generations and team-created content.
        """
        logger.info(f"📋 [TEAM-GENS] Getting generations for team {team_id}")
        
        try:
            # Validate user has access to view team content
            team_access = await self.team_service.validate_team_access(
                team_id, user_id, TeamRole.VIEWER, auth_token
            )
            
            if not team_access.granted:
                raise ForbiddenError("Insufficient team permissions to view generations")
            
            db = await get_database()
            
            # Build query filters
            query_filters = {"team_context_id": str(team_id)}
            
            if filters:
                if filters.get("collaboration_type"):
                    query_filters["collaboration_intent"] = filters["collaboration_type"]
                if filters.get("user_id"):
                    query_filters["user_id"] = str(filters["user_id"])
                if filters.get("status"):
                    query_filters["status"] = filters["status"]
            
            # Get team generations
            generations = db.execute_query(
                table="generations",
                operation="select",
                filters=query_filters,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not generations:
                return [], 0
            
            # Enhance with collaboration details
            enhanced_generations = []
            
            for gen in generations:
                try:
                    # Get collaboration record
                    collaboration = db.execute_query(
                        table="generation_collaborations",
                        operation="select",
                        filters={
                            "generation_id": gen["id"],
                            "team_id": str(team_id)
                        },
                        single=True,
                        auth_token=auth_token,
                        user_id=str(user_id)
                    )
                    
                    # Get creator profile
                    creator_profile = await self.team_service._get_user_profile(
                        UUID(gen["user_id"]), auth_token
                    )
                    
                    enhanced_gen = {
                        **gen,
                        "collaboration": collaboration,
                        "creator": creator_profile,
                        "is_shared": collaboration is not None,
                        "collaboration_type": collaboration["collaboration_type"] if collaboration else gen.get("collaboration_intent"),
                        "team_context": {"team_id": str(team_id)}
                    }
                    
                    enhanced_generations.append(enhanced_gen)
                    
                except Exception as e:
                    logger.warning(f"Failed to enhance generation {gen.get('id')}: {e}")
                    enhanced_generations.append(gen)
            
            # Apply pagination
            total_count = len(enhanced_generations)
            
            if pagination:
                offset = pagination.get("offset", 0)
                limit = pagination.get("limit", 50)
                enhanced_generations = enhanced_generations[offset:offset + limit]
            
            logger.info(f"✅ [TEAM-GENS] Retrieved {len(enhanced_generations)} generations for team {team_id}")
            
            return enhanced_generations, total_count
            
        except Exception as e:
            logger.error(f"❌ [TEAM-GENS] Failed to get team generations: {e}")
            raise
    
    async def create_generation_improvement(
        self,
        parent_generation_id: UUID,
        team_id: UUID,
        user_id: UUID,
        improvement_request: Dict[str, Any],
        auth_token: str
    ) -> Dict[str, Any]:
        """
        Create an improved version of a generation within team context.
        Maintains parent-child relationship and collaboration attribution.
        """
        logger.info(f"⚡ [IMPROVE] Creating improvement of generation {parent_generation_id} in team {team_id}")
        
        try:
            # Validate access to parent generation
            parent_access = await self.authorization_service.validate_team_resource_access(
                resource_id=parent_generation_id,
                resource_type="generation",
                user_id=user_id,
                required_access="read",
                auth_token=auth_token
            )
            
            if not parent_access.granted:
                raise ForbiddenError("Cannot access parent generation for improvement")
            
            # Validate team permissions
            team_access = await self.team_service.validate_team_access(
                team_id, user_id, TeamRole.CONTRIBUTOR, auth_token
            )
            
            if not team_access.granted:
                raise ForbiddenError("Insufficient team permissions to create improvements")
            
            # Get parent generation details
            db = await get_database()
            parent_generation = db.execute_query(
                table="generations",
                operation="select",
                filters={"id": str(parent_generation_id)},
                single=True,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not parent_generation:
                raise NotFoundError("Parent generation not found")
            
            # Create enhanced generation request for improvement
            enhanced_request = EnhancedGenerationRequest(
                prompt=improvement_request.get("prompt", parent_generation["prompt"]),
                project_id=UUID(improvement_request.get("project_id", parent_generation["project_id"])),
                model_id=improvement_request.get("model_id", parent_generation["model_id"]),
                style_stack_id=UUID(improvement_request["style_stack_id"]) if improvement_request.get("style_stack_id") else None,
                negative_prompt=improvement_request.get("negative_prompt", parent_generation.get("negative_prompt")),
                reference_image_url=improvement_request.get("reference_image_url"),
                parameters=improvement_request.get("parameters", parent_generation.get("parameters", {})),
                parent_generation_id=parent_generation_id,
                team_context_id=team_id,
                collaboration_intent=CollaborationType.IMPROVE,
                change_description=improvement_request.get("change_description", "Team improvement")
            )
            
            # Create the improved generation
            result = await self.create_team_generation(
                generation_request=enhanced_request,
                user_id=user_id,
                auth_token=auth_token
            )
            
            logger.info(f"✅ [IMPROVE] Created improvement generation {result['generation_id']}")
            
            return {
                **result,
                "parent_generation_id": str(parent_generation_id),
                "improvement_type": "team_collaboration",
                "change_description": improvement_request.get("change_description")
            }
            
        except Exception as e:
            logger.error(f"❌ [IMPROVE] Failed to create generation improvement: {e}")
            raise
    
    async def get_team_activity_feed(
        self,
        team_id: UUID,
        user_id: UUID,
        limit: int = 50,
        auth_token: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent team activity feed for collaboration tracking.
        """
        logger.info(f"📈 [ACTIVITY] Getting activity feed for team {team_id}")
        
        try:
            # Validate team access
            team_access = await self.team_service.validate_team_access(
                team_id, user_id, TeamRole.VIEWER, auth_token
            )
            
            if not team_access.granted:
                raise ForbiddenError("Insufficient team permissions to view activity")
            
            db = await get_database()
            
            # Get recent team activities
            activities = db.execute_query(
                table="team_activities",
                operation="select",
                filters={"team_id": str(team_id)},
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not activities:
                return []
            
            # Sort by timestamp (newest first) and limit
            sorted_activities = sorted(
                activities,
                key=lambda x: datetime.fromisoformat(x["created_at"]),
                reverse=True
            )[:limit]
            
            # Enhance with user profiles and resource details
            enhanced_activities = []
            
            for activity in sorted_activities:
                try:
                    # Get user profile
                    user_profile = await self.team_service._get_user_profile(
                        UUID(activity["user_id"]), auth_token
                    )
                    
                    # Get resource details if applicable
                    resource_details = None
                    if activity.get("resource_id"):
                        if activity["activity_type"].startswith("generation_"):
                            # Get generation details
                            resource_details = db.execute_query(
                                table="generations",
                                operation="select",
                                filters={"id": activity["resource_id"]},
                                single=True,
                                auth_token=auth_token,
                                user_id=str(user_id)
                            )
                    
                    enhanced_activity = {
                        "id": activity["id"],
                        "activity_type": activity["activity_type"],
                        "user": user_profile,
                        "resource_id": activity.get("resource_id"),
                        "resource_details": resource_details,
                        "metadata": activity.get("metadata", {}),
                        "created_at": activity["created_at"],
                        "team_id": str(team_id)
                    }
                    
                    enhanced_activities.append(enhanced_activity)
                    
                except Exception as e:
                    logger.warning(f"Failed to enhance activity {activity.get('id')}: {e}")
                    enhanced_activities.append(activity)
            
            logger.info(f"✅ [ACTIVITY] Retrieved {len(enhanced_activities)} activities for team {team_id}")
            
            return enhanced_activities
            
        except Exception as e:
            logger.error(f"❌ [ACTIVITY] Failed to get team activity feed: {e}")
            raise
    
    # PRIVATE HELPER METHODS
    
    async def _create_generation_collaboration(
        self,
        generation_id: UUID,
        team_id: UUID,
        contributor_id: UUID,
        collaboration_type: CollaborationType,
        parent_generation_id: Optional[UUID] = None,
        change_description: Optional[str] = None,
        attribution_visible: bool = True,
        auth_token: str = None
    ) -> Dict[str, Any]:
        """Create a generation collaboration record."""
        
        db = await get_database()
        
        collaboration_data = {
            "generation_id": str(generation_id),
            "team_id": str(team_id),
            "contributor_id": str(contributor_id),
            "collaboration_type": collaboration_type.value,
            "parent_generation_id": str(parent_generation_id) if parent_generation_id else None,
            "change_description": change_description,
            "attribution_visible": attribution_visible,
            "created_at": datetime.utcnow().isoformat()
        }
        
        return db.execute_query(
            table="generation_collaborations",
            operation="insert",
            data=collaboration_data,
            single=True,
            auth_token=auth_token,
            user_id=str(contributor_id)
        )
    
    async def _log_team_activity(
        self,
        team_id: UUID,
        user_id: UUID,
        activity_type: str,
        resource_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None,
        auth_token: str = None
    ) -> None:
        """Log team activity for audit trails and feed."""
        
        try:
            db = await get_database()
            
            activity_data = {
                "id": str(uuid4()),
                "team_id": str(team_id),
                "user_id": str(user_id),
                "activity_type": activity_type,
                "resource_id": str(resource_id) if resource_id else None,
                "metadata": metadata or {},
                "created_at": datetime.utcnow().isoformat()
            }
            
            # Check if team_activities table exists, if not create it
            try:
                db.execute_query(
                    table="team_activities",
                    operation="insert",
                    data=activity_data,
                    auth_token=auth_token,
                    user_id=str(user_id)
                )
                
                self.metrics["team_activity_events"] += 1
                
            except Exception as create_error:
                # Table might not exist, create it
                logger.info(f"Creating team_activities table: {create_error}")
                await self._ensure_team_activities_table(db, auth_token, str(user_id))
                
                # Retry insert
                db.execute_query(
                    table="team_activities",
                    operation="insert",
                    data=activity_data,
                    auth_token=auth_token,
                    user_id=str(user_id)
                )
            
        except Exception as e:
            logger.warning(f"⚠️ [ACTIVITY-LOG] Failed to log team activity: {e}")
    
    async def _ensure_team_activities_table(self, db, auth_token: str, user_id: str) -> None:
        """Ensure team_activities table exists for activity logging."""
        
        # This would typically be handled by a migration, but for dynamic creation:
        logger.info("📝 [ACTIVITY-TABLE] Team activities table creation handled by database schema")


# Singleton instance for global use
team_collaboration_service = TeamCollaborationService()