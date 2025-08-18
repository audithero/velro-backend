"""
Storage API endpoints with comprehensive rate limiting and security.
Following CLAUDE.md: Router layer for API endpoints.
Following PRD.MD: Secure, efficient storage operations.
"""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request, File, UploadFile, Form
from fastapi.security import HTTPBearer
from fastapi.responses import Response, StreamingResponse
import io
import logging

from middleware.auth import get_current_user
from middleware.rate_limiting import limit, api_limit
from services.storage_service import storage_service
from models.storage import (
    FileMetadataResponse,
    FileMetadataUpdate,
    StorageUrlRequest,
    StorageUrlResponse,
    FileUploadRequest,
    StorageStatsResponse,
    BulkDeleteRequest,
    ProcessingResult,
    StorageBucket,
    ContentType
)
from models.user import UserResponse

router = APIRouter(tags=["storage"])
security = HTTPBearer()
logger = logging.getLogger(__name__)


# === File Upload Endpoints ===

@router.post("/upload", response_model=FileMetadataResponse)
@limit("20/minute")  # Moderate limit for file uploads
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    bucket: StorageBucket = Form(...),
    generation_id: Optional[str] = Form(None),
    project_id: Optional[str] = Form(None),
    metadata: Optional[str] = Form("{}"),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Upload file to storage with validation and processing.
    
    Rate limit: 20 uploads per minute to prevent abuse while allowing normal usage.
    """
    try:
        # Read file data
        file_data = await file.read()
        
        # Validate file size (max 100MB as per PRD.MD requirements)
        max_size = 104857600  # 100MB
        if len(file_data) > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File too large. Maximum size is {max_size} bytes"
            )
        
        # Detect content type if not provided
        content_type = file.content_type or "application/octet-stream"
        
        # Validate content type
        try:
            content_type_enum = ContentType(content_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported content type: {content_type}"
            )
        
        # Parse metadata
        import json
        try:
            metadata_dict = json.loads(metadata) if metadata != "{}" else {}
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid metadata JSON"
            )
        
        # Create upload request
        upload_request = FileUploadRequest(
            bucket_name=bucket,
            filename=file.filename or "untitled",
            content_type=content_type_enum,
            file_size=len(file_data),
            generation_id=UUID(generation_id) if generation_id else None,
            project_id=UUID(project_id) if project_id else None,
            metadata=metadata_dict
        )
        
        # Upload file
        file_metadata = await storage_service.upload_file(
            user_id=current_user.id,
            file_data=file_data,
            upload_request=upload_request,
            generation_id=UUID(generation_id) if generation_id else None
        )
        
        # Log successful upload
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"File uploaded by user {current_user.id} from {client_ip}: "
            f"bucket={bucket.value}, filename={file.filename}, size={len(file_data)}"
        )
        
        return file_metadata
        
    except ValueError as e:
        logger.warning(f"File upload validation error for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"File upload failed for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed")


@router.post("/upload-url", response_model=dict)
@limit("30/minute")  # Higher limit for signed URL generation
async def create_upload_url(
    upload_request: StorageUrlRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Create signed upload URL for direct client uploads.
    
    Rate limit: 30 requests per minute for URL generation.
    """
    try:
        # Generate signed upload URL (implementation depends on storage service)
        signed_url = "https://example.com/upload"  # Placeholder - implement in storage service
        
        return {
            "upload_url": signed_url,
            "expires_in": upload_request.expires_in,
            "bucket": upload_request.bucket_name.value,
            "file_path": upload_request.file_path
        }
        
    except Exception as e:
        logger.error(f"Failed to create upload URL for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create upload URL")


# === File Access Endpoints ===

@router.get("/files/{file_id}", response_model=FileMetadataResponse)
@api_limit()  # Standard API rate limit
async def get_file_metadata(
    file_id: UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get file metadata with user verification.
    
    Rate limit: Standard API limit (100/minute).
    """
    try:
        file_metadata = await storage_service.get_file_metadata(file_id, current_user.id)
        return file_metadata
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get file metadata {file_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get file metadata")


@router.get("/files/{file_id}/download")
@limit("60/minute")  # Higher limit for file downloads
async def download_file(
    file_id: UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Download file data directly.
    
    Rate limit: 60 downloads per minute for reasonable usage.
    """
    try:
        file_data, file_metadata = await storage_service.download_file(file_id, current_user.id)
        
        # Create streaming response
        def iter_file():
            yield file_data
        
        return StreamingResponse(
            io.BytesIO(file_data),
            media_type=file_metadata.content_type.value,
            headers={
                "Content-Disposition": f"attachment; filename={file_metadata.original_filename or 'file'}",
                "Content-Length": str(len(file_data))
            }
        )
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to download file {file_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Download failed")


@router.post("/files/{file_id}/signed-url", response_model=StorageUrlResponse)
@limit("100/minute")  # Higher limit for signed URL generation
async def get_signed_url(
    file_id: UUID,
    request: Request,
    expires_in: int = 3600,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get signed URL for file access.
    
    Rate limit: 100 requests per minute for URL generation.
    """
    try:
        # Validate expires_in parameter
        if expires_in < 60 or expires_in > 86400:  # 1 minute to 24 hours
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expires_in must be between 60 and 86400 seconds"
            )
        
        signed_url_response = await storage_service.get_signed_url(
            file_id=file_id,
            user_id=current_user.id,
            expires_in=expires_in
        )
        
        return signed_url_response
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create signed URL for file {file_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create signed URL")


# === File Management Endpoints ===

@router.get("/files", response_model=List[FileMetadataResponse])
@api_limit()  # Standard API rate limit
async def list_user_files(
    request: Request,
    bucket: Optional[StorageBucket] = None,
    generation_id: Optional[UUID] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    List user's files with optional filtering.
    
    Rate limit: Standard API limit (100/minute).
    """
    try:
        # Validate pagination parameters
        if limit < 1 or limit > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit must be between 1 and 100"
            )
        
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="offset must be non-negative"
            )
        
        files = await storage_service.list_user_files(
            user_id=current_user.id,
            bucket_name=bucket,
            generation_id=generation_id,
            limit=limit,
            offset=offset
        )
        
        return files
        
    except Exception as e:
        logger.error(f"Failed to list files for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list files")


@router.put("/files/{file_id}", response_model=FileMetadataResponse)
@api_limit()  # Standard API rate limit
async def update_file_metadata(
    file_id: UUID,
    update_data: FileMetadataUpdate,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Update file metadata.
    
    Rate limit: Standard API limit (100/minute).
    """
    try:
        updated_metadata = await storage_service.storage_repo.update_file_metadata(
            file_id=file_id,
            updates=update_data,
            user_id=current_user.id
        )
        
        return updated_metadata
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update file metadata {file_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update file")


@router.delete("/files/{file_id}")
@limit("30/minute")  # Moderate limit for delete operations
async def delete_file(
    file_id: UUID,
    request: Request,
    force: bool = False,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Delete file from storage.
    
    Rate limit: 30 deletions per minute to prevent abuse.
    """
    try:
        success = await storage_service.delete_file(
            file_id=file_id,
            user_id=current_user.id,
            force=force
        )
        
        if not success:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Delete failed")
        
        # Log deletion for audit trail
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"File {file_id} deleted by user {current_user.id} from {client_ip}")
        
        return {"message": "File deleted successfully"}
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to delete file {file_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Delete failed")


@router.post("/bulk-delete", response_model=ProcessingResult)
@limit("10/minute")  # Strict limit for bulk operations
async def bulk_delete_files(
    delete_request: BulkDeleteRequest,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Bulk delete multiple files.
    
    Rate limit: 10 bulk operations per minute to prevent abuse.
    """
    try:
        result = await storage_service.bulk_delete_files(
            delete_request=delete_request,
            user_id=current_user.id
        )
        
        # Log bulk deletion
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"Bulk delete by user {current_user.id} from {client_ip}: "
            f"bucket={delete_request.bucket_name.value}, "
            f"processed={len(result.processed_files)}, "
            f"failed={len(result.failed_files)}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Bulk delete failed for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Bulk delete failed")


# === Storage Statistics and Management ===

@router.get("/stats", response_model=StorageStatsResponse)
@api_limit()  # Standard API rate limit
async def get_storage_stats(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get user's storage usage statistics.
    
    Rate limit: Standard API limit (100/minute).
    """
    try:
        stats = await storage_service.get_user_storage_stats(current_user.id)
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get storage stats for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get storage stats")


@router.get("/duplicates")
@limit("10/minute")  # Lower limit for resource-intensive operations
async def find_duplicate_files(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Find duplicate files for the user.
    
    Rate limit: 10 requests per minute for resource-intensive operations.
    """
    try:
        duplicates = await storage_service.find_duplicate_files(current_user.id)
        return {"duplicates": duplicates}
        
    except Exception as e:
        logger.error(f"Failed to find duplicates for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to find duplicates")


@router.post("/files/{file_id}/verify")
@limit("20/minute")  # Moderate limit for verification operations
async def verify_file_integrity(
    file_id: UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Verify file integrity using hash comparison.
    
    Rate limit: 20 verifications per minute.
    """
    try:
        is_valid = await storage_service.verify_file_integrity(
            file_id=file_id,
            user_id=current_user.id
        )
        
        return {
            "file_id": str(file_id),
            "is_valid": is_valid,
            "message": "File integrity verified" if is_valid else "File integrity check failed"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to verify file {file_id} for user {current_user.id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Verification failed")


# === Project Media Management ===

@router.post("/files/{file_id}/move-to-project")
@limit("20/minute")  # Moderate limit for file operations
async def move_media_to_project(
    file_id: UUID,
    request: Request,
    destination_project_id: UUID,
    source_project_id: Optional[UUID] = None,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Move media file from one project to another.
    
    This enables the frontend to reassign media between projects
    while maintaining proper storage organization.
    
    Rate limit: 20 moves per minute.
    """
    try:
        if source_project_id == destination_project_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source and destination projects cannot be the same"
            )
        
        success = await storage_service.move_media_between_projects(
            user_id=current_user.id,
            file_id=file_id,
            source_project_id=source_project_id or UUID('00000000-0000-0000-0000-000000000000'),
            destination_project_id=destination_project_id
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to move media between projects"
            )
        
        # Log media movement for audit trail
        client_ip = request.client.host if request.client else "unknown"
        logger.info(
            f"Media moved by user {current_user.id} from {client_ip}: "
            f"file={file_id}, from_project={source_project_id}, to_project={destination_project_id}"
        )
        
        return {
            "message": "Media successfully moved to project",
            "file_id": str(file_id),
            "destination_project_id": str(destination_project_id)
        }
        
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to move media {file_id} to project {destination_project_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Media move operation failed"
        )


@router.post("/setup-user-folders")
@limit("5/minute")  # Strict limit for setup operations
async def setup_user_storage_folders(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Manually trigger user storage folder setup.
    
    This can be used to retroactively create storage folders for existing users
    or to re-create folders if they were accidentally deleted.
    
    Rate limit: 5 requests per minute.
    """
    try:
        success = await storage_service.create_user_storage_folders(current_user.id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user storage folders"
            )
        
        # Log folder setup for audit trail
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"User storage setup by user {current_user.id} from {client_ip}")
        
        return {
            "message": "User storage folders created successfully",
            "user_id": str(current_user.id)
        }
        
    except Exception as e:
        logger.error(f"Failed to setup user storage folders for {current_user.id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage folder setup failed"
        )


@router.post("/projects/{project_id}/setup-folders")
@limit("10/minute")  # Moderate limit for project setup
async def setup_project_storage_folders(
    project_id: UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Manually trigger project storage folder setup.
    
    This can be used to retroactively create storage folders for existing projects
    or to re-create folders if they were accidentally deleted.
    
    Rate limit: 10 requests per minute.
    """
    try:        
        success = await storage_service.create_project_storage_folders(current_user.id, project_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create project storage folders"
            )
        
        # Log folder setup for audit trail
        client_ip = request.client.host if request.client else "unknown"
        logger.info(f"Project storage setup by user {current_user.id} from {client_ip}: project={project_id}")
        
        return {
            "message": "Project storage folders created successfully",
            "project_id": str(project_id),
            "user_id": str(current_user.id)
        }
        
    except Exception as e:
        logger.error(f"Failed to setup project storage folders for {project_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Project storage folder setup failed"
        )


# === Administrative Endpoints ===

@router.post("/cleanup/expired")
@limit("5/minute")  # Very strict limit for admin operations
async def cleanup_expired_files(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Clean up expired temporary files (admin operation).
    
    Rate limit: 5 requests per minute for admin operations.
    """
    try:
        # Check if user has admin permissions (based on PRD.MD user roles)
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin access required"
            )
        
        deleted_count = await storage_service.cleanup_expired_files()
        
        logger.info(f"Cleanup performed by admin {current_user.id}: {deleted_count} files deleted")
        
        return {
            "message": f"Cleanup completed: {deleted_count} expired files deleted",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        logger.error(f"Cleanup failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Cleanup failed")


# === Health and Info Endpoints ===

@router.get("/health")
@limit("60/minute")  # Higher limit for health checks
async def storage_health(
    request: Request
):
    """
    Storage service health check.
    
    Rate limit: 60 requests per minute for monitoring.
    """
    try:
        # Basic health check - could expand to check storage connectivity
        return {
            "status": "healthy",
            "service": "storage",
            "timestamp": str(storage_service.db.storage),  # Basic connectivity check
            "buckets_available": [bucket.value for bucket in StorageBucket],
            "max_file_size": "100MB",
            "supported_types": [content_type.value for content_type in ContentType]
        }
        
    except Exception as e:
        logger.error(f"Storage health check failed: {str(e)}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Storage service unhealthy")


@router.get("/info")
@api_limit()  # Standard API rate limit
async def storage_info(
    request: Request
):
    """
    Get storage service information and configuration.
    
    Rate limit: Standard API limit (100/minute).
    """
    return {
        "service": "Velro Storage API",
        "version": "1.0.0",
        "storage_buckets": {
            "generations": "AI generated content storage",
            "uploads": "User uploaded reference images", 
            "thumbnails": "Optimized thumbnail storage",
            "temp": "Temporary processing files"
        },
        "file_limits": {
            "max_size": "100MB",
            "max_uploads_per_bucket": {
                "uploads": "20MB",
                "thumbnails": "2MB", 
                "generations": "50MB",
                "temp": "100MB"
            }
        },
        "rate_limits": {
            "upload": "20 per minute",
            "download": "60 per minute",
            "delete": "30 per minute",
            "bulk_operations": "10 per minute",
            "admin_operations": "5 per minute"
        },
        "supported_formats": [content_type.value for content_type in ContentType],
        "features": [
            "Automatic thumbnail generation",
            "File deduplication",
            "Integrity verification",
            "Signed URL access",
            "User isolation",
            "Bulk operations"
        ]
    }