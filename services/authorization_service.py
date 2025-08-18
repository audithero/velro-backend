"""
Centralized Authorization Service
Enterprise-grade authorization system with comprehensive security and performance optimization.
Implements the complete UUID Validation Standards with OWASP compliance.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Any, Tuple
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
from utils.enhanced_uuid_utils import EnhancedUUIDUtils, secure_uuid_validator
from utils.cache_manager import CacheManager
from services.team_service import TeamService
from services.cache_service import (
    get_authorization_cache_service, AuthorizationCacheType,
    get_cached_user_authorization, cache_user_authorization_result,
    AuthorizationCacheEntry
)
import json

logger = logging.getLogger(__name__)


class AuthorizationService:
    """
    Enterprise authorization service with multi-layer security validation and 3-level caching.
    Implements comprehensive UUID validation standards with <50ms performance optimization.
    """
    
    def __init__(self):
        self.cache_manager = CacheManager()
        self.authorization_cache = get_authorization_cache_service()
        self.team_service = TeamService()
        self.rate_limiter = {}
        self.security_violations = {}
        
        # Performance metrics
        self.metrics = {
            "authorization_requests": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "average_response_time": 0,
            "security_violations": 0
        }
    
    async def validate_generation_media_access(
        self, 
        generation_id: UUID, 
        user_id: UUID, 
        auth_token: str,
        client_ip: Optional[str] = None,
        expires_in: int = 3600
    ) -> GenerationPermissions:
        """
        Enterprise-grade generation media access validation with 3-level caching.
        Target: <50ms response time with >95% cache hit rate.
        """
        start_time = time.time()
        self.metrics["authorization_requests"] += 1
        
        try:
            # Step 1: Security input validation (OWASP compliance)
            validated_generation_id = await secure_uuid_validator.validate_uuid_format(
                generation_id, ValidationContext.GENERATION_ACCESS, strict=True, client_ip=client_ip
            )
            validated_user_id = await secure_uuid_validator.validate_uuid_format(
                user_id, ValidationContext.USER_PROFILE, strict=True, client_ip=client_ip
            )
            
            if not validated_generation_id or not validated_user_id:
                raise SecurityViolationError(
                    "invalid_uuid_format", 
                    {"generation_id": str(generation_id), "user_id": str(user_id)},
                    user_id=user_id,
                    client_ip=client_ip
                )
            
            # Step 2: CHECK CACHE FIRST - Ultra-fast path for repeated requests
            cached_auth = await self.authorization_cache.get_authorization_cache(
                user_id=UUID(validated_user_id),
                resource_id=UUID(validated_generation_id),
                resource_type="generation",
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS
            )
            
            if cached_auth and cached_auth.is_valid():
                self.metrics["cache_hits"] += 1
                response_time_ms = (time.time() - start_time) * 1000
                
                logger.info(f"🚀 CACHE HIT: Authorization for {validated_user_id}/{validated_generation_id} in {response_time_ms:.1f}ms")
                
                # Return cached permissions directly
                return GenerationPermissions(
                    generation_id=UUID(validated_generation_id),
                    user_id=UUID(validated_user_id),
                    granted=cached_auth.permissions.get("can_view", False),
                    access_method=getattr(AuthorizationMethod, cached_auth.access_method.upper(), AuthorizationMethod.DIRECT_OWNERSHIP),
                    can_view=cached_auth.permissions.get("can_view", False),
                    can_edit=cached_auth.permissions.get("can_edit", False),
                    can_delete=cached_auth.permissions.get("can_delete", False),
                    can_download=cached_auth.permissions.get("can_download", False),
                    can_share=cached_auth.permissions.get("can_share", False),
                    can_create_child=cached_auth.permissions.get("can_edit", False),
                    project_context=None,
                    security_level=SecurityLevel.AUTHENTICATED,
                    expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
                    media_urls=await self._generate_secure_media_urls_cached(validated_generation_id, cached_auth.access_method, expires_in),
                    rate_limit_remaining=await self._get_rate_limit_remaining(validated_user_id),
                    audit_trail=[]
                )
            
            # CACHE MISS - Proceed with full validation
            self.metrics["cache_misses"] += 1
            logger.debug(f"💾 CACHE MISS: Full authorization check required for {validated_user_id}/{validated_generation_id}")
            
            # Step 3: Rate limiting and abuse prevention
            if not await self._check_rate_limiting(validated_user_id, client_ip):
                raise SecurityViolationError(
                    "rate_limit_exceeded",
                    {"user_id": validated_user_id, "client_ip": client_ip},
                    user_id=user_id,
                    client_ip=client_ip
                )
            
            # Step 4: Get generation with full security context
            generation = await self._get_generation_with_auth_context(
                generation_id=UUID(validated_generation_id),
                user_id=UUID(validated_user_id),
                auth_token=auth_token
            )
            
            if not generation:
                await self._audit_log_access_denied(
                    validated_generation_id, validated_user_id, "not_found"
                )
                raise GenerationNotFoundError(UUID(validated_generation_id))
            
            # Step 5: Multi-layer authorization check
            authorization_result = await self._comprehensive_authorization_check(
                generation, UUID(validated_user_id), auth_token, client_ip
            )
            
            if not authorization_result.granted:
                await self._audit_log_access_denied(
                    validated_generation_id, validated_user_id, authorization_result.denial_reason
                )
                raise GenerationAccessDeniedError(
                    generation_id=UUID(validated_generation_id),
                    user_id=UUID(validated_user_id),
                    reason=authorization_result.denial_reason,
                    authorization_attempts=authorization_result.audit_trail
                )
            
            # Step 6: CACHE THE SUCCESSFUL AUTHORIZATION RESULT - Critical for performance
            permissions_dict = {
                "can_view": authorization_result.can_view,
                "can_edit": authorization_result.can_edit,
                "can_delete": authorization_result.can_delete,
                "can_download": authorization_result.can_download,
                "can_share": authorization_result.can_share
            }
            
            # Cache the authorization result for future requests
            await self.authorization_cache.set_authorization_cache(
                user_id=UUID(validated_user_id),
                resource_id=UUID(validated_generation_id),
                resource_type="generation",
                permissions=permissions_dict,
                access_method=authorization_result.access_method.value,
                effective_role=None,  # Could be enhanced with role information
                cache_type=AuthorizationCacheType.GENERATION_RIGHTS,
                priority=3  # High priority for successful authorizations
            )
            
            # Step 7: Generate secure media URLs with expiration
            media_urls = await self._generate_secure_media_urls(
                generation, authorization_result.access_method, expires_in
            )
            
            # Step 8: Success audit logging
            await self._audit_log_access_granted(
                validated_generation_id, validated_user_id, 
                authorization_result.access_method, len(media_urls)
            )
            
            # Step 9: Update performance metrics
            response_time = (time.time() - start_time) * 1000
            self._update_performance_metrics(response_time)
            
            logger.info(f"✅ FULL AUTH: Authorization for {validated_user_id}/{validated_generation_id} in {response_time:.1f}ms (cached for future)")
            
            return GenerationPermissions(
                generation_id=UUID(validated_generation_id),
                user_id=UUID(validated_user_id),
                granted=True,
                access_method=authorization_result.access_method,
                can_view=authorization_result.can_view,
                can_edit=authorization_result.can_edit,
                can_delete=authorization_result.can_delete,
                can_download=authorization_result.can_download,
                can_share=authorization_result.can_share,
                can_create_child=authorization_result.can_edit,
                project_context=generation.get('project_id'),
                security_level=SecurityLevel.AUTHENTICATED,
                expires_at=datetime.utcnow() + timedelta(seconds=expires_in),
                media_urls=media_urls,
                rate_limit_remaining=await self._get_rate_limit_remaining(validated_user_id),
                audit_trail=authorization_result.audit_trail
            )
            
        except (SecurityViolationError, GenerationAccessDeniedError, GenerationNotFoundError):
            # Re-raise known authorization errors
            raise
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"❌ [AUTH-ERROR] Unexpected error in media access validation: {e}")
            await self._audit_log_access_denied(
                str(generation_id), str(user_id), f"system_error: {str(e)}"
            )
            raise VelroAuthorizationError(
                message="Internal authorization error",
                error_code="AUTHORIZATION_SYSTEM_ERROR",
                context={"generation_id": str(generation_id), "user_id": str(user_id)},
                user_id=user_id,
                resource_id=generation_id
            )
    
    async def validate_direct_ownership(
        self, resource_user_id: UUID, request_user_id: UUID, context: ValidationContext
    ) -> AuthorizationResult:
        """Enhanced direct ownership validation with security checks."""
        
        # UUID normalization with security checks
        resource_str = await secure_uuid_validator.validate_uuid_format(
            resource_user_id, context, strict=True
        )
        request_str = await secure_uuid_validator.validate_uuid_format(
            request_user_id, ValidationContext.USER_PROFILE, strict=True
        )
        
        if not resource_str or not request_str:
            return AuthorizationResult(
                granted=False, denial_reason="invalid_uuid_format"
            )
        
        # Use constant-time comparison for security
        is_owner = await EnhancedUUIDUtils.validate_uuid_ownership(
            resource_user_id, request_user_id, context
        )
        
        return AuthorizationResult(
            granted=is_owner,
            access_method=AuthorizationMethod.DIRECT_OWNERSHIP if is_owner else None,
            can_view=is_owner,
            can_edit=is_owner,
            can_delete=is_owner,
            can_download=is_owner,
            can_share=is_owner,
            audit_trail=[{
                "method": "direct_ownership",
                "result": is_owner,
                "timestamp": datetime.utcnow().isoformat()
            }]
        )
    
    async def validate_team_access(
        self, 
        resource_id: UUID, 
        user_id: UUID,
        required_role: TeamRole = TeamRole.VIEWER,
        auth_token: str = None,
        client_ip: Optional[str] = None
    ) -> TeamAccessResult:
        """Enterprise team-based access validation with comprehensive security."""
        
        # Security input validation
        validated_resource_id = await secure_uuid_validator.validate_uuid_format(
            resource_id, ValidationContext.GENERATION_ACCESS, client_ip=client_ip
        )
        validated_user_id = await secure_uuid_validator.validate_uuid_format(
            user_id, ValidationContext.USER_PROFILE, client_ip=client_ip
        )
        
        if not validated_resource_id or not validated_user_id:
            return TeamAccessResult(
                granted=False, 
                denial_reason="invalid_uuid_format"
            )
        
        # Step 1: Check direct ownership first (fastest path)
        resource = await self._get_resource_with_security_context(
            UUID(validated_resource_id), UUID(validated_user_id), auth_token
        )
        
        if not resource:
            return TeamAccessResult(
                granted=False, 
                denial_reason="resource_not_found"
            )
        
        direct_ownership = await self.validate_direct_ownership(
            UUID(resource.get('user_id')), UUID(validated_user_id), 
            ValidationContext.GENERATION_ACCESS
        )
        
        if direct_ownership.granted:
            return TeamAccessResult(
                granted=True, 
                role=TeamRole.OWNER, 
                access_method=AuthorizationMethod.DIRECT_OWNERSHIP,
                checked_methods=["direct_ownership"]
            )
        
        # Step 2: Check project-level team access (cached for performance)
        project_access = None
        if resource.get('project_id'):
            project_access = await self._get_cached_project_team_access(
                project_id=UUID(resource['project_id']),
                user_id=UUID(validated_user_id),
                required_role=required_role
            )
            
            if project_access and project_access.granted:
                return TeamAccessResult(
                    granted=True,
                    role=project_access.role,
                    access_method=AuthorizationMethod.PROJECT_COLLABORATION,
                    team_id=project_access.team_id,
                    project_id=UUID(resource['project_id']),
                    checked_methods=["direct_ownership", "project_team"]
                )
        
        # Step 3: Check generation-specific collaboration context
        collaboration_access = None
        if resource.get('team_context_id'):
            collaboration_access = await self._validate_generation_collaboration(
                generation_id=UUID(validated_resource_id),
                user_id=UUID(validated_user_id),
                team_context_id=UUID(resource['team_context_id']),
                required_role=required_role,
                auth_token=auth_token
            )
            
            if collaboration_access and collaboration_access.granted:
                return TeamAccessResult(
                    granted=True,
                    role=collaboration_access.role,
                    access_method=AuthorizationMethod.GENERATION_INHERITANCE,
                    team_id=UUID(resource['team_context_id']),
                    collaboration_type=collaboration_access.collaboration_type,
                    checked_methods=["direct_ownership", "project_team", "generation_collaboration"]
                )
        
        # Step 4: Check inheritance-based access (with security boundaries)
        inheritance_access = None
        if resource.get('parent_generation_id'):
            inheritance_access = await self._validate_secure_inheritance_access(
                parent_generation_id=UUID(resource['parent_generation_id']),
                child_generation_id=UUID(validated_resource_id),
                user_id=UUID(validated_user_id),
                required_role=required_role,
                max_depth=3  # Prevent deep recursion attacks
            )
            
            if inheritance_access and inheritance_access.granted:
                return TeamAccessResult(
                    granted=True,
                    role=inheritance_access.role,
                    access_method=AuthorizationMethod.GENERATION_INHERITANCE,
                    inheritance_depth=inheritance_access.depth,
                    parent_generation_id=UUID(resource['parent_generation_id']),
                    checked_methods=["direct_ownership", "project_team", "generation_collaboration", "inheritance"]
                )
        
        # Access denied - comprehensive logging
        await self._audit_log_team_access_denied(
            resource_id=UUID(validated_resource_id),
            user_id=UUID(validated_user_id),
            required_role=required_role,
            denial_reasons={
                "direct_ownership": False,
                "project_team_access": project_access.granted if project_access else False,
                "generation_collaboration": collaboration_access.granted if collaboration_access else False,
                "inheritance_access": inheritance_access.granted if inheritance_access else False
            }
        )
        
        return TeamAccessResult(
            granted=False, 
            denial_reason="insufficient_team_permissions",
            checked_methods=["direct_ownership", "project_team", "generation_collaboration", "inheritance"]
        )
    
    async def _comprehensive_authorization_check(
        self, generation: Dict[str, Any], user_id: UUID, auth_token: str, client_ip: Optional[str]
    ) -> AuthorizationResult:
        """Multi-layer authorization check with comprehensive validation."""
        
        audit_trail = []
        
        # Layer 1: Direct ownership check
        direct_result = await self.validate_direct_ownership(
            UUID(generation['user_id']), user_id, ValidationContext.GENERATION_ACCESS
        )
        audit_trail.extend(direct_result.audit_trail)
        
        if direct_result.granted:
            return AuthorizationResult(
                granted=True,
                access_method=AuthorizationMethod.DIRECT_OWNERSHIP,
                can_view=True, can_edit=True, can_delete=True,
                can_download=True, can_share=True,
                audit_trail=audit_trail
            )
        
        # Layer 2: Team-based access check
        team_result = await self.validate_team_access(
            UUID(generation['id']), user_id, TeamRole.VIEWER, auth_token, client_ip
        )
        audit_trail.append({
            "method": "team_access",
            "result": team_result.granted,
            "role": team_result.role.value if team_result.role else None,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        if team_result.granted:
            role_permissions = get_role_permissions(team_result.role)
            return AuthorizationResult(
                granted=True,
                access_method=team_result.access_method,
                can_view=role_permissions.can_view,
                can_edit=role_permissions.can_edit,
                can_delete=role_permissions.can_delete,
                can_download=role_permissions.can_download,
                can_share=role_permissions.can_share,
                audit_trail=audit_trail
            )
        
        # Layer 3: Project visibility check
        if generation.get('project_id'):
            project_result = await self._check_project_visibility_access(
                UUID(generation['project_id']), user_id, auth_token
            )
            audit_trail.append({
                "method": "project_visibility",
                "result": project_result.granted,
                "timestamp": datetime.utcnow().isoformat()
            })
            
            if project_result.granted:
                return AuthorizationResult(
                    granted=True,
                    access_method=AuthorizationMethod.PUBLIC_ACCESS,
                    can_view=True, can_download=True,
                    audit_trail=audit_trail
                )
        
        # All authorization methods failed
        return AuthorizationResult(
            granted=False,
            denial_reason="insufficient_permissions",
            audit_trail=audit_trail
        )
    
    async def _get_generation_with_auth_context(
        self, generation_id: UUID, user_id: UUID, auth_token: str
    ) -> Optional[Dict[str, Any]]:
        """Get generation with full authorization context."""
        
        db = await get_database()
        
        try:
            # Step 1: Get the generation data
            logger.info(f"🔍 [AUTH] Fetching generation {generation_id} for authorization context")
            generation_result = db.execute_query(
                table="generations",
                operation="select",
                filters={
                    "id": str(generation_id),
                    "status": "completed"
                },
                auth_token=auth_token,
                user_id=str(user_id),
                single=True,
                use_service_key=True  # Use service key to bypass RLS for security validation
            )
            
            if not generation_result:
                logger.warning(f"❌ [AUTH] Generation {generation_id} not found or not completed")
                return None
            
            logger.info(f"✅ [AUTH] Generation found: {generation_id}")
            
            # Step 2: Get project context if generation has a project
            project_context = None
            if generation_result.get('project_id'):
                logger.info(f"🔍 [AUTH] Fetching project context for project {generation_result['project_id']}")
                try:
                    project_result = db.execute_query(
                        table="projects",
                        operation="select",
                        filters={"id": generation_result['project_id']},
                        auth_token=auth_token,
                        user_id=str(user_id),
                        single=True,
                        use_service_key=True  # Use service key to get project visibility info
                    )
                    
                    if project_result:
                        project_context = {
                            "project_visibility": project_result.get('visibility'),
                            "project_owner_id": project_result.get('owner_id')
                        }
                        logger.info(f"✅ [AUTH] Project context loaded: visibility={project_result.get('visibility')}")
                    else:
                        logger.warning(f"⚠️ [AUTH] Project {generation_result['project_id']} not found")
                        
                except Exception as project_error:
                    logger.error(f"❌ [AUTH] Failed to fetch project context: {project_error}")
                    # Continue without project context - generation may still be accessible
            
            # Step 3: Combine generation and project data
            combined_result = dict(generation_result)
            if project_context:
                combined_result.update(project_context)
            else:
                # Set default values if no project context
                combined_result.update({
                    "project_visibility": None,
                    "project_owner_id": None
                })
            
            logger.info(f"✅ [AUTH] Authorization context prepared for generation {generation_id}")
            return combined_result
            
        except Exception as e:
            logger.error(f"❌ [AUTH] Failed to get generation with auth context: {e}")
            logger.error(f"❌ [AUTH] Error type: {type(e).__name__}")
            # Re-raise the exception to be handled by the calling method
            raise
    
    async def _generate_secure_media_urls(
        self, generation: Dict[str, Any], access_method: AuthorizationMethod, expires_in: int
    ) -> List[str]:
        """Generate secure, signed media URLs with expiration."""
        
        try:
            from services.storage_service import StorageService
            storage_service = StorageService()
            
            storage_info = await storage_service.get_generation_storage_info(
                generation_id=UUID(generation['id']),
                user_id=UUID(generation['user_id']),
                expires_in=expires_in
            )
            
            return storage_info.get('signed_urls', [])
            
        except Exception as e:
            logger.error(f"❌ [MEDIA-URL] Failed to generate secure media URLs: {e}")
            return []
    
    async def _generate_secure_media_urls_cached(
        self, generation_id: str, access_method: str, expires_in: int
    ) -> List[str]:
        """Generate secure media URLs from cached authorization data."""
        
        try:
            from services.storage_service import StorageService
            storage_service = StorageService()
            
            # For cached entries, we need to get minimal generation info
            # In a full implementation, this could also be cached
            storage_info = await storage_service.get_generation_storage_info(
                generation_id=UUID(generation_id),
                user_id=None,  # Will be resolved by storage service
                expires_in=expires_in
            )
            
            return storage_info.get('signed_urls', [])
            
        except Exception as e:
            logger.error(f"❌ [MEDIA-URL-CACHED] Failed to generate cached media URLs: {e}")
            return []
    
    async def _check_rate_limiting(self, user_id: str, client_ip: Optional[str]) -> bool:
        """Check rate limiting for authorization requests."""
        current_minute = int(datetime.utcnow().timestamp() // 60)
        
        # Per-user rate limiting
        user_key = f"user:{user_id}:{current_minute}"
        user_count = self.rate_limiter.get(user_key, 0)
        if user_count >= 100:  # 100 requests per minute per user
            return False
        self.rate_limiter[user_key] = user_count + 1
        
        # Per-IP rate limiting
        if client_ip:
            ip_key = f"ip:{client_ip}:{current_minute}"
            ip_count = self.rate_limiter.get(ip_key, 0)
            if ip_count >= 500:  # 500 requests per minute per IP
                return False
            self.rate_limiter[ip_key] = ip_count + 1
        
        return True
    
    async def _get_rate_limit_remaining(self, user_id: str) -> int:
        """Get remaining rate limit for user."""
        current_minute = int(datetime.utcnow().timestamp() // 60)
        user_key = f"user:{user_id}:{current_minute}"
        used = self.rate_limiter.get(user_key, 0)
        return max(0, 100 - used)
    
    async def _audit_log_access_granted(
        self, generation_id: str, user_id: str, access_method: AuthorizationMethod, media_count: int
    ) -> None:
        """Audit log for successful access."""
        logger.info(
            f"✅ [AUTH-SUCCESS] User {EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
            f"granted access to generation {EnhancedUUIDUtils.hash_uuid_for_logging(generation_id)} "
            f"via {access_method.value} ({media_count} media files)"
        )
    
    async def _audit_log_access_denied(
        self, generation_id: str, user_id: str, reason: str
    ) -> None:
        """Audit log for denied access."""
        logger.warning(
            f"❌ [AUTH-DENIED] User {EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
            f"denied access to generation {EnhancedUUIDUtils.hash_uuid_for_logging(generation_id)}: {reason}"
        )
    
    def _update_performance_metrics(self, response_time_ms: float) -> None:
        """Update performance metrics."""
        self.metrics["average_response_time"] = (
            (self.metrics["average_response_time"] * (self.metrics["authorization_requests"] - 1) + response_time_ms)
            / self.metrics["authorization_requests"]
        )
        
        logger.info(
            f"📊 [AUTH-METRICS] Avg response time: {self.metrics['average_response_time']:.2f}ms, "
            f"Total requests: {self.metrics['authorization_requests']}"
        )
    
    # Additional helper methods for comprehensive authorization
    async def _get_resource_with_security_context(
        self, resource_id: UUID, user_id: UUID, auth_token: str
    ) -> Optional[Dict[str, Any]]:
        """Get resource with security context for authorization."""
        # Implementation would depend on resource type
        return await self._get_generation_with_auth_context(resource_id, user_id, auth_token)
    
    async def _get_cached_project_team_access(
        self, project_id: UUID, user_id: UUID, required_role: TeamRole
    ) -> Optional[TeamAccessResult]:
        """Get cached project team access result."""
        # This would integrate with the caching system
        # For now, return None to skip this optimization
        return None
    
    async def _validate_generation_collaboration(
        self, generation_id: UUID, user_id: UUID, team_context_id: UUID, 
        required_role: TeamRole, auth_token: str
    ) -> Optional[TeamAccessResult]:
        """Validate generation-specific collaboration access."""
        # Implementation for generation-specific collaboration
        return None
    
    async def _validate_secure_inheritance_access(
        self, parent_generation_id: UUID, child_generation_id: UUID, user_id: UUID,
        required_role: TeamRole, max_depth: int = 3
    ) -> Optional[InheritedAccessResult]:
        """Validate inheritance-based access with security boundaries."""
        # Implementation for inheritance validation
        return None
    
    async def _audit_log_team_access_denied(
        self, resource_id: UUID, user_id: UUID, required_role: TeamRole, denial_reasons: Dict[str, bool]
    ) -> None:
        """Audit log for team access denial."""
        logger.warning(
            f"❌ [TEAM-ACCESS-DENIED] User {EnhancedUUIDUtils.hash_uuid_for_logging(user_id)} "
            f"denied {required_role.value} access to {EnhancedUUIDUtils.hash_uuid_for_logging(resource_id)}: "
            f"{denial_reasons}"
        )
    
    async def _check_project_visibility_access(
        self, project_id: UUID, user_id: UUID, auth_token: str
    ) -> AuthorizationResult:
        """Check project visibility-based access."""
        # Implementation for project visibility check
        return AuthorizationResult(granted=False, denial_reason="not_implemented")
    
    async def invalidate_user_authorization_cache(self, user_id: UUID) -> Dict[str, int]:
        """Invalidate all authorization cache entries for a specific user."""
        try:
            return await self.authorization_cache.invalidate_authorization_cache(user_id=user_id)
        except Exception as e:
            logger.error(f"Failed to invalidate user authorization cache for {user_id}: {e}")
            return {"L1": 0, "L2": 0, "L3": 0}
    
    async def invalidate_resource_authorization_cache(self, resource_id: UUID, resource_type: str = "generation") -> Dict[str, int]:
        """Invalidate all authorization cache entries for a specific resource."""
        try:
            return await self.authorization_cache.invalidate_authorization_cache(
                resource_id=resource_id, 
                resource_type=resource_type
            )
        except Exception as e:
            logger.error(f"Failed to invalidate resource authorization cache for {resource_id}: {e}")
            return {"L1": 0, "L2": 0, "L3": 0}
    
    async def warm_user_authorization_cache(self, user_id: UUID) -> Dict[str, Dict[str, int]]:
        """Proactively warm authorization cache for a user."""
        try:
            from services.cache_service import CacheWarmingStrategy
            return await self.authorization_cache.warm_authorization_caches(
                user_id=user_id,
                cache_types=[AuthorizationCacheType.GENERATION_RIGHTS, AuthorizationCacheType.USER_PERMISSIONS],
                strategy=CacheWarmingStrategy.IMMEDIATE
            )
        except Exception as e:
            logger.error(f"Failed to warm user authorization cache for {user_id}: {e}")
            return {}
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics including caching performance."""
        base_metrics = self.metrics.copy()
        
        # Add cache performance metrics
        try:
            cache_metrics = self.authorization_cache.get_performance_metrics()
            base_metrics["cache_performance"] = cache_metrics
        except Exception as e:
            logger.error(f"Failed to get cache performance metrics: {e}")
            base_metrics["cache_performance"] = {"error": str(e)}
        
        return base_metrics
    
    async def health_check(self) -> Dict[str, Any]:
        """Comprehensive health check including cache health."""
        health_status = {
            "service_healthy": True,
            "authorization_service": "healthy",
            "performance_targets_met": False,
            "errors": []
        }
        
        try:
            # Check cache health
            cache_health = await self.authorization_cache.health_check()
            health_status["cache_service"] = cache_health
            
            if not cache_health.get("service_healthy", False):
                health_status["service_healthy"] = False
                health_status["errors"].append("Authorization cache service unhealthy")
            
            # Check performance targets
            metrics = self.get_performance_metrics()
            if "cache_performance" in metrics:
                cache_perf = metrics["cache_performance"].get("authorization_cache_performance", {})
                health_status["performance_targets_met"] = cache_perf.get("performance_targets_met", False)
            
        except Exception as e:
            health_status["service_healthy"] = False
            health_status["errors"].append(f"Health check failed: {str(e)}")
        
        return health_status


# Global authorization service instance
authorization_service = AuthorizationService()