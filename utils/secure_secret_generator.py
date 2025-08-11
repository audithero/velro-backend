"""
Secure Secret Generator for JWT and other cryptographic keys
SECURITY: Enterprise-grade secret generation following OWASP guidelines
"""
import os
import secrets
import string
import hashlib
import base64
from typing import Dict, Any, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SecureSecretGenerator:
    """Generate cryptographically secure secrets for JWT and other purposes."""
    
    @staticmethod
    def generate_jwt_secret(length: int = 128) -> str:
        """
        Generate a cryptographically secure JWT secret.
        
        Args:
            length: Minimum length of the secret (default: 128 chars for enterprise)
            
        Returns:
            Secure JWT secret string
        """
        if length < 96:
            raise ValueError("JWT secret must be at least 96 characters for production")
        
        # Use secure character set
        charset = string.ascii_letters + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
        
        # Generate random secret
        secret = ''.join(secrets.choice(charset) for _ in range(length))
        
        # Validate generated secret meets security requirements
        validation_result = SecureSecretGenerator.validate_jwt_secret(secret)
        if not validation_result['valid']:
            # Regenerate if validation fails (rare but possible)
            logger.warning("Generated secret failed validation, regenerating...")
            return SecureSecretGenerator.generate_jwt_secret(length)
        
        return secret
    
    @staticmethod
    def validate_jwt_secret(secret: str) -> Dict[str, Any]:
        """
        Validate JWT secret strength according to security requirements.
        
        Args:
            secret: JWT secret to validate
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'valid': True,
            'errors': [],
            'warnings': [],
            'strength_score': 0
        }
        
        # Check minimum length
        if len(secret) < 32:
            validation_result['errors'].append("Secret too short (minimum 32 characters)")
            validation_result['valid'] = False
        elif len(secret) < 96:
            validation_result['warnings'].append("Secret should be at least 96 characters for production")
        
        # Check character set diversity
        has_upper = any(c.isupper() for c in secret)
        has_lower = any(c.islower() for c in secret)
        has_digit = any(c.isdigit() for c in secret)
        has_special = any(c in string.punctuation for c in secret)
        
        charset_score = sum([has_upper, has_lower, has_digit, has_special])
        if charset_score < 4:
            validation_result['errors'].append("Secret must contain uppercase, lowercase, digits, and special characters")
            validation_result['valid'] = False
        
        # Check entropy (unique characters)
        unique_chars = len(set(secret))
        if unique_chars < 16:
            validation_result['errors'].append(f"Insufficient entropy: {unique_chars} unique characters (minimum 16)")
            validation_result['valid'] = False
        elif unique_chars < 32:
            validation_result['warnings'].append(f"Low entropy: {unique_chars} unique characters (recommended 32+)")
        
        # Check for weak patterns
        weak_patterns = [
            "123456", "abcdef", "qwerty", "password", "secret", "jwt", "token",
            "admin", "user", "test", "dev", "prod", "velro", "api", "key"
        ]
        
        secret_lower = secret.lower()
        for pattern in weak_patterns:
            if pattern in secret_lower:
                validation_result['errors'].append(f"Contains weak pattern: {pattern}")
                validation_result['valid'] = False
        
        # Check for repetitive patterns
        repetitive_count = 0
        for i in range(len(secret) - 3):
            substring = secret[i:i+4]
            if secret.count(substring) > 1:
                repetitive_count += 1
        
        repetition_ratio = repetitive_count / max(1, len(secret) - 3)
        if repetition_ratio > 0.25:
            validation_result['warnings'].append("Contains repetitive patterns")
        
        # Calculate strength score (0-100)
        length_score = min(25, len(secret) // 4)  # Up to 25 points for length
        charset_score = charset_score * 10  # Up to 40 points for character diversity
        entropy_score = min(25, unique_chars // 2)  # Up to 25 points for entropy
        pattern_score = max(0, 10 - repetitive_count)  # Up to 10 points for avoiding patterns
        
        validation_result['strength_score'] = length_score + charset_score + entropy_score + pattern_score
        
        return validation_result
    
    @staticmethod
    def generate_encryption_key() -> bytes:
        """Generate a secure encryption key for token storage."""
        return base64.urlsafe_b64encode(os.urandom(32))
    
    @staticmethod
    def generate_api_key(prefix: str = "vk", length: int = 32) -> str:
        """
        Generate a secure API key with prefix.
        
        Args:
            prefix: Key prefix (default: "vk" for Velro Key)
            length: Length of random part (default: 32)
            
        Returns:
            API key in format: prefix_randomstring
        """
        random_part = base64.urlsafe_b64encode(os.urandom(length)).decode('ascii').rstrip('=')
        return f"{prefix}_{random_part}"
    
    @staticmethod
    def generate_session_token(length: int = 64) -> str:
        """Generate a secure session token."""
        return secrets.token_urlsafe(length)
    
    @staticmethod 
    def generate_csrf_token() -> str:
        """Generate a CSRF protection token."""
        return secrets.token_urlsafe(32)
    
    @staticmethod
    def hash_secret(secret: str, salt: Optional[str] = None) -> Dict[str, str]:
        """
        Hash a secret with salt for secure storage.
        
        Args:
            secret: Secret to hash
            salt: Optional salt (generated if not provided)
            
        Returns:
            Dictionary with hash and salt
        """
        if salt is None:
            salt = secrets.token_hex(16)
        
        # Use PBKDF2 for secure hashing
        secret_hash = hashlib.pbkdf2_hmac('sha256', secret.encode(), salt.encode(), 100000)
        
        return {
            'hash': base64.b64encode(secret_hash).decode('ascii'),
            'salt': salt
        }
    
    @staticmethod
    def verify_secret_hash(secret: str, stored_hash: str, salt: str) -> bool:
        """
        Verify a secret against its hash.
        
        Args:
            secret: Secret to verify
            stored_hash: Stored hash
            salt: Salt used for hashing
            
        Returns:
            True if secret matches hash
        """
        try:
            secret_hash = hashlib.pbkdf2_hmac('sha256', secret.encode(), salt.encode(), 100000)
            computed_hash = base64.b64encode(secret_hash).decode('ascii')
            
            # Constant-time comparison to prevent timing attacks
            import hmac
            return hmac.compare_digest(computed_hash, stored_hash)
        except Exception as e:
            logger.error(f"Secret hash verification failed: {e}")
            return False

def generate_production_secrets():
    """Generate all production secrets and print setup commands."""
    print("=" * 80)
    print("VELRO PRODUCTION SECRETS GENERATOR")
    print("=" * 80)
    print()
    
    # Generate JWT secret
    print("Generating JWT Secret...")
    jwt_secret = SecureSecretGenerator.generate_jwt_secret(128)
    validation = SecureSecretGenerator.validate_jwt_secret(jwt_secret)
    
    print(f"✅ JWT Secret Generated (Length: {len(jwt_secret)}, Strength: {validation['strength_score']}/100)")
    if validation['warnings']:
        for warning in validation['warnings']:
            print(f"⚠️  {warning}")
    
    # Generate encryption key
    print("\nGenerating Token Encryption Key...")
    encryption_key = SecureSecretGenerator.generate_encryption_key()
    print(f"✅ Token Encryption Key Generated")
    
    # Generate API key
    print("\nGenerating API Key...")
    api_key = SecureSecretGenerator.generate_api_key("velro", 48)
    print(f"✅ API Key Generated")
    
    print("\n" + "=" * 80)
    print("RAILWAY ENVIRONMENT VARIABLES - COPY TO RAILWAY DASHBOARD")
    print("=" * 80)
    print()
    print(f"JWT_SECRET={jwt_secret}")
    print(f"TOKEN_ENCRYPTION_KEY={encryption_key.decode('ascii')}")
    print(f"API_KEY={api_key}")
    print()
    print("=" * 80)
    print("SECURITY CHECKLIST:")
    print("1. Set these secrets in Railway dashboard (not in code)")
    print("2. Enable all security flags in production")
    print("3. Rotate secrets regularly (every 90 days)")
    print("4. Monitor for security violations")
    print("5. Backup encryption keys securely")
    print("=" * 80)

if __name__ == "__main__":
    generate_production_secrets()