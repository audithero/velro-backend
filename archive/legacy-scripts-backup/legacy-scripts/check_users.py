#!/usr/bin/env python3
"""
Check Users Script
Lists existing users in Supabase and tries common demo passwords.
"""
import asyncio
import sys
import os
import logging

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SupabaseClient
from models.user import UserLogin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def check_existing_users():
    """Check what users exist in the database."""
    logger.info("👥 Checking existing users...")
    
    try:
        db_client = SupabaseClient()
        
        # Check users in custom database
        try:
            result = db_client.service_client.table('users').select('id, email, display_name, credits_balance, created_at').execute()
            
            if result.data:
                logger.info(f"✅ Found {len(result.data)} users in custom database:")
                for user in result.data:
                    logger.info(f"   ID: {user['id']}")
                    logger.info(f"   Email: {user.get('email', 'N/A')}")
                    logger.info(f"   Display Name: {user.get('display_name', 'N/A')}")
                    logger.info(f"   Credits: {user.get('credits_balance', 0)}")
                    logger.info(f"   Created: {user.get('created_at', 'N/A')}")
                    logger.info("")
            else:
                logger.info("ℹ️ No users found in custom database")
                
        except Exception as db_error:
            logger.error(f"❌ Failed to query custom database: {db_error}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to check users: {e}")
        return False

async def try_common_passwords():
    """Try common demo passwords for demo@example.com."""
    logger.info("🔐 Trying common demo passwords...")
    
    demo_email = "demo@example.com"
    common_passwords = [
        "password",
        "password123",
        "demo123",
        "demo",
        "DemoPassword123!",
        "Password123!",
        "test123",
        "123456"
    ]
    
    db_client = SupabaseClient()
    
    for password in common_passwords:
        try:
            logger.info(f"🔍 Trying password: {password}")
            
            response = db_client.client.auth.sign_in_with_password({
                "email": demo_email,
                "password": password
            })
            
            if response.user and response.session:
                logger.info(f"✅ SUCCESS! Password found: {password}")
                logger.info(f"   User ID: {response.user.id}")
                logger.info(f"   Email: {response.user.email}")
                logger.info(f"   Token: {response.session.access_token[:30]}...")
                return password
                
        except Exception as e:
            if "Invalid login credentials" in str(e):
                logger.info(f"❌ Wrong password: {password}")
            else:
                logger.error(f"❌ Error with password {password}: {e}")
    
    logger.warning("⚠️ No common password worked")
    return None

async def create_new_demo_user():
    """Create a new demo user with a known password."""
    logger.info("📝 Creating new demo user...")
    
    # Use a unique email that doesn't exist
    demo_email = f"demo+{int(asyncio.get_event_loop().time())}@example.com"
    demo_password = "DemoPassword123!"
    
    try:
        db_client = SupabaseClient()
        
        response = db_client.client.auth.sign_up({
            "email": demo_email,
            "password": demo_password
        })
        
        if response.user:
            logger.info(f"✅ New demo user created!")
            logger.info(f"   Email: {demo_email}")
            logger.info(f"   Password: {demo_password}")
            logger.info(f"   User ID: {response.user.id}")
            
            # Test login immediately
            login_response = db_client.client.auth.sign_in_with_password({
                "email": demo_email,
                "password": demo_password
            })
            
            if login_response.user and login_response.session:
                logger.info(f"✅ Login test successful!")
                logger.info(f"   Token: {login_response.session.access_token[:30]}...")
                return demo_email, demo_password
            
        return None, None
        
    except Exception as e:
        logger.error(f"❌ Failed to create new demo user: {e}")
        return None, None

async def main():
    """Main function."""
    logger.info("🎯 USER MANAGEMENT DIAGNOSTIC")
    logger.info("=" * 50)
    
    # Step 1: Check existing users
    await check_existing_users()
    
    logger.info("=" * 50)
    
    # Step 2: Try common passwords
    working_password = await try_common_passwords()
    
    if working_password:
        logger.info("=" * 50)
        logger.info("🎉 DEMO CREDENTIALS FOUND!")
        logger.info(f"   Email: demo@example.com")
        logger.info(f"   Password: {working_password}")
    else:
        logger.info("=" * 50)
        
        # Step 3: Create new demo user
        new_email, new_password = await create_new_demo_user()
        
        if new_email:
            logger.info("🎉 NEW DEMO USER CREATED!")
            logger.info(f"   Email: {new_email}")
            logger.info(f"   Password: {new_password}")
        else:
            logger.error("❌ Could not create demo user")

if __name__ == "__main__":
    asyncio.run(main())