"""
Storage model schemas for file management and media operations.
Following CLAUDE.md: Pure models with strict validation.
Following PRD.MD: Secure, organized, efficient storage.
"""
from pydantic import Field, validator, HttpUrl
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime, timedelta
from uuid import UUID
from enum import Enum

from middleware.validation import SecurityValidator, ValidationConfig, EnhancedBaseModel


class StorageBucket(str, Enum):
    """Allowed storage buckets with specific purposes."""
    GENERATIONS = "velro-generations"      # AI generated content
    UPLOADS = "velro-uploads"              # User uploaded reference images
    THUMBNAILS = "velro-thumbnails"        # Optimized thumbnails
    TEMP = "velro-temp"                    # Temporary processing files


class MediaType(str, Enum):
    """Supported media types for storage."""
    IMAGE = "image"
    VIDEO = "video"


class ContentType(str, Enum):
    """Allowed content types with validation."""
    # Image types
    JPEG = "image/jpeg"
    JPG = "image/jpg"
    PNG = "image/png"
    WEBP = "image/webp"
    GIF = "image/gif"
    
    # Video types
    MP4 = "video/mp4"
    WEBM = "video/webm"
    MOV = "video/mov"
    AVI = "video/avi"


class FileMetadataBase(EnhancedBaseModel):
    """Base file metadata model with validation."""
    bucket_name: StorageBucket
    file_path: str = Field(..., min_length=1, max_length=500)
    original_filename: Optional[str] = Field(None, max_length=255)
    file_size: int = Field(..., gt=0, le=104857600)  # Max 100MB
    content_type: ContentType
    file_hash: Optional[str] = Field(None, min_length=64, max_length=64)  # SHA-256
    is_thumbnail: bool = False
    is_processed: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    expires_at: Optional[datetime] = None
    
    @validator('file_path')
    def validate_file_path(cls, v):
        """Validate and sanitize file path."""
        # Check for dangerous patterns
        SecurityValidator.check_dangerous_patterns(v)
        
        # Ensure path doesn't contain directory traversal
        if '..' in v or v.startswith('/') or '\\' in v:
            raise ValueError("File path contains invalid characters or directory traversal")
        
        # Must follow pattern: user_id/generation_id/filename or user_id/upload_id/filename
        path_parts = v.split('/')
        if len(path_parts) < 2 or len(path_parts) > 4:
            raise ValueError("File path must follow pattern: user_id/folder/filename")
        
        # Validate UUID format for user_id
        try:
            SecurityValidator.validate_uuid(path_parts[0])
        except ValueError:
            raise ValueError("File path must start with valid user UUID")
        
        return v
    
    @validator('original_filename')
    def validate_original_filename(cls, v):
        """Validate original filename."""
        if v is None:
            return v
        
        # Check for dangerous patterns
        SecurityValidator.check_dangerous_patterns(v)
        
        # Validate filename safety
        return SecurityValidator.validate_filename(v)
    
    @validator('file_hash')
    def validate_file_hash(cls, v):
        """Validate SHA-256 hash format."""
        if v is None:
            return v
        
        # Must be valid SHA-256 hex string
        if not all(c in '0123456789abcdef' for c in v.lower()):
            raise ValueError("File hash must be valid SHA-256 hex string")
        
        return v.lower()
    
    @validator('metadata')
    def validate_metadata(cls, v):
        """Validate metadata dictionary."""
        if not isinstance(v, dict):
            raise ValueError("Metadata must be a dictionary")
        
        # Limit metadata size
        if len(str(v)) > 2048:  # 2KB limit
            raise ValueError("Metadata too large")
        
        # Validate metadata keys and values
        for key, value in v.items():
            if not isinstance(key, str) or len(key) > 50:
                raise ValueError("Metadata keys must be strings with max length 50")
            
            if isinstance(value, str):
                SecurityValidator.check_dangerous_patterns(value)
                if len(value) > 500:
                    raise ValueError(f"Metadata value for '{key}' too long")
        
        return v
    
    @validator('expires_at')
    def validate_expires_at(cls, v, values):
        """Validate expiration time for temp files."""
        if v is None:
            return v
        
        # Only temp files should have expiration
        if values.get('bucket_name') == StorageBucket.TEMP:
            # Must be in the future but not more than 7 days
            if v <= datetime.utcnow():
                raise ValueError("Expiration time must be in the future")
            
            max_expiry = datetime.utcnow() + timedelta(days=7)
            if v > max_expiry:
                raise ValueError("Expiration time cannot be more than 7 days in the future")
        else:
            # Non-temp files should not have expiration
            if v is not None:
                raise ValueError("Only temp files can have expiration time")
        
        return v


class FileMetadataCreate(FileMetadataBase):
    """File metadata creation model."""
    pass


class FileMetadataUpdate(EnhancedBaseModel):
    """File metadata update model."""
    original_filename: Optional[str] = Field(None, max_length=255)
    is_processed: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @validator('original_filename')
    def validate_original_filename(cls, v):
        """Validate original filename."""
        if v is None:
            return v
        return SecurityValidator.validate_filename(v)


class FileMetadataResponse(FileMetadataBase):
    """File metadata response model."""
    id: UUID
    user_id: UUID
    generation_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    media_type: Optional[MediaType] = None
    file_extension: Optional[str] = None
    size_formatted: Optional[str] = None
    
    @validator('media_type', pre=False, always=True)
    def compute_media_type(cls, v, values):
        """Compute media type from content type."""
        content_type = values.get('content_type')
        if content_type:
            if content_type.startswith('image/'):
                return MediaType.IMAGE
            elif content_type.startswith('video/'):
                return MediaType.VIDEO
        return None
    
    @validator('file_extension', pre=False, always=True)
    def compute_file_extension(cls, v, values):
        """Extract file extension from filename or path."""
        filename = values.get('original_filename') or values.get('file_path', '')
        if '.' in filename:
            return filename.split('.')[-1].lower()
        return None
    
    @validator('size_formatted', pre=False, always=True)
    def compute_size_formatted(cls, v, values):
        """Format file size in human-readable format."""
        size = values.get('file_size', 0)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"

    model_config = {
        "from_attributes": True,
        "json_encoders": {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }
    }


class StorageUrlRequest(EnhancedBaseModel):
    """Request model for generating signed URLs."""
    bucket_name: StorageBucket
    file_path: str = Field(..., min_length=1, max_length=500)
    expires_in: int = Field(3600, gt=0, le=86400)  # 1 hour to 24 hours
    
    @validator('file_path')
    def validate_file_path(cls, v):
        """Validate file path."""
        SecurityValidator.check_dangerous_patterns(v)
        return v


class StorageUrlResponse(EnhancedBaseModel):
    """Response model for signed URLs."""
    signed_url: HttpUrl
    expires_at: datetime
    file_path: str
    bucket_name: StorageBucket


class FileUploadRequest(EnhancedBaseModel):
    """Request model for file uploads."""
    bucket_name: StorageBucket
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: ContentType
    file_size: int = Field(..., gt=0, le=104857600)  # Max 100MB
    generation_id: Optional[UUID] = None
    project_id: Optional[UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('filename')
    def validate_filename(cls, v):
        """Validate filename."""
        return SecurityValidator.validate_filename(v)
    
    @validator('file_size')
    def validate_file_size_by_bucket(cls, v, values):
        """Validate file size based on bucket limits."""
        bucket = values.get('bucket_name')
        
        # Different size limits per bucket
        if bucket == StorageBucket.UPLOADS and v > 20971520:  # 20MB
            raise ValueError("Upload files cannot exceed 20MB")
        elif bucket == StorageBucket.THUMBNAILS and v > 2097152:  # 2MB
            raise ValueError("Thumbnail files cannot exceed 2MB")
        elif bucket == StorageBucket.GENERATIONS and v > 52428800:  # 50MB
            raise ValueError("Generation files cannot exceed 50MB")
        elif bucket == StorageBucket.TEMP and v > 104857600:  # 100MB
            raise ValueError("Temp files cannot exceed 100MB")
        
        return v


class StorageStatsResponse(EnhancedBaseModel):
    """Storage usage statistics response."""
    user_id: UUID
    total_files: int
    total_size: int
    total_size_formatted: str
    buckets: Dict[str, Dict[str, Any]]
    
    @validator('total_size_formatted', pre=False, always=True)
    def compute_total_size_formatted(cls, v, values):
        """Format total size in human-readable format."""
        size = values.get('total_size', 0)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"


class BulkDeleteRequest(EnhancedBaseModel):
    """Request model for bulk file deletion."""
    file_paths: List[str] = Field(..., min_items=1, max_items=100)
    bucket_name: StorageBucket
    force: bool = False  # Force delete even if referenced by generations
    
    @validator('file_paths')
    def validate_file_paths(cls, v):
        """Validate all file paths."""
        for path in v:
            SecurityValidator.check_dangerous_patterns(path)
            if '..' in path or path.startswith('/'):
                raise ValueError(f"Invalid file path: {path}")
        return v


class MediaFileInfo(EnhancedBaseModel):
    """Media file information for generation storage."""
    bucket: StorageBucket
    path: str
    size: int
    content_type: ContentType
    is_thumbnail: bool = False
    thumbnail_sizes: Optional[List[str]] = None  # e.g., ["256x256", "512x512"]


class ProcessingResult(EnhancedBaseModel):
    """Result of media processing operations."""
    success: bool
    processed_files: List[MediaFileInfo] = Field(default_factory=list)
    failed_files: List[str] = Field(default_factory=list)
    total_size: int = 0
    processing_time: float = 0
    error_message: Optional[str] = None