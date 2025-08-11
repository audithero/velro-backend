"""
Generation API endpoints with comprehensive rate limiting and security.
Following CLAUDE.md: Router layer for API endpoints.
"""
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, File, UploadFile, Form
from fastapi.security import HTTPBearer
import json

from middleware.auth import get_current_user, require_credits
from middleware.rate_limiting import limit, api_limit, generation_limit
from services.generation_service import generation_service
from services.fal_service import fal_service
from models.generation import (
    GenerationCreate,
    GenerationResponse, 
    GenerationListResponse,
    GenerationStatsResponse
)
from models.user import UserResponse

router = APIRouter(tags=["generations"])
security = HTTPBearer()


@router.post("", response_model=GenerationResponse)
@router.post("/", response_model=GenerationResponse)
@limit("10/minute")  # Strict rate limit for generation creation
async def create_generation(
    request: Request,
    model_id: str = Form(...),
    prompt: str = Form(...),
    negative_prompt: Optional[str] = Form(None),
    reference_image_url: Optional[str] = Form(None),
    parameters: Optional[str] = Form("{}"),
    project_id: Optional[str] = Form(None),
    reference_image: Optional[UploadFile] = File(None),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Create a new AI generation with optional reference image upload.
    
    Rate limit: 10 generations per minute per user to prevent abuse and manage costs.
    Supports both reference image URLs and direct file uploads.
    """
    try:
        # Parse parameters JSON
        try:
            parameters_dict = json.loads(parameters) if parameters != "{}" else {}
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid parameters JSON")
        
        # Create generation data object
        generation_data = GenerationCreate(
            model_id=model_id,
            prompt=prompt,
            negative_prompt=negative_prompt,
            reference_image_url=reference_image_url,
            parameters=parameters_dict,
            project_id=project_id
        )
        
        # Handle reference image file if provided
        reference_image_file = None
        reference_image_filename = None
        
        if reference_image:
            # Validate file size (max 20MB for reference images)
            max_size = 20 * 1024 * 1024  # 20MB
            reference_image_file = await reference_image.read()
            
            if len(reference_image_file) > max_size:
                raise HTTPException(
                    status_code=413,
                    detail=f"Reference image too large. Maximum size is {max_size} bytes"
                )
            
            # Validate content type
            if not reference_image.content_type or not reference_image.content_type.startswith('image/'):
                raise HTTPException(
                    status_code=400,
                    detail="Reference image must be an image file"
                )
            
            reference_image_filename = reference_image.filename
        
        # Check if user has sufficient credits
        from models.fal_config import get_model_config
        model_config = get_model_config(generation_data.model_id)
        
        # Check if user has sufficient credits
        if current_user.credits_balance < model_config.credits:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits. Required: {model_config.credits}, Available: {current_user.credits_balance}"
            )
        
        # Log generation attempt for monitoring
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.info(
            f"Generation requested by user {str(current_user.id)} from {client_ip}: "
            f"model={generation_data.model_id}, credits={model_config.credits}, "
            f"has_reference_file={reference_image is not None}"
        )
        
        # CRITICAL FIX: Extract auth token from request header for database operations
        auth_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ", 1)[1]
            logger.info(f"🔑 [GENERATION-API] Auth token extracted for user {current_user.id}: {auth_token[:20]}...")
        else:
            logger.error(f"❌ [GENERATION-API] No auth token found in request headers for user {current_user.id}")
            logger.error(f"❌ [GENERATION-API] Available headers: {list(request.headers.keys())}")
        
        # CRITICAL FIX: Enhanced error context and validation before calling generation service
        logger.info(f"🚀 [GENERATION-API] Attempting generation creation for user {current_user.id}")
        logger.info(f"🔍 [GENERATION-API] Model: {generation_data.model_id}, Cost: {model_config.credits}")
        logger.info(f"🔍 [GENERATION-API] Auth token available: {bool(auth_token)}")
        logger.info(f"🔍 [GENERATION-API] User balance: {current_user.credits_balance}")
        
        try:
            generation = await generation_service.create_generation(
                user_id=str(current_user.id),  # Convert UUID to string for JSON serialization
                generation_data=generation_data,
                reference_image_file=reference_image_file,
                reference_image_filename=reference_image_filename,
                auth_token=auth_token  # Pass JWT token for database operations
            )
            logger.info(f"✅ [GENERATION-API] Generation created successfully: {generation.id}")
            
        except ValueError as val_error:
            # User-facing validation errors (insufficient credits, auth issues)
            error_msg = str(val_error)
            logger.error(f"👤 [GENERATION-API] User validation error: {error_msg}")
            
            # Enhanced error messaging for common issues
            if "authentication expired" in error_msg.lower() or "refresh your session" in error_msg.lower():
                raise HTTPException(
                    status_code=401, 
                    detail="Your session has expired. Please refresh the page and log in again."
                )
            elif "insufficient credits" in error_msg.lower():
                raise HTTPException(
                    status_code=402,
                    detail=error_msg
                )
            elif "not found" in error_msg.lower():
                raise HTTPException(
                    status_code=404,
                    detail="User profile not found. Please contact support if this continues."
                )
            else:
                raise HTTPException(status_code=400, detail=error_msg)
                
        except RuntimeError as runtime_error:
            # System/service errors  
            error_msg = str(runtime_error)
            logger.error(f"⚙️ [GENERATION-API] System error during generation: {error_msg}")
            
            # Enhanced system error handling
            if "database" in error_msg.lower():
                raise HTTPException(
                    status_code=503,
                    detail="Database service temporarily unavailable. Please try again in a moment."
                )
            elif "circuit breaker" in error_msg.lower():
                raise HTTPException(
                    status_code=503,
                    detail="AI generation service is experiencing high load. Please try again in a few minutes."
                )
            elif "service initialization failed" in error_msg.lower():
                raise HTTPException(
                    status_code=503,
                    detail="Generation service temporarily unavailable. Please try again later."
                )
            else:
                raise HTTPException(
                    status_code=503,
                    detail="Generation service temporarily unavailable. Please try again later."
                )
        
        return generation
        
    except ValueError as e:
        # Log validation errors (user errors like insufficient credits)
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Generation validation error for user {str(current_user.id)}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        # Log system errors (service unavailable, etc.)
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Generation system error for user {str(current_user.id)}: {str(e)}")
        
        # Handle specific service unavailable cases
        error_msg = str(e)
        if "circuit breaker" in error_msg.lower():
            logger.error(f"🚨 [GEN-API] Circuit breaker triggered: {error_msg}")
            raise HTTPException(
                status_code=503, 
                detail="AI generation service is experiencing high load. Please try again in a few minutes."
            )
        elif "database" in error_msg.lower():
            logger.error(f"🚨 [GEN-API] Database unavailable: {error_msg}")
            raise HTTPException(
                status_code=503, 
                detail="Database service temporarily unavailable. Please try again later."
            )
        elif "storage" in error_msg.lower():
            logger.error(f"🚨 [GEN-API] Storage unavailable: {error_msg}")
            raise HTTPException(
                status_code=503, 
                detail="File storage service temporarily unavailable. Please try again later."
            )
        elif "ai generation service" in error_msg.lower():
            logger.error(f"🚨 [GEN-API] AI service unavailable: {error_msg}")
            raise HTTPException(
                status_code=503, 
                detail="AI generation service temporarily unavailable. Please try again later."
            )
        else:
            raise HTTPException(
                status_code=503, 
                detail="Service temporarily unavailable. Please try again later."
            )
    except Exception as e:
        # CRITICAL FIX: Comprehensive error handling to prevent ALL 500 errors
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        
        error_msg = str(e)
        error_type = type(e).__name__
        
        logger.error(f"❌ [GENERATION-API] Unexpected generation error for user {str(current_user.id)}: {error_msg}")
        logger.error(f"❌ [GENERATION-API] Exception type: {error_type}")
        logger.error(f"❌ [GENERATION-API] Traceback: {traceback.format_exc()}")
        
        # Enhanced error categorization to prevent 500 errors
        if "connection" in error_msg.lower() or "network" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="Network connectivity issue. Please check your connection and try again."
            )
        elif "permission" in error_msg.lower() or "unauthorized" in error_msg.lower():
            raise HTTPException(
                status_code=401,
                detail="Authentication issue detected. Please refresh the page and log in again."
            )
        elif "json" in error_msg.lower() or "parse" in error_msg.lower():
            raise HTTPException(
                status_code=400,
                detail="Invalid request format. Please check your input data and try again."
            )
        elif "memory" in error_msg.lower() or "resource" in error_msg.lower():
            raise HTTPException(
                status_code=503,
                detail="Server resources temporarily unavailable. Please try again with a smaller image or simpler request."
            )
        else:
            # Last resort: Always return service unavailable instead of 500
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable due to an unexpected issue. Our team has been notified. Please try again in a few minutes."
            )


@router.get("", response_model=List[GenerationResponse])
@router.get("/", response_model=List[GenerationResponse])
@limit("200/minute")  # Higher limit for list operations
async def list_generations(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    project_id: Optional[str] = Query(None),
    current_user: UserResponse = Depends(get_current_user)
):
    """
    List user's generations with optional project filter.
    
    Rate limit: 200 requests per minute for list operations.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Extract auth token from request header for database operations
        auth_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ", 1)[1]
            logger.info(f"🔑 [GENERATIONS-LIST] Auth token extracted for user {current_user.id}: {auth_token[:20]}...")
        else:
            logger.warning(f"⚠️ [GENERATIONS-LIST] No auth token found in request headers for user {current_user.id}")
        
        generations = await generation_service.list_user_generations(
            user_id=str(current_user.id),  # Convert UUID to string for JSON serialization
            project_id=project_id,
            limit=limit,
            offset=skip,
            auth_token=auth_token  # Pass auth token for database access
        )
        
        logger.info(f"✅ [GENERATIONS-LIST] Successfully listed {len(generations)} generations for user {current_user.id}")
        return generations
        
    except Exception as e:
        logger.error(f"❌ [GENERATIONS-LIST] Failed to list generations for user {str(current_user.id)}: {str(e)}")
        logger.error(f"❌ [GENERATIONS-LIST] Error type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [GENERATIONS-LIST] Traceback: {traceback.format_exc()}")
        
        # CRITICAL FIX: Prevent 500 errors in list endpoint
        error_msg = str(e).lower()
        if "authentication" in error_msg or "unauthorized" in error_msg:
            raise HTTPException(status_code=401, detail="Authentication expired. Please refresh the page and log in again.")
        elif "database" in error_msg or "connection" in error_msg:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable. Please try again in a moment.")
        else:
            raise HTTPException(status_code=503, detail="Generation list temporarily unavailable. Please try again later.")


@router.get("/stats/", response_model=GenerationStatsResponse)
@router.get("/stats", response_model=GenerationStatsResponse)  # CRITICAL FIX: Add route without trailing slash
@api_limit()  # Standard API rate limit
async def get_generation_stats(
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get generation statistics for the current user.
    
    Rate limit: Standard API limit (100/minute).
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # CRITICAL FIX: Extract auth token from request header for database operations
        auth_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ", 1)[1]
            logger.info(f"🔑 [STATS] Auth token extracted for user {current_user.id}: {auth_token[:20]}...")
        else:
            logger.warning(f"⚠️ [STATS] No auth token found in request headers for user {current_user.id}")
            logger.warning(f"⚠️ [STATS] Available headers: {list(request.headers.keys())}")
        
        # Pass auth token to service for proper database access
        stats = await generation_service.get_generation_stats(
            str(current_user.id),  # Convert UUID to string for JSON serialization
            auth_token=auth_token  # Pass JWT token for database operations
        )
        
        logger.info(f"✅ [STATS] Successfully retrieved stats for user {current_user.id}")
        return GenerationStatsResponse(**stats)
        
    except Exception as e:
        logger.error(f"❌ [STATS] Failed to get generation stats for user {str(current_user.id)}: {str(e)}")
        logger.error(f"❌ [STATS] Error type: {type(e).__name__}")
        import traceback
        logger.error(f"❌ [STATS] Traceback: {traceback.format_exc()}")
        
        # CRITICAL FIX: Prevent 500 errors in stats endpoint
        error_msg = str(e).lower()
        if "authentication" in error_msg or "unauthorized" in error_msg:
            raise HTTPException(status_code=401, detail="Authentication expired. Please refresh the page and log in again.")
        elif "database" in error_msg or "connection" in error_msg:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable. Please try again in a moment.")
        else:
            raise HTTPException(status_code=503, detail="Generation statistics temporarily unavailable. Please try again later.")


@router.get("/{generation_id}", response_model=GenerationResponse)
@limit("60/minute")  # Higher limit for status checks
async def get_generation(
    generation_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get a specific generation by ID.
    
    Rate limit: 60 requests per minute for individual generation access.
    """
    try:
        # Extract auth token from request header for database operations
        auth_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ", 1)[1]
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🔑 [GET-GENERATION] Auth token extracted for user {current_user.id}: {auth_token[:20]}...")
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"⚠️ [GET-GENERATION] No auth token found in request headers for user {current_user.id}")
        
        generation = await generation_service.get_generation(
            generation_id=generation_id,
            user_id=str(current_user.id),  # Convert UUID to string for JSON serialization
            auth_token=auth_token  # Pass auth token for database authentication
        )
        
        return generation
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get generation {generation_id} for user {str(current_user.id)}: {str(e)}")
        
        # CRITICAL FIX: Prevent 500 errors in get generation endpoint
        error_msg = str(e).lower()
        if "authentication" in error_msg or "unauthorized" in error_msg:
            raise HTTPException(status_code=401, detail="Authentication expired. Please refresh the page and log in again.")
        elif "database" in error_msg or "connection" in error_msg:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable. Please try again in a moment.")
        else:
            raise HTTPException(status_code=503, detail="Generation details temporarily unavailable. Please try again later.")


@router.delete("/{generation_id}")
@limit("20/minute")  # Stricter limit for delete operations
async def delete_generation(
    generation_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Delete a generation.
    
    Rate limit: 20 deletions per minute to prevent abuse.
    """
    try:
        success = await generation_service.delete_generation(
            generation_id=generation_id,
            user_id=str(current_user.id)  # Convert UUID to string for JSON serialization
        )
        
        if not success:
            logger.error(f"❌ [DELETE] Generation deletion returned False for {generation_id}")
            raise HTTPException(status_code=503, detail="Delete operation temporarily unavailable. Please try again later.")
        
        # Log deletion for audit trail
        client_ip = request.client.host if request.client else "unknown"
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Generation {generation_id} deleted by user {str(current_user.id)} from {client_ip}")
        
        return {"message": "Generation deleted successfully"}
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to delete generation {generation_id} for user {str(current_user.id)}: {str(e)}")
        
        # CRITICAL FIX: Prevent 500 errors in delete endpoint
        error_msg = str(e).lower()
        if "authentication" in error_msg or "unauthorized" in error_msg:
            raise HTTPException(status_code=401, detail="Authentication expired. Please refresh the page and log in again.")
        elif "database" in error_msg or "connection" in error_msg:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable. Please try again in a moment.")
        else:
            raise HTTPException(status_code=503, detail="Delete operation temporarily unavailable. Please try again later.")


@router.post("/{generation_id}/favorite", response_model=GenerationResponse)
@api_limit()  # Standard API rate limit
async def toggle_generation_favorite(
    generation_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Toggle favorite status of a generation.
    
    Rate limit: Standard API limit (100/minute).
    """
    try:
        generation = await generation_service.toggle_generation_favorite(
            generation_id=generation_id,
            user_id=str(current_user.id)  # Convert UUID to string for JSON serialization
        )
        
        return generation
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to toggle favorite for generation {generation_id}: {str(e)}")
        
        # CRITICAL FIX: Prevent 500 errors in favorite toggle endpoint
        error_msg = str(e).lower()
        if "authentication" in error_msg or "unauthorized" in error_msg:
            raise HTTPException(status_code=401, detail="Authentication expired. Please refresh the page and log in again.")
        elif "database" in error_msg or "connection" in error_msg:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable. Please try again in a moment.")
        else:
            raise HTTPException(status_code=503, detail="Favorite toggle temporarily unavailable. Please try again later.")


@router.get("/{generation_id}/media-urls", response_model=Dict[str, Any])
@limit("60/minute")  # Higher limit for media access
async def get_generation_media_urls(
    generation_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user)
):
    """
    Get comprehensive media access information for generation files.
    
    Returns signed URLs, file information, and storage metadata.
    Rate limit: 60 requests per minute for media access.
    """
    try:
        # CRITICAL FIX: Extract auth token from request header for database operations
        auth_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            auth_token = auth_header.split(" ", 1)[1]
            import logging
            logger = logging.getLogger(__name__)
            logger.info(f"🔑 [MEDIA-URLS] Auth token extracted for user {current_user.id}: {auth_token[:20]}...")
        else:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"⚠️ [MEDIA-URLS] No auth token found in request headers for user {current_user.id}")
        
        media_info = await generation_service.get_generation_media_urls(
            generation_id=generation_id,
            user_id=str(current_user.id),  # Convert UUID to string for JSON serialization
            auth_token=auth_token  # Pass auth token for database authentication
        )
        
        return media_info
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to get media URLs for generation {generation_id}: {str(e)}")
        
        # CRITICAL FIX: Prevent 500 errors in media URLs endpoint
        error_msg = str(e).lower()
        if "authentication" in error_msg or "unauthorized" in error_msg:
            raise HTTPException(status_code=401, detail="Authentication expired. Please refresh the page and log in again.")
        elif "database" in error_msg or "connection" in error_msg:
            raise HTTPException(status_code=503, detail="Database temporarily unavailable. Please try again in a moment.")
        elif "storage" in error_msg:
            raise HTTPException(status_code=503, detail="File storage temporarily unavailable. Please try again later.")
        else:
            raise HTTPException(status_code=503, detail="Media URLs temporarily unavailable. Please try again later.")


@router.get("/models/supported/")
@router.get("/models/supported")  # CRITICAL FIX: Add route without trailing slash
# @limit("20/minute")  # Moderate limit for model info - temporarily disabled for testing
async def get_supported_models(request: Request):
    """
    Get all supported AI models with their configurations.
    
    Rate limit: 20 requests per minute for model information.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("Getting supported models from FAL service...")
        models = fal_service.get_supported_models()
        logger.info(f"Successfully got {len(models)} models")
        return {"models": models}
        
    except Exception as e:
        logger.error(f"Failed to get supported models: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # CRITICAL FIX: Prevent 500 errors in supported models endpoint
        error_msg = str(e).lower()
        if "api key" in error_msg or "authentication" in error_msg:
            raise HTTPException(status_code=503, detail="AI service temporarily unavailable. Please try again later.")
        elif "connection" in error_msg or "network" in error_msg:
            raise HTTPException(status_code=503, detail="Network connectivity issue. Please try again in a moment.")
        else:
            raise HTTPException(status_code=503, detail="AI models list temporarily unavailable. Please try again later.")