#\!/bin/bash

# Colors
GREEN='\\033[0;32m'
RED='\\033[0;31m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

echo "🔐 Testing User Endpoints with Authentication"
echo "=============================================="
echo ""

# Register a new user
TIMESTAMP=$(date +%s)
EMAIL="test_${TIMESTAMP}@example.com"

echo "1️⃣ Registering user: $EMAIL"
REGISTER_RESPONSE=$(curl -s -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${EMAIL}\",
    \"password\": \"TestPassword123\!\",
    \"full_name\": \"Test User\"
  }")

TOKEN=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")

if [ -n "$TOKEN" ]; then
  echo "✅ Registration successful"
  echo ""
  
  echo "2️⃣ Testing /api/v1/user/profile..."
  PROFILE_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" "https://velro-backend-production.up.railway.app/api/v1/user/profile" \
    -H "Authorization: Bearer $TOKEN")
  
  HTTP_STATUS=$(echo "$PROFILE_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
  BODY=$(echo "$PROFILE_RESPONSE" | sed '/HTTP_STATUS:/d')
  
  if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ User profile endpoint working\!"
    echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  else
    echo "❌ User profile failed (HTTP $HTTP_STATUS)"
    echo "$BODY"
  fi
  
  echo ""
  echo "3️⃣ Testing /api/v1/user/credits..."
  CREDITS_RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" "https://velro-backend-production.up.railway.app/api/v1/user/credits" \
    -H "Authorization: Bearer $TOKEN")
  
  HTTP_STATUS=$(echo "$CREDITS_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
  BODY=$(echo "$CREDITS_RESPONSE" | sed '/HTTP_STATUS:/d')
  
  if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ User credits endpoint working\!"
    echo "$BODY" | python3 -m json.tool 2>/dev/null || echo "$BODY"
  else
    echo "❌ User credits failed (HTTP $HTTP_STATUS)"
    echo "$BODY"
  fi
  
  echo ""
  echo "4️⃣ Testing /api/v1/health/config..."
  CONFIG_RESPONSE=$(curl -s "https://velro-backend-production.up.railway.app/api/v1/health/config")
  echo "$CONFIG_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$CONFIG_RESPONSE"
  
else
  echo "❌ Registration failed"
  echo "$REGISTER_RESPONSE"
fi
