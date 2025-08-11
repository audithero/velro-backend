"""
E2E Testing Router
==================
Provides production-safe endpoints for E2E testing infrastructure.
All endpoints are secured and only available when E2E testing is explicitly enabled.
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status, Request, Depends, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Import testing service with fallback
import os

try:
    from services.e2e_testing_service import e2e_testing_service
    E2E_SERVICE_AVAILABLE = True
except ImportError as e:
    logger.warning(f"⚠️ [E2E-ROUTER] E2E testing service not available: {e}")
    E2E_SERVICE_AVAILABLE = False

# Production-safe E2E testing check
def is_e2e_testing_enabled():
    """Check if E2E testing is enabled via environment variable."""
    return os.getenv("E2E_TESTING_ENABLED", "false").lower() == "true"

def get_test_user_credentials():
    """Get test user credentials from environment."""
    if not is_e2e_testing_enabled():
        return None
    return {
        "email": os.getenv("E2E_TEST_USER_EMAIL", "test@velro.ai"),
        "password": os.getenv("E2E_TEST_USER_PASSWORD", "TestPassword123!"),
        "credits": int(os.getenv("E2E_TEST_USER_CREDITS", "10000"))
    }

router = APIRouter(prefix="/api/v1/e2e", tags=["E2E Testing"])


class TestSessionRequest(BaseModel):
    """Request model for creating test sessions."""
    test_name: str = Field(default="default", description="Name/identifier for the test")
    credits: Optional[int] = Field(default=None, description="Initial credits for test user")


class GenerationTestRequest(BaseModel):
    """Request model for testing image generation."""
    session_id: str = Field(description="Test session ID")
    prompt: str = Field(default="A beautiful sunset over mountains", description="Generation prompt")
    model: str = Field(default="flux-schnell", description="Model to use for generation")


class MediaUrlTestRequest(BaseModel):
    """Request model for testing media URL generation."""
    session_id: str = Field(description="Test session ID")
    generation_id: str = Field(description="Generation ID to test media URLs for")


def require_e2e_testing():
    """Dependency to ensure E2E testing is enabled."""
    if not E2E_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="E2E testing service is not available"
        )
    
    if not is_e2e_testing_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="E2E testing is not enabled. Set E2E_TESTING_ENABLED=true to enable."
        )
    
    return True


@router.get("/health")
async def e2e_health_check():
    """
    Health check for E2E testing infrastructure.
    This endpoint is always available for testing the E2E router itself.
    """
    try:
        health_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "e2e_router_available": True,
            "e2e_service_available": E2E_SERVICE_AVAILABLE,
            "e2e_testing_enabled": is_e2e_testing_enabled() if E2E_SERVICE_AVAILABLE else False
        }
        
        # If service is available, get detailed health info
        if E2E_SERVICE_AVAILABLE and is_e2e_testing_enabled():
            service_health = await e2e_testing_service.health_check()
            health_info.update(service_health)
            
        return {
            "status": "healthy",
            "service": "e2e_testing",
            **health_info
        }
        
    except Exception as e:
        logger.error(f"❌ [E2E-HEALTH] Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.post("/test-session")
async def create_test_session(
    request: TestSessionRequest,
    _: bool = Depends(require_e2e_testing)
) -> Dict[str, Any]:
    """
    Create a new E2E test session with isolated test user.
    
    This endpoint:
    1. Creates an isolated test user with specified credits
    2. Returns session information for subsequent test operations
    3. Sets up proper cleanup tracking
    """
    try:
        logger.info(f"🧪 [E2E-ROUTER] Creating test session: {request.test_name}")
        
        session_id, session_info = await e2e_testing_service.create_test_session(
            test_name=request.test_name,
            credits=request.credits
        )
        
        logger.info(f"✅ [E2E-ROUTER] Test session created successfully: {session_id}")
        
        return {
            "success": True,
            "message": "Test session created successfully",
            **session_info
        }
        
    except ValueError as e:
        logger.error(f"❌ [E2E-ROUTER] Invalid request for test session: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ [E2E-ROUTER] Failed to create test session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create test session: {str(e)}"
        )


@router.get("/test-session/{session_id}")
async def get_test_session(
    session_id: str,
    _: bool = Depends(require_e2e_testing)
) -> Dict[str, Any]:
    """Get information about a specific test session."""
    try:
        session_info = await e2e_testing_service.get_session_info(session_id)
        
        return {
            "success": True,
            **session_info
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ [E2E-ROUTER] Failed to get session info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get session information"
        )


@router.get("/test-session/{session_id}/token")
async def get_test_user_token(
    session_id: str,
    _: bool = Depends(require_e2e_testing)
) -> Dict[str, Any]:
    """
    Get authentication token for test user in session.
    This token can be used in subsequent API calls during testing.
    """
    try:
        token_info = await e2e_testing_service.get_test_user_token(session_id)
        
        return {
            "success": True,
            "message": "Test user token generated",
            **token_info
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ [E2E-ROUTER] Failed to generate test token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate test user token"
        )


@router.post("/test-generation")
async def test_image_generation(
    request: GenerationTestRequest,
    _: bool = Depends(require_e2e_testing)
) -> Dict[str, Any]:
    """
    Test the complete image generation flow including storage integration.
    
    This endpoint:
    1. Uses the test user from the specified session
    2. Creates an image generation
    3. Verifies proper Supabase Storage integration
    4. Returns detailed results for testing validation
    """
    try:
        logger.info(f"🧪 [E2E-ROUTER] Testing image generation for session: {request.session_id}")
        
        generation_result = await e2e_testing_service.test_image_generation(
            session_id=request.session_id,
            prompt=request.prompt,
            model=request.model
        )
        
        logger.info(f"✅ [E2E-ROUTER] Image generation test completed successfully")
        
        return {
            "success": True,
            "message": "Image generation test completed",
            "generation": generation_result
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ [E2E-ROUTER] Image generation test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Image generation test failed: {str(e)}"
        )


@router.post("/test-media-urls")
async def test_media_url_generation(
    request: MediaUrlTestRequest,
    _: bool = Depends(require_e2e_testing)
) -> Dict[str, Any]:
    """
    Test media URL generation for a completed generation.
    
    This endpoint:
    1. Takes a completed generation ID from a test session
    2. Tests the media URL generation process
    3. Verifies that proper Supabase Storage signed URLs are generated
    4. Returns detailed verification results for testing validation
    """
    try:
        logger.info(f"🧪 [E2E-ROUTER] Testing media URL generation for generation: {request.generation_id}")
        
        media_test_result = await e2e_testing_service.test_media_url_generation(
            session_id=request.session_id,
            generation_id=request.generation_id
        )
        
        logger.info(f"✅ [E2E-ROUTER] Media URL generation test completed successfully")
        
        return {
            "success": True,
            "message": "Media URL generation test completed",
            **media_test_result
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ [E2E-ROUTER] Media URL generation test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Media URL generation test failed: {str(e)}"
        )


@router.delete("/test-session/{session_id}")
async def cleanup_test_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    _: bool = Depends(require_e2e_testing)
) -> Dict[str, Any]:
    """
    Clean up a test session and all associated test data.
    
    This endpoint:
    1. Deletes the test user and all associated data
    2. Cleans up any generated images/files
    3. Removes session tracking
    4. Returns cleanup results
    """
    try:
        logger.info(f"🧹 [E2E-ROUTER] Starting cleanup for session: {session_id}")
        
        # Start cleanup in background to avoid timeout
        cleanup_task = asyncio.create_task(
            e2e_testing_service.cleanup_session(session_id)
        )
        
        # Wait for cleanup with timeout
        try:
            cleanup_result = await asyncio.wait_for(cleanup_task, timeout=30.0)
        except asyncio.TimeoutError:
            # If cleanup takes too long, continue in background
            background_tasks.add_task(
                _wait_for_cleanup_completion, cleanup_task, session_id
            )
            return {
                "success": True,
                "message": "Cleanup started - will complete in background",
                "session_id": session_id,
                "status": "cleanup_in_progress"
            }
        
        logger.info(f"✅ [E2E-ROUTER] Session cleanup completed: {session_id}")
        
        return {
            "success": True,
            "message": "Test session cleaned up successfully",
            **cleanup_result
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"❌ [E2E-ROUTER] Session cleanup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Session cleanup failed: {str(e)}"
        )


@router.post("/cleanup-expired")
async def cleanup_expired_sessions(
    background_tasks: BackgroundTasks,
    _: bool = Depends(require_e2e_testing)
) -> Dict[str, Any]:
    """
    Clean up all expired test sessions.
    This is typically called by monitoring systems or test infrastructure.
    """
    try:
        logger.info("🧹 [E2E-ROUTER] Starting cleanup of expired sessions")
        
        # Run cleanup in background
        background_tasks.add_task(_cleanup_expired_sessions)
        
        return {
            "success": True,
            "message": "Cleanup of expired sessions started",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"❌ [E2E-ROUTER] Failed to start expired session cleanup: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start expired session cleanup"
        )


@router.get("/status")
async def get_e2e_status(_: bool = Depends(require_e2e_testing)) -> Dict[str, Any]:
    """
    Get overall status of E2E testing infrastructure.
    Includes active sessions, service health, and configuration.
    """
    try:
        status_info = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "e2e_testing_enabled": True,  # Must be true if we reach this point
            "service_available": E2E_SERVICE_AVAILABLE
        }
        
        if E2E_SERVICE_AVAILABLE:
            # Get service health information
            health_info = await e2e_testing_service.health_check()
            status_info.update(health_info)
            
            # Get test credentials info (without exposing actual credentials)
            test_creds = get_test_user_credentials()
            status_info["test_credentials_configured"] = test_creds is not None
            
        return {
            "success": True,
            **status_info
        }
        
    except Exception as e:
        logger.error(f"❌ [E2E-ROUTER] Failed to get E2E status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get E2E testing status"
        )


# Background task helpers
async def _wait_for_cleanup_completion(cleanup_task: asyncio.Task, session_id: str):
    """Wait for cleanup task completion in background."""
    try:
        result = await cleanup_task
        logger.info(f"✅ [E2E-BACKGROUND] Background cleanup completed for session: {session_id}")
    except Exception as e:
        logger.error(f"❌ [E2E-BACKGROUND] Background cleanup failed for session {session_id}: {e}")


async def _cleanup_expired_sessions():
    """Background task to cleanup expired sessions."""
    try:
        await e2e_testing_service.cleanup_expired_sessions()
        logger.info("✅ [E2E-BACKGROUND] Expired session cleanup completed")
    except Exception as e:
        logger.error(f"❌ [E2E-BACKGROUND] Expired session cleanup failed: {e}")


# Router status endpoint (always available for debugging)
@router.get("")
async def e2e_router_info():
    """
    Basic information about the E2E testing router.
    Available even when E2E testing is disabled for debugging.
    """
    return {
        "service": "E2E Testing Router",
        "version": "1.0.0",
        "status": "available",
        "e2e_testing_enabled": is_e2e_testing_enabled(),
        "service_available": E2E_SERVICE_AVAILABLE,
        "endpoints": [
            "GET /api/v1/e2e/health - Health check",
            "POST /api/v1/e2e/test-session - Create test session",
            "GET /api/v1/e2e/test-session/{id} - Get session info",
            "GET /api/v1/e2e/test-session/{id}/token - Get test user token",
            "POST /api/v1/e2e/test-generation - Test image generation",
            "POST /api/v1/e2e/test-media-urls - Test media URL generation",
            "DELETE /api/v1/e2e/test-session/{id} - Cleanup session",
            "POST /api/v1/e2e/cleanup-expired - Cleanup expired sessions",
            "GET /api/v1/e2e/status - Get E2E status"
        ],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }