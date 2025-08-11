"""
Projects router for CRUD operations on user projects.
Following CLAUDE.md: Router layer for API endpoints.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional
from uuid import UUID
import logging

from middleware.auth import get_current_user, get_user_supabase_client
from middleware.rate_limiting import limit
from services.project_service import ProjectService
from repositories.project_repository import ProjectRepository
from models.project import ProjectCreate, ProjectUpdate, ProjectResponse
from models.user import UserResponse

router = APIRouter(tags=["projects"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[ProjectResponse])
@router.get("", response_model=List[ProjectResponse])  # CRITICAL FIX: Add route without trailing slash
@limit("200/minute")  # List operations limit - increased to match merged functionality
async def list_projects(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    visibility: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    user_client = Depends(get_user_supabase_client)
):
    """List user's projects with optional filtering and pagination."""
    try:
        project_repo = ProjectRepository(user_client)
        project_service = ProjectService(project_repo)
        
        logger.info(f"📋 [PROJECTS] Listing projects for user {current_user.id} (skip={skip}, limit={limit}, visibility={visibility})")
        
        # Use enhanced list method with pagination and filtering
        projects = await project_service.list_user_projects(
            str(current_user.id), skip, limit, visibility  # Convert UUID to string for JSON serialization
        )
        
        logger.info(f"📋 [PROJECTS] Found {len(projects)} projects")
        
        return projects
    except ValueError as e:
        logger.warning(f"Project listing validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ [PROJECTS] Failed to list projects: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve projects"
        )


@router.post("/", response_model=ProjectResponse)
@router.post("", response_model=ProjectResponse)  # CRITICAL FIX: Add route without trailing slash
@limit("30/minute")  # Create operations limit
async def create_project(
    request: Request,
    project_data: ProjectCreate,
    current_user: UserResponse = Depends(get_current_user),
    user_client = Depends(get_user_supabase_client)
):
    """Create a new project."""
    try:
        logger.info(f"🚀 [PROJECTS] Creating project for user {current_user.id}")
        logger.info(f"🔍 [PROJECTS] Project data received: {project_data.model_dump()}")
        logger.info(f"🔍 [PROJECTS] Project name: '{project_data.name}'")
        logger.info(f"🔍 [PROJECTS] Project visibility: '{project_data.visibility}'")
        logger.info(f"🔍 [PROJECTS] Project tags: {project_data.tags}")
        logger.info(f"🔍 [PROJECTS] Project metadata: {project_data.metadata}")
        
        # Create authenticated repository and service for this request
        project_repository = ProjectRepository(user_client)
        project_service = ProjectService(project_repository)
        project = await project_service.create_project(str(current_user.id), project_data)  # Convert UUID to string for JSON serialization
        
        logger.info(f"✅ [PROJECTS] Created project {str(project.id)} for user {str(current_user.id)}")
        return project
        
    except ValueError as e:
        logger.error(f"❌ [PROJECTS] Project creation validation error: {str(e)}")
        logger.error(f"❌ [PROJECTS] User ID: {current_user.id}")
        logger.error(f"❌ [PROJECTS] Project data: {project_data.model_dump() if hasattr(project_data, 'model_dump') else str(project_data)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ [PROJECTS] Project creation failed: {str(e)}")
        logger.error(f"❌ [PROJECTS] Exception type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [PROJECTS] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail="Failed to create project")


@router.get("/{project_id}", response_model=ProjectResponse)
@limit("60/minute")  # Read operations limit
async def get_project(
    project_id: UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    user_client = Depends(get_user_supabase_client)
):
    """Get project by ID."""
    try:
        # Create authenticated repository and service for this request
        project_repository = ProjectRepository(user_client)
        project_service = ProjectService(project_repository)
        project = await project_service.get_project(project_id, str(current_user.id))  # Convert UUID to string for JSON serialization
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        return project
        
    except ValueError as e:
        logger.warning(f"Project retrieval error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Project retrieval failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get project")


# REMOVED: Duplicate route definition - merged functionality into primary list_projects function above


@router.put("/{project_id}", response_model=ProjectResponse)
@limit("50/minute")  # Update operations limit
async def update_project(
    project_id: UUID,
    project_data: ProjectUpdate,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    user_client = Depends(get_user_supabase_client)
):
    """Update project details."""
    try:
        # Create authenticated repository and service for this request
        project_repository = ProjectRepository(user_client)
        project_service = ProjectService(project_repository)
        project = await project_service.update_project(project_id, str(current_user.id), project_data)  # Convert UUID to string for JSON serialization
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found or no permission")
        
        logger.info(f"Updated project {str(project_id)} by user {str(current_user.id)}")
        return project
        
    except ValueError as e:
        logger.warning(f"Project update validation error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Project update failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update project")


@router.delete("/{project_id}")
@limit("20/minute")  # Delete operations limit
async def delete_project(
    project_id: UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    user_client = Depends(get_user_supabase_client)
):
    """Delete a project."""
    try:
        # Create authenticated repository and service for this request
        project_repository = ProjectRepository(user_client)
        project_service = ProjectService(project_repository)
        success = await project_service.delete_project(project_id, str(current_user.id))  # Convert UUID to string for JSON serialization
        
        if not success:
            raise HTTPException(status_code=404, detail="Project not found or no permission")
        
        logger.info(f"Deleted project {str(project_id)} by user {str(current_user.id)}")
        return {"message": "Project deleted successfully"}
        
    except ValueError as e:
        logger.warning(f"Project deletion error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Project deletion failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to delete project")


@router.get("/{project_id}/stats")
@limit("60/minute")  # Stats operations limit
async def get_project_stats(
    project_id: UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    user_client = Depends(get_user_supabase_client)
):
    """Get project statistics."""
    try:
        # Create authenticated repository and service for this request
        project_repository = ProjectRepository(user_client)
        project_service = ProjectService(project_repository)
        stats = await project_service.get_project_stats(project_id, str(current_user.id))  # Convert UUID to string for JSON serialization
        
        return stats
        
    except ValueError as e:
        logger.warning(f"Project stats error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Project stats failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to get project statistics")