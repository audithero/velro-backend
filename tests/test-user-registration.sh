#!/bin/bash

echo "🧪 Testing User Registration with Fixed Service Key"
echo "=================================================="

TIMESTAMP=$(date +%s)
EMAIL="testuser${TIMESTAMP}@example.com"

echo "Testing registration for: $EMAIL"

RESPONSE=$(curl -s -X POST "https://velro-kong-gateway-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"TestPass123!\",\"full_name\":\"Test User\"}")

echo "Registration Response:"
echo "$RESPONSE"

# If registration successful, test login
if [[ "$RESPONSE" == *"id"* ]] && [[ "$RESPONSE" != *"error"* ]]; then
    echo ""
    echo "✅ Registration successful! Testing login..."
    
    LOGIN_RESPONSE=$(curl -s -X POST "https://velro-kong-gateway-production.up.railway.app/api/v1/auth/login" \
      -H "Content-Type: application/json" \
      -d "{\"email\":\"${EMAIL}\",\"password\":\"TestPass123!\"}")
    
    echo "Login Response:"
    echo "$LOGIN_RESPONSE"
    
    # Extract token for testing protected endpoints
    TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
    
    if [ ! -z "$TOKEN" ]; then
        echo ""
        echo "✅ Login successful! Testing protected endpoint..."
        echo "Token: ${TOKEN:0:50}..."
        
        CREDITS_RESPONSE=$(curl -s "https://velro-kong-gateway-production.up.railway.app/api/v1/credits/balance" \
          -H "Authorization: Bearer $TOKEN")
        
        echo "Credits Balance Response:"
        echo "$CREDITS_RESPONSE"
    fi
else
    echo ""
    echo "❌ Registration failed. Response indicates error."
fi