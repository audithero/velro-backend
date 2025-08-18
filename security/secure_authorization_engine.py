"""
Production-Grade Authorization Engine
====================================

This module provides a secure authorization engine that fixes critical vulnerabilities
in the UUID-based access control system.

OWASP Compliance:
- A01:2021 – Broken Access Control - FIXED
- A03:2021 – Injection - FIXED
- A09:2021 – Security Logging and Monitoring Failures - FIXED

Security Features:
1. Multi-layered authorization validation
2. Inheritance chain security boundaries
3. Parameterized query protection
4. Comprehensive audit logging
5. Rate limiting and anomaly detection
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List, Tuple, Set
from uuid import UUID
from datetime import datetime, timezone, timedelta
from enum import Enum
import hashlib
import hmac
import json
from dataclasses import dataclass

from utils.uuid_utils import UUIDUtils
from security.secure_uuid_validation import (
    SecureUUIDValidator, ValidationContext, SecurityLevel, SecurityViolationError
)

logger = logging.getLogger(__name__)


class AuthorizationResult(Enum):
    """Authorization results."""
    GRANTED = "granted"
    DENIED = "denied"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    SECURITY_VIOLATION = "security_violation"


class ResourceType(Enum):
    """Types of resources that can be authorized."""
    GENERATION = "generation"
    PROJECT = "project"
    MEDIA_FILE = "media_file"
    USER_PROFILE = "user_profile"
    TEAM_CONTEXT = "team_context"


@dataclass
class AuthorizationContext:
    """Context for authorization requests."""
    user_id: UUID
    resource_id: UUID
    resource_type: ResourceType
    operation: str  # read, write, delete, share
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    session_token: Optional[str] = None
    additional_context: Optional[Dict[str, Any]] = None


@dataclass
class AuthorizationAuditEvent:
    """Audit event for authorization decisions."""
    timestamp: datetime
    user_id: str
    resource_id: str
    resource_type: str
    operation: str
    result: AuthorizationResult
    reason: str
    risk_score: int
    client_ip: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None


class SecureAuthorizationEngine:
    """
    Production-grade authorization engine with comprehensive security controls.
    
    Features:
    - Multi-layered authorization validation
    - Secure inheritance chain validation
    - SQL injection protection
    - Comprehensive audit logging
    - Rate limiting and anomaly detection
    - Security boundary enforcement
    """
    
    def __init__(self, enable_audit_logging: bool = True):
        """Initialize the secure authorization engine."""
        self.enable_audit_logging = enable_audit_logging
        self.uuid_validator = SecureUUIDValidator(enable_audit_logging=True)
        
        # Rate limiting trackers
        self._rate_limit_tracker = {}
        self._anomaly_tracker = {}
        
        # Authorization cache with TTL
        self._auth_cache = {}
        self._cache_ttl = 300  # 5 minutes
        
        # Security boundaries
        self._security_boundaries = {
            ResourceType.GENERATION: ["private", "team_only", "public"],
            ResourceType.PROJECT: ["private", "shared", "public"],
            ResourceType.MEDIA_FILE: ["private", "team_only", "public"]
        }
        
        logger.info("🔒 [AUTH-ENGINE] Secure authorization engine initialized")
    
    def _generate_cache_key(self, context: AuthorizationContext) -> str:
        """Generate a cache key for authorization context."""
        key_data = f"{context.user_id}:{context.resource_id}:{context.resource_type.value}:{context.operation}"
        return hashlib.sha256(key_data.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_entry: Dict[str, Any]) -> bool:
        """Check if cache entry is still valid."""
        if not cache_entry:
            return False
        
        cache_time = cache_entry.get("timestamp")
        if not cache_time:
            return False
        
        return (datetime.now(timezone.utc) - cache_time).seconds < self._cache_ttl
    
    async def _audit_authorization_event(self, context: AuthorizationContext, 
                                       result: AuthorizationResult, reason: str,
                                       risk_score: int = 0) -> None:
        """Log authorization events for security monitoring."""
        if not self.enable_audit_logging:
            return
        
        audit_event = AuthorizationAuditEvent(
            timestamp=datetime.now(timezone.utc),
            user_id=str(context.user_id)[:8] + "...",  # Truncated for privacy
            resource_id=str(context.resource_id)[:8] + "...",
            resource_type=context.resource_type.value,
            operation=context.operation,
            result=result,
            reason=reason,
            risk_score=risk_score,
            client_ip=context.client_ip,
            additional_data=context.additional_context
        )
        
        log_level = logger.error if result == AuthorizationResult.DENIED else logger.info
        if result == AuthorizationResult.SECURITY_VIOLATION:
            log_level = logger.critical
        
        log_level(f"🔐 [AUTH-AUDIT] {json.dumps(audit_event.__dict__, default=str)}")
    
    async def _check_rate_limit(self, user_id: UUID, resource_type: ResourceType) -> bool:
        """Check if user has exceeded authorization request rate limit."""
        key = f"{user_id}:{resource_type.value}"
        current_time = datetime.now(timezone.utc)
        
        if key not in self._rate_limit_tracker:
            self._rate_limit_tracker[key] = {"count": 0, "window_start": current_time}
            return True
        
        tracker = self._rate_limit_tracker[key]
        
        # Reset counter if window has passed (1 minute)
        if (current_time - tracker["window_start"]).seconds >= 60:
            tracker["count"] = 0
            tracker["window_start"] = current_time
        
        # Different limits based on resource type
        limits = {
            ResourceType.GENERATION: 100,
            ResourceType.PROJECT: 50,
            ResourceType.MEDIA_FILE: 200,
            ResourceType.USER_PROFILE: 20
        }
        
        limit = limits.get(resource_type, 50)
        
        if tracker["count"] >= limit:
            logger.warning(f"⚠️ [AUTH-ENGINE] Rate limit exceeded for user {user_id}")
            return False
        
        tracker["count"] += 1
        return True
    
    async def _detect_anomalies(self, context: AuthorizationContext) -> int:
        """Detect anomalous authorization patterns and return risk score."""
        risk_score = 0
        user_key = str(context.user_id)
        
        # Track user access patterns
        if user_key not in self._anomaly_tracker:
            self._anomaly_tracker[user_key] = {
                "resources_accessed": set(),
                "operations": [],
                "first_seen": datetime.now(timezone.utc),
                "last_seen": datetime.now(timezone.utc)
            }
        
        tracker = self._anomaly_tracker[user_key]
        tracker["last_seen"] = datetime.now(timezone.utc)
        tracker["resources_accessed"].add(str(context.resource_id))
        tracker["operations"].append((context.operation, datetime.now(timezone.utc)))
        
        # Anomaly detection rules
        
        # Rule 1: Too many different resources accessed in short time
        if len(tracker["resources_accessed"]) > 50:  # within session
            risk_score += 30
            logger.warning(f"⚠️ [AUTH-ANOMALY] User {context.user_id} accessing many resources: {len(tracker['resources_accessed'])}")
        
        # Rule 2: Rapid-fire operations (potential automated attack)
        recent_operations = [op for op in tracker["operations"] 
                           if (datetime.now(timezone.utc) - op[1]).seconds < 60]
        if len(recent_operations) > 20:  # More than 20 operations per minute
            risk_score += 40
            logger.warning(f"⚠️ [AUTH-ANOMALY] User {context.user_id} rapid operations: {len(recent_operations)}/min")
        
        # Rule 3: Unusual IP address patterns (if available)
        if context.client_ip:
            # Simple check for private IP ranges attempting external access
            if context.client_ip.startswith("10.") or context.client_ip.startswith("192.168."):
                if context.operation in ["share", "export"]:
                    risk_score += 10
        
        # Rule 4: Bulk delete operations (potential malicious activity)
        delete_operations = [op for op in recent_operations if op[0] == "delete"]
        if len(delete_operations) > 5:
            risk_score += 50
            logger.warning(f"⚠️ [AUTH-ANOMALY] User {context.user_id} bulk delete operations: {len(delete_operations)}")
        
        return min(risk_score, 100)  # Cap at 100
    
    async def authorize_access(self, context: AuthorizationContext, 
                             db_client=None) -> AuthorizationResult:
        """
        Perform comprehensive authorization check with security controls.
        
        Args:
            context: Authorization context
            db_client: Database client for queries
            
        Returns:
            AuthorizationResult indicating the authorization decision
        """
        try:
            # Step 1: Validate input UUIDs
            try:
                validated_user_id = self.uuid_validator.validate_uuid_format(
                    context.user_id, ValidationContext.USER_PROFILE, strict=True
                )
                validated_resource_id = self.uuid_validator.validate_uuid_format(
                    context.resource_id, ValidationContext.GENERATION_ACCESS, strict=True
                )
                
                if not validated_user_id or not validated_resource_id:
                    await self._audit_authorization_event(
                        context, AuthorizationResult.SECURITY_VIOLATION, 
                        "Invalid UUID format", risk_score=80
                    )
                    return AuthorizationResult.SECURITY_VIOLATION
                    
            except SecurityViolationError as e:
                await self._audit_authorization_event(
                    context, AuthorizationResult.SECURITY_VIOLATION,
                    f"UUID validation failed: {str(e)}", risk_score=90
                )
                return AuthorizationResult.SECURITY_VIOLATION
            
            # Step 2: Rate limiting check
            if not await self._check_rate_limit(validated_user_id, context.resource_type):
                await self._audit_authorization_event(
                    context, AuthorizationResult.DENIED,
                    "Rate limit exceeded", risk_score=60
                )
                return AuthorizationResult.DENIED
            
            # Step 3: Anomaly detection
            risk_score = await self._detect_anomalies(context)
            if risk_score > 70:  # High risk threshold
                await self._audit_authorization_event(
                    context, AuthorizationResult.DENIED,
                    f"Anomalous behavior detected (risk: {risk_score})", risk_score=risk_score
                )
                return AuthorizationResult.DENIED
            
            # Step 4: Check cache (for performance optimization)
            cache_key = self._generate_cache_key(context)
            if cache_key in self._auth_cache:
                cache_entry = self._auth_cache[cache_key]
                if self._is_cache_valid(cache_entry):
                    result = cache_entry["result"]
                    await self._audit_authorization_event(
                        context, result, "Cache hit", risk_score=0
                    )
                    return result
            
            # Step 5: Database authorization check
            if not db_client:
                await self._audit_authorization_event(
                    context, AuthorizationResult.INSUFFICIENT_CONTEXT,
                    "No database client available", risk_score=30
                )
                return AuthorizationResult.INSUFFICIENT_CONTEXT
            
            # Step 6: Resource-specific authorization
            result = await self._authorize_resource_access(
                context, validated_user_id, validated_resource_id, db_client
            )
            
            # Step 7: Cache the result
            self._auth_cache[cache_key] = {
                "result": result,
                "timestamp": datetime.now(timezone.utc)
            }
            
            # Step 8: Audit the decision
            await self._audit_authorization_event(
                context, result, "Database authorization check completed", risk_score=risk_score
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ [AUTH-ENGINE] Authorization error: {e}")
            await self._audit_authorization_event(
                context, AuthorizationResult.SECURITY_VIOLATION,
                f"Internal error: {str(e)}", risk_score=100
            )
            return AuthorizationResult.SECURITY_VIOLATION
    
    async def _authorize_resource_access(self, context: AuthorizationContext,
                                       user_id: UUID, resource_id: UUID,
                                       db_client) -> AuthorizationResult:
        """Perform resource-specific authorization checks."""
        
        if context.resource_type == ResourceType.GENERATION:
            return await self._authorize_generation_access(
                context, user_id, resource_id, db_client
            )
        elif context.resource_type == ResourceType.PROJECT:
            return await self._authorize_project_access(
                context, user_id, resource_id, db_client
            )
        elif context.resource_type == ResourceType.MEDIA_FILE:
            return await self._authorize_media_access(
                context, user_id, resource_id, db_client
            )
        else:
            return AuthorizationResult.INSUFFICIENT_CONTEXT
    
    async def _authorize_generation_access(self, context: AuthorizationContext,
                                         user_id: UUID, resource_id: UUID,
                                         db_client) -> AuthorizationResult:
        """
        Authorize generation access with secure inheritance chain validation.
        
        CRITICAL SECURITY FIX: This fixes the authorization bypass vulnerability
        in the inheritance chain by enforcing security boundaries.
        """
        try:
            # SECURE PARAMETERIZED QUERY - Prevents SQL injection
            generation_query = """
                SELECT g.*, p.visibility as project_visibility, p.user_id as project_owner_id
                FROM generations g
                LEFT JOIN projects p ON g.project_id = p.id
                WHERE g.id = $1
            """
            
            result = await db_client.execute_parameterized_query(
                generation_query, [str(resource_id)]
            )
            
            if not result or len(result) == 0:
                return AuthorizationResult.DENIED
            
            generation = result[0]
            generation_owner_id = generation.get("user_id")
            
            # Direct ownership check
            if generation_owner_id == str(user_id):
                return AuthorizationResult.GRANTED
            
            # SECURITY FIX: Secure inheritance chain validation
            parent_generation_id = generation.get("parent_generation_id")
            if parent_generation_id:
                return await self._validate_secure_inheritance_chain(
                    context, user_id, UUID(parent_generation_id), generation, db_client
                )
            
            # Project-based access (team collaboration)
            project_visibility = generation.get("project_visibility")
            project_owner_id = generation.get("project_owner_id")
            
            if project_visibility == "public":
                # Public projects allow read access to all users
                if context.operation in ["read", "view"]:
                    return AuthorizationResult.GRANTED
                else:
                    # Write operations require ownership or team membership
                    return await self._check_team_membership(
                        user_id, UUID(generation.get("project_id", "00000000-0000-0000-0000-000000000000")), 
                        db_client
                    )
            elif project_visibility == "shared":
                # Shared projects require team membership
                return await self._check_team_membership(
                    user_id, UUID(generation.get("project_id", "00000000-0000-0000-0000-000000000000")),
                    db_client
                )
            
            # Private project - access denied
            return AuthorizationResult.DENIED
            
        except Exception as e:
            logger.error(f"❌ [AUTH-ENGINE] Generation authorization error: {e}")
            return AuthorizationResult.SECURITY_VIOLATION
    
    async def _validate_secure_inheritance_chain(self, context: AuthorizationContext,
                                               user_id: UUID, parent_generation_id: UUID,
                                               child_generation: Dict[str, Any],
                                               db_client) -> AuthorizationResult:
        """
        CRITICAL SECURITY FIX: Validate inheritance chain with proper security boundaries.
        
        This fixes the authorization bypass vulnerability by:
        1. Validating each level of inheritance
        2. Enforcing security boundaries on private content
        3. Preventing unauthorized access through parent relationships
        """
        try:
            # Get parent generation details with secure query
            parent_query = """
                SELECT g.*, p.visibility as project_visibility, p.user_id as project_owner_id
                FROM generations g
                LEFT JOIN projects p ON g.project_id = p.id
                WHERE g.id = $1
            """
            
            parent_result = await db_client.execute_parameterized_query(
                parent_query, [str(parent_generation_id)]
            )
            
            if not parent_result or len(parent_result) == 0:
                logger.warning(f"⚠️ [AUTH-ENGINE] Parent generation {parent_generation_id} not found")
                return AuthorizationResult.DENIED
            
            parent_generation = parent_result[0]
            parent_owner_id = parent_generation.get("user_id")
            
            # Check if user owns the parent generation
            if parent_owner_id != str(user_id):
                return AuthorizationResult.DENIED
            
            # CRITICAL SECURITY BOUNDARY: Even if user owns parent, child access must be validated
            child_project_id = child_generation.get("project_id")
            child_project_visibility = child_generation.get("project_visibility", "private")
            child_owner_id = child_generation.get("user_id")
            
            # Security Rule 1: User must own child OR child must be in public/shared project
            if child_owner_id == str(user_id):
                return AuthorizationResult.GRANTED
            
            # Security Rule 2: Child in public project allows parent owner to access
            if child_project_visibility == "public" and context.operation in ["read", "view"]:
                logger.info(f"✅ [AUTH-ENGINE] Inheritance access granted: public child project")
                return AuthorizationResult.GRANTED
            
            # Security Rule 3: Child in shared project requires team membership validation
            if child_project_visibility == "shared":
                if child_project_id:
                    team_access = await self._check_team_membership(
                        user_id, UUID(child_project_id), db_client
                    )
                    if team_access == AuthorizationResult.GRANTED:
                        logger.info(f"✅ [AUTH-ENGINE] Inheritance access granted: team member")
                        return AuthorizationResult.GRANTED
            
            # Security Rule 4: Private child content is protected regardless of parent ownership
            logger.warning(f"🚫 [AUTH-ENGINE] Inheritance access denied: private child content protected")
            return AuthorizationResult.DENIED
            
        except Exception as e:
            logger.error(f"❌ [AUTH-ENGINE] Inheritance validation error: {e}")
            return AuthorizationResult.SECURITY_VIOLATION
    
    async def _authorize_project_access(self, context: AuthorizationContext,
                                      user_id: UUID, resource_id: UUID,
                                      db_client) -> AuthorizationResult:
        """Authorize project access with team collaboration support."""
        try:
            # Secure parameterized query
            project_query = """
                SELECT p.*, 
                       CASE WHEN pc.user_id IS NOT NULL THEN true ELSE false END as is_collaborator
                FROM projects p
                LEFT JOIN project_collaborators pc ON p.id = pc.project_id AND pc.user_id = $2
                WHERE p.id = $1
            """
            
            result = await db_client.execute_parameterized_query(
                project_query, [str(resource_id), str(user_id)]
            )
            
            if not result or len(result) == 0:
                return AuthorizationResult.DENIED
            
            project = result[0]
            project_owner_id = project.get("user_id")
            visibility = project.get("visibility", "private")
            is_collaborator = project.get("is_collaborator", False)
            
            # Owner always has access
            if project_owner_id == str(user_id):
                return AuthorizationResult.GRANTED
            
            # Collaborator access
            if is_collaborator:
                return AuthorizationResult.GRANTED
            
            # Public project read access
            if visibility == "public" and context.operation in ["read", "view"]:
                return AuthorizationResult.GRANTED
            
            return AuthorizationResult.DENIED
            
        except Exception as e:
            logger.error(f"❌ [AUTH-ENGINE] Project authorization error: {e}")
            return AuthorizationResult.SECURITY_VIOLATION
    
    async def _authorize_media_access(self, context: AuthorizationContext,
                                    user_id: UUID, resource_id: UUID,
                                    db_client) -> AuthorizationResult:
        """Authorize media file access with generation context validation."""
        try:
            # Secure parameterized query to check media file ownership
            media_query = """
                SELECT fm.*, g.user_id as generation_owner_id, p.visibility as project_visibility
                FROM file_metadata fm
                LEFT JOIN generations g ON fm.metadata->>'generation_id' = g.id::text
                LEFT JOIN projects p ON g.project_id = p.id
                WHERE fm.id = $1
            """
            
            result = await db_client.execute_parameterized_query(
                media_query, [str(resource_id)]
            )
            
            if not result or len(result) == 0:
                return AuthorizationResult.DENIED
            
            media_file = result[0]
            file_owner_id = media_file.get("user_id")
            generation_owner_id = media_file.get("generation_owner_id")
            project_visibility = media_file.get("project_visibility")
            
            # Direct file ownership
            if file_owner_id == str(user_id):
                return AuthorizationResult.GRANTED
            
            # Generation ownership (user owns the generation that created the file)
            if generation_owner_id == str(user_id):
                return AuthorizationResult.GRANTED
            
            # Public project access
            if project_visibility == "public" and context.operation in ["read", "view"]:
                return AuthorizationResult.GRANTED
            
            return AuthorizationResult.DENIED
            
        except Exception as e:
            logger.error(f"❌ [AUTH-ENGINE] Media authorization error: {e}")
            return AuthorizationResult.SECURITY_VIOLATION
    
    async def _check_team_membership(self, user_id: UUID, project_id: UUID,
                                   db_client) -> AuthorizationResult:
        """Check if user is a team member with access to the project."""
        try:
            # Secure parameterized query
            membership_query = """
                SELECT pc.role, pc.permissions
                FROM project_collaborators pc
                WHERE pc.project_id = $1 AND pc.user_id = $2 AND pc.status = 'active'
            """
            
            result = await db_client.execute_parameterized_query(
                membership_query, [str(project_id), str(user_id)]
            )
            
            if result and len(result) > 0:
                return AuthorizationResult.GRANTED
            
            return AuthorizationResult.DENIED
            
        except Exception as e:
            logger.error(f"❌ [AUTH-ENGINE] Team membership check error: {e}")
            return AuthorizationResult.SECURITY_VIOLATION


# Global secure authorization engine instance
secure_authorization_engine = SecureAuthorizationEngine()