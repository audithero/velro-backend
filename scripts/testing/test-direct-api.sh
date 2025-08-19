#!/bin/bash
# Test API directly to confirm credits are returned

echo "=========================================="
echo "🔍 TESTING BACKEND API DIRECTLY"
echo "=========================================="
echo ""

# Test with a new user registration
TIMESTAMP=$(date +%s)
EMAIL="test_credits_${TIMESTAMP}@example.com"

echo "1️⃣ Registering new test user: $EMAIL"
REGISTER_RESPONSE=$(curl -s -X POST "https://velro-backend-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"${EMAIL}\",
    \"password\": \"TestPassword123!\",
    \"full_name\": \"Test User\"
  }")

TOKEN=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -n "$TOKEN" ]; then
  echo "   ✅ Registration successful"
  
  # Extract user data from registration response
  echo ""
  echo "2️⃣ User data from registration:"
  echo "$REGISTER_RESPONSE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
user = data.get('user', {})
print(f'   Email: {user.get(\"email\")}')
print(f'   Credits: {user.get(\"credits_balance\", \"NOT PROVIDED\")}')
print(f'   Plan: {user.get(\"current_plan\", \"NOT PROVIDED\")}')
"
  
  echo ""
  echo "3️⃣ Fetching user profile via /auth/me..."
  ME_RESPONSE=$(curl -s "https://velro-backend-production.up.railway.app/api/v1/auth/me" \
    -H "Authorization: Bearer $TOKEN")
  
  echo "$ME_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'   Email: {data.get(\"email\")}')
    print(f'   Credits: {data.get(\"credits_balance\", \"NOT PROVIDED\")}')
    print(f'   Display Name: {data.get(\"display_name\")}')
    print(f'   Role: {data.get(\"role\")}')
except:
    print('   Error parsing response')
    print(sys.stdin.read())
"

  echo ""
  echo "4️⃣ Fetching credits via /credits/balance..."
  CREDITS_RESPONSE=$(curl -s "https://velro-backend-production.up.railway.app/api/v1/credits/balance" \
    -H "Authorization: Bearer $TOKEN")
  
  echo "   Response: $CREDITS_RESPONSE"
  
else
  echo "   ❌ Registration failed"
  echo "$REGISTER_RESPONSE"
fi

echo ""
echo "=========================================="
echo "✅ TEST COMPLETE"
echo "=========================================="