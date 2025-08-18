"""
Authentication service for user management and JWT tokens.
Following CLAUDE.md: Business logic layer with Supabase Auth integration.
Enhanced with comprehensive monitoring, security features, and production optimizations.
"""
import os
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException, status
from supabase import Client, create_client

from models.user import UserCreate, UserResponse, UserLogin, Token, User
from database import SupabaseClient
from config import settings
import uuid
import logging

# Import enhanced monitoring and security features
from utils.auth_monitor import get_auth_monitor, AuthEvent, AuthEventType, SecurityThreatLevel
from utils.token_manager import get_token_manager, get_session_manager

logger = logging.getLogger(__name__)


class AuthService:
    """Authentication service using Supabase Auth with enhanced monitoring and security."""
    
    def __init__(self, db_client: SupabaseClient):
        self.db_client = db_client
        self.client = db_client.client  # Use regular client for auth operations
        self.auth_monitor = get_auth_monitor()
        self.token_manager = get_token_manager()
        self.session_manager = get_session_manager()
    
    async def register_user(self, user_data: UserCreate) -> UserResponse:
        """Register a new user using Supabase Auth and create profile."""
        try:
            # SECURITY: Removed development mode bypass - security vulnerability removed
            
            # Step 1: Register with Supabase Auth with timeout protection
            logger.info(f"🔍 [DEBUG] Starting Supabase auth signup for: {user_data.email}")
            loop = asyncio.get_event_loop()
            
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self.client.auth.sign_up({
                            "email": user_data.email,
                            "password": user_data.password
                        })
                    ),
                    timeout=2.0  # 2 second max timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ [DEBUG] Supabase auth signup timeout for {user_data.email}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service temporarily unavailable"
                )
            
            logger.info(f"🔍 [DEBUG] Supabase signup response - User: {bool(response.user)}, Session: {bool(response.session)}")
            if response.user:
                logger.info(f"🔍 [DEBUG] Auth user created - ID: {response.user.id}, Email: {response.user.email}")
            if response.session:
                logger.info(f"🔍 [DEBUG] Session created - Access token length: {len(response.session.access_token) if response.session.access_token else 0}")
            
            if response.user is None:
                logger.error(f"🔍 [DEBUG] Supabase auth signup failed - no user returned")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Registration failed"
                )
            
            auth_user = response.user
            
            # Fix datetime parsing - Supabase returns ISO format with Z
            created_at = auth_user.created_at
            if isinstance(created_at, str):
                if created_at.endswith('Z'):
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    created_at = datetime.fromisoformat(created_at)
            
            # Step 2: Create profile in public.users table with correct schema
            try:
                profile_data = {
                    "id": str(auth_user.id),
                    "display_name": user_data.full_name or "",
                    "avatar_url": None,
                    "credits_balance": 100,  # Default credits
                    "role": "viewer",  # Default role
                    "created_at": created_at.isoformat()
                }
                
                logger.info(f"🔍 [DEBUG] Profile data prepared: {profile_data}")
                
                # CRITICAL FIX: Use the user's own session to create their profile
                # This aligns with PRD requirement for proper user sync and works with RLS policies
                if response.session and response.session.access_token:
                    logger.info(f"🔍 [DEBUG] Using user session approach for profile creation")
                    # Create authenticated client with user's token
                    user_client = create_client(settings.supabase_url, settings.supabase_anon_key)
                    logger.info(f"🔍 [DEBUG] Created user client, setting session...")
                    
                    # ENHANCED FIX: Proper session setup for RLS policy compliance
                    try:
                        # Method 1: Set session properly
                        user_client.auth.set_session({
                            "access_token": response.session.access_token,
                            "refresh_token": response.session.refresh_token
                        })
                        logger.info(f"🔍 [DEBUG] Session set successfully")
                    except Exception as session_error:
                        logger.warning(f"⚠️ [DEBUG] Session setup failed, trying alternative: {session_error}")
                        # Method 2: Set authorization header directly
                        user_client.auth.session = response.session
                    
                    logger.info(f"🔍 [DEBUG] Session set, attempting profile insert...")
                    result = user_client.table('users').insert(profile_data).execute()
                    logger.info(f"✅ [DEBUG] User session profile creation successful: {auth_user.email}")
                else:
                    logger.warning(f"🔍 [DEBUG] No session available, checking service client")
                    
                    # ENHANCED FALLBACK: Check if service client is valid before using
                    if self.db_client._service_key_valid:
                        logger.info(f"🔍 [DEBUG] Service client is valid, using it")
                        result = self.db_client.service_client.table('users').insert(profile_data).execute()
                        logger.info(f"✅ [DEBUG] Service client profile creation successful: {auth_user.email}")
                    else:
                        logger.error(f"🔍 [DEBUG] Service client invalid, cannot create profile without user session")
                        raise Exception("Cannot create user profile: No valid session or service key")
                
                if result.data and len(result.data) > 0:
                    logger.info(f"✅ Created user profile for {auth_user.email}")
                else:
                    logger.warning(f"⚠️ User profile creation returned no data for {auth_user.email}")
                
                return UserResponse(
                    id=UUID(str(auth_user.id)),
                    email=auth_user.email,
                    display_name=user_data.full_name or "",
                    avatar_url=None,
                    credits_balance=100,
                    role="viewer",
                    created_at=created_at
                )
                
            except Exception as profile_error:
                # If profile creation fails, we still have the auth user
                # This is a critical issue that needs to be logged
                logger.error(f"❌ [DEBUG] Profile creation failed for {auth_user.email}")
                logger.error(f"🔍 [DEBUG] Profile error type: {type(profile_error).__name__}")
                logger.error(f"🔍 [DEBUG] Profile error message: {str(profile_error)}")
                logger.error(f"🔍 [DEBUG] Profile error details: {profile_error}")
                
                # Check if this is a specific error type
                if hasattr(profile_error, 'message'):
                    logger.error(f"🔍 [DEBUG] Supabase error message: {profile_error.message}")
                if hasattr(profile_error, 'details'):
                    logger.error(f"🔍 [DEBUG] Supabase error details: {profile_error.details}")
                    
                # Don't return success - this is the critical PRD issue
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Database error saving new user"
                )
            
        except Exception as e:
            if "already_registered" in str(e) or "already exists" in str(e):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Registration failed: {str(e)}"
            )
    
    async def authenticate_user(self, credentials: UserLogin, request_ip: str = "unknown", user_agent: str = "unknown") -> Optional[UserResponse]:
        """Authenticate user using Supabase Auth and get profile with enhanced monitoring."""
        auth_event = None
        try:
            # Debug logging
            logger.info(f"🔍 [AUTH-SERVICE] Production authentication attempt for: {credentials.email}")
            logger.info(f"🔍 [AUTH-SERVICE] Database available: {self.db_client.is_available()}")
            
            # CRITICAL FIX: Enhanced error handling for Supabase authentication failures
            try:
                # Step 1: Authenticate with Supabase Auth with comprehensive error handling
                logger.info(f"🔐 [AUTH-SERVICE] Attempting Supabase sign_in_with_password for {credentials.email}")
                
                # CRITICAL FIX: Run synchronous Supabase call in executor with timeout protection
                # Using run_in_executor with explicit None (default thread pool) + timeout
                try:
                    loop = asyncio.get_event_loop()
                    response = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.client.auth.sign_in_with_password({
                                "email": credentials.email,
                                "password": credentials.password
                            })
                        ),
                        timeout=2.0  # 2 second max timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"❌ [AUTH-SERVICE] Supabase auth timeout for {credentials.email}")
                    # Log timeout event
                    auth_event = AuthEvent(
                        event_type=AuthEventType.LOGIN_FAILED,
                        user_id=None,
                        email=credentials.email,
                        ip_address=request_ip,
                        user_agent=user_agent,
                        timestamp=datetime.now(timezone.utc),
                        success=False,
                        error_message="Authentication timeout",
                        threat_level=SecurityThreatLevel.LOW
                    )
                    await self.auth_monitor.log_auth_event(auth_event)
                    return None
                except Exception as auth_error:
                    logger.error(f"❌ [AUTH-SERVICE] Supabase auth error: {auth_error}")
                    return None
                
                logger.info(f"🔍 [AUTH-SERVICE] Supabase auth response received")
                logger.info(f"🔍 [AUTH-SERVICE] Response has user: {response.user is not None}")
                logger.info(f"🔍 [AUTH-SERVICE] Response has session: {response.session is not None}")
                
                if response.user is None or response.session is None:
                    logger.warning(f"🚫 [AUTH-SERVICE] Supabase authentication failed - no user or session returned")
                    # Log failed authentication
                    auth_event = AuthEvent(
                        event_type=AuthEventType.LOGIN_FAILED,
                        user_id=None,
                        email=credentials.email,
                        ip_address=request_ip,
                        user_agent=user_agent,
                        timestamp=datetime.now(timezone.utc),
                        success=False,
                        error_message="Invalid credentials",
                        threat_level=SecurityThreatLevel.LOW
                    )
                    await self.auth_monitor.log_auth_event(auth_event)
                    return None
                    
            except Exception as supabase_auth_error:
                logger.error(f"❌ [AUTH-SERVICE] Supabase authentication error: {supabase_auth_error}")
                logger.error(f"❌ [AUTH-SERVICE] Error type: {type(supabase_auth_error).__name__}")
                
                # Enhanced error analysis for Supabase auth failures
                error_str = str(supabase_auth_error).lower()
                if "database error granting user" in error_str:
                    logger.error(f"🚨 [AUTH-SERVICE] CRITICAL: Database error granting user - Supabase RLS or permissions issue")
                    logger.error(f"🔧 [AUTH-SERVICE] SOLUTION: Check Supabase Auth and RLS policies")
                    
                    # SECURITY: Removed database bypass authentication - security vulnerability
                elif "invalid api key" in error_str or "api key" in error_str:
                    logger.error(f"🚨 [AUTH-SERVICE] CRITICAL: Invalid Supabase API key")
                    logger.error(f"🔧 [AUTH-SERVICE] SOLUTION: Verify SUPABASE_ANON_KEY environment variable")
                elif "jwt" in error_str or "token" in error_str:
                    logger.error(f"🚨 [AUTH-SERVICE] CRITICAL: JWT/Token issue with Supabase")
                    logger.error(f"🔧 [AUTH-SERVICE] SOLUTION: Check Supabase JWT settings and keys")
                elif "network" in error_str or "connection" in error_str or "timeout" in error_str:
                    logger.error(f"🚨 [AUTH-SERVICE] CRITICAL: Network connection issue with Supabase")
                    logger.error(f"🔧 [AUTH-SERVICE] SOLUTION: Check Supabase URL and network connectivity")
                else:
                    logger.error(f"🚨 [AUTH-SERVICE] CRITICAL: Unknown Supabase authentication error")
                
                # SECURITY: Removed hardcoded demo user bypass - security vulnerability
                
                # SECURITY: Removed development fallback - security vulnerability removed
                if settings.is_production():
                    # CRITICAL FIX: In production, fail fast with proper error messages
                    logger.error(f"❌ [AUTH-SERVICE] PRODUCTION FAILURE: Supabase authentication failed for {credentials.email}")
                    logger.error(f"❌ [AUTH-SERVICE] Error: {str(supabase_auth_error)}")
                    logger.error(f"❌ [AUTH-SERVICE] This indicates a critical Supabase configuration issue")
                    # Return None to trigger 401 response
                    return None
                
                # Log authentication error and return None for production
                auth_event = AuthEvent(
                    event_type=AuthEventType.LOGIN_FAILED,
                    user_id=None,
                    email=credentials.email,
                    ip_address=request_ip,
                    user_agent=user_agent,
                    timestamp=datetime.now(timezone.utc),
                    success=False,
                    error_message=f"Supabase auth error: {str(supabase_auth_error)}",
                    threat_level=SecurityThreatLevel.MEDIUM
                )
                await self.auth_monitor.log_auth_event(auth_event)
                return None
            
            auth_user = response.user
            auth_session = response.session
            
            # Store session for token creation
            self._current_session = auth_session
            logger.info(f"✅ [AUTH-SERVICE] Authentication successful for {auth_user.email}")
            logger.info(f"🔍 [AUTH-SERVICE] Session stored - access_token length: {len(auth_session.access_token) if auth_session.access_token else 0}")
            logger.info(f"🔍 [AUTH-SERVICE] Session expires_in: {auth_session.expires_in}")
            logger.info(f"🔍 [AUTH-SERVICE] Session user_id: {auth_user.id}")
            
            # Fix datetime parsing - handle different formats
            created_at = auth_user.created_at
            if isinstance(created_at, str):
                if created_at.endswith('Z'):
                    created_at = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    created_at = datetime.fromisoformat(created_at)
            
            # Step 2: Ensure profile exists in public.users table
            try:
                # Check if profile exists - use asyncio executor with timeout protection
                try:
                    loop = asyncio.get_event_loop()
                    profile_result = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: self.db_client.service_client.table('users').select('*').eq('id', str(auth_user.id)).execute()
                        ),
                        timeout=2.0  # 2 second max timeout
                    )
                except asyncio.TimeoutError:
                    logger.error(f"❌ [AUTH-SERVICE] Profile lookup timeout for user {auth_user.id}")
                    # Return basic user info without profile details to prevent total auth failure
                    return UserResponse(
                        id=UUID(str(auth_user.id)),
                        email=auth_user.email,
                        display_name=auth_user.email,
                        avatar_url=None,
                        credits_balance=0,  # Default when profile lookup fails
                        role="viewer",
                        created_at=created_at
                    )
                except Exception as profile_error:
                    logger.error(f"❌ [AUTH-SERVICE] Profile lookup error for user {auth_user.id}: {profile_error}")
                    # Return basic user info without profile details to prevent total auth failure
                    return UserResponse(
                        id=UUID(str(auth_user.id)),
                        email=auth_user.email,
                        display_name=auth_user.email,
                        avatar_url=None,
                        credits_balance=0,  # Default when profile lookup fails
                        role="viewer",
                        created_at=created_at
                    )
                
                if profile_result.data and len(profile_result.data) > 0:
                    profile = profile_result.data[0]
                    
                    user_response = UserResponse(
                        id=UUID(str(auth_user.id)),
                        email=auth_user.email,
                        display_name=profile.get('display_name', ''),
                        avatar_url=profile.get('avatar_url'),
                        credits_balance=profile.get('credits_balance', 100),
                        role=profile.get('role', 'viewer'),
                        created_at=created_at
                    )
                    
                    # Log successful authentication
                    auth_event = AuthEvent(
                        event_type=AuthEventType.LOGIN_SUCCESS,
                        user_id=str(auth_user.id),
                        email=auth_user.email,
                        ip_address=request_ip,
                        user_agent=user_agent,
                        timestamp=datetime.now(timezone.utc),
                        success=True,
                        threat_level=SecurityThreatLevel.LOW
                    )
                    await self.auth_monitor.log_auth_event(auth_event)
                    
                    # Track user activity for session management
                    await self.session_manager.track_user_activity(str(auth_user.id), "login")
                    
                    return user_response
                else:
                    # Profile doesn't exist, create one
                    logger.warning(f"⚠️ [AUTH-SERVICE] User profile missing for {auth_user.email} (ID: {auth_user.id}), creating new profile")
                    profile_data = {
                        "id": str(auth_user.id),
                        "email": str(auth_user.email),  # Add email to profile
                        "display_name": "",
                        "avatar_url": None,
                        "credits_balance": 100,  # Default credits
                        "role": "viewer",
                        "created_at": created_at.isoformat()
                    }
                    
                    try:
                        result = self.db_client.service_client.table('users').insert(profile_data).execute()
                        logger.info(f"✅ [AUTH-SERVICE] Created new profile for {auth_user.email}")
                        logger.info(f"🔍 [AUTH-SERVICE] Profile creation result: {len(result.data) if result.data else 0} records")
                    except Exception as profile_error:
                        logger.error(f"❌ [AUTH-SERVICE] Failed to create profile for {auth_user.email}: {profile_error}")
                        # Continue anyway - we'll use auth data as fallback
                    
                    user_response = UserResponse(
                        id=UUID(str(auth_user.id)),
                        email=auth_user.email,
                        display_name="",
                        avatar_url=None,
                        credits_balance=100,
                        role="viewer",
                        created_at=created_at
                    )
                    
                    # Log successful authentication (fallback profile)
                    auth_event = AuthEvent(
                        event_type=AuthEventType.LOGIN_SUCCESS,
                        user_id=str(auth_user.id),
                        email=auth_user.email,
                        ip_address=request_ip,
                        user_agent=user_agent,
                        timestamp=datetime.now(timezone.utc),
                        success=True,
                        metadata={"profile_created": True},
                        threat_level=SecurityThreatLevel.LOW
                    )
                    await self.auth_monitor.log_auth_event(auth_event)
                    
                    # Track user activity
                    await self.session_manager.track_user_activity(str(auth_user.id), "login")
                    
                    return user_response
                    
            except Exception as profile_error:
                # If profile lookup fails, log the error but still return user
                logger.error(f"❌ Profile lookup/creation failed for {auth_user.email}: {profile_error}")
                
                # Return basic user data
                return UserResponse(
                    id=UUID(str(auth_user.id)),
                    email=auth_user.email,
                    display_name="",
                    avatar_url=None,
                    credits_balance=100,
                    role="viewer",
                    created_at=created_at
                )
            
        except Exception as e:
            # Log the actual error for debugging with full traceback
            logger.error(f"Authentication error for {credentials.email}: {e}", exc_info=True)
            # Also log the type of error to help with debugging
            logger.error(f"Error type: {type(e).__name__}")
            
            # Log authentication error event
            if not auth_event:  # Only if we haven't already logged an event
                auth_event = AuthEvent(
                    event_type=AuthEventType.LOGIN_FAILED,
                    user_id=None,
                    email=credentials.email,
                    ip_address=request_ip,
                    user_agent=user_agent,
                    timestamp=datetime.now(timezone.utc),
                    success=False,
                    error_message=str(e),
                    threat_level=SecurityThreatLevel.MEDIUM
                )
                await self.auth_monitor.log_auth_event(auth_event)
            
            return None
    
    async def create_access_token(self, user: UserResponse, refresh_token: str = None) -> Token:
        """Create access token using proper Supabase JWT tokens for production."""
        logger.info(f"🔍 [AUTH-SERVICE] Creating production access token for user {user.id}")
        logger.info(f"🔍 [AUTH-SERVICE] Environment: {settings.environment}, production: {settings.is_production()}")
        
        # SECURITY: Removed hardcoded demo user token creation - security vulnerability
        
        # SECURITY: Removed development fallback - security vulnerability removed
        
        # PRODUCTION-GRADE: Use real Supabase JWT tokens in production
        try:
            # Primary: Use the stored session from authentication (most reliable)
            logger.info(f"🔍 [AUTH-SERVICE] Token creation debug - has _current_session: {hasattr(self, '_current_session')}")
            if hasattr(self, '_current_session'):
                logger.info(f"🔍 [AUTH-SERVICE] _current_session value: {self._current_session is not None}")
                if self._current_session:
                    logger.info(f"🔍 [AUTH-SERVICE] Session access_token exists: {hasattr(self._current_session, 'access_token') and self._current_session.access_token is not None}")
            
            if hasattr(self, '_current_session') and self._current_session:
                session = self._current_session
                if session.access_token:
                    # CRITICAL FIX: Validate that this is a proper JWT token
                    if self._is_valid_jwt_token(session.access_token):
                        logger.info(f"✅ [AUTH-SERVICE] Using valid Supabase JWT token for user {user.id}")
                        logger.info(f"🔍 [AUTH-SERVICE] JWT token length: {len(session.access_token)}")
                        token = Token(
                            access_token=session.access_token,
                            token_type="bearer", 
                            expires_in=session.expires_in or settings.jwt_expiration_seconds,
                            user=user
                        )
                        
                        # Register token for automatic refresh management
                        try:
                            await self.token_manager.register_token(token, user, getattr(session, 'refresh_token', refresh_token))
                        except Exception as token_mgmt_error:
                            logger.warning(f"⚠️ [AUTH-SERVICE] Token management registration failed: {token_mgmt_error}")
                        
                        return token
                    else:
                        logger.warning(f"⚠️ [AUTH-SERVICE] Stored session access_token is not a valid JWT")
                else:
                    logger.warning(f"⚠️ [AUTH-SERVICE] Stored session has no access_token")
            
            # Secondary: Try to get current session from client with timeout protection
            logger.info(f"🔍 [AUTH-SERVICE] Attempting to get current session from client")
            try:
                loop = asyncio.get_event_loop()
                session = await asyncio.wait_for(
                    loop.run_in_executor(None, self.client.auth.get_session),
                    timeout=2.0  # 2 second max timeout
                )
                logger.info(f"🔍 [AUTH-SERVICE] Current session retrieved: {session is not None}")
                if session:
                    logger.info(f"🔍 [AUTH-SERVICE] Current session has access_token: {hasattr(session, 'access_token') and session.access_token is not None}")
                
                if session and hasattr(session, 'access_token') and session.access_token:
                    if self._is_valid_jwt_token(session.access_token):
                        logger.info(f"✅ [AUTH-SERVICE] Using current valid Supabase JWT token for user {user.id}")
                        logger.info(f"🔍 [AUTH-SERVICE] Current JWT token length: {len(session.access_token)}")
                        return Token(
                            access_token=session.access_token,
                            token_type="bearer", 
                            expires_in=getattr(session, 'expires_in', settings.jwt_expiration_seconds),
                            user=user
                        )
                    else:
                        logger.warning(f"⚠️ [AUTH-SERVICE] Current session access_token is not a valid JWT")
                else:
                    logger.warning(f"⚠️ [AUTH-SERVICE] Current session has no valid access_token")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ [AUTH-SERVICE] Get current session timeout")
            except Exception as session_error:
                logger.warning(f"⚠️ [AUTH-SERVICE] Failed to get current session: {session_error}")
            
            # CRITICAL FIX: In production, fail fast instead of creating custom tokens
            if settings.is_production():
                logger.error(f"❌ [AUTH-SERVICE] PRODUCTION ERROR: No valid Supabase JWT token available for user {user.id}")
                logger.error(f"❌ [AUTH-SERVICE] This indicates Supabase authentication is not working properly")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authentication service unavailable - no valid JWT token"
                )
            
            # Development fallback only - use proper JWT
            logger.warning(f"⚠️ [AUTH-SERVICE] Development fallback: No Supabase session available, creating JWT token for user {user.id}")
            try:
                from utils.security import JWTSecurity
                
                dev_jwt = JWTSecurity.create_access_token(
                    user_id=str(user.id),
                    email=user.email,
                    additional_claims={
                        "role": user.role,
                        "credits_balance": user.credits_balance,
                        "display_name": user.display_name or ""
                    }
                )
                
                return Token(
                    access_token=dev_jwt,
                    token_type="bearer",
                    expires_in=settings.jwt_expiration_seconds,
                    user=user
                )
            except Exception as jwt_dev_error:
                logger.error(f"❌ [AUTH-SERVICE] Development JWT creation failed: {jwt_dev_error}")
                # Final fallback
                return Token(
                    access_token=f"dev_token_{user.id}",
                    token_type="bearer",
                    expires_in=settings.jwt_expiration_seconds,
                    user=user
                )
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            logger.error(f"❌ [AUTH-SERVICE] Error creating access token for user {user.id}: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            
            # In production, fail fast
            if settings.is_production():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Authentication service error"
                )
            
            # Development fallback only
            logger.warning(f"⚠️ [AUTH-SERVICE] Development fallback: Using emergency JWT for user {user.id}")
            try:
                from utils.security import JWTSecurity
                
                emergency_jwt = JWTSecurity.create_access_token(
                    user_id=str(user.id),
                    email=user.email,
                    additional_claims={
                        "role": user.role,
                        "credits_balance": user.credits_balance,
                        "display_name": user.display_name or ""
                    }
                )
                
                return Token(
                    access_token=emergency_jwt,
                    token_type="bearer",
                    expires_in=settings.jwt_expiration_seconds,
                    user=user
                )
            except Exception as jwt_emergency_error:
                logger.error(f"❌ [AUTH-SERVICE] Emergency JWT creation failed: {jwt_emergency_error}")
                # Absolute final fallback
                return Token(
                    access_token=f"dev_token_{user.id}",
                    token_type="bearer",
                    expires_in=settings.jwt_expiration_seconds,
                    user=user
                )
    
    def _is_valid_jwt_token(self, token: str) -> bool:
        """Validate that a token is a proper JWT format."""
        try:
            # JWT tokens should have 3 parts separated by dots
            parts = token.split('.')
            if len(parts) != 3:
                return False
            
            # Each part should be base64-encoded
            import base64
            for part in parts:
                # Add padding if needed
                padded = part + '=' * (4 - len(part) % 4)
                try:
                    base64.b64decode(padded)
                except Exception:
                    return False
            
            # Should not have our custom prefixes
            custom_prefixes = ['demo_token_', 'mock_token_', 'supabase_token_', 'emergency_token_', 'dev_token_']
            return not any(token.startswith(prefix) for prefix in custom_prefixes)
            
        except Exception as e:
            logger.warning(f"⚠️ [AUTH-SERVICE] JWT validation error: {e}")
            return False
    
    async def get_user_by_id(self, user_id: UUID) -> Optional[UserResponse]:
        """Get user by ID from local database."""
        try:
            # SECURITY: Removed development fallback - security vulnerability removed
            
            # Use service client to bypass RLS
            result = self.db_client.service_client.table('users').select('*').eq('id', str(user_id)).execute()
            
            if result.data and len(result.data) > 0:
                user_data = result.data[0]
                return UserResponse(
                    id=UUID(user_data['id']),
                    email=user_data.get('email', ''),
                    display_name=user_data.get('display_name', ''),
                    avatar_url=user_data.get('avatar_url'),
                    credits_balance=user_data.get('credits_balance', 100),
                    role=user_data.get('role', 'viewer'),
                    created_at=datetime.fromisoformat(user_data['created_at'])
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None
    
    async def refresh_access_token(self, refresh_token: str) -> Optional[Token]:
        """Refresh access token using Supabase refresh token."""
        try:
            logger.info("🔄 [AUTH-SERVICE] Attempting token refresh")
            
            # SECURITY: Removed development mode bypass - security vulnerability removed
            
            # Use Supabase refresh token to get new session with timeout protection
            loop = asyncio.get_event_loop()
            try:
                response = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: self.client.auth.refresh_session(refresh_token)
                    ),
                    timeout=2.0  # 2 second max timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"❌ [AUTH-SERVICE] Token refresh timeout")
                return None
            
            if response.session is None or response.user is None:
                logger.warning("⚠️ [AUTH-SERVICE] Token refresh failed - invalid refresh token")
                return None
            
            session = response.session
            auth_user = response.user
            
            # Store new session
            self._current_session = session
            logger.info(f"✅ [AUTH-SERVICE] Token refresh successful for user {auth_user.id}")
            
            # Get user profile
            user_profile = await self.get_user_by_id(UUID(str(auth_user.id)))
            if not user_profile:
                # Create basic user profile if not found
                user_profile = UserResponse(
                    id=UUID(str(auth_user.id)),
                    email=auth_user.email,
                    display_name="",
                    avatar_url=None,
                    credits_balance=100,
                    role="viewer",
                    created_at=datetime.now(timezone.utc)
                )
            
            return Token(
                access_token=session.access_token,
                token_type="bearer",
                expires_in=session.expires_in or settings.jwt_expiration_seconds,
                user=user_profile
            )
            
        except Exception as e:
            logger.error(f"❌ [AUTH-SERVICE] Token refresh error: {e}")
            return None
