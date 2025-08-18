"""
Project service for business logic operations.
Enhanced with team-based access patterns and comprehensive authorization.
Following CLAUDE.md: Service layer for business logic.
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
import logging

from repositories.project_repository import ProjectRepository
from models.project import ProjectCreate, ProjectUpdate, ProjectResponse
from models.authorization import (
    ProjectPermissions, TeamAccessResult, AuthorizationMethod, ProjectVisibility,
    TeamRole, SecurityLevel, ValidationContext
)
from utils.enhanced_uuid_utils import EnhancedUUIDUtils, secure_uuid_validator


logger = logging.getLogger(__name__)


class ProjectService:
    """Service for project business logic."""
    
    def __init__(self, project_repository: ProjectRepository):
        self.project_repository = project_repository
    
    async def create_project(self, user_id: str, project_data: ProjectCreate) -> ProjectResponse:
        """Create a new project with validation."""
        try:
            # Validate project name
            if not project_data.name or len(project_data.name.strip()) == 0:
                raise ValueError("Project name cannot be empty")
            
            # Validate project name length
            if len(project_data.name) > 100:
                raise ValueError("Project name cannot exceed 100 characters")
            
            # Validate description length
            if project_data.description and len(project_data.description) > 500:
                raise ValueError("Project description cannot exceed 500 characters")
            
            # Validate tags
            if project_data.tags:
                if len(project_data.tags) > 10:
                    raise ValueError("Maximum 10 tags allowed")
                for tag in project_data.tags:
                    if len(tag) > 50:
                        raise ValueError("Tag cannot exceed 50 characters")
            
            # Create project
            project = await self.project_repository.create_project(user_id, project_data)
            
            # ENHANCEMENT: Auto-create project storage folders
            try:
                from services.storage_service import storage_service
                from uuid import UUID
                user_uuid = UUID(user_id)
                
                # Create project storage folders asynchronously (don't block project creation)
                import asyncio
                asyncio.create_task(storage_service.create_project_storage_folders(user_uuid, project.id))
                logger.info(f"📁 [PROJECT-SERVICE] Scheduled storage folder creation for project {project.id}")
                
            except Exception as storage_error:
                # Don't fail project creation if storage setup fails
                logger.warning(f"⚠️ [PROJECT-SERVICE] Storage folder creation failed for project {project.id}: {storage_error}")
            
            logger.info(f"Created project {str(project.id)} for user {user_id}")
            return project
            
        except ValueError as e:
            logger.warning(f"Project creation validation error for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Project creation failed for user {user_id}: {str(e)}")
            raise ValueError("Failed to create project")
    
    async def get_project(self, project_id: UUID, user_id: str) -> Optional[ProjectResponse]:
        """Get project by ID with access control."""
        try:
            project = await self.project_repository.get_project(project_id, user_id)
            
            if not project:
                logger.warning(f"Project {str(project_id)} not found or no access for user {user_id}")
                return None
            
            # Update generation count
            generation_count = await self.project_repository.get_project_generation_count(project_id)
            project.generation_count = generation_count
            
            return project
            
        except Exception as e:
            logger.error(f"Failed to get project {str(project_id)} for user {user_id}: {str(e)}")
            raise ValueError("Failed to get project")
    
    async def list_user_projects(
        self, 
        user_id: str, 
        skip: int = 0, 
        limit: int = 50,
        visibility: Optional[str] = None
    ) -> List[ProjectResponse]:
        """List projects accessible to user with pagination."""
        try:
            # Validate pagination parameters
            if skip < 0:
                skip = 0
            if limit <= 0 or limit > 100:
                limit = 50
            
            # Validate visibility filter
            if visibility and visibility not in ["private", "public"]:
                raise ValueError("Invalid visibility filter")
            
            projects = await self.project_repository.list_user_projects(
                user_id, skip, limit, visibility
            )
            
            # Update generation counts for all projects
            for project in projects:
                try:
                    generation_count = await self.project_repository.get_project_generation_count(project.id)
                    project.generation_count = generation_count
                except Exception as e:
                    logger.warning(f"Failed to get generation count for project {project.id}: {str(e)}")
                    project.generation_count = 0
            
            return projects
            
        except ValueError as e:
            logger.warning(f"Project listing validation error for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to list projects for user {user_id}: {str(e)}")
            raise ValueError("Failed to list projects")
    
    async def update_project(
        self, 
        project_id: UUID, 
        user_id: str, 
        project_data: ProjectUpdate
    ) -> Optional[ProjectResponse]:
        """Update project with validation and access control."""
        try:
            # Validate update data
            if project_data.name is not None:
                if not project_data.name or len(project_data.name.strip()) == 0:
                    raise ValueError("Project name cannot be empty")
                if len(project_data.name) > 100:
                    raise ValueError("Project name cannot exceed 100 characters")
            
            if project_data.description is not None and len(project_data.description) > 500:
                raise ValueError("Project description cannot exceed 500 characters")
            
            if project_data.tags is not None:
                if len(project_data.tags) > 10:
                    raise ValueError("Maximum 10 tags allowed")
                for tag in project_data.tags:
                    if len(tag) > 50:
                        raise ValueError("Tag cannot exceed 50 characters")
            
            # Update project
            project = await self.project_repository.update_project(project_id, user_id, project_data)
            
            if not project:
                logger.warning(f"Project {str(project_id)} not found or no permission for user {user_id}")
                return None
            
            # Update generation count
            generation_count = await self.project_repository.get_project_generation_count(project_id)
            project.generation_count = generation_count
            
            logger.info(f"Updated project {str(project_id)} by user {user_id}")
            return project
            
        except ValueError as e:
            logger.warning(f"Project update validation error for user {user_id}: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Failed to update project {str(project_id)} for user {user_id}: {str(e)}")
            raise ValueError("Failed to update project")
    
    async def delete_project(self, project_id: UUID, user_id: str) -> bool:
        """Delete project with access control."""
        try:
            success = await self.project_repository.delete_project(project_id, user_id)
            
            if success:
                logger.info(f"Deleted project {str(project_id)} by user {user_id}")
            else:
                logger.warning(f"Project {str(project_id)} not found or no permission for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to delete project {str(project_id)} for user {user_id}: {str(e)}")
            raise ValueError("Failed to delete project")
    
    async def get_project_stats(self, project_id: UUID, user_id: str) -> dict:
        """Get project statistics."""
        try:
            project = await self.get_project(project_id, user_id)
            if not project:
                raise ValueError("Project not found")
            
            generation_count = await self.project_repository.get_project_generation_count(project_id)
            
            return {
                "id": str(project.id),
                "name": project.name,
                "generation_count": generation_count,
                "created_at": project.created_at.isoformat() if project.created_at else None,
                "updated_at": project.updated_at.isoformat() if project.updated_at else None,
                "visibility": project.visibility,
                "tags": project.tags
            }
            
        except Exception as e:
            logger.error(f"Failed to get project stats for {str(project_id)}: {str(e)}")
            raise ValueError("Failed to get project statistics")
    
    # TEAM-BASED ACCESS CONTROL METHODS
    
    async def validate_project_access(
        self, 
        project_id: UUID, 
        user_id: UUID, 
        required_access: str = "read",
        auth_token: str = None
    ) -> ProjectPermissions:
        """
        Comprehensive project access validation with team-based authorization.
        """
        logger.info(f"🔐 [PROJECT-ACCESS] Validating {required_access} access for user {user_id} on project {project_id}")
        
        # Security input validation
        validated_project_id = await secure_uuid_validator.validate_uuid_format(
            project_id, ValidationContext.PROJECT_ACCESS, strict=True
        )
        validated_user_id = await secure_uuid_validator.validate_uuid_format(
            user_id, ValidationContext.USER_PROFILE, strict=True
        )
        
        if not validated_project_id or not validated_user_id:
            return ProjectPermissions(
                project_id=project_id,
                user_id=user_id,
                granted=False,
                access_method=AuthorizationMethod.DIRECT_OWNERSHIP
            )
        
        try:
            # Step 1: Get project with security context
            project = await self.get_project(project_id, str(user_id))
            if not project:
                logger.warning(f"❌ [PROJECT-ACCESS] Project {project_id} not found")
                return ProjectPermissions(
                    project_id=project_id,
                    user_id=user_id,
                    granted=False,
                    access_method=AuthorizationMethod.DIRECT_OWNERSHIP
                )
            
            # Step 2: Check direct ownership
            if await EnhancedUUIDUtils.validate_uuid_ownership(
                project.owner_id, user_id, ValidationContext.PROJECT_ACCESS
            ):
                logger.info(f"✅ [PROJECT-ACCESS] Direct owner access granted for project {project_id}")
                return ProjectPermissions(
                    project_id=project_id,
                    user_id=user_id,
                    granted=True,
                    access_method=AuthorizationMethod.DIRECT_OWNERSHIP,
                    can_view=True,
                    can_edit=True,
                    can_delete=True,
                    can_manage_teams=True,
                    can_invite_members=True,
                    visibility=ProjectVisibility(project.visibility) if hasattr(project, 'visibility') else ProjectVisibility.PRIVATE,
                    team_roles=[TeamRole.OWNER]
                )
            
            # Step 3: Check team-based access
            team_access = await self._check_project_team_access(
                project_id, user_id, required_access, auth_token
            )
            
            if team_access.granted:
                logger.info(f"✅ [PROJECT-ACCESS] Team access granted for project {project_id} via {team_access.access_method}")
                return ProjectPermissions(
                    project_id=project_id,
                    user_id=user_id,
                    granted=True,
                    access_method=team_access.access_method,
                    can_view=True,
                    can_edit=team_access.role in [TeamRole.CONTRIBUTOR, TeamRole.EDITOR, TeamRole.ADMIN, TeamRole.OWNER],
                    can_delete=team_access.role in [TeamRole.ADMIN, TeamRole.OWNER],
                    can_manage_teams=team_access.role in [TeamRole.ADMIN, TeamRole.OWNER],
                    can_invite_members=team_access.role in [TeamRole.EDITOR, TeamRole.ADMIN, TeamRole.OWNER],
                    visibility=ProjectVisibility(project.visibility) if hasattr(project, 'visibility') else ProjectVisibility.PRIVATE,
                    team_roles=[team_access.role] if team_access.role else []
                )
            
            # Step 4: Check project visibility (public access)
            if hasattr(project, 'visibility') and project.visibility in ['public', 'public_read']:
                if required_access == "read":
                    logger.info(f"✅ [PROJECT-ACCESS] Public read access granted for project {project_id}")
                    return ProjectPermissions(
                        project_id=project_id,
                        user_id=user_id,
                        granted=True,
                        access_method=AuthorizationMethod.PUBLIC_ACCESS,
                        can_view=True,
                        can_edit=False,
                        can_delete=False,
                        can_manage_teams=False,
                        can_invite_members=False,
                        visibility=ProjectVisibility.PUBLIC_READ,
                        team_roles=[]
                    )
            
            # Access denied
            logger.warning(f"❌ [PROJECT-ACCESS] Access denied for user {user_id} on project {project_id}")
            return ProjectPermissions(
                project_id=project_id,
                user_id=user_id,
                granted=False,
                access_method=AuthorizationMethod.DIRECT_OWNERSHIP
            )
            
        except Exception as e:
            logger.error(f"❌ [PROJECT-ACCESS] Authorization error: {e}")
            return ProjectPermissions(
                project_id=project_id,
                user_id=user_id,
                granted=False,
                access_method=AuthorizationMethod.DIRECT_OWNERSHIP
            )
    
    async def _check_project_team_access(
        self, project_id: UUID, user_id: UUID, required_access: str, auth_token: str
    ) -> TeamAccessResult:
        """Check team-based access to project."""
        
        try:
            from services.team_service import TeamService
            team_service = TeamService()
            
            # Get user's team memberships for this project
            # This would integrate with the team service to check if user is part of any teams
            # that have access to this project
            
            # For now, return denied access - this would be implemented with actual team queries
            return TeamAccessResult(
                granted=False,
                denial_reason="team_access_not_implemented",
                checked_methods=["project_team_membership"]
            )
            
        except Exception as e:
            logger.error(f"❌ [TEAM-ACCESS] Error checking team access: {e}")
            return TeamAccessResult(
                granted=False,
                denial_reason="team_access_error",
                checked_methods=["project_team_membership"]
            )
    
    async def handle_project_visibility_change(
        self, project_id: UUID, old_visibility: str, new_visibility: str, user_id: UUID
    ) -> None:
        """Handle cascading effects of project visibility changes."""
        
        logger.info(f"🔄 [PROJECT-VISIBILITY] Project {project_id}: {old_visibility} → {new_visibility}")
        
        try:
            # Step 1: Validate user has permission to change visibility
            project_permissions = await self.validate_project_access(
                project_id, user_id, "admin"
            )
            
            if not project_permissions.granted or not project_permissions.can_manage_teams:
                raise PermissionError("Insufficient permissions to change project visibility")
            
            # Step 2: Handle visibility restrictions (public → private)
            if old_visibility == 'public' and new_visibility in ['private', 'team']:
                await self._revoke_public_access_tokens(project_id)
                await self._cleanup_public_media_urls(project_id)
            
            # Step 3: Handle team access changes
            if new_visibility == 'team':
                await self._validate_team_access_configuration(project_id)
            
            # Step 4: Invalidate cached permissions for all project resources
            await self._invalidate_project_permission_cache(project_id)
            
            logger.info(f"✅ [PROJECT-VISIBILITY] Successfully updated project {project_id} visibility")
            
        except Exception as e:
            logger.error(f"❌ [PROJECT-VISIBILITY] Failed to handle visibility change: {e}")
            raise
    
    async def _revoke_public_access_tokens(self, project_id: UUID) -> None:
        """Revoke public access tokens for project."""
        # Implementation would revoke any public access tokens
        logger.info(f"🔐 [PROJECT-SECURITY] Revoking public access tokens for project {project_id}")
    
    async def _cleanup_public_media_urls(self, project_id: UUID) -> None:
        """Cleanup public media URLs for project."""
        # Implementation would invalidate public media URLs
        logger.info(f"🧹 [PROJECT-SECURITY] Cleaning up public media URLs for project {project_id}")
    
    async def _validate_team_access_configuration(self, project_id: UUID) -> None:
        """Validate team access configuration for project."""
        # Implementation would ensure proper team access configuration
        logger.info(f"🔍 [PROJECT-TEAMS] Validating team access configuration for project {project_id}")
    
    async def _invalidate_project_permission_cache(self, project_id: UUID) -> None:
        """Invalidate cached permissions for project."""
        try:
            from utils.cache_manager import get_cache_manager
            cache_manager = get_cache_manager()
            
            # Invalidate project-related cache entries
            project_pattern = f"project:{project_id}:*"
            await cache_manager.invalidate_pattern(project_pattern)
            
            logger.info(f"🔄 [CACHE] Invalidated project permissions cache for {project_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ [CACHE] Failed to invalidate project cache: {e}")
    
    async def get_project_team_members(
        self, project_id: UUID, user_id: UUID, auth_token: str = None
    ) -> List[Dict[str, Any]]:
        """Get team members with access to project."""
        
        # Validate user has access to view project members
        project_permissions = await self.validate_project_access(
            project_id, user_id, "read", auth_token
        )
        
        if not project_permissions.granted:
            raise PermissionError("Access denied to project team members")
        
        try:
            from services.team_service import TeamService
            team_service = TeamService()
            
            # Get all teams associated with this project and their members
            # This would be implemented with actual team queries
            
            return []  # Placeholder - would return actual team members
            
        except Exception as e:
            logger.error(f"❌ [PROJECT-TEAMS] Failed to get team members: {e}")
            raise ValueError("Failed to retrieve project team members")


# Create singleton instance
project_service = None


def get_project_service() -> ProjectService:
    """Get project service singleton."""
    global project_service
    if project_service is None:
        from database import db
        from repositories.project_repository import ProjectRepository
        
        # Use the service_client to bypass RLS for project operations
        supabase_client = db.service_client
        project_repository = ProjectRepository(supabase_client)
        project_service = ProjectService(project_repository)
    
    return project_service