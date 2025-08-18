"""
Developer Tools and Local Development Debugging Utilities
Comprehensive toolkit for local development and testing.
"""
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from uuid import uuid4, UUID
from dataclasses import dataclass, asdict
from pathlib import Path
import os

from config import settings
from database import SupabaseClient
from models.user import UserResponse, UserCreate, UserLogin, Token
from services.auth_service import AuthService
from utils.auth_debugger import auth_debugger
from utils.production_debugger import production_debugger, DebugLevel

logger = logging.getLogger(__name__)


@dataclass
class MockUser:
    """Mock user for development testing."""
    id: UUID
    email: str
    password: str
    display_name: str
    credits_balance: int
    role: str


@dataclass
class TestResult:
    """Test execution result."""
    test_name: str
    success: bool
    duration_ms: float
    message: str
    details: Dict[str, Any]
    errors: List[str]


class DeveloperToolkit:
    """Comprehensive development and debugging toolkit."""
    
    def __init__(self):
        self.mock_users = self._create_mock_users()
        self.test_results: List[TestResult] = []
        self.active_test_session = None
        
    def _create_mock_users(self) -> List[MockUser]:
        """Create predefined mock users for testing."""
        return [
            MockUser(
                id=UUID("bd1a2f69-89eb-489f-9288-8aacf4924763"),
                email="demo@example.com",
                password="demo123456",
                display_name="Demo User",
                credits_balance=1000,
                role="viewer"
            ),
            MockUser(
                id=UUID("550e8400-e29b-41d4-a716-446655440000"),
                email="test@velro.ai",
                password="test123456",
                display_name="Test User",
                credits_balance=500,
                role="viewer"
            ),
            MockUser(
                id=UUID("123e4567-e89b-12d3-a456-426614174000"),
                email="admin@velro.ai",
                password="admin123456",
                display_name="Admin User",
                credits_balance=10000,
                role="admin"
            )
        ]
    
    def get_mock_user(self, identifier: str) -> Optional[MockUser]:
        """Get mock user by email or ID."""
        for user in self.mock_users:
            if user.email == identifier or str(user.id) == identifier:
                return user
        return None
    
    async def test_authentication_flow(self, email: str = None) -> TestResult:
        """Test complete authentication flow with mock or real data."""
        test_name = "authentication_flow"
        start_time = time.time()
        errors = []
        details = {}
        
        try:
            # Use provided email or default to demo user
            test_email = email or "demo@example.com"
            mock_user = self.get_mock_user(test_email)
            
            if not mock_user:
                errors.append(f"Mock user not found for {test_email}")
                return TestResult(
                    test_name=test_name,
                    success=False,
                    duration_ms=(time.time() - start_time) * 1000,
                    message=f"Mock user not found: {test_email}",
                    details=details,
                    errors=errors
                )
            
            # Test database connection
            db_client = SupabaseClient()
            details["database_available"] = db_client.is_available()
            
            # Test auth service initialization
            auth_service = AuthService(db_client)
            details["auth_service_initialized"] = True
            
            # Test user creation (if in development mode)
            if settings.development_mode:
                user_create = UserCreate(
                    email=mock_user.email,
                    password=mock_user.password,
                    full_name=mock_user.display_name
                )
                
                try:
                    # This might fail if user already exists - that's okay
                    user_response = await auth_service.register_user(user_create)
                    details["user_registration"] = "success"
                    details["registered_user_id"] = str(user_response.id)
                except Exception as reg_error:
                    details["user_registration"] = f"failed: {str(reg_error)[:100]}"
            
            # Test authentication
            user_login = UserLogin(email=mock_user.email, password=mock_user.password)
            auth_result = await auth_service.authenticate_user(user_login)
            
            if auth_result:
                details["authentication"] = "success"
                details["authenticated_user"] = {
                    "id": str(auth_result.id),
                    "email": auth_result.email,
                    "credits": auth_result.credits_balance
                }
                
                # Test token creation
                token = await auth_service.create_access_token(auth_result)
                details["token_creation"] = "success"
                details["token_type"] = token.token_type
                details["token_length"] = len(token.access_token)
                
                # Test token validation
                from utils.auth_debugger import debug_token
                token_analysis = debug_token(token.access_token)
                details["token_analysis"] = {
                    "type": token_analysis.token_type,
                    "valid": token_analysis.is_valid,
                    "format_valid": token_analysis.format_valid
                }
                
            else:
                errors.append("Authentication failed")
                details["authentication"] = "failed"
            
            success = len(errors) == 0 and auth_result is not None
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                success=success,
                duration_ms=duration_ms,
                message=f"Authentication flow test completed - {'Success' if success else 'Failed'}",
                details=details,
                errors=errors
            )
            
            self.test_results.append(result)
            return result
            
        except Exception as e:
            errors.append(f"Test execution error: {str(e)}")
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration_ms,
                message=f"Authentication flow test failed: {str(e)[:100]}",
                details=details,
                errors=errors
            )
            
            self.test_results.append(result)
            return result
    
    async def test_token_lifecycle(self, user_email: str = "demo@example.com") -> TestResult:
        """Test complete token lifecycle including creation, validation, and refresh."""
        test_name = "token_lifecycle"
        start_time = time.time()
        errors = []
        details = {}
        
        try:
            mock_user = self.get_mock_user(user_email)
            if not mock_user:
                errors.append(f"Mock user not found: {user_email}")
                return TestResult(
                    test_name=test_name,
                    success=False,
                    duration_ms=(time.time() - start_time) * 1000,
                    message=f"Mock user not found: {user_email}",
                    details=details,
                    errors=errors
                )
            
            # Initialize auth service
            db_client = SupabaseClient()
            auth_service = AuthService(db_client)
            
            # Authenticate user
            user_login = UserLogin(email=mock_user.email, password=mock_user.password)
            user = await auth_service.authenticate_user(user_login)
            
            if not user:
                errors.append("User authentication failed")
                return TestResult(
                    test_name=test_name,
                    success=False,
                    duration_ms=(time.time() - start_time) * 1000,
                    message="User authentication failed",
                    details=details,
                    errors=errors
                )
            
            # Test token creation
            token = await auth_service.create_access_token(user)
            details["token_created"] = True
            details["token_type"] = token.token_type
            details["expires_in"] = token.expires_in
            
            # Test token analysis
            from utils.auth_debugger import debug_token
            analysis = debug_token(token.access_token)
            details["token_analysis"] = {
                "type": analysis.token_type,
                "valid": analysis.is_valid,
                "format_valid": analysis.format_valid,
                "signature_valid": analysis.signature_valid,
                "expired": analysis.expired,
                "security_flags": analysis.security_flags
            }
            
            # Test middleware token validation
            try:
                from middleware.auth import AuthMiddleware
                temp_middleware = AuthMiddleware(app=None)
                validated_user = await temp_middleware._verify_token(token.access_token)
                details["middleware_validation"] = "success"
                details["validated_user_id"] = str(validated_user.id)
            except Exception as middleware_error:
                errors.append(f"Middleware validation failed: {str(middleware_error)[:100]}")
                details["middleware_validation"] = "failed"
            
            # Test token refresh (if supported)
            try:
                # Note: This might not work with all token types
                if hasattr(token, 'refresh_token') and token.refresh_token:
                    refresh_result = await auth_service.refresh_access_token(token.refresh_token)
                    if refresh_result:
                        details["token_refresh"] = "success"
                        details["new_token_length"] = len(refresh_result.access_token)
                    else:
                        details["token_refresh"] = "failed"
                else:
                    details["token_refresh"] = "not_applicable"
            except Exception as refresh_error:
                details["token_refresh"] = f"error: {str(refresh_error)[:50]}"
            
            success = len(errors) == 0
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                success=success,
                duration_ms=duration_ms,
                message=f"Token lifecycle test completed - {'Success' if success else 'Partial success'}",
                details=details,
                errors=errors
            )
            
            self.test_results.append(result)
            return result
            
        except Exception as e:
            errors.append(f"Token lifecycle test error: {str(e)}")
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration_ms,
                message=f"Token lifecycle test failed: {str(e)[:100]}",
                details=details,
                errors=errors
            )
            
            self.test_results.append(result)
            return result
    
    async def test_database_connectivity(self) -> TestResult:
        """Test database connectivity and basic operations."""
        test_name = "database_connectivity"
        start_time = time.time()
        errors = []
        details = {}
        
        try:
            # Test Supabase client initialization
            db_client = SupabaseClient()
            details["client_initialized"] = True
            
            # Test availability
            is_available = db_client.is_available()
            details["database_available"] = is_available
            
            if not is_available:
                errors.append("Database not available")
                details["skip_reason"] = "Database unavailable, using mock mode"
            else:
                # Test basic query
                try:
                    result = db_client.client.table('users').select('id').limit(1).execute()
                    details["basic_query"] = "success"
                    details["query_result_count"] = len(result.data) if result.data else 0
                except Exception as query_error:
                    errors.append(f"Basic query failed: {str(query_error)[:100]}")
                    details["basic_query"] = "failed"
                
                # Test service client (if available)
                try:
                    service_result = db_client.service_client.table('users').select('id').limit(1).execute()
                    details["service_client_query"] = "success"
                    details["service_query_result_count"] = len(service_result.data) if service_result.data else 0
                except Exception as service_error:
                    details["service_client_query"] = f"failed: {str(service_error)[:100]}"
            
            # Test configuration
            details["supabase_url"] = settings.supabase_url[:30] + "..." if len(settings.supabase_url) > 30 else settings.supabase_url
            details["anon_key_length"] = len(settings.supabase_anon_key)
            details["service_key_configured"] = bool(settings.supabase_service_role_key)
            
            success = len(errors) == 0 or (not is_available and "mock mode" in str(details))
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                success=success,
                duration_ms=duration_ms,
                message=f"Database connectivity test completed - {'Success' if success else 'Issues detected'}",
                details=details,
                errors=errors
            )
            
            self.test_results.append(result)
            return result
            
        except Exception as e:
            errors.append(f"Database connectivity test error: {str(e)}")
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration_ms,
                message=f"Database connectivity test failed: {str(e)[:100]}",
                details=details,
                errors=errors
            )
            
            self.test_results.append(result)
            return result
    
    async def test_cors_configuration(self) -> TestResult:
        """Test CORS configuration and common issues."""
        test_name = "cors_configuration"
        start_time = time.time()
        errors = []
        details = {}
        
        try:
            # Get CORS configuration
            cors_origins = settings.cors_origins
            details["configured_origins"] = cors_origins
            details["origins_count"] = len(cors_origins)
            
            # Check for common issues
            issues = []
            recommendations = []
            
            # Check for localhost in production
            if settings.is_production():
                localhost_origins = [origin for origin in cors_origins if 'localhost' in origin]
                if localhost_origins:
                    issues.append("Localhost origins found in production")
                    recommendations.append("Remove localhost origins in production")
                    details["localhost_origins"] = localhost_origins
            
            # Check for wildcard usage
            if "*" in cors_origins:
                if settings.is_production():
                    issues.append("Wildcard CORS origin in production")
                    recommendations.append("Use specific origins instead of wildcard in production")
                details["uses_wildcard"] = True
            
            # Check for empty origins
            if not cors_origins:
                issues.append("No CORS origins configured")
                recommendations.append("Configure CORS origins for your frontend")
            
            # Check for HTTPS/HTTP mismatch
            http_origins = [origin for origin in cors_origins if origin.startswith('http://')]
            https_origins = [origin for origin in cors_origins if origin.startswith('https://')]
            
            details["http_origins_count"] = len(http_origins)
            details["https_origins_count"] = len(https_origins)
            
            if settings.is_production() and http_origins:
                issues.append("HTTP origins found in production")
                recommendations.append("Use HTTPS origins in production")
            
            # Test CORS with common frontend URLs
            common_origins = [
                "http://localhost:3000",
                "http://localhost:3001",
                "https://velro-frontend-production.up.railway.app"
            ]
            
            origin_tests = {}
            for origin in common_origins:
                origin_allowed = (
                    origin in cors_origins or 
                    "*" in cors_origins or
                    any(origin.endswith(allowed.replace("*", "")) for allowed in cors_origins if "*" in allowed)
                )
                origin_tests[origin] = origin_allowed
            
            details["origin_tests"] = origin_tests
            details["issues"] = issues
            details["recommendations"] = recommendations
            
            success = len(issues) == 0
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                success=success,
                duration_ms=duration_ms,
                message=f"CORS configuration test completed - {len(issues)} issues found",
                details=details,
                errors=errors
            )
            
            self.test_results.append(result)
            return result
            
        except Exception as e:
            errors.append(f"CORS configuration test error: {str(e)}")
            duration_ms = (time.time() - start_time) * 1000
            
            result = TestResult(
                test_name=test_name,
                success=False,
                duration_ms=duration_ms,
                message=f"CORS configuration test failed: {str(e)[:100]}",
                details=details,
                errors=errors
            )
            
            self.test_results.append(result)
            return result
    
    async def run_comprehensive_test_suite(self) -> Dict[str, Any]:
        """Run comprehensive test suite for authentication system."""
        suite_start = time.time()
        self.active_test_session = str(uuid4())
        
        production_debugger.log_event(
            "developer_tools", "test_suite_started",
            f"Comprehensive test suite started - Session: {self.active_test_session}",
            DebugLevel.SAFE
        )
        
        test_results = {}
        
        # Run all tests
        tests = [
            ("database_connectivity", self.test_database_connectivity()),
            ("cors_configuration", self.test_cors_configuration()),
            ("authentication_flow", self.test_authentication_flow()),
            ("token_lifecycle", self.test_token_lifecycle())
        ]
        
        for test_name, test_coro in tests:
            try:
                result = await test_coro
                test_results[test_name] = asdict(result)
            except Exception as e:
                test_results[test_name] = {
                    "test_name": test_name,
                    "success": False,
                    "duration_ms": 0,
                    "message": f"Test execution failed: {str(e)[:100]}",
                    "details": {},
                    "errors": [str(e)]
                }
        
        # Calculate summary
        total_tests = len(test_results)
        successful_tests = sum(1 for result in test_results.values() if result["success"])
        total_duration = (time.time() - suite_start) * 1000
        
        summary = {
            "session_id": self.active_test_session,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": settings.environment,
            "total_tests": total_tests,
            "successful_tests": successful_tests,
            "failed_tests": total_tests - successful_tests,
            "success_rate": (successful_tests / total_tests * 100) if total_tests > 0 else 0,
            "total_duration_ms": total_duration,
            "overall_status": "success" if successful_tests == total_tests else "partial" if successful_tests > 0 else "failed"
        }
        
        production_debugger.log_event(
            "developer_tools", "test_suite_completed",
            f"Test suite completed - {successful_tests}/{total_tests} tests passed",
            DebugLevel.SAFE,
            metadata={
                "session_id": self.active_test_session,
                "success_rate": summary["success_rate"],
                "duration_ms": total_duration
            }
        )
        
        return {
            "summary": summary,
            "test_results": test_results,
            "recommendations": self._generate_recommendations(test_results)
        }
    
    def _generate_recommendations(self, test_results: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on test results."""
        recommendations = []
        
        for test_name, result in test_results.items():
            if not result["success"]:
                if test_name == "database_connectivity":
                    recommendations.append("Check database connection settings and network connectivity")
                elif test_name == "cors_configuration":
                    recommendations.append("Review CORS origins configuration for frontend compatibility")
                elif test_name == "authentication_flow":
                    recommendations.append("Verify authentication service configuration and user credentials")
                elif test_name == "token_lifecycle":
                    recommendations.append("Check JWT configuration and token validation logic")
            
            # Add specific recommendations from test details
            if "recommendations" in result.get("details", {}):
                recommendations.extend(result["details"]["recommendations"])
        
        # Add general recommendations
        if settings.is_production():
            recommendations.append("Ensure all security configurations are production-ready")
        else:
            recommendations.append("Use comprehensive testing before deploying to production")
        
        return list(set(recommendations))  # Remove duplicates
    
    def get_test_history(self, limit: int = 20) -> List[TestResult]:
        """Get recent test results."""
        return sorted(self.test_results, key=lambda x: x.test_name, reverse=True)[:limit]
    
    def export_test_results(self, format: str = "json") -> str:
        """Export test results for analysis."""
        export_data = {
            "export_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": settings.environment,
                "total_tests": len(self.test_results)
            },
            "test_results": [asdict(result) for result in self.test_results],
            "mock_users": [asdict(user) for user in self.mock_users],
            "configuration_summary": {
                "debug_mode": settings.debug,
                "development_mode": settings.development_mode,
                "cors_origins_count": len(settings.cors_origins),
                "database_configured": bool(settings.supabase_url)
            }
        }
        
        if format == "json":
            return json.dumps(export_data, indent=2, default=str)
        else:
            return export_data


# Global developer toolkit instance
dev_toolkit = DeveloperToolkit()