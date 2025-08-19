#!/usr/bin/env python3
"""
Script to update user credits for production deployment.
Specifically for demo@example.com and any users with insufficient credits.
"""
import asyncio
import os
from database import SupabaseClient
from config import settings

async def update_user_credits():
    """Update demo user and all users to have sufficient credits."""
    
    print("🔧 Starting credit update process...")
    
    # Initialize database client
    db_client = SupabaseClient()
    
    if not db_client.is_available():
        print("❌ Database client not available")
        return False
    
    try:
        # Update demo@example.com user specifically
        demo_email = "demo@example.com"
        print(f"🔍 Looking for user: {demo_email}")
        
        # First check if user exists
        user_check = db_client.service_client.table('users').select('*').eq('email', demo_email).execute()
        
        if user_check.data and len(user_check.data) > 0:
            user_id = user_check.data[0]['id']
            current_credits = user_check.data[0].get('credits', 0)
            
            print(f"✅ Found user {demo_email} with ID {user_id}")
            print(f"📊 Current credits: {current_credits}")
            
            # Update to 1000 credits if less than 1000
            if current_credits < 1000:
                print(f"🔄 Updating credits from {current_credits} to 1000...")
                
                update_result = db_client.service_client.table('users').update({
                    'credits': 1000
                }).eq('id', user_id).execute()
                
                if update_result.data:
                    print(f"✅ Successfully updated {demo_email} to 1000 credits")
                else:
                    print(f"❌ Failed to update {demo_email} credits")
            else:
                print(f"✅ User {demo_email} already has sufficient credits ({current_credits})")
        else:
            print(f"⚠️ User {demo_email} not found in database")
        
        # Update all users with credits < 100 to have 1000
        print("\n🔍 Checking for users with insufficient credits...")
        
        low_credits_users = db_client.service_client.table('users').select('*').lt('credits', 100).execute()
        
        if low_credits_users.data:
            print(f"📊 Found {len(low_credits_users.data)} users with < 100 credits")
            
            for user in low_credits_users.data:
                user_id = user['id']
                current_credits = user.get('credits', 0)
                email = user.get('email', 'unknown')
                
                print(f"🔄 Updating user {email} from {current_credits} to 1000 credits...")
                
                update_result = db_client.service_client.table('users').update({
                    'credits': 1000
                }).eq('id', user_id).execute()
                
                if update_result.data:
                    print(f"✅ Updated user {email}")
                else:
                    print(f"❌ Failed to update user {email}")
        else:
            print("✅ All users have sufficient credits")
        
        # Verify demo user final state
        print(f"\n🔍 Final verification for {demo_email}...")
        final_check = db_client.service_client.table('users').select('*').eq('email', demo_email).execute()
        
        if final_check.data:
            final_credits = final_check.data[0].get('credits', 0)
            print(f"✅ Final credits for {demo_email}: {final_credits}")
        
        print("\n🎉 Credit update process completed successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error updating credits: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(update_user_credits())