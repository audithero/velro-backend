#!/bin/bash

echo "🧪 Testing Generation Endpoints After Fix"
echo "========================================"

# Test 1: Register a new user
echo ""
echo "1. Testing User Registration..."
REGISTER_RESPONSE=$(curl -s -X POST "https://velro-kong-gateway-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "test-gen-'$(date +%s)'@example.com",
    "password": "TestPass123!",
    "full_name": "Generation Test User"
  }')

echo "Registration Response: $REGISTER_RESPONSE"

# Extract email from registration
EMAIL=$(echo "$REGISTER_RESPONSE" | grep -o '"email":"[^"]*"' | cut -d'"' -f4)
echo "Registered Email: $EMAIL"

# Test 2: Login and get token
echo ""
echo "2. Testing User Login..."
LOGIN_RESPONSE=$(curl -s -X POST "https://velro-kong-gateway-production.up.railway.app/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"TestPass123!\"
  }")

echo "Login Response: $LOGIN_RESPONSE"

# Extract token
TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
echo "Access Token: ${TOKEN:0:50}..."

# Test 3: Test Generation List Endpoint
echo ""
echo "3. Testing Generation List Endpoint (Previously HTTP 503)..."
GENERATIONS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  "https://velro-kong-gateway-production.up.railway.app/api/v1/generations/?limit=10" \
  -H "Authorization: Bearer $TOKEN")

echo "$GENERATIONS_RESPONSE"

# Test 4: Test individual model endpoints through Kong
echo ""
echo "4. Testing AI Model Endpoints through Kong Gateway..."

echo "4a. Testing Flux Pro Ultra endpoint..."
FLUX_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
  "https://velro-kong-gateway-production.up.railway.app/fal/flux-pro-ultra" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -X POST \
  -d '{"prompt": "test generation"}')

echo "$FLUX_RESPONSE"

echo ""
echo "🏁 Generation Endpoints Test Complete!"
echo "======================================"