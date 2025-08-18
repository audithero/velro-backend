"""
Storage service for coordinating file operations and media management.
Following CLAUDE.md: Service layer for business logic.
Following PRD.MD: Secure, efficient media storage with user isolation.
"""
import asyncio
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple, Union
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from pathlib import Path
import mimetypes
from PIL import Image
import io

from database import get_database
from repositories.storage_repository import StorageRepository
from repositories.generation_repository import GenerationRepository
from models.storage import (
    FileMetadataCreate,
    FileMetadataResponse,
    FileMetadataUpdate,
    StorageBucket,
    StorageUrlRequest,
    StorageUrlResponse,
    FileUploadRequest,
    StorageStatsResponse,
    BulkDeleteRequest,
    MediaFileInfo,
    ProcessingResult,
    ContentType
)
from models.generation import GenerationResponse

logger = logging.getLogger(__name__)


class StorageService:
    """Service for managing file storage and media operations."""
    
    def __init__(self):
        self.db = None
        self.storage_repo = None
        self.generation_repo = None
    
    async def _get_repositories(self):
        """Initialize repositories if not already done."""
        if self.db is None:
            self.db = await get_database()
            self.storage_repo = StorageRepository(self.db)
            self.generation_repo = GenerationRepository(self.db)
    
    # === File Upload Operations ===
    
    async def upload_file(
        self,
        user_id: Union[UUID, str],
        file_data: bytes,
        upload_request: FileUploadRequest,
        generation_id: Optional[Union[UUID, str]] = None
    ) -> FileMetadataResponse:
        """
        Upload file with comprehensive validation and processing.
        
        Args:
            user_id: User uploading the file
            file_data: Raw file bytes
            upload_request: Upload parameters and metadata
            generation_id: Optional generation to associate with
            
        Returns:
            Created file metadata
        """
        # Convert string user_id to UUID for consistency
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(generation_id, str) and generation_id is not None:
            generation_id = UUID(generation_id)
            
        logger.info(f"📤 [STORAGE-FILE] Starting file upload for user {str(user_id)}")
        # Safe enum value extraction to prevent AttributeError
        content_type_str = upload_request.content_type.value if hasattr(upload_request.content_type, 'value') else str(upload_request.content_type)
        bucket_name_str = upload_request.bucket_name.value if hasattr(upload_request.bucket_name, 'value') else str(upload_request.bucket_name)
        
        logger.info(f"🔍 [STORAGE-FILE] Upload details: filename={upload_request.filename}, size={len(file_data)}, type={content_type_str}, bucket={bucket_name_str}")
        
        await self._get_repositories()
        
        try:
            # Validate file content and size
            logger.info(f"✅ [STORAGE-FILE] Validating file upload...")
            await self._validate_file_upload(file_data, upload_request)
            logger.info(f"✅ [STORAGE-FILE] File validation passed")
            
            # Generate secure file path with project support
            file_path = self._generate_secure_file_path(
                user_id=user_id,
                filename=upload_request.filename,
                bucket=upload_request.bucket_name,
                generation_id=generation_id,
                project_id=getattr(upload_request, 'project_id', None)
            )
            logger.info(f"📁 [STORAGE-FILE] Generated secure file path: {file_path}")
            
            # Calculate file hash for deduplication
            file_hash = self._calculate_file_hash(file_data)
            logger.info(f"🔐 [STORAGE-FILE] Calculated file hash: {file_hash[:16]}...")
            
            # Check for duplicate files
            existing_file = await self._check_duplicate_file(user_id, file_hash, upload_request.bucket_name)
            if existing_file and upload_request.bucket_name != StorageBucket.TEMP:
                logger.info(f"🔄 [STORAGE-FILE] Duplicate file found for user {str(user_id)}: {existing_file.file_path}")
                logger.info(f"♾️ [STORAGE-FILE] Returning existing file instead of re-uploading")
                return existing_file
            
            # Upload to Supabase Storage
            logger.info(f"☁️ [STORAGE-FILE] Uploading to Supabase Storage repository...")
            # Safe enum value extraction
            content_type_value = upload_request.content_type.value if hasattr(upload_request.content_type, 'value') else str(upload_request.content_type)
            
            uploaded_path = await self.storage_repo.upload_file(
                bucket_name=upload_request.bucket_name,
                file_path=file_path,
                file_data=file_data,
                content_type=content_type_value,
                user_id=user_id
            )
            logger.info(f"✅ [STORAGE-FILE] File uploaded to Supabase Storage: {uploaded_path}")
            
            # Create file metadata
            metadata_create = FileMetadataCreate(
                bucket_name=upload_request.bucket_name,
                file_path=uploaded_path,
                original_filename=upload_request.filename,
                file_size=len(file_data),
                content_type=upload_request.content_type,
                file_hash=file_hash,
                is_thumbnail=False,
                is_processed=False,
                metadata=upload_request.metadata,
                expires_at=self._calculate_expiry(upload_request.bucket_name)
            )
            
            logger.info(f"📝 [STORAGE-FILE] Creating file metadata in database...")
            file_metadata = await self.storage_repo.create_file_metadata(
                metadata=metadata_create,
                user_id=user_id
            )
            logger.info(f"✅ [STORAGE-FILE] File metadata created: ID={file_metadata.id}")
            
            # Update generation metadata if provided
            if generation_id:
                logger.info(f"🔗 [STORAGE-FILE] Linking file to generation {generation_id}...")
                await self._link_file_to_generation(file_metadata, generation_id, user_id)
                logger.info(f"✅ [STORAGE-FILE] File linked to generation successfully")
            
            # Process thumbnails for images - safe enum handling
            content_type_value = upload_request.content_type.value if hasattr(upload_request.content_type, 'value') else str(upload_request.content_type)
            if content_type_value.startswith("image/"):
                logger.info(f"🖼️ [STORAGE-FILE] Scheduling thumbnail generation for image file...")
                asyncio.create_task(
                    self._generate_thumbnails(file_metadata, file_data, user_id)
                )
            
            logger.info(f"🎉 [STORAGE-FILE] File upload completed successfully: {uploaded_path} for user {str(user_id)}")
            logger.info(f"🔍 [STORAGE-FILE] Final file metadata: ID={file_metadata.id}, Path={file_metadata.file_path}, Size={file_metadata.file_size}")
            return file_metadata
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-FILE] Failed to upload file for user {str(user_id)}: {e}")
            logger.error(f"❌ [STORAGE-FILE] Upload error type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ [STORAGE-FILE] Upload error traceback: {traceback.format_exc()}")
            raise
    
    async def upload_generation_result(
        self,
        user_id: Union[UUID, str],
        generation_id: Union[UUID, str],
        file_urls: List[str],
        file_type: str = "image",
        project_id: Optional[Union[UUID, str]] = None,
        progress_callback: Optional[callable] = None
    ) -> List[FileMetadataResponse]:
        """
        Upload generation results from external URLs.
        
        Args:
            user_id: User who owns the generation
            generation_id: Generation ID
            file_urls: List of URLs to download and store
            file_type: Type of files (image/video)
            project_id: Optional project ID for organization
            
        Returns:
            List of created file metadata
        """
        # Convert string IDs to UUID objects for consistency
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(generation_id, str):
            generation_id = UUID(generation_id)
        if isinstance(project_id, str) and project_id:
            project_id = UUID(project_id)
            
        logger.info(f"📦 [STORAGE-UPLOAD] Starting upload of generation results for generation {generation_id}")
        logger.info(f"🔍 [STORAGE-UPLOAD] User: {user_id}, File count: {len(file_urls)}, Type: {file_type}")
        
        await self._get_repositories()
        
        try:
            uploaded_files = []
            
            for i, url in enumerate(file_urls):
                logger.info(f"📥 [STORAGE-UPLOAD] Processing file {i+1}/{len(file_urls)}: {url[:100]}{'...' if len(url) > 100 else ''}")
                
                # Update progress if callback provided - handle signature mismatch
                if progress_callback:
                    try:
                        # Try dictionary-style callback first
                        await progress_callback({
                            'stage': 'downloading',
                            'current_file': i + 1,
                            'total_files': len(file_urls),
                            'percentage': (i / len(file_urls)) * 50  # First 50% is downloading
                        })
                    except TypeError as te:
                        # Fallback to individual parameters if signature mismatch
                        try:
                            await progress_callback(i + 1, len(file_urls), f"Downloading file {i + 1}")
                        except Exception as cb_error:
                            logger.warning(f"⚠️ [STORAGE-UPLOAD] Progress callback error: {cb_error}")
                
                max_retries = 3
                retry_delay = 2  # seconds
                
                for attempt in range(max_retries):
                    try:
                        # Download file from URL with enhanced error handling
                        logger.info(f"⬇️ [STORAGE-UPLOAD] Downloading file from external URL (attempt {attempt + 1}/{max_retries})...")
                        file_data = await self._download_file_from_url(url, max_retries=2, timeout=120.0)
                        logger.info(f"✅ [STORAGE-UPLOAD] File downloaded successfully: {len(file_data)} bytes")
                        break  # Success, exit retry loop
                        
                    except Exception as download_error:
                        logger.error(f"❌ [STORAGE-UPLOAD] Download attempt {attempt + 1} failed: {download_error}")
                        
                        if attempt == max_retries - 1:
                            # Last attempt failed, skip this file
                            logger.error(f"❌ [STORAGE-UPLOAD] All download attempts failed for file {i+1}, skipping...")
                            continue  # Skip to next file in outer loop
                        
                        # Wait before retry
                        await asyncio.sleep(retry_delay * (attempt + 1))
                        continue
                else:
                    # This executes only if the for loop completed without break (all attempts failed)
                    logger.error(f"❌ [STORAGE-UPLOAD] Failed to download file {i+1} after {max_retries} attempts, skipping")
                    continue  # Skip to next file
                
                try:
                    # Determine content type and extension
                    content_type, extension = self._detect_content_type(file_data, url)
                    logger.info(f"🔍 [STORAGE-UPLOAD] Detected content type: {content_type}, extension: {extension}")
                    
                    # Generate filename - ensure generation_id is converted to string
                    filename = f"generation_{str(generation_id)}_{i+1}.{extension}"
                    logger.info(f"📁 [STORAGE-UPLOAD] Generated filename: {filename}")
                    
                    # Create upload request
                    upload_request = FileUploadRequest(
                    bucket_name=StorageBucket.GENERATIONS,
                    filename=filename,
                    content_type=ContentType(content_type),
                        file_size=len(file_data),
                        generation_id=generation_id,
                        project_id=project_id,
                        metadata={
                            "source_url": url,
                            "generation_id": str(generation_id),
                            "project_id": str(project_id) if project_id else None,
                            "file_index": i,
                            "upload_type": "generation_result",
                            "original_external_url": url
                        }
                    )
                    
                    # Safe enum value extraction
                    bucket_value = StorageBucket.GENERATIONS.value if hasattr(StorageBucket.GENERATIONS, 'value') else str(StorageBucket.GENERATIONS)
                    logger.info(f"☁️ [STORAGE-UPLOAD] Uploading file to Supabase Storage bucket: {bucket_value}")
                    
                    # Upload file with progress tracking - handle signature mismatch
                    if progress_callback:
                        try:
                            # Try dictionary-style callback first
                            await progress_callback({
                                'stage': 'uploading',
                                'current_file': i + 1,
                                'total_files': len(file_urls),
                                'percentage': 50 + ((i / len(file_urls)) * 50)  # Second 50% is uploading
                            })
                        except TypeError as te:
                            # Fallback to individual parameters if signature mismatch
                            try:
                                await progress_callback(i + 1, len(file_urls), f"Uploading file {i + 1}")
                            except Exception as cb_error:
                                logger.warning(f"⚠️ [STORAGE-UPLOAD] Upload progress callback error: {cb_error}")
                    
                    # Upload with retry logic
                    upload_retries = 2
                    file_metadata = None
                    
                    for upload_attempt in range(upload_retries):
                        try:
                            file_metadata = await self.upload_file(
                                user_id=user_id,
                                file_data=file_data,
                                upload_request=upload_request,
                                generation_id=generation_id
                            )
                            break  # Success, exit retry loop
                            
                        except Exception as upload_error:
                            logger.error(f"❌ [STORAGE-UPLOAD] Upload attempt {upload_attempt + 1} failed: {upload_error}")
                            
                            if upload_attempt == upload_retries - 1:
                                # Last attempt failed
                                raise upload_error
                            
                            # Wait before retry
                            await asyncio.sleep(1.0 * (upload_attempt + 1))
                    
                    if not file_metadata:
                        raise RuntimeError("Upload failed after all retry attempts")
                    
                    logger.info(f"✅ [STORAGE-UPLOAD] File uploaded successfully: {file_metadata.file_path}")
                    # Safe enum value extraction
                    bucket_value = file_metadata.bucket_name.value if hasattr(file_metadata.bucket_name, 'value') else str(file_metadata.bucket_name)
                    logger.info(f"🔍 [STORAGE-UPLOAD] File metadata: ID={file_metadata.id}, Size={file_metadata.file_size}, Bucket={bucket_value}")
                    
                    uploaded_files.append(file_metadata)
                    
                except Exception as e:
                    logger.error(f"❌ [STORAGE-UPLOAD] Failed to upload generation result file {i+1} from {url}: {e}")
                    logger.error(f"❌ [STORAGE-UPLOAD] File upload error type: {type(e).__name__}")
                    import traceback
                    logger.error(f"❌ [STORAGE-UPLOAD] File upload traceback: {traceback.format_exc()}")
                    continue
            
            logger.info(f"🎉 [STORAGE-UPLOAD] Upload process completed: {len(uploaded_files)}/{len(file_urls)} files uploaded successfully for generation {generation_id}")
            
            if len(uploaded_files) == 0:
                logger.error(f"❌ [STORAGE-UPLOAD] No files were uploaded successfully for generation {generation_id}")
                raise ValueError(f"Failed to upload any generation result files")
            elif len(uploaded_files) < len(file_urls):
                logger.warning(f"⚠️ [STORAGE-UPLOAD] Partial upload success: {len(uploaded_files)}/{len(file_urls)} files uploaded")
            
            return uploaded_files
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-UPLOAD] Critical failure uploading generation results for generation {generation_id}: {e}")
            logger.error(f"❌ [STORAGE-UPLOAD] Critical error type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ [STORAGE-UPLOAD] Critical error traceback: {traceback.format_exc()}")
            raise
    
    # === File Access Operations ===
    
    async def get_file_metadata(
        self,
        file_id: UUID,
        user_id: UUID
    ) -> FileMetadataResponse:
        """Get file metadata with user verification."""
        await self._get_repositories()
        
        file_metadata = await self.storage_repo.get_file_metadata(file_id, user_id)
        if not file_metadata:
            raise ValueError(f"File {file_id} not found or access denied")
        
        return file_metadata
    
    async def get_signed_url(
        self,
        file_id: UUID,
        user_id: UUID,
        expires_in: int = 3600
    ) -> StorageUrlResponse:
        """Get signed URL for file access."""
        await self._get_repositories()
        
        # Get file metadata and verify ownership
        file_metadata = await self.get_file_metadata(file_id, user_id)
        
        # Create signed URL
        return await self.storage_repo.create_signed_url(
            bucket_name=file_metadata.bucket_name,
            file_path=file_metadata.file_path,
            expires_in=expires_in,
            user_id=user_id
        )
    
    async def download_file(
        self,
        file_id: UUID,
        user_id: UUID
    ) -> Tuple[bytes, FileMetadataResponse]:
        """Download file data with metadata."""
        await self._get_repositories()
        
        # Get file metadata and verify ownership
        file_metadata = await self.get_file_metadata(file_id, user_id)
        
        # Download file data
        file_data = await self.storage_repo.download_file(
            bucket_name=file_metadata.bucket_name,
            file_path=file_metadata.file_path,
            user_id=user_id
        )
        
        return file_data, file_metadata
    
    async def list_user_files(
        self,
        user_id: UUID,
        bucket_name: Optional[StorageBucket] = None,
        generation_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[FileMetadataResponse]:
        """List user's files with filtering."""
        await self._get_repositories()
        
        return await self.storage_repo.list_user_files(
            user_id=user_id,
            bucket_name=bucket_name,
            generation_id=generation_id,
            limit=limit,
            offset=offset
        )
    
    # === File Management Operations ===
    
    async def delete_file(
        self,
        file_id: UUID,
        user_id: UUID,
        force: bool = False
    ) -> bool:
        """
        Delete file with business logic validation.
        
        Args:
            file_id: File to delete
            user_id: User requesting deletion
            force: Force delete even if referenced by generations
            
        Returns:
            True if deleted successfully
        """
        await self._get_repositories()
        
        # Get file metadata and verify ownership
        file_metadata = await self.get_file_metadata(file_id, user_id)
        
        # Check if file is referenced by any generations (unless forced)
        if not force and file_metadata.generation_id:
            generation = await self.generation_repo.get_generation_by_id(str(file_metadata.generation_id))
            if generation and generation.status in ["pending", "processing", "completed"]:
                raise ValueError("Cannot delete file referenced by active generation. Use force=True to override.")
        
        # Delete thumbnails if this is a main image
        if not file_metadata.is_thumbnail:
            await self._delete_file_thumbnails(file_metadata, user_id)
        
        # Delete from storage
        success = await self.storage_repo.delete_file(
            bucket_name=file_metadata.bucket_name,
            file_path=file_metadata.file_path,
            user_id=user_id
        )
        
        if success:
            # Delete metadata
            await self.storage_repo.delete_file_metadata(file_id, user_id)
            
            # Update generation metadata if applicable
            if file_metadata.generation_id:
                await self._unlink_file_from_generation(file_metadata, user_id)
        
        return success
    
    async def bulk_delete_files(
        self,
        delete_request: BulkDeleteRequest,
        user_id: UUID
    ) -> ProcessingResult:
        """Bulk delete files with validation."""
        await self._get_repositories()
        
        return await self.storage_repo.bulk_delete_files(
            bucket_name=delete_request.bucket_name,
            file_paths=delete_request.file_paths,
            user_id=user_id,
            force=delete_request.force
        )
    
    async def move_file(
        self,
        file_id: UUID,
        dest_bucket: StorageBucket,
        user_id: UUID
    ) -> FileMetadataResponse:
        """Move file between buckets."""
        await self._get_repositories()
        
        # Get file metadata and verify ownership
        file_metadata = await self.get_file_metadata(file_id, user_id)
        
        # Generate new path in destination bucket
        dest_path = self._generate_secure_file_path(
            user_id=user_id,
            filename=file_metadata.original_filename or "file",
            bucket=dest_bucket
        )
        
        # Move file in storage
        success = await self.storage_repo.move_file(
            bucket_name=file_metadata.bucket_name,
            source_path=file_metadata.file_path,
            dest_path=dest_path,
            user_id=user_id
        )
        
        if success:
            # Update metadata
            update_data = FileMetadataUpdate(bucket_name=dest_bucket, file_path=dest_path)
            return await self.storage_repo.update_file_metadata(file_id, update_data, user_id)
        
        raise Exception("Failed to move file")
    
    # === Thumbnail and Processing Operations ===
    
    async def _generate_thumbnails(
        self,
        file_metadata: FileMetadataResponse,
        original_data: bytes,
        user_id: UUID
    ):
        """Generate thumbnails for image files."""
        try:
            if not file_metadata.content_type.startswith("image/"):
                return
            
            thumbnail_sizes = [
                (256, 256, "thumb_256"),
                (512, 512, "thumb_512"),
                (1024, 1024, "thumb_1024")
            ]
            
            for width, height, suffix in thumbnail_sizes:
                try:
                    # Generate thumbnail
                    thumbnail_data = await self._create_thumbnail(original_data, width, height)
                    
                    # Generate thumbnail filename
                    original_name = Path(file_metadata.original_filename or "image")
                    thumbnail_filename = f"{original_name.stem}_{suffix}{original_name.suffix}"
                    
                    # Upload thumbnail
                    thumbnail_path = self._generate_secure_file_path(
                        user_id=user_id,
                        filename=thumbnail_filename,
                        bucket=StorageBucket.THUMBNAILS,
                        generation_id=file_metadata.generation_id
                    )
                    
                    await self.storage_repo.upload_file(
                        bucket_name=StorageBucket.THUMBNAILS,
                        file_path=thumbnail_path,
                        file_data=thumbnail_data,
                        content_type="image/webp",  # Always use WebP for thumbnails
                        user_id=user_id
                    )
                    
                    # Create thumbnail metadata
                    thumbnail_metadata = FileMetadataCreate(
                        bucket_name=StorageBucket.THUMBNAILS,
                        file_path=thumbnail_path,
                        original_filename=thumbnail_filename,
                        file_size=len(thumbnail_data),
                        content_type=ContentType.WEBP,
                        file_hash=self._calculate_file_hash(thumbnail_data),
                        is_thumbnail=True,
                        is_processed=True,
                        metadata={
                            "original_file_id": str(file_metadata.id),
                            "thumbnail_size": f"{width}x{height}",
                            "compression": "webp"
                        }
                    )
                    
                    await self.storage_repo.create_file_metadata(
                        metadata=thumbnail_metadata,
                        user_id=user_id
                    )
                    
                except Exception as e:
                    logger.error(f"Failed to generate {width}x{height} thumbnail: {e}")
                    continue
            
            # Mark original file as processed
            await self.storage_repo.update_file_metadata(
                file_metadata.id,
                FileMetadataUpdate(is_processed=True),
                user_id
            )
            
        except Exception as e:
            logger.error(f"Failed to generate thumbnails for file {file_metadata.id}: {e}")
    
    async def _create_thumbnail(self, image_data: bytes, width: int, height: int) -> bytes:
        """Create thumbnail from image data."""
        try:
            # Open image
            image = Image.open(io.BytesIO(image_data))
            
            # Convert to RGB if necessary
            if image.mode != "RGB":
                image = image.convert("RGB")
            
            # Create thumbnail maintaining aspect ratio
            image.thumbnail((width, height), Image.Resampling.LANCZOS)
            
            # Save as WebP with optimization
            output = io.BytesIO()
            image.save(output, format="WEBP", quality=85, optimize=True)
            
            return output.getvalue()
            
        except Exception as e:
            logger.error(f"Failed to create thumbnail: {e}")
            raise
    
    # === Statistics and Management ===
    
    async def get_user_storage_stats(self, user_id: UUID) -> StorageStatsResponse:
        """Get comprehensive storage statistics for user."""
        await self._get_repositories()
        
        return await self.storage_repo.get_user_storage_stats(user_id)
    
    async def cleanup_expired_files(self) -> int:
        """Clean up expired temporary files."""
        await self._get_repositories()
        
        return await self.storage_repo.cleanup_expired_temp_files()
    
    async def find_duplicate_files(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Find duplicate files for user."""
        await self._get_repositories()
        
        return await self.storage_repo.find_duplicate_files(user_id)
    
    async def verify_file_integrity(
        self,
        file_id: UUID,
        user_id: UUID
    ) -> bool:
        """Verify file integrity using hash comparison."""
        await self._get_repositories()
        
        file_metadata = await self.get_file_metadata(file_id, user_id)
        
        if not file_metadata.file_hash:
            logger.warning(f"No hash available for file {file_id}")
            return False
        
        return await self.storage_repo.verify_file_integrity(
            bucket_name=file_metadata.bucket_name,
            file_path=file_metadata.file_path,
            expected_hash=file_metadata.file_hash,
            user_id=user_id
        )
    
    # === Storage Folder Management ===
    
    async def create_user_storage_folders(self, user_id: UUID) -> bool:
        """
        Create user storage folder structure when user signs up.
        
        Creates the base user folder structure in all storage buckets.
        This should be called when a user account is created.
        """
        logger.info(f"📁 [STORAGE-SETUP] Creating storage folders for user {user_id}")
        
        try:
            await self._get_repositories()
            
            # Create placeholder files to ensure folder structure exists
            # Supabase Storage creates folders implicitly when files are uploaded
            placeholder_content = b"# Placeholder file to maintain folder structure"
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            
            user_str = str(user_id)
            folders_created = []
            
            # Create base user folders in each bucket
            buckets_to_setup = [
                StorageBucket.GENERATIONS,
                StorageBucket.UPLOADS, 
                StorageBucket.THUMBNAILS,
                StorageBucket.TEMP
            ]
            
            for bucket in buckets_to_setup:
                try:
                    placeholder_path = f"{user_str}/.folder_placeholder_{timestamp}.txt"
                    
                    await self.storage_repo.upload_file(
                        bucket_name=bucket,
                        file_path=placeholder_path,
                        file_data=placeholder_content,
                        content_type="text/plain",
                        user_id=user_id
                    )
                    
                    bucket_value = bucket.value if hasattr(bucket, 'value') else str(bucket)
                    folders_created.append(f"{bucket_value}/{user_str}")
                    logger.info(f"✅ [STORAGE-SETUP] Created folder: {bucket_value}/{user_str}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ [STORAGE-SETUP] Failed to create folder {bucket_value}/{user_str}: {e}")
                    continue
            
            logger.info(f"🎉 [STORAGE-SETUP] User storage setup complete: {len(folders_created)} folders created for user {user_id}")
            return len(folders_created) > 0
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-SETUP] Failed to create user storage folders for {user_id}: {e}")
            return False
    
    async def create_project_storage_folders(self, user_id: UUID, project_id: UUID) -> bool:
        """
        Create project-specific storage folder structure.
        
        Creates project folders within the user's storage for organized media management.
        This should be called when a project is created.
        """
        logger.info(f"📁 [STORAGE-PROJECT] Creating project storage folders for user {user_id}, project {project_id}")
        
        try:
            await self._get_repositories()
            
            # Create placeholder files to ensure project folder structure exists
            placeholder_content = f"# Project {project_id} storage folder - created {datetime.utcnow().isoformat()}".encode()
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            
            user_str = str(user_id)
            project_str = str(project_id)
            folders_created = []
            
            # Create project subfolders in each bucket (except temp)
            project_buckets = [
                StorageBucket.GENERATIONS,
                StorageBucket.UPLOADS,
                StorageBucket.THUMBNAILS
            ]
            
            for bucket in project_buckets:
                try:
                    placeholder_path = f"{user_str}/projects/{project_str}/.project_placeholder_{timestamp}.txt"
                    
                    await self.storage_repo.upload_file(
                        bucket_name=bucket,
                        file_path=placeholder_path,
                        file_data=placeholder_content,
                        content_type="text/plain",
                        user_id=user_id
                    )
                    
                    bucket_value = bucket.value if hasattr(bucket, 'value') else str(bucket)
                    folders_created.append(f"{bucket_value}/{user_str}/projects/{project_str}")
                    logger.info(f"✅ [STORAGE-PROJECT] Created project folder: {bucket_value}/{user_str}/projects/{project_str}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ [STORAGE-PROJECT] Failed to create project folder {bucket_value}/{user_str}/projects/{project_str}: {e}")
                    continue
            
            logger.info(f"🎉 [STORAGE-PROJECT] Project storage setup complete: {len(folders_created)} folders created for project {project_id}")
            return len(folders_created) > 0
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-PROJECT] Failed to create project storage folders for {user_id}/{project_id}: {e}")
            return False
    
    async def move_media_between_projects(
        self,
        user_id: UUID,
        file_id: UUID,
        source_project_id: UUID,
        destination_project_id: UUID
    ) -> bool:
        """
        Move media file from one project to another.
        
        Updates the file's storage path and metadata to reflect the new project.
        This enables the frontend to reassign media between projects.
        """
        logger.info(f"🔄 [STORAGE-MOVE] Moving file {file_id} from project {source_project_id} to {destination_project_id} for user {user_id}")
        
        try:
            await self._get_repositories()
            
            # Get file metadata and verify ownership
            file_metadata = await self.get_file_metadata(file_id, user_id)
            if not file_metadata:
                raise ValueError(f"File {file_id} not found or access denied")
            
            # Generate new path in destination project
            new_file_path = self._generate_secure_file_path(
                user_id=user_id,
                filename=file_metadata.original_filename or "moved_file",
                bucket=file_metadata.bucket_name,
                generation_id=file_metadata.generation_id,
                project_id=destination_project_id
            )
            
            logger.info(f"📁 [STORAGE-MOVE] New path: {file_metadata.file_path} -> {new_file_path}")
            
            # Move file in storage
            success = await self.storage_repo.move_file(
                bucket_name=file_metadata.bucket_name,
                source_path=file_metadata.file_path,
                dest_path=new_file_path,
                user_id=user_id
            )
            
            if success:
                # Update metadata with new path
                update_data = FileMetadataUpdate(
                    file_path=new_file_path,
                    metadata={
                        **file_metadata.metadata,
                        "moved_from_project": str(source_project_id),
                        "moved_to_project": str(destination_project_id),
                        "moved_at": datetime.utcnow().isoformat()
                    }
                )
                
                await self.storage_repo.update_file_metadata(file_id, update_data, user_id)
                
                logger.info(f"✅ [STORAGE-MOVE] Successfully moved file {file_id} between projects")
                return True
            else:
                logger.error(f"❌ [STORAGE-MOVE] Failed to move file {file_id} in storage")
                return False
                
        except Exception as e:
            logger.error(f"❌ [STORAGE-MOVE] Failed to move file {file_id} between projects: {e}")
            return False
    
    # === Helper Methods ===
    
    async def _validate_file_upload(self, file_data: bytes, upload_request: FileUploadRequest):
        """Validate file upload request."""
        # Check file size matches
        if len(file_data) != upload_request.file_size:
            raise ValueError("File size mismatch")
        
        # Validate file signature matches content type
        detected_type, _ = self._detect_content_type(file_data)
        if not self._is_content_type_compatible(detected_type, upload_request.content_type.value):
            raise ValueError(f"File content does not match declared type: {upload_request.content_type.value}")
        
        # Check for malicious content
        if self._contains_malicious_content(file_data):
            raise ValueError("File contains potentially malicious content")
    
    def _generate_secure_file_path(
        self,
        user_id: UUID,
        filename: str,
        bucket: StorageBucket,
        generation_id: Optional[UUID] = None,
        project_id: Optional[UUID] = None
    ) -> str:
        """Generate secure file path with user and project isolation."""
        # Sanitize filename
        safe_filename = Path(filename).name
        safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in ".-_").strip()
        
        if not safe_filename:
            safe_filename = f"file_{uuid4().hex[:8]}"
        
        # Generate unique filename to prevent conflicts
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid4().hex[:8]
        unique_filename = f"{timestamp}_{unique_id}_{safe_filename}"
        
        # Build path based on bucket type with project-based organization
        user_str = str(user_id)
        
        if bucket == StorageBucket.TEMP:
            # Temp files don't need project organization
            return f"{user_str}/temp/{unique_filename}"
        
        # All other buckets use project-based organization
        if project_id:
            project_str = str(project_id)
            if bucket == StorageBucket.GENERATIONS:
                if generation_id:
                    return f"{user_str}/projects/{project_str}/generations/{str(generation_id)}/{unique_filename}"
                else:
                    return f"{user_str}/projects/{project_str}/generations/{unique_filename}"
            elif bucket == StorageBucket.UPLOADS:
                return f"{user_str}/projects/{project_str}/uploads/{unique_filename}"
            elif bucket == StorageBucket.THUMBNAILS:
                return f"{user_str}/projects/{project_str}/thumbnails/{unique_filename}"
            else:
                return f"{user_str}/projects/{project_str}/{unique_filename}"
        else:
            # Fallback to legacy structure for backwards compatibility
            if bucket == StorageBucket.GENERATIONS and generation_id:
                return f"{user_str}/generations/{str(generation_id)}/{unique_filename}"
            elif bucket == StorageBucket.UPLOADS:
                return f"{user_str}/uploads/{unique_filename}"
            elif bucket == StorageBucket.THUMBNAILS:
                return f"{user_str}/thumbnails/{unique_filename}"
            else:
                return f"{user_str}/{unique_filename}"
    
    def _calculate_file_hash(self, file_data: bytes) -> str:
        """Calculate SHA-256 hash of file data."""
        return hashlib.sha256(file_data).hexdigest()
    
    def _calculate_expiry(self, bucket: StorageBucket) -> Optional[datetime]:
        """Calculate expiry time for temporary files."""
        if bucket == StorageBucket.TEMP:
            return datetime.utcnow() + timedelta(hours=24)
        return None
    
    def _detect_content_type(self, file_data: bytes, url: Optional[str] = None) -> Tuple[str, str]:
        """Detect content type and extension from file data."""
        # Check file signature (magic bytes)
        if file_data.startswith(b'\xff\xd8\xff'):
            return "image/jpeg", "jpg"
        elif file_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return "image/png", "png"
        elif file_data.startswith(b'RIFF') and b'WEBP' in file_data[:12]:
            return "image/webp", "webp"
        elif file_data.startswith(b'GIF8'):
            return "image/gif", "gif"
        elif file_data.startswith(b'\x00\x00\x00\x20ftypmp4'):
            return "video/mp4", "mp4"
        
        # Fallback to URL-based detection
        if url:
            content_type, _ = mimetypes.guess_type(url)
            if content_type:
                extension = mimetypes.guess_extension(content_type) or ""
                return content_type, extension.lstrip(".")
        
        return "application/octet-stream", "bin"
    
    def _is_content_type_compatible(self, detected: str, declared: str) -> bool:
        """Check if detected content type is compatible with declared type."""
        # Normalize types
        detected = detected.lower()
        declared = declared.lower()
        
        # Exact match
        if detected == declared:
            return True
        
        # JPEG variations
        if detected in ["image/jpeg", "image/jpg"] and declared in ["image/jpeg", "image/jpg"]:
            return True
        
        # Allow generic image type for specific image types
        if detected.startswith("image/") and declared == "image/*":
            return True
        
        return False
    
    def _contains_malicious_content(self, file_data: bytes) -> bool:
        """Basic check for malicious content."""
        # Check for executable signatures
        malicious_signatures = [
            b'MZ',  # Windows executable
            b'\x7fELF',  # Linux executable
            b'\xfe\xed\xfa',  # Mach-O executable
            b'<script',  # JavaScript
            b'javascript:',  # JavaScript URL
        ]
        
        file_start = file_data[:1024].lower()
        return any(sig in file_start for sig in malicious_signatures)
    
    async def _check_duplicate_file(
        self,
        user_id: UUID,
        file_hash: str,
        bucket: StorageBucket
    ) -> Optional[FileMetadataResponse]:
        """Check if file with same hash already exists for user."""
        try:
            files = await self.storage_repo.list_user_files(user_id, bucket, limit=1000)
            for file_meta in files:
                if file_meta.file_hash == file_hash:
                    return file_meta
            return None
        except Exception as e:
            logger.error(f"Failed to check for duplicate files: {e}")
            return None
    
    async def _download_file_from_url(self, url: str, max_retries: int = 3, timeout: float = 60.0) -> bytes:
        """Download file from external URL with retry logic and progress tracking."""
        import httpx
        import asyncio
        from datetime import datetime
        
        logger.info(f"🌐 [DOWNLOAD] Starting download from URL: {url[:100]}{'...' if len(url) > 100 else ''}")
        
        for attempt in range(max_retries):
            try:
                start_time = datetime.utcnow()
                
                async with httpx.AsyncClient() as client:
                    logger.info(f"📥 [DOWNLOAD] Attempt {attempt + 1}/{max_retries} - Downloading from FAL.ai...")
                    
                    response = await client.get(
                        url, 
                        timeout=timeout,
                        follow_redirects=True,
                        headers={
                            'User-Agent': 'Velro-Backend/1.0 (Storage-Service)',
                            'Accept': 'image/*, video/*, application/octet-stream'
                        }
                    )
                    
                    response.raise_for_status()
                    content = response.content
                    
                    # Log download metrics
                    download_time = (datetime.utcnow() - start_time).total_seconds()
                    content_length = len(content)
                    
                    logger.info(f"✅ [DOWNLOAD] Success: {content_length} bytes downloaded in {download_time:.2f}s")
                    logger.info(f"📊 [DOWNLOAD] Speed: {content_length / download_time / 1024:.2f} KB/s")
                    
                    # Validate minimum file size (prevent empty/corrupt downloads)
                    if content_length < 100:  # Less than 100 bytes is suspicious
                        raise ValueError(f"Downloaded file is too small ({content_length} bytes), possibly corrupted")
                    
                    # Validate maximum file size (prevent memory issues)
                    max_file_size = 100 * 1024 * 1024  # 100MB limit
                    if content_length > max_file_size:
                        raise ValueError(f"Downloaded file is too large ({content_length} bytes), exceeds {max_file_size} bytes limit")
                    
                    return content
                    
            except (httpx.TimeoutException, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
                logger.warning(f"⏰ [DOWNLOAD] Timeout on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Download failed after {max_retries} attempts due to timeout")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                logger.error(f"❌ [DOWNLOAD] HTTP error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Download failed after {max_retries} attempts: {str(e)}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            except Exception as e:
                logger.error(f"💥 [DOWNLOAD] Unexpected error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Download failed after {max_retries} attempts: {str(e)}")
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        raise RuntimeError(f"Download failed after all {max_retries} attempts")
    
    async def _link_file_to_generation(
        self,
        file_metadata: FileMetadataResponse,
        generation_id: UUID,
        user_id: UUID
    ):
        """Link file to generation in metadata."""
        try:
            generation = await self.generation_repo.get_generation_by_id(str(generation_id))
            if generation and generation.user_id == str(user_id):
                # Update generation with file information
                media_files = generation.media_files or []
                media_files.append({
                    "file_id": str(file_metadata.id),
                    "bucket": file_metadata.bucket_name.value if hasattr(file_metadata.bucket_name, 'value') else str(file_metadata.bucket_name),
                    "path": file_metadata.file_path,
                    "size": file_metadata.file_size,
                    "content_type": file_metadata.content_type.value if hasattr(file_metadata.content_type, 'value') else str(file_metadata.content_type)
                })
                
                await self.generation_repo.update_generation(
                    str(generation_id),
                    {"media_files": media_files}
                )
        except Exception as e:
            logger.error(f"Failed to link file to generation {generation_id}: {e}")
    
    async def _unlink_file_from_generation(
        self,
        file_metadata: FileMetadataResponse,
        user_id: UUID
    ):
        """Remove file link from generation metadata."""
        try:
            if file_metadata.generation_id:
                generation = await self.generation_repo.get_generation_by_id(str(file_metadata.generation_id))
                if generation and generation.user_id == str(user_id):
                    media_files = generation.media_files or []
                    media_files = [f for f in media_files if f.get("file_id") != str(file_metadata.id)]
                    
                    await self.generation_repo.update_generation(
                        str(file_metadata.generation_id),
                        {"media_files": media_files}
                    )
        except Exception as e:
            logger.error(f"Failed to unlink file from generation: {e}")
    
    async def _delete_file_thumbnails(self, file_metadata: FileMetadataResponse, user_id: UUID):
        """Delete all thumbnails associated with a file."""
        try:
            thumbnails = await self.storage_repo.list_user_files(
                user_id=user_id,
                bucket_name=StorageBucket.THUMBNAILS,
                limit=100
            )
            
            for thumbnail in thumbnails:
                thumbnail_meta = thumbnail.metadata or {}
                if thumbnail_meta.get("original_file_id") == str(file_metadata.id):
                    await self.storage_repo.delete_file(
                        bucket_name=StorageBucket.THUMBNAILS,
                        file_path=thumbnail.file_path,
                        user_id=user_id
                    )
                    await self.storage_repo.delete_file_metadata(thumbnail.id, user_id)
                    
        except Exception as e:
            logger.error(f"Failed to delete thumbnails for file {file_metadata.id}: {e}")
    
    async def _get_storage_client(self):
        """
        EMERGENCY FIX: Compatibility method for generation service dependency check.
        This method exists to prevent 503 errors in production when generation service
        calls this method during dependency validation.
        """
        logger.info("🔧 [STORAGE-CLIENT] Compatibility method called - ensuring repositories are initialized")
        await self._get_repositories()
        return True
    
    # === Enhanced Storage Management Methods ===
    
    async def cleanup_failed_generation_files(
        self,
        generation_id: Union[UUID, str],
        user_id: Union[UUID, str]
    ) -> int:
        """
        Clean up storage files from a failed generation.
        
        Args:
            generation_id: Generation ID to clean up
            user_id: User ID for ownership verification
            
        Returns:
            Number of files cleaned up
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(generation_id, str):
            generation_id = UUID(generation_id)
            
        logger.info(f"🧹 [STORAGE-CLEANUP] Starting cleanup for failed generation {generation_id}")
        
        try:
            await self._get_repositories()
            
            # Find all files associated with this generation
            generation_files = await self.storage_repo.list_user_files(
                user_id=user_id,
                generation_id=generation_id,
                limit=100
            )
            
            cleanup_count = 0
            
            for file_metadata in generation_files:
                try:
                    # Delete from storage
                    success = await self.storage_repo.delete_file(
                        bucket_name=file_metadata.bucket_name,
                        file_path=file_metadata.file_path,
                        user_id=user_id
                    )
                    
                    if success:
                        # Delete metadata
                        await self.storage_repo.delete_file_metadata(file_metadata.id, user_id)
                        cleanup_count += 1
                        logger.info(f"✅ [STORAGE-CLEANUP] Cleaned up file: {file_metadata.file_path}")
                    
                except Exception as e:
                    logger.warning(f"⚠️ [STORAGE-CLEANUP] Failed to delete file {file_metadata.id}: {e}")
                    continue
            
            logger.info(f"🎉 [STORAGE-CLEANUP] Cleanup completed: {cleanup_count} files removed for generation {generation_id}")
            return cleanup_count
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-CLEANUP] Failed to cleanup generation files for {generation_id}: {e}")
            return 0
    
    async def get_generation_storage_info(
        self,
        generation_id: Union[UUID, str],
        user_id: Union[UUID, str]
    ) -> Dict[str, Any]:
        """
        Get comprehensive storage information for a generation.
        
        Args:
            generation_id: Generation ID
            user_id: User ID for ownership verification
            
        Returns:
            Storage information including file count, total size, URLs
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(generation_id, str):
            generation_id = UUID(generation_id)
            
        logger.info(f"📊 [STORAGE-INFO] Getting storage info for generation {generation_id}")
        
        try:
            await self._get_repositories()
            
            # Get all files for this generation
            generation_files = await self.storage_repo.list_user_files(
                user_id=user_id,
                generation_id=generation_id,
                limit=100
            )
            
            # Calculate metrics
            total_size = sum(file_meta.file_size for file_meta in generation_files)
            file_count = len(generation_files)
            
            # Categorize files
            main_files = [f for f in generation_files if not f.is_thumbnail]
            thumbnail_files = [f for f in generation_files if f.is_thumbnail]
            
            # Generate signed URLs for main files
            signed_urls = []
            for file_meta in main_files[:10]:  # Limit to 10 URLs
                try:
                    signed_url_response = await self.get_signed_url(
                        file_id=file_meta.id,
                        user_id=user_id,
                        expires_in=3600  # 1 hour
                    )
                    signed_urls.append({
                        'file_id': str(file_meta.id),
                        'signed_url': signed_url_response.signed_url,
                        'file_path': file_meta.file_path,
                        'content_type': file_meta.content_type.value if hasattr(file_meta.content_type, 'value') else str(file_meta.content_type),
                        'file_size': file_meta.file_size
                    })
                except Exception as e:
                    logger.warning(f"⚠️ [STORAGE-INFO] Failed to generate signed URL for file {file_meta.id}: {e}")
            
            storage_info = {
                'generation_id': str(generation_id),
                'total_files': file_count,
                'main_files': len(main_files),
                'thumbnail_files': len(thumbnail_files),
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2),
                'signed_urls': signed_urls,
                'storage_paths': [f.file_path for f in main_files],
                'buckets_used': list(set(f.bucket_name.value if hasattr(f.bucket_name, 'value') else str(f.bucket_name) for f in generation_files)),
                'has_thumbnails': len(thumbnail_files) > 0,
                'is_fully_processed': all(f.is_processed for f in generation_files)
            }
            
            logger.info(f"✅ [STORAGE-INFO] Retrieved storage info: {file_count} files, {total_size} bytes")
            return storage_info
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-INFO] Failed to get storage info for generation {generation_id}: {e}")
            raise
    
    async def migrate_external_urls_to_storage(
        self,
        user_id: Union[UUID, str],
        generation_id: Union[UUID, str],
        external_urls: List[str]
    ) -> List[FileMetadataResponse]:
        """
        Migrate external URLs (like FAL.ai URLs) to Supabase storage.
        This is used for retroactive migration of existing generations.
        
        Args:
            user_id: User ID
            generation_id: Generation ID
            external_urls: List of external URLs to migrate
            
        Returns:
            List of migrated file metadata
        """
        logger.info(f"🔄 [STORAGE-MIGRATE] Starting migration of {len(external_urls)} external URLs to storage")
        logger.info(f"🔍 [STORAGE-MIGRATE] Generation: {generation_id}, User: {user_id}")
        
        try:
            # Use the existing upload_generation_result method with progress tracking
            migrated_files = await self.upload_generation_result(
                user_id=user_id,
                generation_id=generation_id,
                file_urls=external_urls,
                file_type="image"  # Default to image, will be detected automatically
            )
            
            logger.info(f"✅ [STORAGE-MIGRATE] Successfully migrated {len(migrated_files)} files to storage")
            return migrated_files
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-MIGRATE] Failed to migrate external URLs: {e}")
            raise
    
    async def validate_generation_storage_integrity(
        self,
        generation_id: Union[UUID, str],
        user_id: Union[UUID, str]
    ) -> Dict[str, Any]:
        """
        Validate the integrity of storage files for a generation.
        
        Args:
            generation_id: Generation ID to validate
            user_id: User ID for ownership verification
            
        Returns:
            Validation report with integrity status
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(generation_id, str):
            generation_id = UUID(generation_id)
            
        logger.info(f"🔍 [STORAGE-VALIDATE] Starting integrity validation for generation {generation_id}")
        
        await self._get_repositories()
        
        validation_report = {
            'generation_id': str(generation_id),
            'validation_timestamp': datetime.utcnow().isoformat(),
            'files_validated': 0,
            'files_valid': 0,
            'files_invalid': 0,
            'missing_files': 0,
            'total_size_bytes': 0,
            'integrity_issues': [],
            'overall_status': 'unknown'
        }
        
        try:
            # Get all files for this generation
            generation_files = await self.storage_repo.list_user_files(
                user_id=user_id,
                generation_id=generation_id,
                limit=100
            )
            
            validation_report['files_validated'] = len(generation_files)
            
            for file_metadata in generation_files:
                try:
                    # Check if file exists in storage
                    file_exists = await self.storage_repo.file_exists(
                        bucket_name=file_metadata.bucket_name,
                        file_path=file_metadata.file_path
                    )
                    
                    if not file_exists:
                        validation_report['missing_files'] += 1
                        validation_report['integrity_issues'].append({
                            'file_id': str(file_metadata.id),
                            'issue': 'file_missing',
                            'file_path': file_metadata.file_path
                        })
                        continue
                    
                    # Validate file integrity using hash if available
                    if file_metadata.file_hash:
                        is_valid = await self.verify_file_integrity(file_metadata.id, user_id)
                        if is_valid:
                            validation_report['files_valid'] += 1
                            validation_report['total_size_bytes'] += file_metadata.file_size
                        else:
                            validation_report['files_invalid'] += 1
                            validation_report['integrity_issues'].append({
                                'file_id': str(file_metadata.id),
                                'issue': 'hash_mismatch',
                                'file_path': file_metadata.file_path
                            })
                    else:
                        # No hash available, assume valid if file exists
                        validation_report['files_valid'] += 1
                        validation_report['total_size_bytes'] += file_metadata.file_size
                    
                except Exception as e:
                    validation_report['files_invalid'] += 1
                    validation_report['integrity_issues'].append({
                        'file_id': str(file_metadata.id),
                        'issue': f'validation_error: {str(e)}',
                        'file_path': file_metadata.file_path
                    })
            
            # Determine overall status
            if validation_report['files_invalid'] == 0 and validation_report['missing_files'] == 0:
                validation_report['overall_status'] = 'valid'
            elif validation_report['files_valid'] > 0:
                validation_report['overall_status'] = 'partial'
            else:
                validation_report['overall_status'] = 'invalid'
            
            logger.info(f"✅ [STORAGE-VALIDATE] Validation completed: {validation_report['overall_status']}")
            logger.info(f"🔍 [STORAGE-VALIDATE] Valid: {validation_report['files_valid']}, Invalid: {validation_report['files_invalid']}, Missing: {validation_report['missing_files']}")
            
            return validation_report
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-VALIDATE] Validation failed for generation {generation_id}: {e}")
            validation_report['overall_status'] = 'error'
            validation_report['integrity_issues'].append({
                'issue': f'validation_error: {str(e)}'
            })
            return validation_report


# Global service instance
storage_service = StorageService()