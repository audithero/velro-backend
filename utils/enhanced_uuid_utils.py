"""
Enhanced UUID Utilities with Enterprise Security Features
Provides comprehensive UUID validation with OWASP compliance and security monitoring.
Maintains backward compatibility with existing uuid_utils.py
"""

import logging
import hashlib
import secrets
from typing import Optional, Union, Dict, Any
from uuid import UUID, uuid4
import re
from datetime import datetime

from models.authorization import ValidationContext, SecurityViolationError

logger = logging.getLogger(__name__)


class SecureUUIDValidator:
    """Enterprise-grade UUID validation with security compliance."""
    
    # Valid UUID regex pattern with strict validation
    UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.IGNORECASE)
    SIMPLE_UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    
    # Security thresholds
    MAX_VALIDATION_ATTEMPTS_PER_MINUTE = 1000
    SUSPICIOUS_PATTERN_THRESHOLD = 10
    
    _validation_attempts = {}
    _suspicious_patterns = set()
    
    @classmethod
    async def validate_uuid_format(
        cls, 
        uuid_value: Union[str, UUID, None], 
        context: ValidationContext,
        strict: bool = True,
        client_ip: Optional[str] = None
    ) -> Union[str, None]:
        """Enterprise UUID format validation with security monitoring."""
        
        if uuid_value is None:
            return None
        
        # Rate limiting check
        if client_ip:
            await cls._check_rate_limiting(client_ip)
        
        # Convert to string for validation
        uuid_str = str(uuid_value) if isinstance(uuid_value, UUID) else str(uuid_value)
        
        # Security pattern detection
        await cls._detect_security_violations(uuid_str, context, client_ip)
        
        # Format validation
        pattern = cls.UUID_PATTERN if strict else cls.SIMPLE_UUID_PATTERN
        if not pattern.match(uuid_str):
            logger.warning(f"🚨 [UUID-SECURITY] Invalid UUID format in context {context.value}: {uuid_str[:8]}...")
            return None
        
        # Entropy validation for security
        if strict and not await cls._validate_uuid_entropy(uuid_str):
            logger.warning(f"🚨 [UUID-SECURITY] Low entropy UUID detected in context {context.value}")
            return None
        
        return uuid_str
    
    @classmethod
    async def _check_rate_limiting(cls, client_ip: str) -> None:
        """Rate limiting for UUID validation requests."""
        current_minute = int(datetime.utcnow().timestamp() // 60)
        key = f"{client_ip}:{current_minute}"
        
        cls._validation_attempts[key] = cls._validation_attempts.get(key, 0) + 1
        
        if cls._validation_attempts[key] > cls.MAX_VALIDATION_ATTEMPTS_PER_MINUTE:
            raise SecurityViolationError(
                "uuid_validation_rate_limit",
                {"client_ip": client_ip, "attempts": cls._validation_attempts[key]},
                client_ip=client_ip
            )
    
    @classmethod
    async def _detect_security_violations(cls, uuid_str: str, context: ValidationContext, client_ip: Optional[str]) -> None:
        """Detect potential security violations in UUID patterns."""
        
        # Check for SQL injection patterns
        sql_patterns = ["'", '"', ';', '--', '/*', '*/', 'DROP', 'DELETE', 'UPDATE', 'INSERT']
        if any(pattern.lower() in uuid_str.lower() for pattern in sql_patterns):
            raise SecurityViolationError(
                "sql_injection_attempt",
                {"uuid_input": uuid_str[:20], "context": context.value},
                client_ip=client_ip
            )
        
        # Check for script injection patterns
        script_patterns = ['<script', 'javascript:', 'vbscript:', 'onload=', 'onerror=']
        if any(pattern.lower() in uuid_str.lower() for pattern in script_patterns):
            raise SecurityViolationError(
                "script_injection_attempt",
                {"uuid_input": uuid_str[:20], "context": context.value},
                client_ip=client_ip
            )
        
        # Check for suspicious repeated patterns
        if len(set(uuid_str.replace('-', ''))) < 8:  # Too few unique characters
            cls._suspicious_patterns.add(uuid_str)
            if len(cls._suspicious_patterns) > cls.SUSPICIOUS_PATTERN_THRESHOLD:
                logger.warning(f"🚨 [UUID-SECURITY] Suspicious pattern detected: {uuid_str[:8]}...")
    
    @classmethod
    async def _validate_uuid_entropy(cls, uuid_str: str) -> bool:
        """Validate UUID has sufficient entropy for security."""
        # Remove hyphens for analysis
        clean_uuid = uuid_str.replace('-', '')
        
        # Check character distribution
        char_counts = {}
        for char in clean_uuid:
            char_counts[char] = char_counts.get(char, 0) + 1
        
        # Calculate entropy (simplified)
        max_char_count = max(char_counts.values())
        entropy_ratio = max_char_count / len(clean_uuid)
        
        # If more than 50% of characters are the same, consider it low entropy
        return entropy_ratio < 0.5


class EnhancedUUIDUtils:
    """Enhanced UUID utility class with enterprise security features."""
    
    _secure_validator = SecureUUIDValidator()
    
    @staticmethod
    def is_valid_uuid_string(uuid_str: str, strict: bool = False) -> bool:
        """Check if string is a valid UUID format."""
        if not isinstance(uuid_str, str):
            return False
        
        pattern = SecureUUIDValidator.UUID_PATTERN if strict else SecureUUIDValidator.SIMPLE_UUID_PATTERN
        return bool(pattern.match(uuid_str))
    
    @staticmethod
    def safe_uuid_convert(value: Union[str, UUID, None]) -> Optional[UUID]:
        """Safely convert value to UUID object."""
        if value is None:
            return None
            
        if isinstance(value, UUID):
            return value
            
        if isinstance(value, str):
            try:
                if EnhancedUUIDUtils.is_valid_uuid_string(value):
                    return UUID(value)
                else:
                    logger.warning(f"⚠️ [UUID-UTILS] Invalid UUID format: {value}")
                    return None
            except ValueError as e:
                logger.warning(f"⚠️ [UUID-UTILS] UUID conversion failed for '{value}': {e}")
                return None
        
        logger.warning(f"⚠️ [UUID-UTILS] Unsupported type for UUID conversion: {type(value)}")
        return None
    
    @staticmethod
    def safe_uuid_string(value: Union[str, UUID, None]) -> Optional[str]:
        """Safely convert value to UUID string."""
        if value is None:
            return None
            
        if isinstance(value, str):
            if EnhancedUUIDUtils.is_valid_uuid_string(value):
                return value
            else:
                logger.warning(f"⚠️ [UUID-UTILS] Invalid UUID string format: {value}")
                return None
                
        if isinstance(value, UUID):
            return str(value)
        
        logger.warning(f"⚠️ [UUID-UTILS] Unsupported type for UUID string conversion: {type(value)}")
        return None
    
    @staticmethod
    async def secure_uuid_validation(
        value: Union[str, UUID, None],
        context: ValidationContext,
        strict: bool = True,
        client_ip: Optional[str] = None
    ) -> Optional[str]:
        """Enterprise-grade UUID validation with security monitoring."""
        return await SecureUUIDValidator.validate_uuid_format(
            value, context, strict, client_ip
        )
    
    @staticmethod
    def generate_secure_uuid(context: ValidationContext = ValidationContext.USER_PROFILE) -> str:
        """Generate cryptographically secure UUID with context logging."""
        new_uuid = str(uuid4())
        logger.info(f"🔐 [UUID-SECURITY] Generated secure UUID for context: {context.value}")
        return new_uuid
    
    @staticmethod
    def hash_uuid_for_logging(uuid_value: Union[str, UUID]) -> str:
        """Create a hash of UUID for secure logging (GDPR compliant)."""
        uuid_str = str(uuid_value) if isinstance(uuid_value, UUID) else str(uuid_value)
        return hashlib.sha256(uuid_str.encode()).hexdigest()[:8]
    
    @staticmethod
    async def validate_uuid_ownership(
        resource_uuid: Union[str, UUID],
        owner_uuid: Union[str, UUID],
        context: ValidationContext
    ) -> bool:
        """Validate UUID ownership with security context."""
        
        # Normalize both UUIDs
        resource_str = await EnhancedUUIDUtils.secure_uuid_validation(
            resource_uuid, context, strict=True
        )
        owner_str = await EnhancedUUIDUtils.secure_uuid_validation(
            owner_uuid, ValidationContext.USER_PROFILE, strict=True
        )
        
        if not resource_str or not owner_str:
            return False
        
        # Constant-time comparison to prevent timing attacks
        return secrets.compare_digest(resource_str, owner_str)
    
    @staticmethod
    def audit_uuid_access(uuid_value: Union[str, UUID], context: ValidationContext, 
                         user_id: Optional[str] = None, success: bool = True) -> None:
        """Audit UUID access for security monitoring."""
        hashed_uuid = EnhancedUUIDUtils.hash_uuid_for_logging(uuid_value)
        hashed_user = EnhancedUUIDUtils.hash_uuid_for_logging(user_id) if user_id else "anonymous"
        
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "context": context.value,
            "uuid_hash": hashed_uuid,
            "user_hash": hashed_user,
            "success": success,
            "audit_type": "uuid_access"
        }
        
        logger.info(f"🔍 [UUID-AUDIT] {audit_entry}")
    
    @staticmethod
    def get_validation_stats() -> Dict[str, Any]:
        """Get UUID validation statistics for monitoring."""
        return {
            "validation_attempts": len(SecureUUIDValidator._validation_attempts),
            "suspicious_patterns": len(SecureUUIDValidator._suspicious_patterns),
            "last_updated": datetime.utcnow().isoformat()
        }
    
    @staticmethod
    def validate_and_convert(value: Union[str, UUID, None], context: str = "unknown") -> UUID:
        """Validate and convert value to UUID, raising appropriate errors."""
        if value is None:
            raise ValueError(f"UUID cannot be None in context: {context}")
            
        converted = EnhancedUUIDUtils.safe_uuid_convert(value)
        if converted is None:
            raise ValueError(f"Invalid UUID format in context: {context}, value: {value}")
            
        return converted


# Global secure validator instance
secure_uuid_validator = SecureUUIDValidator()

# Backward compatibility aliases
UUIDSecurityValidator = SecureUUIDValidator
EnhancedUUIDValidator = EnhancedUUIDUtils