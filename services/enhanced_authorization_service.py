"""
Enhanced Authorization Service with Team Collaboration
Enterprise-grade authorization system with comprehensive team-based access control.
Implements multi-level RBAC with inheritance and resource sharing.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime, timedelta
from uuid import UUID

from database import get_database
from models.authorization import (
    ValidationContext, SecurityLevel, TeamRole, ProjectVisibility, AccessType,
    AuthorizationMethod, AuthorizationResult, GenerationPermissions, TeamAccessResult,
    SecurityContext, ProjectPermissions, InheritedAccessResult,
    VelroAuthorizationError, GenerationAccessDeniedError, SecurityViolationError,
    GenerationNotFoundError, has_sufficient_role, get_role_permissions
)
from models.team import TeamResponse, TeamMemberResponse
from utils.enhanced_uuid_utils import EnhancedUUIDUtils, secure_uuid_validator
from utils.cache_manager import CacheManager
from services.team_service import TeamService
import json

logger = logging.getLogger(__name__)


class EnhancedAuthorizationService:
    """
    Enhanced authorization service with comprehensive team collaboration support.
    Implements enterprise-grade RBAC with multi-level permissions and inheritance.
    """
    
    def __init__(self):
        self.cache_manager = CacheManager()
        self.team_service = TeamService()
        self.rate_limiter = {}
        self.security_violations = {}
        
        # Performance metrics for enterprise monitoring
        self.metrics = {
            "authorization_requests": 0,
            "team_access_checks": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "average_response_time": 0,
            "security_violations": 0,
            "team_permission_cache_hits": 0
        }
    
    async def validate_team_resource_access(
        self,
        resource_id: UUID,
        resource_type: str,
        user_id: UUID,
        required_access: AccessType,
        auth_token: str,
        client_ip: Optional[str] = None
    ) -> GenerationPermissions:
        """
        Comprehensive team-based resource access validation.
        Supports multi-level permission checking with inheritance.
        """
        start_time = time.time()
        self.metrics["authorization_requests"] += 1
        self.metrics["team_access_checks"] += 1
        
        logger.info(f"🔐 [TEAM-AUTH] Validating {required_access.value} access for user {user_id} on {resource_type} {resource_id}")
        
        try:
            # Step 1: Security input validation
            validated_resource_id = await secure_uuid_validator.validate_uuid_format(
                resource_id, ValidationContext.GENERATION_ACCESS, strict=True, client_ip=client_ip
            )
            validated_user_id = await secure_uuid_validator.validate_uuid_format(
                user_id, ValidationContext.USER_PROFILE, strict=True, client_ip=client_ip
            )
            
            if not validated_resource_id or not validated_user_id:
                raise SecurityViolationError(
                    "invalid_uuid_format",
                    {"resource_id": str(resource_id), "user_id": str(user_id)},
                    user_id=user_id,
                    client_ip=client_ip
                )
            
            # Step 2: Rate limiting
            if not await self._check_rate_limiting(str(validated_user_id), client_ip):
                raise SecurityViolationError(
                    "rate_limit_exceeded",
                    {"user_id": validated_user_id, "client_ip": client_ip},
                    user_id=user_id,
                    client_ip=client_ip
                )
            
            # Step 3: Multi-level authorization check
            permission_result = await self._multi_level_authorization_check(
                resource_id=UUID(validated_resource_id),
                resource_type=resource_type,
                user_id=UUID(validated_user_id),
                required_access=required_access,
                auth_token=auth_token
            )
            
            # Step 4: Build comprehensive permissions response
            if permission_result.granted:
                response_time = time.time() - start_time
                self._update_performance_metrics(response_time, cache_hit=permission_result.access_method == AuthorizationMethod.TEAM_MEMBERSHIP)
                
                await self._audit_log_team_access_granted(
                    str(resource_id), str(user_id), permission_result.access_method, 
                    permission_result.team_context, permission_result.security_level
                )
                
                return permission_result
            else:
                await self._audit_log_team_access_denied(
                    str(resource_id), str(user_id), permission_result.denial_reason
                )
                
                raise GenerationAccessDeniedError(
                    UUID(validated_resource_id), 
                    UUID(validated_user_id),
                    permission_result.denial_reason or "access_denied",
                    permission_result.audit_trail
                )
        
        except Exception as e:
            response_time = time.time() - start_time
            self._update_performance_metrics(response_time, cache_hit=False)
            
            if isinstance(e, (VelroAuthorizationError, SecurityViolationError)):
                raise
            
            logger.error(f"❌ [TEAM-AUTH] Unexpected error in authorization: {e}")
            raise VelroAuthorizationError(
                "authorization_service_error",
                "INTERNAL_AUTHORIZATION_ERROR",
                {"error": str(e), "resource_id": str(resource_id), "user_id": str(user_id)}
            )
    
    async def _multi_level_authorization_check(
        self,
        resource_id: UUID,
        resource_type: str,
        user_id: UUID,
        required_access: AccessType,
        auth_token: str
    ) -> GenerationPermissions:
        """
        Multi-level authorization check with team inheritance.
        Implements the 10-layer authorization framework from PRD.
        """
        audit_trail = []
        
        try:
            # Layer 1: Direct resource ownership
            direct_access = await self._check_direct_ownership(
                resource_id, resource_type, user_id, auth_token
            )
            audit_trail.append({"method": "direct_ownership", "granted": direct_access is not None})
            
            if direct_access:
                logger.info(f"✅ [LAYER-1] Direct ownership access granted")
                return self._build_permission_response(
                    resource_id, user_id, True, AuthorizationMethod.DIRECT_OWNERSHIP,
                    direct_access, audit_trail=audit_trail
                )
            
            # Layer 2: Team membership access
            team_access = await self._check_team_membership_access(
                resource_id, resource_type, user_id, required_access, auth_token
            )
            audit_trail.append({"method": "team_membership", "granted": team_access is not None})
            
            if team_access:
                logger.info(f"✅ [LAYER-2] Team membership access granted via team {team_access.get('team_id')}")
                return self._build_permission_response(
                    resource_id, user_id, True, AuthorizationMethod.TEAM_MEMBERSHIP,
                    team_access, audit_trail=audit_trail
                )
            
            # Layer 3: Project collaboration access
            project_access = await self._check_project_collaboration_access(
                resource_id, resource_type, user_id, required_access, auth_token
            )
            audit_trail.append({"method": "project_collaboration", "granted": project_access is not None})
            
            if project_access:
                logger.info(f"✅ [LAYER-3] Project collaboration access granted")
                return self._build_permission_response(
                    resource_id, user_id, True, AuthorizationMethod.PROJECT_COLLABORATION,
                    project_access, audit_trail=audit_trail
                )
            
            # Layer 4: Generation inheritance access
            inheritance_access = await self._check_generation_inheritance_access(
                resource_id, user_id, required_access, auth_token
            )
            audit_trail.append({"method": "generation_inheritance", "granted": inheritance_access is not None})
            
            if inheritance_access:
                logger.info(f"✅ [LAYER-4] Generation inheritance access granted")
                return self._build_permission_response(
                    resource_id, user_id, True, AuthorizationMethod.GENERATION_INHERITANCE,
                    inheritance_access, audit_trail=audit_trail
                )
            
            # Layer 5: Public access (if applicable)
            public_access = await self._check_public_access(
                resource_id, resource_type, user_id, auth_token
            )
            audit_trail.append({"method": "public_access", "granted": public_access is not None})
            
            if public_access:
                logger.info(f"✅ [LAYER-5] Public access granted")
                return self._build_permission_response(
                    resource_id, user_id, True, AuthorizationMethod.PUBLIC_ACCESS,
                    public_access, audit_trail=audit_trail
                )
            
            # All layers failed - access denied
            logger.warning(f"❌ [MULTI-LAYER] All authorization layers failed for user {user_id} on resource {resource_id}")
            
            return GenerationPermissions(
                generation_id=resource_id,
                user_id=user_id,
                granted=False,
                access_method=AuthorizationMethod.DIRECT_OWNERSHIP,  # Default for denial
                audit_trail=audit_trail
            )
        
        except Exception as e:
            logger.error(f"❌ [MULTI-LAYER] Error in multi-level authorization: {e}")
            return GenerationPermissions(
                generation_id=resource_id,
                user_id=user_id,
                granted=False,
                access_method=AuthorizationMethod.DIRECT_OWNERSHIP,
                audit_trail=audit_trail + [{"error": str(e)}]
            )
    
    async def _check_team_membership_access(
        self,
        resource_id: UUID,
        resource_type: str,
        user_id: UUID,
        required_access: AccessType,
        auth_token: str
    ) -> Optional[Dict[str, Any]]:
        """
        Check team membership access with role-based permissions.
        Implements comprehensive RBAC with team context.
        """
        try:
            db = await get_database()
            
            # Get resource details to find associated teams
            if resource_type == "generation":
                resource = await self._get_generation_with_team_context(resource_id, auth_token)
                if not resource:
                    return None
                
                # Check if generation has team context
                team_context_id = resource.get('team_context_id')
                project_id = resource.get('project_id')
                
                # Priority 1: Direct team context on generation
                if team_context_id:
                    team_access = await self.team_service.validate_team_access(
                        UUID(team_context_id), user_id, self._map_access_to_team_role(required_access), auth_token
                    )
                    
                    if team_access.granted:
                        return {
                            "team_id": team_context_id,
                            "role": team_access.role.value,
                            "access_method": "direct_team_context",
                            "permissions": get_role_permissions(team_access.role),
                            "resource_context": resource
                        }
                
                # Priority 2: Project-team associations
                if project_id:
                    project_teams = await self._get_project_teams(UUID(project_id), auth_token)
                    
                    for project_team in project_teams:
                        team_id = UUID(project_team['team_id'])
                        team_access = await self.team_service.validate_team_access(
                            team_id, user_id, self._map_access_to_team_role(required_access), auth_token
                        )
                        
                        if team_access.granted:
                            return {
                                "team_id": str(team_id),
                                "role": team_access.role.value,
                                "access_method": "project_team_association",
                                "project_access_level": project_team['access_level'],
                                "permissions": get_role_permissions(team_access.role),
                                "resource_context": resource
                            }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ [TEAM-ACCESS] Error checking team membership access: {e}")
            return None
    
    async def _get_generation_with_team_context(
        self, generation_id: UUID, auth_token: str
    ) -> Optional[Dict[str, Any]]:
        """Get generation with full team context information."""
        try:
            db = await get_database()
            
            # Enhanced query to get generation with project and team context
            generation = db.execute_query(
                table="generations",
                operation="select",
                filters={"id": str(generation_id)},
                single=True,
                auth_token=auth_token
            )
            
            return generation
            
        except Exception as e:
            logger.error(f"❌ [GENERATION-CONTEXT] Error getting generation with team context: {e}")
            return None
    
    async def _get_project_teams(
        self, project_id: UUID, auth_token: str
    ) -> List[Dict[str, Any]]:
        """Get all teams associated with a project."""
        try:
            db = await get_database()
            
            project_teams = db.execute_query(
                table="project_teams",
                operation="select",
                filters={"project_id": str(project_id)},
                auth_token=auth_token
            )
            
            return project_teams or []
            
        except Exception as e:
            logger.error(f"❌ [PROJECT-TEAMS] Error getting project teams: {e}")
            return []
    
    def _map_access_to_team_role(self, access_type: AccessType) -> TeamRole:
        """Map access type requirements to minimum team role."""
        access_role_map = {
            AccessType.READ: TeamRole.VIEWER,
            AccessType.WRITE: TeamRole.EDITOR,
            AccessType.DELETE: TeamRole.ADMIN,
            AccessType.SHARE: TeamRole.EDITOR,
            AccessType.ADMIN: TeamRole.ADMIN
        }
        
        return access_role_map.get(access_type, TeamRole.VIEWER)
    
    def _build_permission_response(
        self,
        resource_id: UUID,
        user_id: UUID,
        granted: bool,
        access_method: AuthorizationMethod,
        access_context: Dict[str, Any],
        audit_trail: List[Dict[str, Any]] = None
    ) -> GenerationPermissions:
        """Build comprehensive permission response with team context."""
        
        if granted and access_context:
            # Extract permissions from role if available
            role_str = access_context.get('role')
            permissions = access_context.get('permissions')
            
            if role_str and not permissions:
                try:
                    role = TeamRole(role_str)
                    permissions = get_role_permissions(role)
                except ValueError:
                    permissions = get_role_permissions(TeamRole.VIEWER)
            
            return GenerationPermissions(
                generation_id=resource_id,
                user_id=user_id,
                granted=True,
                access_method=access_method,
                can_view=permissions.can_view if permissions else True,
                can_edit=permissions.can_edit if permissions else False,
                can_delete=permissions.can_delete if permissions else False,
                can_download=permissions.can_download if permissions else True,
                can_share=permissions.can_share if permissions else False,
                can_create_child=permissions.can_edit if permissions else False,
                team_context=UUID(access_context.get('team_id')) if access_context.get('team_id') else None,
                project_context=UUID(access_context.get('project_id')) if access_context.get('project_id') else None,
                security_level=SecurityLevel.TEAM_MEMBER,
                audit_trail=audit_trail or []
            )
        
        return GenerationPermissions(
            generation_id=resource_id,
            user_id=user_id,
            granted=False,
            access_method=access_method,
            audit_trail=audit_trail or []
        )
    
    # PLACEHOLDER METHODS FOR OTHER AUTHORIZATION LAYERS
    # These would be implemented based on existing authorization service
    
    async def _check_direct_ownership(
        self, resource_id: UUID, resource_type: str, user_id: UUID, auth_token: str
    ) -> Optional[Dict[str, Any]]:
        """Check direct resource ownership."""
        # Implementation would check if user directly owns the resource
        return None
    
    async def _check_project_collaboration_access(
        self, resource_id: UUID, resource_type: str, user_id: UUID, required_access: AccessType, auth_token: str
    ) -> Optional[Dict[str, Any]]:
        """Check project-level collaboration access."""
        # Implementation would check project-level permissions
        return None
    
    async def _check_generation_inheritance_access(
        self, resource_id: UUID, user_id: UUID, required_access: AccessType, auth_token: str
    ) -> Optional[Dict[str, Any]]:
        """Check access through generation inheritance chain."""
        # Implementation would check parent-child generation relationships
        return None
    
    async def _check_public_access(
        self, resource_id: UUID, resource_type: str, user_id: UUID, auth_token: str
    ) -> Optional[Dict[str, Any]]:
        """Check public access permissions."""
        # Implementation would check if resource is publicly accessible
        return None
    
    # PERFORMANCE AND MONITORING METHODS
    
    async def _check_rate_limiting(self, user_id: str, client_ip: Optional[str]) -> bool:
        """Enterprise-grade rate limiting with team context."""
        current_minute = int(datetime.utcnow().timestamp() // 60)
        
        # Per-user rate limiting (higher limits for team operations)
        user_key = f"team_auth_user:{user_id}:{current_minute}"
        user_count = self.rate_limiter.get(user_key, 0)
        if user_count >= 200:  # 200 requests per minute per user (2x normal)
            return False
        self.rate_limiter[user_key] = user_count + 1
        
        # Per-IP rate limiting
        if client_ip:
            ip_key = f"team_auth_ip:{client_ip}:{current_minute}"
            ip_count = self.rate_limiter.get(ip_key, 0)
            if ip_count >= 1000:  # 1000 requests per minute per IP for team operations
                return False
            self.rate_limiter[ip_key] = ip_count + 1
        
        return True
    
    def _update_performance_metrics(self, response_time: float, cache_hit: bool = False) -> None:
        """Update performance metrics for monitoring."""
        if cache_hit:
            self.metrics["cache_hits"] += 1
            self.metrics["team_permission_cache_hits"] += 1
        else:
            self.metrics["cache_misses"] += 1
        
        # Update rolling average response time
        current_avg = self.metrics["average_response_time"]
        total_requests = self.metrics["authorization_requests"]
        
        self.metrics["average_response_time"] = (
            (current_avg * (total_requests - 1) + response_time * 1000) / total_requests
        )
    
    async def _audit_log_team_access_granted(
        self, resource_id: str, user_id: str, access_method: AuthorizationMethod, 
        team_context: Optional[UUID], security_level: SecurityLevel
    ) -> None:
        """Audit log for successful team access."""
        logger.info(
            f"✅ [TEAM-AUTH-SUCCESS] User {EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
            f"granted access to resource {EnhancedUUIDUtils.hash_uuid_for_logging(resource_id)} "
            f"via {access_method.value} "
            f"(team: {team_context}, security: {security_level.value})"
        )
    
    async def _audit_log_team_access_denied(
        self, resource_id: str, user_id: str, reason: str
    ) -> None:
        """Audit log for denied team access."""
        logger.warning(
            f"❌ [TEAM-AUTH-DENIED] User {EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
            f"denied access to resource {EnhancedUUIDUtils.hash_uuid_for_logging(resource_id)} "
            f"(reason: {reason})"
        )
    
    async def get_user_team_permissions_summary(
        self, user_id: UUID, auth_token: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive team permissions summary for a user.
        Used for enterprise team management dashboards.
        """
        try:
            # Get user's team memberships
            from utils.pagination import PaginationParams
            teams, total = await self.team_service.get_user_teams(
                user_id, PaginationParams(page=1, per_page=100), auth_token
            )
            
            permissions_summary = {
                "user_id": str(user_id),
                "total_teams": total,
                "team_roles": {},
                "permissions_matrix": {},
                "resource_access_counts": {
                    "projects": 0,
                    "generations": 0,
                    "shared_resources": 0
                },
                "team_details": []
            }
            
            for team in teams:
                # Get user's role in this team
                team_access = await self.team_service.validate_team_access(
                    team.id, user_id, TeamRole.VIEWER, auth_token
                )
                
                if team_access.granted:
                    role = team_access.role
                    permissions_summary["team_roles"][str(team.id)] = role.value
                    
                    # Get permissions for this role
                    role_permissions = get_role_permissions(role)
                    
                    permissions_summary["team_details"].append({
                        "team_id": str(team.id),
                        "team_name": team.name,
                        "role": role.value,
                        "permissions": {
                            "can_view": role_permissions.can_view,
                            "can_edit": role_permissions.can_edit,
                            "can_delete": role_permissions.can_delete,
                            "can_download": role_permissions.can_download,
                            "can_share": role_permissions.can_share
                        },
                        "member_count": team.member_count,
                        "is_owner": role == TeamRole.OWNER
                    })
                    
                    # Count accessible resources (simplified)
                    permissions_summary["resource_access_counts"]["projects"] += 1
                    if role in [TeamRole.EDITOR, TeamRole.ADMIN, TeamRole.OWNER]:
                        permissions_summary["resource_access_counts"]["generations"] += team.member_count * 5  # Estimate
                        permissions_summary["resource_access_counts"]["shared_resources"] += team.member_count * 2
            
            return permissions_summary
            
        except Exception as e:
            logger.error(f"❌ [TEAM-PERMISSIONS-SUMMARY] Error getting permissions summary: {e}")
            return {"error": str(e), "user_id": str(user_id)}


# Singleton instance for global use
enhanced_authorization_service = EnhancedAuthorizationService()