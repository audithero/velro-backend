"""
Validation utilities for user models and security.
Following CLAUDE.md: Pure validation functions without middleware dependencies.
"""
import re
from typing import Optional
from pydantic import BaseModel
import html
import bleach
from email_validator import validate_email, EmailNotValidError


class ValidationConfig:
    """Configuration for request validation."""
    
    # Field length limits
    MAX_STRING_LENGTH = 10000            # Max string field length
    MAX_TEXT_LENGTH = 50000              # Max text area length
    MAX_PROMPT_LENGTH = 2000             # Max AI prompt length
    MAX_NAME_LENGTH = 200                # Max name field length
    MAX_EMAIL_LENGTH = 254               # Max email length (RFC 5321)
    MAX_PASSWORD_LENGTH = 128            # Max password length
    
    # Dangerous patterns to block
    DANGEROUS_PATTERNS = [
        r'<script[^>]*>.*?</script>',
        r'javascript:',
        r'data:text/html',
        r'vbscript:',
        r'on\w+\s*=',
        r'<iframe[^>]*>.*?</iframe>',
        r'<object[^>]*>.*?</object>',
        r'<embed[^>]*>.*?</embed>',
    ]


class SecurityValidator:
    """Security validation utilities."""
    
    @staticmethod
    def sanitize_string(value: str, max_length: Optional[int] = None) -> str:
        """Sanitize string input to prevent XSS and other attacks."""
        if not isinstance(value, str):
            raise ValueError("Value must be a string")
        
        # HTML escape
        value = html.escape(value, quote=True)
        
        # Clean with bleach (remove all HTML tags)
        value = bleach.clean(value, tags=[], attributes={}, strip=True)
        
        # Length validation
        if max_length and len(value) > max_length:
            raise ValueError(f"String too long. Maximum length: {max_length}")
        
        return value.strip()
    
    @staticmethod
    def validate_email_address(email: str) -> str:
        """Validate and normalize email address."""
        try:
            # Use email-validator library with test mode for development
            valid = validate_email(email, check_deliverability=False)  # Disable deliverability check for testing
            return valid.email.lower()
        except EmailNotValidError as e:
            raise ValueError(f"Invalid email address: {str(e)}")
    
    @staticmethod
    def validate_password(password: str) -> str:
        """Validate password strength."""
        if not isinstance(password, str):
            raise ValueError("Password must be a string")
        
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters long")
        
        if len(password) > ValidationConfig.MAX_PASSWORD_LENGTH:
            raise ValueError(f"Password too long. Maximum length: {ValidationConfig.MAX_PASSWORD_LENGTH}")
        
        # Check for at least one letter and one number
        if not re.search(r'[a-zA-Z]', password):
            raise ValueError("Password must contain at least one letter")
        
        if not re.search(r'\d', password):
            raise ValueError("Password must contain at least one number")
        
        return password
    
    @staticmethod
    def check_dangerous_patterns(value: str) -> None:
        """Check for dangerous patterns in input."""
        for pattern in ValidationConfig.DANGEROUS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                raise ValueError("Input contains dangerous content")


class EnhancedBaseModel(BaseModel):
    """Enhanced Pydantic base model with security validation."""
    
    model_config = {
        # Strict validation - updated for Pydantic V2
        "validate_assignment": True,
        "use_enum_values": True,
        "validate_default": True,  # Renamed from validate_all
        "extra": "forbid",  # Reject extra fields
        "str_strip_whitespace": True,
        "str_min_length": 0,
        "str_to_lower": False,  # Renamed from anystr_lower
        "protected_namespaces": ()  # Disable protected namespace warnings
    }