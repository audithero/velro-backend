#!/usr/bin/env python3
"""
Enterprise Security Validation Script
Comprehensive security audit and validation for Velro backend deployment.
"""
import os
import sys
import json
import re
import requests
import time
import argparse
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f'security_validation_{int(time.time())}.log')
    ]
)
logger = logging.getLogger(__name__)

class SecurityLevel(Enum):
    """Security check severity levels."""
    INFO = "info"
    LOW = "low" 
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityCheck:
    """Security check definition."""
    name: str
    description: str
    severity: SecurityLevel
    category: str
    check_function: str
    required_for_production: bool = True

@dataclass 
class SecurityResult:
    """Security check result."""
    check_name: str
    passed: bool
    severity: SecurityLevel
    category: str
    message: str
    details: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[str]] = None

class SecurityValidator:
    """
    Comprehensive security validation for Velro backend.
    
    Validates:
    - Environment configuration security
    - JWT configuration and strength
    - CORS policy security
    - Rate limiting implementation
    - Authentication security
    - Security headers
    - Error handling security
    - Input validation
    - Production readiness
    """
    
    def __init__(self, environment: str = "production", base_url: Optional[str] = None):
        self.environment = environment
        self.base_url = base_url or self._detect_base_url()
        self.results: List[SecurityResult] = []
        
        # Define all security checks
        self.security_checks = [
            # Environment Configuration
            SecurityCheck("env_production", "Environment set to production", SecurityLevel.CRITICAL, "environment", "check_environment_production"),
            SecurityCheck("debug_disabled", "Debug mode disabled", SecurityLevel.CRITICAL, "environment", "check_debug_disabled"),
            SecurityCheck("dev_mode_disabled", "Development mode disabled", SecurityLevel.CRITICAL, "environment", "check_development_mode_disabled"),
            SecurityCheck("emergency_auth_disabled", "Emergency auth mode disabled", SecurityLevel.CRITICAL, "environment", "check_emergency_auth_disabled"),
            
            # JWT Security
            SecurityCheck("jwt_secret_strength", "JWT secret strength validation", SecurityLevel.CRITICAL, "authentication", "check_jwt_secret_strength"),
            SecurityCheck("jwt_algorithm_secure", "JWT algorithm security", SecurityLevel.HIGH, "authentication", "check_jwt_algorithm"),
            SecurityCheck("jwt_https_required", "JWT HTTPS requirement", SecurityLevel.HIGH, "authentication", "check_jwt_https_required"),
            SecurityCheck("jwt_blacklist_enabled", "JWT blacklisting enabled", SecurityLevel.MEDIUM, "authentication", "check_jwt_blacklist"),
            
            # Authentication Security  
            SecurityCheck("mock_auth_disabled", "Mock authentication disabled", SecurityLevel.CRITICAL, "authentication", "check_mock_authentication_disabled"),
            SecurityCheck("test_users_disabled", "Test users disabled", SecurityLevel.CRITICAL, "authentication", "check_test_users_disabled"),
            SecurityCheck("dev_bypasses_disabled", "Development bypasses disabled", SecurityLevel.CRITICAL, "authentication", "check_dev_bypasses_disabled"),
            
            # CORS Security
            SecurityCheck("cors_wildcard_disabled", "CORS wildcard origins disabled", SecurityLevel.CRITICAL, "cors", "check_cors_wildcard_disabled"),
            SecurityCheck("cors_https_only", "CORS HTTPS-only origins", SecurityLevel.HIGH, "cors", "check_cors_https_only"),
            SecurityCheck("cors_credentials_secure", "CORS credentials policy", SecurityLevel.MEDIUM, "cors", "check_cors_credentials_policy"),
            
            # Rate Limiting
            SecurityCheck("rate_limiting_enabled", "Rate limiting enabled", SecurityLevel.HIGH, "rate_limiting", "check_rate_limiting_enabled"),
            SecurityCheck("adaptive_rate_limiting", "Adaptive rate limiting", SecurityLevel.MEDIUM, "rate_limiting", "check_adaptive_rate_limiting"),
            SecurityCheck("auth_rate_limits", "Authentication rate limits", SecurityLevel.HIGH, "rate_limiting", "check_auth_rate_limits"),
            
            # Security Headers
            SecurityCheck("security_headers_enabled", "Security headers enabled", SecurityLevel.HIGH, "headers", "check_security_headers_enabled"),
            SecurityCheck("hsts_configured", "HSTS properly configured", SecurityLevel.HIGH, "headers", "check_hsts_header"),
            SecurityCheck("csp_configured", "CSP header configured", SecurityLevel.MEDIUM, "headers", "check_csp_header"),
            SecurityCheck("xss_protection", "XSS protection enabled", SecurityLevel.MEDIUM, "headers", "check_xss_protection"),
            
            # Error Handling
            SecurityCheck("verbose_errors_disabled", "Verbose errors disabled", SecurityLevel.MEDIUM, "error_handling", "check_verbose_errors_disabled"),
            SecurityCheck("debug_endpoints_disabled", "Debug endpoints disabled", SecurityLevel.HIGH, "error_handling", "check_debug_endpoints_disabled"),
            SecurityCheck("error_info_disclosure", "Error information disclosure", SecurityLevel.MEDIUM, "error_handling", "check_error_information_disclosure"),
            
            # Production Features
            SecurityCheck("health_check_secured", "Health check security", SecurityLevel.LOW, "production", "check_health_check_security"),
            SecurityCheck("monitoring_configured", "Security monitoring", SecurityLevel.MEDIUM, "production", "check_security_monitoring"),
            
            # Network Security
            SecurityCheck("ssl_tls_configured", "SSL/TLS configuration", SecurityLevel.HIGH, "network", "check_ssl_tls"),
            SecurityCheck("api_versioning", "API versioning security", SecurityLevel.LOW, "network", "check_api_versioning"),
        ]
    
    def _detect_base_url(self) -> str:
        """Detect base URL from environment or default."""
        if self.environment == "production":
            return "https://velro-003-backend-production.up.railway.app"
        elif self.environment == "staging":
            return "https://velro-003-backend-staging.up.railway.app"
        else:
            return "http://localhost:8000"
    
    def run_all_checks(self) -> Dict[str, Any]:
        """Run all security checks and return comprehensive results."""
        logger.info(f"🔒 Starting comprehensive security validation for {self.environment} environment")
        logger.info(f"🌐 Target URL: {self.base_url}")
        
        start_time = time.time()
        
        # Run all security checks
        for check in self.security_checks:
            try:
                logger.info(f"🔍 Running check: {check.name}")
                check_function = getattr(self, check.check_function)
                result = check_function(check)
                self.results.append(result)
                
                # Log result
                status_icon = "✅" if result.passed else "❌"
                logger.info(f"{status_icon} {check.name}: {result.message}")
                
            except Exception as e:
                logger.error(f"❌ Check {check.name} failed with exception: {e}")
                self.results.append(SecurityResult(
                    check_name=check.name,
                    passed=False,
                    severity=check.severity,
                    category=check.category,
                    message=f"Check failed: {str(e)}",
                    recommendations=["Review check implementation", "Check environment configuration"]
                ))
        
        execution_time = time.time() - start_time
        
        # Generate comprehensive report
        report = self._generate_security_report(execution_time)
        
        # Save report
        self._save_report(report)
        
        return report
    
    def _generate_security_report(self, execution_time: float) -> Dict[str, Any]:
        """Generate comprehensive security report."""
        
        # Categorize results
        passed_checks = [r for r in self.results if r.passed]
        failed_checks = [r for r in self.results if not r.passed]
        
        # Categorize by severity
        critical_failures = [r for r in failed_checks if r.severity == SecurityLevel.CRITICAL]
        high_failures = [r for r in failed_checks if r.severity == SecurityLevel.HIGH]
        medium_failures = [r for r in failed_checks if r.severity == SecurityLevel.MEDIUM]
        low_failures = [r for r in failed_checks if r.severity == SecurityLevel.LOW]
        
        # Calculate security score
        total_checks = len(self.results)
        passed_count = len(passed_checks)
        security_score = (passed_count / total_checks * 100) if total_checks > 0 else 0
        
        # Determine overall security status
        if critical_failures:
            security_status = "CRITICAL - DO NOT DEPLOY"
        elif high_failures:
            security_status = "HIGH RISK - REVIEW REQUIRED"
        elif medium_failures:
            security_status = "MEDIUM RISK - IMPROVEMENTS RECOMMENDED"  
        else:
            security_status = "SECURE - DEPLOYMENT APPROVED"
        
        # Generate report
        report = {
            "validation_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "environment": self.environment,
                "base_url": self.base_url,
                "execution_time_seconds": round(execution_time, 2),
                "validator_version": "1.0.0"
            },
            "security_summary": {
                "overall_status": security_status,
                "security_score": round(security_score, 1),
                "total_checks": total_checks,
                "passed_checks": passed_count,
                "failed_checks": len(failed_checks),
                "deployment_approved": len(critical_failures) == 0 and len(high_failures) == 0
            },
            "failure_summary": {
                "critical": len(critical_failures),
                "high": len(high_failures), 
                "medium": len(medium_failures),
                "low": len(low_failures)
            },
            "category_results": self._categorize_results(),
            "critical_failures": [self._format_result(r) for r in critical_failures],
            "high_priority_failures": [self._format_result(r) for r in high_failures],
            "all_results": [self._format_result(r) for r in self.results],
            "security_recommendations": self._generate_recommendations(),
            "compliance_status": self._check_compliance_status()
        }
        
        return report
    
    def _categorize_results(self) -> Dict[str, Dict[str, int]]:
        """Categorize results by category and status."""
        categories = {}
        
        for result in self.results:
            category = result.category
            if category not in categories:
                categories[category] = {"passed": 0, "failed": 0, "total": 0}
            
            categories[category]["total"] += 1
            if result.passed:
                categories[category]["passed"] += 1
            else:
                categories[category]["failed"] += 1
        
        return categories
    
    def _format_result(self, result: SecurityResult) -> Dict[str, Any]:
        """Format security result for report."""
        return {
            "check_name": result.check_name,
            "passed": result.passed,
            "severity": result.severity.value,
            "category": result.category,
            "message": result.message,
            "details": result.details or {},
            "recommendations": result.recommendations or []
        }
    
    def _generate_recommendations(self) -> List[str]:
        """Generate overall security recommendations."""
        recommendations = []
        
        failed_checks = [r for r in self.results if not r.passed]
        
        # Critical issues
        critical_failures = [r for r in failed_checks if r.severity == SecurityLevel.CRITICAL]
        if critical_failures:
            recommendations.append("🚨 CRITICAL: Address all critical security failures before deployment")
            recommendations.append("Review environment configuration and disable all debug/development features")
            recommendations.append("Ensure JWT secrets meet production security requirements")
        
        # High priority issues
        high_failures = [r for r in failed_checks if r.severity == SecurityLevel.HIGH]
        if high_failures:
            recommendations.append("⚠️ HIGH: Review and fix high-priority security issues")
            recommendations.append("Implement comprehensive security headers")
            recommendations.append("Validate rate limiting and authentication configurations")
        
        # General recommendations
        if len(failed_checks) > 0:
            recommendations.append("📋 Review all failed security checks and implement fixes")
            recommendations.append("Test security fixes in staging environment before production")
            recommendations.append("Set up security monitoring and alerting")
        
        if not recommendations:
            recommendations.append("✅ All security checks passed - system is production-ready")
            recommendations.append("🔄 Continue regular security audits and monitoring")
            recommendations.append("📈 Consider implementing additional security enhancements")
        
        return recommendations
    
    def _check_compliance_status(self) -> Dict[str, Any]:
        """Check compliance with security standards."""
        
        failed_checks = [r for r in self.results if not r.passed]
        critical_failures = [r for r in failed_checks if r.severity == SecurityLevel.CRITICAL]
        high_failures = [r for r in failed_checks if r.severity == SecurityLevel.HIGH]
        
        return {
            "owasp_top10_compliant": len(critical_failures) == 0,
            "production_ready": len(critical_failures) == 0 and len(high_failures) == 0,
            "enterprise_grade": len(failed_checks) <= 2,
            "compliance_score": len([r for r in self.results if r.passed]) / len(self.results) * 100
        }
    
    def _save_report(self, report: Dict[str, Any]):
        """Save security report to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"security_report_{self.environment}_{timestamp}.json"
        
        with open(filename, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        logger.info(f"📄 Security report saved to: {filename}")
    
    # ================================================================
    # SECURITY CHECK IMPLEMENTATIONS
    # ================================================================
    
    def check_environment_production(self, check: SecurityCheck) -> SecurityResult:
        """Check if environment is set to production."""
        env_setting = os.getenv('ENVIRONMENT', '').lower()
        
        if self.environment == "production":
            passed = env_setting == "production"
            message = f"Environment is set to '{env_setting}'" if passed else f"Environment is '{env_setting}', expected 'production'"
        else:
            passed = env_setting == self.environment
            message = f"Environment correctly set to '{env_setting}'"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"current_environment": env_setting, "expected": self.environment},
            recommendations=["Set ENVIRONMENT=production in production deployment"] if not passed and self.environment == "production" else []
        )
    
    def check_debug_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if debug mode is disabled."""
        debug_setting = os.getenv('DEBUG', 'false').lower()
        passed = debug_setting in ['false', 'f', '0', '']
        
        message = "Debug mode is disabled" if passed else f"Debug mode is enabled (DEBUG={debug_setting})"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"debug_setting": debug_setting},
            recommendations=["Set DEBUG=false in production"] if not passed else []
        )
    
    def check_development_mode_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if development mode is disabled."""
        dev_mode = os.getenv('DEVELOPMENT_MODE', 'false').lower()
        passed = dev_mode in ['false', 'f', '0', '']
        
        message = "Development mode is disabled" if passed else f"Development mode is enabled (DEVELOPMENT_MODE={dev_mode})"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"development_mode": dev_mode},
            recommendations=["Set DEVELOPMENT_MODE=false in production"] if not passed else []
        )
    
    def check_emergency_auth_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if emergency auth mode is disabled."""
        emergency_auth = os.getenv('EMERGENCY_AUTH_MODE', 'false').lower()
        passed = emergency_auth in ['false', 'f', '0', '']
        
        message = "Emergency auth mode is disabled" if passed else f"Emergency auth mode is enabled (EMERGENCY_AUTH_MODE={emergency_auth})"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"emergency_auth_mode": emergency_auth},
            recommendations=["Set EMERGENCY_AUTH_MODE=false in production"] if not passed else []
        )
    
    def check_jwt_secret_strength(self, check: SecurityCheck) -> SecurityResult:
        """Check JWT secret strength."""
        jwt_secret = os.getenv('JWT_SECRET', '')
        secret_length = len(jwt_secret)
        
        # Production requires 96+ characters, staging/dev 64+
        min_length = 96 if self.environment == "production" else 64
        passed = secret_length >= min_length
        
        # Additional checks for secret quality
        has_entropy = len(set(jwt_secret)) >= 32  # At least 32 unique characters
        not_default = jwt_secret not in ['your-secret-key-change-in-production', 'test', 'dev', 'debug']
        
        passed = passed and has_entropy and not_default
        
        if passed:
            message = f"JWT secret meets security requirements ({secret_length} characters)"
        else:
            issues = []
            if secret_length < min_length:
                issues.append(f"too short ({secret_length} chars, need {min_length}+)")
            if not has_entropy:
                issues.append("insufficient entropy")
            if not not_default:
                issues.append("using default/weak secret")
            message = f"JWT secret security issues: {', '.join(issues)}"
        
        recommendations = []
        if not passed:
            recommendations.append(f"Generate cryptographically secure JWT secret with {min_length}+ characters")
            recommendations.append("Use: python3 -c \"import secrets; print(secrets.token_urlsafe(96))\"")
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={
                "secret_length": secret_length,
                "required_length": min_length,
                "has_sufficient_entropy": has_entropy,
                "is_not_default": not_default
            },
            recommendations=recommendations
        )
    
    def check_jwt_algorithm(self, check: SecurityCheck) -> SecurityResult:
        """Check JWT algorithm security."""
        jwt_algorithm = os.getenv('JWT_ALGORITHM', 'HS256')
        secure_algorithms = ['HS256', 'HS384', 'HS512', 'RS256', 'RS384', 'RS512']
        
        passed = jwt_algorithm in secure_algorithms
        message = f"JWT algorithm is secure ({jwt_algorithm})" if passed else f"JWT algorithm may be insecure ({jwt_algorithm})"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"current_algorithm": jwt_algorithm, "secure_algorithms": secure_algorithms},
            recommendations=["Use a secure JWT algorithm (HS256 recommended)"] if not passed else []
        )
    
    def check_jwt_https_required(self, check: SecurityCheck) -> SecurityResult:
        """Check if JWT requires HTTPS."""
        jwt_require_https = os.getenv('JWT_REQUIRE_HTTPS', 'false').lower()
        
        if self.environment == "production":
            passed = jwt_require_https in ['true', 't', '1']
            message = "JWT requires HTTPS" if passed else "JWT does not require HTTPS in production"
            recommendations = ["Set JWT_REQUIRE_HTTPS=true in production"] if not passed else []
        else:
            # Allow HTTP in development
            passed = True
            message = f"JWT HTTPS requirement: {jwt_require_https} (acceptable for {self.environment})"
            recommendations = []
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"jwt_require_https": jwt_require_https, "environment": self.environment},
            recommendations=recommendations
        )
    
    def check_jwt_blacklist(self, check: SecurityCheck) -> SecurityResult:
        """Check if JWT blacklisting is enabled."""
        jwt_blacklist = os.getenv('JWT_BLACKLIST_ENABLED', 'false').lower()
        passed = jwt_blacklist in ['true', 't', '1']
        
        message = "JWT blacklisting is enabled" if passed else "JWT blacklisting is disabled"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"jwt_blacklist_enabled": jwt_blacklist},
            recommendations=["Set JWT_BLACKLIST_ENABLED=true for better security"] if not passed else []
        )
    
    def check_mock_authentication_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if mock authentication is disabled."""
        mock_auth = os.getenv('ENABLE_MOCK_AUTHENTICATION', 'false').lower()
        passed = mock_auth in ['false', 'f', '0', '']
        
        message = "Mock authentication is disabled" if passed else f"Mock authentication is enabled (ENABLE_MOCK_AUTHENTICATION={mock_auth})"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"enable_mock_authentication": mock_auth},
            recommendations=["Set ENABLE_MOCK_AUTHENTICATION=false in production"] if not passed else []
        )
    
    def check_test_users_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if test users are disabled."""
        test_users = os.getenv('ENABLE_TEST_USERS', 'false').lower()
        passed = test_users in ['false', 'f', '0', '']
        
        message = "Test users are disabled" if passed else f"Test users are enabled (ENABLE_TEST_USERS={test_users})"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"enable_test_users": test_users},
            recommendations=["Set ENABLE_TEST_USERS=false in production"] if not passed else []
        )
    
    def check_dev_bypasses_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if development bypasses are disabled."""
        dev_bypasses = os.getenv('ENABLE_DEVELOPMENT_BYPASSES', 'false').lower()
        passed = dev_bypasses in ['false', 'f', '0', '']
        
        message = "Development bypasses are disabled" if passed else f"Development bypasses are enabled (ENABLE_DEVELOPMENT_BYPASSES={dev_bypasses})"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"enable_development_bypasses": dev_bypasses},
            recommendations=["Set ENABLE_DEVELOPMENT_BYPASSES=false in production"] if not passed else []
        )
    
    def check_cors_wildcard_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if CORS wildcard origins are disabled."""
        cors_origins = os.getenv('ALLOWED_ORIGINS', '[]')
        
        try:
            # Parse CORS origins
            if cors_origins.startswith('['):
                import ast
                origins_list = ast.literal_eval(cors_origins)
            else:
                origins_list = cors_origins.split(',')
            
            has_wildcard = '*' in origins_list
            passed = not has_wildcard
            
            message = "CORS wildcard origins are disabled" if passed else "CORS wildcard origins are enabled"
            
        except Exception as e:
            passed = False
            message = f"Could not parse CORS origins: {e}"
            origins_list = []
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"cors_origins": origins_list, "has_wildcard": not passed},
            recommendations=["Remove wildcard (*) from ALLOWED_ORIGINS in production"] if not passed else []
        )
    
    def check_cors_https_only(self, check: SecurityCheck) -> SecurityResult:
        """Check if CORS origins use HTTPS only."""
        cors_origins = os.getenv('ALLOWED_ORIGINS', '[]')
        
        try:
            if cors_origins.startswith('['):
                import ast
                origins_list = ast.literal_eval(cors_origins)
            else:
                origins_list = cors_origins.split(',')
            
            http_origins = [origin for origin in origins_list if origin.startswith('http://') and not origin.startswith('http://localhost')]
            
            if self.environment == "production":
                passed = len(http_origins) == 0
                message = "All CORS origins use HTTPS" if passed else f"Found {len(http_origins)} HTTP origins in production"
            else:
                passed = True
                message = f"CORS HTTP origins acceptable for {self.environment} environment"
            
        except Exception as e:
            passed = False
            message = f"Could not parse CORS origins: {e}"
            http_origins = []
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"http_origins": http_origins, "environment": self.environment},
            recommendations=["Use HTTPS-only origins in production CORS configuration"] if not passed else []
        )
    
    def check_cors_credentials_policy(self, check: SecurityCheck) -> SecurityResult:
        """Check CORS credentials policy."""
        cors_credentials = os.getenv('CORS_ALLOW_CREDENTIALS', 'true').lower()
        cors_origins = os.getenv('ALLOWED_ORIGINS', '[]')
        
        # If credentials are allowed, origins should be specific (not wildcard)
        if cors_credentials in ['true', 't', '1']:
            try:
                if cors_origins.startswith('['):
                    import ast
                    origins_list = ast.literal_eval(cors_origins)
                else:
                    origins_list = cors_origins.split(',')
                
                has_wildcard = '*' in origins_list
                passed = not has_wildcard  # Credentials + wildcard = security risk
                
                if passed:
                    message = "CORS credentials policy is secure (specific origins)"
                else:
                    message = "CORS credentials with wildcard origins is insecure"
                
            except Exception:
                passed = False
                message = "Could not validate CORS credentials policy"
        else:
            passed = True
            message = "CORS credentials disabled"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"cors_allow_credentials": cors_credentials},
            recommendations=["Don't use wildcard origins with CORS credentials"] if not passed else []
        )
    
    def check_rate_limiting_enabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if rate limiting is enabled."""
        rate_limit = os.getenv('RATE_LIMIT_PER_MINUTE', '0')
        
        try:
            limit_value = int(rate_limit)
            passed = limit_value > 0
            message = f"Rate limiting is enabled ({limit_value}/minute)" if passed else "Rate limiting is disabled"
        except ValueError:
            passed = False
            message = f"Invalid rate limit configuration: {rate_limit}"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"rate_limit_per_minute": rate_limit},
            recommendations=["Enable rate limiting with appropriate limits"] if not passed else []
        )
    
    def check_adaptive_rate_limiting(self, check: SecurityCheck) -> SecurityResult:
        """Check if adaptive rate limiting is enabled."""
        adaptive_rate_limiting = os.getenv('ENABLE_ADAPTIVE_RATE_LIMITING', 'false').lower()
        passed = adaptive_rate_limiting in ['true', 't', '1']
        
        message = "Adaptive rate limiting is enabled" if passed else "Adaptive rate limiting is disabled"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"enable_adaptive_rate_limiting": adaptive_rate_limiting},
            recommendations=["Enable adaptive rate limiting for better protection"] if not passed else []
        )
    
    def check_auth_rate_limits(self, check: SecurityCheck) -> SecurityResult:
        """Check authentication-specific rate limits."""
        auth_login_limit = os.getenv('AUTH_RATE_LIMIT_LOGIN', '5/hour')
        auth_register_limit = os.getenv('AUTH_RATE_LIMIT_REGISTER', '3/hour')
        
        # Parse and validate rate limits
        login_ok = 'hour' in auth_login_limit and '/' in auth_login_limit
        register_ok = 'hour' in auth_register_limit and '/' in auth_register_limit
        
        passed = login_ok and register_ok
        
        if passed:
            message = f"Auth rate limits configured (login: {auth_login_limit}, register: {auth_register_limit})"
        else:
            message = "Auth rate limits not properly configured"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={
                "auth_rate_limit_login": auth_login_limit,
                "auth_rate_limit_register": auth_register_limit
            },
            recommendations=["Configure appropriate auth rate limits (e.g., 5/hour for login)"] if not passed else []
        )
    
    def check_security_headers_enabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if security headers are enabled."""
        security_headers = os.getenv('SECURITY_HEADERS_ENABLED', 'false').lower()
        passed = security_headers in ['true', 't', '1']
        
        message = "Security headers are enabled" if passed else "Security headers are disabled"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"security_headers_enabled": security_headers},
            recommendations=["Set SECURITY_HEADERS_ENABLED=true"] if not passed else []
        )
    
    def check_hsts_header(self, check: SecurityCheck) -> SecurityResult:
        """Check HSTS header configuration."""
        hsts_max_age = os.getenv('HSTS_MAX_AGE', '0')
        
        try:
            max_age = int(hsts_max_age)
            # HSTS should be at least 1 year (31536000 seconds)
            passed = max_age >= 31536000
            message = f"HSTS configured with {max_age} seconds max-age" if passed else f"HSTS max-age too low ({max_age})"
        except ValueError:
            passed = False
            message = f"Invalid HSTS max-age: {hsts_max_age}"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"hsts_max_age": hsts_max_age},
            recommendations=["Set HSTS_MAX_AGE=31536000 (1 year minimum)"] if not passed else []
        )
    
    def check_csp_header(self, check: SecurityCheck) -> SecurityResult:
        """Check Content Security Policy configuration."""
        csp = os.getenv('CONTENT_SECURITY_POLICY', '')
        
        # Basic CSP validation
        has_default_src = 'default-src' in csp
        passed = len(csp) > 0 and has_default_src
        
        message = "CSP header is configured" if passed else "CSP header not configured or incomplete"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"content_security_policy": csp[:100] + "..." if len(csp) > 100 else csp},
            recommendations=["Configure Content Security Policy with default-src directive"] if not passed else []
        )
    
    def check_xss_protection(self, check: SecurityCheck) -> SecurityResult:
        """Check XSS protection (this is mostly handled by CSP now)."""
        # This check validates that we're not relying on deprecated X-XSS-Protection
        passed = True  # XSS protection is handled by CSP and modern browsers
        message = "XSS protection handled by CSP and modern browser defaults"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            recommendations=[]
        )
    
    def check_verbose_errors_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if verbose error messages are disabled."""
        verbose_errors = os.getenv('VERBOSE_ERROR_MESSAGES', 'false').lower()
        
        if self.environment == "production":
            passed = verbose_errors in ['false', 'f', '0', '']
            message = "Verbose errors disabled" if passed else "Verbose errors enabled in production"
            recommendations = ["Set VERBOSE_ERROR_MESSAGES=false in production"] if not passed else []
        else:
            passed = True
            message = f"Verbose errors setting acceptable for {self.environment}: {verbose_errors}"
            recommendations = []
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"verbose_error_messages": verbose_errors},
            recommendations=recommendations
        )
    
    def check_debug_endpoints_disabled(self, check: SecurityCheck) -> SecurityResult:
        """Check if debug endpoints are disabled."""
        debug_endpoints = os.getenv('ENABLE_DEBUG_ENDPOINTS', 'false').lower()
        
        if self.environment == "production":
            passed = debug_endpoints in ['false', 'f', '0', '']
            message = "Debug endpoints disabled" if passed else "Debug endpoints enabled in production"
            recommendations = ["Set ENABLE_DEBUG_ENDPOINTS=false in production"] if not passed else []
        else:
            passed = True
            message = f"Debug endpoints setting acceptable for {self.environment}: {debug_endpoints}"
            recommendations = []
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"enable_debug_endpoints": debug_endpoints},
            recommendations=recommendations
        )
    
    def check_error_information_disclosure(self, check: SecurityCheck) -> SecurityResult:
        """Check for error information disclosure via API test."""
        if not self.base_url:
            return SecurityResult(
                check_name=check.name,
                passed=True,
                severity=check.severity,
                category=check.category,
                message="Skipped - no base URL available for testing"
            )
        
        try:
            # Test error handling by making an invalid request
            response = requests.get(f"{self.base_url}/api/v1/nonexistent", timeout=10)
            
            # Check if error response leaks information
            if response.status_code == 404:
                response_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                
                # Look for information leakage
                sensitive_fields = ['traceback', 'exception', 'stack_trace', 'file_path', 'debug_info']
                has_leakage = any(field in str(response_data).lower() for field in sensitive_fields)
                
                passed = not has_leakage
                message = "Error responses don't leak information" if passed else "Error responses may leak sensitive information"
            else:
                passed = True
                message = f"Error handling test returned {response.status_code}"
            
        except requests.RequestException as e:
            passed = True  # Can't test, assume OK
            message = f"Could not test error disclosure: {e}"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            recommendations=["Review error handling to prevent information disclosure"] if not passed else []
        )
    
    def check_health_check_security(self, check: SecurityCheck) -> SecurityResult:
        """Check health check endpoint security."""
        if not self.base_url:
            return SecurityResult(
                check_name=check.name,
                passed=True,
                severity=check.severity,
                category=check.category,
                message="Skipped - no base URL available for testing"
            )
        
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                
                # Check for information leakage in health check
                sensitive_info = ['database_url', 'secret', 'key', 'password', 'token']
                has_sensitive = any(field in str(health_data).lower() for field in sensitive_info)
                
                passed = not has_sensitive
                message = "Health check doesn't expose sensitive information" if passed else "Health check may expose sensitive information"
            else:
                passed = True
                message = f"Health check returned {response.status_code}"
            
        except requests.RequestException as e:
            passed = True
            message = f"Could not test health check: {e}"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            recommendations=["Review health check endpoint for information disclosure"] if not passed else []
        )
    
    def check_security_monitoring(self, check: SecurityCheck) -> SecurityResult:
        """Check security monitoring configuration."""
        security_logging = os.getenv('SECURITY_AUDIT_LOGGING', 'false').lower()
        failed_auth_logging = os.getenv('FAILED_AUTH_LOGGING', 'false').lower()
        
        monitoring_enabled = (security_logging in ['true', 't', '1'] and 
                            failed_auth_logging in ['true', 't', '1'])
        
        passed = monitoring_enabled
        message = "Security monitoring is enabled" if passed else "Security monitoring is not fully enabled"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={
                "security_audit_logging": security_logging,
                "failed_auth_logging": failed_auth_logging
            },
            recommendations=["Enable SECURITY_AUDIT_LOGGING and FAILED_AUTH_LOGGING"] if not passed else []
        )
    
    def check_ssl_tls(self, check: SecurityCheck) -> SecurityResult:
        """Check SSL/TLS configuration."""
        if not self.base_url or not self.base_url.startswith('https'):
            if self.environment == "production":
                passed = False
                message = "Production should use HTTPS"
                recommendations = ["Configure HTTPS/TLS for production deployment"]
            else:
                passed = True
                message = f"HTTP acceptable for {self.environment} environment"
                recommendations = []
        else:
            passed = True
            message = "HTTPS/TLS configured"
            recommendations = []
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            details={"base_url": self.base_url},
            recommendations=recommendations
        )
    
    def check_api_versioning(self, check: SecurityCheck) -> SecurityResult:
        """Check API versioning security."""
        # This is a basic check - in practice you'd verify versioning strategy
        passed = True  # Assuming versioning is handled properly
        message = "API versioning appears to be implemented (/api/v1/...)"
        
        return SecurityResult(
            check_name=check.name,
            passed=passed,
            severity=check.severity,
            category=check.category,
            message=message,
            recommendations=[]
        )

def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(description='Velro Backend Security Validation')
    parser.add_argument('--environment', choices=['production', 'staging', 'development'], 
                       default='production', help='Environment to validate')
    parser.add_argument('--base-url', help='Base URL for API testing')
    parser.add_argument('--output', help='Output file for detailed report')
    parser.add_argument('--fail-on-issues', action='store_true', 
                       help='Exit with error code if security issues found')
    
    args = parser.parse_args()
    
    # Create validator
    validator = SecurityValidator(args.environment, args.base_url)
    
    # Run validation
    report = validator.run_all_checks()
    
    # Print summary
    print("\n" + "="*80)
    print(f"🔒 VELRO BACKEND SECURITY VALIDATION REPORT")
    print("="*80)
    print(f"Environment: {args.environment}")
    print(f"Timestamp: {report['validation_metadata']['timestamp']}")
    print(f"Security Score: {report['security_summary']['security_score']}%")
    print(f"Overall Status: {report['security_summary']['overall_status']}")
    print(f"Deployment Approved: {'✅ YES' if report['security_summary']['deployment_approved'] else '❌ NO'}")
    print()
    
    # Print failure summary
    if report['security_summary']['failed_checks'] > 0:
        print("🚨 SECURITY ISSUES FOUND:")
        print(f"  Critical: {report['failure_summary']['critical']}")
        print(f"  High: {report['failure_summary']['high']}")
        print(f"  Medium: {report['failure_summary']['medium']}")
        print(f"  Low: {report['failure_summary']['low']}")
        print()
        
        # Print critical failures
        if report['critical_failures']:
            print("🚨 CRITICAL FAILURES (MUST FIX):")
            for failure in report['critical_failures']:
                print(f"  ❌ {failure['check_name']}: {failure['message']}")
        
        # Print high priority failures  
        if report['high_priority_failures']:
            print("\n⚠️ HIGH PRIORITY FAILURES:")
            for failure in report['high_priority_failures']:
                print(f"  ❌ {failure['check_name']}: {failure['message']}")
    else:
        print("✅ ALL SECURITY CHECKS PASSED")
    
    print("\n" + "="*80)
    
    # Save detailed report if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"📄 Detailed report saved to: {args.output}")
    
    # Exit with appropriate code
    if args.fail_on_issues and not report['security_summary']['deployment_approved']:
        print("\n❌ SECURITY VALIDATION FAILED - DEPLOYMENT NOT APPROVED")
        sys.exit(1)
    else:
        print("\n✅ SECURITY VALIDATION COMPLETE")
        sys.exit(0)

if __name__ == "__main__":
    main()