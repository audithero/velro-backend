#!/usr/bin/env python3
"""
Debug script to check authentication context when using the anon client.
"""

import os
import sys
import logging
from supabase import create_client

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings

# Test what auth context is available
print("🔍 Testing Auth Context with Anon Client")
print("=" * 50)

anon_client = create_client(settings.supabase_url, settings.supabase_anon_key)

# Try to check auth context
try:
    result = anon_client.rpc('auth_uid').execute()
    print(f"auth.uid(): {result.data}")
except Exception as e:
    print(f"auth.uid() failed: {e}")

try:
    result = anon_client.rpc('auth_role').execute()
    print(f"auth.role(): {result.data}")
except Exception as e:
    print(f"auth.role() failed: {e}")

# Check current_setting for JWT claims
try:
    result = anon_client.rpc('exec_sql', {
        'query': "SELECT current_setting('request.jwt.claims', true) as jwt_claims;"
    }).execute()
    print(f"JWT claims: {result.data}")
except Exception as e:
    print(f"JWT claims check failed: {e}")

# Try inserting with a simpler policy test
print("\n🧪 Testing Simple Insert")
print("=" * 50)

try:
    # Try a simple insert to see what happens
    result = anon_client.table('generations').insert({
        'user_id': '8d089504-4659-4ea3-9b66-9e8734114bef',
        'model_id': 'fal-ai/flux-dev',
        'prompt': 'Simple test insert',
        'status': 'pending',
        'generation_type': 'image'
    }).execute()
    print(f"✅ Insert successful: {result.data}")
except Exception as e:
    print(f"❌ Insert failed: {e}")

print("\n🔧 Current Policies")
print("=" * 50)
print("The current policy should allow:")
print("1. Service role (bypasses RLS)")
print("2. Authenticated users (auth.uid() = user_id)")
print("3. Backend operations (auth.uid() IS NULL)")