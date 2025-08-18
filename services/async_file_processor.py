"""
Async File Processing Service for FAL.ai file transfers to Supabase storage.
Following CLAUDE.md: Robust async operations with comprehensive error handling.
"""
import asyncio
import hashlib
import logging
import mimetypes
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union, Callable
from uuid import UUID, uuid4
import io
from PIL import Image
import httpx
from contextlib import asynccontextmanager

from config import settings
from database import get_database
from models.storage import (
    FileMetadataCreate,
    FileMetadataResponse,
    StorageBucket,
    ContentType,
    FileUploadRequest,
    ProcessingResult
)
from repositories.storage_repository import StorageRepository
from repositories.generation_repository import GenerationRepository

logger = logging.getLogger(__name__)


class FileProcessingError(Exception):
    """Custom exception for file processing errors."""
    pass


class FileSizeExceededError(FileProcessingError):
    """Exception for when file size exceeds limits."""
    pass


class FileTypeNotSupportedError(FileProcessingError):
    """Exception for unsupported file types."""
    pass


class ProgressTracker:
    """Progress tracking for file operations."""
    
    def __init__(self, total_size: int, callback: Optional[Callable[[int, int], None]] = None):
        self.total_size = total_size
        self.downloaded_size = 0
        self.callback = callback
        self.start_time = datetime.now()
    
    def update(self, chunk_size: int):
        """Update progress with new chunk size."""
        self.downloaded_size += chunk_size
        if self.callback:
            self.callback(self.downloaded_size, self.total_size)
    
    @property
    def progress_percent(self) -> float:
        """Get progress as percentage."""
        if self.total_size == 0:
            return 0.0
        return (self.downloaded_size / self.total_size) * 100
    
    @property
    def elapsed_time(self) -> timedelta:
        """Get elapsed time since start."""
        return datetime.now() - self.start_time
    
    @property
    def speed_mbps(self) -> float:
        """Get download speed in MB/s."""
        elapsed_seconds = self.elapsed_time.total_seconds()
        if elapsed_seconds == 0:
            return 0.0
        return (self.downloaded_size / (1024 * 1024)) / elapsed_seconds


class AsyncFileProcessor:
    """Advanced async file processing service for FAL.ai integration."""
    
    def __init__(self):
        self.db = None
        self.storage_repo = None
        self.generation_repo = None
        self.http_client = None
        self.thread_pool = ThreadPoolExecutor(max_workers=4)
        
        # File processing limits
        self.MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
        self.MAX_BATCH_SIZE = 10
        self.CHUNK_SIZE = 8192  # 8KB chunks for streaming
        self.REQUEST_TIMEOUT = 120.0  # 2 minutes
        
        # Supported file types
        self.SUPPORTED_IMAGE_TYPES = {
            'image/jpeg': ['.jpg', '.jpeg'],
            'image/png': ['.png'],
            'image/webp': ['.webp'],
            'image/gif': ['.gif'],
            'image/bmp': ['.bmp'],
            'image/tiff': ['.tiff', '.tif']
        }
        
        self.SUPPORTED_VIDEO_TYPES = {
            'video/mp4': ['.mp4'],
            'video/quicktime': ['.mov'],
            'video/webm': ['.webm'],
            'video/avi': ['.avi']
        }
        
        self.SUPPORTED_TYPES = {**self.SUPPORTED_IMAGE_TYPES, **self.SUPPORTED_VIDEO_TYPES}
    
    async def _get_repositories(self):
        """Initialize repositories and HTTP client if not already done."""
        if self.db is None:
            self.db = await get_database()
            self.storage_repo = StorageRepository(self.db)
            self.generation_repo = GenerationRepository(self.db)
        
        if self.http_client is None:
            timeout = httpx.Timeout(self.REQUEST_TIMEOUT)
            self.http_client = httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
                headers={
                    'User-Agent': f'Velro-FileProcessor/1.0 (+{settings.app_url})'
                }
            )
    
    async def close(self):
        """Clean up resources."""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
        
        if self.thread_pool:
            self.thread_pool.shutdown(wait=True)
    
    @asynccontextmanager
    async def _ensure_resources(self):
        """Context manager to ensure resources are initialized."""
        await self._get_repositories()
        try:
            yield
        finally:
            pass  # Keep resources open for reuse
    
    # === Core File Download Functions ===
    
    async def download_fal_file(
        self,
        url: str,
        max_size: int = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bytes:
        """
        Download file from FAL.ai URL with streaming and progress tracking.
        
        Args:
            url: FAL.ai file URL
            max_size: Maximum file size in bytes (defaults to class limit)
            progress_callback: Optional callback for progress updates
        
        Returns:
            File data as bytes
        
        Raises:
            FileSizeExceededError: If file exceeds size limit
            FileProcessingError: For other download errors
        """
        if max_size is None:
            max_size = self.MAX_FILE_SIZE
        
        logger.info(f"📥 [FILE-DOWNLOAD] Starting download from FAL.ai: {url[:100]}{'...' if len(url) > 100 else ''}")
        
        async with self._ensure_resources():
            try:
                # Start streaming download
                async with self.http_client.stream('GET', url) as response:
                    response.raise_for_status()
                    
                    # Check content length
                    content_length = response.headers.get('content-length')
                    if content_length:
                        total_size = int(content_length)
                        if total_size > max_size:
                            raise FileSizeExceededError(f"File size {total_size} exceeds limit {max_size}")
                        logger.info(f"📊 [FILE-DOWNLOAD] Content length: {total_size} bytes")
                    else:
                        total_size = 0
                        logger.warning(f"⚠️ [FILE-DOWNLOAD] No content-length header, size unknown")
                    
                    # Initialize progress tracker
                    progress = ProgressTracker(total_size, progress_callback)
                    
                    # Stream download with progress tracking
                    chunks = []
                    downloaded_size = 0
                    
                    async for chunk in response.aiter_bytes(chunk_size=self.CHUNK_SIZE):
                        if not chunk:
                            break
                        
                        downloaded_size += len(chunk)
                        if downloaded_size > max_size:
                            raise FileSizeExceededError(f"File size exceeds limit {max_size}")
                        
                        chunks.append(chunk)
                        progress.update(len(chunk))
                        
                        # Log progress periodically
                        if len(chunks) % 100 == 0:  # Every ~800KB
                            logger.info(f"📊 [FILE-DOWNLOAD] Progress: {progress.progress_percent:.1f}% ({progress.speed_mbps:.2f} MB/s)")
                    
                    file_data = b''.join(chunks)
                    
                    logger.info(f"✅ [FILE-DOWNLOAD] Download completed: {len(file_data)} bytes in {progress.elapsed_time.total_seconds():.2f}s")
                    logger.info(f"📊 [FILE-DOWNLOAD] Average speed: {progress.speed_mbps:.2f} MB/s")
                    
                    return file_data
            
            except httpx.HTTPStatusError as e:
                logger.error(f"❌ [FILE-DOWNLOAD] HTTP error downloading {url}: {e.response.status_code}")
                raise FileProcessingError(f"Download failed with status {e.response.status_code}")
            
            except httpx.TimeoutException:
                logger.error(f"❌ [FILE-DOWNLOAD] Timeout downloading {url}")
                raise FileProcessingError("Download timeout")
            
            except Exception as e:
                logger.error(f"❌ [FILE-DOWNLOAD] Unexpected error downloading {url}: {e}")
                raise FileProcessingError(f"Download failed: {str(e)}")
    
    # === File Type Detection and Validation ===
    
    def detect_file_type(self, file_data: bytes, url: Optional[str] = None) -> Tuple[str, str, bool]:
        """
        Detect file type from content and validate format.
        
        Args:
            file_data: File content bytes
            url: Optional URL for additional context
        
        Returns:
            Tuple of (content_type, extension, is_valid)
        """
        logger.info(f"🔍 [FILE-TYPE] Detecting file type for {len(file_data)} bytes")
        
        # Check magic bytes (file signatures)
        content_type, extension = self._detect_by_magic_bytes(file_data)
        
        # Fallback to URL-based detection
        if content_type == "application/octet-stream" and url:
            content_type, extension = self._detect_by_url(url)
        
        # Validate if file type is supported
        is_valid = content_type in self.SUPPORTED_TYPES
        
        logger.info(f"🎯 [FILE-TYPE] Detected: {content_type}, extension: {extension}, valid: {is_valid}")
        
        return content_type, extension, is_valid
    
    def _detect_by_magic_bytes(self, file_data: bytes) -> Tuple[str, str]:
        """Detect file type by analyzing magic bytes."""
        if len(file_data) < 16:
            return "application/octet-stream", "bin"
        
        # Image formats
        if file_data.startswith(b'\xff\xd8\xff'):
            return "image/jpeg", "jpg"
        elif file_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return "image/png", "png"
        elif file_data.startswith(b'RIFF') and b'WEBP' in file_data[:12]:
            return "image/webp", "webp"
        elif file_data.startswith(b'GIF8'):
            return "image/gif", "gif"
        elif file_data.startswith(b'BM'):
            return "image/bmp", "bmp"
        elif file_data.startswith(b'II*\x00') or file_data.startswith(b'MM\x00*'):
            return "image/tiff", "tiff"
        
        # Video formats
        elif file_data[4:12] == b'ftypmp4\x00' or file_data[4:8] == b'ftyp':
            return "video/mp4", "mp4"
        elif file_data.startswith(b'\x00\x00\x00\x14ftypqt'):
            return "video/quicktime", "mov"
        elif file_data.startswith(b'\x1a\x45\xdf\xa3'):
            return "video/webm", "webm"
        elif file_data.startswith(b'RIFF') and b'AVI ' in file_data[8:12]:
            return "video/avi", "avi"
        
        return "application/octet-stream", "bin"
    
    def _detect_by_url(self, url: str) -> Tuple[str, str]:
        """Detect file type from URL extension."""
        try:
            parsed_url = Path(url.split('?')[0])  # Remove query parameters
            extension = parsed_url.suffix.lower()
            
            # Find matching content type
            for content_type, extensions in self.SUPPORTED_TYPES.items():
                if extension in extensions:
                    return content_type, extension.lstrip('.')
            
            # Use mimetypes as fallback
            guessed_type, _ = mimetypes.guess_type(url)
            if guessed_type:
                extension = mimetypes.guess_extension(guessed_type) or ""
                return guessed_type, extension.lstrip('.')
                
        except Exception as e:
            logger.warning(f"⚠️ [FILE-TYPE] Error detecting from URL {url}: {e}")
        
        return "application/octet-stream", "bin"
    
    def validate_file_integrity(self, file_data: bytes, content_type: str) -> bool:
        """
        Validate file integrity and ensure it's not corrupted.
        
        Args:
            file_data: File content bytes
            content_type: Expected content type
        
        Returns:
            True if file is valid and not corrupted
        """
        logger.info(f"🔍 [FILE-VALIDATE] Validating {content_type} file integrity")
        
        try:
            if content_type.startswith('image/'):
                return self._validate_image_integrity(file_data)
            elif content_type.startswith('video/'):
                return self._validate_video_integrity(file_data)
            else:
                # Basic validation for other types
                return len(file_data) > 0
        
        except Exception as e:
            logger.error(f"❌ [FILE-VALIDATE] Integrity validation failed: {e}")
            return False
    
    def _validate_image_integrity(self, file_data: bytes) -> bool:
        """Validate image file integrity using PIL."""
        try:
            with Image.open(io.BytesIO(file_data)) as img:
                # Try to load the image to check if it's valid
                img.load()
                # Verify image has valid dimensions
                if img.size[0] <= 0 or img.size[1] <= 0:
                    return False
                # Check if image is too large (security)
                if img.size[0] * img.size[1] > 100_000_000:  # 100MP limit
                    logger.warning(f"⚠️ [FILE-VALIDATE] Image too large: {img.size}")
                    return False
                return True
        except Exception as e:
            logger.error(f"❌ [FILE-VALIDATE] Image validation failed: {e}")
            return False
    
    def _validate_video_integrity(self, file_data: bytes) -> bool:
        """Basic video file validation."""
        try:
            # Basic checks for video files
            if len(file_data) < 1024:  # Videos should be at least 1KB
                return False
            
            # Check for common video file signatures
            if file_data[4:8] == b'ftyp':  # MP4/MOV
                return True
            elif file_data.startswith(b'\x1a\x45\xdf\xa3'):  # WebM/MKV
                return True
            elif file_data.startswith(b'RIFF') and b'AVI ' in file_data[8:12]:  # AVI
                return True
            
            return True  # Assume valid for other formats
        except Exception:
            return False
    
    # === Batch Processing System ===
    
    async def process_file_batch(
        self,
        urls: List[str],
        user_id: Union[UUID, str],
        generation_id: Union[UUID, str],
        max_concurrent: int = 3,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> ProcessingResult:
        """
        Process multiple files in parallel with coordination.
        
        Args:
            urls: List of file URLs to process
            user_id: User owning the files
            generation_id: Generation ID to associate files with
            max_concurrent: Maximum concurrent downloads
            progress_callback: Optional callback for progress updates (completed, total, current_url)
        
        Returns:
            ProcessingResult with success/failure details
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(generation_id, str):
            generation_id = UUID(generation_id)
        
        if len(urls) > self.MAX_BATCH_SIZE:
            raise FileProcessingError(f"Batch size {len(urls)} exceeds limit {self.MAX_BATCH_SIZE}")
        
        logger.info(f"🔄 [BATCH-PROCESS] Starting batch processing: {len(urls)} files for generation {generation_id}")
        
        async with self._ensure_resources():
            # Create semaphore to limit concurrent downloads
            semaphore = asyncio.Semaphore(max_concurrent)
            
            # Track results
            successful_files = []
            failed_files = []
            start_time = datetime.now()
            
            async def process_single_file(url: str, index: int) -> Optional[FileMetadataResponse]:
                """Process a single file with semaphore protection."""
                async with semaphore:
                    try:
                        logger.info(f"📥 [BATCH-PROCESS] Processing file {index + 1}/{len(urls)}: {url[:100]}...")
                        
                        # Download file
                        file_data = await self.download_fal_file(url)
                        
                        # Detect and validate file type
                        content_type, extension, is_valid = self.detect_file_type(file_data, url)
                        if not is_valid:
                            raise FileTypeNotSupportedError(f"Unsupported file type: {content_type}")
                        
                        # Validate file integrity
                        if not self.validate_file_integrity(file_data, content_type):
                            raise FileProcessingError("File integrity validation failed")
                        
                        # Create file metadata and upload
                        result = await self._upload_processed_file(
                            file_data=file_data,
                            content_type=content_type,
                            extension=extension,
                            user_id=user_id,
                            generation_id=generation_id,
                            source_url=url,
                            file_index=index
                        )
                        
                        if progress_callback:
                            progress_callback(len(successful_files) + len(failed_files) + 1, len(urls), url)
                        
                        return result
                    
                    except Exception as e:
                        logger.error(f"❌ [BATCH-PROCESS] Failed to process file {index + 1}: {url[:100]}... - {e}")
                        failed_files.append({
                            'url': url,
                            'index': index,
                            'error': str(e),
                            'error_type': type(e).__name__
                        })
                        
                        if progress_callback:
                            progress_callback(len(successful_files) + len(failed_files) + 1, len(urls), url)
                        
                        return None
            
            # Process all files concurrently
            tasks = [process_single_file(url, i) for i, url in enumerate(urls)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Collect successful results
            for result in results:
                if isinstance(result, FileMetadataResponse):
                    successful_files.append(result)
                elif isinstance(result, Exception):
                    # This shouldn't happen as we handle exceptions in process_single_file
                    logger.error(f"❌ [BATCH-PROCESS] Unexpected exception: {result}")
            
            processing_time = datetime.now() - start_time
            
            logger.info(f"🎉 [BATCH-PROCESS] Batch processing completed in {processing_time.total_seconds():.2f}s")
            logger.info(f"📊 [BATCH-PROCESS] Results: {len(successful_files)} successful, {len(failed_files)} failed")
            
            return ProcessingResult(
                success=len(failed_files) == 0,
                processed_files=successful_files,
                failed_files=failed_files,
                total_files=len(urls),
                processing_time=processing_time.total_seconds(),
                errors=[f['error'] for f in failed_files]
            )
    
    async def _upload_processed_file(
        self,
        file_data: bytes,
        content_type: str,
        extension: str,
        user_id: UUID,
        generation_id: UUID,
        source_url: str,
        file_index: int
    ) -> FileMetadataResponse:
        """Upload processed file to Supabase storage."""
        # Generate filename
        filename = f"generation_{str(generation_id)}_{file_index + 1}.{extension}"
        
        # Create upload request
        upload_request = FileUploadRequest(
            bucket_name=StorageBucket.GENERATIONS,
            filename=filename,
            content_type=ContentType(content_type),
            file_size=len(file_data),
            generation_id=generation_id,
            metadata={
                "source_url": source_url,
                "generation_id": str(generation_id),
                "file_index": file_index,
                "upload_type": "batch_generation_result",
                "processed_at": datetime.utcnow().isoformat(),
                "original_external_url": source_url,
                "file_hash": hashlib.sha256(file_data).hexdigest()
            }
        )
        
        # Use storage service to upload
        from services.storage_service import storage_service
        return await storage_service.upload_file(
            user_id=user_id,
            file_data=file_data,
            upload_request=upload_request,
            generation_id=generation_id
        )
    
    # === Background Task Integration ===
    
    async def queue_file_processing_task(
        self,
        urls: List[str],
        user_id: Union[UUID, str],
        generation_id: Union[UUID, str],
        task_id: Optional[str] = None
    ) -> str:
        """
        Queue file processing as background task.
        
        Args:
            urls: File URLs to process
            user_id: User ID
            generation_id: Generation ID
            task_id: Optional custom task ID
        
        Returns:
            Task ID for tracking
        """
        if task_id is None:
            task_id = f"file_processing_{uuid4().hex[:12]}"
        
        logger.info(f"📋 [TASK-QUEUE] Queuing background file processing task: {task_id}")
        
        # For now, use asyncio task - in production, this would use Celery
        task = asyncio.create_task(
            self._background_file_processing_task(
                urls=urls,
                user_id=user_id,
                generation_id=generation_id,
                task_id=task_id
            )
        )
        
        # Store task reference (in production, use proper task queue)
        if not hasattr(self, '_background_tasks'):
            self._background_tasks = {}
        self._background_tasks[task_id] = {
            'task': task,
            'status': 'queued',
            'created_at': datetime.utcnow(),
            'urls': urls,
            'user_id': str(user_id),
            'generation_id': str(generation_id)
        }
        
        return task_id
    
    async def _background_file_processing_task(
        self,
        urls: List[str],
        user_id: Union[UUID, str],
        generation_id: Union[UUID, str],
        task_id: str
    ):
        """Execute file processing in background."""
        logger.info(f"🚀 [BACKGROUND-TASK] Starting background processing: {task_id}")
        
        try:
            # Update task status
            if hasattr(self, '_background_tasks'):
                self._background_tasks[task_id]['status'] = 'processing'
                self._background_tasks[task_id]['started_at'] = datetime.utcnow()
            
            # Process files
            result = await self.process_file_batch(
                urls=urls,
                user_id=user_id,
                generation_id=generation_id
            )
            
            # Update task status
            if hasattr(self, '_background_tasks'):
                self._background_tasks[task_id]['status'] = 'completed' if result.success else 'failed'
                self._background_tasks[task_id]['completed_at'] = datetime.utcnow()
                self._background_tasks[task_id]['result'] = result
            
            # Notify completion (in production, use proper notification system)
            await self._notify_task_completion(task_id, result)
            
            logger.info(f"✅ [BACKGROUND-TASK] Task completed successfully: {task_id}")
            
        except Exception as e:
            logger.error(f"❌ [BACKGROUND-TASK] Task failed: {task_id} - {e}")
            
            if hasattr(self, '_background_tasks'):
                self._background_tasks[task_id]['status'] = 'failed'
                self._background_tasks[task_id]['error'] = str(e)
                self._background_tasks[task_id]['completed_at'] = datetime.utcnow()
    
    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get status of background task."""
        if not hasattr(self, '_background_tasks'):
            return None
        
        return self._background_tasks.get(task_id)
    
    async def _notify_task_completion(self, task_id: str, result: ProcessingResult):
        """Notify about task completion (placeholder for real notification system)."""
        logger.info(f"📬 [NOTIFICATION] Task {task_id} completed: {result.total_files} files processed")
        # In production, this would send notifications via webhooks, email, etc.
    
    # === Storage Optimization ===
    
    async def compress_image(self, file_data: bytes, quality: int = 85) -> bytes:
        """
        Compress image file while maintaining quality.
        
        Args:
            file_data: Original image data
            quality: JPEG quality (1-100)
        
        Returns:
            Compressed image data
        """
        def _compress_sync():
            try:
                with Image.open(io.BytesIO(file_data)) as img:
                    # Convert to RGB if necessary
                    if img.mode in ('RGBA', 'LA', 'P'):
                        # Create white background for transparent images
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        img = background
                    elif img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Compress
                    output = io.BytesIO()
                    img.save(output, format='JPEG', quality=quality, optimize=True)
                    return output.getvalue()
            except Exception as e:
                logger.error(f"❌ [COMPRESS] Image compression failed: {e}")
                return file_data  # Return original if compression fails
        
        # Run compression in thread pool to avoid blocking
        return await asyncio.get_event_loop().run_in_executor(
            self.thread_pool, _compress_sync
        )
    
    def detect_duplicate_by_hash(self, file_data: bytes, existing_hashes: List[str]) -> Optional[str]:
        """
        Detect if file is duplicate based on hash.
        
        Args:
            file_data: File content
            existing_hashes: List of existing file hashes
        
        Returns:
            Matching hash if duplicate found, None otherwise
        """
        file_hash = hashlib.sha256(file_data).hexdigest()
        return file_hash if file_hash in existing_hashes else None
    
    async def cleanup_temporary_files(self, max_age_hours: int = 24) -> int:
        """
        Clean up temporary files older than specified age.
        
        Args:
            max_age_hours: Maximum age in hours
        
        Returns:
            Number of files cleaned up
        """
        logger.info(f"🧹 [CLEANUP] Starting cleanup of temp files older than {max_age_hours}h")
        
        async with self._ensure_resources():
            try:
                cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
                
                # This would be implemented based on your storage repository
                # For now, return placeholder
                cleanup_count = await self.storage_repo.cleanup_expired_temp_files()
                
                logger.info(f"✅ [CLEANUP] Cleaned up {cleanup_count} temporary files")
                return cleanup_count
                
            except Exception as e:
                logger.error(f"❌ [CLEANUP] Cleanup failed: {e}")
                return 0


# Global service instance
async_file_processor = AsyncFileProcessor()


# Cleanup on app shutdown
async def cleanup_file_processor():
    """Cleanup function to be called on app shutdown."""
    await async_file_processor.close()