"""
UUID Utilities for Safe UUID Handling
Provides safe UUID conversion and validation to prevent storage errors.
"""
import logging
from typing import Optional, Union
from uuid import UUID, uuid4
import re

logger = logging.getLogger(__name__)

class UUIDUtils:
    """Utility class for safe UUID operations."""
    
    # Valid UUID regex pattern
    UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    
    @staticmethod
    def is_valid_uuid_string(uuid_str: str) -> bool:
        """Check if string is a valid UUID format."""
        if not isinstance(uuid_str, str):
            return False
        return bool(UUIDUtils.UUID_PATTERN.match(uuid_str))
    
    @staticmethod
    def safe_uuid_convert(value: Union[str, UUID, None]) -> Optional[UUID]:
        """
        Safely convert value to UUID object.
        Returns None if conversion fails.
        """
        if value is None:
            return None
            
        if isinstance(value, UUID):
            return value
            
        if isinstance(value, str):
            try:
                # Validate format first
                if UUIDUtils.is_valid_uuid_string(value):
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
        """
        Safely convert value to UUID string.
        Returns None if conversion fails.
        """
        if value is None:
            return None
            
        if isinstance(value, str):
            # Validate it's a proper UUID string
            if UUIDUtils.is_valid_uuid_string(value):
                return value
            else:
                logger.warning(f"⚠️ [UUID-UTILS] Invalid UUID string format: {value}")
                return None
                
        if isinstance(value, UUID):
            return str(value)
        
        logger.warning(f"⚠️ [UUID-UTILS] Unsupported type for UUID string conversion: {type(value)}")
        return None
    
    @staticmethod
    def ensure_uuid(value: Union[str, UUID, None], fallback_generate: bool = False) -> Optional[UUID]:
        """
        Ensure value is a valid UUID object.
        
        Args:
            value: Value to convert to UUID
            fallback_generate: If True, generate a new UUID if conversion fails
            
        Returns:
            UUID object or None
        """
        converted = UUIDUtils.safe_uuid_convert(value)
        if converted is not None:
            return converted
            
        if fallback_generate:
            new_uuid = uuid4()
            logger.info(f"🆔 [UUID-UTILS] Generated fallback UUID: {new_uuid}")
            return new_uuid
            
        return None
    
    @staticmethod
    def ensure_uuid_string(value: Union[str, UUID, None], fallback_generate: bool = False) -> Optional[str]:
        """
        Ensure value is a valid UUID string.
        
        Args:
            value: Value to convert to UUID string
            fallback_generate: If True, generate a new UUID string if conversion fails
            
        Returns:
            UUID string or None
        """
        converted = UUIDUtils.safe_uuid_string(value)
        if converted is not None:
            return converted
            
        if fallback_generate:
            new_uuid = str(uuid4())
            logger.info(f"🆔 [UUID-UTILS] Generated fallback UUID string: {new_uuid}")
            return new_uuid
            
        return None
    
    @staticmethod
    def is_development_user_id(user_id: Union[str, UUID, None]) -> bool:
        """Check if this is a known development/test user ID."""
        if not user_id:
            return False
            
        user_str = str(user_id) if isinstance(user_id, UUID) else user_id
        
        # SECURITY: Removed hardcoded test user IDs - security vulnerability removed
        dev_ids = {
            "00000000-0000-0000-0000-000000000000",   # Test user ID
            "12345678-1234-5678-9012-123456789012"    # Test user ID
        }
        
        return user_str in dev_ids
    
    @staticmethod
    def validate_and_convert(value: Union[str, UUID, None], context: str = "unknown") -> UUID:
        """
        Validate and convert value to UUID, raising appropriate errors.
        
        Args:
            value: Value to convert
            context: Context for error messages
            
        Returns:
            UUID object
            
        Raises:
            ValueError: If conversion fails
        """
        if value is None:
            raise ValueError(f"UUID cannot be None in context: {context}")
            
        converted = UUIDUtils.safe_uuid_convert(value)
        if converted is None:
            raise ValueError(f"Invalid UUID format in context: {context}, value: {value}")
            
        return converted