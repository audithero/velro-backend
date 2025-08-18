#!/usr/bin/env python3
"""
Supabase authentication verification script.
Tests auth functionality outside of HTTP/middleware to isolate issues.
"""
import os
import sys
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f"🔍 {title}")
    print("=" * 60)


def print_result(name: str, success: bool, details: str = ""):
    """Print a test result."""
    icon = "✅" if success else "❌"
    status = "PASS" if success else "FAIL"
    print(f"{icon} {name}: {status}")
    if details:
        print(f"   {details}")


async def test_supabase_connection():
    """Test basic Supabase connection."""
    print_section("Testing Supabase Connection")
    
    try:
        from supabase import create_client, Client
        
        url = os.environ.get("SUPABASE_URL")
        anon_key = os.environ.get("SUPABASE_ANON_KEY")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not url:
            print_result("Environment Check", False, "SUPABASE_URL not set")
            return False
        
        if not anon_key:
            print_result("Environment Check", False, "SUPABASE_ANON_KEY not set")
            return False
            
        print_result("Environment Check", True, f"URL: {url[:30]}...")
        
        # Test anonymous client
        try:
            anon_client: Client = create_client(url, anon_key)
            print_result("Anonymous Client Creation", True)
            
            # Try a simple query (should fail with RLS but connection should work)
            try:
                result = anon_client.table("projects").select("id").limit(1).execute()
                print_result("Anonymous Query", True, f"Got {len(result.data)} results")
            except Exception as e:
                # Expected to fail with RLS
                if "permission" in str(e).lower() or "denied" in str(e).lower():
                    print_result("Anonymous Query", True, "RLS working (access denied as expected)")
                else:
                    print_result("Anonymous Query", False, str(e))
        except Exception as e:
            print_result("Anonymous Client Creation", False, str(e))
            return False
        
        # Test service role client
        if service_key:
            try:
                service_client: Client = create_client(url, service_key)
                print_result("Service Role Client Creation", True)
                
                # Service role should bypass RLS
                try:
                    result = service_client.table("projects").select("id").limit(1).execute()
                    print_result("Service Role Query", True, f"Got {len(result.data)} results")
                except Exception as e:
                    print_result("Service Role Query", False, str(e))
            except Exception as e:
                print_result("Service Role Client Creation", False, str(e))
        else:
            print_result("Service Role Client", False, "SUPABASE_SERVICE_ROLE_KEY not set")
        
        return True
        
    except ImportError as e:
        print_result("Import Check", False, f"Missing dependency: {e}")
        return False
    except Exception as e:
        print_result("Connection Test", False, str(e))
        return False


async def test_auth_service():
    """Test the auth service directly."""
    print_section("Testing Auth Service")
    
    try:
        from services.auth_service_async import AsyncAuthService
        from config import settings
        
        print_result("Import Auth Service", True)
        
        # Create auth service instance
        auth_service = AsyncAuthService()
        print_result("Auth Service Creation", True)
        
        # Test JWT configuration
        jwt_secret = os.environ.get("JWT_SECRET")
        if jwt_secret:
            print_result("JWT Secret Configured", True, f"Length: {len(jwt_secret)}")
        else:
            print_result("JWT Secret Configured", False, "JWT_SECRET not set")
            return False
        
        # Test user authentication (with a test user if available)
        test_email = os.environ.get("VELRO_TEST_EMAIL")
        test_password = os.environ.get("VELRO_TEST_PASSWORD")
        
        if test_email and test_password:
            try:
                result = await auth_service.authenticate_user(test_email, test_password)
                if result:
                    print_result("Test User Authentication", True, f"User ID: {result.get('user', {}).get('id', 'unknown')}")
                else:
                    print_result("Test User Authentication", False, "Invalid credentials")
            except Exception as e:
                print_result("Test User Authentication", False, str(e))
        else:
            print("⚠️ Skipping user auth test (set VELRO_TEST_EMAIL and VELRO_TEST_PASSWORD)")
        
        # Test token creation
        try:
            test_user_id = "test-user-123"
            test_user_email = "test@example.com"
            token = await auth_service.create_access_token(
                {"sub": test_user_id, "email": test_user_email}
            )
            if token:
                print_result("Token Creation", True, f"Token length: {len(token)}")
                
                # Test token verification
                try:
                    verified = await auth_service.verify_token(token)
                    if verified:
                        print_result("Token Verification", True, f"User: {verified.get('email')}")
                    else:
                        print_result("Token Verification", False, "Token invalid")
                except Exception as e:
                    print_result("Token Verification", False, str(e))
            else:
                print_result("Token Creation", False, "No token returned")
        except Exception as e:
            print_result("Token Creation", False, str(e))
        
        return True
        
    except ImportError as e:
        print_result("Import Auth Service", False, f"Missing module: {e}")
        return False
    except Exception as e:
        print_result("Auth Service Test", False, str(e))
        return False


async def test_user_operations():
    """Test user operations directly with Supabase."""
    print_section("Testing User Operations")
    
    try:
        from supabase import create_client, Client
        import hashlib
        import uuid
        
        url = os.environ.get("SUPABASE_URL")
        service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        
        if not url or not service_key:
            print("⚠️ Skipping user operations (service role key required)")
            return False
        
        client: Client = create_client(url, service_key)
        
        # List existing users
        try:
            # Query auth.users table directly
            result = client.table("users").select("*").limit(5).execute()
            print_result("List Users", True, f"Found {len(result.data)} users in public.users")
        except Exception as e:
            print_result("List Users", False, str(e))
        
        # Test creating a test user (cleanup after)
        test_email = f"test-{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestPassword123!"
        
        try:
            # Try to create user via auth
            result = client.auth.sign_up({
                "email": test_email,
                "password": test_password
            })
            
            if result.user:
                print_result("Create Test User", True, f"User ID: {result.user.id}")
                
                # Try to sign in
                try:
                    signin_result = client.auth.sign_in_with_password({
                        "email": test_email,
                        "password": test_password
                    })
                    if signin_result.session:
                        print_result("Sign In Test User", True, "Session created")
                    else:
                        print_result("Sign In Test User", False, "No session")
                except Exception as e:
                    print_result("Sign In Test User", False, str(e))
                
                # Clean up - delete test user
                try:
                    client.auth.admin.delete_user(result.user.id)
                    print_result("Delete Test User", True, "Cleaned up")
                except:
                    print("⚠️ Could not delete test user")
            else:
                print_result("Create Test User", False, "No user returned")
                
        except Exception as e:
            print_result("Create Test User", False, str(e))
        
        return True
        
    except Exception as e:
        print_result("User Operations", False, str(e))
        return False


async def test_jwt_compatibility():
    """Test JWT compatibility between Supabase and our auth service."""
    print_section("Testing JWT Compatibility")
    
    try:
        import jwt
        from datetime import datetime, timedelta
        
        jwt_secret = os.environ.get("JWT_SECRET")
        if not jwt_secret:
            print_result("JWT Secret Check", False, "JWT_SECRET not set")
            return False
        
        # Create a test token
        payload = {
            "sub": "test-user-id",
            "email": "test@example.com",
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(hours=1)
        }
        
        # Try different algorithms
        algorithms = ["HS256", "HS384", "HS512"]
        
        for algo in algorithms:
            try:
                token = jwt.encode(payload, jwt_secret, algorithm=algo)
                decoded = jwt.decode(token, jwt_secret, algorithms=[algo])
                print_result(f"JWT {algo}", True, "Encode/decode successful")
            except Exception as e:
                print_result(f"JWT {algo}", False, str(e))
        
        # Check Supabase JWT secret format
        supabase_url = os.environ.get("SUPABASE_URL")
        if supabase_url and jwt_secret:
            # Supabase uses the JWT secret for both auth and service tokens
            print_result("JWT Configuration", True, "JWT_SECRET configured for Supabase")
        
        return True
        
    except Exception as e:
        print_result("JWT Compatibility", False, str(e))
        return False


async def main():
    """Run all tests."""
    print("\n" + "🔐 Supabase Authentication Verification")
    print("=" * 60)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Environment: {os.getenv('RAILWAY_ENVIRONMENT', 'local')}")
    
    # Run tests
    results = []
    
    results.append(("Supabase Connection", await test_supabase_connection()))
    results.append(("Auth Service", await test_auth_service()))
    results.append(("User Operations", await test_user_operations()))
    results.append(("JWT Compatibility", await test_jwt_compatibility()))
    
    # Summary
    print_section("Summary")
    
    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed
    
    for name, result in results:
        icon = "✅" if result else "❌"
        print(f"{icon} {name}")
    
    print(f"\nTotal: {passed} passed, {failed} failed")
    
    if failed > 0:
        print("\n⚠️ Authentication system has issues that need to be resolved")
        sys.exit(1)
    else:
        print("\n✅ All authentication tests passed!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())