#!/usr/bin/env python3
"""
Debug script to test JWT verification and identify the specific error.
"""
import os
import sys
import json
from datetime import datetime, timezone

# Add the current directory to Python path to import our modules
sys.path.append('/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend')

from config import settings
from utils.security import JWTSecurity, SecurityError
from jose import jwt, JWTError
import base64
import hmac
import hashlib

def test_jwt_verification():
    """Test JWT verification with various scenarios."""
    
    print("=== JWT VERIFICATION DEBUG ===")
    print(f"JWT Secret available: {'Yes' if settings.jwt_secret else 'No'}")
    print(f"JWT Secret length: {len(settings.jwt_secret) if settings.jwt_secret else 0}")
    print(f"JWT Algorithm: {settings.jwt_algorithm}")
    
    # Test 1: Create a JWT using auth service method
    print("\n=== TEST 1: Auth Service JWT Creation ===")
    try:
        # Simulate the same JWT creation as in auth service
        header = {"alg": "HS256", "typ": "JWT"}
        header_encoded = base64.b64encode(json.dumps(header).encode()).decode().rstrip('=')
        
        payload = {
            "sub": "bd1a2f69-89eb-489f-9288-8aacf4924763",
            "email": "demo@example.com",
            "role": "viewer",
            "iat": int(datetime.now().timestamp()),
            "exp": int(datetime.now().timestamp()) + settings.jwt_expiration_seconds,
            "iss": "velro-api"
        }
        payload_encoded = base64.b64encode(json.dumps(payload).encode()).decode().rstrip('=')
        
        # Create signature using the same method as auth service
        secret = settings.jwt_secret.encode()
        message = f"{header_encoded}.{payload_encoded}"
        signature = hmac.new(secret, message.encode(), hashlib.sha256).digest()
        signature_encoded = base64.b64encode(signature).decode().rstrip('=')
        
        manual_jwt = f"{header_encoded}.{payload_encoded}.{signature_encoded}"
        
        print(f"Manual JWT created: {manual_jwt[:100]}...")
        
        # Try to verify this token with JWTSecurity.verify_token
        try:
            verified_payload = JWTSecurity.verify_token(manual_jwt, "access_token")
            print("✅ JWTSecurity.verify_token succeeded!")
            print(f"Verified payload: {verified_payload}")
        except SecurityError as e:
            print(f"❌ JWTSecurity.verify_token failed: {e}")
        except Exception as e:
            print(f"❌ JWTSecurity.verify_token unexpected error: {e}")
            
    except Exception as e:
        print(f"❌ JWT creation failed: {e}")
    
    # Test 2: Try using jose JWT directly
    print("\n=== TEST 2: Jose JWT Direct Test ===")
    try:
        # Create JWT using jose library (same as JWTSecurity should use)
        payload = {
            "sub": "bd1a2f69-89eb-489f-9288-8aacf4924763",
            "email": "demo@example.com",
            "role": "viewer",
            "iat": int(datetime.now().timestamp()),
            "exp": int(datetime.now().timestamp()) + settings.jwt_expiration_seconds,
            "nbf": int(datetime.now().timestamp()),
            "iss": "velro-api",
            "aud": "velro-frontend",
            "type": "access_token"
        }
        
        jose_jwt = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        print(f"Jose JWT created: {jose_jwt[:100]}...")
        
        # Try to decode it
        try:
            decoded = jwt.decode(
                jose_jwt,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": False,
                    "require_exp": True,
                    "require_iat": True,
                    "require_nbf": True
                }
            )
            print("✅ Jose JWT decode succeeded!")
            print(f"Decoded payload: {decoded}")
            
            # Now try with JWTSecurity.verify_token
            try:
                verified_payload = JWTSecurity.verify_token(jose_jwt, "access_token")
                print("✅ JWTSecurity.verify_token on Jose JWT succeeded!")
                print(f"Verified payload: {verified_payload}")
            except SecurityError as e:
                print(f"❌ JWTSecurity.verify_token on Jose JWT failed: {e}")
            except Exception as e:
                print(f"❌ JWTSecurity.verify_token on Jose JWT unexpected error: {e}")
                
        except JWTError as e:
            print(f"❌ Jose JWT decode failed: {e}")
        except Exception as e:
            print(f"❌ Jose JWT decode unexpected error: {e}")
            
    except Exception as e:
        print(f"❌ Jose JWT creation failed: {e}")
    
    # Test 3: Test what happens with a real Supabase-style JWT
    print("\n=== TEST 3: Supabase-style JWT Test ===")
    try:
        # Create a more complete payload like Supabase would
        supabase_payload = {
            "sub": "bd1a2f69-89eb-489f-9288-8aacf4924763",
            "email": "demo@example.com",
            "email_confirmed_at": datetime.now(timezone.utc).isoformat(),
            "phone": "",
            "phone_confirmed_at": None,
            "aud": "authenticated",
            "role": "authenticated",
            "aal": "aal1",
            "amr": [{"method": "password", "timestamp": int(datetime.now().timestamp())}],
            "session_id": "test-session-id",
            "is_anonymous": False,
            "iss": settings.supabase_url + "/auth/v1",
            "iat": int(datetime.now().timestamp()),
            "exp": int(datetime.now().timestamp()) + 3600,
            "nbf": int(datetime.now().timestamp()),
        }
        
        supabase_jwt = jwt.encode(supabase_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        print(f"Supabase-style JWT created: {supabase_jwt[:100]}...")
        
        # Try to decode it with jose
        try:
            decoded = jwt.decode(
                supabase_jwt,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": False,
                    "verify_iss": False,  # Different issuer
                    "require_exp": True,
                    "require_iat": True,
                    "require_nbf": True
                }
            )
            print("✅ Supabase-style JWT decode succeeded!")
            print(f"Decoded keys: {list(decoded.keys())}")
            
        except JWTError as e:
            print(f"❌ Supabase-style JWT decode failed: {e}")
        except Exception as e:
            print(f"❌ Supabase-style JWT decode unexpected error: {e}")
            
    except Exception as e:
        print(f"❌ Supabase-style JWT creation failed: {e}")

if __name__ == "__main__":
    test_jwt_verification()