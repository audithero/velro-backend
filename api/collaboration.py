"""
Team collaboration API endpoints for generation management.
Following CLAUDE.md: Security-first, RLS-aware, team collaboration features.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from uuid import UUID

from models.team import (
    EnhancedGenerationRequest, GenerationCollaborationCreate,
    GenerationCollaborationResponse, ProjectPrivacySettingsUpdate,
    ProjectPrivacySettingsResponse, ProjectTeamCreate, ProjectTeamUpdate,
    ProjectTeamResponse
)
from models.generation import GenerationResponse
from services.team_service import TeamService
from services.collaboration_service import CollaborationService
from services.team_collaboration_service import team_collaboration_service
from services.team_audit_service import team_audit_service, AuditEventType, AuditSeverity
from middleware.auth import require_auth, get_current_user
from utils.exceptions import NotFoundError, ConflictError, ForbiddenError
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/collaboration", tags=["collaboration"])


@router.post("/generations", response_model=GenerationResponse, status_code=status.HTTP_201_CREATED)
async def create_collaborative_generation(
    generation_data: EnhancedGenerationRequest,
    current_user: dict = Depends(get_current_user)
):
    """Create a generation with team collaboration context."""
    try:
        generation = await CollaborationService.create_collaborative_generation(
            generation_data, current_user["id"]
        )
        logger.info(f"User {current_user['id']} created collaborative generation {generation.id}")
        return generation
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to create collaborative generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create generation"
        )


@router.post("/generations/{generation_id}/transfer", response_model=GenerationResponse)
async def transfer_generation(
    generation_id: UUID,
    target_project_id: UUID = Query(..., description="Target project ID"),
    change_description: Optional[str] = Query(None, max_length=1000),
    preserve_attribution: bool = Query(True),
    current_user: dict = Depends(get_current_user)
):
    """Transfer a generation to another project with attribution."""
    try:
        transferred_generation = await CollaborationService.transfer_generation(
            generation_id=generation_id,
            target_project_id=target_project_id,
            user_id=current_user["id"],
            change_description=change_description,
            preserve_attribution=preserve_attribution
        )
        logger.info(f"User {current_user['id']} transferred generation {generation_id} to project {target_project_id}")
        return transferred_generation
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation or target project not found"
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to transfer generation {generation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to transfer generation"
        )


@router.post("/generations/{generation_id}/collaborate", response_model=GenerationCollaborationResponse)
async def add_generation_collaboration(
    generation_id: UUID,
    collaboration_data: GenerationCollaborationCreate,
    current_user: dict = Depends(get_current_user)
):
    """Add team collaboration metadata to a generation."""
    try:
        collaboration = await CollaborationService.add_generation_collaboration(
            generation_id, collaboration_data, current_user["id"]
        )
        logger.info(f"Added collaboration for generation {generation_id} by user {current_user['id']}")
        return collaboration
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found"
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to add collaboration for generation {generation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add collaboration"
        )


@router.get("/generations/{generation_id}/collaborations", response_model=List[GenerationCollaborationResponse])
async def get_generation_collaborations(
    generation_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get all collaborations for a generation."""
    try:
        collaborations = await CollaborationService.get_generation_collaborations(
            generation_id, current_user["id"]
        )
        return collaborations
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found or access denied"
        )
    except Exception as e:
        logger.error(f"Failed to get collaborations for generation {generation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve collaborations"
        )


@router.get("/generations/{generation_id}/provenance")
async def get_generation_provenance(
    generation_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get the full provenance chain for a generation."""
    try:
        provenance = await CollaborationService.get_generation_provenance(
            generation_id, current_user["id"]
        )
        return provenance
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation not found or access denied"
        )
    except Exception as e:
        logger.error(f"Failed to get provenance for generation {generation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve provenance"
        )


@router.get("/projects/{project_id}/privacy", response_model=ProjectPrivacySettingsResponse)
async def get_project_privacy_settings(
    project_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get project privacy settings."""
    try:
        settings = await CollaborationService.get_project_privacy_settings(
            project_id, current_user["id"]
        )
        return settings
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied"
        )
    except Exception as e:
        logger.error(f"Failed to get privacy settings for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve privacy settings"
        )


@router.put("/projects/{project_id}/privacy", response_model=ProjectPrivacySettingsResponse)
async def update_project_privacy_settings(
    project_id: UUID,
    privacy_data: ProjectPrivacySettingsUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update project privacy settings (owner only)."""
    try:
        settings = await CollaborationService.update_project_privacy_settings(
            project_id, privacy_data, current_user["id"]
        )
        logger.info(f"User {current_user['id']} updated privacy settings for project {project_id}")
        return settings
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only project owner can update privacy settings"
        )
    except Exception as e:
        logger.error(f"Failed to update privacy settings for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update privacy settings"
        )


@router.post("/projects/{project_id}/teams", response_model=ProjectTeamResponse)
async def add_team_to_project(
    project_id: UUID,
    team_data: ProjectTeamCreate,
    current_user: dict = Depends(get_current_user)
):
    """Add a team to a project with specific access level."""
    try:
        project_team = await CollaborationService.add_team_to_project(
            project_id, team_data, current_user["id"]
        )
        logger.info(f"Added team {team_data.team_id} to project {project_id}")
        return project_team
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project or team not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to add team to project"
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to add team to project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to add team to project"
        )


@router.get("/projects/{project_id}/teams", response_model=List[ProjectTeamResponse])
async def get_project_teams(
    project_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get teams associated with a project."""
    try:
        teams = await CollaborationService.get_project_teams(project_id, current_user["id"])
        return teams
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found or access denied"
        )
    except Exception as e:
        logger.error(f"Failed to get teams for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve project teams"
        )


@router.put("/projects/{project_id}/teams/{team_id}", response_model=ProjectTeamResponse)
async def update_project_team_access(
    project_id: UUID,
    team_id: UUID,
    team_data: ProjectTeamUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update team access level for a project."""
    try:
        project_team = await CollaborationService.update_project_team_access(
            project_id, team_id, team_data, current_user["id"]
        )
        logger.info(f"Updated team {team_id} access for project {project_id}")
        return project_team
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project team relationship not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update team access"
        )
    except Exception as e:
        logger.error(f"Failed to update team access for project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update team access"
        )


@router.delete("/projects/{project_id}/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_from_project(
    project_id: UUID,
    team_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Remove team access from a project."""
    try:
        await CollaborationService.remove_team_from_project(
            project_id, team_id, current_user["id"]
        )
        logger.info(f"Removed team {team_id} from project {project_id}")
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project team relationship not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to remove team access"
        )
    except Exception as e:
        logger.error(f"Failed to remove team from project {project_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove team from project"
        )


@router.get("/teams/{team_id}/accessible-projects")
async def get_team_accessible_projects(
    team_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get all projects accessible to a team."""
    try:
        projects = await CollaborationService.get_team_accessible_projects(
            team_id, current_user["id"]
        )
        return projects
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or access denied"
        )
    except Exception as e:
        logger.error(f"Failed to get accessible projects for team {team_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve accessible projects"
        )


# ENHANCED TEAM COLLABORATION ENDPOINTS

@router.get("/teams/{team_id}/activity")
async def get_team_activity_feed(
    team_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get recent team activity feed for collaboration tracking."""
    try:
        activities = await team_collaboration_service.get_team_activity_feed(
            team_id=team_id,
            user_id=current_user["id"],
            limit=limit,
            auth_token=current_user.get("token")
        )
        
        # Log access to activity feed
        await team_audit_service.log_team_audit_event(
            event_type=AuditEventType.RESOURCE_ACCESSED,
            team_id=team_id,
            user_id=current_user["id"],
            severity=AuditSeverity.LOW,
            details={
                "resource_type": "activity_feed",
                "activities_retrieved": len(activities),
                "limit": limit
            },
            auth_token=current_user.get("token")
        )
        
        from datetime import datetime
        return {
            "team_id": str(team_id),
            "activities": activities,
            "limit": limit,
            "retrieved_at": datetime.utcnow().isoformat()
        }
        
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient team permissions to view activity feed"
        )
    except Exception as e:
        logger.error(f"Failed to get team activity feed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve team activity feed"
        )


@router.get("/health")
async def collaboration_health_check():
    """Health check endpoint for collaboration services."""
    try:
        from datetime import datetime
        return {
            "status": "healthy",
            "service": "team_collaboration",
            "features": [
                "team_generations",
                "resource_sharing", 
                "activity_tracking",
                "audit_trails",
                "performance_metrics"
            ],
            "services_loaded": {
                "team_collaboration_service": "loaded",
                "team_audit_service": "loaded"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Collaboration health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Collaboration services unavailable"
        )