"""
Production JWT Security Service for Supabase Authentication
Replaces emergency auth mode with proper JWT validation and Redis caching.
CRITICAL: This implements OWASP-compliant JWT validation with performance optimization.
"""

import json
import time
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Union
import logging
from uuid import UUID

import jwt
from jwt import ExpiredSignatureError, InvalidSignatureError, InvalidTokenError
import redis
from redis.exceptions import RedisError, ConnectionError

from config import settings

logger = logging.getLogger(__name__)

class JWTSecurityError(Exception):
    """JWT security-related exceptions."""
    pass

class SupabaseJWTValidator:
    """
    Production-grade Supabase JWT validator with Redis caching.
    Implements OWASP security guidelines with <50ms performance target.
    """
    
    def __init__(self):
        """Initialize JWT validator with Redis connection."""
        self.redis_client = None
        self.cache_enabled = False
        
        # Initialize Redis connection if available
        if hasattr(settings, 'redis_url') and settings.redis_url:
            try:
                self.redis_client = redis.from_url(
                    settings.redis_url,
                    socket_connect_timeout=0.5,
                    socket_timeout=0.5,
                    retry_on_timeout=True,
                    max_connections=20,
                    decode_responses=True
                )
                # Test connection
                self.redis_client.ping()
                self.cache_enabled = True
                logger.info("✅ JWT validator: Redis cache enabled")
            except Exception as e:
                logger.warning(f"⚠️ JWT validator: Redis unavailable, using in-memory cache: {e}")
                self.redis_client = None
                self.cache_enabled = False
        
        # In-memory cache fallback
        self._memory_cache = {}
        self._memory_cache_timestamps = {}
        
        # Performance metrics
        self._validation_count = 0
        self._cache_hits = 0
        self._cache_misses = 0
    
    def _get_cache_key(self, token: str) -> str:
        """Generate cache key for JWT token."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
        return f"jwt_valid:{token_hash}"
    
    def _cache_get(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get validated token data from cache."""
        if not self.cache_enabled:
            # Use in-memory cache
            if cache_key in self._memory_cache:
                timestamp = self._memory_cache_timestamps.get(cache_key, 0)
                if time.time() - timestamp < 300:  # 5 minute TTL for memory cache
                    self._cache_hits += 1
                    return self._memory_cache[cache_key]
                else:
                    # Expired
                    self._memory_cache.pop(cache_key, None)
                    self._memory_cache_timestamps.pop(cache_key, None)
            return None
        
        try:
            cached_data = self.redis_client.get(cache_key)
            if cached_data:
                self._cache_hits += 1
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"JWT cache get error: {e}")
        
        return None
    
    def _cache_set(self, cache_key: str, payload: Dict[str, Any], ttl: int = 600):
        """Cache validated token data."""
        if not self.cache_enabled:
            # Use in-memory cache
            self._memory_cache[cache_key] = payload
            self._memory_cache_timestamps[cache_key] = time.time()
            return
        
        try:
            self.redis_client.setex(cache_key, ttl, json.dumps(payload, default=str))
        except Exception as e:
            logger.warning(f"JWT cache set error: {e}")
    
    def validate_jwt_token(self, token: str) -> Dict[str, Any]:
        """
        Validate Supabase JWT token with caching and security checks.
        
        Args:
            token: JWT token string
            
        Returns:
            Dict containing validated user information
            
        Raises:
            JWTSecurityError: If token is invalid or security checks fail
        """
        start_time = time.time()
        self._validation_count += 1
        
        try:
            # SECURITY: Basic token format validation
            if not token or not isinstance(token, str) or len(token) < 50:
                raise JWTSecurityError("Invalid token format")
            
            # Check cache first for performance
            cache_key = self._get_cache_key(token)
            cached_payload = self._cache_get(cache_key)
            
            if cached_payload:
                elapsed = (time.time() - start_time) * 1000
                logger.debug(f"JWT validation cached in {elapsed:.1f}ms")
                return cached_payload
            
            self._cache_misses += 1
            
            # SECURITY: Decode and validate JWT with strict options
            try:
                # First, validate the header to prevent algorithm confusion
                unverified_header = jwt.get_unverified_header(token)
                algorithm = unverified_header.get('alg', '')
                
                # CRITICAL: Prevent algorithm confusion attacks
                if algorithm.lower() in ['none', 'null', '']:
                    raise JWTSecurityError("Algorithm 'none' not allowed")
                
                if algorithm != 'HS256':
                    raise JWTSecurityError(f"Unsupported algorithm: {algorithm}")
                
                # CRITICAL: Use Supabase JWT secret for validation
                jwt_secret = settings.jwt_secret
                if not jwt_secret:
                    raise JWTSecurityError("JWT secret not configured")
                
                # Decode with strict validation
                payload = jwt.decode(
                    token,
                    jwt_secret,
                    algorithms=['HS256'],
                    options={
                        'verify_signature': True,
                        'verify_exp': True,
                        'verify_nbf': True,
                        'verify_iat': True,
                        'require_exp': True,
                        'require_iat': True,
                        'require_sub': True
                    }
                )
                
                # SECURITY: Additional validation checks
                current_time = datetime.now(timezone.utc).timestamp()
                
                # Check required claims
                required_claims = ['sub', 'exp', 'iat']
                for claim in required_claims:
                    if claim not in payload:
                        raise JWTSecurityError(f"Missing required claim: {claim}")
                
                # Validate expiration with buffer
                exp = payload.get('exp', 0)
                if exp <= current_time:
                    raise JWTSecurityError("Token has expired")
                
                # Validate not-before with buffer
                nbf = payload.get('nbf', 0)
                if nbf > current_time + 60:  # 60 second tolerance
                    raise JWTSecurityError("Token not yet valid")
                
                # Validate issued-at (not too old)
                iat = payload.get('iat', 0)
                max_age = 7 * 24 * 3600  # 7 days
                if iat < current_time - max_age:
                    raise JWTSecurityError("Token too old")
                
                # Validate subject format (user UUID)
                subject = payload.get('sub', '')
                try:
                    user_uuid = UUID(subject)
                except ValueError:
                    raise JWTSecurityError("Invalid user ID format")
                
                # Extract user information
                validated_payload = {
                    'user_id': str(user_uuid),
                    'email': payload.get('email', ''),
                    'role': payload.get('role', 'viewer'),
                    'exp': exp,
                    'iat': iat,
                    'aud': payload.get('aud', ''),
                    'app_metadata': payload.get('app_metadata', {}),
                    'user_metadata': payload.get('user_metadata', {})
                }
                
                # Cache the validated payload (TTL based on remaining token life)
                remaining_time = int(exp - current_time)
                cache_ttl = min(remaining_time, 600)  # Max 10 minutes
                
                if cache_ttl > 60:  # Only cache if more than 1 minute remaining
                    self._cache_set(cache_key, validated_payload, cache_ttl)
                
                elapsed = (time.time() - start_time) * 1000
                logger.debug(f"JWT validation completed in {elapsed:.1f}ms")
                
                if elapsed > 50:
                    logger.warning(f"JWT validation took {elapsed:.1f}ms (target: <50ms)")
                
                return validated_payload
                
            except ExpiredSignatureError:
                raise JWTSecurityError("Token has expired")
            except InvalidSignatureError:
                raise JWTSecurityError("Invalid token signature")
            except InvalidTokenError as e:
                raise JWTSecurityError(f"Invalid token: {str(e)}")
            
        except JWTSecurityError:
            # Re-raise our security errors
            raise
        except Exception as e:
            logger.error(f"JWT validation error: {e}", exc_info=True)
            raise JWTSecurityError("Token validation failed")
    
    def verify_supabase_token(self, token: str, expected_aud: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify Supabase-specific JWT token.
        
        Args:
            token: JWT token from Supabase Auth
            expected_aud: Expected audience claim
            
        Returns:
            Validated user payload
            
        Raises:
            JWTSecurityError: If validation fails
        """
        payload = self.validate_jwt_token(token)
        
        # Additional Supabase-specific checks
        if expected_aud:
            token_aud = payload.get('aud')
            if token_aud != expected_aud:
                raise JWTSecurityError(f"Invalid audience. Expected: {expected_aud}, got: {token_aud}")
        
        return payload
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get JWT validation performance metrics."""
        if self._validation_count == 0:
            hit_rate = 0.0
        else:
            hit_rate = self._cache_hits / (self._cache_hits + self._cache_misses)
        
        return {
            'total_validations': self._validation_count,
            'cache_hits': self._cache_hits,
            'cache_misses': self._cache_misses,
            'cache_hit_rate': round(hit_rate * 100, 2),
            'cache_enabled': self.cache_enabled,
            'redis_available': self.redis_client is not None
        }
    
    def clear_cache(self):
        """Clear JWT validation cache."""
        if self.cache_enabled and self.redis_client:
            try:
                # Clear Redis JWT cache
                keys = self.redis_client.keys("jwt_valid:*")
                if keys:
                    self.redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} JWT cache entries from Redis")
            except Exception as e:
                logger.error(f"Error clearing JWT cache: {e}")
        
        # Clear memory cache
        self._memory_cache.clear()
        self._memory_cache_timestamps.clear()

# Global JWT validator instance
_jwt_validator: Optional[SupabaseJWTValidator] = None

def get_jwt_validator() -> SupabaseJWTValidator:
    """Get global JWT validator instance (singleton)."""
    global _jwt_validator
    if _jwt_validator is None:
        _jwt_validator = SupabaseJWTValidator()
    return _jwt_validator

def validate_jwt(token: str) -> Dict[str, Any]:
    """
    Validate JWT token using global validator instance.
    
    Args:
        token: JWT token string
        
    Returns:
        Validated user payload
        
    Raises:
        JWTSecurityError: If validation fails
    """
    validator = get_jwt_validator()
    return validator.validate_jwt_token(token)

def verify_supabase_jwt(token: str, expected_aud: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify Supabase JWT token using global validator.
    
    Args:
        token: Supabase JWT token
        expected_aud: Expected audience claim
        
    Returns:
        Validated user payload
        
    Raises:
        JWTSecurityError: If validation fails
    """
    validator = get_jwt_validator()
    return validator.verify_supabase_token(token, expected_aud)

def get_jwt_metrics() -> Dict[str, Any]:
    """Get JWT validation performance metrics."""
    validator = get_jwt_validator()
    return validator.get_metrics()

def clear_jwt_cache():
    """Clear JWT validation cache."""
    validator = get_jwt_validator()
    validator.clear_cache()

# Health check function
async def jwt_health_check() -> Dict[str, Any]:
    """JWT security service health check."""
    try:
        validator = get_jwt_validator()
        metrics = validator.get_metrics()
        
        return {
            "status": "healthy",
            "cache_enabled": validator.cache_enabled,
            "redis_available": validator.redis_client is not None,
            "performance_metrics": metrics
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }