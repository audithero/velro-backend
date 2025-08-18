"""
Team collaboration models for multi-user project support.
Following CLAUDE.md: Type safety, validation, security-first design.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum


class TeamRole(str, Enum):
    """Team member role enum."""
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class CollaborationType(str, Enum):
    """Generation collaboration type enum."""
    ORIGINAL = "original"
    IMPROVE = "improve"
    ITERATE = "iterate"
    FORK = "fork"
    REMIX = "remix"


class ProjectAccessLevel(str, Enum):
    """Project access level enum."""
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class InvitationStatus(str, Enum):
    """Team invitation status enum."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class TeamBase(BaseModel):
    """Base team model."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    max_members: int = Field(default=10, ge=1, le=100)
    metadata: Dict[str, Any] = {}


class TeamCreate(TeamBase):
    """Team creation model."""
    pass


class TeamUpdate(BaseModel):
    """Team update model."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    max_members: Optional[int] = Field(None, ge=1, le=100)
    metadata: Optional[Dict[str, Any]] = None


class TeamResponse(TeamBase):
    """Team response model."""
    id: UUID
    owner_id: UUID
    team_code: str
    is_active: bool = True
    member_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class TeamMemberBase(BaseModel):
    """Base team member model."""
    role: TeamRole = TeamRole.VIEWER


class TeamMemberCreate(TeamMemberBase):
    """Team member creation model (internal use)."""
    team_id: UUID
    user_id: UUID
    invited_by: Optional[UUID] = None


class TeamMemberUpdate(BaseModel):
    """Team member update model."""
    role: Optional[TeamRole] = None
    is_active: Optional[bool] = None


class UserProfile(BaseModel):
    """Minimal user profile for team member responses."""
    id: UUID
    email: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str
        }
    }


class TeamMemberResponse(TeamMemberBase):
    """Team member response model."""
    id: UUID
    team_id: UUID
    user: UserProfile
    invited_by: Optional[UUID] = None
    joined_at: datetime
    is_active: bool = True

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class TeamInvitationCreate(BaseModel):
    """Team invitation creation model."""
    invited_email: str = Field(..., pattern=r'^[^@]+@[^@]+\.[^@]+$')
    role: TeamRole = TeamRole.VIEWER

    @validator('role')
    def validate_role(cls, v):
        if v == TeamRole.OWNER:
            raise ValueError("Cannot invite someone as owner")
        return v


class TeamInvitationResponse(BaseModel):
    """Team invitation response model."""
    id: UUID
    team_id: UUID
    team_name: str
    invited_email: str
    invited_by: UUID
    inviter_name: Optional[str] = None
    role: TeamRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class TeamInvitationAccept(BaseModel):
    """Team invitation acceptance model."""
    invitation_token: str = Field(..., min_length=36, max_length=36)


class ProjectPrivacySettingsBase(BaseModel):
    """Base project privacy settings model."""
    allow_team_access: bool = False
    restrict_to_specific_teams: bool = False
    allowed_team_ids: List[UUID] = []
    hide_from_other_teams: bool = True
    allow_generation_attribution: bool = True
    allow_generation_improvements: bool = True


class ProjectPrivacySettingsUpdate(ProjectPrivacySettingsBase):
    """Project privacy settings update model."""
    pass


class ProjectPrivacySettingsResponse(ProjectPrivacySettingsBase):
    """Project privacy settings response model."""
    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class ProjectTeamCreate(BaseModel):
    """Project team relationship creation model."""
    team_id: UUID
    access_level: ProjectAccessLevel = ProjectAccessLevel.READ


class ProjectTeamUpdate(BaseModel):
    """Project team relationship update model."""
    access_level: ProjectAccessLevel


class ProjectTeamResponse(BaseModel):
    """Project team relationship response model."""
    id: UUID
    project_id: UUID
    team: TeamResponse
    access_level: ProjectAccessLevel
    granted_by: UUID
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class GenerationCollaborationCreate(BaseModel):
    """Generation collaboration creation model."""
    team_id: UUID
    collaboration_type: CollaborationType
    parent_generation_id: Optional[UUID] = None
    change_description: Optional[str] = Field(None, max_length=1000)
    attribution_visible: bool = True


class GenerationCollaborationResponse(BaseModel):
    """Generation collaboration response model."""
    id: UUID
    generation_id: UUID
    team: TeamResponse
    contributor: UserProfile
    collaboration_type: CollaborationType
    parent_generation_id: Optional[UUID] = None
    change_description: Optional[str] = None
    attribution_visible: bool = True
    created_at: datetime

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class EnhancedGenerationRequest(BaseModel):
    """Enhanced generation request with team collaboration support."""
    prompt: str = Field(..., max_length=2000)
    project_id: UUID
    model_id: str
    style_stack_id: Optional[UUID] = None
    negative_prompt: Optional[str] = Field(None, max_length=1000)
    reference_image_url: Optional[str] = None
    parameters: Dict[str, Any] = {}
    
    # Team collaboration fields
    parent_generation_id: Optional[UUID] = None
    team_context_id: Optional[UUID] = None
    collaboration_intent: Optional[CollaborationType] = None
    change_description: Optional[str] = Field(None, max_length=1000)


class TeamListResponse(BaseModel):
    """Paginated team list response."""
    items: List[TeamResponse]
    total: int
    page: int
    per_page: int
    pages: int


class TeamMemberListResponse(BaseModel):
    """Team member list response."""
    items: List[TeamMemberResponse]
    total: int


class TeamStatistics(BaseModel):
    """Team statistics model."""
    total_members: int
    total_projects: int
    total_generations: int
    recent_activity: int
    roles_breakdown: Dict[str, int]

    model_config = {
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None
        }
    }