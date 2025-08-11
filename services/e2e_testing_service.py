"""
Production-Ready E2E Testing Service
===================================
Provides comprehensive E2E testing infrastructure with proper session management,
test user isolation, and automatic cleanup. Security-first design with production-safe defaults.
"""

import asyncio
import logging
import uuid
import time
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
import json

from database import SupabaseClient
from config import settings
from utils.uuid_utils import UUIDUtils
from models.user import UserResponse

logger = logging.getLogger(__name__)


@dataclass
class E2ETestSession:
    """Represents an E2E test session with isolated test data."""
    session_id: str
    test_user_id: str
    test_user_email: str
    start_time: datetime
    end_time: Optional[datetime] = None
    status: str = "active"  # active, completed, failed, cleanup_needed
    test_data: Dict[str, Any] = None
    cleanup_completed: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for JSON serialization."""
        data = asdict(self)
        data['start_time'] = self.start_time.isoformat()
        if self.end_time:
            data['end_time'] = self.end_time.isoformat()
        return data


class E2ETestingService:
    """
    Production-safe E2E testing service.
    
    Features:
    - Isolated test user creation and management
    - Session-based test data tracking
    - Automatic cleanup after test completion
    - Credit management for test users
    - Generation testing with proper storage integration
    """
    
    def __init__(self):
        self.db = SupabaseClient()
        self.active_sessions: Dict[str, E2ETestSession] = {}
        self.cleanup_lock = asyncio.Lock()
        
        # Test user configuration
        self.test_user_prefix = "e2e_test_"
        self.test_user_domain = "@e2e.velro.test"
        self.default_test_credits = 10000
        
        # Session management
        self.max_session_duration = timedelta(hours=1)
        self.cleanup_interval = timedelta(minutes=5)
        
        logger.info("✅ [E2E-SERVICE] E2E Testing Service initialized")
    
    async def create_test_session(
        self, 
        test_name: str = "default",
        credits: Optional[int] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Create a new E2E test session with isolated test user.
        
        Args:
            test_name: Name/identifier for the test
            credits: Initial credits for test user
            
        Returns:
            Tuple of (session_id, session_info)
        """
        # Check if E2E testing is enabled via environment variable
        import os
        if os.getenv("E2E_TESTING_ENABLED", "false").lower() != "true":
            raise ValueError("E2E testing is not enabled")
        
        session_id = str(uuid.uuid4())
        test_user_email = f"{self.test_user_prefix}{test_name}_{int(time.time())}{self.test_user_domain}"
        
        logger.info(f"🧪 [E2E-SESSION] Creating test session: {session_id}")
        logger.info(f"🧪 [E2E-SESSION] Test user email: {test_user_email}")
        
        try:
            # Create isolated test user
            test_user_id = await self._create_test_user(
                email=test_user_email,
                credits=credits or self.default_test_credits
            )
            
            # Create session
            session = E2ETestSession(
                session_id=session_id,
                test_user_id=test_user_id,
                test_user_email=test_user_email,
                start_time=datetime.now(timezone.utc),
                test_data={"test_name": test_name}
            )
            
            self.active_sessions[session_id] = session
            
            logger.info(f"✅ [E2E-SESSION] Test session created: {session_id}")
            
            return session_id, {
                "session_id": session_id,
                "test_user_id": test_user_id,
                "test_user_email": test_user_email,
                "credits": credits or self.default_test_credits,
                "status": "active",
                "start_time": session.start_time.isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ [E2E-SESSION] Failed to create test session: {e}")
            # Cleanup any partial state
            await self._cleanup_failed_session(session_id, test_user_email)
            raise
    
    async def _create_test_user(self, email: str, credits: int) -> str:
        """Create an isolated test user with specified credits."""
        try:
            # Generate test user data
            test_user_id = str(uuid.uuid4())
            display_name = f"E2E Test User {int(time.time())}"
            
            # Insert user into database
            user_data = {
                "id": test_user_id,
                "email": email,
                "display_name": display_name,
                "credits_balance": credits,
                "role": "viewer",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "avatar_url": None,
                "is_test_user": True  # Flag for cleanup
            }
            
            # Check if service key is available before using it
            use_service_key = False
            try:
                # Quick check if service client is available
                if hasattr(self.db, '_service_key_valid') and self.db._service_key_valid:
                    use_service_key = True
                    logger.info("✅ [E2E-USER] Using service key for user creation")
                else:
                    logger.warning("⚠️ [E2E-USER] Service key not available, using anon client")
            except Exception as e:
                logger.warning(f"⚠️ [E2E-USER] Service key check failed: {e}")
            
            result = await self.db.execute_query_async(
                table="users",
                operation="insert",
                data=user_data,
                use_service_key=use_service_key,
                timeout=5.0
            )
            
            if not result:
                raise ValueError("Failed to create test user in database")
                
            logger.info(f"✅ [E2E-USER] Created test user: {test_user_id} with {credits} credits")
            return test_user_id
            
        except Exception as e:
            logger.error(f"❌ [E2E-USER] Failed to create test user: {e}")
            raise
    
    async def get_test_user_token(self, session_id: str) -> Dict[str, Any]:
        """
        Generate authentication token for test user.
        For E2E testing, we create a simple test token that can be validated.
        """
        if session_id not in self.active_sessions:
            raise ValueError(f"Test session not found: {session_id}")
            
        session = self.active_sessions[session_id]
        
        # Create a test token (simplified for E2E testing)
        test_token = f"e2e_test_token_{session.test_user_id}_{session_id}"
        
        return {
            "access_token": test_token,
            "token_type": "bearer",
            "user_id": session.test_user_id,
            "email": session.test_user_email,
            "session_id": session_id
        }
    
    async def test_image_generation(
        self,
        session_id: str,
        prompt: str = "A beautiful sunset over mountains",
        model: str = "flux-schnell"
    ) -> Dict[str, Any]:
        """
        Test the complete image generation flow including storage.
        
        Returns:
            Dict with generation results and storage information
        """
        if session_id not in self.active_sessions:
            raise ValueError(f"Test session not found: {session_id}")
            
        session = self.active_sessions[session_id]
        
        logger.info(f"🧪 [E2E-GENERATION] Testing image generation for session: {session_id}")
        
        try:
            # Import generation service
            from services.generation_service import generation_service
            
            # Create a test generation request
            generation_request = {
                "prompt": prompt,
                "model": model,
                "project_id": None,  # Use default project
                "style_stack_ids": [],
                "width": 512,
                "height": 512,
                "num_inference_steps": 8,
                "guidance_scale": 7.0
            }
            
            # Execute generation
            generation_result = await generation_service.create_generation(
                user_id=session.test_user_id,
                generation_data=generation_request
            )
            
            logger.info(f"✅ [E2E-GENERATION] Generation completed: {generation_result.get('id')}")
            
            # Check if image is properly stored in Supabase Storage
            media_url = generation_result.get("media_url")
            if media_url:
                storage_info = await self._verify_storage_integration(media_url)
                generation_result["storage_verification"] = storage_info
            
            # Update session test data
            if "generations" not in session.test_data:
                session.test_data["generations"] = []
            session.test_data["generations"].append({
                "generation_id": generation_result.get("id"),
                "prompt": prompt,
                "model": model,
                "media_url": media_url,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return generation_result
            
        except Exception as e:
            logger.error(f"❌ [E2E-GENERATION] Image generation test failed: {e}")
            session.status = "failed"
            raise
    
    async def _verify_storage_integration(self, media_url: str) -> Dict[str, Any]:
        """Verify that image is properly stored in Supabase Storage."""
        try:
            storage_info = {
                "media_url": media_url,
                "verification_time": datetime.now(timezone.utc).isoformat()
            }
            
            # Check if the media_url is a Supabase Storage path (file path format)
            # The generation service should store file paths, not URLs
            is_storage_path = media_url and isinstance(media_url, str) and "/" in media_url
            is_fal_url = media_url and ("fal.ai" in media_url or "fal.media" in media_url)
            is_http_url = media_url and media_url.startswith(("http://", "https://"))
            is_supabase_signed_url = is_http_url and "supabase" in media_url and "sign" in media_url
            
            storage_info.update({
                "is_storage_path": is_storage_path,
                "is_fal_url": is_fal_url,
                "is_http_url": is_http_url,
                "is_supabase_signed_url": is_supabase_signed_url
            })
            
            # Determine storage status
            if is_storage_path and not is_http_url:
                logger.info("✅ [E2E-STORAGE] Image properly stored as Supabase Storage path")
                storage_info["status"] = "verified_supabase_path"
            elif is_supabase_signed_url:
                logger.info("✅ [E2E-STORAGE] Image stored with Supabase signed URL")
                storage_info["status"] = "verified_supabase_url"
            elif is_fal_url:
                logger.warning("⚠️ [E2E-STORAGE] Image still using FAL URL - storage migration needed")
                storage_info["status"] = "needs_migration"
            elif is_http_url:
                logger.warning("⚠️ [E2E-STORAGE] Unknown HTTP URL storage location")
                storage_info["status"] = "unknown_url"
            else:
                logger.warning("⚠️ [E2E-STORAGE] Unknown storage format")
                storage_info["status"] = "unknown"
                
            return storage_info
            
        except Exception as e:
            logger.error(f"❌ [E2E-STORAGE] Storage verification failed: {e}")
            return {
                "status": "verification_failed",
                "error": str(e),
                "media_url": media_url
            }
    
    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """Get information about a test session."""
        if session_id not in self.active_sessions:
            raise ValueError(f"Test session not found: {session_id}")
            
        session = self.active_sessions[session_id]
        return session.to_dict()
    
    async def test_media_url_generation(self, session_id: str, generation_id: str) -> Dict[str, Any]:
        """
        Test media URL generation for a completed generation.
        This verifies that signed URLs can be generated from stored files.
        """
        if session_id not in self.active_sessions:
            raise ValueError(f"Test session not found: {session_id}")
            
        session = self.active_sessions[session_id]
        
        logger.info(f"🧪 [E2E-MEDIA] Testing media URL generation for generation: {generation_id}")
        
        try:
            # Import generation service to get media URLs
            from services.generation_service import generation_service
            
            # Get media URLs for the generation
            media_info = await generation_service.get_generation_media_urls(
                generation_id=generation_id,
                user_id=session.test_user_id,
                expires_in=3600  # 1 hour
            )
            
            # Verify the media information
            media_verification = {
                "generation_id": generation_id,
                "test_time": datetime.now(timezone.utc).isoformat(),
                "media_info_received": media_info is not None,
                "primary_url_available": media_info.get("primary_url") is not None if media_info else False,
                "signed_urls_count": len(media_info.get("signed_urls", [])) if media_info else 0,
                "file_count": media_info.get("file_count", 0) if media_info else 0
            }
            
            # Check if signed URLs are properly formatted Supabase URLs
            if media_info and media_info.get("signed_urls"):
                signed_urls = media_info["signed_urls"]
                supabase_url_count = 0
                
                for url_info in signed_urls:
                    signed_url = url_info.get("signed_url", "")
                    if "supabase" in signed_url and "sign" in signed_url:
                        supabase_url_count += 1
                
                media_verification.update({
                    "supabase_signed_urls": supabase_url_count,
                    "all_urls_supabase": supabase_url_count == len(signed_urls),
                    "sample_signed_url": signed_urls[0].get("signed_url", "")[:100] + "..." if signed_urls else None
                })
            
            # Update session test data
            if "media_url_tests" not in session.test_data:
                session.test_data["media_url_tests"] = []
            session.test_data["media_url_tests"].append(media_verification)
            
            logger.info(f"✅ [E2E-MEDIA] Media URL test completed: {media_verification['signed_urls_count']} URLs generated")
            
            return {
                "success": True,
                "media_verification": media_verification,
                "media_info": media_info
            }
            
        except Exception as e:
            logger.error(f"❌ [E2E-MEDIA] Media URL generation test failed: {e}")
            session.status = "failed"
            raise
    
    async def cleanup_session(self, session_id: str) -> Dict[str, Any]:
        """Clean up a test session and all associated test data."""
        async with self.cleanup_lock:
            if session_id not in self.active_sessions:
                logger.warning(f"⚠️ [E2E-CLEANUP] Session not found for cleanup: {session_id}")
                return {"status": "not_found"}
                
            session = self.active_sessions[session_id]
            
            logger.info(f"🧹 [E2E-CLEANUP] Starting cleanup for session: {session_id}")
            
            try:
                cleanup_results = {
                    "session_id": session_id,
                    "cleanup_started": datetime.now(timezone.utc).isoformat(),
                    "steps": []
                }
                
                # 1. Delete test user and all associated data
                await self._cleanup_test_user(session.test_user_id, cleanup_results)
                
                # 2. Clean up any generated images/files
                await self._cleanup_test_generations(session, cleanup_results)
                
                # 3. Mark session as cleaned up
                session.end_time = datetime.now(timezone.utc)
                session.status = "completed"
                session.cleanup_completed = True
                
                # 4. Remove from active sessions
                del self.active_sessions[session_id]
                
                cleanup_results["cleanup_completed"] = datetime.now(timezone.utc).isoformat()
                cleanup_results["status"] = "success"
                
                logger.info(f"✅ [E2E-CLEANUP] Session cleanup completed: {session_id}")
                return cleanup_results
                
            except Exception as e:
                logger.error(f"❌ [E2E-CLEANUP] Cleanup failed for session {session_id}: {e}")
                session.status = "cleanup_failed"
                return {
                    "status": "failed",
                    "error": str(e),
                    "session_id": session_id
                }
    
    async def _cleanup_test_user(self, test_user_id: str, results: Dict[str, Any]):
        """Clean up test user and all associated data."""
        try:
            # Delete from users table
            await self.db.execute_query_async(
                table="users",
                operation="delete",
                filters={"id": test_user_id},
                use_service_key=True,
                timeout=10.0
            )
            
            results["steps"].append({
                "step": "delete_test_user",
                "status": "success",
                "user_id": test_user_id
            })
            
            logger.info(f"✅ [E2E-CLEANUP] Deleted test user: {test_user_id}")
            
        except Exception as e:
            logger.error(f"❌ [E2E-CLEANUP] Failed to delete test user {test_user_id}: {e}")
            results["steps"].append({
                "step": "delete_test_user",
                "status": "failed",
                "error": str(e)
            })
    
    async def _cleanup_test_generations(self, session: E2ETestSession, results: Dict[str, Any]):
        """Clean up test generations and associated files."""
        try:
            if "generations" not in session.test_data:
                return
                
            generation_ids = [
                gen["generation_id"] for gen in session.test_data["generations"]
                if "generation_id" in gen
            ]
            
            if not generation_ids:
                return
                
            # Delete generations from database
            for gen_id in generation_ids:
                try:
                    await self.db.execute_query_async(
                        table="generations",
                        operation="delete",
                        filters={"id": gen_id},
                        use_service_key=True,
                        timeout=5.0
                    )
                    
                except Exception as e:
                    logger.warning(f"⚠️ [E2E-CLEANUP] Failed to delete generation {gen_id}: {e}")
            
            results["steps"].append({
                "step": "cleanup_generations",
                "status": "success",
                "count": len(generation_ids)
            })
            
            logger.info(f"✅ [E2E-CLEANUP] Cleaned up {len(generation_ids)} test generations")
            
        except Exception as e:
            logger.error(f"❌ [E2E-CLEANUP] Failed to cleanup generations: {e}")
            results["steps"].append({
                "step": "cleanup_generations", 
                "status": "failed",
                "error": str(e)
            })
    
    async def _cleanup_failed_session(self, session_id: str, test_user_email: str):
        """Clean up any partial state from a failed session creation."""
        try:
            # Try to find and delete any partially created test user
            result = await self.db.execute_query_async(
                table="users",
                operation="select",
                filters={"email": test_user_email},
                use_service_key=True,
                timeout=5.0
            )
            
            if result:
                await self.db.execute_query_async(
                    table="users",
                    operation="delete",
                    filters={"email": test_user_email},
                    use_service_key=True,
                    timeout=5.0
                )
                logger.info(f"✅ [E2E-CLEANUP] Cleaned up partial test user: {test_user_email}")
                
        except Exception as e:
            logger.warning(f"⚠️ [E2E-CLEANUP] Failed to cleanup partial session: {e}")
    
    async def cleanup_expired_sessions(self):
        """Clean up sessions that have exceeded maximum duration."""
        async with self.cleanup_lock:
            current_time = datetime.now(timezone.utc)
            expired_sessions = []
            
            for session_id, session in self.active_sessions.items():
                if current_time - session.start_time > self.max_session_duration:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                logger.warning(f"⚠️ [E2E-CLEANUP] Cleaning up expired session: {session_id}")
                try:
                    await self.cleanup_session(session_id)
                except Exception as e:
                    logger.error(f"❌ [E2E-CLEANUP] Failed to cleanup expired session {session_id}: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check for E2E testing service."""
        try:
            # Check E2E testing status via environment variable
            import os
            e2e_enabled = os.getenv("E2E_TESTING_ENABLED", "false").lower() == "true"
            test_creds_available = e2e_enabled and os.getenv("E2E_TEST_USER_EMAIL") is not None
            
            return {
                "status": "healthy",
                "e2e_testing_enabled": e2e_enabled,
                "active_sessions": len(self.active_sessions),
                "database_available": self.db.is_available(),
                "test_credentials_available": test_creds_available,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }


# Global E2E testing service instance
e2e_testing_service = E2ETestingService()