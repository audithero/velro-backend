"""
Team collaboration service for multi-user project management.
Following CLAUDE.md: Security-first, RLS-aware, performant queries.
"""
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta

from database import get_database, SupabaseClient
from models.team import (
    TeamCreate, TeamUpdate, TeamResponse, TeamMemberCreate, TeamMemberUpdate,
    TeamMemberResponse, TeamInvitationCreate, TeamInvitationResponse,
    TeamInvitationAccept, ProjectPrivacySettingsUpdate, ProjectPrivacySettingsResponse,
    ProjectTeamCreate, ProjectTeamUpdate, ProjectTeamResponse,
    GenerationCollaborationCreate, GenerationCollaborationResponse,
    TeamRole, InvitationStatus, TeamStatistics, UserProfile
)
from models.authorization import (
    TeamAccessResult, AuthorizationMethod, ValidationContext, 
    has_sufficient_role, get_role_permissions
)
from utils.enhanced_uuid_utils import EnhancedUUIDUtils, secure_uuid_validator
from utils.exceptions import NotFoundError, ConflictError, ForbiddenError
from utils.pagination import PaginationParams
import logging

logger = logging.getLogger(__name__)


class TeamService:
    """Team collaboration service with security and RLS support."""
    
    @staticmethod
    async def create_team(
        team_data: TeamCreate, 
        owner_id: UUID,
        auth_token: str = None
    ) -> TeamResponse:
        """Create a new team with owner as first member."""
        db = await get_database()
        
        try:
            # Generate unique team code
            team_code = f"TM-{str(uuid4())[:6].upper()}"
            
            # Create team record
            team_record = {
                "name": team_data.name,
                "description": team_data.description,
                "owner_id": str(owner_id),
                "team_code": team_code,
                "max_members": team_data.max_members,
                "metadata": team_data.metadata,
                "is_active": True,
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }
            
            # Create team
            created_team = db.execute_query(
                table="teams",
                operation="insert",
                data=team_record,
                single=True,
                auth_token=auth_token,
                user_id=str(owner_id)
            )
            
            # Owner should be automatically added via trigger, but verify
            member_check = db.execute_query(
                table="team_members",
                operation="select",
                filters={
                    "team_id": created_team["id"],
                    "user_id": str(owner_id),
                    "role": TeamRole.OWNER.value
                },
                single=True,
                auth_token=auth_token,
                user_id=str(owner_id)
            )
            
            if not member_check:
                # Fallback: manually add owner if trigger failed
                member_record = {
                    "team_id": created_team["id"],
                    "user_id": str(owner_id),
                    "role": TeamRole.OWNER.value,
                    "joined_at": datetime.utcnow().isoformat(),
                    "is_active": True
                }
                
                db.execute_query(
                    table="team_members",
                    operation="insert",
                    data=member_record,
                    auth_token=auth_token,
                    user_id=str(owner_id)
                )
            
            logger.info(f"Created team {created_team['id']} with owner {owner_id}")
            
            return TeamResponse(
                id=UUID(created_team["id"]),
                name=created_team["name"],
                description=created_team["description"],
                owner_id=UUID(created_team["owner_id"]),
                team_code=created_team["team_code"],
                is_active=created_team["is_active"],
                max_members=created_team["max_members"],
                metadata=created_team["metadata"],
                member_count=1,
                created_at=datetime.fromisoformat(created_team["created_at"]),
                updated_at=datetime.fromisoformat(created_team["updated_at"])
            )
            
        except Exception as e:
            logger.error(f"Failed to create team: {e}")
            raise
    
    @staticmethod
    async def get_user_teams(
        user_id: UUID,
        pagination: PaginationParams,
        auth_token: str = None
    ) -> Tuple[List[TeamResponse], int]:
        """Get teams for a user with member count."""
        # Performance optimization: Use cache for frequently accessed user teams
        try:
            from utils.cache_manager import get_cache_manager
            cache_manager = get_cache_manager()
            cache_key = f"user_teams:{user_id}:{pagination.offset}:{pagination.limit}"
            
            # Try cache first (30 second TTL for active data)
            cached_result = await cache_manager.get(cache_key)
            if cached_result:
                logger.info(f"🚀 [CACHE-HIT] User teams for {user_id}")
                return cached_result['teams'], cached_result['total']
        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
        
        db = await get_database()
        
        try:
            # Get user's team memberships
            user_memberships = db.execute_query(
                table="team_members",
                operation="select",
                filters={
                    "user_id": str(user_id),
                    "is_active": True
                },
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not user_memberships:
                return [], 0
            
            team_ids = [member["team_id"] for member in user_memberships]
            
            # Get teams with basic info
            all_teams = []
            total_count = 0
            
            for team_id in team_ids:
                team = db.execute_query(
                    table="teams",
                    operation="select",
                    filters={
                        "id": team_id,
                        "is_active": True
                    },
                    single=True,
                    auth_token=auth_token,
                    user_id=str(user_id)
                )
                
                if team:
                    # Get member count for this team
                    members = db.execute_query(
                        table="team_members",
                        operation="select",
                        filters={
                            "team_id": team_id,
                            "is_active": True
                        },
                        auth_token=auth_token,
                        user_id=str(user_id)
                    )
                    
                    team_response = TeamResponse(
                        id=UUID(team["id"]),
                        name=team["name"],
                        description=team["description"],
                        owner_id=UUID(team["owner_id"]),
                        team_code=team["team_code"],
                        is_active=team["is_active"],
                        max_members=team["max_members"],
                        metadata=team["metadata"],
                        member_count=len(members) if members else 0,
                        created_at=datetime.fromisoformat(team["created_at"]),
                        updated_at=datetime.fromisoformat(team["updated_at"])
                    )
                    all_teams.append(team_response)
            
            # Sort by creation date (newest first)
            all_teams.sort(key=lambda x: x.created_at, reverse=True)
            total_count = len(all_teams)
            
            # Apply pagination
            start_idx = pagination.offset
            end_idx = start_idx + pagination.limit
            paginated_teams = all_teams[start_idx:end_idx]
            
            # Cache the result for performance (30 seconds)
            try:
                result_data = {'teams': paginated_teams, 'total': total_count}
                await cache_manager.set(cache_key, result_data, ttl=30)
            except Exception as e:
                logger.warning(f"Failed to cache result: {e}")
            
            return paginated_teams, total_count
            
        except Exception as e:
            logger.error(f"Failed to get user teams: {e}")
            raise
    
    @staticmethod
    async def get_team(team_id: UUID, user_id: UUID, auth_token: str = None) -> TeamResponse:
        """Get team details if user has access."""
        db = await get_database()
        
        try:
            # Verify user is a member of the team
            membership = db.execute_query(
                table="team_members",
                operation="select",
                filters={
                    "team_id": str(team_id),
                    "user_id": str(user_id),
                    "is_active": True
                },
                single=True,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not membership:
                raise NotFoundError("Team not found or access denied")
            
            # Get team details
            team = db.execute_query(
                table="teams",
                operation="select",
                filters={
                    "id": str(team_id),
                    "is_active": True
                },
                single=True,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not team:
                raise NotFoundError("Team not found")
            
            # Get member count
            members = db.execute_query(
                table="team_members",
                operation="select",
                filters={
                    "team_id": str(team_id),
                    "is_active": True
                },
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            return TeamResponse(
                id=UUID(team["id"]),
                name=team["name"],
                description=team["description"],
                owner_id=UUID(team["owner_id"]),
                team_code=team["team_code"],
                is_active=team["is_active"],
                max_members=team["max_members"],
                metadata=team["metadata"],
                member_count=len(members) if members else 0,
                created_at=datetime.fromisoformat(team["created_at"]),
                updated_at=datetime.fromisoformat(team["updated_at"])
            )
            
        except Exception as e:
            logger.error(f"Failed to get team {team_id}: {e}")
            raise
    
    @staticmethod
    async def invite_user(
        team_id: UUID,
        inviter_id: UUID,
        invitation_data: TeamInvitationCreate,
        db = None
    ) -> TeamInvitationResponse:
        """Invite a user to join a team."""
        if db is None:
            db = await get_async_session()
        
        # Verify inviter has admin access
        inviter_role = await TeamService._get_user_role(team_id, inviter_id, db)
        if inviter_role not in [TeamRole.OWNER, TeamRole.ADMIN]:
            raise ForbiddenError("Insufficient permissions to invite users")
        
        # Check if user is already a member or invited
        existing = await db.execute(
            select(team_members_table.c.id).where(
                and_(
                    team_members_table.c.team_id == team_id,
                    team_members_table.c.user_id.in_(
                        select(users_table.c.id).where(
                            users_table.c.email == invitation_data.invited_email
                        )
                    ),
                    team_members_table.c.is_active == True
                )
            )
        )
        
        if existing.fetchone():
            raise ConflictError("User is already a team member")
        
        # Check for existing pending invitation
        existing_invite = await db.execute(
            select(team_invitations_table).where(
                and_(
                    team_invitations_table.c.team_id == team_id,
                    team_invitations_table.c.invited_email == invitation_data.invited_email,
                    team_invitations_table.c.status == InvitationStatus.PENDING,
                    team_invitations_table.c.expires_at > datetime.utcnow()
                )
            )
        )
        
        if existing_invite.fetchone():
            raise ConflictError("User already has a pending invitation")
        
        # Create invitation
        invitation_token = str(uuid4())
        expires_at = datetime.utcnow() + timedelta(days=7)
        
        result = await db.execute(
            insert(team_invitations_table).values(
                team_id=team_id,
                invited_email=invitation_data.invited_email,
                invited_by=inviter_id,
                role=invitation_data.role,
                invitation_token=invitation_token,
                expires_at=expires_at
            ).returning(team_invitations_table)
        )
        
        invitation = result.fetchone()
        
        # Get team info for response
        team_info = await db.execute(
            select(teams_table.c.name).where(teams_table.c.id == team_id)
        )
        team_name = team_info.fetchone().name
        
        # Get inviter info
        inviter_info = await db.execute(
            select(users_table.c.full_name).where(users_table.c.id == inviter_id)
        )
        inviter_name = inviter_info.fetchone().full_name
        
        await db.commit()
        
        logger.info(f"Created invitation {invitation.id} for {invitation_data.invited_email} to team {team_id}")
        
        return TeamInvitationResponse(
            id=invitation.id,
            team_id=invitation.team_id,
            team_name=team_name,
            invited_email=invitation.invited_email,
            invited_by=invitation.invited_by,
            inviter_name=inviter_name,
            role=invitation.role,
            status=invitation.status,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at
        )
    
    @staticmethod
    async def accept_invitation(
        user_id: UUID,
        token: str,
        db = None
    ) -> TeamMemberResponse:
        """Accept a team invitation and join the team."""
        if db is None:
            db = await get_async_session()
        
        # Get and validate invitation
        invitation_result = await db.execute(
            select(team_invitations_table).where(
                and_(
                    team_invitations_table.c.invitation_token == token,
                    team_invitations_table.c.status == InvitationStatus.PENDING,
                    team_invitations_table.c.expires_at > datetime.utcnow()
                )
            )
        )
        
        invitation = invitation_result.fetchone()
        if not invitation:
            raise NotFoundError("Invalid or expired invitation")
        
        # Verify user email matches invitation
        user_result = await db.execute(
            select(users_table.c.email).where(users_table.c.id == user_id)
        )
        user_email = user_result.fetchone().email
        
        if user_email.lower() != invitation.invited_email.lower():
            raise ForbiddenError("Invitation email does not match user account")
        
        # Check team capacity
        member_count = await db.execute(
            select(func.count()).where(
                and_(
                    team_members_table.c.team_id == invitation.team_id,
                    team_members_table.c.is_active == True
                )
            )
        )
        current_count = member_count.scalar()
        
        team_info = await db.execute(
            select(teams_table.c.max_members).where(teams_table.c.id == invitation.team_id)
        )
        max_members = team_info.fetchone().max_members
        
        if current_count >= max_members:
            raise ConflictError("Team is at maximum capacity")
        
        # Add user as team member
        member_result = await db.execute(
            insert(team_members_table).values(
                team_id=invitation.team_id,
                user_id=user_id,
                role=invitation.role,
                invited_by=invitation.invited_by,
                joined_at=datetime.utcnow()
            ).returning(team_members_table)
        )
        
        member = member_result.fetchone()
        
        # Mark invitation as accepted
        await db.execute(
            update(team_invitations_table).where(
                team_invitations_table.c.id == invitation.id
            ).values(
                status=InvitationStatus.ACCEPTED,
                updated_at=datetime.utcnow()
            )
        )
        
        await db.commit()
        
        # Get user profile for response
        user_profile = await TeamService._get_user_profile(user_id, db)
        
        logger.info(f"User {user_id} joined team {invitation.team_id} via invitation {invitation.id}")
        
        return TeamMemberResponse(
            id=member.id,
            team_id=member.team_id,
            user=user_profile,
            role=member.role,
            invited_by=member.invited_by,
            joined_at=member.joined_at,
            is_active=member.is_active
        )
    
    @staticmethod
    async def _get_user_role(team_id: UUID, user_id: UUID, auth_token: str = None) -> Optional[TeamRole]:
        """Get user's role in a team."""
        db = await get_database()
        
        try:
            membership = db.execute_query(
                table="team_members",
                operation="select",
                filters={
                    "team_id": str(team_id),
                    "user_id": str(user_id),
                    "is_active": True
                },
                single=True,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            return TeamRole(membership["role"]) if membership else None
            
        except Exception as e:
            logger.error(f"Failed to get user role: {e}")
            return None
    
    @staticmethod
    async def _get_user_profile(user_id: UUID, auth_token: str = None) -> UserProfile:
        """Get user profile for team member responses."""
        db = await get_database()
        
        try:
            user = db.execute_query(
                table="users",
                operation="select",
                filters={"id": str(user_id)},
                single=True,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not user:
                raise NotFoundError("User not found")
            
            return UserProfile(
                id=UUID(user["id"]),
                email=user["email"],
                full_name=user.get("full_name"),
                avatar_url=user.get("avatar_url")
            )
            
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            raise
    
    @staticmethod
    async def get_team_statistics(
        team_id: UUID,
        user_id: UUID,
        db = None
    ) -> TeamStatistics:
        """Get team statistics and metrics."""
        if db is None:
            db = await get_async_session()
        
        # Verify access
        await TeamService.get_team(team_id, user_id, db)
        
        # Get member statistics
        members_result = await db.execute(
            select(
                func.count().label('total_members'),
                team_members_table.c.role
            ).where(
                and_(
                    team_members_table.c.team_id == team_id,
                    team_members_table.c.is_active == True
                )
            ).group_by(team_members_table.c.role)
        )
        
        total_members = 0
        roles_breakdown = {}
        
        for member in members_result:
            total_members += member.total_members
            roles_breakdown[member.role] = member.total_members
        
        # Get project count for team
        projects_result = await db.execute(
            select(func.count()).where(
                project_teams_table.c.team_id == team_id
            )
        )
        total_projects = projects_result.scalar()
        
        # Get generation count from team projects
        generations_result = await db.execute(
            select(func.count()).where(
                generations_table.c.team_context_id == team_id
            )
        )
        total_generations = generations_result.scalar()
        
        # Get recent activity (last 7 days)
        recent_cutoff = datetime.utcnow() - timedelta(days=7)
        activity_result = await db.execute(
            select(func.count()).where(
                and_(
                    generations_table.c.team_context_id == team_id,
                    generations_table.c.created_at >= recent_cutoff
                )
            )
        )
        recent_activity = activity_result.scalar()
        
        return TeamStatistics(
            total_members=total_members,
            total_projects=total_projects,
            total_generations=total_generations,
            recent_activity=recent_activity,
            roles_breakdown=roles_breakdown
        )
    
    # ENHANCED ROLE-BASED ACCESS CONTROL METHODS
    
    @staticmethod
    async def validate_team_access(
        team_id: UUID,
        user_id: UUID, 
        required_role: TeamRole = TeamRole.VIEWER,
        auth_token: str = None,
        client_ip: str = None
    ) -> TeamAccessResult:
        """
        Comprehensive team access validation with security monitoring.
        """
        logger.info(f"🔐 [TEAM-ACCESS] Validating {required_role.value} access for user {user_id} on team {team_id}")
        
        # Security input validation
        validated_team_id = await secure_uuid_validator.validate_uuid_format(
            team_id, ValidationContext.TEAM_ACCESS, strict=True, client_ip=client_ip
        )
        validated_user_id = await secure_uuid_validator.validate_uuid_format(
            user_id, ValidationContext.USER_PROFILE, strict=True, client_ip=client_ip
        )
        
        if not validated_team_id or not validated_user_id:
            return TeamAccessResult(
                granted=False,
                denial_reason="invalid_uuid_format",
                checked_methods=["input_validation"]
            )
        
        try:
            db = await get_database()
            
            # Check team membership with role
            member_record = await db.execute_query(
                table="team_members",
                operation="select",
                filters={
                    "team_id": str(validated_team_id),
                    "user_id": str(validated_user_id),
                    "is_active": True
                },
                single=True,
                auth_token=auth_token,
                user_id=str(validated_user_id)
            )
            
            if not member_record:
                logger.warning(f"❌ [TEAM-ACCESS] User {user_id} not a member of team {team_id}")
                return TeamAccessResult(
                    granted=False,
                    denial_reason="not_team_member",
                    checked_methods=["team_membership"]
                )
            
            current_role = TeamRole(member_record["role"])
            
            # Check if current role has sufficient permissions
            if has_sufficient_role(current_role, required_role):
                logger.info(f"✅ [TEAM-ACCESS] Access granted - user has {current_role.value} role (required: {required_role.value})")
                return TeamAccessResult(
                    granted=True,
                    role=current_role,
                    access_method=AuthorizationMethod.TEAM_MEMBERSHIP,
                    team_id=UUID(validated_team_id),
                    checked_methods=["team_membership", "role_validation"]
                )
            else:
                logger.warning(f"❌ [TEAM-ACCESS] Insufficient role - user has {current_role.value} role (required: {required_role.value})")
                return TeamAccessResult(
                    granted=False,
                    role=current_role,
                    denial_reason="insufficient_role",
                    team_id=UUID(validated_team_id),
                    checked_methods=["team_membership", "role_validation"]
                )
                
        except Exception as e:
            logger.error(f"❌ [TEAM-ACCESS] Error validating team access: {e}")
            return TeamAccessResult(
                granted=False,
                denial_reason=f"access_validation_error: {str(e)}",
                checked_methods=["team_membership"]
            )
    
    @staticmethod
    async def handle_team_membership_change(
        team_id: UUID,
        user_id: UUID,
        old_role: Optional[TeamRole],
        new_role: Optional[TeamRole],
        auth_token: str = None
    ) -> None:
        """Handle cascading effects of team membership changes."""
        
        logger.info(f"🔄 [TEAM-CHANGE] User {user_id} role change in team {team_id}: {old_role} → {new_role}")
        
        try:
            # Audit the change for security monitoring
            EnhancedUUIDUtils.audit_uuid_access(
                team_id, ValidationContext.TEAM_ACCESS, str(user_id), success=True
            )
            
            # If user removed from team, check for orphaned resources
            if old_role is not None and new_role is None:
                await TeamService._check_and_handle_orphaned_resources(team_id, user_id, auth_token)
            
            # Update cached permissions
            await TeamService._invalidate_user_team_cache(user_id)
            
            # Notify affected projects and generations
            affected_projects = await TeamService._get_projects_by_team(team_id, auth_token)
            for project_id in affected_projects:
                await TeamService._recalculate_project_permissions(project_id, auth_token)
                
            logger.info(f"✅ [TEAM-CHANGE] Successfully handled membership change for user {user_id}")
            
        except Exception as e:
            logger.error(f"❌ [TEAM-CHANGE] Failed to handle membership change: {e}")
            raise
    
    @staticmethod
    async def validate_role_change_permission(
        team_id: UUID,
        requesting_user_id: UUID,
        target_user_id: UUID,
        new_role: TeamRole,
        auth_token: str = None
    ) -> bool:
        """Validate if user has permission to change another user's role."""
        
        # Get requester's role
        requester_access = await TeamService.validate_team_access(
            team_id, requesting_user_id, TeamRole.ADMIN, auth_token
        )
        
        if not requester_access.granted:
            logger.warning(f"❌ [ROLE-CHANGE] User {requesting_user_id} lacks admin permission for team {team_id}")
            return False
        
        # Owners can change anyone's role
        if requester_access.role == TeamRole.OWNER:
            return True
        
        # Admins can change roles but not to owner, and not other admins/owner roles
        if requester_access.role == TeamRole.ADMIN:
            if new_role == TeamRole.OWNER:
                logger.warning(f"❌ [ROLE-CHANGE] Admins cannot promote users to owner")
                return False
            
            # Check target user's current role
            target_access = await TeamService.validate_team_access(
                team_id, target_user_id, TeamRole.VIEWER, auth_token
            )
            
            if target_access.granted and target_access.role in [TeamRole.ADMIN, TeamRole.OWNER]:
                logger.warning(f"❌ [ROLE-CHANGE] Admins cannot modify other admin/owner roles")
                return False
            
            return True
        
        return False
    
    @staticmethod
    async def get_team_access_matrix(
        team_id: UUID,
        user_id: UUID,
        auth_token: str = None
    ) -> Dict[str, Any]:
        """Get comprehensive access matrix for team operations."""
        
        # Validate user has access to view team details
        team_access = await TeamService.validate_team_access(
            team_id, user_id, TeamRole.VIEWER, auth_token
        )
        
        if not team_access.granted:
            raise PermissionError("Access denied to team access matrix")
        
        user_role = team_access.role
        permissions = get_role_permissions(user_role)
        
        # Build access matrix based on role
        access_matrix = {
            "user_id": str(user_id),
            "team_id": str(team_id),
            "user_role": user_role.value,
            "permissions": {
                "can_view": permissions.can_view,
                "can_edit": permissions.can_edit,
                "can_delete": permissions.can_delete,
                "can_download": permissions.can_download,
                "can_share": permissions.can_share,
                "can_invite_members": user_role in [TeamRole.EDITOR, TeamRole.ADMIN, TeamRole.OWNER],
                "can_remove_members": user_role in [TeamRole.ADMIN, TeamRole.OWNER],
                "can_change_roles": user_role in [TeamRole.ADMIN, TeamRole.OWNER],
                "can_manage_projects": user_role in [TeamRole.ADMIN, TeamRole.OWNER],
                "can_delete_team": user_role == TeamRole.OWNER
            },
            "role_hierarchy": {
                role.value: has_sufficient_role(user_role, role) 
                for role in TeamRole
            }
        }
        
        return access_matrix
    
    # HELPER METHODS FOR TEAM ACCESS MANAGEMENT
    
    @staticmethod
    async def _check_and_handle_orphaned_resources(
        team_id: UUID, user_id: UUID, auth_token: str
    ) -> None:
        """Check for and handle resources orphaned by team membership removal."""
        
        try:
            db = await get_database()
            
            # Check for generations with this team context that user owns
            orphaned_generations = await db.execute_query(
                table="generations",
                operation="select",
                filters={
                    "team_context_id": str(team_id),
                    "user_id": str(user_id)
                },
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if orphaned_generations:
                logger.warning(f"⚠️ [ORPHANED-RESOURCES] Found {len(orphaned_generations)} orphaned generations for user {user_id}")
                # In production, decide whether to transfer ownership, mark as private, etc.
                
        except Exception as e:
            logger.error(f"❌ [ORPHANED-RESOURCES] Failed to check orphaned resources: {e}")
    
    @staticmethod
    async def _invalidate_user_team_cache(user_id: UUID) -> None:
        """Invalidate cached team permissions for user."""
        try:
            from utils.cache_manager import get_cache_manager
            cache_manager = get_cache_manager()
            
            # Invalidate user's team-related cache entries
            user_pattern = f"team:*:{user_id}:*"
            await cache_manager.invalidate_pattern(user_pattern)
            
            logger.info(f"🔄 [CACHE] Invalidated team permissions cache for user {user_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ [CACHE] Failed to invalidate team cache: {e}")
    
    @staticmethod
    async def _get_projects_by_team(team_id: UUID, auth_token: str) -> List[UUID]:
        """Get all projects associated with team."""
        try:
            db = await get_database()
            
            project_teams = await db.execute_query(
                table="project_teams",
                operation="select",
                filters={"team_id": str(team_id)},
                auth_token=auth_token
            )
            
            return [UUID(pt["project_id"]) for pt in project_teams or []]
            
        except Exception as e:
            logger.error(f"❌ [TEAM-PROJECTS] Failed to get projects for team {team_id}: {e}")
            return []
    
    @staticmethod
    async def _recalculate_project_permissions(project_id: UUID, auth_token: str) -> None:
        """Recalculate and cache project permissions after team changes."""
        try:
            # This would integrate with project service to recalculate permissions
            logger.info(f"🔄 [PROJECT-PERMS] Recalculating permissions for project {project_id}")
            
            # Invalidate project permission caches
            from utils.cache_manager import get_cache_manager
            cache_manager = get_cache_manager()
            
            project_pattern = f"project:{project_id}:*"
            await cache_manager.invalidate_pattern(project_pattern)
            
        except Exception as e:
            logger.error(f"❌ [PROJECT-PERMS] Failed to recalculate project permissions: {e}")


# ENTERPRISE TEAM MANAGEMENT ENHANCEMENTS
    
    @staticmethod
    async def update_team(
        team_id: UUID,
        team_data: 'TeamUpdate',
        user_id: UUID,
        auth_token: str = None
    ) -> 'TeamResponse':
        """Update team details (admin/owner only)."""
        # Validate user has admin access
        team_access = await TeamService.validate_team_access(
            team_id, user_id, TeamRole.ADMIN, auth_token
        )
        
        if not team_access.granted:
            raise ForbiddenError("Insufficient permissions to update team")
        
        db = await get_database()
        
        try:
            # Build update data
            update_data = {}
            if team_data.name is not None:
                update_data["name"] = team_data.name
            if team_data.description is not None:
                update_data["description"] = team_data.description
            if team_data.max_members is not None:
                update_data["max_members"] = team_data.max_members
            if team_data.metadata is not None:
                update_data["metadata"] = team_data.metadata
            
            update_data["updated_at"] = datetime.utcnow().isoformat()
            
            # Update team
            updated_team = db.execute_query(
                table="teams",
                operation="update",
                filters={"id": str(team_id)},
                data=update_data,
                single=True,
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not updated_team:
                raise NotFoundError("Team not found")
            
            # Invalidate cache
            await TeamService._invalidate_user_team_cache(user_id)
            
            logger.info(f"Team {team_id} updated by user {user_id}")
            
            # Get member count for response
            members = db.execute_query(
                table="team_members",
                operation="select",
                filters={"team_id": str(team_id), "is_active": True},
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            return TeamResponse(
                id=UUID(updated_team["id"]),
                name=updated_team["name"],
                description=updated_team["description"],
                owner_id=UUID(updated_team["owner_id"]),
                team_code=updated_team["team_code"],
                is_active=updated_team["is_active"],
                max_members=updated_team["max_members"],
                metadata=updated_team["metadata"],
                member_count=len(members) if members else 0,
                created_at=datetime.fromisoformat(updated_team["created_at"]),
                updated_at=datetime.fromisoformat(updated_team["updated_at"])
            )
            
        except Exception as e:
            logger.error(f"Failed to update team {team_id}: {e}")
            raise
    
    @staticmethod
    async def delete_team(
        team_id: UUID,
        user_id: UUID,
        auth_token: str = None
    ) -> None:
        """Delete team (owner only)."""
        # Validate user is team owner
        team_access = await TeamService.validate_team_access(
            team_id, user_id, TeamRole.OWNER, auth_token
        )
        
        if not team_access.granted:
            raise ForbiddenError("Only team owner can delete team")
        
        db = await get_database()
        
        try:
            # Check for active projects or resources
            project_teams = db.execute_query(
                table="project_teams",
                operation="select",
                filters={"team_id": str(team_id)},
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if project_teams:
                logger.warning(f"Team {team_id} has {len(project_teams)} active project associations")
                # In production, you might want to transfer or archive these
            
            # Soft delete team (set inactive)
            db.execute_query(
                table="teams",
                operation="update",
                filters={"id": str(team_id)},
                data={
                    "is_active": False,
                    "updated_at": datetime.utcnow().isoformat()
                },
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            # Deactivate all memberships
            db.execute_query(
                table="team_members",
                operation="update",
                filters={"team_id": str(team_id)},
                data={"is_active": False},
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            # Invalidate caches
            await TeamService._invalidate_team_related_cache(team_id)
            
            logger.info(f"Team {team_id} deleted by owner {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to delete team {team_id}: {e}")
            raise

    @staticmethod
    async def get_team_members(
        team_id: UUID,
        user_id: UUID,
        auth_token: str = None
    ) -> List[TeamMemberResponse]:
        """Get team members list."""
        # Validate user has access to view team members
        team_access = await TeamService.validate_team_access(
            team_id, user_id, TeamRole.VIEWER, auth_token
        )
        
        if not team_access.granted:
            raise NotFoundError("Team not found or access denied")
        
        db = await get_database()
        
        try:
            # Get team members with user profiles
            members = db.execute_query(
                table="team_members",
                operation="select",
                filters={"team_id": str(team_id), "is_active": True},
                auth_token=auth_token,
                user_id=str(user_id)
            )
            
            if not members:
                return []
            
            member_responses = []
            for member in members:
                try:
                    user_profile = await TeamService._get_user_profile(
                        UUID(member["user_id"]), auth_token
                    )
                    
                    member_response = TeamMemberResponse(
                        id=UUID(member["id"]),
                        team_id=UUID(member["team_id"]),
                        user=user_profile,
                        role=TeamRole(member["role"]),
                        invited_by=UUID(member["invited_by"]) if member.get("invited_by") else None,
                        joined_at=datetime.fromisoformat(member["joined_at"]),
                        is_active=member["is_active"]
                    )
                    member_responses.append(member_response)
                    
                except Exception as e:
                    logger.warning(f"Failed to get profile for member {member['user_id']}: {e}")
                    continue
            
            return member_responses
            
        except Exception as e:
            logger.error(f"Failed to get team members for {team_id}: {e}")
            raise

    @staticmethod
    async def _invalidate_team_related_cache(team_id: UUID) -> None:
        """Invalidate all team-related cache entries."""
        try:
            from utils.cache_manager import get_cache_manager
            cache_manager = get_cache_manager()
            
            # Invalidate team-specific cache entries
            patterns = [
                f"team:{team_id}:*",
                f"user_teams:*",  # User teams cache affected
                f"project_teams:*:{team_id}:*"
            ]
            
            for pattern in patterns:
                await cache_manager.invalidate_pattern(pattern)
            
            logger.info(f"🔄 [CACHE] Invalidated team-related cache for team {team_id}")
            
        except Exception as e:
            logger.warning(f"⚠️ [CACHE] Failed to invalidate team cache: {e}")


# Note: Database tables are now accessed through the Supabase client interface