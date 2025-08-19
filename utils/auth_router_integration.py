"""
Practical Integration Example: Updating Generations Router
Shows how to integrate the comprehensive auth system into existing routers.
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from middleware.auth import get_current_user
from models.user import UserResponse
from models.generation import GenerationResponse, GenerationListResponse

# Import the new auth system
from utils.auth_system import (
    authorize_generation_access, handle_auth_error, 
    auth_system, AuthSystemConfig
)
from utils.exceptions import GenerationAccessDeniedError, UUIDAuthorizationError
from utils.auth_logger import log_generation_access_attempt, AuthLogMetrics
from utils.circuit_breaker import CircuitBreakerError

logger = logging.getLogger(__name__)

# Updated generations router with comprehensive auth
enhanced_generations_router = APIRouter(tags=["generations"], prefix="/api/v1/generations")


@enhanced_generations_router.get("/{generation_id}", response_model=GenerationResponse)
async def get_generation_enhanced(
    generation_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get a specific generation with comprehensive authorization and error handling.
    
    This replaces the basic ownership check with the full auth system:
    - UUID validation
    - Ownership verification with database circuit breaker
    - Comprehensive error handling and logging
    - Security monitoring
    - Performance tracking
    """
    correlation_id = getattr(request.state, 'request_id', 'unknown')
    
    logger.info(
        f"🔍 [GENERATION-API] Get generation request: {generation_id}",
        extra={
            'user_id': str(current_user.id),
            'generation_id': generation_id,
            'correlation_id': correlation_id
        }
    )
    
    try:
        # Use comprehensive authorization system
        auth_result = await authorize_generation_access(
            user_id=str(current_user.id),
            generation_id=generation_id,
            action="read",
            request=request
        )
        
        # Log successful authorization
        logger.info(
            f"✅ [GENERATION-API] Generation access authorized",
            extra={
                'user_id': str(current_user.id),
                'generation_id': generation_id,
                'processing_time_ms': auth_result.get('processing_time_ms'),
                'correlation_id': correlation_id
            }
        )
        
        # Proceed with generation retrieval (your existing business logic)
        try:
            # Import generation service
            from services.generation_service import generation_service
            
            # Get the generation data
            generation = await generation_service.get_generation(
                generation_id, 
                str(current_user.id)
            )
            
            if not generation:
                # This shouldn't happen after auth check, but safety first
                raise GenerationAccessDeniedError(
                    generation_id=generation_id,
                    user_id=str(current_user.id),
                    details={'reason': 'Generation not found after auth check'}
                )
            
            return generation
            
        except Exception as service_error:
            logger.error(
                f"❌ [GENERATION-API] Service error after auth success: {service_error}",
                extra={
                    'user_id': str(current_user.id),
                    'generation_id': generation_id,
                    'correlation_id': correlation_id,
                    'service_error': str(service_error)
                }
            )
            
            # Re-raise as HTTP exception for consistency
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to retrieve generation data"
            )
    
    except GenerationAccessDeniedError as auth_error:
        # Comprehensive error handling with user-friendly messages
        logger.warning(
            f"🚫 [GENERATION-API] Generation access denied: {auth_error.message}",
            extra={
                'user_id': str(current_user.id),
                'generation_id': generation_id,
                'error_code': auth_error.error_code,
                'correlation_id': correlation_id
            }
        )
        
        # Use centralized error handler
        return await handle_auth_error(
            auth_error,
            user_id=str(current_user.id),
            resource_id=generation_id,
            resource_type="generation",
            request=request
        )
    
    except CircuitBreakerError as cb_error:
        # Handle circuit breaker errors gracefully
        logger.error(
            f"🔥 [GENERATION-API] Circuit breaker error: {cb_error}",
            extra={
                'user_id': str(current_user.id),
                'generation_id': generation_id,
                'circuit_name': cb_error.circuit_name,
                'circuit_state': cb_error.state.value,
                'correlation_id': correlation_id
            }
        )
        
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                'error': True,
                'message': 'Authorization service temporarily unavailable. Please try again in a moment.',
                'error_type': 'service_unavailable',
                'correlation_id': correlation_id,
                'retry_after': 60
            }
        )
    
    except Exception as unexpected_error:
        # Handle any unexpected errors
        logger.error(
            f"❌ [GENERATION-API] Unexpected error: {unexpected_error}",
            extra={
                'user_id': str(current_user.id),
                'generation_id': generation_id,
                'error_type': type(unexpected_error).__name__,
                'correlation_id': correlation_id
            }
        )
        
        # Use centralized error handler for consistency
        return await handle_auth_error(
            unexpected_error,
            user_id=str(current_user.id),
            resource_id=generation_id,
            resource_type="generation", 
            request=request
        )