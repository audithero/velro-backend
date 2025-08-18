#!/usr/bin/env python3
"""
Comprehensive authentication diagnostic script.
Gathers ALL information about the auth system before attempting fixes.
"""
import os
import sys
import json
import asyncio
import hashlib
import base64
from datetime import datetime
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def print_section(title: str):
    print("\n" + "=" * 80)
    print(f"🔍 {title}")
    print("=" * 80)


def print_result(name: str, value: Any, status: str = "INFO"):
    """Print a diagnostic result."""
    icons = {"INFO": "ℹ️", "OK": "✅", "FAIL": "❌", "WARN": "⚠️"}
    print(f"{icons.get(status, '•')} {name}: {value}")


async def test_environment_variables():
    """Check all auth-related environment variables."""
    print_section("Environment Variables")
    
    required_vars = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_ANON_KEY": os.getenv("SUPABASE_ANON_KEY"),
        "SUPABASE_SERVICE_ROLE_KEY": os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
        "JWT_SECRET": os.getenv("JWT_SECRET"),
        "JWT_ALGORITHM": os.getenv("JWT_ALGORITHM", "HS256"),
    }
    
    results = {}
    for var, value in required_vars.items():
        if value:
            if "KEY" in var or "SECRET" in var:
                # Redact sensitive values
                display = f"{value[:20]}...{value[-10:]}" if len(value) > 30 else "***"
                print_result(var, f"Set ({len(value)} chars) - {display}", "OK")
            else:
                print_result(var, value, "OK")
            results[var] = value
        else:
            print_result(var, "NOT SET", "FAIL")
            results[var] = None
    
    # Decode JWT tokens to check structure
    if results.get("SUPABASE_ANON_KEY"):
        try:
            import jwt
            # Decode without verification to see payload
            anon_payload = jwt.decode(
                results["SUPABASE_ANON_KEY"], 
                options={"verify_signature": False}
            )
            print_result("Anon Key Payload", json.dumps(anon_payload, indent=2), "INFO")
        except Exception as e:
            print_result("Anon Key Decode", str(e), "WARN")
    
    return results


async def test_supabase_connection(env_vars: Dict):
    """Test direct Supabase connection."""
    print_section("Supabase Connection Test")
    
    if not env_vars.get("SUPABASE_URL"):
        print_result("Connection", "Cannot test - SUPABASE_URL not set", "FAIL")
        return None
    
    try:
        from supabase import create_client, Client
        
        # Test with anon key
        anon_client = create_client(
            env_vars["SUPABASE_URL"],
            env_vars["SUPABASE_ANON_KEY"]
        )
        print_result("Anon Client", "Created successfully", "OK")
        
        # Test with service role key
        if env_vars.get("SUPABASE_SERVICE_ROLE_KEY"):
            service_client = create_client(
                env_vars["SUPABASE_URL"],
                env_vars["SUPABASE_SERVICE_ROLE_KEY"]
            )
            print_result("Service Client", "Created successfully", "OK")
            
            # Try to get user count
            try:
                result = service_client.table("users").select("id").execute()
                print_result("Users Table Query", f"{len(result.data)} users found", "OK")
            except Exception as e:
                print_result("Users Table Query", str(e), "FAIL")
            
            return service_client
        
        return anon_client
        
    except Exception as e:
        print_result("Supabase Connection", str(e), "FAIL")
        return None


async def test_specific_user_login(client, email: str = "info@apostle.io"):
    """Test login for a specific user."""
    print_section(f"Testing Login for: {email}")
    
    if not client:
        print_result("Test", "No client available", "FAIL")
        return
    
    # Test various passwords that might work
    test_passwords = [
        "password123",
        "Password123!",
        "demo123456",
        "test123",
        "Temp1234!",
        "apostle123"
    ]
    
    for password in test_passwords:
        try:
            print(f"\n  Testing password: {password}")
            
            # Try Supabase auth
            result = client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            
            if result.user:
                print_result("Login Success", f"User ID: {result.user.id}", "OK")
                print_result("Session", f"Token: {result.session.access_token[:30]}...", "OK")
                return result
            else:
                print_result("Login Failed", "No user returned", "FAIL")
                
        except Exception as e:
            error_msg = str(e)
            if "Invalid login credentials" in error_msg:
                print_result("Password", "Invalid", "FAIL")
            else:
                print_result("Error", error_msg, "FAIL")
    
    print("\n  ❌ No passwords worked")
    return None


async def analyze_auth_service():
    """Analyze the auth service implementation."""
    print_section("Auth Service Analysis")
    
    try:
        from services.auth_service_async import AsyncAuthService
        print_result("Import", "AsyncAuthService imported", "OK")
        
        # Check methods
        auth_service = AsyncAuthService()
        methods = [m for m in dir(auth_service) if not m.startswith('_')]
        print_result("Available Methods", f"{len(methods)} methods", "INFO")
        
        # Check critical methods
        critical_methods = [
            "authenticate_user",
            "create_access_token",
            "verify_token",
            "get_supabase_client"
        ]
        
        for method in critical_methods:
            if hasattr(auth_service, method):
                print_result(f"Method: {method}", "Present", "OK")
            else:
                print_result(f"Method: {method}", "Missing", "FAIL")
        
        # Check Supabase client initialization
        try:
            client = auth_service.supabase
            if client:
                print_result("Supabase Client", "Initialized", "OK")
            else:
                print_result("Supabase Client", "Not initialized", "FAIL")
        except Exception as e:
            print_result("Supabase Client", str(e), "FAIL")
            
    except Exception as e:
        print_result("Auth Service", str(e), "FAIL")


async def trace_login_flow():
    """Trace the exact login flow in the code."""
    print_section("Login Flow Trace")
    
    flow_steps = []
    
    # Step 1: Router endpoint
    try:
        from routers.auth import login
        flow_steps.append("1. routers/auth.py -> login()")
        print_result("Router Import", "Success", "OK")
    except Exception as e:
        print_result("Router Import", str(e), "FAIL")
    
    # Step 2: Auth service
    try:
        from services.auth_service_optimized import get_optimized_async_auth_service
        flow_steps.append("2. services/auth_service_optimized.py -> get_optimized_async_auth_service()")
        print_result("Optimized Service Import", "Success", "OK")
    except:
        try:
            from services.auth_service_async import get_async_auth_service
            flow_steps.append("2. services/auth_service_async.py -> get_async_auth_service()")
            print_result("Async Service Import", "Success", "OK")
        except Exception as e:
            print_result("Service Import", str(e), "FAIL")
    
    # Step 3: Supabase call
    flow_steps.append("3. AsyncAuthService.authenticate_user()")
    flow_steps.append("4. supabase.auth.sign_in_with_password()")
    flow_steps.append("5. JWT token creation")
    flow_steps.append("6. Response with token")
    
    print("\nLogin Flow:")
    for step in flow_steps:
        print(f"  → {step}")


async def compare_jwt_secrets():
    """Compare JWT secrets between Supabase and our config."""
    print_section("JWT Secret Analysis")
    
    jwt_secret = os.getenv("JWT_SECRET")
    
    if not jwt_secret:
        print_result("JWT_SECRET", "Not set in environment", "FAIL")
        return
    
    print_result("JWT_SECRET Length", len(jwt_secret), "INFO")
    print_result("JWT_SECRET Format", "Hexadecimal" if all(c in '0123456789abcdef' for c in jwt_secret.lower()) else "Other", "INFO")
    
    # Check if it matches Supabase format
    supabase_url = os.getenv("SUPABASE_URL")
    if supabase_url:
        project_ref = supabase_url.split('.')[0].split('//')[1]
        print_result("Supabase Project Ref", project_ref, "INFO")
        
        # Supabase typically uses the JWT secret from the dashboard
        print("\n  ⚠️ Verify JWT_SECRET matches Supabase Dashboard:")
        print("     1. Go to Supabase Dashboard")
        print("     2. Settings -> API")
        print("     3. Check 'JWT Secret' under 'Config'")
        print(f"     4. Current value starts with: {jwt_secret[:20]}...")


async def test_minimal_login():
    """Test the absolute minimum login code."""
    print_section("Minimal Login Test")
    
    print("\nTesting with minimal Python code:")
    print("```python")
    print("from supabase import create_client")
    print("client = create_client(url, key)")
    print("result = client.auth.sign_in_with_password({")
    print('    "email": "info@apostle.io",')
    print('    "password": "???"')
    print("})")
    print("```")
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_ANON_KEY")
    
    if not url or not key:
        print_result("Test", "Missing environment variables", "FAIL")
        return
    
    try:
        from supabase import create_client
        client = create_client(url, key)
        
        # Try login with a test password
        result = client.auth.sign_in_with_password({
            "email": "info@apostle.io",
            "password": "password123"
        })
        
        if result.user:
            print_result("Minimal Login", "SUCCESS!", "OK")
            print_result("User ID", result.user.id, "INFO")
        else:
            print_result("Minimal Login", "Failed - invalid credentials", "FAIL")
            
    except Exception as e:
        print_result("Minimal Login", str(e), "FAIL")
        
        # Check the exact error
        if "Invalid login credentials" in str(e):
            print("\n  📝 Password is wrong")
        elif "connection" in str(e).lower():
            print("\n  📝 Connection issue")
        elif "jwt" in str(e).lower():
            print("\n  📝 JWT configuration issue")
        else:
            print(f"\n  📝 Unknown error: {e}")


async def create_comparison_matrix():
    """Create a comparison matrix of all configurations."""
    print_section("Configuration Comparison Matrix")
    
    matrix = []
    
    # Get Supabase keys from environment
    supabase_url = os.getenv("SUPABASE_URL")
    anon_key = os.getenv("SUPABASE_ANON_KEY")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    jwt_secret = os.getenv("JWT_SECRET")
    jwt_algo = os.getenv("JWT_ALGORITHM", "HS256")
    
    # Parse Supabase project reference
    project_ref = supabase_url.split('.')[0].split('//')[1] if supabase_url else "unknown"
    
    print("\n| Config Item | Railway Env | Supabase Expected | Match? |")
    print("|-------------|-------------|-------------------|---------|")
    print(f"| Project Ref | {project_ref} | ltspnsduziplpuqxczvy | {'✅' if project_ref == 'ltspnsduziplpuqxczvy' else '❌'} |")
    print(f"| JWT Algorithm | {jwt_algo} | HS256 | {'✅' if jwt_algo == 'HS256' else '❌'} |")
    print(f"| JWT Secret Length | {len(jwt_secret) if jwt_secret else 0} | 64 (typical) | {'✅' if jwt_secret and len(jwt_secret) == 64 else '⚠️'} |")
    print(f"| Anon Key Set | {'Yes' if anon_key else 'No'} | Yes | {'✅' if anon_key else '❌'} |")
    print(f"| Service Key Set | {'Yes' if service_key else 'No'} | Yes | {'✅' if service_key else '❌'} |")


async def main():
    """Run all diagnostic tests."""
    print("\n" + "🔐 AUTHENTICATION DIAGNOSTIC DEEP DIVE")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Environment: {os.getenv('RAILWAY_ENVIRONMENT', 'local')}")
    
    # Run all diagnostics
    env_vars = await test_environment_variables()
    
    client = await test_supabase_connection(env_vars)
    
    await test_specific_user_login(client)
    
    await analyze_auth_service()
    
    await trace_login_flow()
    
    await compare_jwt_secrets()
    
    await test_minimal_login()
    
    await create_comparison_matrix()
    
    # Final recommendations
    print_section("Recommendations")
    
    print("\n📋 Next Steps:")
    print("1. Verify JWT_SECRET matches Supabase Dashboard exactly")
    print("2. Reset password for info@apostle.io via Supabase Dashboard")
    print("3. Test login via Supabase Dashboard Auth UI")
    print("4. Check if password hashing algorithm matches (bcrypt)")
    print("5. Verify no RLS policies blocking auth.users access")


if __name__ == "__main__":
    asyncio.run(main())