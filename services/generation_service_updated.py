"""
Updated Generation Service with Kong API Gateway Integration
Routes external AI API calls through Kong proxy for monitoring and fallback.
Maintains compatibility with existing FastAPI architecture.
Date: August 5, 2025
Author: Kong Integration Specialist
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import HttpUrl

from database import get_database
from repositories.generation_repository import GenerationRepository
from services.kong_proxy_service import kong_proxy_service
from services.kong_transition_manager import kong_transition_manager
from services.fal_service import fal_service  # Fallback service
from services.storage_service import storage_service
from services.credit_transaction_service import credit_transaction_service, CreditTransaction
from models.generation import (
    GenerationCreate, 
    GenerationResponse, 
    GenerationStatus,
    GenerationType
)
from models.fal_config import get_model_config
from models.credit import TransactionType
from utils.logging_config import perf_logger, log_performance
from utils.performance_monitor import performance_monitor
from utils.cache_manager import cached, CacheLevel

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


class GenerationServiceKongIntegrated:
    """
    Enhanced Generation service with Kong API Gateway integration.
    
    Routes external API calls through Kong proxy while maintaining
    compatibility with existing FastAPI architecture and fallback mechanisms.
    """
    
    def __init__(self):
        self.db = None
        self.generation_repo = None
        
        # Circuit breaker for Kong proxy service
        self._circuit_breaker_state = "closed"  # closed, open, half-open
        self._circuit_breaker_failures = 0
        self._circuit_breaker_last_failure = 0
        self._circuit_breaker_timeout = 30  # 30 seconds
        self._max_circuit_failures = 5
        
        # Performance optimization settings
        self._enable_caching = True
        self._cache_ttl = 300  # 5 minutes default
        
        # Kong integration settings - now managed by transition manager
        self._kong_enabled = True
        self._direct_fal_fallback = True
        
        # Kong transition manager integration
        self._transition_manager = kong_transition_manager
        
        logger.info("🚀 Generation Service initialized with Kong API Gateway integration")
        logger.info(f"🔗 Kong Proxy: {'Enabled' if self._kong_enabled else 'Disabled'}")
        logger.info(f"🔙 Direct FAL Fallback: {'Enabled' if self._direct_fal_fallback else 'Disabled'}")
    
    async def _get_repositories(self):
        """Initialize repositories if not already done."""
        if self.db is None:
            try:
                logger.info("Initializing database connection for GenerationService")
                self.db = await get_database()
                
                if not self.db.is_available():
                    raise ConnectionError("Database is not available")
                
                self.generation_repo = GenerationRepository(self.db)
                logger.info("Successfully initialized GenerationService repositories")
                
            except Exception as e:
                logger.error(f"Failed to initialize GenerationService repositories: {e}")
                raise RuntimeError(f"Service initialization failed: {str(e)}")
    
    def _can_execute_generation(self) -> bool:
        """Check if generation can be executed based on circuit breaker state."""
        current_time = time.time()
        
        if self._circuit_breaker_state == "closed":
            return True
        elif self._circuit_breaker_state == "open":
            if current_time - self._circuit_breaker_last_failure >= self._circuit_breaker_timeout:
                self._circuit_breaker_state = "half-open"
                logger.info("🔄 Circuit breaker half-open - testing recovery")
                return True
            return False
        else:  # half-open
            return True
    
    def _record_circuit_breaker_success(self):
        """Record successful operation for circuit breaker."""
        self._circuit_breaker_failures = 0
        if self._circuit_breaker_state == "half-open":
            self._circuit_breaker_state = "closed"
            logger.info("✅ Circuit breaker closed - operations restored")
    
    def _record_circuit_breaker_failure(self):
        """Record failed operation for circuit breaker."""
        self._circuit_breaker_failures += 1
        self._circuit_breaker_last_failure = time.time()
        
        if self._circuit_breaker_failures >= self._max_circuit_failures:
            self._circuit_breaker_state = "open"
            logger.warning(f"🚨 Circuit breaker opened after {self._circuit_breaker_failures} failures")
    
    async def create_generation(
        self,
        generation_data: GenerationCreate,
        user_id: UUID,
        auth_token: str,
        project_id: Optional[UUID] = None
    ) -> GenerationResponse:
        """
        Create a new AI generation using Kong API Gateway proxy.
        
        Enhanced version that routes through Kong for monitoring and fallback,
        while maintaining compatibility with existing generation workflow.
        """
        await self._get_repositories()
        
        # Check circuit breaker
        if not self._can_execute_generation():
            raise CircuitBreakerError("Generation service circuit breaker is open")
        
        generation_id = None
        start_time = time.time()
        
        try:
            logger.info(f"🚀 Starting Kong-proxied generation for user {user_id}")
            logger.info(f"📋 Model: {generation_data.model_id}")
            logger.info(f"🎯 Kong Proxy: {'Enabled' if self._kong_enabled else 'Disabled'}")
            
            # Get model configuration for credit calculation
            model_config = get_model_config(generation_data.model_id)
            credits_required = model_config.credits
            
            # Validate user has sufficient credits
            credit_check = await credit_transaction_service.check_sufficient_credits(
                user_id, credits_required
            )
            if not credit_check["sufficient"]:
                raise ValueError(f"Insufficient credits. Required: {credits_required}, Available: {credit_check['available']}")
            
            # Create generation record
            generation_record = await self.generation_repo.create_generation(
                user_id=user_id,
                project_id=project_id,
                model_id=generation_data.model_id,
                generation_type=GenerationType.from_model_type(model_config.ai_model_type),
                prompt=generation_data.prompt,
                negative_prompt=generation_data.negative_prompt,
                reference_image_url=generation_data.reference_image_url,
                parameters=generation_data.parameters or {},
                credits_required=credits_required,
                status=GenerationStatus.PROCESSING
            )
            
            generation_id = generation_record.id
            logger.info(f"📝 Created generation record: {generation_id}")
            
            # Deduct credits (atomic transaction)
            await credit_transaction_service.create_transaction(
                CreditTransaction(
                    user_id=user_id,
                    generation_id=generation_id,
                    amount=-credits_required,
                    transaction_type=TransactionType.GENERATION,
                    metadata={
                        "model_id": generation_data.model_id,
                        "generation_type": model_config.ai_model_type.value,
                        "kong_proxy_enabled": self._kong_enabled
                    }
                )
            )
            
            logger.info(f"💳 Deducted {credits_required} credits for generation")
            
            # Execute AI generation through Kong proxy or direct fallback
            generation_result = await self._execute_ai_generation(
                model_id=generation_data.model_id,
                prompt=generation_data.prompt,
                user_id=user_id,
                auth_token=auth_token,
                negative_prompt=generation_data.negative_prompt,
                reference_image_url=generation_data.reference_image_url,
                parameters=generation_data.parameters
            )
            
            # Process generation result
            if generation_result["status"] == GenerationStatus.COMPLETED:
                logger.info(f"✅ Generation completed successfully")
                
                # Process and store output files
                processed_outputs = await self._process_generation_outputs(
                    generation_id=generation_id,
                    user_id=user_id,
                    output_urls=generation_result["output_urls"],
                    model_config=model_config
                )
                
                # Update generation record with results
                await self.generation_repo.update_generation(
                    generation_id=generation_id,
                    status=GenerationStatus.COMPLETED,
                    output_urls=processed_outputs["output_urls"],
                    metadata={
                        **generation_result.get("metadata", {}),
                        "processed_outputs": processed_outputs,
                        "total_processing_time": time.time() - start_time
                    }
                )
                
                # Record circuit breaker success
                self._record_circuit_breaker_success()
                
                # Get updated generation record
                final_generation = await self.generation_repo.get_generation_by_id(generation_id)
                
                return GenerationResponse.from_orm(final_generation)
                
            else:
                # Handle generation failure
                logger.error(f"❌ Generation failed: {generation_result.get('error_message')}")
                
                # Update generation record with failure
                await self.generation_repo.update_generation(
                    generation_id=generation_id,
                    status=GenerationStatus.FAILED,
                    metadata={
                        **generation_result.get("metadata", {}),
                        "error_message": generation_result.get("error_message"),
                        "failure_time": time.time() - start_time
                    }
                )
                
                # Refund credits for failed generation
                await credit_transaction_service.create_transaction(
                    CreditTransaction(
                        user_id=user_id,
                        generation_id=generation_id,
                        amount=credits_required,  # Positive amount for refund
                        transaction_type=TransactionType.REFUND,
                        metadata={
                            "reason": "Generation failed",
                            "original_error": generation_result.get("error_message"),
                            "kong_proxy_used": generation_result.get("metadata", {}).get("kong_proxy_used", False)
                        }
                    )
                )
                
                logger.info(f"💰 Refunded {credits_required} credits for failed generation")
                
                # Record circuit breaker failure
                self._record_circuit_breaker_failure()
                
                raise RuntimeError(f"Generation failed: {generation_result.get('error_message')}")
                
        except Exception as e:
            logger.error(f"❌ Generation service error: {e}")
            
            # Record circuit breaker failure
            self._record_circuit_breaker_failure()
            
            # Clean up and refund if generation record was created
            if generation_id:
                try:
                    await self.generation_repo.update_generation(
                        generation_id=generation_id,
                        status=GenerationStatus.FAILED,
                        metadata={
                            "error_message": str(e),
                            "failure_type": "service_error",
                            "total_processing_time": time.time() - start_time
                        }
                    )
                    
                    # Refund credits
                    await credit_transaction_service.create_transaction(
                        CreditTransaction(
                            user_id=user_id,
                            generation_id=generation_id,
                            amount=credits_required,
                            transaction_type=TransactionType.REFUND,
                            metadata={
                                "reason": "Service error",
                                "error": str(e)
                            }
                        )
                    )
                    
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up failed generation: {cleanup_error}")
            
            raise
    
    async def _execute_ai_generation(
        self,
        model_id: str,
        prompt: str,
        user_id: UUID,
        auth_token: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Execute AI generation through Kong proxy with progressive rollout and fallback.
        Uses Kong transition manager to determine routing strategy.
        """
        start_time = time.time()
        
        # Check if Kong should be used based on transition manager
        use_kong, routing_reason = await self._transition_manager.should_use_kong(user_id)
        
        logger.info(f"🎯 Routing decision: {'Kong' if use_kong else 'Direct FAL.ai'} (reason: {routing_reason})")
        
        if self._kong_enabled and use_kong:
            try:
                logger.info(f"🚀 Attempting Kong proxy generation for {model_id}")
                
                # Use Kong proxy service
                result = await kong_proxy_service.create_generation(
                    model_id=model_id,
                    prompt=prompt,
                    user_id=user_id,
                    auth_token=auth_token,
                    negative_prompt=negative_prompt,
                    reference_image_url=reference_image_url,
                    parameters=parameters
                )
                
                # Record successful Kong request
                response_time_ms = int((time.time() - start_time) * 1000)
                await self._transition_manager.record_kong_request_result(
                    success=True,
                    response_time_ms=response_time_ms,
                    status_code=200
                )
                
                # Add routing information to metadata
                if "metadata" not in result:
                    result["metadata"] = {}
                result["metadata"]["kong_routing"] = {
                    "used_kong": True,
                    "routing_reason": routing_reason,
                    "transition_state": self._transition_manager.current_state.value,
                    "traffic_percentage": self._transition_manager.traffic_percentage
                }
                
                logger.info(f"✅ Kong proxy generation successful (routing: {routing_reason})")
                return result
                    
            except Exception as kong_error:
                # Record failed Kong request
                response_time_ms = int((time.time() - start_time) * 1000)
                error_status_code = getattr(kong_error, 'status_code', 500)
                
                await self._transition_manager.record_kong_request_result(
                    success=False,
                    response_time_ms=response_time_ms,
                    status_code=error_status_code,
                    error_message=str(kong_error)
                )
                
                logger.warning(f"⚠️ Kong proxy failed: {kong_error}")
                
                if self._direct_fal_fallback:
                    logger.info(f"🔄 Falling back to direct FAL.ai service")
                    fallback_result = await self._direct_fal_generation(
                        model_id, prompt, negative_prompt, reference_image_url, parameters
                    )
                    
                    # Add fallback information to metadata
                    if "metadata" not in fallback_result:
                        fallback_result["metadata"] = {}
                    fallback_result["metadata"]["kong_routing"] = {
                        "used_kong": False,
                        "routing_reason": "kong_fallback_after_error",
                        "kong_error": str(kong_error),
                        "transition_state": self._transition_manager.current_state.value
                    }
                    
                    return fallback_result
                else:
                    raise kong_error
        else:
            # Use direct FAL.ai (Kong disabled or transition manager says no)
            logger.info(f"🔄 Using direct FAL.ai (reason: {routing_reason})")
            result = await self._direct_fal_generation(
                model_id, prompt, negative_prompt, reference_image_url, parameters
            )
            
            # Add routing information to metadata
            if "metadata" not in result:
                result["metadata"] = {}
            result["metadata"]["kong_routing"] = {
                "used_kong": False,
                "routing_reason": routing_reason,
                "transition_state": self._transition_manager.current_state.value,
                "traffic_percentage": self._transition_manager.traffic_percentage
            }
            
            return result
    
    async def _direct_fal_generation(
        self,
        model_id: str,
        prompt: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Direct FAL.ai generation fallback."""
        try:
            result = await fal_service.create_generation(
                model_id=model_id,
                prompt=prompt,
                negative_prompt=negative_prompt,
                reference_image_url=reference_image_url,
                parameters=parameters
            )
            
            # Add fallback metadata
            if "metadata" not in result:
                result["metadata"] = {}
            result["metadata"]["kong_proxy_used"] = False
            result["metadata"]["fallback_mode"] = "direct_fal"
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Direct FAL.ai generation failed: {e}")
            return {
                "status": GenerationStatus.FAILED,
                "error_message": f"Both Kong proxy and direct FAL.ai failed: {str(e)}",
                "output_urls": [],
                "metadata": {"fallback_mode": "failed"}
            }
    
    async def _process_generation_outputs(
        self,
        generation_id: UUID,
        user_id: UUID,
        output_urls: List[str],
        model_config
    ) -> Dict[str, Any]:
        """Process and store generation outputs with enhanced metadata."""
        try:
            processed_outputs = {
                "output_urls": [],
                "thumbnail_urls": [],
                "file_metadata": [],
                "total_files": len(output_urls)
            }
            
            for i, output_url in enumerate(output_urls):
                try:
                    # Download and store the generated file
                    stored_file = await storage_service.store_generation_output(
                        generation_id=generation_id,
                        user_id=user_id,
                        source_url=output_url,
                        file_index=i,
                        model_type=model_config.ai_model_type
                    )
                    
                    processed_outputs["output_urls"].append(stored_file["file_url"])
                    
                    # Generate thumbnail for images
                    if stored_file.get("thumbnail_url"):
                        processed_outputs["thumbnail_urls"].append(stored_file["thumbnail_url"])
                    
                    processed_outputs["file_metadata"].append({
                        "index": i,
                        "original_url": output_url,
                        "stored_url": stored_file["file_url"],
                        "file_size": stored_file.get("file_size"),
                        "format": stored_file.get("format"),
                        "dimensions": stored_file.get("dimensions")
                    })
                    
                except Exception as file_error:
                    logger.error(f"Failed to process output file {i}: {file_error}")
                    # Still include original URL as fallback
                    processed_outputs["output_urls"].append(output_url)
                    processed_outputs["file_metadata"].append({
                        "index": i,
                        "original_url": output_url,
                        "processing_error": str(file_error)
                    })
            
            return processed_outputs
            
        except Exception as e:
            logger.error(f"Failed to process generation outputs: {e}")
            # Return original URLs as fallback
            return {
                "output_urls": output_urls,
                "processing_error": str(e),
                "fallback_mode": True
            }
    
    async def get_generation_by_id(
        self,
        generation_id: UUID,
        user_id: UUID
    ) -> Optional[GenerationResponse]:
        """Get generation by ID with Kong metrics integration."""
        await self._get_repositories()
        
        generation = await self.generation_repo.get_generation_by_id(generation_id)
        
        if not generation or generation.user_id != user_id:
            return None
        
        # Add Kong metrics if available
        if generation.metadata and "kong_request_id" in generation.metadata:
            try:
                # Get Kong metrics for this generation
                kong_metrics = await kong_proxy_service.get_api_metrics_summary(
                    user_id=user_id,
                    hours=24
                )
                generation.metadata["kong_metrics"] = kong_metrics
            except Exception as e:
                logger.warning(f"Failed to fetch Kong metrics: {e}")
        
        return GenerationResponse.from_orm(generation)
    
    async def list_user_generations(
        self,
        user_id: UUID,
        project_id: Optional[UUID] = None,
        limit: int = 50,
        offset: int = 0,
        include_kong_metrics: bool = False
    ) -> List[GenerationResponse]:
        """List user generations with optional Kong metrics."""
        await self._get_repositories()
        
        generations = await self.generation_repo.list_user_generations(
            user_id=user_id,
            project_id=project_id,
            limit=limit,
            offset=offset
        )
        
        generation_responses = [GenerationResponse.from_orm(gen) for gen in generations]
        
        # Add Kong metrics if requested
        if include_kong_metrics:
            try:
                user_metrics = await kong_proxy_service.get_api_metrics_summary(
                    user_id=user_id,
                    hours=24
                )
                
                # Add metrics to each generation response
                for response in generation_responses:
                    response.kong_metrics = user_metrics
                    
            except Exception as e:
                logger.warning(f"Failed to fetch Kong metrics for user {user_id}: {e}")
        
        return generation_responses
    
    async def get_service_health(self) -> Dict[str, Any]:
        """Get comprehensive service health including Kong transition status."""
        health_info = {
            "generation_service": {
                "status": "healthy",
                "circuit_breaker_state": self._circuit_breaker_state,
                "circuit_breaker_failures": self._circuit_breaker_failures,
                "kong_enabled": self._kong_enabled,
                "direct_fal_fallback": self._direct_fal_fallback
            }
        }
        
        # Add Kong transition status
        try:
            transition_status = await self._transition_manager.get_transition_status()
            health_info["kong_transition"] = transition_status
        except Exception as e:
            health_info["kong_transition"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        # Add Kong health if enabled
        if self._kong_enabled:
            try:
                kong_health = await kong_proxy_service.get_kong_health()
                health_info["kong_gateway"] = kong_health
            except Exception as e:
                health_info["kong_gateway"] = {
                    "status": "unhealthy",
                    "error": str(e)
                }
        
        # Add database health
        try:
            await self._get_repositories()
            health_info["database"] = {
                "status": "healthy" if self.db.is_available() else "unhealthy"
            }
        except Exception as e:
            health_info["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
        
        return health_info
    
    async def get_kong_transition_control(self) -> Dict[str, Any]:
        """Get Kong transition control interface for admin operations."""
        try:
            return await self._transition_manager.get_transition_status()
        except Exception as e:
            logger.error(f"Failed to get Kong transition status: {e}")
            return {"error": str(e)}
    
    async def advance_kong_rollout(self) -> Dict[str, Any]:
        """Advance Kong rollout to next stage."""
        try:
            advanced, reason = await self._transition_manager.advance_rollout()
            return {
                "success": advanced,
                "reason": reason,
                "new_state": self._transition_manager.current_state.value,
                "traffic_percentage": self._transition_manager.traffic_percentage,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to advance Kong rollout: {e}")
            return {"error": str(e), "success": False}
    
    async def rollback_kong(self) -> Dict[str, Any]:
        """Rollback Kong to previous stage."""
        try:
            rolled_back, reason = await self._transition_manager.rollback()
            return {
                "success": rolled_back,
                "reason": reason,
                "new_state": self._transition_manager.current_state.value,
                "traffic_percentage": self._transition_manager.traffic_percentage,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to rollback Kong: {e}")
            return {"error": str(e), "success": False}
    
    async def emergency_stop_kong(self) -> Dict[str, Any]:
        """Emergency stop Kong and fallback to direct FAL.ai."""
        try:
            result = await self._transition_manager.emergency_stop()
            logger.warning(f"🚨 Kong emergency stop executed: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to execute Kong emergency stop: {e}")
            return {"error": str(e)}


# Global service instance with Kong integration
generation_service = GenerationServiceKongIntegrated()