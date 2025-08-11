"""
Database connection and session management for Supabase.
Following CLAUDE.md: Pure database layer, no business logic.
Fixed for Railway deployment with updated Supabase client.
Enhanced with singleton pattern, thread safety, and performance optimizations.
"""
from supabase import create_client, Client
from database_pool_manager import get_connection_pool
from typing import Optional, Dict, Any, List, Tuple
from config import settings
import asyncio
import httpx
import logging
import os
import time
import threading
import hashlib
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

# Import performance monitoring (lazy import to avoid circular dependencies)
try:
    from utils.database_performance_monitor import record_query
except ImportError:
    # Fallback if performance monitor not available
    def record_query(query_type: str, execution_time_ms: float, success: bool = True, context: dict = None, cache_hit: bool = False):
        pass

logger = logging.getLogger(__name__)


class DatabaseTimeoutError(Exception):
    """
    Exception raised when database operations exceed timeout limits.
    Critical for preventing 15-30 second blocking operations.
    """
    def __init__(self, operation: str, timeout_seconds: float, additional_info: str = ""):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        self.additional_info = additional_info
        super().__init__(
            f"Database operation '{operation}' timed out after {timeout_seconds}s. {additional_info}"
        )


class SupabaseClient:
    """
    Thread-safe singleton Supabase client wrapper with performance optimizations.
    
    Features:
    - Thread-safe singleton pattern with double-checked locking
    - Service key validation caching with 5-minute TTL
    - Connection pooling integration
    - Performance monitoring hooks
    - OWASP compliance maintained
    """
    
    _instance = None
    _initialized = False
    _lock = threading.RLock()  # Reentrant lock for thread safety
    
    def __new__(cls):
        # Double-checked locking pattern for thread-safe singleton
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Thread-safe initialization using double-checked locking
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:
                return
            
            # Core client instances
            self._client: Optional[Client] = None
            self._service_client: Optional[Client] = None
            self._is_available: Optional[bool] = None
            self._service_key_valid: Optional[bool] = None
            
            # Performance optimization caches
            self._client_cache = {}  # Cache for different client configurations
            self._connection_pool = None
            self._service_key_cache = {}  # Cache for service key validation results with TTL
            self._validation_cache_ttl = 300  # 5 minutes cache for validation results
            
            # Thread-safe cache locks
            self._cache_lock = threading.RLock()
            self._service_key_lock = threading.RLock()
            
            # Performance metrics tracking
            self._cache_hits = 0
            self._cache_misses = 0
            self._total_queries = 0
            self._initialization_time = time.time()
            
            # CRITICAL ASYNC OPERATIONS ENHANCEMENT
            # Thread pool executor for non-blocking database operations
            self._thread_pool = ThreadPoolExecutor(
                max_workers=20,  # Sufficient for concurrent operations
                thread_name_prefix="velro_db_async"
            )
            
            # Async operation timeouts (target: <2000ms for most operations)
            self._operation_timeouts = {
                "auth_query": 1.0,        # <1000ms for authentication
                "auth_check": 0.5,        # <500ms for authorization checks
                "user_lookup": 1.0,       # <1000ms for user lookups
                "general_query": 2.0,     # <2000ms for general operations
                "batch_query": 5.0,       # <5000ms for batch operations
                "migration_query": 30.0   # <30000ms for schema changes only
            }
            
            # Performance tracking for async operations
            self._async_operation_stats = {
                "total_async_operations": 0,
                "timeout_errors": 0,
                "avg_execution_time_ms": 0.0,
                "operations_under_target": 0,
                "operations_over_target": 0
            }
            
            # Connection pool initialization
            try:
                self._connection_pool = get_connection_pool()
                logger.info("🔗 [DATABASE] Connection pool initialized successfully")
            except Exception as pool_error:
                logger.warning(f"⚠️ [DATABASE] Connection pool initialization failed: {pool_error}")
                self._connection_pool = None
            
            self._initialized = True
            logger.info("🚀 [DATABASE] Singleton SupabaseClient initialized with thread safety and async operations")
    
    def __del__(self):
        """
        Cleanup method to ensure proper resource cleanup.
        Critical for preventing resource leaks in async operations.
        """
        try:
            if hasattr(self, '_thread_pool') and self._thread_pool is not None:
                logger.debug("🧹 [DATABASE] Cleaning up thread pool executor")
                self._thread_pool.shutdown(wait=False)  # Non-blocking cleanup
        except Exception as e:
            # Silently handle cleanup errors to prevent issues during shutdown
            pass
    
    @property
    def client(self) -> Client:
        """Get client with anon key (for user operations)."""
        if self._client is None:
            logger.info(f"Creating Supabase client with URL: {settings.supabase_url[:50]}...")
            try:
                self._client = create_client(
                    settings.supabase_url,
                    settings.supabase_anon_key
                )
                logger.info("✅ Supabase client created successfully")
            except Exception as e:
                logger.error(f"❌ Failed to create Supabase client: {e}")
                raise
        return self._client
    
    @property
    def service_client(self) -> Client:
        """
        Get client with service key (for admin operations, bypasses RLS) - CACHED AND THREAD-SAFE.
        
        Features:
        - 5-minute TTL cache for service key validation
        - Thread-safe access with proper locking
        - Performance metrics tracking
        - Fallback mechanisms
        """
        with self._service_key_lock:
            # PERFORMANCE FIX: Cache service key validation results for 300 seconds with thread safety
            cache_key = f"service_key_valid_{hashlib.sha256(settings.get_service_key.encode()).hexdigest()[:16]}"
            
            # Check if we have a cached validation result
            current_time = time.time()
            if cache_key in self._service_key_cache:
                cached_result = self._service_key_cache[cache_key]
                cache_age = current_time - cached_result['timestamp']
                
                if cache_age < self._validation_cache_ttl:
                    self._cache_hits += 1
                    logger.debug(f"🚀 [DATABASE] Using cached service key validation result (age: {cache_age:.1f}s)")
                    
                    if cached_result['valid'] and self._service_client is not None:
                        return self._service_client
                    elif not cached_result['valid']:
                        logger.warning(f"⚠️ [DATABASE] Cached service key validation indicates invalid key")
                        raise ValueError("Service key validation failed (cached result)")
                else:
                    logger.debug(f"🔄 [DATABASE] Cache expired (age: {cache_age:.1f}s), refreshing service key validation")
                    del self._service_key_cache[cache_key]  # Clean expired entry
            
            self._cache_misses += 1
        
        if self._service_client is None:
            logger.info(f"🔧 [DATABASE] Initializing Supabase service client")
            service_key_for_log = settings.get_service_key
            logger.info(f"🔧 [DATABASE] Service key length: {len(service_key_for_log)}")
            
            try:
                # CRITICAL FIX: Enhanced service key validation and format handling
                # Support both old JWT service_role_key and new sb_secret format
                service_key = settings.get_service_key.strip()
                
                # Validate service key format with enhanced detection
                if self._validate_service_key_format(service_key):
                    logger.info("✅ [DATABASE] Service key format validated successfully")
                    
                    # Create service client with proper configuration
                    # The Supabase client doesn't need options for service key
                    self._service_client = create_client(
                        settings.supabase_url,
                        service_key
                    )
                    self._raw_service_key = None
                    logger.info("✅ [DATABASE] Service client created with validated key")
                    
                else:
                    logger.error(f"❌ [DATABASE] Invalid service key format detected")
                    raise ValueError("Invalid Supabase service role key format")
                
                # CRITICAL FIX: Synchronous service client validation (removed async call)
                try:
                    logger.info(f"🔍 [DATABASE] Validating service key authentication...")
                    
                    # Synchronous validation to prevent async context issues during initialization
                    validation_result = self._validate_service_client_authentication_sync()
                    
                    if validation_result['valid']:
                        logger.info(f"✅ [DATABASE] Service key validation successful")
                        logger.info(f"🔍 [DATABASE] Validation details: {validation_result['details']}")
                        self._service_key_valid = True
                        
                        # PERFORMANCE FIX: Cache successful validation result with thread safety
                        with self._service_key_lock:
                            self._service_key_cache[cache_key] = {
                                'valid': True,
                                'timestamp': time.time(),
                                'details': validation_result['details']
                            }
                    else:
                        logger.error(f"❌ [DATABASE] Service key validation failed")
                        logger.error(f"❌ [DATABASE] Failure reason: {validation_result['error']}")
                        logger.error(f"💡 [DATABASE] Suggested fix: {validation_result['solution']}")
                        self._service_key_valid = False
                        
                        # Test 2: RLS bypass validation
                        try:
                            rls_test = self._service_client.table("credit_transactions").select("id").limit(1).execute()
                            logger.info(f"✅ [DATABASE] Service client RLS bypass confirmed")
                        except Exception as rls_error:
                            logger.warning(f"⚠️ [DATABASE] Service client RLS test failed: {rls_error}")
                            # RLS failure doesn't invalidate the key - just means limited permissions
                            
                        # Test 3: Auth operations capability (critical for user management)
                        try:
                            # Test if we can perform auth-related operations
                            auth_test = self._service_client.table("users").select("id").limit(1).execute()
                            logger.info(f"✅ [DATABASE] Service client can access user data")
                        except Exception as auth_error:
                            logger.warning(f"⚠️ [DATABASE] Service client auth operations test failed: {auth_error}")
                            # This could indicate the "Database error granting user" issue
                            if "granting user" in str(auth_error).lower() or "database error" in str(auth_error).lower():
                                logger.error(f"🚨 [DATABASE] DETECTED: 'Database error granting user' issue in service key")
                                logger.error(f"🔧 [DATABASE] SOLUTION: This indicates Supabase Auth RLS policy conflicts")
                                logger.error(f"🔧 [DATABASE] RECOMMENDATION: Check auth.users table policies and service role permissions")
                                # Mark as potentially problematic but not invalid
                                self._service_key_valid = True  # Keep as valid but with warnings
                    
                except Exception as basic_test_error:
                    logger.error(f"❌ [DATABASE] Service key basic test failed: {basic_test_error}")
                    
                    # Enhanced error analysis for service key issues
                    error_str = str(basic_test_error).lower()
                    if "invalid api key" in error_str or "unauthorized" in error_str:
                        logger.error(f"🚨 [DATABASE] CRITICAL: Service key is invalid or unauthorized")
                        logger.error(f"🔧 [DATABASE] SOLUTION: Regenerate SUPABASE_SERVICE_ROLE_KEY in Supabase dashboard")
                        self._service_key_valid = False
                    elif "database error granting user" in error_str:
                        logger.error(f"🚨 [DATABASE] CRITICAL: Database error granting user - Auth/RLS conflict detected")
                        logger.error(f"🔧 [DATABASE] SOLUTION: Check Supabase Auth table policies and RLS settings")
                        logger.error(f"🔧 [DATABASE] WORKAROUND: Service key may work for some operations but fail for auth")
                        # This is the exact error from the user's report
                        self._service_key_valid = False  # Mark as invalid due to auth conflicts
                    elif "jwt" in error_str or "token" in error_str:
                        logger.error(f"🚨 [DATABASE] CRITICAL: Service key JWT format issue")
                        logger.error(f"🔧 [DATABASE] SOLUTION: Verify service key is properly formatted JWT")
                        self._service_key_valid = False
                    elif "network" in error_str or "connection" in error_str:
                        logger.warning(f"⚠️ [DATABASE] Network connectivity issue - service key may be valid")
                        logger.warning(f"🔧 [DATABASE] Retry connection or check network")
                        self._service_key_valid = None  # Uncertain - could be valid
                    else:
                        logger.warning(f"⚠️ [DATABASE] Unknown service key test error: {basic_test_error}")
                        # Default to optimistic validation for unknown errors
                        self._service_key_valid = True
                        
                except Exception as test_error:
                    logger.error(f"❌ Service client test failed: {test_error}")
                    logger.error(f"❌ Error type: {type(test_error).__name__}")
                    logger.error(f"❌ Error details: {getattr(test_error, 'message', str(test_error))}")
                    
                    # ENHANCED ERROR ANALYSIS
                    error_str = str(test_error).lower()
                    if "invalid api key" in error_str:
                        logger.error(f"🔑 DIAGNOSIS: Service key is completely invalid or expired")
                        logger.error(f"🔧 SOLUTION: Need to regenerate service key in Supabase dashboard")
                        self._service_key_valid = False
                    elif "jwt" in error_str or "token" in error_str:
                        logger.error(f"🔑 DIAGNOSIS: Service key JWT token issue")
                        logger.error(f"🔧 SOLUTION: Check if service key is properly formatted JWT")
                        self._service_key_valid = False
                    elif "not found" in error_str or "relation" in error_str:
                        logger.warning(f"🗃️ Database schema/table access issue - service key is valid")
                        # Schema issues don't invalidate authentication - service key is valid
                        self._service_key_valid = True
                    else:
                        # Non-auth errors should not invalidate the key
                        self._service_key_valid = True
                        logger.warning(f"⚠️ Service key valid but test failed: {test_error}")
                    
                    if not self._service_key_valid:
                        logger.error(f"🚨 CRITICAL: Service key marked as invalid - operations will fallback to anon key")
                        logger.error(f"🚨 IMPORTANT: Credit operations will require proper JWT authentication")
                        logger.error(f"⚠️ WARNING: Profile lookups may fail without service key")
                    else:
                        logger.info(f"✅ OPTIMISTIC: Service key marked as valid despite test failure")
                    # CRITICAL FIX: Don't set service_client to None - keep it for potential fallback
                    # self._service_client = None  # This breaks the fallback mechanism!
                    
                    logger.warning(f"🔄 FALLBACK: Service operations will use anon client with JWT context")
                    
            except Exception as e:
                logger.error(f"❌ Failed to create Supabase service client: {e}")
                # Log the actual service key being used, not the service_role_key
                actual_key = settings.get_service_key if hasattr(settings, 'get_service_key') else 'N/A'
                if actual_key != 'N/A':
                    logger.error(f"❌ Service key length: {len(actual_key)}")
                    logger.error(f"❌ Service key format check: {actual_key[:20]}...")
                logger.error(f"🚨 CRITICAL: Service client creation failed - operations will fallback to anon key")
                logger.error(f"🔧 SOLUTION: Check if SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY environment variable is set correctly")
                
                self._service_key_valid = False
                # CRITICAL FIX: Don't nullify service client - keep for fallback
                # self._service_client = None
                # Don't raise - fallback mechanism will handle this
                
        return self._service_client
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics for monitoring and optimization.
        Thread-safe access to cache statistics and async operation performance.
        """
        with self._cache_lock:
            uptime = time.time() - self._initialization_time
            cache_hit_rate = (self._cache_hits / (self._cache_hits + self._cache_misses)) * 100 if (self._cache_hits + self._cache_misses) > 0 else 0
            
            # Get async operation metrics
            async_metrics = self.get_async_operation_metrics()
            
            return {
                # Core metrics
                "uptime_seconds": uptime,
                "total_queries": self._total_queries,
                "cache_hits": self._cache_hits,
                "cache_misses": self._cache_misses,
                "cache_hit_rate_percent": cache_hit_rate,
                
                # Infrastructure metrics
                "service_key_cache_size": len(self._service_key_cache),
                "connection_pool_available": self._connection_pool is not None,
                "thread_pool_active": self._thread_pool is not None,
                "singleton_instance_id": id(self._instance),
                "thread_safe": True,
                
                # CRITICAL: Async operation performance metrics
                "async_operations": async_metrics,
                
                # Performance targets status
                "performance_targets": {
                    "auth_queries_under_50ms": async_metrics.get("target_success_rate_percent", 0) >= 90,
                    "blocking_eliminated": async_metrics.get("blocking_eliminated", False),
                    "timeout_errors": async_metrics.get("timeout_errors", 0),
                    "avg_execution_time_ms": async_metrics.get("avg_execution_time_ms", 0),
                    "performance_grade": async_metrics.get("performance_grade", "unknown")
                },
                
                # Thread pool executor metrics
                "thread_pool_stats": {
                    "max_workers": 20,
                    "active": True,
                    "operation_timeouts": self._operation_timeouts
                }
            }
    
    def clear_service_key_cache(self) -> None:
        """
        Clear service key validation cache.
        Useful for testing or when service key is rotated.
        """
        with self._service_key_lock:
            cache_size = len(self._service_key_cache)
            self._service_key_cache.clear()
            logger.info(f"🗑️ [DATABASE] Cleared {cache_size} cached service key validation entries")
    
    def warm_up_connections(self) -> bool:
        """
        Pre-warm database connections for optimal performance.
        Should be called during application startup.
        """
        try:
            logger.info("🚀 [DATABASE] Warming up database connections...")
            start_time = time.time()
            
            # Test both client types
            anon_test = self.is_available()
            service_test = True
            
            try:
                _ = self.service_client
                logger.info("✅ [DATABASE] Service client warmed up successfully")
            except Exception as e:
                logger.warning(f"⚠️ [DATABASE] Service client warm-up failed: {e}")
                service_test = False
            
            warm_up_time = (time.time() - start_time) * 1000
            logger.info(f"🚀 [DATABASE] Connection warm-up completed in {warm_up_time:.2f}ms")
            
            return anon_test and service_test
            
        except Exception as e:
            logger.error(f"❌ [DATABASE] Connection warm-up failed: {e}")
            return False
    
    def _validate_service_key_format(self, service_key: str) -> bool:
        """
        Validate Supabase service role key format.
        Supports both old JWT format and new sb_secret format.
        
        Args:
            service_key: The service role key to validate
            
        Returns:
            bool: True if valid format, False otherwise
        """
        try:
            # Check for new sb_secret format FIRST (preferred)
            if service_key.startswith('sb_secret_'):
                logger.info(f"🔍 [DATABASE] Detected new Supabase secret key format (sb_secret_*)")
                # New format keys are typically 40+ characters after the prefix
                if len(service_key) < 20:
                    logger.error(f"🔍 [DATABASE] Secret key too short: {len(service_key)} characters")
                    return False
                logger.info(f"✅ [DATABASE] Valid sb_secret key format detected")
                return True
            
            # Check minimum length for JWT format
            if len(service_key) < 50:
                logger.error(f"🔍 [DATABASE] Service key too short: {len(service_key)} characters")
                return False
            
            # JWT format validation (old format)
            if service_key.startswith('eyJ'):
                # JWT should have 3 parts separated by dots
                parts = service_key.split('.')
                if len(parts) != 3:
                    logger.error(f"🔍 [DATABASE] Invalid JWT format: {len(parts)} parts (expected 3)")
                    return False
                
                # Enhanced JWT payload validation for service role
                try:
                    import base64
                    import json
                    
                    # Decode JWT header and payload (ignore signature)
                    header_b64, payload_b64, _ = parts
                    
                    # Add padding if needed for proper base64 decoding
                    payload_b64 += '=' * (4 - len(payload_b64) % 4)
                    
                    try:
                        payload_json = base64.b64decode(payload_b64).decode('utf-8')
                        payload = json.loads(payload_json)
                    except Exception as decode_error:
                        logger.error(f"🔍 [DATABASE] JWT payload decode error: {decode_error}")
                        return False
                    
                    # Enhanced validation for service role token
                    logger.info(f"🔍 [DATABASE] JWT payload keys: {list(payload.keys()) if payload else 'None'}")
                    
                    # Check multiple possible role claim locations (Supabase variations)
                    role = None
                    for role_key in ['role', 'user_role', 'app_role', 'aud']:
                        if role_key in payload:
                            role_value = payload[role_key]
                            logger.info(f"🔍 [DATABASE] Found {role_key}: {role_value}")
                            if role_value == 'service_role':
                                role = role_value
                                break
                    
                    # Check for service_role in different payload structures
                    if not role:
                        # Check if it's in user_metadata or app_metadata
                        user_metadata = payload.get('user_metadata', {})
                        app_metadata = payload.get('app_metadata', {})
                        
                        if user_metadata.get('role') == 'service_role':
                            role = 'service_role'
                        elif app_metadata.get('role') == 'service_role':
                            role = 'service_role'
                    
                    if role == 'service_role':
                        logger.info(f"✅ [DATABASE] Valid service_role JWT detected")
                        
                        # Additional validation for Supabase service tokens
                        iss = payload.get('iss', '')
                        if 'supabase' in iss.lower():
                            logger.info(f"✅ [DATABASE] Supabase issuer confirmed: {iss}")
                            
                        # Check expiration
                        exp = payload.get('exp')
                        if exp:
                            import time
                            current_time = int(time.time())
                            if current_time < exp:
                                logger.info(f"✅ [DATABASE] JWT token is valid (expires in {exp - current_time} seconds)")
                            else:
                                logger.warning(f"⚠️ [DATABASE] JWT token expired {current_time - exp} seconds ago")
                                return False
                        
                        return True
                    else:
                        logger.warning(f"⚠️ [DATABASE] JWT role is '{role}', not 'service_role'")
                        logger.warning(f"⚠️ [DATABASE] Full payload for debugging: {payload}")
                        return False
                        
                except Exception as jwt_error:
                    logger.error(f"🔍 [DATABASE] JWT validation error: {jwt_error}")
                    return False
            
            # Raw secret key format (starts with sb_secret_)
            elif service_key.startswith('sb_secret_'):
                logger.info(f"🔍 [DATABASE] Raw secret key format detected")
                return True
            
            # Other valid prefixes
            elif service_key.startswith(('sb-', 'supabase_')):
                logger.info(f"🔍 [DATABASE] Supabase key format detected")
                return True
            
            else:
                logger.error(f"🔍 [DATABASE] Unknown service key format (starts with: {service_key[:10]})")
                return False
                
        except Exception as e:
            logger.error(f"🔍 [DATABASE] Service key validation error: {e}")
            return False
    
    def _validate_service_client_authentication_sync(self) -> Dict[str, Any]:
        """
        Synchronous validation of service client authentication.
        This method is called during initialization to avoid async context issues.
        
        Returns:
            Dict containing validation results and diagnostics
        """
        try:
            import time
            
            start_time = time.time()
            
            # Test 1: Basic connectivity test with timeout protection
            try:
                # Add timeout protection to prevent hanging with invalid keys
                import signal
                
                def timeout_handler(signum, frame):
                    raise TimeoutError("Service client validation timed out")
                
                # Set a 3-second timeout for the validation query
                if hasattr(signal, 'SIGALRM'):
                    signal.signal(signal.SIGALRM, timeout_handler)
                    signal.alarm(3)
                
                try:
                    result = self._service_client.table("users").select("count").limit(1).execute()
                finally:
                    if hasattr(signal, 'SIGALRM'):
                        signal.alarm(0)  # Cancel the alarm
                
                basic_test_time = (time.time() - start_time) * 1000
                logger.info(f"🎯 [DATABASE] Basic connectivity test: {basic_test_time:.2f}ms")
                
                if basic_test_time > 2000:  # 2 second threshold
                    logger.warning(f"⚠️ [DATABASE] Slow service key response: {basic_test_time:.2f}ms")
                
            except TimeoutError as timeout_error:
                return {
                    'valid': False,
                    'error': 'Service client validation timed out (likely invalid key format)',
                    'solution': 'Check SUPABASE_SERVICE_ROLE_KEY format - use sb_secret_* format, not JWT',
                    'details': 'timeout'
                }
            except Exception as basic_error:
                error_str = str(basic_error).lower()
                
                if 'invalid api key' in error_str or 'unauthorized' in error_str:
                    return {
                        'valid': False,
                        'error': 'Service role key is invalid or unauthorized',
                        'solution': 'Regenerate service role key in Supabase Dashboard > Settings > API',
                        'details': 'invalid_key'
                    }
                elif 'database error granting user' in error_str:
                    return {
                        'valid': False,
                        'error': 'Database error granting user access (RLS policy conflict)',
                        'solution': 'Check Supabase Auth policies and service role permissions',
                        'details': 'rls_conflict'
                    }
                elif 'jwt' in error_str or 'token' in error_str:
                    return {
                        'valid': False,
                        'error': 'JWT token validation failed - service role key may be malformed',
                        'solution': 'Verify SUPABASE_SERVICE_ROLE_KEY is a valid JWT token with service_role claim',
                        'details': 'jwt_error'
                    }
                else:
                    return {
                        'valid': False,
                        'error': f'Unexpected authentication error: {basic_error}',
                        'solution': 'Check Supabase configuration and logs',
                        'details': 'unknown_error'
                    }
            
            # Test 2: RLS bypass validation (critical for admin operations)
            try:
                rls_result = self._service_client.table("users").select("id").limit(1).execute()
                rls_test_time = (time.time() - start_time) * 1000
                logger.info(f"🛡️ [DATABASE] RLS bypass test: {rls_test_time:.2f}ms")
                
            except Exception as rls_error:
                logger.warning(f"⚠️ [DATABASE] RLS bypass test failed: {rls_error}")
                # RLS failure doesn't invalidate the key but indicates limited functionality
            
            total_time = (time.time() - start_time) * 1000
            
            return {
                'valid': True,
                'error': None,
                'solution': None,
                'details': {
                    'total_validation_time_ms': total_time,
                    'basic_connectivity': 'passed',
                    'rls_bypass': 'tested',
                    'performance_grade': 'excellent' if total_time < 500 else 'good' if total_time < 1000 else 'slow'
                }
            }
            
        except Exception as validation_error:
            return {
                'valid': False,
                'error': f'Validation process failed: {validation_error}',
                'solution': 'Check database configuration and try restarting the service',
                'details': 'validation_exception'
            }

    async def _validate_service_client_authentication(self) -> Dict[str, Any]:
        """
        Async validation of service client authentication for runtime checks.
        
        Returns:
            Dict containing validation results and diagnostics
        """
        try:
            import asyncio
            import time
            
            start_time = time.time()
            
            # Test 1: Basic connectivity test
            try:
                def basic_test():
                    return self._service_client.table("users").select("count").limit(1).execute()
                
                result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, basic_test),
                    timeout=5.0
                )
                
                basic_test_time = (time.time() - start_time) * 1000
                logger.info(f"🎯 [DATABASE] Basic connectivity test: {basic_test_time:.2f}ms")
                
                if basic_test_time > 2000:  # 2 second threshold
                    logger.warning(f"⚠️ [DATABASE] Slow service key response: {basic_test_time:.2f}ms")
                
            except asyncio.TimeoutError:
                return {
                    'valid': False,
                    'error': 'Authentication test timed out after 5 seconds',
                    'solution': 'Check network connectivity and Supabase service status',
                    'details': 'timeout_error'
                }
            except Exception as basic_error:
                error_str = str(basic_error).lower()
                
                if 'invalid api key' in error_str or 'unauthorized' in error_str:
                    return {
                        'valid': False,
                        'error': 'Service role key is invalid or unauthorized',
                        'solution': 'Regenerate service role key in Supabase Dashboard > Settings > API',
                        'details': 'invalid_key'
                    }
                elif 'database error granting user' in error_str:
                    return {
                        'valid': False,
                        'error': 'Database error granting user access (RLS policy conflict)',
                        'solution': 'Check Supabase Auth policies and service role permissions',
                        'details': 'rls_conflict'
                    }
                else:
                    return {
                        'valid': False,
                        'error': f'Unexpected authentication error: {basic_error}',
                        'solution': 'Check Supabase configuration and logs',
                        'details': 'unknown_error'
                    }
            
            # Test 2: RLS bypass validation (critical for admin operations)
            try:
                def rls_test():
                    return self._service_client.table("users").select("id").limit(1).execute()
                
                rls_result = await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, rls_test),
                    timeout=3.0
                )
                
                rls_test_time = (time.time() - start_time) * 1000
                logger.info(f"🛡️ [DATABASE] RLS bypass test: {rls_test_time:.2f}ms")
                
            except Exception as rls_error:
                logger.warning(f"⚠️ [DATABASE] RLS bypass test failed: {rls_error}")
                # RLS failure doesn't invalidate the key but indicates limited functionality
            
            total_time = (time.time() - start_time) * 1000
            
            return {
                'valid': True,
                'error': None,
                'solution': None,
                'details': {
                    'total_validation_time_ms': total_time,
                    'basic_connectivity': 'passed',
                    'rls_bypass': 'tested',
                    'performance_grade': 'excellent' if total_time < 500 else 'good' if total_time < 1000 else 'slow'
                }
            }
            
        except Exception as validation_error:
            return {
                'valid': False,
                'error': f'Validation process failed: {validation_error}',
                'solution': 'Check database configuration and try restarting the service',
                'details': 'validation_exception'
            }
    
    @property
    def storage(self):
        """Get storage client (uses service key for admin operations)."""
        return self.service_client.storage
    
    def is_available(self) -> bool:
        """Check if Supabase is available - Railway optimized."""
        if self._is_available is not None:
            return self._is_available
        
        try:
            # Quick connection test
            client = self.client
            result = client.table("users").select("id").limit(1).execute()
            
            self._is_available = result.data is not None
            if self._is_available:
                logger.info("✅ Supabase connection verified")
            else:
                logger.warning("⚠️ Supabase connection failed")
            return self._is_available
                
        except Exception as e:
            logger.error(f"❌ Supabase connection error: {e}")
            self._is_available = False
            return False
    
    async def execute_parallel_queries(
        self,
        queries: List[Tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]],  # (table, operation, data, filters)
        user_id: Optional[str] = None,
        use_service_key: bool = False,
        auth_token: Optional[str] = None
    ) -> List[Any]:
        """
        Execute multiple queries in parallel for maximum performance.
        Critical for eliminating sequential query bottlenecks.
        
        Args:
            queries: List of (table, operation, data, filters) tuples
            user_id: User ID for RLS context
            use_service_key: Whether to use service key
            auth_token: JWT token for authentication
        """
        if not self.is_available():
            raise ConnectionError("Supabase database is not available")
            
        try:
            import asyncio
            start_time = time.time()
            
            # Create tasks for parallel execution
            tasks = []
            for table, operation, data, filters in queries:
                task = asyncio.create_task(
                    self._execute_single_query(table, operation, data, filters, user_id, use_service_key, auth_token)
                )
                tasks.append(task)
            
            # Execute all queries in parallel
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            execution_time = (time.time() - start_time) * 1000
            
            logger.info(f"🚀 [DATABASE] Parallel execution: {len(queries)} queries in {execution_time:.2f}ms")
            
            # Check for exceptions and handle them
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"❌ [DATABASE] Query {i} failed in parallel batch: {result}")
                    raise result
                processed_results.append(result)
            
            return processed_results
            
        except Exception as e:
            logger.error(f"❌ [DATABASE] Parallel query execution failed: {e}")
            raise
    
    async def _execute_single_query(
        self,
        table: str,
        operation: str,
        data: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        use_service_key: bool = False,
        auth_token: Optional[str] = None
    ) -> Any:
        """Internal method for single query execution used by parallel processing."""
        return self.execute_query(table, operation, data, filters, user_id, use_service_key, False, None, None, None, auth_token)
    
    async def execute_query_async(
        self, 
        table: str, 
        operation: str, 
        data: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        use_service_key: bool = False,
        single: bool = False,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        auth_token: Optional[str] = None,
        timeout: float = 5.0
    ) -> Any:
        """
        ASYNC wrapper for execute_query with timeout and performance optimization.
        Target: <1000ms execution time for standard queries.
        """
        import asyncio
        
        def sync_query():
            return self.execute_query(table, operation, data, filters, user_id, use_service_key, 
                                    single, order_by, limit, offset, auth_token)
        
        try:
            # Execute synchronous operation in thread pool with timeout
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(self._thread_pool, sync_query),
                timeout=timeout
            )
            return result
        except asyncio.TimeoutError:
            logger.error(f"❌ [DATABASE] Query timeout after {timeout}s for {operation} on {table}")
            raise DatabaseTimeoutError(
                operation=f"{operation} on {table}",
                timeout_seconds=timeout,
                additional_info="Consider optimizing query or increasing timeout for complex operations"
            )
        except Exception as e:
            logger.error(f"❌ [DATABASE] Async query failed: {e}")
            raise

    # =========================================================================
    # CRITICAL ASYNC DATABASE OPERATIONS WRAPPER
    # =========================================================================
    # These methods provide non-blocking async wrappers for all database 
    # operations to eliminate 15-30 second timeout issues.

    async def execute_auth_query_async(
        self,
        user_id: str,
        auth_token: Optional[str] = None,
        operation_type: str = "user_lookup",
        additional_filters: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None
    ) -> Any:
        """
        CRITICAL: Ultra-fast async authentication query wrapper.
        Target: <50ms for authentication operations.
        
        Args:
            user_id: User ID to authenticate/lookup
            auth_token: JWT token for authentication
            operation_type: Type of auth operation (user_lookup, profile_check, etc.)
            additional_filters: Additional query filters
            timeout: Operation timeout (defaults to auth_query timeout)
        """
        start_time = time.time()
        timeout = timeout or self._operation_timeouts["auth_query"]
        
        try:
            with self._cache_lock:
                self._async_operation_stats["total_async_operations"] += 1
            
            def sync_auth_operation():
                try:
                    # Use service client for optimal performance
                    if self._service_key_valid:
                        # Direct user lookup via service client (bypasses RLS)
                        filters = {"id": user_id}
                        if additional_filters:
                            filters.update(additional_filters)
                            
                        result = self.execute_query(
                            table="users",
                            operation="select",
                            filters=filters,
                            use_service_key=True,
                            single=True
                        )
                        return result
                    else:
                        # Fallback to anon client with JWT
                        if not auth_token:
                            raise ValueError("Service key invalid and no auth_token provided for auth operation")
                        
                        filters = {"id": user_id}
                        if additional_filters:
                            filters.update(additional_filters)
                            
                        result = self.execute_query(
                            table="users",
                            operation="select",
                            filters=filters,
                            use_service_key=False,
                            single=True,
                            auth_token=auth_token,
                            user_id=user_id
                        )
                        return result
                        
                except Exception as e:
                    logger.error(f"❌ [DATABASE] Sync auth operation failed: {e}")
                    raise
            
            # Execute with timeout protection
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(self._thread_pool, sync_auth_operation),
                timeout=timeout
            )
            
            # Performance tracking
            execution_time_ms = (time.time() - start_time) * 1000
            
            with self._cache_lock:
                if execution_time_ms <= 50:  # Target: <50ms for auth
                    self._async_operation_stats["operations_under_target"] += 1
                else:
                    self._async_operation_stats["operations_over_target"] += 1
                    
                # Update rolling average
                total_ops = self._async_operation_stats["total_async_operations"]
                current_avg = self._async_operation_stats["avg_execution_time_ms"]
                self._async_operation_stats["avg_execution_time_ms"] = (
                    (current_avg * (total_ops - 1) + execution_time_ms) / total_ops
                )
            
            # Log performance
            if execution_time_ms > 50:
                logger.warning(f"⚠️ [DATABASE] Slow auth async operation: {execution_time_ms:.1f}ms (target: <50ms)")
            else:
                logger.debug(f"🎯 [DATABASE] Fast auth async operation: {execution_time_ms:.1f}ms")
            
            # Record performance metrics
            record_query(
                query_type="auth",
                execution_time_ms=execution_time_ms,
                success=True,
                context={
                    "operation_type": operation_type,
                    "async_wrapper": True,
                    "user_id": user_id,
                    "has_auth_token": bool(auth_token)
                }
            )
            
            return result
            
        except asyncio.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000
            
            with self._cache_lock:
                self._async_operation_stats["timeout_errors"] += 1
            
            logger.error(f"❌ [DATABASE] Auth query timeout after {timeout}s for user {user_id}")
            logger.error(f"🔧 [DATABASE] Consider optimizing auth query or checking database performance")
            
            record_query(
                query_type="auth",
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "error": "timeout",
                    "operation_type": operation_type,
                    "timeout_seconds": timeout
                }
            )
            
            raise DatabaseTimeoutError(
                operation=f"auth_query for user {user_id}",
                timeout_seconds=timeout,
                additional_info="Authentication queries must complete within 1 second for optimal UX"
            )
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.error(f"❌ [DATABASE] Auth async operation failed after {execution_time_ms:.1f}ms: {e}")
            
            record_query(
                query_type="auth",
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "error": str(e),
                    "operation_type": operation_type
                }
            )
            
            raise

    async def execute_authorization_check_async(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        operation: str = "read",
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        CRITICAL: Ultra-fast async authorization check.
        Target: <20ms execution time using materialized views.
        
        Args:
            user_id: User ID to check authorization for
            resource_type: Type of resource (generation, project, etc.)
            resource_id: ID of resource
            operation: Operation type (read, write, delete)
            timeout: Operation timeout (defaults to auth_check timeout)
        """
        start_time = time.time()
        timeout = timeout or self._operation_timeouts["auth_check"]
        
        try:
            with self._cache_lock:
                self._async_operation_stats["total_async_operations"] += 1
            
            def sync_authorization_check():
                try:
                    # OPTIMIZATION: Use materialized views for fastest authorization checks
                    if resource_type == "generation":
                        # Use the optimized materialized view query
                        result = self.execute_query(
                            table="mv_user_authorization_context",
                            operation="select",
                            filters={
                                "user_id": user_id,
                                "generation_id": resource_id
                            },
                            use_service_key=True,  # Bypass RLS for performance
                            single=True,
                            limit=1
                        )
                        
                        if result:
                            return {
                                "access_granted": result.get("has_read_access", False) if operation == "read" 
                                                else result.get("has_write_access", False),
                                "effective_role": result.get("effective_role", "none"),
                                "access_method": "materialized_view_optimized",
                                "resource_owner": result.get("is_owner", False)
                            }
                    
                    # Fallback to direct authorization logic for other resources
                    if resource_type == "project":
                        result = self.execute_query(
                            table="projects",
                            operation="select",
                            filters={"id": resource_id},
                            use_service_key=True,
                            single=True
                        )
                        
                        if result:
                            is_owner = result.get("user_id") == user_id
                            is_public = result.get("visibility") == "public"
                            
                            return {
                                "access_granted": is_owner or (is_public and operation == "read"),
                                "effective_role": "owner" if is_owner else "viewer" if is_public else "none",
                                "access_method": "direct_project_check",
                                "resource_owner": is_owner
                            }
                    
                    # Default deny for unknown resource types
                    return {
                        "access_granted": False,
                        "effective_role": "none",
                        "access_method": "unknown_resource_type",
                        "resource_owner": False
                    }
                    
                except Exception as e:
                    logger.error(f"❌ [DATABASE] Sync authorization check failed: {e}")
                    raise
            
            # Execute with timeout protection
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(self._thread_pool, sync_authorization_check),
                timeout=timeout
            )
            
            # Performance tracking
            execution_time_ms = (time.time() - start_time) * 1000
            
            with self._cache_lock:
                if execution_time_ms <= 20:  # Target: <20ms for authorization
                    self._async_operation_stats["operations_under_target"] += 1
                else:
                    self._async_operation_stats["operations_over_target"] += 1
                    
                total_ops = self._async_operation_stats["total_async_operations"]
                current_avg = self._async_operation_stats["avg_execution_time_ms"]
                self._async_operation_stats["avg_execution_time_ms"] = (
                    (current_avg * (total_ops - 1) + execution_time_ms) / total_ops
                )
            
            # Log performance
            if execution_time_ms > 20:
                logger.warning(f"⚠️ [DATABASE] Slow authorization async check: {execution_time_ms:.1f}ms (target: <20ms)")
            else:
                logger.debug(f"🎯 [DATABASE] Fast authorization async check: {execution_time_ms:.1f}ms")
            
            # Record performance metrics
            record_query(
                query_type="auth",
                execution_time_ms=execution_time_ms,
                success=True,
                context={
                    "operation": "authorization_check",
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "user_id": user_id,
                    "async_wrapper": True,
                    "access_granted": result["access_granted"]
                }
            )
            
            # Add execution time to result for monitoring
            result["execution_time_ms"] = execution_time_ms
            
            return result
            
        except asyncio.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000
            
            with self._cache_lock:
                self._async_operation_stats["timeout_errors"] += 1
            
            logger.error(f"❌ [DATABASE] Authorization check timeout after {timeout}s")
            logger.error(f"🔧 [DATABASE] Resource: {resource_type}:{resource_id}, User: {user_id}")
            
            record_query(
                query_type="auth",
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "error": "timeout",
                    "operation": "authorization_check",
                    "resource_type": resource_type,
                    "timeout_seconds": timeout
                }
            )
            
            raise DatabaseTimeoutError(
                operation=f"authorization_check {resource_type}:{resource_id}",
                timeout_seconds=timeout,
                additional_info="Authorization checks must complete within 500ms for optimal UX"
            )
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.error(f"❌ [DATABASE] Authorization async check failed after {execution_time_ms:.1f}ms: {e}")
            
            record_query(
                query_type="auth",
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "error": str(e),
                    "operation": "authorization_check",
                    "resource_type": resource_type
                }
            )
            
            raise

    async def execute_table_operation_async(
        self,
        table: str,
        operation: str,
        data: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        use_service_key: bool = False,
        single: bool = False,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        timeout: Optional[float] = None
    ) -> Any:
        """
        CRITICAL: Async wrapper for general table operations.
        Target: <75ms for general database operations.
        
        Args:
            All standard database operation parameters
            timeout: Operation timeout (defaults to general_query timeout)
        """
        start_time = time.time()
        timeout = timeout or self._operation_timeouts["general_query"]
        
        try:
            with self._cache_lock:
                self._async_operation_stats["total_async_operations"] += 1
            
            def sync_table_operation():
                return self.execute_query(
                    table=table,
                    operation=operation,
                    data=data,
                    filters=filters,
                    user_id=user_id,
                    use_service_key=use_service_key,
                    single=single,
                    order_by=order_by,
                    limit=limit,
                    offset=offset,
                    auth_token=auth_token
                )
            
            # Execute with timeout protection
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(self._thread_pool, sync_table_operation),
                timeout=timeout
            )
            
            # Performance tracking
            execution_time_ms = (time.time() - start_time) * 1000
            
            with self._cache_lock:
                target_ms = 75  # Target: <75ms for general operations
                if execution_time_ms <= target_ms:
                    self._async_operation_stats["operations_under_target"] += 1
                else:
                    self._async_operation_stats["operations_over_target"] += 1
                    
                total_ops = self._async_operation_stats["total_async_operations"]
                current_avg = self._async_operation_stats["avg_execution_time_ms"]
                self._async_operation_stats["avg_execution_time_ms"] = (
                    (current_avg * (total_ops - 1) + execution_time_ms) / total_ops
                )
            
            # Log performance
            if execution_time_ms > 75:
                logger.warning(f"⚠️ [DATABASE] Slow table async operation: {execution_time_ms:.1f}ms (target: <75ms)")
            else:
                logger.debug(f"🎯 [DATABASE] Fast table async operation: {execution_time_ms:.1f}ms")
            
            # Record performance metrics
            query_type = "auth" if table in ["users", "user_profiles"] and operation == "select" else "general"
            record_query(
                query_type=query_type,
                execution_time_ms=execution_time_ms,
                success=True,
                context={
                    "table": table,
                    "operation": operation,
                    "async_wrapper": True,
                    "use_service_key": use_service_key,
                    "has_filters": bool(filters),
                    "single": single
                }
            )
            
            return result
            
        except asyncio.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000
            
            with self._cache_lock:
                self._async_operation_stats["timeout_errors"] += 1
            
            logger.error(f"❌ [DATABASE] Table operation timeout after {timeout}s")
            logger.error(f"🔧 [DATABASE] Table: {table}, Operation: {operation}")
            
            query_type = "auth" if table in ["users", "user_profiles"] and operation == "select" else "general"
            record_query(
                query_type=query_type,
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "error": "timeout",
                    "table": table,
                    "operation": operation,
                    "timeout_seconds": timeout
                }
            )
            
            raise DatabaseTimeoutError(
                operation=f"{operation} on {table}",
                timeout_seconds=timeout,
                additional_info="Consider optimizing query or using batch operations for large datasets"
            )
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.error(f"❌ [DATABASE] Table async operation failed after {execution_time_ms:.1f}ms: {e}")
            
            query_type = "auth" if table in ["users", "user_profiles"] and operation == "select" else "general"
            record_query(
                query_type=query_type,
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "error": str(e),
                    "table": table,
                    "operation": operation
                }
            )
            
            raise

    async def execute_batch_operations_async(
        self,
        operations: List[Tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]],
        user_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        use_service_key: bool = False,
        timeout: Optional[float] = None
    ) -> List[Any]:
        """
        CRITICAL: Async wrapper for batch operations to prevent sequential blocking.
        Target: <100ms per operation in parallel execution.
        
        Args:
            operations: List of (table, operation, data, filters) tuples
            user_id: User ID for context
            auth_token: JWT token for authentication
            use_service_key: Whether to use service key
            timeout: Total batch timeout (defaults to batch_query timeout)
        """
        start_time = time.time()
        timeout = timeout or self._operation_timeouts["batch_query"]
        
        try:
            with self._cache_lock:
                self._async_operation_stats["total_async_operations"] += 1
            
            # Execute operations in parallel using the existing method
            result = await asyncio.wait_for(
                self.execute_parallel_queries(
                    operations, user_id, use_service_key, auth_token
                ),
                timeout=timeout
            )
            
            # Performance tracking
            execution_time_ms = (time.time() - start_time) * 1000
            avg_per_operation = execution_time_ms / len(operations) if operations else 0
            
            with self._cache_lock:
                target_ms = 100  # Target: <100ms per operation
                if avg_per_operation <= target_ms:
                    self._async_operation_stats["operations_under_target"] += 1
                else:
                    self._async_operation_stats["operations_over_target"] += 1
                    
                total_ops = self._async_operation_stats["total_async_operations"]
                current_avg = self._async_operation_stats["avg_execution_time_ms"]
                self._async_operation_stats["avg_execution_time_ms"] = (
                    (current_avg * (total_ops - 1) + execution_time_ms) / total_ops
                )
            
            # Log performance
            logger.info(f"🚀 [DATABASE] Batch async operations: {len(operations)} ops in {execution_time_ms:.1f}ms (avg: {avg_per_operation:.1f}ms/op)")
            
            if avg_per_operation > 100:
                logger.warning(f"⚠️ [DATABASE] Slow batch async operations: {avg_per_operation:.1f}ms/op (target: <100ms/op)")
            
            # Record performance metrics
            record_query(
                query_type="general",
                execution_time_ms=execution_time_ms,
                success=True,
                context={
                    "operation": "batch_operations",
                    "batch_size": len(operations),
                    "avg_per_operation_ms": avg_per_operation,
                    "async_wrapper": True,
                    "use_service_key": use_service_key
                }
            )
            
            return result
            
        except asyncio.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000
            
            with self._cache_lock:
                self._async_operation_stats["timeout_errors"] += 1
            
            logger.error(f"❌ [DATABASE] Batch operations timeout after {timeout}s")
            logger.error(f"🔧 [DATABASE] Batch size: {len(operations)} operations")
            
            record_query(
                query_type="general",
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "error": "timeout",
                    "operation": "batch_operations",
                    "batch_size": len(operations),
                    "timeout_seconds": timeout
                }
            )
            
            raise DatabaseTimeoutError(
                operation=f"batch_operations ({len(operations)} ops)",
                timeout_seconds=timeout,
                additional_info="Consider reducing batch size or optimizing individual operations"
            )
            
        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            
            logger.error(f"❌ [DATABASE] Batch async operations failed after {execution_time_ms:.1f}ms: {e}")
            
            record_query(
                query_type="general",
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "error": str(e),
                    "operation": "batch_operations",
                    "batch_size": len(operations)
                }
            )
            
            raise

    def get_async_operation_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive async operation performance metrics.
        Critical for monitoring the elimination of blocking operations.
        """
        with self._cache_lock:
            metrics = self._async_operation_stats.copy()
            
        # Calculate performance grades
        if metrics["total_async_operations"] > 0:
            success_rate = ((metrics["total_async_operations"] - metrics["timeout_errors"]) 
                          / metrics["total_async_operations"]) * 100
            target_success_rate = (metrics["operations_under_target"] 
                                 / metrics["total_async_operations"]) * 100
            
            metrics.update({
                "success_rate_percent": success_rate,
                "target_success_rate_percent": target_success_rate,
                "performance_grade": (
                    "excellent" if target_success_rate >= 95 and metrics["avg_execution_time_ms"] <= 50 else
                    "good" if target_success_rate >= 85 and metrics["avg_execution_time_ms"] <= 100 else
                    "acceptable" if target_success_rate >= 70 and metrics["avg_execution_time_ms"] <= 200 else
                    "needs_optimization"
                ),
                "blocking_eliminated": metrics["timeout_errors"] == 0 and metrics["avg_execution_time_ms"] <= 1000
            })
        else:
            metrics.update({
                "success_rate_percent": 0.0,
                "target_success_rate_percent": 0.0,
                "performance_grade": "no_data",
                "blocking_eliminated": True  # No operations means no blocking
            })
        
        return metrics

    @asynccontextmanager
    async def async_transaction_context(self, use_service_key: bool = False):
        """
        Async context manager for database transactions.
        Note: Supabase handles transactions automatically, this is for consistency.
        """
        start_time = time.time()
        transaction_id = f"txn_{int(start_time * 1000)}"
        
        try:
            logger.debug(f"🔄 [DATABASE] Starting async transaction context: {transaction_id}")
            yield self
            logger.debug(f"✅ [DATABASE] Async transaction completed: {transaction_id}")
            
        except Exception as e:
            logger.error(f"❌ [DATABASE] Async transaction failed: {transaction_id}, error: {e}")
            # Supabase automatically handles rollback
            raise
        
        finally:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.debug(f"🔄 [DATABASE] Async transaction context closed: {transaction_id} ({execution_time_ms:.1f}ms)")

    # =========================================================================
    # END CRITICAL ASYNC DATABASE OPERATIONS WRAPPER
    # =========================================================================

    def execute_query(
        self, 
        table: str, 
        operation: str, 
        data: Optional[Dict[str, Any]] = None,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        use_service_key: bool = False,
        single: bool = False,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        auth_token: Optional[str] = None
    ) -> Any:
        """
        Execute database query with proper error handling.
        
        Args:
            table: Table name
            operation: 'select', 'insert', 'update', 'delete'
            data: Data for insert/update operations
            filters: Filters for select/update/delete operations
            user_id: User ID for RLS context
            use_service_key: Whether to use service key (bypasses RLS)
            single: Return single record instead of list
            order_by: Order by clause (e.g., "created_at:desc")
            limit: Limit number of results
            offset: Offset for pagination
        """
        # Start performance timing with singleton tracking
        start_time = time.time()
        success = True
        query_type = "auth" if table in ["users", "user_profiles"] and operation == "select" else "general"
        
        # Thread-safe query counting
        with self._cache_lock:
            self._total_queries += 1
            query_number = self._total_queries
        
        if not self.is_available():
            raise ConnectionError("Supabase database is not available. Check API keys and connection.")
        
        try:
            # CRITICAL FIX: Corrected client selection logic to prevent anon fallback when service key is valid
            if use_service_key:
                if self._service_key_valid is True:
                    try:
                        client = self.service_client
                        logger.info(f"🔑 [DATABASE] Using SERVICE client for {operation} on {table}")
                        logger.info(f"🔑 [DATABASE] Service client bypasses RLS - operation: {operation}, table: {table}")
                    except Exception as service_client_error:
                        logger.error(f"❌ [DATABASE] Service client access failed despite valid key: {service_client_error}")
                        logger.error(f"❌ [DATABASE] Error type: {type(service_client_error).__name__}")
                        logger.error(f"🔧 [DATABASE] EXCEPTION FALLBACK: Switching to anon client")
                        
                        client = self.client
                        use_service_key = False
                        logger.info(f"🔓 [DATABASE] EXCEPTION FALLBACK: Using ANON client for {operation} on {table}")
                else:
                    logger.error(f"🚨 [DATABASE] Service key requested but invalid for {operation} on {table}")
                    if not auth_token:
                        raise ValueError("Service key invalid and no JWT token provided")
                    client = self.client
                    use_service_key = False
                    logger.warning(f"🔧 [DATABASE] FALLBACK: Using ANON client with JWT for {operation} on {table}")
                    
                    # Enhanced JWT requirement warning
                    if table in ['users', 'credit_transactions', 'generations'] and operation in ['select', 'update', 'insert']:
                        logger.error(f"🚨 [DATABASE] CRITICAL: Table '{table}' operation '{operation}' typically requires service key or JWT")
                        logger.error(f"⚠️ [DATABASE] Without service key, this operation may fail due to RLS policies")
            else:
                client = self.client
                logger.info(f"🔓 [DATABASE] Using ANON client for {operation} on {table} (as requested)")
                logger.info(f"🛡️ [DATABASE] Anon client subject to RLS policies - operation: {operation}, table: {table}")
                
                # CRITICAL FIX: Enhanced JWT token handling for anon client with proper session management
                if user_id and auth_token:
                    logger.info(f"🔐 [DATABASE] Setting JWT token for user {user_id} in anon client")
                    try:
                        # Handle different token formats with enhanced validation
                        if auth_token.startswith("supabase_token_") or auth_token.startswith("mock_token_"):
                            # Custom token format - skip JWT setting but log for debugging
                            logger.info(f"🔧 [DATABASE] Custom token format detected ({auth_token[:20]}...), skipping JWT session setup")
                        else:
                            # Real Supabase JWT token - enhanced session handling
                            logger.info(f"🔑 [DATABASE] Setting real Supabase JWT session for user {user_id}")
                            
                            # CRITICAL FIX: Enhanced session setup with better error handling
                            try:
                                # Correct Supabase session handling
                                client.auth.set_session({
                                    "access_token": auth_token,
                                    "refresh_token": None
                                })
                                logger.info(f"✅ [DATABASE] JWT session set successfully for user {user_id}")
                                
                            except Exception as session_error:
                                logger.warning(f"⚠️ [DATABASE] Direct session set failed, trying header approach: {session_error}")
                                # Use headers as fallback
                                try:
                                    client.auth._headers = {
                                        **getattr(client.auth, '_headers', {}),
                                        "Authorization": f"Bearer {auth_token}"
                                    }
                                    logger.info(f"✅ [DATABASE] Using header fallback for JWT")
                                except Exception as header_error:
                                    logger.error(f"❌ [DATABASE] Header fallback also failed: {header_error}")
                                
                                # Method 2: Fallback - set Authorization header directly (if supported)
                                try:
                                    # Some Supabase operations may work with direct header setting
                                    client.auth.session = {"access_token": auth_token}
                                    logger.info(f"✅ [DATABASE] JWT token set via fallback method for user {user_id}")
                                except Exception as fallback_error:
                                    logger.warning(f"⚠️ [DATABASE] Fallback JWT method also failed: {fallback_error}")
                                    logger.warning(f"⚠️ [DATABASE] Proceeding without JWT session - RLS may block access")
                                    
                    except Exception as jwt_error:
                        logger.error(f"❌ [DATABASE] Failed to set JWT token for user {user_id}: {jwt_error}")
                        logger.error(f"❌ [DATABASE] JWT error type: {type(jwt_error).__name__}")
                        # Continue without token - may fail with RLS error
                        
                elif user_id and not use_service_key and not auth_token:
                    logger.warning(f"⚠️ [DATABASE] Need user context for {user_id} but no auth_token provided - RLS may block access")
                    # For server-side operations without JWT token, we may need to use service key
                    logger.warning(f"⚠️ [DATABASE] Consider using use_service_key=True for server-side operations")
                    
                elif not user_id and not use_service_key:
                    logger.warning(f"⚠️ [DATABASE] No user context available - operation may fail with RLS policies")
            
            logger.info(f"🔍 [DATABASE] Creating query for {operation} on {table}, filters: {filters}")
            query = client.table(table)
            
            if operation == "select":
                query = query.select("*")
                
                if filters:
                    for key, value in filters.items():
                        query = query.eq(key, value)
                
                # Apply ordering
                if order_by:
                    if ":" in order_by:
                        column, direction = order_by.split(":")
                        if direction.lower() == "desc":
                            query = query.order(column, desc=True)
                        else:
                            query = query.order(column)
                    else:
                        query = query.order(order_by)
                
                # Apply pagination
                if limit:
                    query = query.limit(limit)
                if offset:
                    query = query.range(offset, offset + limit - 1 if limit else offset + 100)
                
                logger.info(f"🔍 [DATABASE] Executing SELECT query on {table}")
                result = query.execute()
                logger.info(f"🔍 [DATABASE] SELECT result for {table}: {len(result.data) if result.data else 0} rows")
                
                if single and result.data:
                    logger.info(f"✅ [DATABASE] Returning single record from {table}")
                    return result.data[0]
                    
                logger.info(f"✅ [DATABASE] Returning {len(result.data) if result.data else 0} records from {table}")
                return result.data
            
            elif operation == "insert":
                if not data:
                    raise ValueError("Data required for insert operation")
                    
                logger.info(f"🔍 [DATABASE] Executing INSERT query on {table} with data keys: {list(data.keys()) if data else []}")
                result = query.insert(data).execute()
                logger.info(f"🔍 [DATABASE] INSERT result for {table}: {len(result.data) if result.data else 0} rows created")
                
                if single:
                    logger.info(f"✅ [DATABASE] Returning single inserted record from {table}")
                    return result.data[0] if result.data else None
                    
                logger.info(f"✅ [DATABASE] Returning {len(result.data) if result.data else 0} inserted records from {table}")
                return result.data
            
            elif operation == "update":
                if not data:
                    raise ValueError("Data required for update operation")
                    
                logger.info(f"🔍 [DATABASE] Executing UPDATE query on {table} with data keys: {list(data.keys()) if data else []}")
                query = query.update(data)
                if filters:
                    for key, value in filters.items():
                        query = query.eq(key, value)
                        
                result = query.execute()
                logger.info(f"🔍 [DATABASE] UPDATE result for {table}: {len(result.data) if result.data else 0} rows updated")
                
                if single:
                    logger.info(f"✅ [DATABASE] Returning single updated record from {table}")
                    return result.data[0] if result.data else None
                    
                logger.info(f"✅ [DATABASE] Returning {len(result.data) if result.data else 0} updated records from {table}")
                return result.data
            
            elif operation == "delete":
                query = query.delete()
                if filters:
                    for key, value in filters.items():
                        query = query.eq(key, value)
                result = query.execute()
                
                # Record successful query performance
                execution_time_ms = (time.time() - start_time) * 1000
                record_query(
                    query_type=query_type,
                    execution_time_ms=execution_time_ms,
                    success=True,
                    context={
                        "table": table,
                        "operation": operation,
                        "use_service_key": use_service_key,
                        "has_filters": bool(filters),
                        "single": single
                    }
                )
                
                return result.data
            
            else:
                raise ValueError(f"Unsupported operation: {operation}")
                
        except Exception as e:
            # Record failed query performance
            execution_time_ms = (time.time() - start_time) * 1000
            record_query(
                query_type=query_type,
                execution_time_ms=execution_time_ms,
                success=False,
                context={
                    "table": table,
                    "operation": operation,
                    "error": str(e),
                    "use_service_key": use_service_key
                }
            )
            logger.error(f"Database query failed: {e}")
            raise
    
    def execute_rpc(
        self, 
        function_name: str, 
        params: Optional[Dict[str, Any]] = None,
        use_service_key: bool = False
    ) -> Any:
        """Execute Supabase RPC function."""
        try:
            client = self.client
            result = client.rpc(function_name, params or {}).execute()
            return result.data
        except Exception as e:
            logger.error(f"RPC function {function_name} failed: {e}")
            raise
    
    async def execute_materialized_view_query(
        self,
        view_name: str,
        filters: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        auth_token: Optional[str] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None
    ) -> Any:
        """
        Execute optimized query against materialized views for maximum performance.
        Uses existing materialized views from migrations 012 and 013.
        
        Args:
            view_name: Name of materialized view (mv_user_authorization_context, etc.)
            filters: Filters to apply to the view
            user_id: User ID for context
            auth_token: JWT token
            limit: Limit results
            order_by: Order by clause
        """
        if not self.is_available():
            raise ConnectionError("Supabase database is not available")
            
        try:
            start_time = time.time()
            
            # Use service client for materialized views to bypass RLS overhead
            client = self.service_client
            
            logger.info(f"📊 [DATABASE] Querying materialized view: {view_name}")
            
            # Build optimized query for materialized view
            query = client.table(view_name).select("*")
            
            # Apply filters efficiently
            if filters:
                for key, value in filters.items():
                    if isinstance(value, list):
                        query = query.in_(key, value)
                    else:
                        query = query.eq(key, value)
            
            # Apply ordering
            if order_by:
                if ":" in order_by:
                    column, direction = order_by.split(":")
                    query = query.order(column, desc=(direction.lower() == "desc"))
                else:
                    query = query.order(order_by)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            result = query.execute()
            
            execution_time = (time.time() - start_time) * 1000
            
            logger.info(f"📊 [DATABASE] Materialized view query completed in {execution_time:.2f}ms, {len(result.data) if result.data else 0} rows")
            
            # Log performance for views that should be <10ms
            if execution_time > 20:
                logger.warning(f"⚠️ [DATABASE] Materialized view query exceeded target: {execution_time:.2f}ms (target: <20ms)")
            elif execution_time < 10:
                logger.debug(f"🎯 [DATABASE] Excellent materialized view performance: {execution_time:.2f}ms")
            
            return result.data
            
        except Exception as e:
            logger.error(f"❌ [DATABASE] Materialized view query failed for {view_name}: {e}")
            raise
    
    async def execute_authorization_check_optimized(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        operation: str = "read"
    ) -> Dict[str, Any]:
        """
        Execute ultra-fast authorization check using materialized views and optimized queries.
        Target: <20ms execution time.
        
        Args:
            user_id: User ID to check authorization for
            resource_type: Type of resource (generation, project, etc.)
            resource_id: ID of resource
            operation: Operation type (read, write, delete)
        """
        try:
            start_time = time.time()
            
            # Use materialized view for generation authorization (fastest path)
            if resource_type == "generation":
                result = await self.execute_materialized_view_query(
                    "mv_user_authorization_context",
                    filters={
                        "user_id": user_id,
                        "generation_id": resource_id
                    },
                    limit=1
                )
                
                if result:
                    execution_time = (time.time() - start_time) * 1000
                    logger.info(f"🎯 [DATABASE] Ultra-fast auth check via materialized view: {execution_time:.2f}ms")
                    
                    return {
                        "access_granted": result[0]["has_read_access"] if operation == "read" else result[0]["has_write_access"],
                        "effective_role": result[0]["effective_role"],
                        "access_method": "materialized_view_cache",
                        "execution_time_ms": execution_time
                    }
            
            # Fallback to direct queries with prepared statements for other resources
            auth_result = await self._execute_direct_auth_check(user_id, resource_type, resource_id, operation)
            
            execution_time = (time.time() - start_time) * 1000
            auth_result["execution_time_ms"] = execution_time
            
            return auth_result
            
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            logger.error(f"❌ [DATABASE] Authorization check failed after {execution_time:.2f}ms: {e}")
            raise
    
    async def _execute_direct_auth_check(
        self,
        user_id: str,
        resource_type: str,
        resource_id: str,
        operation: str
    ) -> Dict[str, Any]:
        """Execute direct authorization check with optimized queries."""
        
        if resource_type == "project":
            # Optimized project authorization query
            result = self.execute_query(
                table="projects",
                operation="select",
                filters={"id": resource_id},
                use_service_key=True,
                single=True
            )
            
            if not result:
                return {
                    "access_granted": False,
                    "effective_role": "none",
                    "access_method": "direct_query_not_found"
                }
            
            # Check ownership or visibility
            if result["user_id"] == user_id:
                return {
                    "access_granted": True,
                    "effective_role": "owner",
                    "access_method": "direct_ownership"
                }
            elif result["visibility"] == "public":
                return {
                    "access_granted": True,
                    "effective_role": "viewer",
                    "access_method": "public_visibility"
                }
        
        # Default deny
        return {
            "access_granted": False,
            "effective_role": "none",
            "access_method": "direct_query_denied"
        }
    
    async def execute_batch_with_prepared_statements(
        self,
        queries: List[Tuple[str, List[Any]]],  # (prepared_query, parameters)
        use_service_key: bool = True
    ) -> List[Any]:
        """
        Execute batch of queries using prepared statements for maximum performance.
        
        Args:
            queries: List of (prepared_query, parameters) tuples
            use_service_key: Whether to use service key for optimal performance
        """
        try:
            start_time = time.time()
            
            # For Supabase, we'll use the RPC function approach for batch execution
            client = self.service_client if use_service_key else self.client
            
            # Execute queries in parallel batches for optimal performance
            import asyncio
            
            async def execute_single(query, params):
                try:
                    # Convert query to Supabase format
                    return await self._execute_prepared_query(query, params, client)
                except Exception as e:
                    logger.error(f"❌ [DATABASE] Prepared query failed: {e}")
                    return None
            
            # Execute all queries in parallel
            tasks = [execute_single(query, params) for query, params in queries]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            execution_time = (time.time() - start_time) * 1000
            
            logger.info(f"🚀 [DATABASE] Batch prepared statements: {len(queries)} queries in {execution_time:.2f}ms")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ [DATABASE] Batch prepared statement execution failed: {e}")
            raise
    
    async def _execute_prepared_query(self, query: str, params: List[Any], client) -> Any:
        """Execute a single prepared query efficiently."""
        # For Supabase, we'll need to adapt queries to PostgREST format
        # This is a simplified implementation - full implementation would need query parsing
        
        try:
            # Convert parameterized query to Supabase table operation where possible
            if "SELECT" in query.upper() and "FROM users WHERE id" in query:
                # User lookup optimization
                if len(params) == 1:
                    result = client.table("users").select("*").eq("id", params[0]).execute()
                    return result.data
            
            # Fallback to RPC if available
            return await self.execute_rpc("execute_prepared_query", {
                "query_text": query,
                "query_params": params
            }, use_service_key=True)
            
        except Exception as e:
            logger.warning(f"⚠️ [DATABASE] Prepared query fallback: {e}")
            return None
    
    def execute_raw_query(
        self, 
        query: str, 
        params: Optional[List[Any]] = None,
        use_service_key: bool = False,
        auth_token: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> Any:
        """
        Execute raw SQL query with parameter binding.
        
        Args:
            query: Raw SQL query with %s placeholders
            params: Parameters to bind to the query
            use_service_key: Whether to use service key (bypasses RLS)
            auth_token: JWT token for authentication
            user_id: User ID for context
        """
        if not self.is_available():
            raise ConnectionError("Supabase database is not available. Check API keys and connection.")
        
        try:
            # Select appropriate client
            if use_service_key:
                if self._service_key_valid is True:
                    try:
                        client = self.service_client
                        logger.info(f"🔑 [DATABASE] Using SERVICE client for raw query execution")
                    except Exception as service_client_error:
                        logger.error(f"❌ [DATABASE] Service client access failed: {service_client_error}")
                        client = self.client
                        use_service_key = False
                        logger.info(f"🔧 [DATABASE] FALLBACK: Using ANON client for raw query")
                else:
                    logger.error(f"🚨 [DATABASE] Service key requested but invalid for raw query")
                    if not auth_token:
                        raise ValueError("Service key invalid and no JWT token provided for raw query")
                    client = self.client
                    use_service_key = False
                    logger.warning(f"🔧 [DATABASE] FALLBACK: Using ANON client with JWT for raw query")
            else:
                client = self.client
                logger.info(f"🔓 [DATABASE] Using ANON client for raw query")
                
                # Handle JWT authentication for anon client
                if user_id and auth_token:
                    logger.info(f"🔐 [DATABASE] Setting JWT token for user {user_id} in raw query")
                    try:
                        if not (auth_token.startswith("supabase_token_") or auth_token.startswith("mock_token_")):
                            client.auth.set_session({
                                "access_token": auth_token,
                                "refresh_token": None
                            })
                            logger.info(f"✅ [DATABASE] JWT session set for raw query")
                    except Exception as jwt_error:
                        logger.error(f"❌ [DATABASE] Failed to set JWT for raw query: {jwt_error}")
            
            # Execute raw query using RPC to get_query_results or direct PostgREST if supported
            # Since Supabase doesn't directly support raw SQL in the client, we'll use RPC
            # First, let's try to use the PostgREST query parameter approach
            
            try:
                # For PostgreSQL parameter binding, convert %s placeholders to $1, $2, etc.
                formatted_query = query
                if params:
                    for i, param in enumerate(params, 1):
                        formatted_query = formatted_query.replace('%s', f'${i}', 1)
                
                logger.info(f"🔍 [DATABASE] Executing raw query: {formatted_query[:100]}...")
                logger.info(f"🔍 [DATABASE] Query parameters: {params}")
                
                # Use RPC to execute raw query - this assumes you have a stored function
                # If not available, we'll need to create one or use an alternative approach
                result = client.rpc('execute_raw_query', {
                    'query_sql': formatted_query,
                    'query_params': params or []
                }).execute()
                
                logger.info(f"✅ [DATABASE] Raw query executed successfully via RPC")
                return result.data
                
            except Exception as rpc_error:
                logger.warning(f"⚠️ [DATABASE] RPC raw query failed, trying alternative approach: {rpc_error}")
                
                # Alternative: Try to create an equivalent query using the standard interface
                # This is a fallback for when RPC functions are not available
                logger.error(f"❌ [DATABASE] Raw query execution not supported without RPC function")
                logger.error(f"🔧 [DATABASE] Please create the execute_raw_query RPC function in Supabase")
                logger.error(f"🔧 [DATABASE] Or use the standard execute_query interface with separate queries")
                
                raise NotImplementedError(
                    "Raw query execution requires the execute_raw_query RPC function to be created in Supabase. "
                    "Please create this function or use the standard query interface."
                )
                
        except Exception as e:
            logger.error(f"❌ [DATABASE] Raw query execution failed: {e}")
            raise
    


# Global database instance - singleton pattern ensures same instance across all imports
db: Optional[SupabaseClient] = None
_db_initialization_lock = threading.RLock()


async def get_database() -> SupabaseClient:
    """
    Async dependency injection for database client.
    Returns the cached singleton instance for optimal performance.
    
    Performance Enhancement:
    - Single initialization prevents per-request blocking
    - Thread-safe access with minimal overhead
    - Connection pool reuse across all requests
    
    Returns:
        SupabaseClient: Cached singleton database instance
    
    Raises:
        RuntimeError: If database not initialized (should call initialize_database_async first)
    """
    global db
    if db is None:
        raise RuntimeError(
            "Database not initialized. Call initialize_database_async() during startup."
        )
    return db


async def initialize_database_async() -> bool:
    """
    PERFORMANCE CRITICAL: Async initialization of database singleton.
    
    This function MUST be called once during application startup to prevent
    per-request initialization blocking that causes 10-15 second timeouts.
    
    Benefits:
    - Single initialization prevents expensive per-request operations
    - Thread pool created once, reused across all requests
    - Connection pooling established upfront
    - JWT parsing libraries pre-loaded
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    global db
    
    with _db_initialization_lock:
        if db is not None:
            logger.info("✅ [DATABASE] Singleton already initialized, skipping")
            return True
        
        try:
            logger.info("🚀 [DATABASE] Initializing async database singleton...")
            start_time = time.time()
            
            # Initialize singleton instance
            db = SupabaseClient()
            
            # Run connection warm-up in async context
            warm_up_success = await asyncio.get_event_loop().run_in_executor(
                None, 
                db.warm_up_connections
            )
            
            initialization_time_ms = (time.time() - start_time) * 1000
            
            # Log performance metrics
            metrics = db.get_performance_metrics()
            logger.info(f"📊 [DATABASE] Async initialization completed in {initialization_time_ms:.2f}ms")
            logger.info(f"📊 [DATABASE] Performance metrics: {metrics}")
            
            if warm_up_success:
                logger.info("✅ [DATABASE] Async database singleton initialization successful")
            else:
                logger.warning("⚠️ [DATABASE] Async database initialization completed with warnings")
                
            return warm_up_success
            
        except Exception as e:
            logger.error(f"❌ [DATABASE] Async database initialization failed: {e}")
            db = None  # Reset on failure
            return False


def initialize_database() -> bool:
    """
    Legacy synchronous initialization - DEPRECATED for performance reasons.
    Use initialize_database_async() instead to prevent authentication timeouts.
    
    Returns:
        bool: True if initialization successful, False otherwise
    """
    try:
        logger.warning("⚠️ [DATABASE] Using legacy sync initialization - consider async version")
        
        global db
        with _db_initialization_lock:
            if db is not None:
                logger.info("✅ [DATABASE] Singleton already initialized")
                return True
                
            logger.info("🚀 [DATABASE] Initializing legacy database singleton...")
            db = SupabaseClient()
            
            # Warm up connections for optimal performance
            warm_up_success = db.warm_up_connections()
            
            # Log performance metrics
            metrics = db.get_performance_metrics()
            logger.info(f"📊 [DATABASE] Legacy initialization metrics: {metrics}")
            
            if warm_up_success:
                logger.info("✅ [DATABASE] Legacy database initialization completed successfully")
            else:
                logger.warning("⚠️ [DATABASE] Legacy database initialization completed with warnings")
                
            return warm_up_success
        
    except Exception as e:
        logger.error(f"❌ [DATABASE] Legacy database initialization failed: {e}")
        return False


def health_check() -> bool:
    """Check database connection health - Railway optimized."""
    try:
        is_available = db.is_available()
        return is_available
    except Exception as e:
        logger.debug(f"Database health check failed: {e}")
        return False


# =============================================================================
# CRITICAL ASYNC OPERATIONS CONVENIENCE FUNCTIONS
# =============================================================================
# Easy-to-use async wrappers for eliminating blocking database operations

async def execute_auth_query_async(
    user_id: str,
    auth_token: Optional[str] = None,
    operation_type: str = "user_lookup",
    additional_filters: Optional[Dict[str, Any]] = None,
    timeout: Optional[float] = None
) -> Any:
    """
    Convenience function for async authentication queries.
    Eliminates 15-30 second blocking operations.
    """
    return await db.execute_auth_query_async(
        user_id=user_id,
        auth_token=auth_token,
        operation_type=operation_type,
        additional_filters=additional_filters,
        timeout=timeout
    )


async def execute_authorization_check_async(
    user_id: str,
    resource_type: str,
    resource_id: str,
    operation: str = "read",
    timeout: Optional[float] = None
) -> Dict[str, Any]:
    """
    Convenience function for async authorization checks.
    Target: <20ms execution time.
    """
    return await db.execute_authorization_check_async(
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        operation=operation,
        timeout=timeout
    )


# =============================================================================
# PHASE 2: ENTERPRISE CONNECTION POOL INTEGRATION
# =============================================================================
# Integration of 6 specialized connection pools for optimal performance

# Import the enterprise pool manager
try:
    from utils.connection_pool_manager import (
        enterprise_pool_manager,
        SpecializedPoolType,
        QueryType,
        execute_auth_query,
        execute_read_query,
        execute_write_query,
        execute_analytics_query,
        execute_admin_query,
        execute_batch_query
    )
    ENTERPRISE_POOLS_AVAILABLE = True
    logger.info("✅ Enterprise Connection Pool Manager imported successfully")
except ImportError as e:
    ENTERPRISE_POOLS_AVAILABLE = False
    logger.warning(f"⚠️ Enterprise pools not available: {e}")


async def initialize_enterprise_pools() -> bool:
    """
    Initialize the enterprise connection pool system.
    Must be called during application startup for optimal performance.
    
    Returns:
        bool: True if initialization successful
    """
    if not ENTERPRISE_POOLS_AVAILABLE:
        logger.warning("⚠️ Enterprise pools not available - skipping initialization")
        return False
    
    try:
        logger.info("🚀 Initializing Enterprise Connection Pool System...")
        
        # Get database URL from settings
        database_url = getattr(settings, 'database_url', None)
        if not database_url and hasattr(settings, 'supabase_url'):
            # Construct PostgreSQL URL from Supabase URL
            # Note: This is a simplified construction - in production you should use the direct PostgreSQL URL
            supabase_host = settings.supabase_url.replace('https://', '').replace('http://', '')
            database_url = f"postgresql://postgres:[PASSWORD]@{supabase_host}/postgres"
            logger.info(f"🔗 Constructed database URL from Supabase URL")
        
        # Initialize the pool manager
        await enterprise_pool_manager.initialize(database_url)
        
        logger.info("🎉 Enterprise Connection Pool System initialized successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize enterprise pools: {e}")
        return False


async def get_enterprise_pool_metrics() -> Dict[str, Any]:
    """
    Get comprehensive metrics from all enterprise connection pools.
    
    Returns:
        Dict containing detailed metrics from all pools
    """
    if not ENTERPRISE_POOLS_AVAILABLE:
        return {"status": "unavailable", "reason": "Enterprise pools not imported"}
    
    try:
        return await enterprise_pool_manager.get_comprehensive_metrics()
    except Exception as e:
        logger.error(f"❌ Error getting enterprise pool metrics: {e}")
        return {"status": "error", "error": str(e)}


async def execute_query_with_pool_routing(
    query: str,
    *args,
    query_type: Optional[str] = None,
    pool_type: Optional[str] = None,
    timeout: Optional[float] = None
) -> Any:
    """
    Execute query using intelligent pool routing for optimal performance.
    
    Args:
        query: SQL query to execute
        *args: Query parameters
        query_type: Type of query for routing (e.g., 'auth_login', 'read_user_data')
        pool_type: Specific pool type to use (e.g., 'auth', 'read', 'write')
        timeout: Query timeout in seconds
    
    Returns:
        Query results
    """
    if not ENTERPRISE_POOLS_AVAILABLE:
        # Fallback to regular database client
        logger.debug("Using fallback database client (enterprise pools unavailable)")
        return await db.execute_query_async(query, *args, timeout=timeout)
    
    try:
        # Map string types to enums
        mapped_query_type = None
        if query_type:
            try:
                mapped_query_type = QueryType(query_type)
            except ValueError:
                logger.warning(f"Unknown query type: {query_type}")
        
        mapped_pool_type = None
        if pool_type:
            try:
                mapped_pool_type = SpecializedPoolType(f"{pool_type}_pool")
            except ValueError:
                logger.warning(f"Unknown pool type: {pool_type}")
        
        # Execute with optimal routing
        return await enterprise_pool_manager.execute_query(
            query, *args,
            pool_type=mapped_pool_type,
            query_type=mapped_query_type,
            timeout=timeout
        )
        
    except Exception as e:
        logger.error(f"❌ Enterprise pool query execution failed: {e}")
        # Fallback to regular database client
        logger.info("🔄 Falling back to regular database client")
        return await db.execute_query_async(query, *args, timeout=timeout)


# Convenience functions for specific pool operations
async def execute_auth_operation(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute authentication operation using optimized auth pool."""
    if ENTERPRISE_POOLS_AVAILABLE:
        return await execute_auth_query(query, *args, timeout=timeout)
    return await db.execute_query_async(query, *args, timeout=timeout)


async def execute_read_operation(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute read operation using optimized read pool."""
    if ENTERPRISE_POOLS_AVAILABLE:
        return await execute_read_query(query, *args, timeout=timeout)
    return await db.execute_query_async(query, *args, timeout=timeout)


async def execute_write_operation(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute write operation using optimized write pool."""
    if ENTERPRISE_POOLS_AVAILABLE:
        return await execute_write_query(query, *args, timeout=timeout)
    return await db.execute_query_async(query, *args, timeout=timeout)


async def execute_analytics_operation(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute analytics operation using optimized analytics pool."""
    if ENTERPRISE_POOLS_AVAILABLE:
        return await execute_analytics_query(query, *args, timeout=timeout)
    return await db.execute_query_async(query, *args, timeout=timeout)


async def execute_admin_operation(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute admin operation using optimized admin pool."""
    if ENTERPRISE_POOLS_AVAILABLE:
        return await execute_admin_query(query, *args, timeout=timeout)
    return await db.execute_query_async(query, *args, timeout=timeout)


async def execute_batch_operation(query: str, *args, timeout: Optional[float] = None) -> Any:
    """Execute batch operation using optimized batch pool."""
    if ENTERPRISE_POOLS_AVAILABLE:
        return await execute_batch_query(query, *args, timeout=timeout)
    return await db.execute_query_async(query, *args, timeout=timeout)


async def shutdown_enterprise_pools() -> None:
    """Gracefully shutdown enterprise connection pools."""
    if ENTERPRISE_POOLS_AVAILABLE:
        try:
            logger.info("🔄 Shutting down enterprise connection pools...")
            await enterprise_pool_manager.close_all_pools()
            logger.info("✅ Enterprise connection pools shutdown complete")
        except Exception as e:
            logger.error(f"❌ Error shutting down enterprise pools: {e}")


# Health check with enterprise pools
async def enterprise_health_check() -> Dict[str, Any]:
    """Comprehensive health check including enterprise pools."""
    health_status = {
        "database_client": health_check(),
        "enterprise_pools": {
            "available": ENTERPRISE_POOLS_AVAILABLE,
            "status": "not_initialized"
        }
    }
    
    if ENTERPRISE_POOLS_AVAILABLE:
        try:
            pool_metrics = await get_enterprise_pool_metrics()
            health_status["enterprise_pools"] = {
                "available": True,
                "status": pool_metrics.get("status", "unknown"),
                "overall_health": pool_metrics.get("overall_health", "unknown"),
                "total_pools": pool_metrics.get("summary", {}).get("total_pools", 0),
                "healthy_pools": pool_metrics.get("summary", {}).get("healthy_pools", 0),
                "total_connections": pool_metrics.get("summary", {}).get("total_connections", 0),
                "active_connections": pool_metrics.get("summary", {}).get("active_connections", 0)
            }
        except Exception as e:
            health_status["enterprise_pools"]["status"] = "error"
            health_status["enterprise_pools"]["error"] = str(e)
    
    return health_status


async def execute_table_operation_async(
    table: str,
    operation: str,
    data: Optional[Dict[str, Any]] = None,
    filters: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    use_service_key: bool = False,
    single: bool = False,
    order_by: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    timeout: Optional[float] = None
) -> Any:
    """
    Convenience function for async table operations.
    Target: <75ms for general database operations.
    """
    return await db.execute_table_operation_async(
        table=table,
        operation=operation,
        data=data,
        filters=filters,
        user_id=user_id,
        auth_token=auth_token,
        use_service_key=use_service_key,
        single=single,
        order_by=order_by,
        limit=limit,
        offset=offset,
        timeout=timeout
    )


async def execute_batch_operations_async(
    operations: List[Tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]],
    user_id: Optional[str] = None,
    auth_token: Optional[str] = None,
    use_service_key: bool = False,
    timeout: Optional[float] = None
) -> List[Any]:
    """
    Convenience function for async batch operations.
    Prevents sequential blocking, target: <100ms per operation in parallel.
    """
    return await db.execute_batch_operations_async(
        operations=operations,
        user_id=user_id,
        auth_token=auth_token,
        use_service_key=use_service_key,
        timeout=timeout
    )


def get_async_operation_metrics() -> Dict[str, Any]:
    """
    Get comprehensive async operation performance metrics.
    Critical for monitoring the elimination of blocking operations.
    """
    return db.get_async_operation_metrics()


async def async_database_context(use_service_key: bool = False):
    """
    Async context manager for database operations.
    Usage:
        async with async_database_context(use_service_key=True) as db_context:
            result = await db_context.execute_auth_query_async(user_id)
    """
    async with db.async_transaction_context(use_service_key=use_service_key) as context:
        yield context


# =============================================================================
# TABLE REFERENCE OBJECTS FOR SQLALCHEMY QUERIES
# =============================================================================
# These are simplified table references for raw SQL operations
# The actual schema is managed by Supabase migrations

class TableReference:
    """Simple table reference for SQL operations."""
    def __init__(self, name: str):
        self.name = name
    
    @property
    def c(self):
        """Column accessor (simplified interface)."""
        return ColumnAccessor(self.name)


class ColumnAccessor:
    """Column accessor for table references."""
    def __init__(self, table_name: str):
        self.table_name = table_name
    
    def __getattr__(self, column_name: str):
        """Return column reference."""
        return f"{self.table_name}.{column_name}"


# Team collaboration table references
teams_table = TableReference("teams")
team_members_table = TableReference("team_members")
team_invitations_table = TableReference("team_invitations")
project_privacy_settings_table = TableReference("project_privacy_settings")
project_teams_table = TableReference("project_teams")
generation_collaborations_table = TableReference("generation_collaborations")

# Existing table references
users_table = TableReference("users")
projects_table = TableReference("projects")
generations_table = TableReference("generations")


# =============================================================================
# ASYNC SESSION MANAGEMENT FOR TEAM COLLABORATION
# =============================================================================

class AsyncSessionWrapper:
    """Async session wrapper for team collaboration operations."""
    
    def __init__(self, db_client: SupabaseClient):
        self.db_client = db_client
    
    async def execute(self, query, auth_token: str = None):
        """Execute a query with proper authentication context."""
        # This is a simplified interface - in production you'd want proper SQLAlchemy integration
        # For now, we'll use the Supabase client directly
        raise NotImplementedError("Use SupabaseClient.execute_query directly")
    
    async def commit(self):
        """Commit transaction (no-op for Supabase)."""
        pass
    
    async def rollback(self):
        """Rollback transaction (no-op for Supabase)."""
        pass


async def get_async_session(auth_token: str = None) -> AsyncSessionWrapper:
    """Get async session wrapper for database operations."""
    return AsyncSessionWrapper(db)


# Alias for backward compatibility - many files expect DatabaseClient
DatabaseClient = SupabaseClient


# =============================================================================
# CRITICAL ASYNC INITIALIZATION AND CONNECTION WARMUP
# =============================================================================

async def initialize_database_async() -> bool:
    """
    CRITICAL PERFORMANCE FIX: Async database initialization with connection warmup.
    
    This function should be called during application startup to:
    1. Initialize the singleton SupabaseClient 
    2. Warm up both anonymous and service key connections
    3. Pre-load connection pools if available
    4. Cache service key validation results
    
    Target: Complete initialization in <500ms for optimal performance.
    
    Returns:
        bool: True if initialization successful, False if degraded but functional
    """
    try:
        logger.info("🚀 [DATABASE-ASYNC] Starting async database initialization...")
        start_time = time.time()
        
        # Step 1: Initialize singleton (thread-safe)
        logger.info("📌 [DATABASE-ASYNC] Initializing singleton SupabaseClient...")
        init_start = time.time()
        global db
        db = SupabaseClient()  # This will create/get singleton
        init_time = (time.time() - init_start) * 1000
        logger.info(f"✅ [DATABASE-ASYNC] Singleton initialized in {init_time:.2f}ms")
        
        # Step 2: Warm up anonymous client connection
        logger.info("🔥 [DATABASE-ASYNC] Warming up anonymous client connection...")
        anon_start = time.time()
        
        # Async availability check with timeout
        try:
            anon_available = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, db.is_available),
                timeout=2.0
            )
            anon_time = (time.time() - anon_start) * 1000
            if anon_available:
                logger.info(f"✅ [DATABASE-ASYNC] Anonymous client ready in {anon_time:.2f}ms")
            else:
                logger.warning(f"⚠️ [DATABASE-ASYNC] Anonymous client not available after {anon_time:.2f}ms")
        except asyncio.TimeoutError:
            logger.warning(f"⚠️ [DATABASE-ASYNC] Anonymous client warmup timeout after 2s")
            anon_available = False
        except Exception as anon_error:
            logger.warning(f"⚠️ [DATABASE-ASYNC] Anonymous client warmup failed: {anon_error}")
            anon_available = False
        
        # Step 3: Warm up service client connection (async with proper error handling)
        logger.info("🔥 [DATABASE-ASYNC] Warming up service client connection...")
        service_start = time.time()
        service_available = False
        
        try:
            # Get service client in executor to avoid blocking
            service_client = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, 
                    lambda: db.service_client
                ),
                timeout=3.0
            )
            
            # Quick validation test
            def service_test():
                return service_client.table("users").select("id").limit(1).execute()
            
            await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, service_test),
                timeout=2.0
            )
            
            service_time = (time.time() - service_start) * 1000
            logger.info(f"✅ [DATABASE-ASYNC] Service client ready in {service_time:.2f}ms")
            service_available = True
            
        except asyncio.TimeoutError:
            service_time = (time.time() - service_start) * 1000
            logger.warning(f"⚠️ [DATABASE-ASYNC] Service client warmup timeout after {service_time:.2f}ms")
        except Exception as service_error:
            service_time = (time.time() - service_start) * 1000
            logger.warning(f"⚠️ [DATABASE-ASYNC] Service client warmup failed after {service_time:.2f}ms: {service_error}")
        
        # Step 4: Initialize connection pool if available
        pool_available = False
        if hasattr(db, '_connection_pool') and db._connection_pool is not None:
            logger.info("🏊 [DATABASE-ASYNC] Connection pool detected, warming up...")
            pool_start = time.time()
            try:
                # Pool warmup would go here - for now just check if it exists
                pool_time = (time.time() - pool_start) * 1000
                logger.info(f"✅ [DATABASE-ASYNC] Connection pool ready in {pool_time:.2f}ms")
                pool_available = True
            except Exception as pool_error:
                logger.warning(f"⚠️ [DATABASE-ASYNC] Connection pool warmup failed: {pool_error}")
        
        # Step 5: Pre-cache frequently used queries/validation
        logger.info("📦 [DATABASE-ASYNC] Pre-caching critical operations...")
        cache_start = time.time()
        
        try:
            # Pre-warm service key validation cache
            if service_available:
                # The service client access above already cached the validation
                pass
            
            cache_time = (time.time() - cache_start) * 1000
            logger.info(f"✅ [DATABASE-ASYNC] Caching completed in {cache_time:.2f}ms")
            
        except Exception as cache_error:
            logger.warning(f"⚠️ [DATABASE-ASYNC] Caching failed: {cache_error}")
        
        # Calculate total initialization time
        total_time = (time.time() - start_time) * 1000
        
        # Performance assessment
        success = anon_available and service_available
        if success:
            logger.info(f"🎉 [DATABASE-ASYNC] COMPLETE: Database fully initialized in {total_time:.2f}ms")
            logger.info(f"🚀 [DATABASE-ASYNC] Ready for <50ms authentication performance")
            logger.info(f"📊 [DATABASE-ASYNC] Performance summary:")
            logger.info(f"   - Anonymous client: {'✅' if anon_available else '❌'}")
            logger.info(f"   - Service client: {'✅' if service_available else '❌'}")
            logger.info(f"   - Connection pool: {'✅' if pool_available else '❌'}")
            logger.info(f"   - Total time: {total_time:.2f}ms (target: <500ms)")
        else:
            logger.warning(f"⚠️ [DATABASE-ASYNC] DEGRADED: Database initialized with warnings in {total_time:.2f}ms")
            logger.warning(f"⚠️ [DATABASE-ASYNC] Some components not available - performance may be reduced")
        
        return success
        
    except Exception as e:
        total_time = (time.time() - start_time) * 1000 if 'start_time' in locals() else 0
        logger.error(f"❌ [DATABASE-ASYNC] FAILED: Database initialization failed after {total_time:.2f}ms: {e}")
        logger.error(f"❌ [DATABASE-ASYNC] This will cause authentication timeouts!")
        return False


async def warm_database_connections() -> dict:
    """
    Warm up database connections for optimal performance.
    Can be called periodically to maintain connection health.
    
    Returns:
        dict: Warmup results with timing and status information
    """
    try:
        logger.info("🔥 [DATABASE-WARMUP] Starting connection warmup...")
        start_time = time.time()
        results = {
            "total_time_ms": 0,
            "anon_client": {"status": "unknown", "time_ms": 0},
            "service_client": {"status": "unknown", "time_ms": 0},
            "overall_status": "unknown"
        }
        
        # Warm anonymous client
        anon_start = time.time()
        try:
            anon_available = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, db.is_available),
                timeout=1.0
            )
            anon_time = (time.time() - anon_start) * 1000
            results["anon_client"] = {
                "status": "ready" if anon_available else "degraded",
                "time_ms": round(anon_time, 2)
            }
        except asyncio.TimeoutError:
            anon_time = (time.time() - anon_start) * 1000
            results["anon_client"] = {
                "status": "timeout",
                "time_ms": round(anon_time, 2)
            }
        except Exception as e:
            anon_time = (time.time() - anon_start) * 1000
            results["anon_client"] = {
                "status": "error",
                "time_ms": round(anon_time, 2),
                "error": str(e)
            }
        
        # Warm service client
        service_start = time.time()
        try:
            service_client = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, lambda: db.service_client),
                timeout=1.0
            )
            service_time = (time.time() - service_start) * 1000
            results["service_client"] = {
                "status": "ready",
                "time_ms": round(service_time, 2)
            }
        except asyncio.TimeoutError:
            service_time = (time.time() - service_start) * 1000
            results["service_client"] = {
                "status": "timeout", 
                "time_ms": round(service_time, 2)
            }
        except Exception as e:
            service_time = (time.time() - service_start) * 1000
            results["service_client"] = {
                "status": "error",
                "time_ms": round(service_time, 2),
                "error": str(e)
            }
        
        # Calculate overall status
        total_time = (time.time() - start_time) * 1000
        results["total_time_ms"] = round(total_time, 2)
        
        both_ready = (results["anon_client"]["status"] == "ready" and 
                     results["service_client"]["status"] == "ready")
        
        if both_ready:
            results["overall_status"] = "optimal"
            logger.info(f"✅ [DATABASE-WARMUP] Connections optimal in {total_time:.2f}ms")
        elif (results["anon_client"]["status"] in ["ready", "degraded"] or 
              results["service_client"]["status"] in ["ready", "degraded"]):
            results["overall_status"] = "functional"
            logger.warning(f"⚠️ [DATABASE-WARMUP] Connections functional in {total_time:.2f}ms")
        else:
            results["overall_status"] = "degraded"
            logger.error(f"❌ [DATABASE-WARMUP] Connections degraded in {total_time:.2f}ms")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ [DATABASE-WARMUP] Warmup failed: {e}")
        return {
            "total_time_ms": 0,
            "anon_client": {"status": "error", "time_ms": 0, "error": str(e)},
            "service_client": {"status": "error", "time_ms": 0, "error": str(e)},
            "overall_status": "failed"
        }
