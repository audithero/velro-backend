"""
FAL.ai integration service for AI generation.
Following CLAUDE.md: Service layer for business logic.
"""
import asyncio
import logging
from typing import Dict, Any, Optional, List
from uuid import UUID
import time
import os

import fal_client

from config import settings
from models.fal_config import get_model_config, validate_model_parameters, FALModelType
from models.generation import GenerationStatus

logger = logging.getLogger(__name__)


class FALService:
    """Service for FAL.ai API integration."""
    
    def __init__(self):
        # Configure FAL client
        # CRITICAL FIX: FAL client requires environment variable, not api_key attribute
        if settings.fal_key:
            # Set environment variable for FAL client
            os.environ['FAL_KEY'] = settings.fal_key
            logger.info("FAL_KEY environment variable set for FAL client")
        else:
            logger.warning("FAL_KEY not configured - FAL API calls will fail")
        
    async def create_generation(
        self,
        model_id: str,
        prompt: str,
        negative_prompt: Optional[str] = None,
        reference_image_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new generation using FAL.ai API (synchronous call in async wrapper).
        
        Args:
            model_id: FAL.ai model identifier
            prompt: Text prompt for generation
            negative_prompt: Optional negative prompt
            reference_image_url: Optional reference image URL
            parameters: Additional model-specific parameters
            
        Returns:
            Generation result with output URLs and metadata
        """
        try:
            # Get model configuration
            model_config = get_model_config(model_id)
            
            # Prepare generation parameters
            generation_params = {
                "prompt": prompt
            }
            
            # Add negative prompt if provided
            if negative_prompt:
                generation_params["negative_prompt"] = negative_prompt
                
            # Add reference image for supported models
            if reference_image_url and "image" in model_config.parameters:
                generation_params["image"] = reference_image_url
            elif reference_image_url and "first_frame_image" in model_config.parameters:
                generation_params["first_frame_image"] = reference_image_url
                
            # Add custom parameters
            if parameters:
                generation_params.update(parameters)
                
            # Validate parameters against model configuration
            validated_params = validate_model_parameters(model_id, generation_params)
            
            logger.info(f"Starting FAL.ai generation with model {model_id}")
            logger.debug(f"Generation parameters: {validated_params}")
            
            # Run generation synchronously using fal_client.run
            # This is wrapped in asyncio.to_thread to make it async-compatible
            start_time = time.time()
            
            result = await asyncio.to_thread(
                fal_client.run,
                model_config.endpoint,
                arguments=validated_params
            )
            
            generation_time = time.time() - start_time
            
            # Extract output URLs
            output_urls = []
            if "images" in result:
                output_urls = [img["url"] for img in result["images"]]
            elif "video" in result:
                output_urls = [result["video"]["url"]]
            elif "image" in result:
                output_urls = [result["image"]["url"]]
            
            logger.info(f"FAL.ai generation completed in {generation_time:.2f}s")
            
            return {
                "status": GenerationStatus.COMPLETED,
                "output_urls": output_urls,
                "metadata": {
                    "generation_time": generation_time,
                    "model_id": model_id,
                    "endpoint": model_config.endpoint,
                    "fal_result": result
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to create FAL.ai generation: {e}")
            return {
                "status": GenerationStatus.FAILED,
                "error_message": str(e),
                "output_urls": [],
                "metadata": {}
            }
    
    async def check_generation_status(self, request_id: str) -> Dict[str, Any]:
        """
        Check the status of a FAL.ai generation.
        
        Note: Since we're using synchronous API, this is not needed
        but kept for interface compatibility.
        
        Args:
            request_id: FAL.ai request ID
            
        Returns:
            Status information
        """
        return {
            "status": GenerationStatus.COMPLETED,
            "request_id": request_id
        }
    
    async def get_generation_result(self, request_id: str) -> Dict[str, Any]:
        """
        Get the result of a completed FAL.ai generation.
        
        Note: Since we're using synchronous API, this is not needed
        but kept for interface compatibility.
        
        Args:
            request_id: FAL.ai request ID
            
        Returns:
            Generation result
        """
        return {
            "status": GenerationStatus.COMPLETED,
            "output_urls": [],
            "metadata": {}
        }
    
    async def cancel_generation(self, request_id: str) -> bool:
        """
        Cancel a FAL.ai generation.
        
        Note: Since we're using synchronous API, cancellation is not possible
        but kept for interface compatibility.
        
        Args:
            request_id: FAL.ai request ID
            
        Returns:
            Success status
        """
        logger.warning(f"Cannot cancel generation {request_id} - using synchronous API")
        return False
    
    def _get_estimated_time(self, model_type: FALModelType) -> int:
        """Get estimated generation time in seconds based on model type."""
        estimates = {
            FALModelType.IMAGE: 30,
            FALModelType.VIDEO: 120,
            FALModelType.AUDIO: 60
        }
        return estimates.get(model_type, 60)

    def get_supported_models(self) -> List[Dict[str, Any]]:
        """
        Get list of all supported FAL.ai models with their configurations.
        
        Returns:
            List of model dictionaries with metadata
        """
        try:
            from models.fal_config import get_all_models
            
            models = []
            registry = get_all_models()
            
            for model_id, config in registry.items():
                model_info = {
                    "model_id": model_id,
                    "name": model_id.split('/')[-1].replace('-', ' ').title(),
                    "type": config.ai_model_type.value,  # CRITICAL FIX: Use ai_model_type instead of model_type
                    "credits": config.credits,
                    "max_resolution": config.max_resolution,
                    "supported_formats": config.supported_formats,
                    "description": config.description,
                    "endpoint": config.endpoint,
                    "parameters": config.parameters,
                    "example_params": config.example_params
                }
                models.append(model_info)
            
            # Sort by type and then by credits (lower cost first)
            models.sort(key=lambda x: (x["type"], x["credits"]))
            
            logger.info(f"Retrieved {len(models)} supported FAL.ai models")
            return models
            
        except Exception as e:
            logger.error(f"Failed to get supported models: {e}")
            return []


# Global service instance
fal_service = FALService()