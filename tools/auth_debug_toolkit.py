"""
Authentication Debug Toolkit
Comprehensive debugging and validation tools for production authentication system.
Enterprise-grade diagnostics and troubleshooting utilities.
"""
import asyncio
import json
import logging
import time
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
import httpx
from dataclasses import dataclass, asdict

from config import settings
from database import SupabaseClient
from services.auth_service import AuthService
from utils.token_manager import get_token_manager, get_session_manager
from utils.auth_monitor import get_auth_monitor
from middleware.rate_limiting import get_rate_limiter
from models.user import UserResponse, Token

logger = logging.getLogger(__name__)

@dataclass
class AuthSystemStatus:
    """Authentication system status."""
    timestamp: datetime
    database_available: bool
    supabase_auth_available: bool
    cache_available: bool
    redis_available: bool
    token_manager_active: bool
    rate_limiter_active: bool
    security_monitor_active: bool
    environment: str
    active_sessions: int
    cached_tokens: int
    blocked_ips: int
    security_incidents_24h: int

@dataclass
class TokenValidationResult:
    """Token validation result."""
    is_valid: bool
    token_type: str
    user_id: Optional[str]
    email: Optional[str]
    expires_at: Optional[datetime]
    is_expired: bool
    error_message: Optional[str]
    validation_method: str
    metadata: Dict[str, Any]

class AuthDebugToolkit:
    """Comprehensive authentication debugging toolkit."""
    
    def __init__(self):
        self.db_client = SupabaseClient()
        self.auth_service = AuthService(self.db_client)
        self.token_manager = get_token_manager()
        self.session_manager = get_session_manager()
        self.auth_monitor = get_auth_monitor()
        self.rate_limiter = get_rate_limiter()
    
    async def get_system_status(self) -> AuthSystemStatus:
        """Get comprehensive authentication system status."""
        try:
            logger.info("🔍 [AUTH-DEBUG] Gathering system status...")
            
            # Test database connectivity
            db_available = self.db_client.is_available()
            
            # Test Supabase Auth availability
            supabase_auth_available = await self._test_supabase_auth()
            
            # Test cache availability
            cache_available = await self._test_cache_availability()
            
            # Test Redis availability
            redis_available = await self._test_redis_availability()
            
            # Get monitoring data
            dashboard_data = await self.auth_monitor.get_security_dashboard_data()
            security_incidents_24h = dashboard_data.get('summary', {}).get('total_events_24h', 0)
            
            status = AuthSystemStatus(
                timestamp=datetime.now(timezone.utc),
                database_available=db_available,
                supabase_auth_available=supabase_auth_available,
                cache_available=cache_available,
                redis_available=redis_available,
                token_manager_active=True,  # Always active if instantiated
                rate_limiter_active=True,   # Always active if instantiated
                security_monitor_active=True,  # Always active if instantiated
                environment=settings.environment,
                active_sessions=await self._count_active_sessions(),
                cached_tokens=await self._count_cached_tokens(),
                blocked_ips=await self._count_blocked_ips(),
                security_incidents_24h=security_incidents_24h
            )
            
            logger.info("✅ [AUTH-DEBUG] System status gathered successfully")
            return status
            
        except Exception as e:
            logger.error(f"❌ [AUTH-DEBUG] Failed to get system status: {e}")
            raise
    
    async def validate_token_comprehensive(self, token: str) -> TokenValidationResult:
        """Comprehensive token validation with detailed diagnostics."""
        try:
            logger.info(f"🔍 [AUTH-DEBUG] Validating token: {token[:20]}...")
            
            result = TokenValidationResult(
                is_valid=False,
                token_type="unknown",
                user_id=None,
                email=None,
                expires_at=None,
                is_expired=False,
                error_message=None,
                validation_method="unknown",
                metadata={}
            )
            
            # 1. Check token format
            if not token:
                result.error_message = "Empty token"
                return result
            
            # 2. Identify token type
            if token.startswith("mock_token_"):
                result.token_type = "mock"
                result = await self._validate_mock_token(token, result)
            elif token.startswith("emergency_token_"):
                result.token_type = "emergency"
                result = await self._validate_emergency_token(token, result)
            elif token.startswith("supabase_token_"):
                result.token_type = "custom"
                result = await self._validate_custom_token(token, result)
            else:
                result.token_type = "jwt"
                result = await self._validate_jwt_token(token, result)
            
            # 3. Additional metadata
            result.metadata.update({
                'token_length': len(token),
                'token_prefix': token[:20],
                'validation_timestamp': datetime.now(timezone.utc).isoformat(),
                'environment': settings.environment,
                'debug_mode': settings.debug
            })
            
            logger.info(f"✅ [AUTH-DEBUG] Token validation complete: {result.is_valid}")
            return result
            
        except Exception as e:
            logger.error(f"❌ [AUTH-DEBUG] Token validation failed: {e}")
            result = TokenValidationResult(
                is_valid=False,
                token_type="error",
                user_id=None,
                email=None,
                expires_at=None,
                is_expired=False,
                error_message=str(e),
                validation_method="error",
                metadata={}
            )
            return result
    
    async def _validate_mock_token(self, token: str, result: TokenValidationResult) -> TokenValidationResult:
        """Validate mock token."""
        result.validation_method = "mock_token"
        
        if settings.debug and settings.development_mode:
            user_id = token.replace("mock_token_", "")
            result.is_valid = True
            result.user_id = user_id
            result.email = f"mock@development.local"
            result.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            result.metadata.update({
                'development_mode': True,
                'security_level': 'low'
            })
        else:
            result.error_message = "Mock tokens not allowed in production"
            result.metadata.update({
                'security_violation': True,
                'attempted_environment': settings.environment
            })
        
        return result
    
    async def _validate_emergency_token(self, token: str, result: TokenValidationResult) -> TokenValidationResult:
        """Validate emergency token."""
        result.validation_method = "emergency_token"
        
        if settings.emergency_auth_mode:
            user_id = token.replace("emergency_token_", "")
            result.is_valid = True
            result.user_id = user_id
            result.email = f"emergency@development.local"
            result.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
            result.metadata.update({
                'emergency_mode': True,
                'security_level': 'medium'
            })
        else:
            result.error_message = "Emergency tokens not allowed"
            result.metadata.update({
                'security_violation': True,
                'emergency_mode_disabled': True
            })
        
        return result
    
    async def _validate_custom_token(self, token: str, result: TokenValidationResult) -> TokenValidationResult:
        """Validate custom token format."""
        result.validation_method = "custom_token"
        
        try:
            user_id = token.replace("supabase_token_", "")
            
            # Try to get user from database
            if self.db_client.is_available():
                profile_result = self.db_client.service_client.table('users').select('*').eq('id', user_id).execute()
                
                if profile_result.data and len(profile_result.data) > 0:
                    profile = profile_result.data[0]
                    result.is_valid = True
                    result.user_id = user_id
                    result.email = profile.get('email', 'unknown')
                    result.expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.jwt_expiration_seconds)
                    result.metadata.update({
                        'database_verified': True,
                        'profile_found': True
                    })
                else:
                    result.error_message = "User profile not found"
                    result.metadata.update({
                        'database_verified': True,
                        'profile_found': False
                    })
            else:
                result.error_message = "Database unavailable for verification"
                result.metadata.update({
                    'database_available': False
                })
        
        except Exception as e:
            result.error_message = f"Custom token validation failed: {e}"
        
        return result
    
    async def _validate_jwt_token(self, token: str, result: TokenValidationResult) -> TokenValidationResult:
        """Validate JWT token."""
        result.validation_method = "jwt_token"
        
        try:
            # Try Supabase validation first
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{settings.supabase_url}/auth/v1/user",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "apikey": settings.supabase_anon_key
                    }
                )
                
                if response.status_code == 200:
                    user_data = response.json()
                    result.is_valid = True
                    result.user_id = user_data.get("id")
                    result.email = user_data.get("email")
                    
                    # Parse expiry if available
                    if "exp" in user_data:
                        result.expires_at = datetime.fromtimestamp(user_data["exp"], timezone.utc)
                        result.is_expired = result.expires_at < datetime.now(timezone.utc)
                    
                    result.metadata.update({
                        'supabase_verified': True,
                        'user_metadata': user_data.get('user_metadata', {})
                    })
                else:
                    result.error_message = f"Supabase validation failed: {response.status_code}"
                    result.metadata.update({
                        'supabase_response_code': response.status_code,
                        'supabase_error': response.text
                    })
        
        except Exception as e:
            result.error_message = f"JWT validation failed: {e}"
            result.metadata.update({
                'jwt_validation_error': str(e)
            })
        
        return result
    
    async def test_auth_flow_end_to_end(self, email: str = None, password: str = None) -> Dict[str, Any]:
        """Test complete authentication flow end-to-end."""
        try:
            logger.info("🔍 [AUTH-DEBUG] Starting end-to-end auth flow test...")
            
            # Use test credentials if not provided
            if not email:
                email = f"test-{uuid4()}@example.com"
            if not password:
                password = "TestPass123!"
            
            test_results = {
                'test_id': str(uuid4()),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'email': email,
                'steps': [],
                'overall_success': False,
                'errors': []
            }
            
            # Step 1: Registration
            try:
                logger.info("🔍 [AUTH-DEBUG] Testing registration...")
                from models.user import UserCreate
                
                user_data = UserCreate(
                    email=email,
                    password=password,
                    full_name="Test User"
                )
                
                user = await self.auth_service.register_user(user_data)
                test_results['steps'].append({
                    'step': 'registration',
                    'success': True,
                    'user_id': str(user.id),
                    'email': user.email
                })
                
            except Exception as e:
                test_results['steps'].append({
                    'step': 'registration',
                    'success': False,
                    'error': str(e)
                })
                test_results['errors'].append(f"Registration failed: {e}")
            
            # Step 2: Login
            try:
                logger.info("🔍 [AUTH-DEBUG] Testing login...")
                from models.user import UserLogin
                
                credentials = UserLogin(email=email, password=password)
                user = await self.auth_service.authenticate_user(credentials)
                
                if user:
                    token = await self.auth_service.create_access_token(user)
                    test_results['steps'].append({
                        'step': 'login',
                        'success': True,
                        'user_id': str(user.id),
                        'token_length': len(token.access_token)
                    })
                    
                    # Step 3: Token validation
                    validation_result = await self.validate_token_comprehensive(token.access_token)
                    test_results['steps'].append({
                        'step': 'token_validation',
                        'success': validation_result.is_valid,
                        'token_type': validation_result.token_type,
                        'validation_method': validation_result.validation_method
                    })
                    
                else:
                    test_results['steps'].append({
                        'step': 'login',
                        'success': False,
                        'error': 'Authentication returned None'
                    })
                    test_results['errors'].append("Login failed: Authentication returned None")
                
            except Exception as e:
                test_results['steps'].append({
                    'step': 'login',
                    'success': False,
                    'error': str(e)
                })
                test_results['errors'].append(f"Login failed: {e}")
            
            # Determine overall success
            test_results['overall_success'] = all(step.get('success', False) for step in test_results['steps'])
            
            logger.info(f"✅ [AUTH-DEBUG] End-to-end test complete: {test_results['overall_success']}")
            return test_results
            
        except Exception as e:
            logger.error(f"❌ [AUTH-DEBUG] End-to-end test failed: {e}")
            return {
                'test_id': str(uuid4()),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'overall_success': False,
                'errors': [str(e)]
            }
    
    async def diagnose_auth_issues(self, token: str = None, user_id: str = None) -> Dict[str, Any]:
        """Diagnose authentication issues with detailed analysis."""
        try:
            logger.info("🔍 [AUTH-DEBUG] Starting authentication diagnostics...")
            
            diagnosis = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'system_status': {},
                'token_analysis': {},
                'user_analysis': {},
                'recommendations': [],
                'severity': 'info'
            }
            
            # 1. System status check
            system_status = await self.get_system_status()
            diagnosis['system_status'] = asdict(system_status)
            
            # Check for system issues
            if not system_status.database_available:
                diagnosis['recommendations'].append("Database is unavailable - check connection and credentials")
                diagnosis['severity'] = 'critical'
            
            if not system_status.supabase_auth_available:
                diagnosis['recommendations'].append("Supabase Auth is unavailable - check Supabase status and API keys")
                diagnosis['severity'] = 'high' if diagnosis['severity'] != 'critical' else 'critical'
            
            # 2. Token analysis
            if token:
                token_result = await self.validate_token_comprehensive(token)
                diagnosis['token_analysis'] = asdict(token_result)
                
                if not token_result.is_valid:
                    diagnosis['recommendations'].append(f"Token validation failed: {token_result.error_message}")
                    diagnosis['severity'] = 'high' if diagnosis['severity'] not in ['critical'] else diagnosis['severity']
                
                if token_result.is_expired:
                    diagnosis['recommendations'].append("Token has expired - user needs to refresh or re-authenticate")
                    diagnosis['severity'] = 'medium' if diagnosis['severity'] == 'info' else diagnosis['severity']
            
            # 3. User analysis
            if user_id:
                user_analysis = await self._analyze_user_status(user_id)
                diagnosis['user_analysis'] = user_analysis
                
                if not user_analysis.get('profile_exists', False):
                    diagnosis['recommendations'].append("User profile missing - may need to recreate profile")
                    diagnosis['severity'] = 'high' if diagnosis['severity'] not in ['critical'] else diagnosis['severity']
            
            # 4. Generate recommendations
            if not diagnosis['recommendations']:
                diagnosis['recommendations'].append("No issues detected - system appears healthy")
            
            logger.info(f"✅ [AUTH-DEBUG] Diagnostics complete: {diagnosis['severity']}")
            return diagnosis
            
        except Exception as e:
            logger.error(f"❌ [AUTH-DEBUG] Diagnostics failed: {e}")
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'severity': 'critical',
                'recommendations': ['Diagnostic system failure - check logs for details']
            }
    
    async def _test_supabase_auth(self) -> bool:
        """Test Supabase Auth availability."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.supabase_url}/auth/v1/settings")
                return response.status_code in [200, 404]  # 404 is also valid for some endpoints
        except Exception:
            return False
    
    async def _test_cache_availability(self) -> bool:
        """Test cache availability."""
        try:
            from utils.cache_manager import get_cache_manager, CacheLevel
            cache_manager = get_cache_manager()
            
            test_key = f"cache_test_{int(time.time())}"
            await cache_manager.set(test_key, "test_value", CacheLevel.L1_MEMORY, ttl=10)
            result = await cache_manager.get(test_key, CacheLevel.L1_MEMORY)
            await cache_manager.delete(test_key)
            
            return result == "test_value"
        except Exception:
            return False
    
    async def _test_redis_availability(self) -> bool:
        """Test Redis availability."""
        try:
            redis_client = await self.rate_limiter._get_redis_client()
            if redis_client:
                await redis_client.ping()
                return True
            return False
        except Exception:
            return False
    
    async def _count_active_sessions(self) -> int:
        """Count active user sessions."""
        try:
            # This would need to be implemented based on session storage
            # For now, return 0 as placeholder
            return 0
        except Exception:
            return 0
    
    async def _count_cached_tokens(self) -> int:
        """Count cached tokens."""
        try:
            # This would need to query the cache for token entries
            # For now, return 0 as placeholder
            return 0
        except Exception:
            return 0
    
    async def _count_blocked_ips(self) -> int:
        """Count blocked IP addresses."""
        try:
            # This would need to query blocked IPs from cache/database
            # For now, return 0 as placeholder
            return 0
        except Exception:
            return 0
    
    async def _analyze_user_status(self, user_id: str) -> Dict[str, Any]:
        """Analyze user status and profile."""
        try:
            analysis = {
                'user_id': user_id,
                'profile_exists': False,
                'profile_data': {},
                'recent_activity': [],
                'session_info': {}
            }
            
            # Check if user profile exists
            if self.db_client.is_available():
                try:
                    profile_result = self.db_client.service_client.table('users').select('*').eq('id', user_id).execute()
                    
                    if profile_result.data and len(profile_result.data) > 0:
                        analysis['profile_exists'] = True
                        analysis['profile_data'] = profile_result.data[0]
                
                except Exception as e:
                    analysis['profile_error'] = str(e)
            
            # Check session info
            session_status = await self.session_manager.check_session_timeout(user_id)
            analysis['session_info'] = session_status
            
            return analysis
            
        except Exception as e:
            return {
                'user_id': user_id,
                'error': str(e)
            }
    
    async def generate_debug_report(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Generate comprehensive debug report."""
        try:
            logger.info("🔍 [AUTH-DEBUG] Generating comprehensive debug report...")
            
            report = {
                'report_id': str(uuid4()),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'environment': settings.environment,
                'system_status': {},
                'configuration': {},
                'security_status': {},
                'performance_metrics': {},
                'recent_incidents': [],
                'recommendations': []
            }
            
            # System status
            system_status = await self.get_system_status()
            report['system_status'] = asdict(system_status)
            
            # Configuration (sanitized)
            report['configuration'] = {
                'environment': settings.environment,
                'debug_mode': settings.debug,
                'development_mode': settings.development_mode,
                'emergency_auth_mode': getattr(settings, 'emergency_auth_mode', False),
                'jwt_expiration_seconds': settings.jwt_expiration_seconds,
                'database_available': self.db_client.is_available()
            }
            
            if include_sensitive:
                report['configuration'].update({
                    'supabase_url': settings.supabase_url,
                    'supabase_anon_key_prefix': settings.supabase_anon_key[:10] + "..." if settings.supabase_anon_key else None
                })
            
            # Security status
            dashboard_data = await self.auth_monitor.get_security_dashboard_data()
            report['security_status'] = dashboard_data
            
            # Generate recommendations
            recommendations = []
            
            if not system_status.database_available:
                recommendations.append({
                    'priority': 'critical',
                    'issue': 'Database unavailable',
                    'recommendation': 'Check database connectivity and credentials'
                })
            
            if not system_status.supabase_auth_available:
                recommendations.append({
                    'priority': 'high',
                    'issue': 'Supabase Auth unavailable',
                    'recommendation': 'Verify Supabase configuration and service status'
                })
            
            if settings.debug and settings.is_production():
                recommendations.append({
                    'priority': 'high',
                    'issue': 'Debug mode enabled in production',
                    'recommendation': 'Disable debug mode in production environment'
                })
            
            if system_status.security_incidents_24h > 10:
                recommendations.append({
                    'priority': 'medium',
                    'issue': f'High security incidents: {system_status.security_incidents_24h}',
                    'recommendation': 'Review security logs and consider additional protection measures'
                })
            
            report['recommendations'] = recommendations
            
            logger.info("✅ [AUTH-DEBUG] Debug report generated successfully")
            return report
            
        except Exception as e:
            logger.error(f"❌ [AUTH-DEBUG] Failed to generate debug report: {e}")
            return {
                'report_id': str(uuid4()),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
                'partial_report': True
            }


# CLI Functions for debugging
async def main():
    """Main CLI function for auth debugging."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Authentication Debug Toolkit")
    parser.add_argument("command", choices=[
        "status", "validate-token", "test-flow", "diagnose", "report"
    ], help="Debug command to run")
    parser.add_argument("--token", help="Token to validate")
    parser.add_argument("--user-id", help="User ID to analyze")
    parser.add_argument("--email", help="Email for test flow")
    parser.add_argument("--password", help="Password for test flow")
    parser.add_argument("--include-sensitive", action="store_true", help="Include sensitive data in report")
    
    args = parser.parse_args()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    toolkit = AuthDebugToolkit()
    
    try:
        if args.command == "status":
            status = await toolkit.get_system_status()
            print(json.dumps(asdict(status), indent=2, default=str))
        
        elif args.command == "validate-token":
            if not args.token:
                print("Error: --token required for validate-token command")
                return
            
            result = await toolkit.validate_token_comprehensive(args.token)
            print(json.dumps(asdict(result), indent=2, default=str))
        
        elif args.command == "test-flow":
            result = await toolkit.test_auth_flow_end_to_end(args.email, args.password)
            print(json.dumps(result, indent=2, default=str))
        
        elif args.command == "diagnose":
            result = await toolkit.diagnose_auth_issues(args.token, args.user_id)
            print(json.dumps(result, indent=2, default=str))
        
        elif args.command == "report":
            result = await toolkit.generate_debug_report(args.include_sensitive)
            print(json.dumps(result, indent=2, default=str))
    
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())