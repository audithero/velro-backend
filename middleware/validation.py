"""
Input validation middleware for request sanitization and security.
Following CLAUDE.md: Middleware layer for cross-cutting concerns.
"""
import re
import json
from typing import Dict, List, Any, Optional, Union
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ValidationError, Field
import html
import bleach
from email_validator import validate_email, EmailNotValidError


class ValidationConfig:
    """Configuration for request validation."""
    
    # Request size limits (in bytes)
    MAX_REQUEST_SIZE = 50 * 1024 * 1024  # 50MB for large image uploads
    MAX_JSON_SIZE = 10 * 1024 * 1024     # 10MB for JSON payloads
    MAX_FORM_SIZE = 20 * 1024 * 1024     # 20MB for form data
    MAX_URL_LENGTH = 2048                 # Max URL length
    MAX_HEADER_SIZE = 8192               # Max header size
    
    # Field length limits
    MAX_STRING_LENGTH = 10000            # Max string field length
    MAX_TEXT_LENGTH = 50000              # Max text area length
    MAX_PROMPT_LENGTH = 2000             # Max AI prompt length
    MAX_NAME_LENGTH = 200                # Max name field length
    MAX_EMAIL_LENGTH = 254               # Max email length (RFC 5321)
    MAX_PASSWORD_LENGTH = 128            # Max password length
    
    # File upload limits
    ALLOWED_IMAGE_TYPES = {
        'image/jpeg', 'image/jpg', 'image/png', 
        'image/webp', 'image/gif'
    }
    ALLOWED_FILE_EXTENSIONS = {
        '.jpg', '.jpeg', '.png', '.webp', '.gif',
        '.pdf', '.txt', '.json'
    }
    MAX_FILE_SIZE = 20 * 1024 * 1024     # 20MB per file
    
    # Content validation patterns
    SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')
    UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)
    SLUG_PATTERN = re.compile(r'^[a-z0-9-]+$')
    
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
    
    # SQL injection patterns
    SQL_INJECTION_PATTERNS = [
        r'(\b(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|EXEC|UNION)\b)',
        r'(\b(OR|AND)\b\s+\d+\s*=\s*\d+)',
        r'[\'"]\s*(OR|AND)\s+[\'"]\d+[\'"]\s*=\s*[\'"]\d+[\'"]',
        r'[\'"]\s*;\s*(SELECT|INSERT|UPDATE|DELETE|DROP)',
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
            # Use email-validator library
            valid = validate_email(email)
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
    
    @staticmethod
    def check_sql_injection(value: str) -> None:
        """Check for SQL injection patterns."""
        for pattern in ValidationConfig.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                raise ValueError("Input contains potentially malicious SQL patterns")
    
    @staticmethod
    def validate_filename(filename: str) -> str:
        """Validate and sanitize filename."""
        if not filename:
            raise ValueError("Filename cannot be empty")
        
        # Remove path separators
        filename = filename.replace('/', '').replace('\\', '').replace('..', '')
        
        # Check against safe pattern
        if not ValidationConfig.SAFE_FILENAME_PATTERN.match(filename):
            raise ValueError("Filename contains invalid characters")
        
        if len(filename) > 255:
            raise ValueError("Filename too long")
        
        return filename
    
    @staticmethod
    def validate_uuid(uuid_str: str) -> str:
        """Validate UUID format."""
        if not ValidationConfig.UUID_PATTERN.match(uuid_str):
            raise ValueError("Invalid UUID format")
        return uuid_str.lower()
    
    @staticmethod
    def validate_content_type(content_type: str, allowed_types: set) -> bool:
        """Validate content type against allowed types."""
        return content_type.lower() in {t.lower() for t in allowed_types}


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


class ValidatedString(str):
    """Custom string type with validation."""
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v, max_length: Optional[int] = None):
        if not isinstance(v, str):
            raise TypeError('string required')
        
        # Security validation
        SecurityValidator.check_dangerous_patterns(v)
        SecurityValidator.check_sql_injection(v)
        
        # Sanitize
        v = SecurityValidator.sanitize_string(v, max_length)
        
        return cls(v)


class ValidationMiddleware:
    """Middleware for comprehensive request validation."""
    
    async def __call__(self, request: Request, call_next):
        """Process request validation."""
        try:
            # Validate request size
            await self._validate_request_size(request)
            
            # Validate headers
            self._validate_headers(request)
            
            # Validate URL
            self._validate_url(request)
            
            # Process request
            response = await call_next(request)
            
            return response
            
        except ValidationError as e:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error": "validation_error",
                    "message": "Request validation failed",
                    "details": e.errors()
                }
            )
        except ValueError as e:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "invalid_input",
                    "message": str(e)
                }
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Validation middleware error: {str(e)}")
            logger.error(f"Exception type: {type(e)}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={
                    "error": "request_error",
                    "message": "Invalid request format"
                }
            )
    
    async def _validate_request_size(self, request: Request):
        """Validate request size limits."""
        content_length = request.headers.get('content-length')
        
        if content_length:
            size = int(content_length)
            
            # Check overall size limit
            if size > ValidationConfig.MAX_REQUEST_SIZE:
                raise ValueError(f"Request too large. Maximum size: {ValidationConfig.MAX_REQUEST_SIZE} bytes")
            
            # Check content-type specific limits
            content_type = request.headers.get('content-type', '').lower()
            
            if 'application/json' in content_type and size > ValidationConfig.MAX_JSON_SIZE:
                raise ValueError(f"JSON payload too large. Maximum size: {ValidationConfig.MAX_JSON_SIZE} bytes")
            
            if 'multipart/form-data' in content_type and size > ValidationConfig.MAX_FORM_SIZE:
                raise ValueError(f"Form data too large. Maximum size: {ValidationConfig.MAX_FORM_SIZE} bytes")
    
    def _validate_headers(self, request: Request):
        """Validate request headers."""
        # Check header size
        total_header_size = sum(len(k) + len(v) for k, v in request.headers.items())
        if total_header_size > ValidationConfig.MAX_HEADER_SIZE:
            raise ValueError("Request headers too large")
        
        # Validate specific headers
        user_agent = request.headers.get('user-agent', '')
        if len(user_agent) > 1000:  # Reasonable user-agent length
            raise ValueError("User-Agent header too long")
    
    def _validate_url(self, request: Request):
        """Validate URL format and length."""
        url = str(request.url)
        
        if len(url) > ValidationConfig.MAX_URL_LENGTH:
            raise ValueError(f"URL too long. Maximum length: {ValidationConfig.MAX_URL_LENGTH}")
        
        # Check for dangerous patterns in URL
        SecurityValidator.check_dangerous_patterns(url)


# Global validation middleware instance
validation_middleware = ValidationMiddleware()


# Utility functions for manual validation in endpoints
def validate_json_field(field_name: str, value: Any, max_length: Optional[int] = None) -> Any:
    """Validate a JSON field manually."""
    if isinstance(value, str):
        SecurityValidator.check_dangerous_patterns(value)
        SecurityValidator.check_sql_injection(value)
        return SecurityValidator.sanitize_string(value, max_length)
    return value


def validate_file_upload(filename: str, content_type: str, size: int) -> Dict[str, str]:
    """Validate file upload parameters."""
    # Validate filename
    clean_filename = SecurityValidator.validate_filename(filename)
    
    # Validate content type
    if not SecurityValidator.validate_content_type(content_type, ValidationConfig.ALLOWED_IMAGE_TYPES):
        raise ValueError(f"Invalid file type. Allowed types: {ValidationConfig.ALLOWED_IMAGE_TYPES}")
    
    # Validate file size
    if size > ValidationConfig.MAX_FILE_SIZE:
        raise ValueError(f"File too large. Maximum size: {ValidationConfig.MAX_FILE_SIZE} bytes")
    
    # Validate file extension
    extension = '.' + clean_filename.split('.')[-1].lower() if '.' in clean_filename else ''
    if extension not in ValidationConfig.ALLOWED_FILE_EXTENSIONS:
        raise ValueError(f"Invalid file extension. Allowed extensions: {ValidationConfig.ALLOWED_FILE_EXTENSIONS}")
    
    return {
        "filename": clean_filename,
        "content_type": content_type,
        "size": size
    }