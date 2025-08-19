"""
Async FAL.ai integration service for scalable AI generation.
Replaces blocking calls with non-blocking async queue management.
"""
import asyncio
import json
import logging
import os
import time
from typing import Dict, Any, Optional, List
from uuid import UUID, uuid4
from datetime import datetime, timedelta
from enum import Enum

import fal_client
import redis  # Use synchronous Redis, not async
from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings
from models.fal_config import get_model_config, validate_model_parameters, FALModelType
from models.generation import GenerationStatus

logger = logging.getLogger(__name__)


class QueueStatus(str, Enum):
    """Status for generation queue tracking"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AsyncFALService:
    """Scalable async service for FAL.ai API integration."""
    
    def __init__(self):
        """Initialize the async FAL service with connection pools and rate limiting."""
        # Configure FAL client
        if settings.fal_key:
            os.environ['FAL_KEY'] = settings.fal_key
            logger.info("FAL_KEY configured for async FAL service")
        else:
            logger.error("FAL_KEY not configured - FAL API calls will fail")
            
        # Redis for caching and queue management (optional)
        self.redis_pool = None
        self.redis = None
        
        # Try to initialize Redis if URL is provided
        if hasattr(settings, 'redis_url') and settings.redis_url:
            try:
                self.redis_pool = redis.ConnectionPool.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    max_connections=50
                )
                self.redis = redis.Redis(connection_pool=self.redis_pool)
                logger.info("Redis cache initialized for async FAL service")
            except Exception as e:
                logger.warning(f"Redis not available, running without cache: {e}")
        else:
            logger.info("Running async FAL service without Redis cache")
        
        # Concurrent request management
        self.semaphore = asyncio.Semaphore(10)  # Max 10 concurrent FAL calls
        self.active_generations = {}  # Track active generation requests
        
        # Rate limiting
        self.rate_limit_window = 60  # seconds
        self.rate_limit_max = 100  # requests per window
        
    async def submit_generation(
        self,
        user_id: str,
        model_id: str,
        prompt: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Submit a generation request to FAL.ai async queue.
        Returns immediately with generation ID and status.
        
        Args:
            user_id: User ID requesting generation
            model_id: FAL.ai model identifier
            prompt: Text prompt for generation
            negative_prompt: Optional negative prompt
            reference_image_url: Optional reference image URL
            parameters: Additional model-specific parameters
            
        Returns:
            Dict with generation_id, status, and queue position
        """
        try:
            # Generate unique ID for this generation
            generation_id = str(uuid4())
            
            # Check cache first
            cache_key = self._generate_cache_key(model_id, prompt, parameters)
            cached_result = await self._get_cached_result(cache_key)
            
            if cached_result:
                logger.info(f"Cache hit for generation {generation_id}")
                return {
                    "generation_id": generation_id,
                    "status": QueueStatus.COMPLETED,
                    "output_urls": cached_result["output_urls"],
                    "cached": True,
                    "metadata": cached_result.get("metadata", {})
                }
            
            # Check rate limit
            if not await self._check_rate_limit(user_id):
                return {
                    "generation_id": generation_id,
                    "status": QueueStatus.FAILED,
                    "error": "Rate limit exceeded. Please try again later.",
                    "cached": False
                }
            
            # Get model configuration
            model_config = get_model_config(model_id)
            
            # Prepare generation parameters
            generation_params = {"prompt": prompt}
            
            if negative_prompt:
                generation_params["negative_prompt"] = negative_prompt
                
            if reference_image_url:
                if "image" in model_config.parameters:
                    generation_params["image"] = reference_image_url
                elif "first_frame_image" in model_config.parameters:
                    generation_params["first_frame_image"] = reference_image_url
                    
            if parameters:
                generation_params.update(parameters)
                
            # Validate parameters
            validated_params = validate_model_parameters(model_id, generation_params)
            
            # Submit to FAL async queue (non-blocking)
            logger.info(f"Submitting generation {generation_id} to FAL async queue")
            
            # FAL client has both sync and async methods
            # We'll use the synchronous submit method in an executor
            import asyncio
            from functools import partial
            loop = asyncio.get_event_loop()
            
            async with self.semaphore:  # Limit concurrent FAL calls
                # Use synchronous submit (not submit_async) in thread pool
                response = await loop.run_in_executor(
                    None,
                    partial(fal_client.submit, model_config.endpoint, arguments=validated_params)
                )
            
            # Store generation metadata in Redis
            generation_data = {
                "generation_id": generation_id,
                "user_id": user_id,
                "model_id": model_id,
                "request_id": response.request_id,
                "status": QueueStatus.QUEUED,
                "cache_key": cache_key,
                "created_at": datetime.now().isoformat(),
                "prompt": prompt,
                "parameters": json.dumps(parameters or {})
            }
            
            if self.redis:
                self.redis.setex(
                    f"generation:{generation_id}",
                    3600,  # 1 hour TTL
                    json.dumps(generation_data)
                )
                
                # Store user's generation list
                self.redis.lpush(f"user_generations:{user_id}", generation_id)
                self.redis.ltrim(f"user_generations:{user_id}", 0, 99)  # Keep last 100
            
            # Start background task to process generation
            asyncio.create_task(self._process_generation(generation_id, response))
            
            # Get queue position
            queue_position = await self._get_queue_position(response.request_id)
            
            return {
                "generation_id": generation_id,
                "status": QueueStatus.QUEUED,
                "queue_position": queue_position,
                "estimated_time": self._estimate_generation_time(model_config.ai_model_type),
                "cached": False
            }
            
        except Exception as e:
            logger.error(f"Failed to submit generation: {e}")
            return {
                "generation_id": generation_id if 'generation_id' in locals() else None,
                "status": QueueStatus.FAILED,
                "error": str(e),
                "cached": False
            }
    
    async def get_generation_status(self, generation_id: str) -> Dict[str, Any]:
        """
        Get the current status of a generation request.
        
        Args:
            generation_id: The generation ID to check
            
        Returns:
            Dict with status, queue position, and results if completed
        """
        try:
            # Get generation data from Redis (if available)
            generation_data = None
            if self.redis:
                generation_data = self.redis.get(f"generation:{generation_id}") if self.redis else None
            
            if not generation_data:
                return {
                    "generation_id": generation_id,
                    "status": "not_found",
                    "error": "Generation not found or expired"
                }
            
            data = json.loads(generation_data)
            
            # If completed, return results
            if data["status"] == QueueStatus.COMPLETED:
                return {
                    "generation_id": generation_id,
                    "status": data["status"],
                    "output_urls": data.get("output_urls", []),
                    "metadata": data.get("metadata", {})
                }
            
            # If still processing, check FAL status
            if data["status"] in [QueueStatus.QUEUED, QueueStatus.PROCESSING]:
                request_id = data["request_id"]
                
                # Get current status from FAL
                try:
                    # FAL client is synchronous, run in executor
                    # We need both the application endpoint and request_id
                    model_config = get_model_config(data.get("model_id", ""))
                    loop = asyncio.get_event_loop()
                    status = await loop.run_in_executor(
                        None, 
                        lambda: fal_client.sync_client.status(model_config.endpoint, request_id)
                    )
                    
                    if isinstance(status, fal_client.Completed):
                        # Update to completed and get results
                        # FAL client is synchronous, run in executor
                        result = await loop.run_in_executor(
                            None,
                            lambda: fal_client.sync_client.result(model_config.endpoint, request_id)
                        )
                        await self._handle_completion(generation_id, result)
                        
                        return {
                            "generation_id": generation_id,
                            "status": QueueStatus.COMPLETED,
                            "output_urls": self._extract_output_urls(result),
                            "metadata": {"generation_time": status.metrics.get("inference_time")}
                        }
                    else:
                        # Still in queue or processing
                        queue_position = getattr(status, 'queue_position', None)
                        
                        return {
                            "generation_id": generation_id,
                            "status": QueueStatus.PROCESSING if isinstance(status, fal_client.InProgress) else QueueStatus.QUEUED,
                            "queue_position": queue_position,
                            "estimated_time": self._estimate_remaining_time(queue_position)
                        }
                        
                except Exception as e:
                    logger.error(f"Failed to get FAL status: {e}")
                    
            return {
                "generation_id": generation_id,
                "status": data["status"],
                "error": data.get("error")
            }
            
        except Exception as e:
            logger.error(f"Failed to get generation status: {e}")
            return {
                "generation_id": generation_id,
                "status": "error",
                "error": str(e)
            }
    
    async def stream_generation_events(self, generation_id: str):
        """
        Stream generation events for real-time updates.
        Yields events as they occur.
        
        Args:
            generation_id: The generation ID to stream
            
        Yields:
            Dict events with status updates
        """
        try:
            # Get generation data
            generation_data = self.redis.get(f"generation:{generation_id}") if self.redis else None
            
            if not generation_data:
                yield {
                    "event": "error",
                    "data": {"error": "Generation not found"}
                }
                return
            
            data = json.loads(generation_data)
            request_id = data["request_id"]
            
            # Stream FAL events
            # Note: Streaming is not available with synchronous client
            # We'll poll instead
            import asyncio
            loop = asyncio.get_event_loop()
            
            # Get model config for FAL client calls
            model_config = get_model_config(data.get("model_id", ""))
            
            while True:
                await asyncio.sleep(2)
                status = await loop.run_in_executor(
                    None,
                    lambda: fal_client.sync_client.status(model_config.endpoint, request_id)
                )
                
                if hasattr(status, 'queue_position'):
                    yield {
                        "event": "queued",
                        "data": {
                            "position": status.queue_position,
                            "status": QueueStatus.QUEUED
                        }
                    }
                elif isinstance(status, fal_client.InProgress):
                    yield {
                        "event": "processing",
                        "data": {
                            "status": QueueStatus.PROCESSING
                        }
                    }
                elif isinstance(status, fal_client.Completed):
                    result = await loop.run_in_executor(
                        None,
                        lambda: fal_client.sync_client.result(model_config.endpoint, request_id) 
                    )
                    await self._handle_completion(generation_id, result)
                    
                    yield {
                        "event": "completed",
                        "data": {
                            "status": QueueStatus.COMPLETED,
                            "output_urls": self._extract_output_urls(result)
                        }
                    }
                    break
                elif hasattr(status, 'failed') and status.failed:
                    yield {
                        "event": "error",
                        "data": {
                            "status": QueueStatus.FAILED,
                            "error": getattr(status, 'error', 'Generation failed')
                        }
                    }
                    break
            
            return  # Exit the generator
                    
        except Exception as e:
            logger.error(f"Failed to stream generation events: {e}")
            yield {
                "event": "error",
                "data": {"error": str(e)}
            }
    
    async def cancel_generation(self, generation_id: str) -> bool:
        """
        Cancel a generation request if still in queue.
        
        Args:
            generation_id: The generation ID to cancel
            
        Returns:
            True if cancelled, False otherwise
        """
        try:
            generation_data = self.redis.get(f"generation:{generation_id}") if self.redis else None
            
            if not generation_data:
                return False
            
            data = json.loads(generation_data)
            
            if data["status"] in [QueueStatus.QUEUED, QueueStatus.PROCESSING]:
                # Update status to cancelled
                data["status"] = QueueStatus.CANCELLED
                self.redis.setex(
                    f"generation:{generation_id}",
                    3600,
                    json.dumps(data)
                )
                
                # Attempt to cancel with FAL (may not always work)
                try:
                    # FAL client is synchronous, run in executor
                    model_config = get_model_config(data.get("model_id", ""))
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: fal_client.sync_client.cancel(model_config.endpoint, data["request_id"])
                    )
                except:
                    pass  # FAL cancel might fail if already processing
                
                return True
                
            return False
            
        except Exception as e:
            logger.error(f"Failed to cancel generation: {e}")
            return False
    
    # Private helper methods
    
    async def _process_generation(self, generation_id: str, response):
        """
        Background task to process generation and update status.
        """
        try:
            # The response from submit_async is already a handle object
            # We need to use fal_client.result() to get the actual result
            request_id = response.request_id if hasattr(response, 'request_id') else str(response)
            
            # Poll for completion
            max_attempts = 60  # 3 minutes max
            for attempt in range(max_attempts):
                await asyncio.sleep(3)  # Wait 3 seconds between polls
                
                try:
                    # Check status (FAL client is synchronous, run in executor) 
                    # Get the application endpoint from stored data
                    gen_data = self.redis.get(f"generation:{generation_id}") if self.redis else None
                    if gen_data:
                        data = json.loads(gen_data)
                        model_config = get_model_config(data.get("model_id", ""))
                        
                        loop = asyncio.get_event_loop()
                        status = await loop.run_in_executor(
                            None,
                            lambda: fal_client.sync_client.status(model_config.endpoint, request_id)
                        )
                    else:
                        raise Exception("Generation data not found")
                    
                    if isinstance(status, fal_client.Completed):
                        # Get the result (synchronous, run in executor)
                        result = await loop.run_in_executor(
                            None,
                            lambda: fal_client.sync_client.result(model_config.endpoint, request_id)
                        )
                        await self._handle_completion(generation_id, result)
                        return
                    elif hasattr(status, 'failed') and status.failed:
                        error_msg = getattr(status, 'error', 'Generation failed')
                        await self._mark_generation_failed(generation_id, error_msg)
                        return
                except Exception as poll_error:
                    logger.warning(f"Poll attempt {attempt + 1} failed: {poll_error}")
                    if attempt >= max_attempts - 1:
                        raise
            
            # Timeout
            await self._mark_generation_failed(generation_id, "Generation timed out")
            
        except Exception as e:
            logger.error(f"Failed to process generation {generation_id}: {e}")
            await self._mark_generation_failed(generation_id, str(e))
    
    async def _handle_completion(self, generation_id: str, result: Dict[str, Any]):
        """
        Handle successful generation completion.
        """
        try:
            # Get generation data
            generation_data = self.redis.get(f"generation:{generation_id}") if self.redis else None
            if not generation_data:
                return
            
            data = json.loads(generation_data)
            
            # Extract output URLs
            output_urls = self._extract_output_urls(result)
            
            # Update generation data
            data["status"] = QueueStatus.COMPLETED
            data["output_urls"] = output_urls
            data["completed_at"] = datetime.now().isoformat()
            data["metadata"] = {
                "generation_time": time.time() - datetime.fromisoformat(data["created_at"]).timestamp()
            }
            
            # Store updated data
            if self.redis:
                self.redis.setex(
                    f"generation:{generation_id}",
                    3600,  # Keep for 1 hour
                    json.dumps(data)
                )
            
            # Cache the result
            await self._cache_result(data["cache_key"], {
                "output_urls": output_urls,
                "metadata": data["metadata"]
            })
            
            # Update database
            await self._update_database_record(generation_id, data)
            
            logger.info(f"Generation {generation_id} completed successfully")
            
        except Exception as e:
            logger.error(f"Failed to handle completion for {generation_id}: {e}")
    
    async def _mark_generation_failed(self, generation_id: str, error: str):
        """
        Mark a generation as failed.
        """
        try:
            generation_data = self.redis.get(f"generation:{generation_id}") if self.redis else None
            if not generation_data:
                return
            
            data = json.loads(generation_data)
            data["status"] = QueueStatus.FAILED
            data["error"] = error
            data["failed_at"] = datetime.now().isoformat()
            
            if self.redis:
                self.redis.setex(
                    f"generation:{generation_id}",
                    3600,
                    json.dumps(data)
                )
            
        except Exception as e:
            logger.error(f"Failed to mark generation as failed: {e}")
    
    def _generate_cache_key(self, model_id: str, prompt: str, parameters: Optional[Dict]) -> str:
        """
        Generate a cache key for a generation request.
        """
        import hashlib
        
        # Normalize prompt
        normalized_prompt = prompt.lower().strip()
        
        # Sort parameters for consistency
        sorted_params = json.dumps(parameters or {}, sort_keys=True)
        
        # Create hash
        content = f"{model_id}:{normalized_prompt}:{sorted_params}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def _get_cached_result(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached result if available.
        """
        try:
            cached = self.redis.get(f"cache:{cache_key}") if self.redis else None
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.error(f"Failed to get cached result: {e}")
        return None
    
    async def _cache_result(self, cache_key: str, result: Dict[str, Any]):
        """
        Cache generation result.
        """
        try:
            if self.redis:
                self.redis.setex(
                    f"cache:{cache_key}",
                    3600,  # 1 hour cache
                    json.dumps(result)
                )
        except Exception as e:
            logger.error(f"Failed to cache result: {e}")
    
    async def _check_rate_limit(self, user_id: str) -> bool:
        """
        Check if user is within rate limits.
        """
        try:
            key = f"rate_limit:{user_id}"
            
            # Increment counter
            if not self.redis:
                return True  # No rate limiting without Redis
                
            count = self.redis.incr(key)
            
            # Set expiry on first request
            if count == 1:
                self.redis.expire(key, self.rate_limit_window)
            
            # Check if over limit
            if count > self.rate_limit_max:
                logger.warning(f"Rate limit exceeded for user {user_id}")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to check rate limit: {e}")
            return True  # Allow on error
    
    async def _get_queue_position(self, request_id: str) -> Optional[int]:
        """
        Get queue position for a request.
        """
        try:
            # FAL client is synchronous, run in executor
            # This method needs the generation data to get the model endpoint
            # But we don't have it here, so we'll return None
            # The calling function should handle this case
            return None
            return getattr(status, 'queue_position', None)
        except:
            return None
    
    def _estimate_generation_time(self, model_type: FALModelType) -> int:
        """
        Estimate generation time in seconds.
        """
        estimates = {
            FALModelType.IMAGE: 30,
            FALModelType.VIDEO: 120,
            FALModelType.AUDIO: 60
        }
        return estimates.get(model_type, 60)
    
    def _estimate_remaining_time(self, queue_position: Optional[int]) -> int:
        """
        Estimate remaining time based on queue position.
        """
        if not queue_position:
            return 60
        
        # Assume 30 seconds per position
        return queue_position * 30
    
    def _extract_output_urls(self, result: Dict[str, Any]) -> List[str]:
        """
        Extract output URLs from FAL result.
        """
        output_urls = []
        
        if "images" in result:
            output_urls = [img["url"] for img in result["images"]]
        elif "video" in result:
            output_urls = [result["video"]["url"]]
        elif "image" in result:
            output_urls = [result["image"]["url"]]
            
        return output_urls
    
    async def _update_database_record(self, generation_id: str, data: Dict[str, Any]):
        """
        Update database record for generation.
        """
        try:
            # This would update your Supabase database
            # Implementation depends on your database schema
            pass
        except Exception as e:
            logger.error(f"Failed to update database: {e}")
    
    async def get_user_generations(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get recent generations for a user.
        
        Args:
            user_id: User ID
            limit: Maximum number of generations to return
            
        Returns:
            List of generation records
        """
        try:
            # Get generation IDs for user
            if not self.redis:
                return []
                
            generation_ids = self.redis.lrange(f"user_generations:{user_id}", 0, limit - 1)
            
            generations = []
            for gen_id in generation_ids:
                gen_data = self.redis.get(f"generation:{gen_id}") if self.redis else None
                if gen_data:
                    generations.append(json.loads(gen_data))
            
            return generations
            
        except Exception as e:
            logger.error(f"Failed to get user generations: {e}")
            return []
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """
        Get system metrics for monitoring.
        
        Returns:
            Dict with system metrics
        """
        try:
            # Count active generations by status
            if not self.redis:
                return {
                    "active_generations": len(self.active_generations),
                    "status_counts": {},
                    "cache_entries": 0,
                    "redis_connections": None,
                    "semaphore_available": self.semaphore._value,
                    "timestamp": datetime.now().isoformat()
                }
                
            all_keys = self.redis.keys("generation:*")
            
            status_counts = {
                QueueStatus.QUEUED: 0,
                QueueStatus.PROCESSING: 0,
                QueueStatus.COMPLETED: 0,
                QueueStatus.FAILED: 0
            }
            
            for key in all_keys:
                data = self.redis.get(key) if self.redis else None
                if data:
                    gen_data = json.loads(data)
                    status = gen_data.get("status")
                    if status in status_counts:
                        status_counts[status] += 1
            
            # Get cache stats
            cache_keys = self.redis.keys("cache:*") if self.redis else []
            
            return {
                "active_generations": len(self.active_generations),
                "status_counts": status_counts,
                "cache_entries": len(cache_keys),
                "redis_connections": self.redis_pool.connection_kwargs,
                "semaphore_available": self.semaphore._value,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return {}


# Global service instance
async_fal_service = AsyncFALService()