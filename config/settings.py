"""
Centralized configuration management for Velro Backend.
Loads environment variables with safe defaults and validation.
"""
import os
import json
import logging
from typing import List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class Settings:
    """Configuration settings loaded from environment variables."""
    
    def __init__(self):
        # Service identification
        self.SERVICE_NAME = os.getenv("SERVICE_NAME", "velro-backend")
        self.SERVICE_VERSION = os.getenv("SERVICE_VERSION", "1.1.4")
        self.ENVIRONMENT = os.getenv("RAILWAY_ENVIRONMENT", os.getenv("ENVIRONMENT", "development"))
        self.IS_PRODUCTION = self.ENVIRONMENT == "production"
        
        # Railway-specific
        self.RAILWAY_DEPLOYMENT_ID = os.getenv("RAILWAY_DEPLOYMENT_ID")
        self.RAILWAY_SERVICE_ID = os.getenv("RAILWAY_SERVICE_ID")
        self.RAILWAY_PROJECT_ID = os.getenv("RAILWAY_PROJECT_ID")
        self.PORT = int(os.getenv("PORT", "8000"))
        
        # Emergency bypass flags
        self.BYPASS_MIDDLEWARE = self._parse_bool(os.getenv("BYPASS_MIDDLEWARE", "false"))
        self.BYPASS_ALL_MIDDLEWARE = self._parse_bool(os.getenv("BYPASS_ALL_MIDDLEWARE", "false"))
        self.DISABLE_HEAVY_MIDDLEWARE = self._parse_bool(os.getenv("DISABLE_HEAVY_MIDDLEWARE", "false"))
        
        # CORS configuration
        self.CORS_ORIGINS = self._parse_cors_origins()
        self.ALLOW_CREDENTIALS = self._parse_bool(os.getenv("ALLOW_CREDENTIALS", "true"))
        self.CORS_MAX_AGE = int(os.getenv("CORS_MAX_AGE", "86400"))
        
        # Middleware toggles
        self.ENABLE_TRUSTED_HOSTS = self._parse_bool(
            os.getenv("ENABLE_TRUSTED_HOSTS", "true" if self.IS_PRODUCTION else "false")
        )
        self.ENABLE_AUTH = self._parse_bool(os.getenv("ENABLE_AUTH", "true"))
        self.ENABLE_ACL = self._parse_bool(os.getenv("ENABLE_ACL", "true"))
        self.ENABLE_CSRF = self._parse_bool(os.getenv("ENABLE_CSRF", "false"))  # Off for token-only APIs
        self.ENABLE_SSRF_PROTECT = self._parse_bool(os.getenv("ENABLE_SSRF_PROTECT", "true"))
        self.ENABLE_RATE_LIMIT = self._parse_bool(os.getenv("ENABLE_RATE_LIMIT", "true"))
        self.ENABLE_GZIP = self._parse_bool(os.getenv("ENABLE_GZIP", "true"))
        
        # Trusted hosts
        self.ALLOWED_HOSTS = self._parse_allowed_hosts()
        
        # FastLane paths (bypass heavy middleware)
        self.FASTLANE_PATHS = self._parse_csv(
            os.getenv("FASTLANE_PATHS", "/api/v1/auth/*,/health,/__version,/__health,/__diag/*")
        )
        
        # Database configuration
        self.SUPABASE_URL = os.getenv("SUPABASE_URL", "")
        self.SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")
        self.SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.DATABASE_URL = os.getenv("DATABASE_URL", "")
        
        # Redis configuration
        self.REDIS_URL = os.getenv("REDIS_URL", "")
        self.REDIS_ENABLED = bool(self.REDIS_URL)
        
        # JWT configuration
        self.JWT_SECRET = os.getenv("JWT_SECRET", "")
        self.JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
        self.JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "60"))
        
        # FAL.ai configuration
        self.FAL_KEY = os.getenv("FAL_KEY", "")
        self.fal_key = self.FAL_KEY  # Compatibility alias
        
        # Logging
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.LOG_FORMAT = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        self.debug = self.LOG_LEVEL == "DEBUG"  # Compatibility attribute
        
        # Performance
        self.REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
        self.CONNECTION_POOL_SIZE = int(os.getenv("CONNECTION_POOL_SIZE", "20"))
        
        # Rate limiting defaults
        self.RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "100/minute")
        self.RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "30/minute")
        self.RATE_LIMIT_GENERATION = os.getenv("RATE_LIMIT_GENERATION", "10/minute")
        
        # Compatibility attributes for existing code
        self.supabase_url = self.SUPABASE_URL
        self.supabase_anon_key = self.SUPABASE_ANON_KEY
        self.supabase_service_role_key = self.SUPABASE_SERVICE_ROLE_KEY
        self.database_url = self.DATABASE_URL
        self.redis_url = self.REDIS_URL
        self.jwt_secret = self.JWT_SECRET
        self.jwt_algorithm = self.JWT_ALGORITHM
        self.environment = self.ENVIRONMENT
        
        # Validate critical settings
        self._validate_critical_settings()
    
    def _parse_bool(self, value: str) -> bool:
        """Parse boolean from environment variable."""
        return value.lower() in ("true", "1", "yes", "on")
    
    def _parse_csv(self, value: str) -> List[str]:
        """Parse comma-separated values."""
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]
    
    def _parse_cors_origins(self) -> List[str]:
        """Parse CORS origins from JSON array or CSV."""
        cors_env = os.getenv("CORS_ORIGINS", "")
        
        # Default production origins
        prod_origins = [
            "https://velro-frontend-production.up.railway.app",
            "https://velro-003-frontend-production.up.railway.app",
            "https://velro.ai",
            "https://www.velro.ai",
            "http://localhost:3000",  # Development
            "http://localhost:3001",  # Development alt
        ]
        
        if not cors_env:
            if self.IS_PRODUCTION:
                return prod_origins
            else:
                return ["*"]  # Allow all in development
        
        # Try parsing as JSON array
        try:
            origins = json.loads(cors_env)
            if isinstance(origins, list):
                return origins
        except json.JSONDecodeError:
            pass
        
        # Try parsing as CSV
        if "," in cors_env:
            return self._parse_csv(cors_env)
        
        # Single origin
        return [cors_env]
    
    def _parse_allowed_hosts(self) -> List[str]:
        """Parse allowed hosts for TrustedHostMiddleware."""
        hosts_env = os.getenv("ALLOWED_HOSTS", "")
        
        # Default hosts
        default_hosts = [
            "localhost",
            "127.0.0.1",
            "0.0.0.0",
            "velro-backend-production.up.railway.app",
            "velro-003-backend-production.up.railway.app",
            "*.railway.app",
            "*.railway.internal",
            "api.velro.ai",
            "velro.ai",
        ]
        
        if not hosts_env:
            return default_hosts if self.IS_PRODUCTION else ["*"]
        
        return self._parse_csv(hosts_env)
    
    def _validate_critical_settings(self):
        """Validate critical settings and warn about issues."""
        warnings = []
        
        if self.IS_PRODUCTION:
            if not self.JWT_SECRET:
                warnings.append("JWT_SECRET not set - authentication will fail")
            if not self.SUPABASE_URL:
                warnings.append("SUPABASE_URL not set - database operations will fail")
            if not self.SUPABASE_ANON_KEY:
                warnings.append("SUPABASE_ANON_KEY not set - database operations will fail")
            if not self.FAL_KEY:
                warnings.append("FAL_KEY not set - generation services will fail")
        
        if self.BYPASS_MIDDLEWARE or self.BYPASS_ALL_MIDDLEWARE:
            warnings.append("⚠️ MIDDLEWARE BYPASS ACTIVE - Emergency mode enabled!")
        
        for warning in warnings:
            logger.warning(f"CONFIG WARNING: {warning}")
    
    def get_middleware_status(self) -> dict:
        """Get current middleware configuration status."""
        return {
            "bypass_mode": self.BYPASS_MIDDLEWARE or self.BYPASS_ALL_MIDDLEWARE,
            "cors": True,  # Always enabled
            "trusted_hosts": self.ENABLE_TRUSTED_HOSTS,
            "auth": self.ENABLE_AUTH,
            "access_control": self.ENABLE_ACL,
            "csrf": self.ENABLE_CSRF,
            "ssrf_protection": self.ENABLE_SSRF_PROTECT,
            "rate_limiting": self.ENABLE_RATE_LIMIT,
            "gzip": self.ENABLE_GZIP,
            "fastlane_paths": self.FASTLANE_PATHS,
            "redis_available": self.REDIS_ENABLED,
        }
    
    def is_production(self) -> bool:
        """Check if running in production (compatibility method)."""
        return self.IS_PRODUCTION
    
    def validate_production_security(self) -> bool:
        """Validate production security settings (compatibility method)."""
        if not self.IS_PRODUCTION:
            return True
        
        errors = []
        if not self.JWT_SECRET:
            errors.append("JWT_SECRET not configured")
        if not self.SUPABASE_URL:
            errors.append("SUPABASE_URL not configured")
        if not self.SUPABASE_ANON_KEY:
            errors.append("SUPABASE_ANON_KEY not configured")
        
        if errors:
            for error in errors:
                logger.error(f"Security validation error: {error}")
            return False
        return True
    
    def get_safe_config(self) -> dict:
        """Get configuration safe for logging (no secrets)."""
        return {
            "service": self.SERVICE_NAME,
            "version": self.SERVICE_VERSION,
            "environment": self.ENVIRONMENT,
            "is_production": self.IS_PRODUCTION,
            "port": self.PORT,
            "middleware_status": self.get_middleware_status(),
            "cors_origins": self.CORS_ORIGINS,
            "allowed_hosts": self.ALLOWED_HOSTS,
            "log_level": self.LOG_LEVEL,
            "railway_deployment": self.RAILWAY_DEPLOYMENT_ID,
        }


# Singleton instance
settings = Settings()

# Configure logging based on settings
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format=settings.LOG_FORMAT
)