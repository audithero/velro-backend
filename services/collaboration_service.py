"""
Collaboration service for team-based generation management.
Following CLAUDE.md: Security-first, RLS-aware, performant collaboration features.
"""
import logging
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime

from database import get_database, SupabaseClient
from models.team import (
    EnhancedGenerationRequest, GenerationCollaborationCreate,
    GenerationCollaborationResponse, ProjectPrivacySettingsUpdate,
    ProjectPrivacySettingsResponse, ProjectTeamCreate, ProjectTeamUpdate,
    ProjectTeamResponse, CollaborationType, ProjectAccessLevel,
    TeamResponse, UserProfile
)
from models.generation import GenerationResponse, GenerationCreate, GenerationStatus
from services.generation_service import generation_service
from services.team_service import TeamService
from utils.exceptions import NotFoundError, ConflictError, ForbiddenError, ValidationError
# Security utilities would be imported here if needed

logger = logging.getLogger(__name__)


class CollaborationService:
    """Service for managing collaborative generation features."""
    
    @staticmethod
    async def create_collaborative_generation(
        generation_data: EnhancedGenerationRequest,
        user_id: str,
        auth_token: str = None
    ) -> GenerationResponse:
        """
        Create a generation with team collaboration context.
        
        Args:
            generation_data: Enhanced generation request with team context
            user_id: User creating the generation
            auth_token: JWT token for authentication
            
        Returns:
            Created generation with collaboration metadata
        """
        db = await get_database()
        
        try:
            # Security validation: Verify user access to project
            await CollaborationService._validate_project_access(
                generation_data.project_id, user_id, "write", db, auth_token
            )
            
            # If team context is specified, validate team membership
            if generation_data.team_context_id:
                await CollaborationService._validate_team_membership(
                    generation_data.team_context_id, user_id, db, auth_token
                )
            
            # Create base generation request
            base_generation = GenerationCreate(
                project_id=generation_data.project_id,
                model_id=generation_data.model_id,
                prompt=generation_data.prompt,
                negative_prompt=generation_data.negative_prompt,
                reference_image_url=generation_data.reference_image_url,
                parameters=generation_data.parameters,
                style_stack_id=generation_data.style_stack_id
            )
            
            # Create the generation using the existing service
            generation = await generation_service.create_generation(
                user_id=user_id,
                generation_data=base_generation,
                auth_token=auth_token
            )
            
            # Add collaboration metadata to the database
            if generation_data.team_context_id or generation_data.collaboration_intent:
                await CollaborationService._update_generation_collaboration_metadata(
                    generation.id,
                    generation_data.team_context_id,
                    generation_data.collaboration_intent,
                    generation_data.parent_generation_id,
                    generation_data.change_description,
                    db,
                    auth_token
                )
            
            # Create collaboration record if team context exists
            if generation_data.team_context_id:
                collaboration_create = GenerationCollaborationCreate(
                    team_id=generation_data.team_context_id,
                    collaboration_type=generation_data.collaboration_intent or CollaborationType.ORIGINAL,
                    parent_generation_id=generation_data.parent_generation_id,
                    change_description=generation_data.change_description,
                    attribution_visible=True
                )
                
                await CollaborationService.add_generation_collaboration(
                    generation.id, collaboration_create, user_id, db, auth_token
                )
            
            logger.info(f"Created collaborative generation {generation.id} with team context {generation_data.team_context_id}")
            return generation
            
        except Exception as e:
            logger.error(f"Failed to create collaborative generation: {e}")
            raise
    
    @staticmethod
    async def transfer_generation(
        generation_id: UUID,
        target_project_id: UUID,
        user_id: str,
        change_description: Optional[str] = None,
        preserve_attribution: bool = True,
        auth_token: str = None
    ) -> GenerationResponse:
        """
        Transfer a generation to another project with attribution.
        
        Args:
            generation_id: Generation to transfer
            target_project_id: Target project
            user_id: User performing the transfer
            change_description: Description of changes made
            preserve_attribution: Whether to preserve original attribution
            auth_token: JWT token for authentication
            
        Returns:
            New generation in target project
        """
        db = await get_database()
        
        try:
            # Validate source generation access
            source_generation = await CollaborationService._get_generation_with_access_check(
                generation_id, user_id, db, auth_token
            )
            
            # Validate target project access
            await CollaborationService._validate_project_access(
                target_project_id, user_id, "write", db, auth_token
            )
            
            # Create new generation in target project
            new_generation_data = GenerationCreate(
                project_id=target_project_id,
                model_id=source_generation.get("model_id"),
                prompt=source_generation.get("prompt"),
                negative_prompt=source_generation.get("negative_prompt"),
                parameters=source_generation.get("parameters", {}),
                style_stack_id=source_generation.get("style_stack_id")
            )
            
            # If source has media_url, copy it as reference_image_url
            if source_generation.get("media_url"):
                new_generation_data.reference_image_url = source_generation.get("media_url")
            
            new_generation = await generation_service.create_generation(
                user_id=user_id,
                generation_data=new_generation_data,
                auth_token=auth_token
            )
            
            # Update new generation with transfer metadata
            await CollaborationService._update_generation_collaboration_metadata(
                new_generation.id,
                team_context_id=None,
                collaboration_intent=CollaborationType.FORK,
                parent_generation_id=generation_id,
                change_description=change_description,
                db=db,
                auth_token=auth_token
            )
            
            logger.info(f"Transferred generation {generation_id} to project {target_project_id} as {new_generation.id}")
            return new_generation
            
        except Exception as e:
            logger.error(f"Failed to transfer generation {generation_id}: {e}")
            raise
    
    @staticmethod
    async def add_generation_collaboration(
        generation_id: UUID,
        collaboration_data: GenerationCollaborationCreate,
        user_id: str,
        db: SupabaseClient = None,
        auth_token: str = None
    ) -> GenerationCollaborationResponse:
        """Add collaboration metadata to a generation."""
        if db is None:
            db = await get_database()
        
        try:
            # Validate access to generation
            await CollaborationService._get_generation_with_access_check(
                generation_id, user_id, db, auth_token
            )
            
            # Validate team membership
            await CollaborationService._validate_team_membership(
                collaboration_data.team_id, user_id, db, auth_token
            )
            
            # Check for existing collaboration
            existing = db.execute_query(
                table="generation_collaborations",
                operation="select",
                filters={
                    "generation_id": str(generation_id),
                    "team_id": str(collaboration_data.team_id),
                    "contributor_id": user_id
                },
                single=True,
                auth_token=auth_token
            )
            
            if existing:
                raise ConflictError("Collaboration already exists for this generation and team")
            
            # Create collaboration record
            collaboration_record = {
                "generation_id": str(generation_id),
                "team_id": str(collaboration_data.team_id),
                "contributor_id": user_id,
                "collaboration_type": collaboration_data.collaboration_type.value,
                "parent_generation_id": str(collaboration_data.parent_generation_id) if collaboration_data.parent_generation_id else None,
                "change_description": collaboration_data.change_description,
                "attribution_visible": collaboration_data.attribution_visible,
                "created_at": datetime.utcnow().isoformat()
            }
            
            created_collaboration = db.execute_query(
                table="generation_collaborations",
                operation="insert",
                data=collaboration_record,
                single=True,
                auth_token=auth_token
            )
            
            # Get team and user info for response
            team_info = db.execute_query(
                table="teams",
                operation="select",
                filters={"id": str(collaboration_data.team_id)},
                single=True,
                auth_token=auth_token
            )
            
            user_info = db.execute_query(
                table="users",
                operation="select",
                filters={"id": user_id},
                single=True,
                auth_token=auth_token
            )
            
            return GenerationCollaborationResponse(
                id=created_collaboration["id"],
                generation_id=generation_id,
                team=TeamResponse(**team_info),
                contributor=UserProfile(**user_info),
                collaboration_type=CollaborationType(created_collaboration["collaboration_type"]),
                parent_generation_id=UUID(created_collaboration["parent_generation_id"]) if created_collaboration["parent_generation_id"] else None,
                change_description=created_collaboration["change_description"],
                attribution_visible=created_collaboration["attribution_visible"],
                created_at=datetime.fromisoformat(created_collaboration["created_at"])
            )
            
        except Exception as e:
            logger.error(f"Failed to add collaboration for generation {generation_id}: {e}")
            raise
    
    @staticmethod
    async def get_generation_collaborations(
        generation_id: UUID,
        user_id: str,
        auth_token: str = None
    ) -> List[GenerationCollaborationResponse]:
        """Get all collaborations for a generation."""
        db = await get_database()
        
        try:
            # Validate access to generation
            await CollaborationService._get_generation_with_access_check(
                generation_id, user_id, db, auth_token
            )
            
            # Get collaborations with team and user info
            collaborations = db.execute_query(
                table="generation_collaborations",
                operation="select",
                filters={"generation_id": str(generation_id)},
                auth_token=auth_token
            )
            
            result = []
            for collab in collaborations:
                # Get team info
                team_info = db.execute_query(
                    table="teams",
                    operation="select",
                    filters={"id": collab["team_id"]},
                    single=True,
                    auth_token=auth_token
                )
                
                # Get contributor info
                user_info = db.execute_query(
                    table="users",
                    operation="select",
                    filters={"id": collab["contributor_id"]},
                    single=True,
                    auth_token=auth_token
                )
                
                result.append(GenerationCollaborationResponse(
                    id=collab["id"],
                    generation_id=UUID(collab["generation_id"]),
                    team=TeamResponse(**team_info),
                    contributor=UserProfile(**user_info),
                    collaboration_type=CollaborationType(collab["collaboration_type"]),
                    parent_generation_id=UUID(collab["parent_generation_id"]) if collab["parent_generation_id"] else None,
                    change_description=collab["change_description"],
                    attribution_visible=collab["attribution_visible"],
                    created_at=datetime.fromisoformat(collab["created_at"])
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get collaborations for generation {generation_id}: {e}")
            raise
    
    @staticmethod
    async def get_generation_provenance(
        generation_id: UUID,
        user_id: str,
        auth_token: str = None
    ) -> Dict[str, Any]:
        """Get the full provenance chain for a generation."""
        db = await get_database()
        
        try:
            # Validate access to generation
            await CollaborationService._get_generation_with_access_check(
                generation_id, user_id, db, auth_token
            )
            
            # Get generation with collaboration info
            generation = db.execute_query(
                table="generations",
                operation="select",
                filters={"id": str(generation_id)},
                single=True,
                auth_token=auth_token
            )
            
            # Build provenance chain
            provenance_chain = []
            current_id = generation_id
            
            while current_id:
                current_gen = db.execute_query(
                    table="generations",
                    operation="select",
                    filters={"id": str(current_id)},
                    single=True,
                    auth_token=auth_token
                )
                
                if not current_gen:
                    break
                
                # Get collaborations for this generation
                collaborations = await CollaborationService.get_generation_collaborations(
                    UUID(current_gen["id"]), user_id, auth_token
                )
                
                provenance_chain.append({
                    "generation": current_gen,
                    "collaborations": [collab.model_dump() for collab in collaborations]
                })
                
                # Move to parent
                current_id = UUID(current_gen["parent_generation_id"]) if current_gen.get("parent_generation_id") else None
            
            return {
                "generation_id": str(generation_id),
                "provenance_chain": provenance_chain,
                "chain_length": len(provenance_chain)
            }
            
        except Exception as e:
            logger.error(f"Failed to get provenance for generation {generation_id}: {e}")
            raise
    
    @staticmethod
    async def get_project_privacy_settings(
        project_id: UUID,
        user_id: str,
        auth_token: str = None
    ) -> ProjectPrivacySettingsResponse:
        """Get project privacy settings."""
        db = await get_database()
        
        try:
            # Validate project ownership
            await CollaborationService._validate_project_access(
                project_id, user_id, "admin", db, auth_token
            )
            
            # Get privacy settings
            settings = db.execute_query(
                table="project_privacy_settings",
                operation="select",
                filters={"project_id": str(project_id)},
                single=True,
                auth_token=auth_token
            )
            
            if not settings:
                raise NotFoundError("Privacy settings not found")
            
            return ProjectPrivacySettingsResponse(**settings)
            
        except Exception as e:
            logger.error(f"Failed to get privacy settings for project {project_id}: {e}")
            raise
    
    @staticmethod
    async def update_project_privacy_settings(
        project_id: UUID,
        privacy_data: ProjectPrivacySettingsUpdate,
        user_id: str,
        auth_token: str = None
    ) -> ProjectPrivacySettingsResponse:
        """Update project privacy settings (owner only)."""
        db = await get_database()
        
        try:
            # Validate project ownership
            await CollaborationService._validate_project_access(
                project_id, user_id, "admin", db, auth_token
            )
            
            # Update privacy settings
            update_data = privacy_data.model_dump(exclude_unset=True)
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
            updated_settings = db.execute_query(
                table="project_privacy_settings",
                operation="update",
                data=update_data,
                filters={"project_id": str(project_id)},
                single=True,
                auth_token=auth_token
            )
            
            if not updated_settings:
                raise NotFoundError("Privacy settings not found")
            
            return ProjectPrivacySettingsResponse(**updated_settings)
            
        except Exception as e:
            logger.error(f"Failed to update privacy settings for project {project_id}: {e}")
            raise
    
    @staticmethod
    async def add_team_to_project(
        project_id: UUID,
        team_data: ProjectTeamCreate,
        user_id: str,
        auth_token: str = None
    ) -> ProjectTeamResponse:
        """Add a team to a project with specific access level."""
        db = await get_database()
        
        try:
            # Validate project ownership
            await CollaborationService._validate_project_access(
                project_id, user_id, "admin", db, auth_token
            )
            
            # Validate team exists and user is admin
            await CollaborationService._validate_team_admin_access(
                team_data.team_id, user_id, db, auth_token
            )
            
            # Check for existing relationship
            existing = db.execute_query(
                table="project_teams",
                operation="select",
                filters={
                    "project_id": str(project_id),
                    "team_id": str(team_data.team_id)
                },
                single=True,
                auth_token=auth_token
            )
            
            if existing:
                raise ConflictError("Team already has access to this project")
            
            # Create project-team relationship
            project_team_data = {
                "project_id": str(project_id),
                "team_id": str(team_data.team_id),
                "access_level": team_data.access_level.value,
                "granted_by": user_id,
                "created_at": datetime.utcnow().isoformat()
            }
            
            created_relationship = db.execute_query(
                table="project_teams",
                operation="insert",
                data=project_team_data,
                single=True,
                auth_token=auth_token
            )
            
            # Get team info for response
            team_info = db.execute_query(
                table="teams",
                operation="select",
                filters={"id": str(team_data.team_id)},
                single=True,
                auth_token=auth_token
            )
            
            return ProjectTeamResponse(
                id=created_relationship["id"],
                project_id=project_id,
                team=TeamResponse(**team_info),
                access_level=ProjectAccessLevel(created_relationship["access_level"]),
                granted_by=UUID(created_relationship["granted_by"]),
                created_at=datetime.fromisoformat(created_relationship["created_at"])
            )
            
        except Exception as e:
            logger.error(f"Failed to add team {team_data.team_id} to project {project_id}: {e}")
            raise
    
    @staticmethod
    async def get_project_teams(
        project_id: UUID,
        user_id: str,
        auth_token: str = None
    ) -> List[ProjectTeamResponse]:
        """Get teams associated with a project."""
        db = await get_database()
        
        try:
            # Validate project access
            await CollaborationService._validate_project_access(
                project_id, user_id, "read", db, auth_token
            )
            
            # Get project teams
            project_teams = db.execute_query(
                table="project_teams",
                operation="select",
                filters={"project_id": str(project_id)},
                auth_token=auth_token
            )
            
            result = []
            for pt in project_teams:
                # Get team info
                team_info = db.execute_query(
                    table="teams",
                    operation="select",
                    filters={"id": pt["team_id"]},
                    single=True,
                    auth_token=auth_token
                )
                
                result.append(ProjectTeamResponse(
                    id=pt["id"],
                    project_id=project_id,
                    team=TeamResponse(**team_info),
                    access_level=ProjectAccessLevel(pt["access_level"]),
                    granted_by=UUID(pt["granted_by"]),
                    created_at=datetime.fromisoformat(pt["created_at"])
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get teams for project {project_id}: {e}")
            raise
    
    @staticmethod
    async def update_project_team_access(
        project_id: UUID,
        team_id: UUID,
        team_data: ProjectTeamUpdate,
        user_id: str,
        auth_token: str = None
    ) -> ProjectTeamResponse:
        """Update team access level for a project."""
        db = await get_database()
        
        try:
            # Validate project ownership
            await CollaborationService._validate_project_access(
                project_id, user_id, "admin", db, auth_token
            )
            
            # Update access level
            updated_relationship = db.execute_query(
                table="project_teams",
                operation="update",
                data={"access_level": team_data.access_level.value},
                filters={
                    "project_id": str(project_id),
                    "team_id": str(team_id)
                },
                single=True,
                auth_token=auth_token
            )
            
            if not updated_relationship:
                raise NotFoundError("Project team relationship not found")
            
            # Get team info for response
            team_info = db.execute_query(
                table="teams",
                operation="select",
                filters={"id": str(team_id)},
                single=True,
                auth_token=auth_token
            )
            
            return ProjectTeamResponse(
                id=updated_relationship["id"],
                project_id=project_id,
                team=TeamResponse(**team_info),
                access_level=ProjectAccessLevel(updated_relationship["access_level"]),
                granted_by=UUID(updated_relationship["granted_by"]),
                created_at=datetime.fromisoformat(updated_relationship["created_at"])
            )
            
        except Exception as e:
            logger.error(f"Failed to update team {team_id} access for project {project_id}: {e}")
            raise
    
    @staticmethod
    async def remove_team_from_project(
        project_id: UUID,
        team_id: UUID,
        user_id: str,
        auth_token: str = None
    ):
        """Remove team access from a project."""
        db = await get_database()
        
        try:
            # Validate project ownership
            await CollaborationService._validate_project_access(
                project_id, user_id, "admin", db, auth_token
            )
            
            # Delete relationship
            deleted = db.execute_query(
                table="project_teams",
                operation="delete",
                filters={
                    "project_id": str(project_id),
                    "team_id": str(team_id)
                },
                auth_token=auth_token
            )
            
            if not deleted:
                raise NotFoundError("Project team relationship not found")
            
            logger.info(f"Removed team {team_id} access from project {project_id}")
            
        except Exception as e:
            logger.error(f"Failed to remove team {team_id} from project {project_id}: {e}")
            raise
    
    @staticmethod
    async def get_team_accessible_projects(
        team_id: UUID,
        user_id: str,
        auth_token: str = None
    ) -> List[Dict[str, Any]]:
        """Get all projects accessible to a team."""
        db = await get_database()
        
        try:
            # Validate team membership
            await CollaborationService._validate_team_membership(
                team_id, user_id, db, auth_token
            )
            
            # Get projects accessible to team
            project_teams = db.execute_query(
                table="project_teams",
                operation="select",
                filters={"team_id": str(team_id)},
                auth_token=auth_token
            )
            
            result = []
            for pt in project_teams:
                # Get project info
                project_info = db.execute_query(
                    table="projects",
                    operation="select",
                    filters={"id": pt["project_id"]},
                    single=True,
                    auth_token=auth_token
                )
                
                if project_info:
                    result.append({
                        "project": project_info,
                        "access_level": pt["access_level"],
                        "granted_at": pt["created_at"]
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get accessible projects for team {team_id}: {e}")
            raise
    
    # Private helper methods
    
    @staticmethod
    async def _validate_project_access(
        project_id: UUID,
        user_id: str,
        required_access: str,
        db: SupabaseClient,
        auth_token: str = None
    ):
        """Validate user has required access to project."""
        # Check project ownership
        project = db.execute_query(
            table="projects",
            operation="select",
            filters={"id": str(project_id)},
            single=True,
            auth_token=auth_token
        )
        
        if not project:
            raise NotFoundError("Project not found")
        
        # Owner has full access
        if project["user_id"] == user_id:
            return
        
        # Check team-based access
        if required_access == "read":
            # For read access, check if user's teams have access
            user_teams = db.execute_query(
                table="team_members",
                operation="select",
                filters={"user_id": user_id, "is_active": True},
                auth_token=auth_token
            )
            
            team_ids = [tm["team_id"] for tm in user_teams]
            if team_ids:
                project_teams = db.execute_query(
                    table="project_teams",
                    operation="select",
                    filters={"project_id": str(project_id)},
                    auth_token=auth_token
                )
                
                for pt in project_teams:
                    if pt["team_id"] in team_ids:
                        return  # User has access through team
        
        raise ForbiddenError("Insufficient permissions to access project")
    
    @staticmethod
    async def _validate_team_membership(
        team_id: UUID,
        user_id: str,
        db: SupabaseClient,
        auth_token: str = None
    ):
        """Validate user is a member of the team."""
        membership = db.execute_query(
            table="team_members",
            operation="select",
            filters={
                "team_id": str(team_id),
                "user_id": user_id,
                "is_active": True
            },
            single=True,
            auth_token=auth_token
        )
        
        if not membership:
            raise ForbiddenError("Not a member of the specified team")
    
    @staticmethod
    async def _validate_team_admin_access(
        team_id: UUID,
        user_id: str,
        db: SupabaseClient,
        auth_token: str = None
    ):
        """Validate user has admin access to team."""
        membership = db.execute_query(
            table="team_members",
            operation="select",
            filters={
                "team_id": str(team_id),
                "user_id": user_id,
                "is_active": True
            },
            single=True,
            auth_token=auth_token
        )
        
        if not membership or membership["role"] not in ["owner", "admin"]:
            raise ForbiddenError("Insufficient team permissions")
    
    @staticmethod
    async def _get_generation_with_access_check(
        generation_id: UUID,
        user_id: str,
        db: SupabaseClient,
        auth_token: str = None
    ) -> Dict[str, Any]:
        """Get generation and validate user access."""
        generation = db.execute_query(
            table="generations",
            operation="select",
            filters={"id": str(generation_id)},
            single=True,
            auth_token=auth_token
        )
        
        if not generation:
            raise NotFoundError("Generation not found")
        
        # Check if user owns the generation
        if generation["user_id"] == user_id:
            return generation
        
        # Check if user has access through project/team
        if generation.get("project_id"):
            try:
                await CollaborationService._validate_project_access(
                    UUID(generation["project_id"]), user_id, "read", db, auth_token
                )
                return generation
            except ForbiddenError:
                pass
        
        raise ForbiddenError("Access denied to generation")
    
    @staticmethod
    async def _update_generation_collaboration_metadata(
        generation_id: UUID,
        team_context_id: Optional[UUID],
        collaboration_intent: Optional[CollaborationType],
        parent_generation_id: Optional[UUID],
        change_description: Optional[str],
        db: SupabaseClient,
        auth_token: str = None
    ):
        """Update generation with collaboration metadata."""
        update_data = {}
        
        if team_context_id:
            update_data["team_context_id"] = str(team_context_id)
        
        if collaboration_intent:
            update_data["collaboration_intent"] = collaboration_intent.value
        
        if parent_generation_id:
            update_data["parent_generation_id"] = str(parent_generation_id)
        
        if change_description:
            update_data["change_description"] = change_description
        
        if update_data:
            db.execute_query(
                table="generations",
                operation="update",
                data=update_data,
                filters={"id": str(generation_id)},
                auth_token=auth_token
            )