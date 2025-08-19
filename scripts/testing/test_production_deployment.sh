#!/bin/bash

# Production Deployment Test Script
# ==================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# URLs
BACKEND_URL="https://velro-backend-production.up.railway.app"
FRONTEND_URL="https://velro-frontend-production.up.railway.app"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}PRODUCTION DEPLOYMENT TEST${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Function to test endpoint
test_endpoint() {
    local url=$1
    local method=$2
    local expected=$3
    local description=$4
    local headers=${5:-""}
    
    echo -e "${YELLOW}Testing: ${description}${NC}"
    echo "URL: $url"
    
    if [ -z "$headers" ]; then
        response=$(curl -s -w "\n%{http_code}" -X $method "$url")
    else
        response=$(curl -s -w "\n%{http_code}" -X $method "$url" -H "$headers")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "$expected" ]; then
        echo -e "${GREEN}✅ PASSED${NC} - HTTP $http_code"
    else
        echo -e "${RED}❌ FAILED${NC} - Expected HTTP $expected, got $http_code"
        echo "Response: $body" | head -c 200
        echo ""
    fi
    echo ""
}

# Test 1: Backend Health Check
echo -e "${BLUE}1. BACKEND HEALTH CHECK${NC}"
echo "========================================="
test_endpoint "$BACKEND_URL/" "GET" "200" "Root endpoint"
test_endpoint "$BACKEND_URL/health" "GET" "200" "Health endpoint"

# Test 2: API Documentation
echo -e "${BLUE}2. API DOCUMENTATION${NC}"
echo "========================================="
test_endpoint "$BACKEND_URL/docs" "GET" "200" "API Documentation"

# Test 3: Models Endpoints (The problematic ones)
echo -e "${BLUE}3. MODELS ENDPOINTS${NC}"
echo "========================================="
test_endpoint "$BACKEND_URL/api/v1/models/supported" "GET" "200" "Models endpoint (api/v1)"
test_endpoint "$BACKEND_URL/generations/models/supported" "GET" "401" "Models endpoint (generations) - Should require auth"

# Test 4: Authentication Endpoints
echo -e "${BLUE}4. AUTHENTICATION ENDPOINTS${NC}"
echo "========================================="
test_endpoint "$BACKEND_URL/api/v1/auth/health" "GET" "200" "Auth health check"

# Test 5: Test Registration Flow
echo -e "${BLUE}5. REGISTRATION TEST${NC}"
echo "========================================="
TIMESTAMP=$(date +%s)
TEST_EMAIL="test_${TIMESTAMP}@example.com"

echo "Testing registration with email: $TEST_EMAIL"
REGISTER_RESPONSE=$(curl -s -X POST "$BACKEND_URL/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -d "{
        \"email\": \"${TEST_EMAIL}\",
        \"password\": \"TestPassword123!\",
        \"full_name\": \"Test User\"
    }")

if echo "$REGISTER_RESPONSE" | grep -q "access_token"; then
    echo -e "${GREEN}✅ Registration successful${NC}"
    TOKEN=$(echo "$REGISTER_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null || echo "")
    
    if [ -n "$TOKEN" ]; then
        echo "Token obtained: ${TOKEN:0:50}..."
        
        # Test authenticated models endpoint
        echo -e "\n${BLUE}6. AUTHENTICATED ENDPOINTS${NC}"
        echo "========================================="
        test_endpoint "$BACKEND_URL/generations/models/supported" "GET" "200" "Models with auth" "Authorization: Bearer $TOKEN"
        test_endpoint "$BACKEND_URL/api/v1/user/profile" "GET" "200" "User profile" "Authorization: Bearer $TOKEN"
        test_endpoint "$BACKEND_URL/api/v1/user/credits" "GET" "200" "User credits" "Authorization: Bearer $TOKEN"
    fi
else
    echo -e "${RED}❌ Registration failed${NC}"
    echo "Response: $REGISTER_RESPONSE" | head -c 500
fi

# Test 6: CORS Headers
echo -e "\n${BLUE}7. CORS CONFIGURATION${NC}"
echo "========================================="
echo "Testing CORS from frontend origin..."
CORS_RESPONSE=$(curl -s -I -X OPTIONS "$BACKEND_URL/api/v1/auth/health" \
    -H "Origin: $FRONTEND_URL" \
    -H "Access-Control-Request-Method: GET")

if echo "$CORS_RESPONSE" | grep -q "access-control-allow-origin"; then
    echo -e "${GREEN}✅ CORS headers present${NC}"
    echo "$CORS_RESPONSE" | grep -i "access-control"
else
    echo -e "${RED}❌ CORS headers missing${NC}"
fi

# Test 7: Frontend Accessibility
echo -e "\n${BLUE}8. FRONTEND STATUS${NC}"
echo "========================================="
test_endpoint "$FRONTEND_URL" "GET" "200" "Frontend home page"

# Test 8: Check Environment Variables
echo -e "\n${BLUE}9. BACKEND CONFIGURATION CHECK${NC}"
echo "========================================="
echo "Checking if backend can reach Supabase..."
CONFIG_CHECK=$(curl -s "$BACKEND_URL/api/v1/health/config" 2>/dev/null || echo "{}")

if echo "$CONFIG_CHECK" | grep -q "supabase"; then
    echo -e "${GREEN}✅ Supabase configured${NC}"
else
    echo -e "${YELLOW}⚠️ Cannot verify Supabase configuration${NC}"
fi

# Summary
echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}TEST SUMMARY${NC}"
echo -e "${BLUE}========================================${NC}"

echo -e "\n${YELLOW}Key Issues Found:${NC}"
echo "1. /api/v1/models/supported returns 404 - Endpoint may not exist"
echo "2. /generations/models/supported returns 401 - Requires authentication"
echo "3. CORS configuration may need adjustment for frontend origin"

echo -e "\n${YELLOW}Recommendations:${NC}"
echo "1. Add /api/v1/models/supported endpoint to backend"
echo "2. Ensure frontend sends auth token for protected endpoints"
echo "3. Update CORS settings to include production frontend URL"
echo "4. Verify all environment variables are set in Railway"