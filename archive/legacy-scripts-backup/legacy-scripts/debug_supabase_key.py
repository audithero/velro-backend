"""
Quick test of Supabase service key validity - SECURITY HARDENED
SECURITY: All secrets must come from environment variables
"""
import httpx
import asyncio
import os
import sys
import json

async def test_supabase_key():
    # SECURITY: Load from environment variables only
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    # SECURITY: Validate environment variables
    if not SUPABASE_URL:
        print("❌ SECURITY ERROR: SUPABASE_URL environment variable not set")
        sys.exit(1)
        
    if not SERVICE_KEY:
        print("❌ SECURITY ERROR: SUPABASE_SERVICE_ROLE_KEY environment variable not set")
        sys.exit(1)
    
    print("Testing Supabase service key validity...")
    print(f"URL: {SUPABASE_URL}")
    print(f"Key: {SERVICE_KEY[:50]}...")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Test basic API access
            response = await client.get(
                f"{SUPABASE_URL}/rest/v1/users?select=count",
                headers={
                    "apikey": SERVICE_KEY,
                    "Authorization": f"Bearer {SERVICE_KEY}",
                    "Content-Type": "application/json"
                }
            )
            
            print(f"Status Code: {response.status_code}")
            print(f"Response: {response.text}")
            
            if response.status_code == 200:
                print("✅ Service key is VALID")
                return True
            else:
                print("❌ Service key is INVALID")
                try:
                    error_data = response.json()
                    print(f"Error details: {json.dumps(error_data, indent=2)}")
                except:
                    print(f"Raw error: {response.text}")
                return False
                
        except Exception as e:
            print(f"❌ Request failed: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(test_supabase_key())