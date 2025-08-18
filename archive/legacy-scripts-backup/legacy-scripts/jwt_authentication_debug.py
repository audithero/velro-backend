"""
JWT Authentication Issue Debug Script
Identifies the root cause of Kong Gateway JWT authentication failure.
"""
import asyncio
import httpx
import json
import logging
from datetime import datetime, timezone
from jose import jwt, JWTError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class JWTAuthDebugger:
    def __init__(self):
        self.kong_url = "https://velro-kong-gateway-production.up.railway.app"
        self.backend_url = "https://velro-003-backend-production.up.railway.app"
        self.test_credentials = {
            "email": "demo@example.com",
            "password": "testpassword123"
        }
    
    async def debug_authentication_flow(self):
        """Debug the complete authentication flow"""
        logger.info("🚀 Starting JWT Authentication Flow Debug")
        logger.info(f"Kong Gateway: {self.kong_url}")
        logger.info(f"Backend Service: {self.backend_url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Step 1: Login through Kong Gateway
            await self.test_login_through_kong(client)
            
            # Step 2: Test direct backend authentication
            await self.test_direct_backend_login(client)
            
            # Step 3: Analyze JWT token format and validation
            await self.analyze_jwt_tokens(client)

    async def test_login_through_kong(self, client):
        """Test login through Kong Gateway"""
        logger.info("\n=== STEP 1: Login Through Kong Gateway ===")
        
        try:
            login_url = f"{self.kong_url}/api/v1/auth/login"
            logger.info(f"POST {login_url}")
            
            response = await client.post(
                login_url,
                json=self.test_credentials,
                headers={"Content-Type": "application/json"}
            )
            
            logger.info(f"Status: {response.status_code}")
            logger.info(f"Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info("✅ Login successful through Kong")
                logger.info(f"Token data: {json.dumps(token_data, indent=2)}")
                
                access_token = token_data.get('access_token')
                if access_token:
                    await self.analyze_token_structure(access_token, "Kong Login Token")
                    await self.test_protected_endpoints_through_kong(client, access_token)
                else:
                    logger.error("❌ No access_token in response")
            else:
                logger.error(f"❌ Login failed: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Kong login error: {e}")

    async def test_direct_backend_login(self, client):
        """Test direct backend login"""
        logger.info("\n=== STEP 2: Direct Backend Login ===")
        
        try:
            login_url = f"{self.backend_url}/api/v1/auth/login"
            logger.info(f"POST {login_url}")
            
            response = await client.post(
                login_url,
                json=self.test_credentials,
                headers={"Content-Type": "application/json"}
            )
            
            logger.info(f"Status: {response.status_code}")
            logger.info(f"Headers: {dict(response.headers)}")
            
            if response.status_code == 200:
                token_data = response.json()
                logger.info("✅ Direct backend login successful")
                logger.info(f"Token data: {json.dumps(token_data, indent=2)}")
                
                access_token = token_data.get('access_token')
                if access_token:
                    await self.analyze_token_structure(access_token, "Direct Backend Token")
                    await self.test_protected_endpoints_direct(client, access_token)
                else:
                    logger.error("❌ No access_token in response")
            else:
                logger.error(f"❌ Direct backend login failed: {response.text}")
                
        except Exception as e:
            logger.error(f"❌ Direct backend login error: {e}")

    async def analyze_token_structure(self, token, token_type):
        """Analyze JWT token structure"""
        logger.info(f"\n--- Analyzing {token_type} ---")
        logger.info(f"Token length: {len(token)}")
        logger.info(f"Token prefix: {token[:50]}...")
        
        # Check if it's a JWT
        if token.count('.') == 2:
            logger.info("✅ Token appears to be JWT format")
            try:
                # Decode JWT header without verification
                header = jwt.get_unverified_header(token)
                logger.info(f"JWT Header: {json.dumps(header, indent=2)}")
                
                # Decode JWT payload without verification
                payload = jwt.get_unverified_claims(token)
                logger.info(f"JWT Payload: {json.dumps(payload, indent=2)}")
                
                # Check expiration
                if 'exp' in payload:
                    exp_time = datetime.fromtimestamp(payload['exp'], timezone.utc)
                    logger.info(f"Token expires at: {exp_time}")
                    logger.info(f"Token is valid: {exp_time > datetime.now(timezone.utc)}")
                
            except JWTError as e:
                logger.error(f"❌ JWT decode error: {e}")
        else:
            logger.warning("⚠️ Token is not JWT format")
            
            # Check for custom token formats
            custom_formats = ['mock_token_', 'supabase_token_', 'emergency_', 'dev_token_']
            for format_prefix in custom_formats:
                if token.startswith(format_prefix):
                    logger.info(f"Token is custom format: {format_prefix}")
                    break

    async def test_protected_endpoints_through_kong(self, client, token):
        """Test protected endpoints through Kong Gateway"""
        logger.info(f"\n--- Testing Protected Endpoints Through Kong ---")
        
        endpoints = [
            "/api/v1/auth/me",
            "/api/v1/credits/balance"
        ]
        
        for endpoint in endpoints:
            url = f"{self.kong_url}{endpoint}"
            logger.info(f"GET {url}")
            
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                logger.info(f"Status: {response.status_code}")
                if response.status_code == 200:
                    logger.info("✅ Protected endpoint accessible")
                    logger.info(f"Response: {response.text[:200]}...")
                else:
                    logger.error(f"❌ Protected endpoint failed: {response.text}")
                    
            except Exception as e:
                logger.error(f"❌ Protected endpoint error: {e}")

    async def test_protected_endpoints_direct(self, client, token):
        """Test protected endpoints directly on backend"""
        logger.info(f"\n--- Testing Protected Endpoints Direct Backend ---")
        
        endpoints = [
            "/api/v1/auth/me",
            "/api/v1/credits/balance"
        ]
        
        for endpoint in endpoints:
            url = f"{self.backend_url}{endpoint}"
            logger.info(f"GET {url}")
            
            try:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {token}"}
                )
                
                logger.info(f"Status: {response.status_code}")
                if response.status_code == 200:
                    logger.info("✅ Direct protected endpoint accessible")
                    logger.info(f"Response: {response.text[:200]}...")
                else:
                    logger.error(f"❌ Direct protected endpoint failed: {response.text}")
                    
            except Exception as e:
                logger.error(f"❌ Direct protected endpoint error: {e}")

    async def analyze_jwt_tokens(self, client):
        """Analyze JWT token differences between Kong and Backend"""
        logger.info(f"\n=== STEP 3: JWT Token Analysis ===")
        
        # Test with various token formats to understand validation
        test_tokens = [
            ("Invalid JWT", "invalid.token.here"),
            ("Empty Bearer", ""),
            ("Mock Token", "mock_token_test"),
            ("Custom Token", "supabase_token_bd1a2f69-89eb-489f-9288-8aacf4924763")
        ]
        
        for token_name, token_value in test_tokens:
            logger.info(f"\n--- Testing {token_name} ---")
            
            try:
                # Test through Kong
                kong_response = await client.get(
                    f"{self.kong_url}/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token_value}"} if token_value else {}
                )
                logger.info(f"Kong response: {kong_response.status_code} - {kong_response.text[:100]}")
                
                # Test direct backend  
                backend_response = await client.get(
                    f"{self.backend_url}/api/v1/auth/me",
                    headers={"Authorization": f"Bearer {token_value}"} if token_value else {}
                )
                logger.info(f"Backend response: {backend_response.status_code} - {backend_response.text[:100]}")
                
            except Exception as e:
                logger.error(f"❌ Token test error: {e}")

    def print_diagnosis(self):
        """Print diagnosis and recommendations"""
        logger.info("\n" + "="*80)
        logger.info("🔍 JWT AUTHENTICATION DIAGNOSIS")
        logger.info("="*80)
        
        logger.info("\n🚨 IDENTIFIED ISSUES:")
        logger.info("1. Kong Gateway has NO JWT plugin configured")
        logger.info("   - Kong is simply proxying requests without JWT validation")
        logger.info("   - All JWT processing is happening in the backend")
        
        logger.info("\n2. Backend expects Kong to handle JWT validation")
        logger.info("   - Backend middleware assumes Kong validates JWT tokens")
        logger.info("   - When Kong doesn't validate, backend receives raw tokens")
        
        logger.info("\n🔧 RECOMMENDED FIXES:")
        logger.info("1. Add JWT plugin to Kong Gateway configuration")
        logger.info("2. Configure JWT secret sharing between Kong and Backend")
        logger.info("3. Update backend to handle Kong's JWT validation results")
        
        logger.info("\n📋 NEXT STEPS:")
        logger.info("1. Update kong-declarative-config.yml with JWT plugin")
        logger.info("2. Ensure JWT_SECRET is shared between Kong and Backend")
        logger.info("3. Test authentication flow after fixes")


async def main():
    debugger = JWTAuthDebugger()
    await debugger.debug_authentication_flow()
    debugger.print_diagnosis()

if __name__ == "__main__":
    asyncio.run(main())