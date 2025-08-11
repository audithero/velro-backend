"""
Authorization Models and Type System
Complete enterprise-grade authorization models with OWASP A01 compliance.
Enhanced for comprehensive access control implementation.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Set
from uuid import UUID
from datetime import datetime
from enum import Enum


class SecurityLevel(str, Enum):
    """Enterprise security levels with RBAC integration."""
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    TEAM_MEMBER = "team_member"
    ADMIN = "admin"
    OWNER = "owner"


class TeamRole(str, Enum):
    """Hierarchical team roles with permission inheritance."""
    VIEWER = "viewer"         # Read-only access (Level 1)
    CONTRIBUTOR = "contributor" # Create/edit own content (Level 2)  
    EDITOR = "editor"         # Edit all team content (Level 3)
    ADMIN = "admin"          # Team management (Level 4)
    OWNER = "owner"          # Full control (Level 5)


class ProjectVisibility(str, Enum):
    """Project visibility levels with privacy controls."""
    PRIVATE = "private"       # Owner + explicit invites only
    TEAM_RESTRICTED = "team_restricted"  # Specific teams only
    TEAM_OPEN = "team_open"   # All team members
    PUBLIC_READ = "public_read"  # Authenticated users (read)
    PUBLIC_FULL = "public_full"  # Public access (legacy)


class AccessType(str, Enum):
    """Resource access operation types."""
    READ = "read"
    WRITE = "write" 
    DELETE = "delete"
    SHARE = "share"
    ADMIN = "admin"


class AuthorizationMethod(str, Enum):
    """Authorization path tracking for audit purposes."""
    DIRECT_OWNERSHIP = "direct_ownership"
    PROJECT_OWNERSHIP = "project_ownership"
    TEAM_MEMBERSHIP = "team_membership"
    PROJECT_COLLABORATION = "project_collaboration"
    GENERATION_INHERITANCE = "generation_inheritance"
    PUBLIC_ACCESS = "public_access"
    EMERGENCY_ACCESS = "emergency_access"


class ValidationContext(str, Enum):
    """UUID validation context types for security."""
    USER_PROFILE = "user_profile"
    GENERATION_ACCESS = "generation_access"
    PROJECT_ACCESS = "project_access"
    TEAM_ACCESS = "team_access"
    MEDIA_URL = "media_url"
    ADMIN_OPERATION = "admin_operation"


@dataclass
class AuthorizationResult:
    """Base authorization result with comprehensive context."""
    granted: bool
    access_method: Optional[AuthorizationMethod] = None
    can_view: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_download: bool = False
    can_share: bool = False
    denial_reason: Optional[str] = None
    security_flags: List[str] = field(default_factory=list)
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class GenerationPermissions:
    """Comprehensive permission set for generation access."""
    generation_id: UUID
    user_id: UUID
    granted: bool
    access_method: AuthorizationMethod
    can_view: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_download: bool = False
    can_share: bool = False
    can_create_child: bool = False
    team_context: Optional[UUID] = None
    project_context: Optional[UUID] = None
    security_level: SecurityLevel = SecurityLevel.AUTHENTICATED
    expires_at: Optional[datetime] = None
    media_urls: List[str] = field(default_factory=list)
    rate_limit_remaining: int = 0
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)


@dataclass 
class TeamAccessResult:
    """Team access validation result with comprehensive context."""
    granted: bool
    role: Optional[TeamRole] = None
    access_method: Optional[AuthorizationMethod] = None
    team_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    collaboration_type: Optional[str] = None
    inheritance_depth: Optional[int] = None
    parent_generation_id: Optional[UUID] = None
    denial_reason: Optional[str] = None
    checked_methods: List[str] = field(default_factory=list)
    security_flags: List[str] = field(default_factory=list)
    expires_at: Optional[datetime] = None


@dataclass
class SecurityContext:
    """Complete security context for authorization operations."""
    user_id: UUID
    session_id: str
    client_ip: str
    user_agent: str
    jwt_payload: Dict[str, Any]
    team_memberships: List[UUID] = field(default_factory=list)
    security_level: SecurityLevel = SecurityLevel.AUTHENTICATED
    rate_limit_remaining: int = 100
    last_activity: datetime = field(default_factory=datetime.utcnow)
    security_violations: List[str] = field(default_factory=list)
    audit_session_id: Optional[str] = None


@dataclass
class ProjectPermissions:
    """Project-level permission set."""
    project_id: UUID
    user_id: UUID
    granted: bool
    access_method: AuthorizationMethod
    can_view: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_manage_teams: bool = False
    can_invite_members: bool = False
    visibility: ProjectVisibility = ProjectVisibility.PRIVATE
    team_roles: List[TeamRole] = field(default_factory=list)
    expires_at: Optional[datetime] = None


@dataclass
class InheritedAccessResult:
    """Result for inheritance-based access validation."""
    granted: bool
    final_generation_id: Optional[UUID] = None
    inheritance_chain: List[UUID] = field(default_factory=list)
    access_method: Optional[AuthorizationMethod] = None
    depth: int = 0
    max_depth_reached: bool = False
    security_violations: List[str] = field(default_factory=list)


@dataclass
class GenerationTransferResult:
    """Result for generation transfer between projects."""
    success: bool
    new_project_id: Optional[UUID] = None
    transferred_files: int = 0
    preserved_contexts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# Additional models for OWASP A01 compliance

class ResourceType(str, Enum):
    """Types of resources that can be access-controlled."""
    USER_PROFILE = "user_profile"
    GENERATION = "generation"
    PROJECT = "project"
    TEAM = "team"
    ADMIN_RESOURCE = "admin_resource"
    SYSTEM_RESOURCE = "system_resource"

class AccessLevel(str, Enum):
    """Access levels for resources."""
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    OWNER = "owner"

class Permission(str, Enum):
    """Granular permissions for RBAC."""
    VIEW = "view"
    CREATE = "create"
    EDIT = "edit"
    DELETE = "delete"
    SHARE = "share"
    DOWNLOAD = "download"
    MANAGE_USERS = "manage_users"
    MANAGE_TEAMS = "manage_teams"
    ADMIN_PANEL = "admin_panel"
    SYSTEM_CONFIG = "system_config"

@dataclass
class AuthorizationContext:
    """Complete authorization context for access control middleware."""
    user_id: Optional[UUID]
    user_role: str
    resource_type: Optional[ResourceType]
    resource_owner: Optional[str]
    access_level: Any  # AccessControlLevel from middleware
    granted_permissions: Set[Any]  # Set of Permission enums
    client_ip: Optional[str] = None
    session_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class ResourceOwnership:
    """Resource ownership validation result."""
    is_owner: bool
    resource_id: Optional[str] = None
    owner_id: Optional[str] = None
    access_via: Optional[str] = None  # e.g., "direct", "project_collaboration"
    access_role: Optional[str] = None
    reason: Optional[str] = None
    validated_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class AccessControlResult:
    """Result of access control validation."""
    granted: bool
    access_level: Optional[Any] = None  # AccessControlLevel
    context: Optional[AuthorizationContext] = None
    permissions: Optional[Set[Any]] = None
    denial_reason: Optional[str] = None
    security_flags: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

@dataclass
class PrivilegeEscalationCheck:
    """Result of privilege escalation detection."""
    is_escalation_attempt: bool
    indicators: List[str] = field(default_factory=list)
    risk_score: int = 0
    recommended_action: Optional[str] = None
    additional_monitoring: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)

# Exception Classes for Authorization
class VelroAuthorizationError(Exception):
    """Base authorization exception with comprehensive context."""
    
    def __init__(self, 
                 message: str, 
                 error_code: str, 
                 context: Dict[str, Any],
                 user_id: Optional[UUID] = None,
                 resource_id: Optional[UUID] = None,
                 severity: str = "ERROR"):
        self.message = message
        self.error_code = error_code
        self.context = context
        self.user_id = user_id
        self.resource_id = resource_id
        self.severity = severity
        self.timestamp = datetime.utcnow()
        super().__init__(self.message)


class GenerationAccessDeniedError(VelroAuthorizationError):
    """HTTP 403 generation access error with detailed diagnostics."""
    
    def __init__(self, generation_id: UUID, user_id: UUID, reason: str, 
                 authorization_attempts: List[str] = None):
        super().__init__(
            message=f"Access denied to generation {generation_id}",
            error_code="GENERATION_ACCESS_DENIED_403",
            context={
                "generation_id": str(generation_id),
                "user_id": str(user_id),
                "denial_reason": reason,
                "authorization_attempts": authorization_attempts or [],
                "suggested_actions": self._get_suggested_actions(reason)
            },
            user_id=user_id,
            resource_id=generation_id,
            severity="WARNING"
        )
    
    def _get_suggested_actions(self, reason: str) -> List[str]:
        """Provide actionable suggestions based on denial reason."""
        suggestions = {
            "resource_not_found": [
                "Verify the generation ID is correct",
                "Check if the generation has been deleted",
                "Ensure you have access to the parent project"
            ],
            "insufficient_team_permissions": [
                "Request team membership from project owner",
                "Ask team admin to upgrade your role",
                "Verify you're logged into the correct account"
            ],
            "project_visibility_restricted": [
                "Request project access from the owner",
                "Check if project visibility has changed",
                "Verify your team membership status"
            ],
            "rate_limit_exceeded": [
                "Wait before retrying the request",
                "Contact support if rate limits seem incorrect",
                "Consider upgrading your plan for higher limits"
            ]
        }
        return suggestions.get(reason, ["Contact support with the trace ID above"])


class SecurityViolationError(VelroAuthorizationError):
    """Critical security violation requiring immediate attention."""
    
    def __init__(self, violation_type: str, details: Dict[str, Any],
                 user_id: Optional[UUID] = None, client_ip: str = None):
        super().__init__(
            message=f"Security violation detected: {violation_type}",
            error_code="SECURITY_VIOLATION_CRITICAL",
            context={
                "violation_type": violation_type,
                "details": details,
                "client_ip": client_ip,
                "requires_investigation": True,
                "auto_blocked": True,
                "escalation_level": "CRITICAL"
            },
            user_id=user_id,
            severity="CRITICAL"
        )


class GenerationNotFoundError(VelroAuthorizationError):
    """Generation not found error."""
    
    def __init__(self, generation_id: UUID):
        super().__init__(
            message=f"Generation {generation_id} not found",
            error_code="GENERATION_NOT_FOUND_404",
            context={"generation_id": str(generation_id)},
            resource_id=generation_id,
            severity="WARNING"
        )


# Utility Functions
def has_sufficient_role(current_role: TeamRole, required_role: TeamRole) -> bool:
    """Check if current role has sufficient permissions for required role."""
    role_hierarchy = {
        TeamRole.VIEWER: 1,
        TeamRole.CONTRIBUTOR: 2,
        TeamRole.EDITOR: 3,
        TeamRole.ADMIN: 4,
        TeamRole.OWNER: 5
    }
    
    return role_hierarchy.get(current_role, 0) >= role_hierarchy.get(required_role, 0)


def get_role_permissions(role: TeamRole) -> AuthorizationResult:
    """Get permission set for a team role."""
    permissions_map = {
        TeamRole.VIEWER: AuthorizationResult(
            granted=True, can_view=True
        ),
        TeamRole.CONTRIBUTOR: AuthorizationResult(
            granted=True, can_view=True, can_edit=True, can_download=True
        ),
        TeamRole.EDITOR: AuthorizationResult(
            granted=True, can_view=True, can_edit=True, can_delete=True, 
            can_download=True, can_share=True
        ),
        TeamRole.ADMIN: AuthorizationResult(
            granted=True, can_view=True, can_edit=True, can_delete=True, 
            can_download=True, can_share=True
        ),
        TeamRole.OWNER: AuthorizationResult(
            granted=True, can_view=True, can_edit=True, can_delete=True, 
            can_download=True, can_share=True
        )
    }
    
    return permissions_map.get(role, AuthorizationResult(granted=False))