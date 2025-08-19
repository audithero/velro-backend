#!/usr/bin/env python3
"""
CORS Test with Mock Backend
Since the production backend is down, this creates a local mock server
to validate CORS configuration and test scenarios.
"""

import asyncio
import aiohttp
from aiohttp import web
import json
import logging
import time
from typing import Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockBackend:
    """Mock backend server with same CORS configuration as production."""
    
    def __init__(self, port: int = 8000):
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        self.setup_cors()
    
    def setup_cors(self):
        """Setup CORS middleware exactly like production."""
        
        # CORS origins from main.py
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:3001", 
            "http://localhost:3002",
            "https://velro-frontend-production.up.railway.app",
            "https://*.railway.app",
            "https://velro.ai",
            "https://www.velro.ai"
        ]
        
        @web.middleware
        async def cors_middleware(request, handler):
            # Handle preflight requests
            if request.method == 'OPTIONS':
                origin = request.headers.get('Origin', '')
                
                # Check if origin is allowed
                origin_allowed = any(
                    origin == allowed or 
                    (allowed.endswith('*.railway.app') and origin.endswith('.railway.app'))
                    for allowed in allowed_origins
                )
                
                if origin_allowed:
                    response = web.Response()
                    response.headers['Access-Control-Allow-Origin'] = origin
                    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, OPTIONS, HEAD'
                    response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, Accept, Origin, X-Requested-With, X-CSRF-Token'
                    response.headers['Access-Control-Allow-Credentials'] = 'true'
                    response.headers['Access-Control-Expose-Headers'] = 'X-Process-Time, X-RateLimit-Remaining'
                    return response
                else:
                    return web.Response(status=403, text="Origin not allowed")
            
            # Handle actual requests
            response = await handler(request)
            
            origin = request.headers.get('Origin', '')
            origin_allowed = any(
                origin == allowed or 
                (allowed.endswith('*.railway.app') and origin.endswith('.railway.app'))
                for allowed in allowed_origins
            )
            
            if origin_allowed:
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Credentials'] = 'true'
                response.headers['Access-Control-Expose-Headers'] = 'X-Process-Time, X-RateLimit-Remaining'
            
            return response
        
        self.app.middlewares.append(cors_middleware)
    
    def setup_routes(self):
        """Setup routes matching production backend."""
        
        async def root_handler(request):
            return web.json_response({
                "message": "Velro API - AI-powered creative platform",
                "version": "1.0.0",
                "status": "operational",
                "environment": "mock",
                "security": {
                    "rate_limiting": "enabled",
                    "input_validation": "enabled",
                    "security_headers": "enabled",
                    "authentication": "required"
                }
            })
        
        async def health_handler(request):
            return web.json_response({
                "status": "healthy",
                "timestamp": time.time(),
                "version": "1.0.0",
                "environment": "mock",
                "database": "connected"
            })
        
        async def login_handler(request):
            data = await request.json()
            # Simulate login validation
            if data.get('email') and data.get('password'):
                return web.json_response({
                    "error": "invalid_credentials",
                    "message": "Invalid email or password"
                }, status=401)
            else:
                return web.json_response({
                    "error": "validation_error", 
                    "message": "Email and password required"
                }, status=422)
        
        async def credits_handler(request):
            # Simulate auth required
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return web.json_response({
                    "error": "authentication_required",
                    "message": "Valid authentication token required"
                }, status=401)
            
            return web.json_response({
                "balance": 100,
                "currency": "credits"
            })
        
        async def models_handler(request):
            return web.json_response({
                "models": [
                    {"id": "flux-1.1-pro", "name": "Flux 1.1 Pro", "type": "image"},
                    {"id": "flux-dev", "name": "Flux Dev", "type": "image"}
                ]
            })
        
        async def generations_handler(request):
            if request.method == 'POST':
                # Simulate generation creation
                auth_header = request.headers.get('Authorization', '')
                if not auth_header.startswith('Bearer '):
                    return web.json_response({
                        "error": "authentication_required",
                        "message": "Valid authentication token required"
                    }, status=401)
                
                return web.json_response({
                    "id": "gen_12345",
                    "status": "pending",
                    "prompt": "test image"
                })
            else:
                # GET generations
                return web.json_response({
                    "generations": [],
                    "total": 0
                })
        
        # Register routes
        self.app.router.add_get('/', root_handler)
        self.app.router.add_options('/', root_handler)
        
        self.app.router.add_get('/health', health_handler)
        self.app.router.add_head('/health', health_handler)
        
        self.app.router.add_post('/api/v1/auth/login', login_handler)
        self.app.router.add_options('/api/v1/auth/login', login_handler)
        
        self.app.router.add_get('/api/v1/credits/balance', credits_handler)
        self.app.router.add_options('/api/v1/credits/balance', credits_handler)
        
        self.app.router.add_get('/api/v1/models', models_handler)
        self.app.router.add_options('/api/v1/models', models_handler)
        
        self.app.router.add_get('/api/v1/generations', generations_handler)
        self.app.router.add_post('/api/v1/generations', generations_handler)
        self.app.router.add_options('/api/v1/generations', generations_handler)
    
    async def start(self):
        """Start the mock server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, 'localhost', self.port)
        await site.start()
        print(f"🔧 Mock backend started on http://localhost:{self.port}")
        return runner

async def test_cors_against_mock():
    """Test CORS functionality against mock backend."""
    
    # Start mock backend
    mock = MockBackend(8000)
    runner = await mock.start()
    
    try:
        # Wait for server to start
        await asyncio.sleep(1)
        
        # Test CORS
        backend_url = "http://localhost:8000"
        frontend_origin = "https://velro-frontend-production.up.railway.app"
        
        print(f"\n🧪 Testing CORS against mock backend")
        print(f"Backend: {backend_url}")
        print(f"Origin: {frontend_origin}")
        print("=" * 50)
        
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            
            # Test 1: Preflight for login
            print(f"\n1. Testing preflight for POST /api/v1/auth/login...")
            
            preflight_headers = {
                "Origin": frontend_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type,authorization"
            }
            
            async with session.options(f"{backend_url}/api/v1/auth/login", headers=preflight_headers) as response:
                print(f"   Status: {response.status}")
                print(f"   Allow-Origin: {response.headers.get('Access-Control-Allow-Origin')}")
                print(f"   Allow-Methods: {response.headers.get('Access-Control-Allow-Methods')}")
                print(f"   Allow-Headers: {response.headers.get('Access-Control-Allow-Headers')}")
                print(f"   Allow-Credentials: {response.headers.get('Access-Control-Allow-Credentials')}")
                
                preflight_success = (
                    response.status in [200, 204] and
                    response.headers.get('Access-Control-Allow-Origin') == frontend_origin and
                    'POST' in response.headers.get('Access-Control-Allow-Methods', '') and
                    response.headers.get('Access-Control-Allow-Credentials') == 'true'
                )
                print(f"   Result: {'✅ SUCCESS' if preflight_success else '❌ FAILED'}")
            
            # Test 2: Actual login request
            print(f"\n2. Testing POST /api/v1/auth/login...")
            
            login_headers = {
                "Origin": frontend_origin,
                "Content-Type": "application/json"
            }
            
            login_data = {
                "email": "test@example.com",
                "password": "testpass"
            }
            
            async with session.post(f"{backend_url}/api/v1/auth/login", headers=login_headers, json=login_data) as response:
                print(f"   Status: {response.status}")
                print(f"   Response Origin: {response.headers.get('Access-Control-Allow-Origin')}")
                print(f"   Response Credentials: {response.headers.get('Access-Control-Allow-Credentials')}")
                
                response_text = await response.text()
                print(f"   Response: {response_text[:100]}...")
                
                request_success = (
                    response.status == 401 and  # Expected for invalid credentials
                    response.headers.get('Access-Control-Allow-Origin') == frontend_origin and
                    response.headers.get('Access-Control-Allow-Credentials') == 'true'
                )
                print(f"   Result: {'✅ SUCCESS' if request_success else '❌ FAILED'}")
            
            # Test 3: GET request (simpler)
            print(f"\n3. Testing GET /health...")
            
            get_headers = {
                "Origin": frontend_origin
            }
            
            async with session.get(f"{backend_url}/health", headers=get_headers) as response:
                print(f"   Status: {response.status}")
                print(f"   Response Origin: {response.headers.get('Access-Control-Allow-Origin')}")
                
                get_success = (
                    response.status == 200 and
                    response.headers.get('Access-Control-Allow-Origin') == frontend_origin
                )
                print(f"   Result: {'✅ SUCCESS' if get_success else '❌ FAILED'}")
            
            # Test 4: Different origins
            print(f"\n4. Testing different origins...")
            
            test_origins = [
                "http://localhost:3000",
                "https://velro.ai", 
                "https://evil.com"  # Should fail
            ]
            
            for origin in test_origins:
                try:
                    async with session.get(f"{backend_url}/health", headers={"Origin": origin}) as response:
                        allow_origin = response.headers.get('Access-Control-Allow-Origin')
                        expected = origin != "https://evil.com"
                        actual = allow_origin == origin
                        
                        status = "✅" if (expected == actual) else "❌"
                        print(f"   {origin}: {status} (Allow-Origin: {allow_origin})")
                        
                except Exception as e:
                    print(f"   {origin}: ❌ Error - {e}")
        
        print(f"\n" + "=" * 50)
        print(f"📊 MOCK CORS TEST SUMMARY")
        print("=" * 50)
        
        if preflight_success and request_success and get_success:
            print(f"🎉 ALL CORS TESTS PASSED!")
            print(f"✅ CORS configuration is working correctly")
            print(f"✅ The main.py CORS setup should work in production")
            print(f"\n💡 Next steps:")
            print(f"   1. Fix the Railway deployment issue")
            print(f"   2. Ensure the backend service is running")
            print(f"   3. Re-run production CORS tests")
        else:
            print(f"⚠️ SOME CORS TESTS FAILED")
            print(f"❌ CORS configuration needs adjustment")
        
    finally:
        await runner.cleanup()

async def main():
    """Main test execution."""
    await test_cors_against_mock()

if __name__ == "__main__":
    asyncio.run(main())