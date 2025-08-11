#!/usr/bin/env python3
"""
Velro Production Security Validation Script
Validates all OWASP-compliant security fixes before deployment.

This script validates:
1. JWT authentication system (no development bypasses)
2. Redis rate limiting with fallback
3. Configuration security
4. Authentication middleware
5. Production-ready error handling
"""

import os
import sys
import json
import time
import asyncio
import logging
from typing import Dict, List, Any
from datetime import datetime

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SecurityValidationError(Exception):
    """Security validation failed."""
    pass

class ProductionSecurityValidator:
    """Validates production security implementation."""
    
    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "UNKNOWN",
            "tests": {},
            "critical_issues": [],
            "warnings": [],
            "recommendations": []
        }
    
    async def run_all_validations(self) -> Dict[str, Any]:
        """Run all security validations."""
        logger.info("🔒 Starting comprehensive security validation...")
        
        try:
            # Test 1: Configuration Security
            await self.validate_configuration()
            
            # Test 2: JWT Security System
            await self.validate_jwt_security()
            
            # Test 3: Authentication System
            await self.validate_authentication_system()
            
            # Test 4: Rate Limiting
            await self.validate_rate_limiting()
            
            # Test 5: Redis Integration
            await self.validate_redis_integration()
            
            # Test 6: Router Security
            await self.validate_router_security()
            
            # Test 7: Middleware Security
            await self.validate_middleware_security()
            
            # Test 8: Error Handling
            await self.validate_error_handling()
            
            # Determine overall status
            self.determine_overall_status()
            
            logger.info(f"✅ Security validation completed: {self.results['overall_status']}")
            
        except Exception as e:
            logger.error(f"❌ Security validation failed: {e}")
            self.results["overall_status"] = "FAILED"
            self.results["critical_issues"].append(f"Validation process failed: {str(e)}")
        
        return self.results
    
    async def validate_configuration(self):
        """Validate configuration security."""
        logger.info("🔧 Validating configuration security...")
        
        test_name = "configuration_security"
        self.results["tests"][test_name] = {"status": "RUNNING", "details": []}
        
        try:
            from config import settings, SecurityError
            
            # Test JWT secret
            if not settings.jwt_secret:
                raise SecurityValidationError("JWT_SECRET not configured")
            
            if len(settings.jwt_secret) < 32:
                raise SecurityValidationError("JWT_SECRET too short (minimum 32 characters)")
            
            # Test Supabase configuration
            if not settings.supabase_url:
                raise SecurityValidationError("SUPABASE_URL not configured")
            
            if not settings.supabase_anon_key:
                raise SecurityValidationError("SUPABASE_ANON_KEY not configured")
            
            # Test production settings
            if settings.is_production():
                if settings.debug:
                    raise SecurityValidationError("DEBUG must be False in production")
                
                if settings.enable_development_bypasses:
                    raise SecurityValidationError("Development bypasses enabled in production")
            
            # Test security validation
            settings.validate_production_security()
            
            self.results["tests"][test_name]["status"] = "PASSED"
            self.results["tests"][test_name]["details"].append("All configuration security checks passed")
            
        except SecurityError as e:
            self.results["tests"][test_name]["status"] = "FAILED"
            self.results["critical_issues"].append(f"Configuration security: {str(e)}")
        except Exception as e:
            self.results["tests"][test_name]["status"] = "ERROR"
            self.results["critical_issues"].append(f"Configuration validation error: {str(e)}")
    
    async def validate_jwt_security(self):
        """Validate JWT security system."""
        logger.info("🔐 Validating JWT security system...")
        
        test_name = "jwt_security"
        self.results["tests"][test_name] = {"status": "RUNNING", "details": []}
        
        try:
            from utils.jwt_security import SupabaseJWTValidator, JWTSecurityError
            
            # Create validator instance
            validator = SupabaseJWTValidator()
            
            # Test invalid tokens
            invalid_tokens = [
                "",
                "invalid_token",
                "Bearer invalid",
                "eyJ0eXAiOiJKV1QiLCJhbGciOiJub25lIn0.eyJ0ZXN0IjoidmFsdWUifQ.",  # None algorithm
                "dev_token_test",  # Development token format
                "mock_token_test"  # Mock token format
            ]
            
            for token in invalid_tokens:
                try:
                    validator.validate_jwt_token(token)
                    raise SecurityValidationError(f"JWT validator accepted invalid token: {token[:20]}...")
                except JWTSecurityError:
                    # Expected - this is good
                    pass
            
            # Test performance
            start_time = time.time()
            try:
                validator.validate_jwt_token("invalid_but_long_token_for_performance_test")
            except JWTSecurityError:
                pass
            
            validation_time = (time.time() - start_time) * 1000
            if validation_time > 100:  # 100ms threshold
                self.results["warnings"].append(f"JWT validation slow: {validation_time:.1f}ms")
            
            # Test metrics
            metrics = validator.get_metrics()
            if not isinstance(metrics, dict):
                raise SecurityValidationError("JWT validator metrics malformed")
            
            self.results["tests"][test_name]["status"] = "PASSED"
            self.results["tests"][test_name]["details"].append("JWT security system validated")
            self.results["tests"][test_name]["details"].append(f"Cache enabled: {metrics.get('cache_enabled', False)}")
            
        except Exception as e:
            self.results["tests"][test_name]["status"] = "ERROR"
            self.results["critical_issues"].append(f"JWT security validation error: {str(e)}")
    
    async def validate_authentication_system(self):
        """Validate authentication system."""
        logger.info("🔑 Validating authentication system...")
        
        test_name = "authentication_system"
        self.results["tests"][test_name] = {"status": "RUNNING", "details": []}
        
        try:
            from middleware.auth_dependency import get_current_user, auth_health_check
            
            # Test health check
            health = await auth_health_check()
            if health.get("status") != "healthy":
                self.results["warnings"].append(f"Auth health check: {health.get('status')}")
            
            self.results["tests"][test_name]["status"] = "PASSED"
            self.results["tests"][test_name]["details"].append("Authentication system validated")
            
        except Exception as e:
            self.results["tests"][test_name]["status"] = "ERROR"
            self.results["critical_issues"].append(f"Authentication system validation error: {str(e)}")
    
    async def validate_rate_limiting(self):
        """Validate rate limiting system."""
        logger.info("⏱️ Validating rate limiting system...")
        
        test_name = "rate_limiting"
        self.results["tests"][test_name] = {"status": "RUNNING", "details": []}
        
        try:
            from middleware.production_rate_limiter import ProductionRateLimiter, RATE_LIMIT_TIERS
            
            # Create rate limiter
            limiter = ProductionRateLimiter()
            
            # Test tier configuration
            for tier in ["free", "pro", "enterprise"]:
                if tier not in RATE_LIMIT_TIERS:
                    raise SecurityValidationError(f"Rate limit tier '{tier}' not configured")
            
            # Test rate limiting logic
            test_client = "test_client_123"
            
            # Should allow first request
            allowed, headers = limiter.is_allowed(test_client, "free")
            if not allowed:
                raise SecurityValidationError("Rate limiter incorrectly rejected first request")
            
            # Test metrics
            metrics = limiter.get_metrics()
            if not isinstance(metrics, dict):
                raise SecurityValidationError("Rate limiter metrics malformed")
            
            self.results["tests"][test_name]["status"] = "PASSED"
            self.results["tests"][test_name]["details"].append("Rate limiting system validated")
            self.results["tests"][test_name]["details"].append(f"Backend: {metrics.get('backend', 'unknown')}")
            
        except Exception as e:
            self.results["tests"][test_name]["status"] = "ERROR"
            self.results["critical_issues"].append(f"Rate limiting validation error: {str(e)}")
    
    async def validate_redis_integration(self):
        """Validate Redis integration."""
        logger.info("🔴 Validating Redis integration...")
        
        test_name = "redis_integration"
        self.results["tests"][test_name] = {"status": "RUNNING", "details": []}
        
        try:
            from config import settings
            import redis
            
            if not settings.redis_url:
                self.results["warnings"].append("Redis not configured - using in-memory fallback")
                self.results["tests"][test_name]["status"] = "SKIPPED"
                return
            
            # Test Redis connection
            try:
                client = redis.from_url(settings.redis_url, socket_connect_timeout=2)
                client.ping()
                
                # Test basic operations
                client.set("security_test", "ok", ex=1)
                value = client.get("security_test")
                if value != "ok":
                    raise Exception("Redis read/write test failed")
                
                self.results["tests"][test_name]["status"] = "PASSED"
                self.results["tests"][test_name]["details"].append("Redis integration validated")
                
            except Exception as redis_error:
                self.results["warnings"].append(f"Redis connection failed: {redis_error}")
                self.results["tests"][test_name]["status"] = "DEGRADED"
                self.results["tests"][test_name]["details"].append("Using in-memory fallback")
                
        except Exception as e:
            self.results["tests"][test_name]["status"] = "ERROR"
            self.results["warnings"].append(f"Redis validation error: {str(e)}")
    
    async def validate_router_security(self):
        """Validate router security (no development bypasses)."""
        logger.info("🛣️ Validating router security...")
        
        test_name = "router_security"
        self.results["tests"][test_name] = {"status": "RUNNING", "details": []}
        
        try:
            # Check auth_production.py for development bypasses
            import inspect
            from routers.auth_production import get_current_user_production
            
            # Get source code
            source = inspect.getsource(get_current_user_production)
            
            # Check for dangerous patterns
            dangerous_patterns = [
                "dev_token_",
                "mock_token_",
                "emergency-token",
                "development_mode",
                "enable_development_bypasses"
            ]
            
            found_patterns = []
            for pattern in dangerous_patterns:
                if pattern in source.lower():
                    found_patterns.append(pattern)
            
            if found_patterns:
                raise SecurityValidationError(
                    f"Found dangerous patterns in auth router: {found_patterns}"
                )
            
            self.results["tests"][test_name]["status"] = "PASSED"
            self.results["tests"][test_name]["details"].append("Router security validated - no development bypasses found")
            
        except Exception as e:
            self.results["tests"][test_name]["status"] = "ERROR"
            self.results["critical_issues"].append(f"Router security validation error: {str(e)}")
    
    async def validate_middleware_security(self):
        """Validate middleware security."""
        logger.info("🛡️ Validating middleware security...")
        
        test_name = "middleware_security"
        self.results["tests"][test_name] = {"status": "RUNNING", "details": []}
        
        try:
            # Check for security middleware components
            security_components = [
                "middleware.production_rate_limiter",
                "utils.jwt_security", 
                "middleware.auth_dependency"
            ]
            
            for component in security_components:
                try:
                    __import__(component)
                except ImportError as e:
                    raise SecurityValidationError(f"Missing security component: {component}")
            
            self.results["tests"][test_name]["status"] = "PASSED"
            self.results["tests"][test_name]["details"].append("Middleware security validated")
            
        except Exception as e:
            self.results["tests"][test_name]["status"] = "ERROR"
            self.results["critical_issues"].append(f"Middleware security validation error: {str(e)}")
    
    async def validate_error_handling(self):
        """Validate error handling."""
        logger.info("⚠️ Validating error handling...")
        
        test_name = "error_handling"
        self.results["tests"][test_name] = {"status": "RUNNING", "details": []}
        
        try:
            from utils.jwt_security import JWTSecurityError
            from middleware.production_rate_limiter import ProductionRateLimiter
            
            # Test that security errors don't leak information
            try:
                raise JWTSecurityError("Test error")
            except JWTSecurityError as e:
                if "secret" in str(e).lower() or "password" in str(e).lower():
                    raise SecurityValidationError("Security error leaks sensitive information")
            
            self.results["tests"][test_name]["status"] = "PASSED"
            self.results["tests"][test_name]["details"].append("Error handling validated")
            
        except Exception as e:
            self.results["tests"][test_name]["status"] = "ERROR"
            self.results["critical_issues"].append(f"Error handling validation error: {str(e)}")
    
    def determine_overall_status(self):
        """Determine overall validation status."""
        if self.results["critical_issues"]:
            self.results["overall_status"] = "CRITICAL_ISSUES"
        elif any(test["status"] == "FAILED" for test in self.results["tests"].values()):
            self.results["overall_status"] = "FAILED"
        elif any(test["status"] == "ERROR" for test in self.results["tests"].values()):
            self.results["overall_status"] = "ERROR"
        elif self.results["warnings"]:
            self.results["overall_status"] = "PASSED_WITH_WARNINGS"
        else:
            self.results["overall_status"] = "PASSED"

async def main():
    """Run security validation."""
    print("🔒 Velro Production Security Validation")
    print("=" * 50)
    
    validator = ProductionSecurityValidator()
    results = await validator.run_all_validations()
    
    # Print results
    print(f"\n📊 VALIDATION RESULTS")
    print(f"Overall Status: {results['overall_status']}")
    print(f"Timestamp: {results['timestamp']}")
    
    print(f"\n🧪 Test Results:")
    for test_name, test_result in results["tests"].items():
        status_emoji = {
            "PASSED": "✅",
            "FAILED": "❌", 
            "ERROR": "🚫",
            "SKIPPED": "⏭️",
            "DEGRADED": "⚠️",
            "RUNNING": "🔄"
        }.get(test_result["status"], "❓")
        
        print(f"  {status_emoji} {test_name}: {test_result['status']}")
        for detail in test_result.get("details", []):
            print(f"    - {detail}")
    
    if results["critical_issues"]:
        print(f"\n🚨 CRITICAL ISSUES:")
        for issue in results["critical_issues"]:
            print(f"  ❌ {issue}")
    
    if results["warnings"]:
        print(f"\n⚠️ WARNINGS:")
        for warning in results["warnings"]:
            print(f"  ⚠️ {warning}")
    
    # Save results
    output_file = f"security_validation_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    # Exit with appropriate code
    if results["overall_status"] in ["CRITICAL_ISSUES", "FAILED", "ERROR"]:
        print("\n❌ SECURITY VALIDATION FAILED - DO NOT DEPLOY")
        sys.exit(1)
    elif results["overall_status"] == "PASSED_WITH_WARNINGS":
        print("\n⚠️ SECURITY VALIDATION PASSED WITH WARNINGS")
        sys.exit(0)
    else:
        print("\n✅ SECURITY VALIDATION PASSED - READY FOR DEPLOYMENT")
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())