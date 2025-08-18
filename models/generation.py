"""
Generation model schemas for AI generation requests and responses.
Following CLAUDE.md: Strict validation and security measures.
"""
from pydantic import BaseModel, Field, HttpUrl, validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from uuid import UUID
from enum import Enum
import re

from middleware.validation import SecurityValidator, ValidationConfig, EnhancedBaseModel


class GenerationStatus(str, Enum):
    """Generation status enum."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationType(str, Enum):
    """Generation type enum."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class GenerationBase(EnhancedBaseModel):
    """Base generation model with validation."""
    model_id: str = Field(..., min_length=1, max_length=100)
    prompt: str = Field(..., min_length=1, max_length=ValidationConfig.MAX_PROMPT_LENGTH)
    negative_prompt: Optional[str] = Field(None, max_length=1000)
    reference_image_url: Optional[HttpUrl] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    project_id: Optional[UUID] = None
    
    # Team collaboration fields
    parent_generation_id: Optional[UUID] = None
    team_context_id: Optional[UUID] = None
    collaboration_intent: Optional[str] = Field(None, pattern=r'^(original|improve|iterate|fork|remix)$')
    change_description: Optional[str] = Field(None, max_length=1000)
    
    @validator('model_id')
    def validate_model_id(cls, v):
        """Validate model ID format for FAL.ai and other providers."""
        SecurityValidator.check_dangerous_patterns(v)
        
        # Model IDs should be alphanumeric with hyphens/underscores/periods/forward slashes (for FAL.ai format)
        if not re.match(r'^[a-zA-Z0-9._/-]+$', v):
            raise ValueError("Model ID contains invalid characters")
        
        return v.strip()
    
    @validator('prompt')
    def validate_prompt(cls, v):
        """Validate and sanitize prompt."""
        if not v or not v.strip():
            raise ValueError("Prompt cannot be empty")
        
        # Check for dangerous patterns (but be less strict for creative content)
        dangerous_script_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'data:text/html',
            r'vbscript:',
        ]
        
        for pattern in dangerous_script_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Prompt contains dangerous content")
        
        # Basic sanitization while preserving creative content
        v = v.strip()
        
        # Check for excessive repetition (potential spam)
        words = v.split()
        if len(words) > 10:
            word_count = {}
            for word in words:
                word_lower = word.lower()
                word_count[word_lower] = word_count.get(word_lower, 0) + 1
                # Flag if any word appears more than 30% of the time
                if word_count[word_lower] > len(words) * 0.3:
                    raise ValueError("Prompt contains excessive repetition")
        
        return v
    
    @validator('negative_prompt')
    def validate_negative_prompt(cls, v):
        """Validate negative prompt."""
        if v is None:
            return v
        
        v = v.strip()
        if not v:
            return None
        
        # Apply same dangerous content checks as prompt
        dangerous_script_patterns = [
            r'<script[^>]*>.*?</script>',
            r'javascript:',
            r'data:text/html',
            r'vbscript:',
        ]
        
        for pattern in dangerous_script_patterns:
            if re.search(pattern, v, re.IGNORECASE):
                raise ValueError("Negative prompt contains dangerous content")
        
        return v
    
    @validator('reference_image_url')
    def validate_reference_image_url(cls, v):
        """Validate reference image URL."""
        if v is None:
            return v
        
        # Ensure HTTPS for security
        if str(v).startswith('http://'):
            raise ValueError("Reference image URL must use HTTPS")
        
        # Validate image file extension
        url_str = str(v).lower()
        valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
        if not any(url_str.endswith(ext) for ext in valid_extensions):
            # Allow URLs without extensions (some APIs use query parameters)
            if '?' not in url_str and '#' not in url_str:
                raise ValueError("Reference image URL must point to a valid image file")
        
        return v
    
    @validator('parameters')
    def validate_parameters(cls, v):
        """Validate generation parameters."""
        if not isinstance(v, dict):
            raise ValueError("Parameters must be a dictionary")
        
        # Limit parameters size
        if len(str(v)) > 10000:  # 10KB limit
            raise ValueError("Parameters too large")
        
        # Validate parameter keys and values
        allowed_param_types = (str, int, float, bool, list)
        
        for key, value in v.items():
            if not isinstance(key, str) or len(key) > 100:
                raise ValueError("Parameter keys must be strings with max length 100")
            
            # Check for dangerous patterns in keys
            SecurityValidator.check_dangerous_patterns(key)
            
            # Validate parameter values
            if not isinstance(value, allowed_param_types):
                raise ValueError(f"Parameter '{key}' has invalid type")
            
            if isinstance(value, str):
                SecurityValidator.check_dangerous_patterns(value)
                if len(value) > 1000:
                    raise ValueError(f"Parameter '{key}' value too long")
            
            elif isinstance(value, list):
                if len(value) > 100:
                    raise ValueError(f"Parameter '{key}' list too long")
                
                for item in value:
                    if not isinstance(item, (str, int, float, bool)):
                        raise ValueError(f"Parameter '{key}' contains invalid list item type")
        
        return v
    
    @validator('project_id')
    def validate_project_id(cls, v):
        """Validate project ID format."""
        if v is None:
            return v
        
        # Validate UUID format
        return SecurityValidator.validate_uuid(str(v))


class GenerationCreate(GenerationBase):
    """Generation creation model."""
    pass


class GenerationUpdate(EnhancedBaseModel):
    """Generation update model with validation."""
    prompt: Optional[str] = Field(None, min_length=1, max_length=ValidationConfig.MAX_PROMPT_LENGTH)
    negative_prompt: Optional[str] = Field(None, max_length=1000)
    parameters: Optional[Dict[str, Any]] = None
    is_favorite: Optional[bool] = None
    
    @validator('prompt')
    def validate_prompt(cls, v):
        """Validate prompt if provided."""
        if v is None:
            return v
        
        # Apply same validation as GenerationBase
        return GenerationBase.__fields__['prompt'].type_.validate_prompt(v)
    
    @validator('negative_prompt')
    def validate_negative_prompt(cls, v):
        """Validate negative prompt if provided."""
        if v is None:
            return v
        
        # Apply same validation as GenerationBase
        return GenerationBase.__fields__['negative_prompt'].type_.validate_negative_prompt(v)
    
    @validator('parameters')
    def validate_parameters(cls, v):
        """Validate parameters if provided."""
        if v is None:
            return v
        
        # Apply same validation as GenerationBase
        return GenerationBase.__fields__['parameters'].type_.validate_parameters(v)


class GenerationResponse(BaseModel):
    """Generation response model matching actual database schema."""
    id: UUID
    user_id: UUID
    project_id: Optional[UUID] = None
    parent_generation_id: Optional[UUID] = None
    style_stack_id: Optional[UUID] = None
    media_url: Optional[str] = None
    media_type: str
    prompt: str
    status: GenerationStatus
    cost: int
    created_at: datetime
    
    # Optional fields for compatibility - renamed to avoid model_ namespace conflict
    ai_model_id: Optional[str] = Field(None, alias="model_id")
    negative_prompt: Optional[str] = None
    reference_image_url: Optional[HttpUrl] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    output_urls: List[str] = Field(default_factory=list)
    credits_used: Optional[int] = None
    processing_time: Optional[float] = None
    error_message: Optional[str] = None
    is_favorite: bool = False
    updated_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @validator('output_urls')
    def validate_output_urls(cls, v):
        """Validate output URLs."""
        if not isinstance(v, list):
            raise ValueError("Output URLs must be a list")
        
        if len(v) > 10:  # Reasonable limit
            raise ValueError("Too many output URLs")
        
        for url in v:
            # Ensure HTTPS for security if it's a full URL
            if str(url).startswith('http://'):
                raise ValueError("Output URLs must use HTTPS")
        
        return v
    
    @validator('error_message')
    def validate_error_message(cls, v):
        """Validate error message."""
        if v is None:
            return v
        
        # Sanitize error message to prevent information leakage
        SecurityValidator.check_dangerous_patterns(v)
        return SecurityValidator.sanitize_string(v, 1000)

    model_config = {
        "from_attributes": True,
        "protected_namespaces": (),
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class GenerationListResponse(BaseModel):
    """Paginated generation list response."""
    items: List[GenerationResponse]
    total: int
    page: int
    per_page: int
    pages: int


class GenerationStatsResponse(BaseModel):
    """Generation statistics response."""
    total_generations: int
    completed_generations: int
    failed_generations: int
    processing_generations: int
    favorite_generations: int
    total_credits_used: int
    success_rate: float
    type_breakdown: Dict[str, int]
    ai_model_breakdown: Dict[str, int] = Field(alias="model_breakdown")


class FALGenerationRequest(BaseModel):
    """FAL.ai generation request model."""
    ai_model_id: str = Field(alias="model_id")
    prompt: str
    negative_prompt: Optional[str] = None
    reference_image_url: Optional[str] = None
    parameters: Dict[str, Any] = Field(default_factory=dict)
    
    model_config = {
        "protected_namespaces": ()
    }


class FALGenerationResponse(BaseModel):
    """FAL.ai generation response model."""
    request_id: str
    status: str
    output_urls: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None