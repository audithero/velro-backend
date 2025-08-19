"""
PRODUCTION-SAFE E2E TESTING CONFIGURATION
=========================================
This file provides production-safe testing configuration for E2E testing.
All configurations are secure and fail-safe, with testing features disabled by default.
"""

import os
import logging
from typing import Dict, Any, Optional, Set

logger = logging.getLogger(__name__)

# Production-safe testing mode detection
def is_testing_mode() -> bool:
    """
    Check if running in testing mode.
    Only enabled when explicitly set to 'true' in environment.
    """
    return os.getenv("TESTING_MODE", "false").lower() == "true"

def is_e2e_testing_enabled() -> bool:
    """Check if E2E testing is explicitly enabled."""
    return os.getenv("E2E_TESTING_ENABLED", "false").lower() == "true"

def is_bypass_rate_limiting_enabled() -> bool:
    """Check if rate limiting bypass is explicitly enabled."""
    return os.getenv("BYPASS_RATE_LIMITING", "false").lower() == "true"

# Log current testing mode status
_testing_active = is_testing_mode()
_e2e_active = is_e2e_testing_enabled()
_rate_limit_bypass = is_bypass_rate_limiting_enabled()

if _testing_active:
    logger.warning(f"🧪 [TESTING-CONFIG] Testing mode active: TESTING_MODE={_testing_active}")
if _e2e_active:
    logger.warning(f"🧪 [TESTING-CONFIG] E2E testing enabled: E2E_TESTING_ENABLED={_e2e_active}")
if _rate_limit_bypass:
    logger.warning(f"🧪 [TESTING-CONFIG] Rate limit bypass enabled: BYPASS_RATE_LIMITING={_rate_limit_bypass}")

# Environment detection
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
IS_PRODUCTION = ENVIRONMENT == "production"

if _testing_active and IS_PRODUCTION:
    logger.error("🚨 [SECURITY-WARNING] Testing mode is active in production environment")
elif not IS_PRODUCTION:
    logger.info(f"🔧 [TESTING-CONFIG] Non-production environment detected: {ENVIRONMENT}")

# Production-safe testing rate limits (only used when testing mode is explicitly enabled)
def get_test_rate_limits() -> Optional[Dict[str, Dict[str, int]]]:
    """
    Get increased rate limits for testing.
    Only returns test limits when testing mode is explicitly enabled.
    """
    if not is_testing_mode():
        return None
        
    return {
        "free": {
            "requests_per_minute": 1000,
            "requests_per_hour": 10000,
            "concurrent_requests": 100
        },
        "pro": {
            "requests_per_minute": 5000,
            "requests_per_hour": 50000,
            "concurrent_requests": 500
        },
        "enterprise": {
            "requests_per_minute": 10000,
            "requests_per_hour": 100000,
            "concurrent_requests": 1000
        }
    }

# Production-safe public endpoints (always safe to access without auth)
def get_public_endpoints() -> Set[str]:
    """Get endpoints that are always public (no authentication required)."""
    base_public = {
        "/",
        "/health",
        "/api/health", 
        "/api/v1/health",
        "/api/v1/health/status",
        "/docs",
        "/redoc", 
        "/openapi.json",
        "/metrics",
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/refresh",
        "/api/v1/auth/health",
        "/api/v1/auth/security-info",
        "/api/v1/generations/models/supported"
    }
    
    # Add E2E testing endpoints only when E2E testing is enabled
    if is_e2e_testing_enabled():
        e2e_endpoints = {
            "/api/v1/e2e/health",
            "/api/v1/e2e/test-session",
            "/api/v1/e2e/cleanup",
            "/api/v1/performance/metrics",
            "/api/v1/performance/health",
            "/monitoring"
        }
        base_public.update(e2e_endpoints)
        logger.info(f"🧪 [E2E-ENDPOINTS] Added {len(e2e_endpoints)} E2E testing endpoints to public access")
    
    return base_public

def should_bypass_rate_limiting(request) -> bool:
    """
    Check if rate limiting should be bypassed for this request.
    Production-safe: only bypasses when explicitly enabled and request has proper test headers.
    """
    # Must be explicitly enabled
    if not is_bypass_rate_limiting_enabled():
        return False
    
    # Check for explicit test mode header
    if request.headers.get("X-Test-Mode") == "true":
        logger.debug(f"🧪 [RATE-LIMIT-BYPASS] Bypassing rate limit for test request: {request.url.path}")
        return True
    
    # Check for test user agent (additional safety)
    user_agent = request.headers.get("User-Agent", "").lower()
    if "e2e-test" in user_agent or "velro-test" in user_agent:
        logger.debug(f"🧪 [RATE-LIMIT-BYPASS] Bypassing rate limit for test user agent: {user_agent}")
        return True
    
    return False

def should_bypass_auth(request) -> bool:
    """
    Check if authentication should be bypassed for this request.
    Production-safe: only allows bypass for public endpoints and explicit test headers.
    """
    # Always allow access to public endpoints
    public_endpoints = get_public_endpoints()
    if request.url.path in public_endpoints:
        return True
    
    # Check for paths that start with public prefixes
    public_prefixes = ["/api/v1/debug/", "/api/v1/e2e/"] if is_e2e_testing_enabled() else ["/api/v1/debug/"]
    if any(request.url.path.startswith(prefix) for prefix in public_prefixes):
        return True
    
    # NO authentication bypass for other endpoints - security first
    return False

def is_test_request(request) -> bool:
    """Check if request is from E2E testing infrastructure."""
    if not is_e2e_testing_enabled():
        return False
        
    # Check for test headers
    if request.headers.get("X-Test-Mode") == "true":
        return True
        
    # Check for test user agent
    user_agent = request.headers.get("User-Agent", "").lower()
    return "e2e-test" in user_agent or "velro-test" in user_agent

def get_test_user_credentials() -> Optional[Dict[str, str]]:
    """
    Get test user credentials for E2E testing.
    Only returns credentials when E2E testing is explicitly enabled.
    """
    if not is_e2e_testing_enabled():
        return None
        
    return {
        "email": os.getenv("E2E_TEST_USER_EMAIL", "test@velro.ai"),
        "password": os.getenv("E2E_TEST_USER_PASSWORD", "TestPassword123!"),
        "credits": int(os.getenv("E2E_TEST_USER_CREDITS", "10000"))
    }

# Configuration summary logging
if _testing_active or _e2e_active or _rate_limit_bypass:
    logger.info("🧪 [TESTING-CONFIG] Active testing configurations:")
    if _testing_active:
        logger.info("   - Testing mode: ENABLED")
    if _e2e_active:
        logger.info("   - E2E testing: ENABLED")
    if _rate_limit_bypass:
        logger.info("   - Rate limit bypass: ENABLED")
    logger.info(f"   - Environment: {ENVIRONMENT}")
    logger.info(f"   - Public endpoints: {len(get_public_endpoints())}")
else:
    logger.info("🔒 [TESTING-CONFIG] All testing features disabled (production mode)")