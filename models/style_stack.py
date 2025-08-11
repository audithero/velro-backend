"""
Style Stack schemas for dynamic AI generation templates.
Implements comprehensive Style Stacks PRD v1.2 requirements.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from enum import Enum
import uuid


class StackType(str, Enum):
    """Style stack type enum."""
    CUSTOM = "custom"
    PRESET = "preset"
    MARKETPLACE = "marketplace"
    FEATURED = "featured"


class StackCategory(str, Enum):
    """Style stack category enum."""
    GENERAL = "general"
    DIRECTOR = "director"
    GENRE = "genre"
    TECHNIQUE = "technique"
    CINEMATIC = "cinematic"
    PHOTOGRAPHIC = "photographic"


class CreationSource(str, Enum):
    """Style stack creation source enum."""
    MANUAL = "manual"
    VISION = "vision"
    PRESET = "preset"
    MARKETPLACE = "marketplace"
    ADAPTATION = "adaptation"


class ComplexityLevel(str, Enum):
    """Complexity level enum for presets."""
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class PromptBlocks(BaseModel):
    """
    Multimodal prompt blocks structure (PRD Section 3.1).
    Each field represents a specific aspect of the cinematic prompt.
    """
    description: str = Field(default="", description="Narrative overview of the scene")
    style: str = Field(default="", description="Aesthetic and visual inspiration")
    camera: str = Field(default="", description="Shot angles, movements, and framing")
    lighting: str = Field(default="", description="Illumination details and evolution")
    setting: str = Field(default="", description="Environmental context and location")
    elements: List[str] = Field(default_factory=list, description="Key objects and visual assets")
    motion: str = Field(default="", description="Temporal dynamics and actions")
    ending: str = Field(default="", description="Scene resolution and payoff")
    text: str = Field(default="", description="Dialogue, FX cues, or text elements")
    keywords: List[str] = Field(default_factory=list, description="Semantic anchoring keywords")

    @validator('elements', 'keywords')
    def limit_array_size(cls, v):
        """Limit array sizes for performance."""
        if len(v) > 50:
            raise ValueError("Array cannot contain more than 50 items")
        return v

    @validator('description', 'style', 'camera', 'lighting', 'setting', 'motion', 'ending', 'text')
    def limit_text_length(cls, v):
        """Limit text field lengths."""
        if len(v) > 2000:
            raise ValueError("Text field cannot exceed 2000 characters")
        return v


class PersistentElement(BaseModel):
    """
    Persistent element for consistency across generations (PRD Section 3.5).
    """
    type: str = Field(..., description="Element type (character, brand_asset, object, etc.)")
    ref_url: Optional[str] = Field(None, description="Reference image URL")
    description: str = Field(..., description="Detailed description for consistency")
    weight: float = Field(1.0, ge=0.0, le=2.0, description="Importance weight for adaptation")
    pose_weights: Optional[float] = Field(None, ge=0.0, le=2.0, description="Pose consistency weight")
    color_match: Optional[str] = Field(None, description="Exact color matching requirements")


class LoRAConfig(BaseModel):
    """
    LoRA configuration for compatible models (PRD Section 3.1).
    """
    model_id: str = Field(..., description="Target model ID")
    lora_path: str = Field(..., description="LoRA model path or identifier")
    weight: float = Field(1.0, ge=0.0, le=2.0, description="LoRA application weight")
    trigger_words: List[str] = Field(default_factory=list, description="LoRA activation keywords")


class ModelAdaptation(BaseModel):
    """
    Model-specific adaptation configuration.
    """
    model_id: str = Field(..., description="Target model identifier")
    adapted_prompt: Dict[str, Any] = Field(default_factory=dict, description="Adapted prompt blocks")
    specific_parameters: Dict[str, Any] = Field(default_factory=dict, description="Model-specific parameters")
    adaptation_rules: Dict[str, Any] = Field(default_factory=dict, description="Custom adaptation rules")
    last_adapted: Optional[datetime] = Field(None, description="Last adaptation timestamp")


class StyleStackBase(BaseModel):
    """Base style stack model."""
    name: str = Field(..., min_length=1, max_length=100, description="Style stack name")
    description: Optional[str] = Field(None, max_length=1000, description="Style stack description")
    
    # Core JSON Structure
    base_json: Dict[str, Any] = Field(default_factory=dict, description="Base JSON configuration")
    prompt_blocks: PromptBlocks = Field(default_factory=PromptBlocks, description="Multimodal prompt blocks")
    
    # Model adaptations and LoRA
    model_adaptations: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Model-specific adaptations")
    lora_configs: Dict[str, LoRAConfig] = Field(default_factory=dict, description="LoRA configurations")
    persistent_elements: List[PersistentElement] = Field(default_factory=list, description="Persistent elements for consistency")
    
    # Classification
    stack_type: StackType = Field(default=StackType.CUSTOM, description="Stack type classification")
    category: StackCategory = Field(default=StackCategory.GENERAL, description="Stack category")
    tags: List[str] = Field(default_factory=list, description="Searchable tags")
    
    # Marketplace and sharing
    is_public: bool = Field(default=False, description="Public visibility")
    is_featured: bool = Field(default=False, description="Featured status")
    is_marketplace: bool = Field(default=False, description="Available in marketplace")
    price_credits: int = Field(default=0, ge=0, description="Price in credits")
    royalty_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Creator royalty rate")
    
    # Model compatibility
    compatible_models: List[str] = Field(default_factory=list, description="Compatible model IDs")
    optimal_models: List[str] = Field(default_factory=list, description="Optimal model IDs")
    
    # Creation metadata
    created_from: CreationSource = Field(default=CreationSource.MANUAL, description="Creation source")
    source_image_url: Optional[str] = Field(None, description="Source image for vision-based creation")

    @validator('tags')
    def limit_tags(cls, v):
        """Limit number of tags."""
        if len(v) > 20:
            raise ValueError("Cannot have more than 20 tags")
        return [tag.lower().strip() for tag in v if tag.strip()]

    @validator('persistent_elements')
    def limit_persistent_elements(cls, v):
        """Limit persistent elements for performance."""
        if len(v) > 10:
            raise ValueError("Cannot have more than 10 persistent elements")
        return v


class StyleStackCreate(StyleStackBase):
    """Style stack creation model."""
    pass


class StyleStackUpdate(BaseModel):
    """Style stack update model."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    base_json: Optional[Dict[str, Any]] = None
    prompt_blocks: Optional[PromptBlocks] = None
    model_adaptations: Optional[Dict[str, Dict[str, Any]]] = None
    lora_configs: Optional[Dict[str, LoRAConfig]] = None
    persistent_elements: Optional[List[PersistentElement]] = None
    category: Optional[StackCategory] = None
    tags: Optional[List[str]] = None
    is_public: Optional[bool] = None
    is_marketplace: Optional[bool] = None
    price_credits: Optional[int] = Field(None, ge=0)
    royalty_rate: Optional[float] = Field(None, ge=0.0, le=1.0)
    compatible_models: Optional[List[str]] = None
    optimal_models: Optional[List[str]] = None


class StyleStackResponse(StyleStackBase):
    """Style stack response model."""
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    
    # Analytics
    usage_count: int = Field(default=0, description="Number of times used")
    generation_count: int = Field(default=0, description="Number of generations created")
    success_rate: float = Field(default=0.0, ge=0.0, le=1.0, description="Generation success rate")
    
    # Version control
    version: int = Field(default=1, description="Version number")
    parent_stack_id: Optional[uuid.UUID] = Field(None, description="Parent stack for versioning")
    
    # Timestamps
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "protected_namespaces": (),
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None,
            uuid.UUID: str
        }
    }


class StyleStackPresetBase(BaseModel):
    """Base preset model."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    creator: str = Field(default="Velro", description="Preset creator")
    
    # Template data
    template_json: Dict[str, Any] = Field(..., description="Template JSON configuration")
    prompt_blocks: PromptBlocks = Field(..., description="Template prompt blocks")
    
    # Classification
    category: StackCategory = Field(..., description="Preset category")
    subcategory: Optional[str] = Field(None, description="Preset subcategory")
    tags: List[str] = Field(default_factory=list, description="Searchable tags")
    
    # Usage metadata
    complexity_level: ComplexityLevel = Field(default=ComplexityLevel.BEGINNER, description="Complexity level")
    recommended_models: List[str] = Field(default_factory=list, description="Recommended model IDs")
    
    # Features
    is_featured: bool = Field(default=False, description="Featured preset status")

    @validator('tags')
    def limit_and_clean_tags(cls, v):
        """Limit and clean tags."""
        if len(v) > 15:
            raise ValueError("Cannot have more than 15 tags")
        return [tag.lower().strip() for tag in v if tag.strip()]


class StyleStackPresetResponse(StyleStackPresetBase):
    """Style stack preset response."""
    id: uuid.UUID
    usage_count: int = Field(default=0)
    rating: float = Field(default=0.0, ge=0.0, le=5.0)
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "protected_namespaces": (),
        "json_encoders": {
            datetime: lambda v: v.isoformat() if v else None,
            uuid.UUID: str
        }
    }


class StyleStackListResponse(BaseModel):
    """Style stack list response with pagination."""
    stacks: List[StyleStackResponse]
    total: int
    page: int
    size: int
    has_next: bool


class StyleStackSearchRequest(BaseModel):
    """Style stack search request."""
    query: Optional[str] = Field(None, description="Search query")
    category: Optional[StackCategory] = Field(None, description="Category filter")
    tags: Optional[List[str]] = Field(None, description="Tags filter")
    is_public: Optional[bool] = Field(None, description="Public filter")
    is_featured: Optional[bool] = Field(None, description="Featured filter")
    is_marketplace: Optional[bool] = Field(None, description="Marketplace filter")
    compatible_with_model: Optional[str] = Field(None, description="Model compatibility filter")
    min_rating: Optional[float] = Field(None, ge=0.0, le=5.0, description="Minimum rating filter")
    sort_by: str = Field(default="usage_count", description="Sort field")
    sort_order: str = Field(default="desc", description="Sort order")
    page: int = Field(default=1, ge=1, description="Page number")
    size: int = Field(default=20, ge=1, le=100, description="Page size")


class AdaptationRequest(BaseModel):
    """Request to adapt style stack for specific model."""
    stack_id: uuid.UUID = Field(..., description="Style stack ID")
    target_model_id: str = Field(..., description="Target model ID")
    user_input: Optional[str] = Field(None, description="Additional user input to merge")
    preserve_elements: Optional[List[str]] = Field(None, description="Elements to preserve during adaptation")


class AdaptationResponse(BaseModel):
    """Response from style stack adaptation."""
    adapted_prompt: Dict[str, Any] = Field(..., description="Adapted prompt blocks")
    model_metadata: Dict[str, Any] = Field(default_factory=dict, description="Model-specific metadata")
    adaptation_summary: str = Field(..., description="Summary of changes made")
    estimated_quality: float = Field(ge=0.0, le=1.0, description="Estimated adaptation quality")
    adaptation_timestamp: datetime = Field(default_factory=datetime.utcnow)


class VisionStackCreationRequest(BaseModel):
    """Request to create style stack from image analysis."""
    image_url: Optional[str] = Field(None, description="Image URL to analyze")
    image_data: Optional[str] = Field(None, description="Base64 encoded image data")
    additional_description: Optional[str] = Field(None, description="Additional user description")
    target_models: Optional[List[str]] = Field(None, description="Target models for optimization")
    extract_elements: List[str] = Field(default_factory=lambda: ["style", "lighting", "composition"], description="Elements to extract")


class MarketplaceStats(BaseModel):
    """Marketplace statistics."""
    total_stacks: int
    public_stacks: int
    marketplace_stacks: int
    featured_stacks: int
    total_usage: int
    categories: Dict[str, int]
    top_creators: List[Dict[str, Any]]
    trending_tags: List[str]


class BatchAdaptationRequest(BaseModel):
    """Request to adapt multiple stacks or single stack to multiple models."""
    stack_ids: List[uuid.UUID] = Field(..., description="Style stack IDs")
    target_model_ids: List[str] = Field(..., description="Target model IDs")
    user_input: Optional[str] = Field(None, description="Additional user input")
    generate_previews: bool = Field(default=False, description="Generate preview images")


class BatchAdaptationResponse(BaseModel):
    """Response from batch adaptation."""
    adaptations: List[AdaptationResponse]
    success_count: int
    error_count: int
    errors: List[str] = Field(default_factory=list)
    processing_time: float