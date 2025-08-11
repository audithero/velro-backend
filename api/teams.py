"""
Team collaboration API endpoints.
Following CLAUDE.md: Security-first, RLS-aware, comprehensive validation.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from uuid import UUID

from models.team import (
    TeamCreate, TeamUpdate, TeamResponse, TeamMemberResponse, TeamMemberUpdate,
    TeamInvitationCreate, TeamInvitationResponse, TeamInvitationAccept,
    TeamListResponse, TeamMemberListResponse, TeamStatistics
)
from services.team_service import TeamService
from middleware.auth import require_auth, get_current_user
from utils.pagination import PaginationParams
from utils.exceptions import NotFoundError, ConflictError, ForbiddenError
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/teams", tags=["teams"])


@router.post("", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
async def create_team(
    team_data: TeamCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new team with the current user as owner."""
    try:
        team = await TeamService.create_team(team_data, current_user["id"])
        logger.info(f"User {current_user['id']} created team {team.id}")
        return team
    except Exception as e:
        logger.error(f"Failed to create team: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create team"
        )


@router.get("", response_model=TeamListResponse)
async def get_user_teams(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Get all teams for the current user with pagination."""
    try:
        pagination = PaginationParams(page=page, per_page=per_page)
        teams, total = await TeamService.get_user_teams(current_user["id"], pagination)
        
        return TeamListResponse(
            items=teams,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page
        )
    except Exception as e:
        logger.error(f"Failed to get user teams: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve teams"
        )


@router.get("/{team_id}", response_model=TeamResponse)
async def get_team(
    team_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get team details if user has access."""
    try:
        team = await TeamService.get_team(team_id, current_user["id"])
        return team
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or access denied"
        )
    except Exception as e:
        logger.error(f"Failed to get team {team_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve team"
        )


@router.put("/{team_id}", response_model=TeamResponse)
async def update_team(
    team_id: UUID,
    team_data: TeamUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update team details (admin only)."""
    try:
        team = await TeamService.update_team(team_id, team_data, current_user["id"])
        logger.info(f"User {current_user['id']} updated team {team_id}")
        return team
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update team"
        )
    except Exception as e:
        logger.error(f"Failed to update team {team_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update team"
        )


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Delete team (owner only)."""
    try:
        await TeamService.delete_team(team_id, current_user["id"])
        logger.info(f"User {current_user['id']} deleted team {team_id}")
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team owner can delete team"
        )
    except Exception as e:
        logger.error(f"Failed to delete team {team_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete team"
        )


@router.get("/{team_id}/members", response_model=TeamMemberListResponse)
async def get_team_members(
    team_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get team members list."""
    try:
        members = await TeamService.get_team_members(team_id, current_user["id"])
        return TeamMemberListResponse(items=members, total=len(members))
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or access denied"
        )
    except Exception as e:
        logger.error(f"Failed to get team members for {team_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve team members"
        )


@router.put("/{team_id}/members/{member_id}", response_model=TeamMemberResponse)
async def update_team_member(
    team_id: UUID,
    member_id: UUID,
    member_data: TeamMemberUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update team member role or status (admin only)."""
    try:
        member = await TeamService.update_team_member(
            team_id, member_id, member_data, current_user["id"]
        )
        logger.info(f"User {current_user['id']} updated member {member_id} in team {team_id}")
        return member
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to update team member"
        )
    except Exception as e:
        logger.error(f"Failed to update team member {member_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update team member"
        )


@router.delete("/{team_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    team_id: UUID,
    member_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Remove team member (admin only) or leave team (self)."""
    try:
        await TeamService.remove_team_member(team_id, member_id, current_user["id"])
        logger.info(f"Removed member {member_id} from team {team_id}")
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to remove team member"
        )
    except Exception as e:
        logger.error(f"Failed to remove team member {member_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove team member"
        )


@router.post("/{team_id}/invitations", response_model=TeamInvitationResponse)
async def invite_user(
    team_id: UUID,
    invitation_data: TeamInvitationCreate,
    current_user: dict = Depends(get_current_user)
):
    """Invite a user to join the team (admin only)."""
    try:
        invitation = await TeamService.invite_user(
            team_id, current_user["id"], invitation_data
        )
        logger.info(f"User {current_user['id']} invited {invitation_data.invited_email} to team {team_id}")
        return invitation
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to invite users"
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to create invitation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create invitation"
        )


@router.get("/{team_id}/invitations", response_model=List[TeamInvitationResponse])
async def get_team_invitations(
    team_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get pending invitations for the team (admin only)."""
    try:
        invitations = await TeamService.get_team_invitations(team_id, current_user["id"])
        return invitations
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to view invitations"
        )
    except Exception as e:
        logger.error(f"Failed to get invitations for team {team_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve invitations"
        )


@router.post("/invitations/accept", response_model=TeamMemberResponse)
async def accept_invitation(
    invitation_data: TeamInvitationAccept,
    current_user: dict = Depends(get_current_user)
):
    """Accept a team invitation using the invitation token."""
    try:
        member = await TeamService.accept_invitation(
            current_user["id"], invitation_data.invitation_token
        )
        logger.info(f"User {current_user['id']} accepted team invitation")
        return member
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired invitation"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invitation email does not match your account"
        )
    except ConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to accept invitation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to accept invitation"
        )


@router.delete("/{team_id}/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invitation(
    team_id: UUID,
    invitation_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Cancel a pending invitation (admin only)."""
    try:
        await TeamService.cancel_invitation(team_id, invitation_id, current_user["id"])
        logger.info(f"Cancelled invitation {invitation_id} for team {team_id}")
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions to cancel invitation"
        )
    except Exception as e:
        logger.error(f"Failed to cancel invitation {invitation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel invitation"
        )


@router.get("/{team_id}/statistics", response_model=TeamStatistics)
async def get_team_statistics(
    team_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get team statistics and metrics."""
    try:
        stats = await TeamService.get_team_statistics(team_id, current_user["id"])
        return stats
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or access denied"
        )
    except Exception as e:
        logger.error(f"Failed to get team statistics for {team_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve team statistics"
        )


@router.post("/{team_id}/leave", status_code=status.HTTP_204_NO_CONTENT)
async def leave_team(
    team_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Leave a team (current user leaves themselves)."""
    try:
        await TeamService.leave_team(team_id, current_user["id"])
        logger.info(f"User {current_user['id']} left team {team_id}")
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team not found or you are not a member"
        )
    except ForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Team owner cannot leave team (transfer ownership first)"
        )
    except Exception as e:
        logger.error(f"Failed to leave team {team_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to leave team"
        )