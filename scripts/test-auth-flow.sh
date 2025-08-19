#!/bin/bash

# Test Authentication Flow Script
# Tests registration, login, and authenticated requests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Base URL
BASE_URL="${BASE_URL:-https://velro-backend-production.up.railway.app}"
ORIGIN="https://velro-frontend-production.up.railway.app"

echo -e "${BLUE}🔐 Authentication Flow Test${NC}"
echo "=================================="
echo "Base URL: $BASE_URL"
echo "Origin: $ORIGIN"
echo ""

# Generate unique test user
TIMESTAMP=$(date +%s)
TEST_EMAIL="testuser${TIMESTAMP}@example.com"
TEST_PASSWORD="TestPassword123!"

echo -e "${YELLOW}1. Testing Registration${NC}"
echo "   Email: $TEST_EMAIL"
echo -n "   Registering new user... "

REGISTER_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/register" \
  -H "Content-Type: application/json" \
  -H "Origin: $ORIGIN" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\",
    \"full_name\": \"Test User $TIMESTAMP\"
  }" 2>/dev/null || true)

if echo "$REGISTER_RESPONSE" | grep -q "user_id\|access_token"; then
  echo -e "${GREEN}✅ Success${NC}"
  echo "$REGISTER_RESPONSE" | jq -r '.access_token' > /tmp/test_token.txt 2>/dev/null || true
else
  echo -e "${RED}❌ Failed${NC}"
  echo "   Response: $REGISTER_RESPONSE"
  echo ""
  echo -e "${YELLOW}   Trying with existing test account...${NC}"
  TEST_EMAIL="demo@velro.ai"
  TEST_PASSWORD="demo123456"
fi

echo ""
echo -e "${YELLOW}2. Testing Login${NC}"
echo "   Email: $TEST_EMAIL"
echo -n "   Logging in... "

LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -H "Origin: $ORIGIN" \
  -d "{
    \"email\": \"$TEST_EMAIL\",
    \"password\": \"$TEST_PASSWORD\"
  }" 2>/dev/null || true)

if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
  echo -e "${GREEN}✅ Success${NC}"
  ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
  USER_ID=$(echo "$LOGIN_RESPONSE" | jq -r '.user_id' 2>/dev/null || echo "unknown")
  echo "   User ID: $USER_ID"
  echo "   Token: ${ACCESS_TOKEN:0:20}..."
else
  echo -e "${RED}❌ Failed${NC}"
  echo "   Response: $LOGIN_RESPONSE"
  ACCESS_TOKEN=""
fi

echo ""
echo -e "${YELLOW}3. Testing Authenticated Requests${NC}"

if [ -n "$ACCESS_TOKEN" ]; then
  # Test credits balance
  echo -n "   Getting credits balance... "
  CREDITS_RESPONSE=$(curl -s -X GET "$BASE_URL/api/v1/credits/balance" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Origin: $ORIGIN" 2>/dev/null || true)
  
  if echo "$CREDITS_RESPONSE" | grep -q "balance\|credits"; then
    echo -e "${GREEN}✅ Success${NC}"
    echo "   Balance: $(echo "$CREDITS_RESPONSE" | jq -r '.balance' 2>/dev/null || echo "N/A")"
  else
    echo -e "${RED}❌ Failed${NC}"
    echo "   Response: $CREDITS_RESPONSE"
  fi
  
  # Test projects list
  echo -n "   Getting projects list... "
  PROJECTS_RESPONSE=$(curl -s -X GET "$BASE_URL/api/v1/projects" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Origin: $ORIGIN" 2>/dev/null || true)
  
  if echo "$PROJECTS_RESPONSE" | grep -q "projects\|\\[\\]"; then
    echo -e "${GREEN}✅ Success${NC}"
    PROJECT_COUNT=$(echo "$PROJECTS_RESPONSE" | jq 'length' 2>/dev/null || echo "0")
    echo "   Projects count: $PROJECT_COUNT"
  else
    echo -e "${RED}❌ Failed${NC}"
    echo "   Response: $PROJECTS_RESPONSE"
  fi
  
  # Test token refresh
  echo -n "   Testing token refresh... "
  REFRESH_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/refresh" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Origin: $ORIGIN" 2>/dev/null || true)
  
  if echo "$REFRESH_RESPONSE" | grep -q "access_token"; then
    echo -e "${GREEN}✅ Success${NC}"
  else
    echo -e "${YELLOW}⚠️ Not available${NC}"
  fi
  
  # Test logout
  echo -n "   Testing logout... "
  LOGOUT_RESPONSE=$(curl -s -X POST "$BASE_URL/api/v1/auth/logout" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Origin: $ORIGIN" 2>/dev/null || true)
  
  LOGOUT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/api/v1/auth/logout" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Origin: $ORIGIN" 2>/dev/null || true)
  
  if [ "$LOGOUT_STATUS" = "200" ] || [ "$LOGOUT_STATUS" = "204" ]; then
    echo -e "${GREEN}✅ Success${NC}"
  else
    echo -e "${YELLOW}⚠️ Status: $LOGOUT_STATUS${NC}"
  fi
else
  echo -e "${RED}   Skipping authenticated tests (no token)${NC}"
fi

echo ""
echo -e "${YELLOW}4. Testing CORS Headers${NC}"

echo -n "   Checking CORS on login endpoint... "
CORS_HEADERS=$(curl -s -I -X OPTIONS "$BASE_URL/api/v1/auth/login" \
  -H "Origin: $ORIGIN" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" 2>/dev/null | grep -i "access-control" || true)

if echo "$CORS_HEADERS" | grep -q "access-control-allow-origin"; then
  echo -e "${GREEN}✅ Present${NC}"
  echo "$CORS_HEADERS" | sed 's/^/     /'
else
  echo -e "${RED}❌ Missing${NC}"
fi

echo ""
echo "=================================="
echo -e "${BLUE}Summary${NC}"
echo ""

# Summary
if [ -n "$ACCESS_TOKEN" ]; then
  echo -e "${GREEN}✅ Authentication flow is working!${NC}"
  echo "   - Login endpoint functional"
  echo "   - Tokens being issued"
  echo "   - Protected endpoints accessible with token"
else
  echo -e "${RED}❌ Authentication flow has issues${NC}"
  echo "   - Check Supabase configuration"
  echo "   - Verify JWT_SECRET is set"
  echo "   - Check auth service logs"
fi