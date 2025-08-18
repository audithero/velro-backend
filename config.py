"""
Configuration management for the Velro backend.
Following CLAUDE.md: Centralized configuration with environment variables.
Updated for Railway deployment compatibility.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class SecurityError(Exception):
    """Security configuration error."""
    pass


class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Environment
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    app_env: Optional[str] = Field(default=None, validation_alias="APP_ENV")
    
    # Supabase configuration
    supabase_url: str = Field(..., validation_alias="SUPABASE_URL")
    supabase_anon_key: str = Field(..., validation_alias="SUPABASE_ANON_KEY")
    # Support both old JWT-based service_role_key and new sb_secret format
    supabase_service_role_key: Optional[str] = Field(None, validation_alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_secret_key: Optional[str] = Field(None, validation_alias="SUPABASE_SECRET_KEY")
    
    # Database configuration (Railway provides this)
    database_url: Optional[str] = Field(None, validation_alias="DATABASE_URL")
    
    # FAL.ai configuration
    fal_key: str = Field(..., validation_alias="FAL_KEY")
    
    # Application configuration
    app_name: str = Field(default="Velro", validation_alias="APP_NAME")
    app_version: str = Field(default="1.1.2", validation_alias="APP_VERSION")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    
    # CORS configuration
    cors_origins: list = Field(
        default=[
            "http://localhost:3000", 
            "http://localhost:3001", 
            "http://localhost:3002", 
            "https://velro-frontend-production.up.railway.app",
            "https://velro-003-frontend-production.up.railway.app",
            "https://velro-kong-gateway-production.up.railway.app"
        ], 
        validation_alias="ALLOWED_ORIGINS"
    )
    
    # Rate limiting
    rate_limit_per_minute: int = Field(default=60, validation_alias="RATE_LIMIT_PER_MINUTE")
    generation_rate_limit: Optional[int] = Field(default=None, validation_alias="GENERATION_RATE_LIMIT")
    
    # File upload configuration
    max_file_size: int = Field(default=10 * 1024 * 1024, validation_alias="MAX_FILE_SIZE")  # 10MB
    allowed_file_types: list = Field(
        default=["image/jpeg", "image/png", "image/webp", "image/gif"],
        validation_alias="ALLOWED_FILE_TYPES"
    )
    
    # Storage configuration
    storage_bucket: str = Field(default="velro-storage", validation_alias="STORAGE_BUCKET")
    
    # Redis configuration (optional, for rate limiting and caching)
    redis_url: Optional[str] = Field(default=None, validation_alias="REDIS_URL")
    redis_max_connections: int = Field(default=100, validation_alias="REDIS_MAX_CONNECTIONS")
    redis_timeout: int = Field(default=5, validation_alias="REDIS_TIMEOUT")
    
    # Database performance configuration
    db_connection_pool_size: int = Field(default=50, validation_alias="DB_CONNECTION_POOL_SIZE")
    db_max_overflow: int = Field(default=20, validation_alias="DB_MAX_OVERFLOW")
    db_pool_timeout: int = Field(default=30, validation_alias="DB_POOL_TIMEOUT")
    db_pool_recycle: int = Field(default=3600, validation_alias="DB_POOL_RECYCLE")  # 1 hour
    
    # PHASE 2: Enterprise Connection Pool Configuration (6 Specialized Pools)
    # Total target: 200+ connections across all pools
    
    # Auth Pool Configuration (10-50 connections)
    auth_pool_min_connections: int = Field(default=10, validation_alias="AUTH_POOL_MIN_CONNECTIONS")
    auth_pool_max_connections: int = Field(default=50, validation_alias="AUTH_POOL_MAX_CONNECTIONS")
    auth_pool_query_timeout: int = Field(default=30, validation_alias="AUTH_POOL_QUERY_TIMEOUT")
    auth_pool_connection_timeout: int = Field(default=15, validation_alias="AUTH_POOL_CONNECTION_TIMEOUT")
    
    # Read Pool Configuration (20-75 connections)
    read_pool_min_connections: int = Field(default=20, validation_alias="READ_POOL_MIN_CONNECTIONS")
    read_pool_max_connections: int = Field(default=75, validation_alias="READ_POOL_MAX_CONNECTIONS")
    read_pool_query_timeout: int = Field(default=60, validation_alias="READ_POOL_QUERY_TIMEOUT")
    read_pool_connection_timeout: int = Field(default=30, validation_alias="READ_POOL_CONNECTION_TIMEOUT")
    
    # Write Pool Configuration (5-25 connections)
    write_pool_min_connections: int = Field(default=5, validation_alias="WRITE_POOL_MIN_CONNECTIONS")
    write_pool_max_connections: int = Field(default=25, validation_alias="WRITE_POOL_MAX_CONNECTIONS")
    write_pool_query_timeout: int = Field(default=120, validation_alias="WRITE_POOL_QUERY_TIMEOUT")
    write_pool_connection_timeout: int = Field(default=45, validation_alias="WRITE_POOL_CONNECTION_TIMEOUT")
    
    # Analytics Pool Configuration (5-20 connections)
    analytics_pool_min_connections: int = Field(default=5, validation_alias="ANALYTICS_POOL_MIN_CONNECTIONS")
    analytics_pool_max_connections: int = Field(default=20, validation_alias="ANALYTICS_POOL_MAX_CONNECTIONS")
    analytics_pool_query_timeout: int = Field(default=300, validation_alias="ANALYTICS_POOL_QUERY_TIMEOUT")
    analytics_pool_connection_timeout: int = Field(default=60, validation_alias="ANALYTICS_POOL_CONNECTION_TIMEOUT")
    
    # Admin Pool Configuration (2-10 connections)
    admin_pool_min_connections: int = Field(default=2, validation_alias="ADMIN_POOL_MIN_CONNECTIONS")
    admin_pool_max_connections: int = Field(default=10, validation_alias="ADMIN_POOL_MAX_CONNECTIONS")
    admin_pool_query_timeout: int = Field(default=600, validation_alias="ADMIN_POOL_QUERY_TIMEOUT")
    admin_pool_connection_timeout: int = Field(default=120, validation_alias="ADMIN_POOL_CONNECTION_TIMEOUT")
    
    # Batch Pool Configuration (5-30 connections)
    batch_pool_min_connections: int = Field(default=5, validation_alias="BATCH_POOL_MIN_CONNECTIONS")
    batch_pool_max_connections: int = Field(default=30, validation_alias="BATCH_POOL_MAX_CONNECTIONS")
    batch_pool_query_timeout: int = Field(default=1800, validation_alias="BATCH_POOL_QUERY_TIMEOUT")
    batch_pool_connection_timeout: int = Field(default=90, validation_alias="BATCH_POOL_CONNECTION_TIMEOUT")
    
    # Pool Health Monitoring Configuration
    pool_health_check_interval: int = Field(default=30, validation_alias="POOL_HEALTH_CHECK_INTERVAL")
    pool_circuit_breaker_threshold: int = Field(default=5, validation_alias="POOL_CIRCUIT_BREAKER_THRESHOLD")
    pool_circuit_breaker_recovery_time: int = Field(default=60, validation_alias="POOL_CIRCUIT_BREAKER_RECOVERY_TIME")
    pool_slow_query_threshold_ms: float = Field(default=100.0, validation_alias="POOL_SLOW_QUERY_THRESHOLD_MS")
    
    # Pool Failover Configuration
    pool_failover_enabled: bool = Field(default=True, validation_alias="POOL_FAILOVER_ENABLED")
    pool_performance_monitoring_enabled: bool = Field(default=True, validation_alias="POOL_PERFORMANCE_MONITORING_ENABLED")
    pool_metrics_collection_interval: int = Field(default=60, validation_alias="POOL_METRICS_COLLECTION_INTERVAL")
    
    # Cache configuration for performance optimization
    cache_default_ttl: int = Field(default=300, validation_alias="CACHE_DEFAULT_TTL")  # 5 minutes
    cache_auth_ttl: int = Field(default=60, validation_alias="CACHE_AUTH_TTL")  # 1 minute for security
    cache_max_size: int = Field(default=10000, validation_alias="CACHE_MAX_SIZE")  # Max in-memory cache items
    
    # Enhanced multi-level cache configuration for PRD compliance
    cache_l1_size_mb: int = Field(default=200, validation_alias="CACHE_L1_SIZE_MB")  # L1 memory cache size
    cache_l2_enabled: bool = Field(default=True, validation_alias="CACHE_L2_ENABLED")  # Enable Redis L2 cache
    cache_l3_enabled: bool = Field(default=True, validation_alias="CACHE_L3_ENABLED")  # Enable database L3 cache
    cache_warming_enabled: bool = Field(default=True, validation_alias="CACHE_WARMING_ENABLED")  # Enable cache warming
    cache_invalidation_enabled: bool = Field(default=True, validation_alias="CACHE_INVALIDATION_ENABLED")  # Enable cache invalidation
    
    # Authorization cache TTL settings (optimized for security vs performance)
    cache_auth_generation_ttl: int = Field(default=180, validation_alias="CACHE_AUTH_GENERATION_TTL")  # 3 minutes
    cache_auth_user_permissions_ttl: int = Field(default=300, validation_alias="CACHE_AUTH_USER_PERMISSIONS_TTL")  # 5 minutes
    cache_auth_team_access_ttl: int = Field(default=600, validation_alias="CACHE_AUTH_TEAM_ACCESS_TTL")  # 10 minutes
    cache_auth_project_visibility_ttl: int = Field(default=900, validation_alias="CACHE_AUTH_PROJECT_VISIBILITY_TTL")  # 15 minutes
    
    # Performance targets for monitoring
    cache_target_hit_rate: float = Field(default=95.0, validation_alias="CACHE_TARGET_HIT_RATE")  # >95% hit rate
    cache_target_response_time_ms: float = Field(default=50.0, validation_alias="CACHE_TARGET_RESPONSE_TIME_MS")  # <50ms response
    
    # JWT Configuration - SECURITY HARDENED
    jwt_expiration_hours: int = Field(default=24, validation_alias="JWT_EXPIRATION_HOURS")
    jwt_secret: str = Field(..., validation_alias="JWT_SECRET")  # CRITICAL FIX: No default, must be provided
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_refresh_token_expire_hours: int = Field(default=168, validation_alias="JWT_REFRESH_EXPIRE_HOURS")  # 7 days
    jwt_blacklist_enabled: bool = Field(default=True, validation_alias="JWT_BLACKLIST_ENABLED")
    jwt_require_https: bool = Field(default=True, validation_alias="JWT_REQUIRE_HTTPS")
    password_hash_rounds: int = Field(default=12, validation_alias="PASSWORD_HASH_ROUNDS")
    
    # Advanced Security Configuration
    enable_mock_authentication: bool = Field(default=False, validation_alias="ENABLE_MOCK_AUTHENTICATION")
    enable_test_users: bool = Field(default=False, validation_alias="ENABLE_TEST_USERS")
    enable_development_bypasses: bool = Field(default=False, validation_alias="ENABLE_DEVELOPMENT_BYPASSES")
    security_validation_enabled: bool = Field(default=True, validation_alias="SECURITY_VALIDATION_ENABLED")
    production_security_checks: bool = Field(default=True, validation_alias="PRODUCTION_SECURITY_CHECKS")
    
    # Enhanced Rate Limiting
    auth_rate_limit_login: str = Field(default="5/hour", validation_alias="AUTH_RATE_LIMIT_LOGIN")
    auth_rate_limit_register: str = Field(default="3/hour", validation_alias="AUTH_RATE_LIMIT_REGISTER")
    enable_adaptive_rate_limiting: bool = Field(default=True, validation_alias="ENABLE_ADAPTIVE_RATE_LIMITING")
    
    # Security Headers
    security_headers_enabled: bool = Field(default=True, validation_alias="SECURITY_HEADERS_ENABLED")
    hsts_max_age: int = Field(default=31536000, validation_alias="HSTS_MAX_AGE")
    content_security_policy: str = Field(
        default="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'",
        validation_alias="CONTENT_SECURITY_POLICY"
    )
    
    # CSRF Protection
    csrf_protection_enabled: bool = Field(default=True, validation_alias="CSRF_PROTECTION_ENABLED")
    
    # Error Handling
    verbose_error_messages: bool = Field(default=False, validation_alias="VERBOSE_ERROR_MESSAGES")
    
    # Feature Controls
    enable_debug_endpoints: bool = Field(default=False, validation_alias="ENABLE_DEBUG_ENDPOINTS")
    health_check_detailed: bool = Field(default=False, validation_alias="HEALTH_CHECK_DETAILED")
    
    # Fastpath Configuration for Middleware Optimization
    fastpath_exempt_paths: list = Field(
        default=[
            "/health",
            "/api/v1/auth/ping", 
            "/api/v1/auth/login",
            "/api/v1/auth/register", 
            "/api/v1/auth/refresh",
            "/docs",
            "/openapi.json"
        ],
        validation_alias="FASTPATH_EXEMPT_PATHS"
    )
    
    # SECURITY: Validate JWT secret on initialization
    def __post_init__(self):
        """Validate security settings on initialization."""
        if self.jwt_secret == "your-secret-key-change-in-production":
            raise SecurityError("CRITICAL: Default JWT secret detected. Set JWT_SECRET environment variable.")
        
        if len(self.jwt_secret) < 32:
            raise SecurityError("CRITICAL: JWT_SECRET must be at least 32 characters for security.")
        
        # CRITICAL: Production-only security validation
        if self.is_production():
            self._validate_production_security_settings()
    
    # JWT Security Configuration
    jwt_refresh_token_expire_hours: int = Field(default=168, validation_alias="JWT_REFRESH_EXPIRE_HOURS")  # 7 days
    jwt_blacklist_enabled: bool = Field(default=True, validation_alias="JWT_BLACKLIST_ENABLED")
    jwt_require_https: bool = Field(default=True, validation_alias="JWT_REQUIRE_HTTPS")
    
    # SECURITY: Development mode configurations (NEVER enable in production)
    development_mode: bool = Field(default=False, validation_alias="DEVELOPMENT_MODE")
    emergency_auth_mode: bool = Field(default=False, validation_alias="EMERGENCY_AUTH_MODE")
    
    # Security configuration
    password_hash_rounds: int = Field(default=12, validation_alias="PASSWORD_HASH_ROUNDS")
    session_timeout_minutes: int = Field(default=30, validation_alias="SESSION_TIMEOUT_MINUTES")
    max_login_attempts: int = Field(default=5, validation_alias="MAX_LOGIN_ATTEMPTS")
    lockout_duration_minutes: int = Field(default=15, validation_alias="LOCKOUT_DURATION_MINUTES")
    
    # User configuration
    default_user_credits: int = Field(default=1000, validation_alias="DEFAULT_USER_CREDITS")
    
    # Railway configuration (optional)
    railway_static_url: Optional[str] = Field(default=None, validation_alias="RAILWAY_STATIC_URL")
    railway_public_domain: Optional[str] = Field(default=None, validation_alias="RAILWAY_PUBLIC_DOMAIN")
    railway_private_domain: Optional[str] = Field(default=None, validation_alias="RAILWAY_PRIVATE_DOMAIN")
    railway_project_name: Optional[str] = Field(default=None, validation_alias="RAILWAY_PROJECT_NAME")
    railway_environment_name: Optional[str] = Field(default=None, validation_alias="RAILWAY_ENVIRONMENT_NAME")
    railway_service_name: Optional[str] = Field(default=None, validation_alias="RAILWAY_SERVICE_NAME")
    railway_project_id: Optional[str] = Field(default=None, validation_alias="RAILWAY_PROJECT_ID")
    railway_environment_id: Optional[str] = Field(default=None, validation_alias="RAILWAY_ENVIRONMENT_ID")
    railway_service_id: Optional[str] = Field(default=None, validation_alias="RAILWAY_SERVICE_ID")
    railway_environment: Optional[str] = Field(default=None, validation_alias="RAILWAY_ENVIRONMENT")
    railway_service_velro_frontend_url: Optional[str] = Field(default=None, validation_alias="RAILWAY_SERVICE_VELRO_FRONTEND_URL")
    railway_service_velro_backend_url: Optional[str] = Field(default=None, validation_alias="RAILWAY_SERVICE_VELRO_BACKEND_URL")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Ignore extra environment variables
    )
    
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() in ["development", "dev", "local"]
    
    def validate_production_security(self) -> None:
        """Validate production security configuration."""
        if not self.is_production():
            return
            
        security_errors = []
        
        # JWT secret validation
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            security_errors.append("JWT_SECRET must be at least 32 characters")
        
        # Debug mode validation
        if self.debug:
            security_errors.append("DEBUG must be False in production")
        
        # Development bypasses validation
        if self.enable_development_bypasses:
            security_errors.append("ENABLE_DEVELOPMENT_BYPASSES must be False in production")
        
        # Mock authentication validation
        if self.enable_mock_authentication:
            security_errors.append("ENABLE_MOCK_AUTHENTICATION must be False in production")
        
        # Emergency auth mode validation
        if hasattr(self, 'emergency_auth_mode') and self.emergency_auth_mode:
            security_errors.append("EMERGENCY_AUTH_MODE must be False in production")
        
        # HTTPS validation for JWT
        if self.jwt_require_https and not any(
            origin.startswith('https://') for origin in self.cors_origins
        ):
            security_errors.append("HTTPS origins required when JWT_REQUIRE_HTTPS is enabled")
        
        if security_errors:
            error_msg = "Production security validation failed:\n" + "\n".join(f"- {error}" for error in security_errors)
            raise SecurityError(error_msg)
    
    def _validate_production_security_settings(self) -> None:
        """Comprehensive production security validation."""
        security_errors = []
        
        # Critical security validations for production
        if self.debug:
            security_errors.append("DEBUG mode must be disabled in production")
        
        if self.development_mode:
            security_errors.append("DEVELOPMENT_MODE must be disabled in production")
        
        if self.emergency_auth_mode:
            security_errors.append("EMERGENCY_AUTH_MODE must be disabled in production")
        
        if self.enable_mock_authentication:
            security_errors.append("ENABLE_MOCK_AUTHENTICATION must be disabled in production")
        
        if self.enable_test_users:
            security_errors.append("ENABLE_TEST_USERS must be disabled in production")
        
        if self.enable_development_bypasses:
            security_errors.append("ENABLE_DEVELOPMENT_BYPASSES must be disabled in production")
        
        if self.enable_debug_endpoints:
            security_errors.append("ENABLE_DEBUG_ENDPOINTS must be disabled in production")
        
        if self.verbose_error_messages:
            security_errors.append("VERBOSE_ERROR_MESSAGES must be disabled in production")
        
        # SECURITY: Enhanced JWT secret validation for production
        if len(self.jwt_secret) < 96:
            security_errors.append("JWT_SECRET must be at least 96 characters in production")
        
        # SECURITY: Check for default/weak secrets
        weak_secrets = [
            "your-secret-key-change-in-production", "test", "dev", "debug", 
            "secret", "key", "password", "admin", "velro", "jwt", "token",
            "1234", "abcd", "qwerty", "asdf", "changeme", "default"
        ]
        if any(weak in self.jwt_secret.lower() for weak in weak_secrets):
            security_errors.append("Weak or default JWT secret detected in production")
        
        # SECURITY: Entropy validation - ensure sufficient randomness
        import string
        unique_chars = len(set(self.jwt_secret))
        if unique_chars < 32:  # At least 32 unique characters
            security_errors.append(f"JWT_SECRET has insufficient entropy: {unique_chars} unique characters (minimum 32)")
        
        # SECURITY: Character set validation
        has_upper = any(c.isupper() for c in self.jwt_secret)
        has_lower = any(c.islower() for c in self.jwt_secret)
        has_digit = any(c.isdigit() for c in self.jwt_secret)
        has_special = any(c in string.punctuation for c in self.jwt_secret)
        
        if not (has_upper and has_lower and has_digit and has_special):
            security_errors.append("JWT_SECRET must contain uppercase, lowercase, digits, and special characters")
        
        # SECURITY: Check for repeated patterns
        if len(self.jwt_secret) != len(set(self.jwt_secret[i:i+4] for i in range(len(self.jwt_secret)-3))):
            # More than 75% unique 4-character substrings indicates good randomness
            unique_substrings = len(set(self.jwt_secret[i:i+4] for i in range(len(self.jwt_secret)-3)))
            total_substrings = len(self.jwt_secret) - 3
            if unique_substrings / total_substrings < 0.75:
                security_errors.append("JWT_SECRET contains too many repeated patterns")
        
        # Ensure HTTPS enforcement
        if not self.jwt_require_https:
            security_errors.append("JWT_REQUIRE_HTTPS must be enabled in production")
        
        # Validate security headers
        if not self.security_headers_enabled:
            security_errors.append("SECURITY_HEADERS_ENABLED must be true in production")
        
        # Validate CSRF protection
        if not self.csrf_protection_enabled:
            security_errors.append("CSRF_PROTECTION_ENABLED must be true in production")
        
        # Validate CORS configuration
        if "*" in self.cors_origins:
            security_errors.append("CORS wildcard origins (*) are not allowed in production")
        
        # Rate limiting validation
        if self.rate_limit_per_minute > 100:
            security_errors.append("RATE_LIMIT_PER_MINUTE should not exceed 100 in production")
        
        if security_errors:
            error_message = "CRITICAL SECURITY VIOLATIONS:\n" + "\n".join(f"- {error}" for error in security_errors)
            raise SecurityError(error_message)
    
    def validate_production_security(self) -> None:
        """Validate that security configurations are production-ready."""
        if self.is_production():
            self._validate_production_security_settings()
    
    def get_security_headers(self) -> dict:
        """Get comprehensive security headers configuration."""
        headers = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=(), usb=()",
            "X-Permitted-Cross-Domain-Policies": "none",
            "Cross-Origin-Embedder-Policy": "require-corp",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-site"
        }
        
        # Enhanced security headers for production
        if self.is_production() and self.security_headers_enabled:
            headers.update({
                "Strict-Transport-Security": f"max-age={self.hsts_max_age}; includeSubDomains; preload",
                "Content-Security-Policy": self.content_security_policy,
                "X-Download-Options": "noopen",
                "X-DNS-Prefetch-Control": "off",
                "Expect-CT": "max-age=86400, enforce"
            })
        
        return {k: v for k, v in headers.items() if v is not None}
    
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() == "development"
    
    @property
    def jwt_expiration_seconds(self) -> int:
        """Get JWT expiration time in seconds."""
        return self.jwt_expiration_hours * 3600
    
    @property
    def get_service_key(self) -> str:
        """Get the service key for Supabase operations.
        
        Note: The sb_secret_* format keys are for Supabase Management API,
        not for regular database operations. For database operations,
        use the JWT service_role_key.
        """
        # Use JWT service_role_key for database operations
        if self.supabase_service_role_key:
            return self.supabase_service_role_key
        # Fallback to sb_secret key if that's all we have (though it won't work with regular client)
        elif self.supabase_secret_key:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning("⚠️ Using sb_secret key which is meant for Management API, not database operations")
            return self.supabase_secret_key
        else:
            raise ValueError("No Supabase service key configured. Set SUPABASE_SERVICE_ROLE_KEY environment variable")


# Global settings instance
settings = Settings()
