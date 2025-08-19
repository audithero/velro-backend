"""
Debug authentication router to help troubleshoot production issues.
This adds debug endpoints to help understand what's happening with auth.
"""
from fastapi import APIRouter, HTTPException
from database import SupabaseClient
from models.user import UserResponse
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/debug", tags=["debug"])

@router.get("/database")
async def debug_database():
    """Test database connectivity."""
    try:
        db_client = SupabaseClient()
        
        # Test anon client
        anon_test = None
        anon_error = None
        try:
            anon_client = db_client.client
            anon_test = anon_client.table("users").select("id").limit(1).execute()
            anon_works = anon_test.data is not None
        except Exception as e:
            anon_works = False
            anon_error = str(e)
        
        # Test service client
        service_test = None
        service_error = None
        try:
            service_client = db_client.service_client
            service_test = service_client.table("users").select("id").limit(1).execute()
            service_works = service_test.data is not None
        except Exception as e:
            service_works = False
            service_error = str(e)
        
        return {
            "status": "success",
            "database_available": db_client.is_available(),
            "client_url": db_client.client.supabase_url[:50] + "...",
            "anon_client": {
                "works": anon_works,
                "error": anon_error,
                "result_count": len(anon_test.data) if anon_test and anon_test.data else 0
            },
            "service_client": {
                "works": service_works,
                "error": service_error,
                "result_count": len(service_test.data) if service_test and service_test.data else 0
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }

@router.get("/user/{user_id}")
async def debug_user_lookup(user_id: str):
    """Test user lookup in database."""
    try:
        db_client = SupabaseClient()
        
        # Use the same fallback logic as middleware
        try:
            profile_result = db_client.service_client.table('users').select('*').eq('id', str(user_id)).execute()
            client_used = "service"
        except Exception as service_error:
            profile_result = db_client.client.table('users').select('*').eq('id', str(user_id)).execute()
            client_used = "anon"
        
        return {
            "status": "success",
            "user_id": user_id,
            "database_available": db_client.is_available(),
            "client_used": client_used,
            "query_result_count": len(profile_result.data) if profile_result.data else 0,
            "user_found": profile_result.data and len(profile_result.data) > 0,
            "user_data": profile_result.data[0] if profile_result.data and len(profile_result.data) > 0 else None
        }
        
    except Exception as e:
        return {
            "status": "error",
            "user_id": user_id,
            "error": str(e),
            "error_type": type(e).__name__
        }

@router.get("/token/{user_id}")
async def debug_token_validation(user_id: str):
    """Test the complete token validation logic."""
    try:
        token = f"supabase_token_{user_id}"
        
        # Replicate the middleware logic with fallback
        db_client = SupabaseClient()
        
        # Use the same fallback logic as middleware
        try:
            profile_result = db_client.service_client.table('users').select('*').eq('id', str(user_id)).execute()
            client_used = "service"
        except Exception as service_error:
            profile_result = db_client.client.table('users').select('*').eq('id', str(user_id)).execute()
            client_used = "anon"
        
        if profile_result.data and len(profile_result.data) > 0:
            profile = profile_result.data[0]
            
            # Parse created_at from database
            created_at_str = profile.get('created_at', '')
            if created_at_str:
                if created_at_str.endswith('Z'):
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                else:
                    created_at = datetime.fromisoformat(created_at_str)
            else:
                created_at = datetime.now(timezone.utc)
            
            user = UserResponse(
                id=user_id,
                email=profile.get('email', 'unknown@example.com'),
                display_name=profile.get('display_name', ''),
                avatar_url=profile.get('avatar_url'),
                credits=profile.get('credits', 100),
                role=profile.get('role', 'viewer'),
                created_at=created_at
            )
            
            return {
                "status": "success",
                "token": f"{token[:20]}...",
                "user_id": user_id,
                "client_used": client_used,
                "validation_successful": True,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "display_name": user.display_name,
                    "credits_balance": user.credits_balance,
                    "role": user.role
                }
            }
        else:
            return {
                "status": "error",
                "token": f"{token[:20]}...",
                "user_id": user_id,
                "validation_successful": False,
                "error": "User not found in database",
                "database_response": profile_result.data
            }
            
    except Exception as e:
        return {
            "status": "error",
            "token": f"supabase_token_{user_id}"[:20] + "...",
            "user_id": user_id,
            "validation_successful": False,
            "error": str(e),
            "error_type": type(e).__name__
        }