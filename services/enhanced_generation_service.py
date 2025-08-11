"""
Enhanced Generation Service with Async File Processing Integration.
Following CLAUDE.md: Integration example for async file processing.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
from uuid import UUID
from datetime import datetime

from services.async_file_processor import async_file_processor, FileProcessingError
from services.background_tasks import task_manager
from services.fal_service import fal_service
from services.storage_service import storage_service
from repositories.generation_repository import GenerationRepository
from repositories.credit_repository import CreditRepository
from models.generation import GenerationStatus, GenerationResponse

logger = logging.getLogger(__name__)


class EnhancedGenerationService:
    """
    Enhanced generation service with integrated async file processing.
    
    This service demonstrates how to integrate the async file processing
    system with existing generation workflows.
    """
    
    def __init__(self):
        self.generation_repo = None
        self.credit_repo = None
    
    async def _get_repositories(self):
        """Initialize repositories if needed."""
        if self.generation_repo is None:
            from database import get_database
            db = await get_database()
            self.generation_repo = GenerationRepository(db)
            self.credit_repo = CreditRepository(db)
    
    async def create_generation_with_async_processing(
        self,
        user_id: Union[UUID, str],
        project_id: Union[UUID, str],
        model_id: str,
        prompt: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        use_background_processing: bool = True
    ) -> GenerationResponse:
        """
        Create generation with integrated async file processing.
        
        Args:
            user_id: User creating the generation
            project_id: Project to associate with
            model_id: AI model to use
            prompt: Generation prompt
            negative_prompt: Optional negative prompt
            reference_image_url: Optional reference image
            parameters: Model-specific parameters
            use_background_processing: Whether to use background tasks
        
        Returns:
            Generation response with processing status
        """
        if isinstance(user_id, str):
            user_id = UUID(user_id)
        if isinstance(project_id, str):
            project_id = UUID(project_id)
        
        logger.info(f"🎨 [ENHANCED-GEN] Creating generation with async processing for user {user_id}")
        
        await self._get_repositories()
        
        try:
            # 1. Create initial generation record
            generation_data = {
                "user_id": user_id,
                "project_id": project_id,
                "model_id": model_id,
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "reference_image_url": reference_image_url,
                "parameters": parameters or {},
                "status": GenerationStatus.PENDING,
                "created_at": datetime.utcnow()
            }
            
            generation = await self.generation_repo.create_generation(generation_data)
            generation_id = UUID(generation.id)
            
            logger.info(f"✅ [ENHANCED-GEN] Generation record created: {generation_id}")
            
            # 2. Check and deduct credits
            from models.fal_config import get_model_config
            model_config = get_model_config(model_id)
            credits_required = model_config.credits
            
            # This would integrate with your credit system
            await self._deduct_credits(user_id, credits_required)
            
            # 3. Start FAL.ai generation
            logger.info(f"🚀 [ENHANCED-GEN] Starting FAL.ai generation...")
            await self.generation_repo.update_generation(
                str(generation_id),
                {"status": GenerationStatus.PROCESSING}
            )
            
            fal_result = await fal_service.create_generation(
                model_id=model_id,
                prompt=prompt,
                negative_prompt=negative_prompt,
                reference_image_url=reference_image_url,
                parameters=parameters
            )
            
            if fal_result["status"] != GenerationStatus.COMPLETED:
                raise Exception(f"FAL.ai generation failed: {fal_result.get('error_message')}")
            
            output_urls = fal_result["output_urls"]
            logger.info(f"✅ [ENHANCED-GEN] FAL.ai completed, processing {len(output_urls)} files")
            
            # 4. Process files with async file processor
            if use_background_processing and len(output_urls) > 1:
                # Use background processing for multiple files
                task_id = await self._process_files_in_background(
                    generation_id=generation_id,
                    user_id=user_id,
                    urls=output_urls,
                    fal_metadata=fal_result["metadata"]
                )
                
                # Update generation with task info
                await self.generation_repo.update_generation(
                    str(generation_id),
                    {
                        "status": GenerationStatus.PROCESSING,
                        "metadata": {
                            **fal_result["metadata"],
                            "file_processing_task_id": task_id,
                            "processing_method": "background"
                        }
                    }
                )
                
                logger.info(f"📋 [ENHANCED-GEN] Background processing queued: {task_id}")
                
            else:
                # Process files immediately for single files or when background processing is disabled
                await self._process_files_immediately(
                    generation_id=generation_id,
                    user_id=user_id,
                    urls=output_urls,
                    fal_metadata=fal_result["metadata"]
                )
            
            # 5. Return updated generation
            updated_generation = await self.generation_repo.get_generation_by_id(str(generation_id))
            return GenerationResponse.model_validate(updated_generation.__dict__)
            
        except Exception as e:
            logger.error(f"❌ [ENHANCED-GEN] Generation failed: {e}")
            
            # Update generation status to failed
            if 'generation_id' in locals():
                await self.generation_repo.update_generation(
                    str(generation_id),
                    {
                        "status": GenerationStatus.FAILED,
                        "error_message": str(e),
                        "completed_at": datetime.utcnow()
                    }
                )
            
            raise
    
    async def _process_files_in_background(
        self,
        generation_id: UUID,
        user_id: UUID,
        urls: List[str],
        fal_metadata: Dict[str, Any]
    ) -> str:
        """Process files using background task queue."""
        logger.info(f"📋 [FILE-BACKGROUND] Queuing background file processing for generation {generation_id}")
        
        # Queue background task with custom options
        task_options = {
            'max_concurrent': 3,
            'fal_metadata': fal_metadata,
            'generation_callback': True  # Enable generation status updates
        }
        
        task_id = await task_manager.queue_file_processing(
            urls=urls,
            user_id=user_id,
            generation_id=generation_id,
            task_options=task_options
        )
        
        # Set up task completion callback (if using custom task system)
        asyncio.create_task(
            self._monitor_background_task(generation_id, task_id)
        )
        
        return task_id
    
    async def _process_files_immediately(
        self,
        generation_id: UUID,
        user_id: UUID,
        urls: List[str],
        fal_metadata: Dict[str, Any]
    ):
        """Process files immediately (synchronously)."""
        logger.info(f"⚡ [FILE-IMMEDIATE] Processing {len(urls)} files immediately for generation {generation_id}")
        
        try:
            # Use async file processor for batch processing
            result = await async_file_processor.process_file_batch(
                urls=urls,
                user_id=user_id,
                generation_id=generation_id,
                max_concurrent=2  # Lower concurrency for immediate processing
            )
            
            if result.success:
                # Update generation with completed files
                await self._update_generation_with_files(
                    generation_id=generation_id,
                    processed_files=result.processed_files,
                    fal_metadata=fal_metadata,
                    processing_time=result.processing_time
                )
                
                logger.info(f"✅ [FILE-IMMEDIATE] Files processed successfully for generation {generation_id}")
                
            else:
                # Partial success - update with available files
                await self._update_generation_with_partial_success(
                    generation_id=generation_id,
                    result=result,
                    fal_metadata=fal_metadata
                )
                
                logger.warning(f"⚠️ [FILE-IMMEDIATE] Partial file processing for generation {generation_id}")
        
        except FileProcessingError as e:
            logger.error(f"❌ [FILE-IMMEDIATE] File processing failed for generation {generation_id}: {e}")
            
            # Update generation status to failed
            await self.generation_repo.update_generation(
                str(generation_id),
                {
                    "status": GenerationStatus.FAILED,
                    "error_message": f"File processing failed: {str(e)}",
                    "completed_at": datetime.utcnow()
                }
            )
            raise
    
    async def _monitor_background_task(self, generation_id: UUID, task_id: str):
        """Monitor background task and update generation when complete."""
        logger.info(f"👀 [TASK-MONITOR] Monitoring background task {task_id} for generation {generation_id}")
        
        try:
            # Poll task status until completion
            while True:
                status = await task_manager.get_task_status(task_id)
                
                if status['ready']:
                    if status.get('successful'):
                        # Task completed successfully
                        result = status['result']
                        logger.info(f"✅ [TASK-MONITOR] Background task completed: {task_id}")
                        
                        # The actual file processing and generation update would be handled
                        # by the background task itself. This is just for monitoring.
                        await self.generation_repo.update_generation(
                            str(generation_id),
                            {
                                "status": GenerationStatus.COMPLETED,
                                "completed_at": datetime.utcnow(),
                                "metadata": {
                                    "background_task_completed": True,
                                    "background_task_id": task_id,
                                    "files_processed": result.get('successful_files', 0),
                                    "processing_time": result.get('processing_time', 0)
                                }
                            }
                        )
                        
                    else:
                        # Task failed
                        logger.error(f"❌ [TASK-MONITOR] Background task failed: {task_id}")
                        await self.generation_repo.update_generation(
                            str(generation_id),
                            {
                                "status": GenerationStatus.FAILED,
                                "error_message": f"Background file processing failed: {status.get('error')}",
                                "completed_at": datetime.utcnow()
                            }
                        )
                    
                    break
                
                # Wait before checking again
                await asyncio.sleep(5)
                
        except Exception as e:
            logger.error(f"❌ [TASK-MONITOR] Task monitoring failed for {task_id}: {e}")
    
    async def _update_generation_with_files(
        self,
        generation_id: UUID,
        processed_files: List[Any],
        fal_metadata: Dict[str, Any],
        processing_time: float
    ):
        """Update generation with successfully processed files."""
        # Prepare media files information
        media_files = []
        total_size = 0
        
        for file_meta in processed_files:
            media_files.append({
                "file_id": str(file_meta.id),
                "bucket": file_meta.bucket_name.value,
                "path": file_meta.file_path,
                "size": file_meta.file_size,
                "content_type": file_meta.content_type.value,
                "original_filename": file_meta.original_filename
            })
            total_size += file_meta.file_size
        
        # Update generation record
        await self.generation_repo.update_generation(
            str(generation_id),
            {
                "status": GenerationStatus.COMPLETED,
                "media_files": media_files,
                "completed_at": datetime.utcnow(),
                "metadata": {
                    **fal_metadata,
                    "file_processing_time": processing_time,
                    "total_file_size": total_size,
                    "files_count": len(processed_files),
                    "processing_method": "async_processor"
                }
            }
        )
        
        logger.info(f"✅ [UPDATE-GEN] Generation {generation_id} updated with {len(processed_files)} files")
    
    async def _update_generation_with_partial_success(
        self,
        generation_id: UUID,
        result: Any,
        fal_metadata: Dict[str, Any]
    ):
        """Update generation with partial file processing results."""
        # Prepare media files for successful files only
        media_files = []
        for file_meta in result.processed_files:
            media_files.append({
                "file_id": str(file_meta.id),
                "bucket": file_meta.bucket_name.value,
                "path": file_meta.file_path,
                "size": file_meta.file_size,
                "content_type": file_meta.content_type.value
            })
        
        # Prepare error information
        error_summary = {
            "failed_files_count": len(result.failed_files),
            "successful_files_count": len(result.processed_files),
            "errors": [f['error'] for f in result.failed_files[:5]]  # Limit error details
        }
        
        # Update with partial success status
        status = GenerationStatus.COMPLETED if len(result.processed_files) > 0 else GenerationStatus.FAILED
        
        await self.generation_repo.update_generation(
            str(generation_id),
            {
                "status": status,
                "media_files": media_files,
                "completed_at": datetime.utcnow(),
                "error_message": f"Partial processing: {len(result.failed_files)} files failed" if result.failed_files else None,
                "metadata": {
                    **fal_metadata,
                    "file_processing_time": result.processing_time,
                    "processing_errors": error_summary,
                    "processing_method": "async_processor_partial"
                }
            }
        )
    
    async def _deduct_credits(self, user_id: UUID, credits_required: int):
        """Deduct credits for generation (placeholder implementation)."""
        logger.info(f"💳 [CREDITS] Deducting {credits_required} credits for user {user_id}")
        
        # This would integrate with your existing credit system
        # For now, just log the operation
        
        # Example implementation:
        # user_credits = await self.credit_repo.get_user_credits(user_id)
        # if user_credits < credits_required:
        #     raise InsufficientCreditsError(f"Required: {credits_required}, Available: {user_credits}")
        # await self.credit_repo.deduct_credits(user_id, credits_required)
        
        pass
    
    async def get_generation_with_file_status(self, generation_id: Union[UUID, str]) -> Dict[str, Any]:
        """
        Get generation with detailed file processing status.
        
        Args:
            generation_id: Generation ID
        
        Returns:
            Generation data with file processing details
        """
        if isinstance(generation_id, str):
            generation_id = UUID(generation_id)
        
        await self._get_repositories()
        
        # Get generation data
        generation = await self.generation_repo.get_generation_by_id(str(generation_id))
        if not generation:
            raise ValueError(f"Generation {generation_id} not found")
        
        generation_data = generation.__dict__.copy()
        
        # Add file processing status if background task is running
        metadata = generation_data.get('metadata', {})
        if 'file_processing_task_id' in metadata:
            task_id = metadata['file_processing_task_id']
            task_status = await task_manager.get_task_status(task_id)
            
            generation_data['file_processing_status'] = {
                'task_id': task_id,
                'status': task_status.get('status', 'unknown'),
                'ready': task_status.get('ready', False),
                'progress': task_status.get('meta', {}).get('progress', 0) if not task_status.get('ready') else 100
            }
        
        # Add file details if available
        if generation_data.get('media_files'):
            generation_data['file_details'] = {
                'count': len(generation_data['media_files']),
                'total_size': sum(f.get('size', 0) for f in generation_data['media_files']),
                'types': list(set(f.get('content_type', 'unknown') for f in generation_data['media_files']))
            }
        
        return generation_data
    
    async def retry_failed_file_processing(
        self,
        generation_id: Union[UUID, str],
        use_background: bool = True
    ) -> bool:
        """
        Retry file processing for a failed generation.
        
        Args:
            generation_id: Generation ID to retry
            use_background: Whether to use background processing
        
        Returns:
            True if retry was initiated successfully
        """
        if isinstance(generation_id, str):
            generation_id = UUID(generation_id)
        
        logger.info(f"🔄 [RETRY] Retrying file processing for generation {generation_id}")
        
        await self._get_repositories()
        
        generation = await self.generation_repo.get_generation_by_id(str(generation_id))
        if not generation:
            raise ValueError(f"Generation {generation_id} not found")
        
        # Check if generation has FAL output URLs to retry
        metadata = generation.metadata or {}
        fal_result = metadata.get('fal_result', {})
        output_urls = fal_result.get('output_urls', [])
        
        if not output_urls:
            raise ValueError("No output URLs available for retry")
        
        # Reset generation status
        await self.generation_repo.update_generation(
            str(generation_id),
            {
                "status": GenerationStatus.PROCESSING,
                "error_message": None,
                "completed_at": None,
                "metadata": {
                    **metadata,
                    "retry_attempted": True,
                    "retry_timestamp": datetime.utcnow().isoformat()
                }
            }
        )
        
        # Retry file processing
        user_id = UUID(generation.user_id)
        
        if use_background:
            task_id = await self._process_files_in_background(
                generation_id=generation_id,
                user_id=user_id,
                urls=output_urls,
                fal_metadata=fal_result
            )
            
            await self.generation_repo.update_generation(
                str(generation_id),
                {
                    "metadata": {
                        **metadata,
                        "retry_task_id": task_id
                    }
                }
            )
        else:
            await self._process_files_immediately(
                generation_id=generation_id,
                user_id=user_id,
                urls=output_urls,
                fal_metadata=fal_result
            )
        
        logger.info(f"✅ [RETRY] File processing retry initiated for generation {generation_id}")
        return True


# Global service instance
enhanced_generation_service = EnhancedGenerationService()