"""
Storage repository for Supabase Storage operations.
Following CLAUDE.md: Pure repository layer, no business logic.
Following PRD.MD: Secure, efficient file operations with user isolation.
"""
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID, uuid4
from datetime import datetime, timedelta
import logging
import hashlib
import io
from pathlib import Path

from database import SupabaseClient
from models.storage import (
    FileMetadataCreate, 
    FileMetadataResponse, 
    FileMetadataUpdate,
    StorageBucket,
    StorageUrlRequest,
    StorageUrlResponse,
    StorageStatsResponse,
    BulkDeleteRequest,
    MediaFileInfo,
    ProcessingResult
)

logger = logging.getLogger(__name__)


class StorageRepository:
    """Repository for Supabase Storage and file metadata operations."""
    
    def __init__(self, db_client: SupabaseClient):
        self.db = db_client
        self.storage = db_client.storage
    
    # === File Metadata Operations ===
    
    async def create_file_metadata(self, metadata: FileMetadataCreate, user_id: UUID) -> FileMetadataResponse:
        """Create file metadata record in database."""
        try:
            metadata_dict = metadata.dict()
            metadata_dict.update({
                "id": str(uuid4()),
                "user_id": str(user_id),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            })
            
            result = self.db.execute_query(
                "file_metadata",
                "insert",
                data=metadata_dict,
                single=True
            )
            
            return FileMetadataResponse(**result)
            
        except Exception as e:
            logger.error(f"Failed to create file metadata: {e}")
            raise
    
    async def get_file_metadata(self, file_id: UUID, user_id: UUID) -> Optional[FileMetadataResponse]:
        """Get file metadata by ID with user isolation."""
        try:
            result = self.db.execute_query(
                "file_metadata",
                "select",
                filters={"id": str(file_id), "user_id": str(user_id)},
                single=True
            )
            
            if result:
                return FileMetadataResponse(**result)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get file metadata {file_id}: {e}")
            raise
    
    async def get_file_metadata_by_path(
        self, 
        bucket_name: StorageBucket, 
        file_path: str, 
        user_id: UUID
    ) -> Optional[FileMetadataResponse]:
        """Get file metadata by bucket and path."""
        try:
            result = self.db.execute_query(
                "file_metadata",
                "select",
                filters={
                    "bucket_name": bucket_name.value,
                    "file_path": file_path,
                    "user_id": str(user_id)
                },
                single=True
            )
            
            if result:
                return FileMetadataResponse(**result)
            return None
            
        except Exception as e:
            logger.error(f"Failed to get file metadata by path {bucket_name}/{file_path}: {e}")
            raise
    
    async def update_file_metadata(
        self, 
        file_id: UUID, 
        updates: FileMetadataUpdate, 
        user_id: UUID
    ) -> FileMetadataResponse:
        """Update file metadata with user isolation."""
        try:
            update_dict = updates.dict(exclude_unset=True)
            update_dict["updated_at"] = datetime.utcnow().isoformat()
            
            result = self.db.execute_query(
                "file_metadata",
                "update",
                data=update_dict,
                filters={"id": str(file_id), "user_id": str(user_id)},
                single=True
            )
            
            if result:
                return FileMetadataResponse(**result)
            raise ValueError(f"File metadata {file_id} not found or access denied")
            
        except Exception as e:
            logger.error(f"Failed to update file metadata {file_id}: {e}")
            raise
    
    async def delete_file_metadata(self, file_id: UUID, user_id: UUID) -> bool:
        """Delete file metadata with user isolation."""
        try:
            result = self.db.execute_query(
                "file_metadata",
                "delete",
                filters={"id": str(file_id), "user_id": str(user_id)}
            )
            
            return len(result) > 0
            
        except Exception as e:
            logger.error(f"Failed to delete file metadata {file_id}: {e}")
            raise
    
    async def list_user_files(
        self, 
        user_id: UUID, 
        bucket_name: Optional[StorageBucket] = None,
        generation_id: Optional[UUID] = None,
        limit: int = 50, 
        offset: int = 0
    ) -> List[FileMetadataResponse]:
        """List user's files with optional filtering."""
        try:
            filters = {"user_id": str(user_id)}
            
            if bucket_name:
                filters["bucket_name"] = bucket_name.value
            
            if generation_id:
                filters["generation_id"] = str(generation_id)
            
            results = self.db.execute_query(
                "file_metadata",
                "select",
                filters=filters,
                order_by="created_at:desc",
                limit=limit,
                offset=offset
            )
            
            return [FileMetadataResponse(**result) for result in results]
            
        except Exception as e:
            logger.error(f"Failed to list files for user {user_id}: {e}")
            raise
    
    async def find_duplicate_files(self, user_id: UUID) -> List[Dict[str, Any]]:
        """Find duplicate files by hash for user."""
        try:
            result = await self.db.execute_rpc(
                "find_duplicate_files",
                {"target_user_id": str(user_id)}
            )
            
            return result or []
            
        except Exception as e:
            logger.error(f"Failed to find duplicate files for user {user_id}: {e}")
            raise
    
    # === Storage Operations ===
    
    async def upload_file(
        self, 
        bucket_name: StorageBucket, 
        file_path: str, 
        file_data: bytes,
        content_type: str,
        user_id: UUID
    ) -> str:
        """Upload file to Supabase Storage."""
        try:
            # Ensure file path starts with user ID for RLS
            user_id_str = str(user_id)
            if not file_path.startswith(f"{user_id_str}/"):
                file_path = f"{user_id_str}/{file_path}"
            
            # Upload to storage
            result = self.storage.from_(bucket_name.value).upload(
                path=file_path,
                file=file_data,
                file_options={
                    "content-type": content_type,
                    "cache-control": "3600",  # 1 hour cache
                    "upsert": False  # Prevent overwriting
                }
            )
            
            if result.get("error"):
                raise Exception(f"Storage upload error: {result['error']}")
            
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to upload file {file_path} to {bucket_name}: {e}")
            raise
    
    async def download_file(
        self, 
        bucket_name: StorageBucket, 
        file_path: str,
        user_id: UUID
    ) -> bytes:
        """Download file from Supabase Storage."""
        try:
            # Ensure user can only access their own files
            user_id_str = str(user_id)
            if not file_path.startswith(f"{user_id_str}/"):
                raise PermissionError("Access denied: file does not belong to user")
            
            result = self.storage.from_(bucket_name.value).download(file_path)
            
            if isinstance(result, dict) and result.get("error"):
                raise Exception(f"Storage download error: {result['error']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to download file {file_path} from {bucket_name}: {e}")
            raise
    
    async def delete_file(
        self, 
        bucket_name: StorageBucket, 
        file_path: str,
        user_id: UUID
    ) -> bool:
        """Delete file from Supabase Storage."""
        try:
            # Ensure user can only delete their own files
            user_id_str = str(user_id)
            if not file_path.startswith(f"{user_id_str}/"):
                raise PermissionError("Access denied: file does not belong to user")
            
            result = self.storage.from_(bucket_name.value).remove([file_path])
            
            if isinstance(result, dict) and result.get("error"):
                raise Exception(f"Storage delete error: {result['error']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete file {file_path} from {bucket_name}: {e}")
            raise
    
    async def create_signed_url(
        self, 
        bucket_name: StorageBucket, 
        file_path: str,
        expires_in: int,
        user_id: UUID
    ) -> StorageUrlResponse:
        """Create signed URL for file access."""
        logger.info(f"🔗 [STORAGE-URL] Creating signed URL for file access")
        logger.info(f"🔍 [STORAGE-URL] Bucket: {bucket_name.value}, File: {file_path}, User: {user_id}, Expires: {expires_in}s")
        
        try:
            # Ensure user can only access their own files
            user_id_str = str(user_id)
            logger.info(f"🔐 [STORAGE-URL] Checking file path ownership for user {user_id_str}")
            
            if not file_path.startswith(f"{user_id_str}/"):
                logger.error(f"❌ [STORAGE-URL] Access denied: file path '{file_path}' does not belong to user {user_id_str}")
                raise PermissionError("Access denied: file does not belong to user")
            
            logger.info(f"✅ [STORAGE-URL] File ownership verified, creating Supabase signed URL...")
            
            result = self.storage.from_(bucket_name.value).create_signed_url(
                path=file_path,
                expires_in=expires_in
            )
            
            logger.info(f"🔍 [STORAGE-URL] Supabase signed URL result type: {type(result)}")
            logger.info(f"🔍 [STORAGE-URL] Supabase result keys: {list(result.keys()) if isinstance(result, dict) else 'Non-dict result'}")
            
            if isinstance(result, dict) and result.get("error"):
                logger.error(f"❌ [STORAGE-URL] Supabase signed URL error: {result['error']}")
                raise Exception(f"Signed URL error: {result['error']}")
            
            signed_url = result["signedURL"]
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            logger.info(f"✅ [STORAGE-URL] Signed URL created successfully")
            logger.info(f"🔗 [STORAGE-URL] URL: {signed_url[:100]}{'...' if len(signed_url) > 100 else ''}")
            logger.info(f"🕰️ [STORAGE-URL] Expires at: {expires_at}")
            
            return StorageUrlResponse(
                signed_url=signed_url,
                expires_at=expires_at,
                file_path=file_path,
                bucket_name=bucket_name
            )
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-URL] Failed to create signed URL for {file_path}: {e}")
            logger.error(f"❌ [STORAGE-URL] URL creation error type: {type(e).__name__}")
            import traceback
            logger.error(f"❌ [STORAGE-URL] URL creation traceback: {traceback.format_exc()}")
            raise
    
    async def create_upload_url(
        self, 
        bucket_name: StorageBucket, 
        file_path: str,
        user_id: UUID
    ) -> str:
        """Create signed upload URL for direct client uploads."""
        try:
            # Ensure file path starts with user ID
            user_id_str = str(user_id)
            if not file_path.startswith(f"{user_id_str}/"):
                file_path = f"{user_id_str}/{file_path}"
            
            result = self.storage.from_(bucket_name.value).create_signed_upload_url(file_path)
            
            if isinstance(result, dict) and result.get("error"):
                raise Exception(f"Upload URL error: {result['error']}")
            
            return result["signedURL"]
            
        except Exception as e:
            logger.error(f"Failed to create upload URL for {file_path}: {e}")
            raise
    
    async def copy_file(
        self, 
        source_bucket: StorageBucket,
        source_path: str,
        dest_bucket: StorageBucket,
        dest_path: str,
        user_id: UUID
    ) -> bool:
        """Copy file between buckets/paths."""
        try:
            # Ensure user can only access their own files
            user_id_str = str(user_id)
            if not source_path.startswith(f"{user_id_str}/") or not dest_path.startswith(f"{user_id_str}/"):
                raise PermissionError("Access denied: files must belong to user")
            
            result = self.storage.from_(source_bucket.value).copy(
                from_path=source_path,
                to_path=dest_path,
                destination_bucket=dest_bucket.value
            )
            
            if isinstance(result, dict) and result.get("error"):
                raise Exception(f"Copy error: {result['error']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy file from {source_bucket}/{source_path} to {dest_bucket}/{dest_path}: {e}")
            raise
    
    async def move_file(
        self, 
        bucket_name: StorageBucket,
        source_path: str,
        dest_path: str,
        user_id: UUID
    ) -> bool:
        """Move file within bucket."""
        try:
            # Ensure user can only access their own files
            user_id_str = str(user_id)
            if not source_path.startswith(f"{user_id_str}/") or not dest_path.startswith(f"{user_id_str}/"):
                raise PermissionError("Access denied: files must belong to user")
            
            result = self.storage.from_(bucket_name.value).move(
                from_path=source_path,
                to_path=dest_path
            )
            
            if isinstance(result, dict) and result.get("error"):
                raise Exception(f"Move error: {result['error']}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to move file from {source_path} to {dest_path}: {e}")
            raise
    
    # === Bulk Operations ===
    
    async def bulk_delete_files(
        self, 
        bucket_name: StorageBucket, 
        file_paths: List[str],
        user_id: UUID,
        force: bool = False
    ) -> ProcessingResult:
        """Delete multiple files at once."""
        try:
            processed_files = []
            failed_files = []
            total_size = 0
            start_time = datetime.utcnow()
            
            # Validate all paths belong to user
            user_id_str = str(user_id)
            for path in file_paths:
                if not path.startswith(f"{user_id_str}/"):
                    failed_files.append(f"{path}: Access denied")
                    continue
                
                try:
                    # Get file metadata for size tracking
                    metadata = await self.get_file_metadata_by_path(bucket_name, path, user_id)
                    if metadata:
                        total_size += metadata.file_size
                    
                    # Delete from storage
                    success = await self.delete_file(bucket_name, path, user_id)
                    if success:
                        # Delete metadata
                        if metadata:
                            await self.delete_file_metadata(metadata.id, user_id)
                        
                        processed_files.append(MediaFileInfo(
                            bucket=bucket_name,
                            path=path,
                            size=metadata.file_size if metadata else 0,
                            content_type=metadata.content_type if metadata else "unknown"
                        ))
                    else:
                        failed_files.append(f"{path}: Delete failed")
                        
                except Exception as e:
                    failed_files.append(f"{path}: {str(e)}")
            
            processing_time = (datetime.utcnow() - start_time).total_seconds()
            
            return ProcessingResult(
                success=len(failed_files) == 0,
                processed_files=processed_files,
                failed_files=failed_files,
                total_size=total_size,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Failed to bulk delete files: {e}")
            raise
    
    # === Statistics and Cleanup ===
    
    async def get_user_storage_stats(self, user_id: UUID) -> StorageStatsResponse:
        """Get user's storage usage statistics."""
        try:
            # Get stats from database function
            stats_result = await self.db.execute_rpc(
                "get_user_storage_stats",
                {"target_user_id": str(user_id)}
            )
            
            total_files = 0
            total_size = 0
            buckets = {}
            
            for stat in stats_result or []:
                bucket_name = stat["bucket_name"]
                file_count = stat["file_count"]
                bucket_size = stat["total_size"]
                avg_size = stat["avg_file_size"]
                
                total_files += file_count
                total_size += bucket_size
                
                buckets[bucket_name] = {
                    "file_count": file_count,
                    "total_size": bucket_size,
                    "average_file_size": float(avg_size) if avg_size else 0,
                    "formatted_size": self._format_file_size(bucket_size)
                }
            
            return StorageStatsResponse(
                user_id=user_id,
                total_files=total_files,
                total_size=total_size,
                total_size_formatted=self._format_file_size(total_size),
                buckets=buckets
            )
            
        except Exception as e:
            logger.error(f"Failed to get storage stats for user {user_id}: {e}")
            raise
    
    async def cleanup_expired_temp_files(self) -> int:
        """Clean up expired temporary files."""
        try:
            result = await self.db.execute_rpc("cleanup_expired_temp_files", {})
            return result if isinstance(result, int) else 0
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired temp files: {e}")
            raise
    
    async def verify_file_integrity(
        self, 
        bucket_name: StorageBucket, 
        file_path: str,
        expected_hash: str,
        user_id: UUID
    ) -> bool:
        """Verify file integrity using hash comparison."""
        try:
            # Download file
            file_data = await self.download_file(bucket_name, file_path, user_id)
            
            # Calculate hash
            actual_hash = hashlib.sha256(file_data).hexdigest()
            
            return actual_hash.lower() == expected_hash.lower()
            
        except Exception as e:
            logger.error(f"Failed to verify file integrity for {file_path}: {e}")
            return False
    
    # === Helper Methods ===
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def _generate_file_path(
        self, 
        user_id: UUID, 
        filename: str, 
        folder: Optional[str] = None
    ) -> str:
        """Generate a secure file path with user isolation."""
        # Create safe filename
        safe_filename = Path(filename).name  # Remove any path components
        
        # Build path: user_id/folder/filename or user_id/filename
        if folder:
            return f"{user_id}/{folder}/{safe_filename}"
        return f"{user_id}/{safe_filename}"
    
    def _calculate_file_hash(self, file_data: bytes) -> str:
        """Calculate SHA-256 hash of file data."""
        return hashlib.sha256(file_data).hexdigest()
    
    async def file_exists(
        self, 
        bucket_name: StorageBucket, 
        file_path: str
    ) -> bool:
        """
        Check if file exists in Supabase Storage.
        
        Args:
            bucket_name: Storage bucket
            file_path: Path to the file
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            # Use storage client to check if file exists
            result = self.storage.from_(bucket_name.value).list(
                path=file_path,
                limit=1
            )
            
            # If result is an error, file doesn't exist
            if isinstance(result, dict) and result.get("error"):
                return False
            
            # If result is a list and contains the file, it exists
            if isinstance(result, list):
                for item in result:
                    if item.get("name") == Path(file_path).name:
                        return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ [STORAGE-EXISTS] Error checking if file exists {bucket_name}/{file_path}: {e}")
            return False