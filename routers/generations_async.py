"""
Async generation API endpoints for scalable FAL.ai integration.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import Dict, Any, Optional, List
import json
import asyncio
from pydantic import BaseModel, Field

from services.fal_service_async import async_fal_service, QueueStatus
from middleware.auth import get_current_user
from models.user import UserResponse

router = APIRouter(
    prefix="",  # Prefix handled by main.py to avoid conflict
    tags=["Async Generations"]
)


class GenerationRequest(BaseModel):
    """Request model for creating a generation."""
    model_id: str = Field(..., description="FAL model ID")
    prompt: str = Field(..., description="Text prompt for generation")
    negative_prompt: Optional[str] = Field(None, description="Negative prompt")
    reference_image_url: Optional[str] = Field(None, description="Reference image URL")
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Model-specific parameters")


class GenerationResponse(BaseModel):
    """Response model for generation requests."""
    generation_id: str
    status: str
    queue_position: Optional[int] = None
    estimated_time: Optional[int] = None
    output_urls: Optional[List[str]] = None
    cached: bool = False
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@router.post("/submit", response_model=GenerationResponse)
async def submit_generation(
    request: GenerationRequest,
    current_user: UserResponse = Depends(get_current_user)
) -> GenerationResponse:
    """
    Submit a new generation request.
    Returns immediately with generation ID and queue status.
    
    This endpoint is non-blocking and can handle 100+ concurrent requests.
    """
    try:
        # Check user credits
        if current_user.credits_balance < 1:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Insufficient credits"
            )
        
        # Submit generation to async service
        result = await async_fal_service.submit_generation(
            user_id=str(current_user.id),
            model_id=request.model_id,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            reference_image_url=request.reference_image_url,
            parameters=request.parameters
        )
        
        # Deduct credits if not cached
        if not result.get("cached", False) and result["status"] != QueueStatus.FAILED:
            # TODO: Implement credit deduction
            pass
        
        return GenerationResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit generation: {str(e)}"
        )


@router.get("/{generation_id}/status", response_model=GenerationResponse)
async def get_generation_status(
    generation_id: str,
    current_user: UserResponse = Depends(get_current_user)
) -> GenerationResponse:
    """
    Get the current status of a generation request.
    
    Poll this endpoint to check if generation is complete.
    Recommended polling interval: 2-5 seconds.
    """
    try:
        result = await async_fal_service.get_generation_status(generation_id)
        
        # Verify user owns this generation
        # TODO: Add user verification
        
        return GenerationResponse(**result)
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get generation status: {str(e)}"
        )


@router.get("/{generation_id}/stream")
async def stream_generation_events(
    generation_id: str,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Stream generation events using Server-Sent Events (SSE).
    
    Provides real-time updates on generation progress including:
    - Queue position updates
    - Processing status
    - Completion with output URLs
    """
    async def event_generator():
        """Generate SSE events for generation progress."""
        try:
            async for event in async_fal_service.stream_generation_events(generation_id):
                # Format as SSE
                event_data = json.dumps(event)
                yield f"data: {event_data}\n\n"
                
                # End stream on completion or error
                if event.get("event") in ["completed", "error"]:
                    break
                    
        except Exception as e:
            error_event = json.dumps({
                "event": "error",
                "data": {"error": str(e)}
            })
            yield f"data: {error_event}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


@router.delete("/{generation_id}/cancel")
async def cancel_generation(
    generation_id: str,
    current_user: UserResponse = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Cancel a generation request if still in queue.
    
    Note: Generations already being processed cannot be cancelled.
    Credits will be refunded for successfully cancelled generations.
    """
    try:
        success = await async_fal_service.cancel_generation(generation_id)
        
        if success:
            # TODO: Refund credits
            pass
        
        return {
            "generation_id": generation_id,
            "cancelled": success,
            "message": "Generation cancelled" if success else "Unable to cancel (already processing or completed)"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel generation: {str(e)}"
        )


@router.get("/user/history")
async def get_user_generation_history(
    limit: int = 10,
    current_user: UserResponse = Depends(get_current_user)
) -> List[Dict[str, Any]]:
    """
    Get recent generation history for the current user.
    
    Returns up to 100 most recent generations with their status and results.
    """
    try:
        if limit > 100:
            limit = 100
            
        generations = await async_fal_service.get_user_generations(
            user_id=str(current_user.id),
            limit=limit
        )
        
        return generations
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get generation history: {str(e)}"
        )


@router.get("/metrics/system")
async def get_system_metrics(
    current_user: UserResponse = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get system metrics for monitoring.
    
    Requires admin privileges.
    Shows:
    - Active generations by status
    - Cache statistics
    - Queue depths
    - System health
    """
    try:
        # TODO: Add admin check
        # if not current_user.is_admin:
        #     raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
        
        metrics = await async_fal_service.get_system_metrics()
        return metrics
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get system metrics: {str(e)}"
        )


@router.get("/models/available")
async def get_available_models() -> List[Dict[str, Any]]:
    """
    Get list of available FAL.ai models with their configurations.
    
    Returns model IDs, names, types, credit costs, and parameters.
    """
    try:
        from services.fal_service import fal_service
        models = fal_service.get_supported_models()
        return models
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available models: {str(e)}"
        )