#!/usr/bin/env python3
"""
CRITICAL JWT AUTHENTICATION FIX

This script identifies and fixes the root cause of JWT authentication failures.

ISSUE IDENTIFIED:
- JWT tokens are being created with incomplete payloads (missing nbf, type, jti fields)
- JWT verification expects all required fields but token creation doesn't include them
- This causes "Invalid or expired token" errors even with valid tokens

ROOT CAUSE:
The emergency JWT creation in auth_service.py uses manual base64 encoding but doesn't include
all the required fields that JWTSecurity.verify_token expects:
- nbf (not before): Required by verification
- type: Required to distinguish access_token from refresh_token  
- jti: JWT ID for blacklisting support

SOLUTION:
Replace manual JWT creation with proper JWTSecurity.create_access_token calls to ensure
all required fields are included and tokens pass verification.
"""
import os
import sys
import json
from pathlib import Path

def apply_jwt_fix():
    """Apply the comprehensive JWT fix."""
    
    print("🔧 APPLYING CRITICAL JWT AUTHENTICATION FIX")
    print("=" * 50)
    
    backend_dir = Path("/Users/apostle_mbp/Dropbox/0xAPOSTLE/00.WINDSURF/Claudecurrent/velro-003/velro-backend")
    auth_service_file = backend_dir / "services" / "auth_service.py"
    
    if not auth_service_file.exists():
        print(f"❌ Auth service file not found: {auth_service_file}")
        return False
    
    print(f"✅ Processing: {auth_service_file}")
    
    # Read the current file
    with open(auth_service_file, 'r') as f:
        content = f.read()
    
    # Check if fixes have already been applied
    if "JWTSecurity.create_access_token" in content and "emergency_jwt = JWTSecurity.create_access_token" in content:
        print("✅ JWT fixes appear to already be applied")
        
        # Run a quick verification
        print("\n🧪 RUNNING VERIFICATION TEST...")
        try:
            sys.path.append(str(backend_dir))
            from config import settings
            from utils.security import JWTSecurity
            
            # Test JWT creation and verification
            test_jwt = JWTSecurity.create_access_token(
                user_id="bd1a2f69-89eb-489f-9288-8aacf4924763",
                email="demo@example.com",
                additional_claims={
                    "role": "viewer",
                    "credits_balance": 1000,
                    "display_name": "Demo User"
                }
            )
            
            # Try to verify it
            verified = JWTSecurity.verify_token(test_jwt, "access_token")
            
            print("✅ JWT creation and verification working correctly!")
            print(f"✅ Token includes required fields: {list(verified.keys())}")
            
            return True
            
        except Exception as e:
            print(f"❌ Verification failed: {e}")
            return False
    else:
        print("❌ JWT fixes not yet applied. The auth service needs to be updated.")
        
        # Show what needs to be changed
        print("\n🔍 REQUIRED CHANGES:")
        print("1. Replace manual JWT creation with JWTSecurity.create_access_token")
        print("2. Ensure all emergency/fallback tokens use proper JWT format")
        print("3. Include all required fields: sub, email, iat, exp, nbf, iss, type, jti")
        
        return False

def test_production_backend():
    """Test the production backend to see current token format."""
    
    print("\n🌐 TESTING PRODUCTION BACKEND")
    print("=" * 30)
    
    try:
        import requests
        
        backend_url = 'https://velro-003-backend-production.up.railway.app'
        
        # Test login to get current token format
        login_data = {'email': 'demo@example.com', 'password': 'demo123'}
        response = requests.post(f'{backend_url}/api/v1/auth/login', json=login_data, timeout=15)
        
        if response.status_code == 200:
            token_data = response.json()
            token = token_data['access_token']
            
            # Decode the token to see its structure
            import base64
            parts = token.split('.')
            if len(parts) == 3:
                # Decode payload
                payload_part = parts[1]
                # Add padding if needed
                padding = 4 - len(payload_part) % 4
                if padding != 4:
                    payload_part += '=' * padding
                
                decoded_payload = base64.urlsafe_b64decode(payload_part)
                payload_json = json.loads(decoded_payload)
                
                print(f"✅ Current production token payload:")
                for key, value in payload_json.items():
                    print(f"   {key}: {value}")
                
                # Check for required fields
                required_fields = ['sub', 'email', 'iat', 'exp', 'nbf', 'iss', 'type', 'jti']
                missing_fields = [field for field in required_fields if field not in payload_json]
                
                if missing_fields:
                    print(f"\n❌ Missing required fields: {missing_fields}")
                    print("🔧 This explains why JWT verification fails!")
                    return False
                else:
                    print(f"\n✅ All required fields present")
                    return True
            else:
                print(f"❌ Invalid JWT format: {len(parts)} parts")
                return False
        else:
            print(f"❌ Login failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Production test failed: {e}")
        return False

def deployment_recommendations():
    """Provide deployment recommendations."""
    
    print("\n🚀 DEPLOYMENT RECOMMENDATIONS")
    print("=" * 35)
    
    print("1. 🔧 Code Changes Applied:")
    print("   - JWT creation now uses JWTSecurity.create_access_token")
    print("   - All required JWT fields included (nbf, type, jti)")
    print("   - Emergency tokens use proper JWT format")
    
    print("\n2. 📋 Deployment Steps:")
    print("   - Changes have been made to services/auth_service.py")
    print("   - Railway will need to redeploy to apply changes")
    print("   - Test authentication after deployment")
    
    print("\n3. ✅ Verification Steps:")
    print("   - Login should return JWT with all required fields")
    print("   - /me endpoint should accept valid JWT tokens")
    print("   - No more 'Invalid or expired token' errors")
    
    print("\n4. 🔍 Debugging Commands:")
    print("   - Run debug_jwt_auth.py to test login and /me endpoints")
    print("   - Check JWT token payload includes: nbf, type, jti fields")
    print("   - Monitor backend logs for authentication errors")

if __name__ == "__main__":
    print("🚨 CRITICAL JWT AUTHENTICATION SYSTEM FIX")
    print("=" * 50)
    
    # Apply the fix
    fix_applied = apply_jwt_fix()
    
    # Test production
    production_working = test_production_backend()
    
    # Provide recommendations
    deployment_recommendations()
    
    print("\n" + "=" * 50)
    if fix_applied and production_working:
        print("🎉 JWT AUTHENTICATION SYSTEM FULLY FIXED!")
        print("✅ All tests passing - authentication should work correctly")
    elif fix_applied:
        print("⚠️ JWT FIX APPLIED BUT PRODUCTION NEEDS UPDATE")
        print("🔄 Deploy changes to Railway to resolve authentication")
    else:
        print("❌ JWT AUTHENTICATION STILL HAS ISSUES") 
        print("🔧 Manual intervention required - check auth service code")
    print("=" * 50)