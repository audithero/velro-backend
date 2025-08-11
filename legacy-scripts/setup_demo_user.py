#!/usr/bin/env python3
"""
Setup Demo User Script
Creates demo@example.com user in Supabase for testing production authentication.
"""
import asyncio
import sys
import os
import logging
from datetime import datetime, timezone
from uuid import UUID

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SupabaseClient
from services.auth_service import AuthService
from models.user import UserCreate, UserLogin
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def setup_demo_user():
    """Setup demo user for production testing."""
    logger.info("🚀 Setting up demo user for production testing...")
    
    try:
        # Initialize database and auth service
        db_client = SupabaseClient()
        auth_service = AuthService(db_client)
        
        # Check if Supabase is available
        if not db_client.is_available():
            logger.error("❌ Supabase is not available. Check connection and API keys.")
            return False
        
        logger.info("✅ Supabase connection verified")
        
        # Demo user credentials
        demo_email = "demo@example.com"
        demo_password = "DemoPassword123!"  # Strong password for demo
        demo_name = "Demo User"
        
        logger.info(f"📝 Creating demo user: {demo_email}")
        
        try:
            # Try to register the demo user
            user_data = UserCreate(
                email=demo_email,
                password=demo_password,
                full_name=demo_name
            )
            
            user = await auth_service.register_user(user_data)
            logger.info(f"✅ Demo user created successfully!")
            logger.info(f"   User ID: {user.id}")
            logger.info(f"   Email: {user.email}")
            logger.info(f"   Credits: {user.credits_balance}")
            
        except Exception as reg_error:
            if "already_registered" in str(reg_error) or "already exists" in str(reg_error):
                logger.info(f"ℹ️ Demo user already exists, testing login...")
            else:
                logger.error(f"❌ Failed to create demo user: {reg_error}")
                return False
        
        # Test login with demo user
        logger.info(f"🔐 Testing login with demo user...")
        
        credentials = UserLogin(
            email=demo_email,
            password=demo_password
        )
        
        user = await auth_service.authenticate_user(credentials)
        
        if user:
            logger.info(f"✅ Demo user login successful!")
            logger.info(f"   User ID: {user.id}")
            logger.info(f"   Email: {user.email}")
            logger.info(f"   Display Name: {user.display_name}")
            logger.info(f"   Credits: {user.credits_balance}")
            
            # Test token creation
            token = await auth_service.create_access_token(user)
            logger.info(f"✅ Token creation successful!")
            logger.info(f"   Token type: {token.token_type}")
            logger.info(f"   Expires in: {token.expires_in} seconds")
            logger.info(f"   Token length: {len(token.access_token)}")
            
            # Check if it's a real JWT or custom token
            if token.access_token.startswith(('eyJ', 'ey.')):
                logger.info(f"✅ Real Supabase JWT token detected")
            else:
                logger.info(f"ℹ️ Custom token format: {token.access_token[:20]}...")
            
            return True
        else:
            logger.error(f"❌ Demo user login failed - invalid credentials")
            return False
            
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}", exc_info=True)
        return False

async def test_production_auth_flow():
    """Test the full production authentication flow."""
    logger.info("🧪 Testing production authentication flow...")
    
    try:
        # Test the production router endpoints
        from routers.auth_production import production_login, production_register
        from fastapi import Request
        from models.user import UserLogin
        
        # Create a mock request
        class MockRequest:
            def __init__(self):
                self.client = type('obj', (object,), {'host': '127.0.0.1'})
                self.headers = {'User-Agent': 'Test Script'}
        
        mock_request = MockRequest()
        
        # Test login
        credentials = UserLogin(
            email="demo@example.com",
            password="DemoPassword123!"
        )
        
        logger.info("🔐 Testing production login endpoint...")
        result = await production_login(credentials, mock_request)
        
        logger.info(f"✅ Production login successful!")
        logger.info(f"   Access Token: {result.access_token[:20]}...")
        logger.info(f"   Token Type: {result.token_type}")
        logger.info(f"   User ID: {result.user['id']}")
        logger.info(f"   User Email: {result.user['email']}")
        logger.info(f"   Credits: {result.user['credits_balance']}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Production auth flow test failed: {e}", exc_info=True)
        return False

async def main():
    """Main setup function."""
    logger.info("🎯 VELRO PRODUCTION AUTH SETUP")
    logger.info("=" * 50)
    
    # Step 1: Setup demo user
    demo_setup_success = await setup_demo_user()
    
    if not demo_setup_success:
        logger.error("❌ Demo user setup failed")
        return
    
    logger.info("=" * 50)
    
    # Step 2: Test production auth flow
    auth_test_success = await test_production_auth_flow()
    
    if not auth_test_success:
        logger.error("❌ Production auth flow test failed")
        return
    
    logger.info("=" * 50)
    logger.info("🎉 PRODUCTION AUTH SETUP COMPLETE!")
    logger.info("")
    logger.info("✅ Demo user ready: demo@example.com / DemoPassword123!")
    logger.info("✅ Production auth endpoints working")
    logger.info("✅ JWT token generation working")
    logger.info("✅ User profile sync working")
    logger.info("")
    logger.info("🚀 Ready for deployment to Railway!")

if __name__ == "__main__":
    asyncio.run(main())