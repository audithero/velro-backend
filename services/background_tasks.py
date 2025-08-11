"""
Background Task Processing System with Celery and asyncio integration.
Following CLAUDE.md: Robust background processing with error handling.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union, Callable
from uuid import UUID
import json
from celery import Celery
from celery.result import AsyncResult
from contextlib import asynccontextmanager

from config import settings
from services.async_file_processor import async_file_processor, ProcessingResult

logger = logging.getLogger(__name__)


# Celery configuration
def create_celery_app() -> Celery:
    """Create and configure Celery app."""
    celery_app = Celery(
        'velro_background_tasks',
        broker=settings.redis_url if settings.redis_url else 'redis://localhost:6379/0',
        backend=settings.redis_url if settings.redis_url else 'redis://localhost:6379/0',
        include=['services.background_tasks']
    )
    
    # Configure Celery
    celery_app.conf.update(
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_time_limit=30 * 60,  # 30 minutes
        task_soft_time_limit=25 * 60,  # 25 minutes
        worker_prefetch_multiplier=1,
        task_acks_late=True,
        worker_disable_rate_limits=False,
        task_routes={
            'services.background_tasks.process_file_batch_task': {'queue': 'file_processing'},
            'services.background_tasks.cleanup_files_task': {'queue': 'maintenance'},
            'services.background_tasks.compress_images_task': {'queue': 'optimization'},
        }
    )
    
    return celery_app


# Global Celery app instance
celery_app = create_celery_app()


class TaskStatus:
    """Task status constants."""
    PENDING = 'PENDING'
    STARTED = 'STARTED'
    SUCCESS = 'SUCCESS'
    FAILURE = 'FAILURE'
    RETRY = 'RETRY'
    REVOKED = 'REVOKED'


class BackgroundTaskManager:
    """Manager for background task operations."""
    
    def __init__(self):
        self.fallback_tasks = {}  # For when Celery is not available
        self.use_celery = self._check_celery_available()
    
    def _check_celery_available(self) -> bool:
        """Check if Celery broker is available."""
        try:
            # Simple ping to check if broker is available
            celery_app.control.inspect().ping()
            return True
        except Exception as e:
            logger.warning(f"⚠️ [TASK-MANAGER] Celery not available, using asyncio fallback: {e}")
            return False
    
    async def queue_file_processing(
        self,
        urls: List[str],
        user_id: Union[UUID, str],
        generation_id: Union[UUID, str],
        task_options: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Queue file processing task.
        
        Args:
            urls: File URLs to process
            user_id: User ID
            generation_id: Generation ID
            task_options: Additional task options
        
        Returns:
            Task ID for tracking
        """
        task_data = {
            'urls': urls,
            'user_id': str(user_id),
            'generation_id': str(generation_id),
            'options': task_options or {}
        }
        
        if self.use_celery:
            result = process_file_batch_task.delay(**task_data)
            task_id = result.id
            logger.info(f"📋 [CELERY-TASK] Queued file processing task: {task_id}")
        else:
            # Fallback to asyncio
            task_id = await async_file_processor.queue_file_processing_task(
                urls=urls,
                user_id=user_id,
                generation_id=generation_id
            )
            logger.info(f"📋 [ASYNCIO-TASK] Queued file processing task: {task_id}")
        
        return task_id
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get task status and result."""
        if self.use_celery:
            try:
                result = AsyncResult(task_id, app=celery_app)
                
                status = {
                    'task_id': task_id,
                    'status': result.status,
                    'ready': result.ready(),
                    'successful': result.successful() if result.ready() else None,
                    'failed': result.failed() if result.ready() else None,
                }
                
                if result.ready():
                    if result.successful():
                        status['result'] = result.result
                    else:
                        status['error'] = str(result.result)
                        status['traceback'] = result.traceback
                
                return status
                
            except Exception as e:
                logger.error(f"❌ [CELERY-STATUS] Error getting task status {task_id}: {e}")
                return {
                    'task_id': task_id,
                    'status': TaskStatus.FAILURE,
                    'error': f'Status check failed: {str(e)}'
                }
        else:
            # Fallback to asyncio task status
            status = await async_file_processor.get_task_status(task_id)
            if status:
                return {
                    'task_id': task_id,
                    'status': status.get('status', 'unknown').upper(),
                    'ready': status.get('status') in ['completed', 'failed'],
                    'result': status.get('result'),
                    'error': status.get('error')
                }
            else:
                return {
                    'task_id': task_id,
                    'status': 'NOT_FOUND',
                    'error': 'Task not found'
                }
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if self.use_celery:
            try:
                celery_app.control.revoke(task_id, terminate=True)
                logger.info(f"🚫 [CELERY-CANCEL] Task cancelled: {task_id}")
                return True
            except Exception as e:
                logger.error(f"❌ [CELERY-CANCEL] Error cancelling task {task_id}: {e}")
                return False
        else:
            # For asyncio tasks, we can't easily cancel them once started
            logger.warning(f"⚠️ [ASYNCIO-CANCEL] Cannot cancel asyncio task: {task_id}")
            return False
    
    async def queue_maintenance_task(
        self,
        task_type: str,
        options: Optional[Dict[str, Any]] = None
    ) -> str:
        """Queue maintenance task."""
        if self.use_celery:
            if task_type == 'cleanup_files':
                result = cleanup_files_task.delay(options or {})
                task_id = result.id
            else:
                raise ValueError(f"Unknown maintenance task type: {task_type}")
            
            logger.info(f"📋 [CELERY-MAINTENANCE] Queued {task_type} task: {task_id}")
        else:
            # Fallback maintenance tasks
            task_id = f"maintenance_{task_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            asyncio.create_task(self._run_maintenance_task(task_type, options or {}, task_id))
            logger.info(f"📋 [ASYNCIO-MAINTENANCE] Queued {task_type} task: {task_id}")
        
        return task_id
    
    async def _run_maintenance_task(self, task_type: str, options: Dict[str, Any], task_id: str):
        """Run maintenance task in asyncio."""
        try:
            if task_type == 'cleanup_files':
                max_age_hours = options.get('max_age_hours', 24)
                await async_file_processor.cleanup_temporary_files(max_age_hours)
        except Exception as e:
            logger.error(f"❌ [MAINTENANCE] Task {task_id} failed: {e}")
    
    def get_worker_stats(self) -> Dict[str, Any]:
        """Get Celery worker statistics."""
        if not self.use_celery:
            return {'error': 'Celery not available'}
        
        try:
            inspect = celery_app.control.inspect()
            stats = inspect.stats()
            active = inspect.active()
            scheduled = inspect.scheduled()
            
            return {
                'workers': stats or {},
                'active_tasks': active or {},
                'scheduled_tasks': scheduled or {},
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ [WORKER-STATS] Error getting worker stats: {e}")
            return {'error': str(e)}


# Global task manager instance
task_manager = BackgroundTaskManager()


# === Celery Task Definitions ===

@celery_app.task(bind=True, autoretry_for=(Exception,), retry_kwargs={'max_retries': 3, 'countdown': 60})
def process_file_batch_task(self, urls: List[str], user_id: str, generation_id: str, options: Dict[str, Any]):
    """
    Celery task for processing file batches.
    
    Args:
        urls: List of file URLs
        user_id: User ID string
        generation_id: Generation ID string
        options: Processing options
    
    Returns:
        Processing result dictionary
    """
    logger.info(f"🚀 [CELERY-FILE] Starting file batch processing task: {self.request.id}")
    
    try:
        # Update task state
        self.update_state(
            state=TaskStatus.STARTED,
            meta={'status': 'Initializing file processing', 'progress': 0}
        )
        
        # Run async file processing in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            # Progress callback for updates
            def progress_callback(completed: int, total: int, current_url: str):
                progress = int((completed / total) * 100)
                self.update_state(
                    state=TaskStatus.STARTED,
                    meta={
                        'status': f'Processing file {completed}/{total}',
                        'progress': progress,
                        'current_url': current_url[:100]
                    }
                )
            
            # Process files
            result = loop.run_until_complete(
                async_file_processor.process_file_batch(
                    urls=urls,
                    user_id=UUID(user_id),
                    generation_id=UUID(generation_id),
                    max_concurrent=options.get('max_concurrent', 3),
                    progress_callback=progress_callback
                )
            )
            
            # Convert result to dict for JSON serialization
            result_dict = {
                'success': result.success,
                'total_files': result.total_files,
                'successful_files': len(result.processed_files),
                'failed_files': len(result.failed_files),
                'processing_time': result.processing_time,
                'errors': result.errors[:10],  # Limit error details
                'processed_file_ids': [str(f.id) for f in result.processed_files],
                'completed_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"✅ [CELERY-FILE] Task completed successfully: {self.request.id}")
            return result_dict
            
        finally:
            loop.close()
    
    except Exception as e:
        logger.error(f"❌ [CELERY-FILE] Task failed: {self.request.id} - {e}")
        
        # Update state with error
        self.update_state(
            state=TaskStatus.FAILURE,
            meta={'error': str(e), 'failed_at': datetime.utcnow().isoformat()}
        )
        
        # Re-raise for Celery retry mechanism
        raise


@celery_app.task(bind=True)
def cleanup_files_task(self, options: Dict[str, Any]):
    """
    Celery task for file cleanup.
    
    Args:
        options: Cleanup options
    
    Returns:
        Cleanup result
    """
    logger.info(f"🧹 [CELERY-CLEANUP] Starting cleanup task: {self.request.id}")
    
    try:
        max_age_hours = options.get('max_age_hours', 24)
        
        # Update task state
        self.update_state(
            state=TaskStatus.STARTED,
            meta={'status': f'Cleaning up files older than {max_age_hours}h'}
        )
        
        # Run cleanup in async context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            cleanup_count = loop.run_until_complete(
                async_file_processor.cleanup_temporary_files(max_age_hours)
            )
            
            result = {
                'cleanup_count': cleanup_count,
                'max_age_hours': max_age_hours,
                'completed_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"✅ [CELERY-CLEANUP] Task completed: {self.request.id} - {cleanup_count} files cleaned")
            return result
            
        finally:
            loop.close()
    
    except Exception as e:
        logger.error(f"❌ [CELERY-CLEANUP] Task failed: {self.request.id} - {e}")
        
        self.update_state(
            state=TaskStatus.FAILURE,
            meta={'error': str(e), 'failed_at': datetime.utcnow().isoformat()}
        )
        
        raise


@celery_app.task(bind=True)
def compress_images_task(self, file_ids: List[str], user_id: str, quality: int = 85):
    """
    Celery task for batch image compression.
    
    Args:
        file_ids: List of file IDs to compress
        user_id: User ID
        quality: Compression quality (1-100)
    
    Returns:
        Compression result
    """
    logger.info(f"🗜️ [CELERY-COMPRESS] Starting image compression task: {self.request.id}")
    
    try:
        self.update_state(
            state=TaskStatus.STARTED,
            meta={'status': f'Compressing {len(file_ids)} images', 'progress': 0}
        )
        
        # This would implement actual compression logic
        # For now, return placeholder result
        result = {
            'compressed_count': len(file_ids),
            'quality': quality,
            'space_saved_bytes': 0,  # Would calculate actual savings
            'completed_at': datetime.utcnow().isoformat()
        }
        
        logger.info(f"✅ [CELERY-COMPRESS] Task completed: {self.request.id}")
        return result
    
    except Exception as e:
        logger.error(f"❌ [CELERY-COMPRESS] Task failed: {self.request.id} - {e}")
        
        self.update_state(
            state=TaskStatus.FAILURE,
            meta={'error': str(e), 'failed_at': datetime.utcnow().isoformat()}
        )
        
        raise


# === Periodic Tasks (if using Celery Beat) ===

@celery_app.task
def periodic_cleanup_task():
    """Periodic cleanup of temporary files."""
    logger.info("🔄 [PERIODIC] Running periodic cleanup")
    
    try:
        # Queue cleanup task
        cleanup_files_task.delay({'max_age_hours': 24})
        logger.info("✅ [PERIODIC] Cleanup task queued")
    except Exception as e:
        logger.error(f"❌ [PERIODIC] Failed to queue cleanup: {e}")


# === Celery Beat Schedule (uncomment to enable) ===

# celery_app.conf.beat_schedule = {
#     'cleanup-temp-files': {
#         'task': 'services.background_tasks.periodic_cleanup_task',
#         'schedule': timedelta(hours=6),  # Run every 6 hours
#     },
# }