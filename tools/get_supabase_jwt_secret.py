#!/usr/bin/env python3
"""
Get the Supabase JWT secret from the Supabase anon key.
Supabase uses a standard JWT secret format.
"""

import os
import base64
import json

# The Supabase JWT secret is typically:
# "your-super-secret-jwt-token-with-at-least-32-characters-long"
# But for the hosted Supabase instances, we need to get it from the dashboard

# For local development, we can use a known secret
# This is from Supabase documentation for local development
DEFAULT_JWT_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"

# Get from environment
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ltspnsduziplpuqxczvy.supabase.co")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx0c3Buc2R1emlwbHB1cXhjenZ5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI2MzM2MTEsImV4cCI6MjA2ODIwOTYxMX0.L1LGSXI1hdSd0I02U3dMcVlL6RHfJmEmuQnb86q9WAw")

print("Supabase Configuration:")
print(f"URL: {SUPABASE_URL}")
print(f"Anon Key: {SUPABASE_ANON_KEY[:20]}...")

# Parse the JWT to understand its structure
if SUPABASE_ANON_KEY:
    parts = SUPABASE_ANON_KEY.split('.')
    if len(parts) >= 2:
        # Decode the payload (add padding if needed)
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += '=' * padding
        
        try:
            decoded = base64.urlsafe_b64decode(payload)
            payload_json = json.loads(decoded)
            print("\nJWT Payload:")
            print(json.dumps(payload_json, indent=2))
            
            # The ref in the payload is the project ID
            project_ref = payload_json.get('ref', '')
            print(f"\nProject Reference: {project_ref}")
            
        except Exception as e:
            print(f"Error decoding JWT: {e}")

print("\n" + "="*60)
print("IMPORTANT: The JWT secret for Supabase cannot be derived from the anon key.")
print("You need to get it from the Supabase Dashboard:")
print("1. Go to https://supabase.com/dashboard")
print("2. Select your project")
print("3. Go to Settings > API")
print("4. Find 'JWT Settings' section")
print("5. Copy the 'JWT Secret' value")
print("="*60)

print("\nFor now, we'll need to use Supabase's authentication API directly")
print("without verifying JWTs locally. The backend will call Supabase to validate.")