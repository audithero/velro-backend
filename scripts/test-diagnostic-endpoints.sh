#!/bin/bash

# Test diagnostic endpoints
# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

BASE_URL="${BASE_URL:-https://velro-backend-production.up.railway.app}"

echo "🔍 Testing Diagnostic Endpoints"
echo "================================"
echo "Base URL: $BASE_URL"
echo ""

# Test basic ping
echo -e "${YELLOW}Test 1: Basic ping${NC}"
curl -s "$BASE_URL/__diag/ping" | jq '.' || echo "Failed"
echo ""

# Test credits ping
echo -e "${YELLOW}Test 2: Credits ping (no auth)${NC}"
curl -s "$BASE_URL/api/v1/credits/_ping" | jq '.' || echo "Failed"
echo ""

# Test projects ping  
echo -e "${YELLOW}Test 3: Projects ping (no auth)${NC}"
curl -s "$BASE_URL/api/v1/projects/_ping" | jq '.' || echo "Failed"
echo ""

# Test protected endpoint without auth (should return 401)
echo -e "${YELLOW}Test 4: Credits stats without auth (should be 401)${NC}"
curl -s -w "\nHTTP Status: %{http_code}\n" "$BASE_URL/api/v1/credits/stats?days=30" | tail -1
echo ""

echo -e "${YELLOW}Test 5: Projects list without auth (should be 401)${NC}"
curl -s -w "\nHTTP Status: %{http_code}\n" "$BASE_URL/api/v1/projects" | tail -1
echo ""

# Test non-existent endpoint (should be 404)
echo -e "${YELLOW}Test 6: Non-existent endpoint (should be 404)${NC}"
curl -s -w "\nHTTP Status: %{http_code}\n" "$BASE_URL/api/v1/doesnotexist" | tail -1
echo ""

# Test CORS headers
echo -e "${YELLOW}Test 7: CORS headers on error${NC}"
response=$(curl -s -i -H "Origin: https://velro.ai" "$BASE_URL/api/v1/credits/stats")
cors_header=$(echo "$response" | grep -i "access-control-allow-origin" | head -1)
if [ ! -z "$cors_header" ]; then
    echo -e "${GREEN}✅ CORS header present: $cors_header${NC}"
else
    echo -e "${RED}❌ CORS header missing${NC}"
fi
echo ""

# Test diagnostic endpoints if available
echo -e "${YELLOW}Test 8: Diagnostic request info${NC}"
curl -s "$BASE_URL/api/v1/diagnostic/request-info" 2>/dev/null | jq '.' 2>/dev/null || echo "Diagnostic endpoint not available"
echo ""

echo "================================"
echo "✅ Test complete"