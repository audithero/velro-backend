"""
Project model schemas for project management.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class ProjectVisibility(str, Enum):
    """Project visibility enum."""
    PRIVATE = "private"
    TEAM_ONLY = "team-only"
    PUBLIC = "public"


class ProjectBase(BaseModel):
    """Base project model."""
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    visibility: ProjectVisibility = ProjectVisibility.PRIVATE
    tags: List[str] = []
    metadata: Dict[str, Any] = {}


class ProjectCreate(ProjectBase):
    """Project creation model."""
    pass


class ProjectUpdate(BaseModel):
    """Project update model."""
    name: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    visibility: Optional[ProjectVisibility] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ProjectResponse(ProjectBase):
    """Project response model.""" 
    id: UUID
    user_id: UUID
    generation_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class ProjectListResponse(BaseModel):
    """Paginated project list response."""
    items: List[ProjectResponse]
    total: int
    page: int
    per_page: int
    pages: int