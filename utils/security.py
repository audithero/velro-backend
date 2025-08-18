"""
Security utilities for password hashing, JWT management, and security validations.
Implementation follows OWASP security guidelines and best practices.
"""
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Set, Any, Union
from passlib.context import CryptContext
from passlib.hash import bcrypt
from jose import JWTError, jwt
import logging
import asyncio
from config import settings

logger = logging.getLogger(__name__)

# Password hashing context with bcrypt (OWASP recommended)
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings.password_hash_rounds if hasattr(settings, 'password_hash_rounds') else 12
)

# JWT blacklist for token revocation (in-memory for now, should be Redis in production)
JWT_BLACKLIST: Set[str] = set()

class SecurityError(Exception):
    """Custom security-related exception."""
    pass

class PasswordSecurity:
    """Password security utilities following OWASP guidelines."""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash password using bcrypt with configurable rounds.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password string
            
        Raises:
            SecurityError: If password is invalid
        """
        if not password or len(password) < 8:
            raise SecurityError("Password must be at least 8 characters long")
        
        if len(password) > 128:
            raise SecurityError("Password too long (max 128 characters)")
        
        try:
            return pwd_context.hash(password)
        except Exception as e:
            logger.error(f"Password hashing failed: {e}")
            raise SecurityError("Password hashing failed")
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """
        Verify password against hash.
        
        Args:
            password: Plain text password
            hashed: Hashed password from database
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            return pwd_context.verify(password, hashed)
        except Exception as e:
            logger.error(f"Password verification failed: {e}")
            return False
    
    @staticmethod
    def needs_rehash(hashed: str) -> bool:
        """
        Check if password hash needs updating (e.g., rounds changed).
        
        Args:
            hashed: Hashed password from database
            
        Returns:
            True if hash needs updating
        """
        return pwd_context.needs_update(hashed)
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """
        Generate cryptographically secure random token.
        
        Args:
            length: Token length in bytes
            
        Returns:
            URL-safe base64 encoded token
        """
        return secrets.token_urlsafe(length)

class JWTSecurity:
    """JWT security utilities with blacklisting and validation."""
    
    @staticmethod
    def create_access_token(
        user_id: str,
        email: str,
        additional_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create JWT access token with security enhancements.
        
        Args:
            user_id: User identifier
            email: User email
            additional_claims: Additional JWT claims
            
        Returns:
            JWT token string
            
        Raises:
            SecurityError: If token creation fails
        """
        try:
            now = datetime.now(timezone.utc)
            expires = now + timedelta(hours=settings.jwt_expiration_hours)
            
            # Standard JWT claims
            payload = {
                "sub": str(user_id),  # Subject (user ID)
                "email": email,
                "iat": now.timestamp(),  # Issued at
                "exp": expires.timestamp(),  # Expiration
                "nbf": now.timestamp(),  # Not before
                "iss": "velro-api",  # Issuer
                "aud": "velro-frontend",  # Audience
                "jti": secrets.token_urlsafe(16),  # JWT ID for blacklisting
                "type": "access_token"
            }
            
            # Add additional claims if provided
            if additional_claims:
                payload.update(additional_claims)
            
            # Create token
            token = jwt.encode(
                payload,
                settings.jwt_secret,
                algorithm=settings.jwt_algorithm
            )
            
            logger.info(f"Created access token for user {user_id}")
            return token
            
        except Exception as e:
            logger.error(f"JWT token creation failed: {e}")
            raise SecurityError("Token creation failed")
    
    @staticmethod
    def create_refresh_token(user_id: str) -> str:
        """
        Create JWT refresh token with longer expiration.
        
        Args:
            user_id: User identifier
            
        Returns:
            JWT refresh token string
        """
        try:
            now = datetime.now(timezone.utc)
            expires = now + timedelta(hours=settings.jwt_refresh_token_expire_hours)
            
            payload = {
                "sub": str(user_id),
                "iat": now.timestamp(),
                "exp": expires.timestamp(),
                "nbf": now.timestamp(),
                "iss": "velro-api",
                "jti": secrets.token_urlsafe(16),
                "type": "refresh_token"
            }
            
            token = jwt.encode(
                payload,
                settings.jwt_secret,
                algorithm=settings.jwt_algorithm
            )
            
            logger.info(f"Created refresh token for user {user_id}")
            return token
            
        except Exception as e:
            logger.error(f"Refresh token creation failed: {e}")
            raise SecurityError("Refresh token creation failed")
    
    @staticmethod
    def verify_token(token: str, token_type: str = "access_token") -> Dict[str, Any]:
        """
        Verify JWT token with comprehensive security checks and algorithm validation.
        
        Args:
            token: JWT token string
            token_type: Expected token type (access_token or refresh_token)
            
        Returns:
            Decoded token payload
            
        Raises:
            SecurityError: If token is invalid or security checks fail
        """
        try:
            # SECURITY: Validate token format first
            if not token or not isinstance(token, str):
                raise SecurityError("Invalid token format")
            
            # SECURITY: Prevent algorithm confusion attacks
            try:
                header = jwt.get_unverified_header(token)
                if header.get("alg", "").lower() in ["none", "null", ""]:
                    raise SecurityError("Algorithm 'none' not allowed")
                
                if header.get("alg") != settings.jwt_algorithm:
                    raise SecurityError(f"Invalid algorithm. Expected: {settings.jwt_algorithm}")
                    
            except jwt.JWTError as e:
                raise SecurityError(f"Invalid token header: {str(e)}")
            
            # Check if token is blacklisted
            if settings.jwt_blacklist_enabled and token in JWT_BLACKLIST:
                raise SecurityError("Token has been revoked")
            
            # SECURITY: Enhanced token decode with strict validation
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],  # Only allow configured algorithm
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": False,  # Optional audience verification
                    "require_exp": True,
                    "require_iat": True,
                    "require_nbf": True,
                    "require_sub": True,  # Require subject claim
                    "require_jti": True   # Require JWT ID for blacklisting
                }
            )
            
            # SECURITY: Verify required claims exist
            required_claims = ["sub", "iat", "exp", "nbf", "iss", "jti"]
            missing_claims = [claim for claim in required_claims if claim not in payload]
            if missing_claims:
                raise SecurityError(f"Missing required claims: {missing_claims}")
            
            # Verify token type
            if payload.get("type") != token_type:
                raise SecurityError(f"Invalid token type. Expected: {token_type}")
            
            # Verify issuer
            if payload.get("iss") != "velro-api":
                raise SecurityError("Invalid token issuer")
            
            # SECURITY: Additional timestamp validation
            now = datetime.now(timezone.utc).timestamp()
            
            # Check if token is not yet valid
            if payload.get("nbf", 0) > now + 60:  # 60 second clock skew tolerance
                raise SecurityError("Token not yet valid")
            
            # Check expiration with buffer
            if payload.get("exp", 0) <= now:
                raise SecurityError("Token has expired")
            
            # SECURITY: Check for replay attacks (issued too far in past)
            max_age = 7 * 24 * 3600  # 7 days max token age
            if payload.get("iat", 0) < now - max_age:
                raise SecurityError("Token too old")
            
            # SECURITY: Validate subject (user ID) format
            subject = payload.get("sub")
            if not subject or len(str(subject)) < 10:  # Minimum subject length
                raise SecurityError("Invalid subject claim")
            
            logger.debug(f"Token verification successful for user {payload.get('sub')}")
            return payload
            
        except JWTError as e:
            logger.warning(f"JWT verification failed: {e}")
            raise SecurityError(f"Invalid token: {str(e)}")
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            raise SecurityError("Token verification failed")
    
    @staticmethod
    def blacklist_token(token: str) -> None:
        """
        Add token to blacklist for revocation.
        
        Args:
            token: JWT token to blacklist
        """
        if settings.jwt_blacklist_enabled:
            try:
                # Extract JTI (JWT ID) for more efficient blacklisting
                payload = jwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": False}  # Don't verify expiration for blacklisting
                )
                
                jti = payload.get("jti")
                if jti:
                    JWT_BLACKLIST.add(jti)
                    logger.info(f"Token blacklisted (JTI: {jti})")
                else:
                    # Fallback: blacklist full token
                    JWT_BLACKLIST.add(token)
                    logger.info("Token blacklisted (full token)")
                    
            except Exception as e:
                logger.error(f"Token blacklisting failed: {e}")
                # Fallback: blacklist full token
                JWT_BLACKLIST.add(token)
    
    @staticmethod
    def cleanup_blacklist() -> None:
        """Clean up expired tokens from blacklist."""
        if not settings.jwt_blacklist_enabled:
            return
        
        try:
            current_time = datetime.now(timezone.utc).timestamp()
            expired_tokens = []
            
            for token_or_jti in JWT_BLACKLIST:
                try:
                    # Try to decode to check expiration
                    payload = jwt.decode(
                        token_or_jti,
                        settings.jwt_secret,
                        algorithms=[settings.jwt_algorithm],
                        options={"verify_exp": False}
                    )
                    
                    if payload.get("exp", 0) < current_time:
                        expired_tokens.append(token_or_jti)
                        
                except:
                    # If decoding fails, assume it's expired and remove
                    expired_tokens.append(token_or_jti)
            
            # Remove expired tokens
            for token in expired_tokens:
                JWT_BLACKLIST.discard(token)
            
            if expired_tokens:
                logger.info(f"Cleaned up {len(expired_tokens)} expired tokens from blacklist")
                
        except Exception as e:
            logger.error(f"Blacklist cleanup failed: {e}")

class SecurityValidation:
    """Additional security validation utilities."""
    
    @staticmethod
    def validate_production_config() -> None:
        """
        Validate that the application is configured securely for production.
        
        Raises:
            SecurityError: If production security requirements are not met
        """
        try:
            settings.validate_production_security()
            logger.info("Production security validation passed")
        except Exception as e:
            logger.error(f"Production security validation failed: {e}")
            raise SecurityError(f"Production security validation failed: {e}")
    
    @staticmethod
    def generate_csrf_token() -> str:
        """Generate CSRF token for form protection."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def verify_csrf_token(token: str, expected: str) -> bool:
        """Verify CSRF token using constant-time comparison."""
        return hmac.compare_digest(token, expected)
    
    @staticmethod
    def hash_api_key(api_key: str) -> str:
        """Hash API key for secure storage."""
        return hashlib.sha256(api_key.encode()).hexdigest()
    
    @staticmethod
    def constant_time_compare(a: str, b: str) -> bool:
        """Constant-time string comparison to prevent timing attacks."""
        return hmac.compare_digest(a, b)

# Initialize security system
async def init_security_system():
    """Initialize security system with validation and cleanup tasks."""
    try:
        # Validate production configuration if in production
        if settings.is_production():
            SecurityValidation.validate_production_config()
        
        # Start periodic blacklist cleanup
        if settings.jwt_blacklist_enabled:
            asyncio.create_task(periodic_blacklist_cleanup())
        
        logger.info("Security system initialized successfully")
        
    except Exception as e:
        logger.error(f"Security system initialization failed: {e}")
        if settings.is_production():
            raise

async def periodic_blacklist_cleanup():
    """Periodic task to clean up expired tokens from blacklist."""
    while True:
        try:
            await asyncio.sleep(3600)  # Run every hour
            JWTSecurity.cleanup_blacklist()
        except Exception as e:
            logger.error(f"Blacklist cleanup task failed: {e}")

# Export main utilities
__all__ = [
    "PasswordSecurity",
    "JWTSecurity", 
    "SecurityValidation",
    "SecurityError",
    "init_security_system"
]