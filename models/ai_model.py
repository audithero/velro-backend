"""
AI Model schemas for available models and their configurations.
"""
from pydantic import BaseModel, HttpUrl, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class ModelType(str, Enum):
    """Model type enum."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"


class ModelStatus(str, Enum):
    """Model status enum."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


class AIModelBase(BaseModel):
    """Base AI model configuration."""
    ai_model_id: str = Field(alias="model_id")
    name: str
    description: str
    ai_model_type: ModelType = Field(alias="model_type")
    provider: str
    endpoint_url: HttpUrl
    credits_per_generation: int
    max_resolution: Optional[str] = None
    supported_formats: List[str] = []
    parameters_schema: Dict[str, Any] = {}
    status: ModelStatus = ModelStatus.ACTIVE
    
    model_config = {
        "protected_namespaces": ()
    }


class AIModelResponse(AIModelBase):
    """AI model response."""
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True, 
        "protected_namespaces": (),
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class ModelPricing(BaseModel):
    """Model pricing information."""
    ai_model_id: str = Field(alias="model_id")
    credits_per_generation: int
    usd_per_generation: float
    bulk_discounts: List[Dict[str, Any]] = []
    
    model_config = {
        "protected_namespaces": ()
    }