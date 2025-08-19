#\!/bin/bash

# Generate unique email
TIMESTAMP=$(date +%s)
EMAIL="e2e_test_${TIMESTAMP}@example.com"

echo "=== Testing User Registration through Kong ==="
echo "Email: $EMAIL"
echo ""

# Register user
RESPONSE=$(curl -s -X POST "https://velro-kong-gateway-production.up.railway.app/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"TestPassword123\!\",\"full_name\":\"E2E Test User\"}")

echo "Response:"
echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"

# Check if successful
if echo "$RESPONSE" | grep -q "access_token"; then
  echo ""
  echo "✅ Registration successful"
  TOKEN=$(echo "$RESPONSE" | jq -r '.access_token')
  echo "Token (first 50 chars): ${TOKEN:0:50}..."
else
  echo ""
  echo "❌ Registration failed"
fi
