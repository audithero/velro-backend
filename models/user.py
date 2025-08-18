"""
User model schemas for authentication and user management.
Following CLAUDE.md: Strict validation and security measures.
"""
from pydantic import BaseModel, EmailStr, Field, validator, HttpUrl
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
import re

from utils.validation import SecurityValidator, ValidationConfig, EnhancedBaseModel


class UserBase(EnhancedBaseModel):
    """Base user model with common fields."""
    email: EmailStr = Field(..., max_length=ValidationConfig.MAX_EMAIL_LENGTH)
    full_name: Optional[str] = Field(None, max_length=ValidationConfig.MAX_NAME_LENGTH)
    avatar_url: Optional[HttpUrl] = None
    is_active: bool = True
    
    @validator('email')
    def validate_email(cls, v):
        """Enhanced email validation."""
        return SecurityValidator.validate_email_address(v)
    
    @validator('full_name')
    def validate_full_name(cls, v):
        """Validate and sanitize full name."""
        if v is None or v == "":
            return v
        
        # Check for dangerous patterns
        SecurityValidator.check_dangerous_patterns(v)
        
        # Sanitize and validate length
        clean_name = SecurityValidator.sanitize_string(v, ValidationConfig.MAX_NAME_LENGTH)
        
        # Check for valid name pattern (letters, spaces, hyphens, apostrophes)
        # Allow empty string after sanitization
        if clean_name and not re.match(r"^[a-zA-Z\s\-'\.]+$", clean_name):
            raise ValueError("Full name contains invalid characters")
        
        return clean_name
    
    @validator('avatar_url')
    def validate_avatar_url(cls, v):
        """Validate avatar URL."""
        if v is None:
            return v
        
        # Ensure HTTPS for security
        if str(v).startswith('http://'):
            raise ValueError("Avatar URL must use HTTPS")
        
        return v


class UserCreate(UserBase):
    """User creation model with enhanced password validation."""
    password: str = Field(
        ..., 
        min_length=8, 
        max_length=ValidationConfig.MAX_PASSWORD_LENGTH,
        description="Password must be 8-128 characters with at least one letter and one number"
    )
    confirm_password: Optional[str] = Field(None, description="Password confirmation")
    
    @validator('password')
    def validate_password(cls, v):
        """Enhanced password validation."""
        return SecurityValidator.validate_password(v)
    
    @validator('confirm_password')
    def validate_password_match(cls, v, values):
        """Ensure passwords match if confirmation provided."""
        if v is not None and 'password' in values and v != values['password']:
            raise ValueError("Password confirmation does not match")
        return v
    
    model_config = {"exclude": {"confirm_password"}}


class UserUpdate(EnhancedBaseModel):
    """User update model with validation."""
    full_name: Optional[str] = Field(None, max_length=ValidationConfig.MAX_NAME_LENGTH)
    avatar_url: Optional[HttpUrl] = None
    
    @validator('full_name')
    def validate_full_name(cls, v):
        """Validate and sanitize full name."""
        if v is None or v == "":
            return v
        
        SecurityValidator.check_dangerous_patterns(v)
        clean_name = SecurityValidator.sanitize_string(v, ValidationConfig.MAX_NAME_LENGTH)
        
        # Allow empty string after sanitization
        if clean_name and not re.match(r"^[a-zA-Z\s\-'\.]+$", clean_name):
            raise ValueError("Full name contains invalid characters")
        
        return clean_name
    
    @validator('avatar_url')
    def validate_avatar_url(cls, v):
        """Validate avatar URL."""
        if v is None:
            return v
        
        if str(v).startswith('http://'):
            raise ValueError("Avatar URL must use HTTPS")
        
        return v


class User(EnhancedBaseModel):
    """Internal user model matching database schema (for backend only)."""
    id: UUID
    email: Optional[str] = None  # From auth.users
    display_name: Optional[str] = Field(None, max_length=ValidationConfig.MAX_NAME_LENGTH)
    avatar_url: Optional[HttpUrl] = None
    credits_balance: int = Field(..., ge=0, description="User credit balance") 
    role: str = Field(..., max_length=50, description="User role")
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Additional fields that may come from the database view
    email_confirmed_at: Optional[datetime] = None
    phone: Optional[str] = None
    phone_confirmed_at: Optional[datetime] = None
    
    @validator('display_name')
    def validate_display_name(cls, v):
        """Validate and sanitize display name."""
        if v is None or v == "":
            return v
        
        SecurityValidator.check_dangerous_patterns(v)
        clean_name = SecurityValidator.sanitize_string(v, ValidationConfig.MAX_NAME_LENGTH)
        
        if clean_name and not re.match(r"^[a-zA-Z\s\-'\.]+$", clean_name):
            raise ValueError("Display name contains invalid characters")
        
        return clean_name
    
    @validator('role')
    def validate_role(cls, v):
        """Validate user role."""
        SecurityValidator.check_dangerous_patterns(v)
        return SecurityValidator.sanitize_string(v, 50)

    model_config = {
        "from_attributes": True, 
        "extra": "allow",
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class UserResponse(EnhancedBaseModel):
    """User response model matching actual database schema."""
    id: UUID
    email: Optional[str] = None  # From auth.users, not public.users
    display_name: Optional[str] = Field(None, max_length=ValidationConfig.MAX_NAME_LENGTH)
    avatar_url: Optional[HttpUrl] = None
    credits_balance: int = Field(..., ge=0, description="User credit balance") 
    role: str = Field(..., max_length=50, description="User role")
    created_at: datetime
    updated_at: Optional[datetime] = None
    # Additional fields that may come from the database view
    email_confirmed_at: Optional[datetime] = None
    phone: Optional[str] = None
    phone_confirmed_at: Optional[datetime] = None
    
    @validator('display_name')
    def validate_display_name(cls, v):
        """Validate and sanitize display name."""
        if v is None or v == "":
            return v
        
        SecurityValidator.check_dangerous_patterns(v)
        clean_name = SecurityValidator.sanitize_string(v, ValidationConfig.MAX_NAME_LENGTH)
        
        # Allow empty string after sanitization
        if clean_name and not re.match(r"^[a-zA-Z\s\-'\.]+$", clean_name):
            raise ValueError("Display name contains invalid characters")
        
        return clean_name
    
    @validator('role')
    def validate_role(cls, v):
        """Validate user role."""
        SecurityValidator.check_dangerous_patterns(v)
        return SecurityValidator.sanitize_string(v, 50)
    
    @validator('avatar_url')
    def validate_avatar_url(cls, v):
        """Validate avatar URL."""
        if v is None:
            return v
        
        if str(v).startswith('http://'):
            raise ValueError("Avatar URL must use HTTPS")
        
        return v

    model_config = {
        "from_attributes": True, 
        "extra": "allow",
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class UserLogin(EnhancedBaseModel):
    """User login model with validation."""
    email: EmailStr = Field(..., max_length=ValidationConfig.MAX_EMAIL_LENGTH)
    password: str = Field(..., min_length=1, max_length=ValidationConfig.MAX_PASSWORD_LENGTH)
    remember_me: bool = Field(False, description="Keep user logged in longer")
    
    @validator('email')
    def validate_email(cls, v):
        """Enhanced email validation."""
        return SecurityValidator.validate_email_address(v)
    
    @validator('password')
    def validate_password_not_empty(cls, v):
        """Ensure password is not empty."""
        if not v or not v.strip():
            raise ValueError("Password cannot be empty")
        return v


class PasswordReset(EnhancedBaseModel):
    """Password reset request model."""
    email: EmailStr = Field(..., max_length=ValidationConfig.MAX_EMAIL_LENGTH)
    
    @validator('email')
    def validate_email(cls, v):
        """Enhanced email validation."""
        return SecurityValidator.validate_email_address(v)


class PasswordResetConfirm(EnhancedBaseModel):
    """Password reset confirmation model."""
    token: str = Field(..., min_length=1, max_length=500)
    new_password: str = Field(
        ..., 
        min_length=8, 
        max_length=ValidationConfig.MAX_PASSWORD_LENGTH
    )
    confirm_password: str = Field(..., min_length=8)
    
    @validator('token')
    def validate_token(cls, v):
        """Validate reset token."""
        SecurityValidator.check_dangerous_patterns(v)
        return v.strip()
    
    @validator('new_password')
    def validate_new_password(cls, v):
        """Enhanced password validation."""
        return SecurityValidator.validate_password(v)
    
    @validator('confirm_password')
    def validate_password_match(cls, v, values):
        """Ensure passwords match."""
        if 'new_password' in values and v != values['new_password']:
            raise ValueError("Password confirmation does not match")
        return v


class Token(EnhancedBaseModel):
    """JWT token response model."""
    access_token: str = Field(..., min_length=1)
    token_type: str = Field("bearer", pattern="^bearer$")
    expires_in: int = Field(..., gt=0, le=86400)  # Max 24 hours
    refresh_token: Optional[str] = None
    user: UserResponse
    
    @validator('access_token')
    def validate_access_token(cls, v):
        """Validate access token format."""
        if not v or not v.strip():
            raise ValueError("Access token cannot be empty")
        return v.strip()


class TokenRefresh(EnhancedBaseModel):
    """Token refresh request model."""
    refresh_token: str = Field(..., min_length=1)
    
    @validator('refresh_token')
    def validate_refresh_token(cls, v):
        """Validate refresh token."""
        if not v or not v.strip():
            raise ValueError("Refresh token cannot be empty")
        return v.strip()