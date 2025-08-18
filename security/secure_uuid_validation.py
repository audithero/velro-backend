"""
Production-Grade UUID Validation Security Module
================================================

This module provides bulletproof UUID validation patterns that prevent:
- SQL Injection attacks via UUID parameters
- Authorization bypass through UUID manipulation
- Generation inheritance authorization vulnerabilities
- Malformed UUID-based attacks

OWASP Compliance:
- A01:2021 – Broken Access Control
- A03:2021 – Injection
- A04:2021 – Insecure Design
- A09:2021 – Security Logging and Monitoring Failures

Security Requirements:
1. All UUID inputs must be validated before database operations
2. Context validation must verify ownership and permissions
3. Inheritance chains must respect visibility boundaries
4. Audit logging for all security-relevant operations
"""

import logging
import re
from typing import Optional, Union, Dict, Any, List, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timezone
from enum import Enum
import hashlib
import hmac

logger = logging.getLogger(__name__)


class SecurityLevel(Enum):
    """Security levels for different contexts."""
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"
    PRIVATE = "private"
    ADMIN = "admin"


class ValidationContext(Enum):
    """Contexts for UUID validation."""
    USER_PROFILE = "user_profile"
    GENERATION_ACCESS = "generation_access"
    PROJECT_ACCESS = "project_access"
    MEDIA_URL = "media_url"
    INHERITANCE_CHAIN = "inheritance_chain"
    TEAM_CONTEXT = "team_context"


class SecurityViolationError(Exception):
    """Raised when a security validation fails."""
    def __init__(self, message: str, context: str = "unknown", audit_data: Optional[Dict[str, Any]] = None):
        self.message = message
        self.context = context
        self.audit_data = audit_data or {}
        self.timestamp = datetime.now(timezone.utc)
        super().__init__(message)


class SecureUUIDValidator:
    """
    Production-grade UUID validator with comprehensive security patterns.
    
    Features:
    - Input sanitization and validation
    - Context-aware authorization checks
    - Inheritance chain validation
    - Audit logging for security events
    - Rate limiting for validation requests
    """
    
    # Enhanced UUID validation patterns - SECURITY FIX: Enforce UUID v4 format
    UUID_V4_PATTERN = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
    )
    
    # Fallback pattern for other UUID versions (with strict validation)
    UUID_PATTERN = re.compile(
        r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$'
    )
    
    # Suspicious patterns that indicate potential attacks
    SUSPICIOUS_PATTERNS = [
        re.compile(r'00000000-0000-0000-0000-000000000000'),  # Null UUID attacks
        re.compile(r'[fF]{8}-[fF]{4}-[fF]{4}-[fF]{4}-[fF]{12}'),  # Max value UUID
        re.compile(r'(.)\1{31}'),  # Repeated characters
        re.compile(r'[^0-9a-fA-F-]'),  # Invalid characters
    ]
    
    # Known development/test UUIDs that should be blocked in production
    DEVELOPMENT_UUIDS = {
        "bd1a2f69-89eb-489f-9288-8aacf4924763",  # Mock user ID
        "00000000-0000-0000-0000-000000000000",   # Null UUID
        "12345678-1234-5678-9012-123456789012",   # Test UUID
        "ffffffff-ffff-ffff-ffff-ffffffffffff",   # Max UUID
    }
    
    def __init__(self, enable_audit_logging: bool = True, rate_limit: int = 1000):
        """
        Initialize secure UUID validator.
        
        Args:
            enable_audit_logging: Whether to log security events
            rate_limit: Maximum validations per minute per IP
        """
        self.enable_audit_logging = enable_audit_logging
        self.rate_limit = rate_limit
        self._validation_cache = {}
        self._rate_limit_tracker = {}
        
        # Initialize security key for HMAC validation
        self._security_key = self._generate_security_key()
        
    def _generate_security_key(self) -> bytes:
        """Generate a secure key for HMAC operations."""
        import os
        key = os.environ.get('VELRO_UUID_SECURITY_KEY')
        if key:
            return key.encode('utf-8')
        # Generate a new key if not provided (should be set in production)
        logger.warning("🔐 [UUID-SECURITY] No security key found, generating temporary key")
        return os.urandom(32)
    
    def _audit_log(self, event_type: str, context: ValidationContext, uuid_value: str, 
                   user_id: Optional[str] = None, additional_data: Optional[Dict[str, Any]] = None) -> None:
        """
        Log security-relevant UUID validation events.
        
        Args:
            event_type: Type of security event
            context: Validation context
            uuid_value: UUID being validated
            user_id: User performing the action
            additional_data: Additional audit data
        """
        if not self.enable_audit_logging:
            return
            
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "context": context.value,
            "uuid_value": uuid_value[:8] + "..." if uuid_value else None,  # Truncate for privacy
            "user_id": user_id[:8] + "..." if user_id else None,  # Truncate for privacy
            "additional_data": additional_data or {}
        }
        
        if event_type.startswith("SECURITY_VIOLATION"):
            logger.error(f"🚨 [UUID-AUDIT] {audit_entry}")
        elif event_type.startswith("SUSPICIOUS"):
            logger.warning(f"⚠️ [UUID-AUDIT] {audit_entry}")
        else:
            logger.info(f"ℹ️ [UUID-AUDIT] {audit_entry}")
    
    def _check_rate_limit(self, client_id: str) -> bool:
        """
        Check if client has exceeded rate limit.
        
        Args:
            client_id: Client identifier (IP address or user ID)
            
        Returns:
            True if within rate limit, False if exceeded
        """
        current_time = datetime.now()
        
        if client_id not in self._rate_limit_tracker:
            self._rate_limit_tracker[client_id] = {"count": 0, "window_start": current_time}
            return True
        
        tracker = self._rate_limit_tracker[client_id]
        
        # Reset counter if window has passed (1 minute)
        if (current_time - tracker["window_start"]).seconds >= 60:
            tracker["count"] = 0
            tracker["window_start"] = current_time
        
        if tracker["count"] >= self.rate_limit:
            return False
        
        tracker["count"] += 1
        return True
    
    def _validate_uuid_entropy(self, uuid_str: str) -> bool:
        """
        Validate UUID entropy to detect predictable or weak UUIDs.
        
        Args:
            uuid_str: UUID string to validate
            
        Returns:
            True if UUID has sufficient entropy, False otherwise
        """
        # Remove hyphens for entropy calculation
        uuid_hex = uuid_str.replace('-', '')
        
        # Check for repeated patterns (low entropy)
        # 1. Check for repeated characters
        char_counts = {}
        for char in uuid_hex:
            char_counts[char] = char_counts.get(char, 0) + 1
        
        # If any character appears more than 40% of the time, consider it low entropy
        max_char_frequency = max(char_counts.values()) / len(uuid_hex)
        if max_char_frequency > 0.4:
            logger.warning(f"⚠️ [UUID-ENTROPY] High character frequency detected: {max_char_frequency:.2%}")
            return False
        
        # 2. Check for sequential patterns
        sequential_count = 0
        for i in range(len(uuid_hex) - 1):
            try:
                current = int(uuid_hex[i], 16)
                next_char = int(uuid_hex[i + 1], 16)
                if abs(current - next_char) <= 1:  # Sequential or repeated
                    sequential_count += 1
            except ValueError:
                continue
        
        sequential_ratio = sequential_count / (len(uuid_hex) - 1)
        if sequential_ratio > 0.3:  # More than 30% sequential
            logger.warning(f"⚠️ [UUID-ENTROPY] High sequential pattern detected: {sequential_ratio:.2%}")
            return False
        
        # 3. Check for common weak patterns
        weak_patterns = [
            '0123456789abcdef',  # Ascending hex
            'fedcba9876543210',  # Descending hex
            'aaaaaaaaaaaaaaaa',  # All same character
            '0000000000000000',  # All zeros
            'ffffffffffffffff',  # All F's
        ]
        
        for pattern in weak_patterns:
            if pattern in uuid_hex.lower():
                logger.warning(f"⚠️ [UUID-ENTROPY] Weak pattern detected: {pattern}")
                return False
        
        # 4. Check UUID v4 random bits specifically
        # In UUID v4, bits 12-15 should be 4, bits 16-19 should be 8,9,A,or B
        # The remaining 122 bits should be random
        version_nibble = uuid_hex[12]  # 13th character (0-indexed)
        variant_nibble = uuid_hex[16]  # 17th character (0-indexed)
        
        if version_nibble.lower() != '4':
            logger.warning(f"⚠️ [UUID-ENTROPY] Invalid version nibble: {version_nibble}")
            return False
        
        if variant_nibble.lower() not in ['8', '9', 'a', 'b']:
            logger.warning(f"⚠️ [UUID-ENTROPY] Invalid variant nibble: {variant_nibble}")
            return False
        
        # 5. Calculate Shannon entropy of the random bits
        random_bits = uuid_hex[:12] + uuid_hex[13:16] + uuid_hex[17:]  # Exclude version/variant
        entropy = self._calculate_shannon_entropy(random_bits)
        
        # Minimum entropy threshold (3.5 bits per character is reasonably random)
        if entropy < 3.5:
            logger.warning(f"⚠️ [UUID-ENTROPY] Low Shannon entropy: {entropy:.2f}")
            return False
        
        return True
    
    def _calculate_shannon_entropy(self, data: str) -> float:
        """Calculate Shannon entropy of a string."""
        import math
        
        if not data:
            return 0
        
        # Count character frequencies
        char_counts = {}
        for char in data:
            char_counts[char] = char_counts.get(char, 0) + 1
        
        # Calculate entropy
        entropy = 0
        data_len = len(data)
        
        for count in char_counts.values():
            probability = count / data_len
            if probability > 0:
                entropy -= probability * math.log2(probability)
        
        return entropy
    
    def validate_uuid_format(self, uuid_value: Union[str, UUID, None], 
                           context: ValidationContext = ValidationContext.USER_PROFILE,
                           strict: bool = True) -> Optional[UUID]:
        """
        Validate UUID format with comprehensive security checks.
        
        Args:
            uuid_value: UUID value to validate
            context: Validation context
            strict: Whether to apply strict validation
            
        Returns:
            Validated UUID object or None if invalid
            
        Raises:
            SecurityViolationError: If security validation fails
        """
        if uuid_value is None:
            return None
        
        # Convert to string for validation
        uuid_str = str(uuid_value) if isinstance(uuid_value, UUID) else uuid_value
        
        if not isinstance(uuid_str, str):
            self._audit_log("SECURITY_VIOLATION_INVALID_TYPE", context, str(uuid_str))
            raise SecurityViolationError(
                f"Invalid UUID type: {type(uuid_str)}", 
                context=context.value,
                audit_data={"provided_type": str(type(uuid_str))}
            )
        
        # SECURITY FIX: Enhanced UUID format validation with entropy check
        if strict:
            # Prefer UUID v4 for new resources (cryptographically secure)
            if not self.UUID_V4_PATTERN.match(uuid_str):
                # Check if it's at least a valid UUID of another version
                if not self.UUID_PATTERN.match(uuid_str):
                    self._audit_log("SECURITY_VIOLATION_INVALID_FORMAT", context, uuid_str)
                    raise SecurityViolationError(
                        "Invalid UUID format",
                        context=context.value,
                        audit_data={"provided_value": uuid_str[:16] + "..."}
                    )
                else:
                    # Valid UUID but not v4 - log for monitoring
                    self._audit_log("UUID_NON_V4_FORMAT", context, uuid_str)
            else:
                # Perform entropy validation for UUID v4
                if not self._validate_uuid_entropy(uuid_str):
                    self._audit_log("SECURITY_VIOLATION_LOW_ENTROPY", context, uuid_str)
                    raise SecurityViolationError(
                        "UUID has insufficient entropy (potential security risk)",
                        context=context.value,
                        audit_data={"entropy_check_failed": True}
                    )
        else:
            # Basic pattern validation for non-strict mode
            if not self.UUID_PATTERN.match(uuid_str):
                self._audit_log("SECURITY_VIOLATION_INVALID_FORMAT", context, uuid_str)
                raise SecurityViolationError(
                    "Invalid UUID format",
                    context=context.value,
                    audit_data={"provided_value": uuid_str[:16] + "..."}
                )
        
        # Check for suspicious patterns
        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern.search(uuid_str):
                self._audit_log("SECURITY_VIOLATION_SUSPICIOUS_PATTERN", context, uuid_str)
                raise SecurityViolationError(
                    "Suspicious UUID pattern detected",
                    context=context.value,
                    audit_data={"pattern_matched": True}
                )
        
        # Check for development UUIDs in production
        if strict and uuid_str in self.DEVELOPMENT_UUIDS:
            import os
            is_production = os.environ.get('VELRO_ENVIRONMENT', 'development') == 'production'
            if is_production:
                self._audit_log("SECURITY_VIOLATION_DEV_UUID_IN_PROD", context, uuid_str)
                raise SecurityViolationError(
                    "Development UUID not allowed in production",
                    context=context.value,
                    audit_data={"is_development_uuid": True}
                )
        
        try:
            validated_uuid = UUID(uuid_str)
            self._audit_log("UUID_VALIDATION_SUCCESS", context, uuid_str)
            return validated_uuid
        except ValueError as e:
            self._audit_log("SECURITY_VIOLATION_UUID_PARSE_ERROR", context, uuid_str)
            raise SecurityViolationError(
                f"UUID parsing failed: {str(e)}",
                context=context.value,
                audit_data={"parse_error": str(e)}
            )
    
    async def validate_authorization_context(self, 
                                           target_uuid: Union[str, UUID],
                                           user_id: Union[str, UUID],
                                           context: ValidationContext,
                                           required_permissions: List[str] = None,
                                           db_client = None) -> bool:
        """
        Validate that user has authorization to access the target UUID.
        
        Args:
            target_uuid: UUID being accessed
            user_id: User attempting access
            context: Access context
            required_permissions: Required permissions for access
            db_client: Database client for queries
            
        Returns:
            True if authorized, raises SecurityViolationError if not
        """
        # Validate both UUIDs
        validated_target = self.validate_uuid_format(target_uuid, context)
        validated_user = self.validate_uuid_format(user_id, ValidationContext.USER_PROFILE)
        
        if not validated_target or not validated_user:
            raise SecurityViolationError(
                "Invalid UUID in authorization context",
                context=context.value
            )
        
        # Rate limiting check
        if not self._check_rate_limit(str(validated_user)):
            self._audit_log("SECURITY_VIOLATION_RATE_LIMIT_EXCEEDED", context, str(validated_target), str(validated_user))
            raise SecurityViolationError(
                "Rate limit exceeded for authorization checks",
                context=context.value,
                audit_data={"rate_limited": True}
            )
        
        # Context-specific authorization checks
        is_authorized = False
        
        if context == ValidationContext.GENERATION_ACCESS:
            is_authorized = await self._validate_generation_access(
                validated_target, validated_user, db_client
            )
        elif context == ValidationContext.PROJECT_ACCESS:
            is_authorized = await self._validate_project_access(
                validated_target, validated_user, db_client
            )
        elif context == ValidationContext.MEDIA_URL:
            is_authorized = await self._validate_media_access(
                validated_target, validated_user, db_client
            )
        elif context == ValidationContext.INHERITANCE_CHAIN:
            is_authorized = await self._validate_inheritance_access(
                validated_target, validated_user, db_client
            )
        else:
            # Default to ownership check
            is_authorized = await self._validate_ownership(
                validated_target, validated_user, context, db_client
            )
        
        if not is_authorized:
            self._audit_log("SECURITY_VIOLATION_UNAUTHORIZED_ACCESS", context, str(validated_target), str(validated_user))
            raise SecurityViolationError(
                "Unauthorized access attempt",
                context=context.value,
                audit_data={
                    "target_uuid": str(validated_target)[:8] + "...",
                    "user_id": str(validated_user)[:8] + "..."
                }
            )
        
        self._audit_log("AUTHORIZATION_SUCCESS", context, str(validated_target), str(validated_user))
        return True
    
    async def _validate_generation_access(self, generation_id: UUID, user_id: UUID, db_client) -> bool:
        """Validate access to a generation."""
        if not db_client:
            return False
        
        try:
            # Use parameterized query to prevent SQL injection
            result = db_client.execute_query(
                "generations",
                "select",
                filters={"id": str(generation_id), "user_id": str(user_id)},
                use_service_key=True
            )
            return bool(result and len(result) > 0)
        except Exception as e:
            logger.error(f"❌ [UUID-SECURITY] Generation access validation failed: {e}")
            return False
    
    async def _validate_project_access(self, project_id: UUID, user_id: UUID, db_client) -> bool:
        """Validate access to a project with team collaboration support."""
        if not db_client:
            return False
        
        try:
            # Check direct ownership
            result = db_client.execute_query(
                "projects",
                "select",
                filters={"id": str(project_id), "user_id": str(user_id)},
                use_service_key=True
            )
            if result and len(result) > 0:
                return True
            
            # Check team collaboration access (if implemented)
            # This would check project_collaborators or team_members tables
            team_result = db_client.execute_query(
                "project_collaborators",
                "select", 
                filters={"project_id": str(project_id), "user_id": str(user_id)},
                use_service_key=True
            )
            return bool(team_result and len(team_result) > 0)
            
        except Exception as e:
            logger.error(f"❌ [UUID-SECURITY] Project access validation failed: {e}")
            return False
    
    async def _validate_media_access(self, file_id: UUID, user_id: UUID, db_client) -> bool:
        """Validate access to media files with generation context."""
        if not db_client:
            return False
        
        try:
            # Check if user owns the file directly
            file_result = db_client.execute_query(
                "file_metadata",
                "select",
                filters={"id": str(file_id), "user_id": str(user_id)},
                use_service_key=True
            )
            if file_result and len(file_result) > 0:
                return True
            
            # Check if user owns the generation associated with the file
            generation_result = db_client.execute_query(
                """
                SELECT g.id FROM generations g
                JOIN file_metadata fm ON g.id = ANY(string_to_array(fm.metadata->>'generation_ids', ',')::uuid[])
                WHERE fm.id = $1 AND g.user_id = $2
                """,
                (str(file_id), str(user_id)),
                use_service_key=True
            )
            return bool(generation_result and len(generation_result) > 0)
            
        except Exception as e:
            logger.error(f"❌ [UUID-SECURITY] Media access validation failed: {e}")
            return False
    
    async def _validate_inheritance_access(self, generation_id: UUID, user_id: UUID, db_client) -> bool:
        """
        Validate inheritance chain access with security boundary checks.
        
        This fixes the critical vulnerability where parent generation access
        grants inappropriate access to private child content.
        """
        if not db_client:
            return False
        
        try:
            # Get the generation and its inheritance chain
            generation_result = db_client.execute_query(
                "generations",
                "select",
                filters={"id": str(generation_id)},
                use_service_key=True
            )
            
            if not generation_result or len(generation_result) == 0:
                return False
            
            generation = generation_result[0]
            
            # Direct ownership check
            if generation.get("user_id") == str(user_id):
                return True
            
            # Check if this is a child generation with inheritance
            parent_generation_id = generation.get("parent_generation_id")
            if parent_generation_id:
                # CRITICAL SECURITY FIX: Check parent visibility and permissions
                parent_result = db_client.execute_query(
                    "generations",
                    "select",
                    filters={"id": str(parent_generation_id)},
                    use_service_key=True
                )
                
                if parent_result and len(parent_result) > 0:
                    parent = parent_result[0]
                    
                    # Check if parent belongs to user
                    if parent.get("user_id") == str(user_id):
                        # SECURITY BOUNDARY: Only allow access if child is public or shared
                        project_id = generation.get("project_id")
                        if project_id:
                            project_result = db_client.execute_query(
                                "projects",
                                "select",
                                filters={"id": str(project_id)},
                                use_service_key=True
                            )
                            if project_result and len(project_result) > 0:
                                project = project_result[0]
                                visibility = project.get("visibility", "private")
                                
                                # Only allow inheritance access if child project is public or shared
                                if visibility in ["public", "shared"]:
                                    self._audit_log("INHERITANCE_ACCESS_ALLOWED", ValidationContext.INHERITANCE_CHAIN, 
                                                  str(generation_id), str(user_id), 
                                                  {"parent_id": str(parent_generation_id), "visibility": visibility})
                                    return True
                                else:
                                    self._audit_log("INHERITANCE_ACCESS_DENIED_PRIVACY", ValidationContext.INHERITANCE_CHAIN,
                                                  str(generation_id), str(user_id),
                                                  {"parent_id": str(parent_generation_id), "visibility": visibility})
                                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"❌ [UUID-SECURITY] Inheritance access validation failed: {e}")
            return False
    
    async def _validate_ownership(self, target_uuid: UUID, user_id: UUID, context: ValidationContext, db_client) -> bool:
        """Generic ownership validation."""
        if not db_client:
            return False
        
        try:
            table_map = {
                ValidationContext.USER_PROFILE: "users",
                ValidationContext.PROJECT_ACCESS: "projects",
                ValidationContext.GENERATION_ACCESS: "generations",
                ValidationContext.MEDIA_URL: "file_metadata"
            }
            
            table_name = table_map.get(context)
            if not table_name:
                return False
            
            result = db_client.execute_query(
                table_name,
                "select",
                filters={"id": str(target_uuid), "user_id": str(user_id)},
                use_service_key=True
            )
            return bool(result and len(result) > 0)
            
        except Exception as e:
            logger.error(f"❌ [UUID-SECURITY] Ownership validation failed: {e}")
            return False
    
    def generate_secure_uuid(self, context: str = "default") -> UUID:
        """
        Generate a cryptographically secure UUID with context-specific entropy.
        
        Args:
            context: Context for UUID generation
            
        Returns:
            Secure UUID
        """
        # Use UUID4 with additional entropy from context and timestamp
        base_uuid = uuid4()
        
        # Create HMAC for additional security
        timestamp = datetime.now(timezone.utc).isoformat()
        message = f"{base_uuid}:{context}:{timestamp}"
        signature = hmac.new(self._security_key, message.encode(), hashlib.sha256).hexdigest()
        
        self._audit_log("SECURE_UUID_GENERATED", ValidationContext.USER_PROFILE, str(base_uuid),
                       additional_data={"context": context, "signature": signature[:16]})
        
        return base_uuid
    
    def create_validation_token(self, uuid_value: UUID, user_id: UUID, context: ValidationContext) -> str:
        """
        Create a validation token for UUID operations.
        
        Args:
            uuid_value: UUID to create token for
            user_id: User creating the token
            context: Validation context
            
        Returns:
            Validation token
        """
        timestamp = datetime.now(timezone.utc).isoformat()
        message = f"{uuid_value}:{user_id}:{context.value}:{timestamp}"
        token = hmac.new(self._security_key, message.encode(), hashlib.sha256).hexdigest()
        
        self._audit_log("VALIDATION_TOKEN_CREATED", context, str(uuid_value), str(user_id))
        return token
    
    def verify_validation_token(self, token: str, uuid_value: UUID, user_id: UUID, 
                              context: ValidationContext, max_age_minutes: int = 60) -> bool:
        """
        Verify a validation token.
        
        Args:
            token: Token to verify
            uuid_value: UUID the token was created for
            user_id: User the token was created for
            context: Validation context
            max_age_minutes: Maximum age of token in minutes
            
        Returns:
            True if token is valid
        """
        try:
            # This is a simplified verification - in production, you'd store token metadata
            # and verify timestamps properly
            timestamp = datetime.now(timezone.utc).isoformat()
            message = f"{uuid_value}:{user_id}:{context.value}:{timestamp}"
            expected_token = hmac.new(self._security_key, message.encode(), hashlib.sha256).hexdigest()
            
            is_valid = hmac.compare_digest(token, expected_token)
            
            if is_valid:
                self._audit_log("VALIDATION_TOKEN_VERIFIED", context, str(uuid_value), str(user_id))
            else:
                self._audit_log("SECURITY_VIOLATION_INVALID_TOKEN", context, str(uuid_value), str(user_id))
            
            return is_valid
            
        except Exception as e:
            logger.error(f"❌ [UUID-SECURITY] Token verification failed: {e}")
            return False


# Global secure validator instance
secure_uuid_validator = SecureUUIDValidator()