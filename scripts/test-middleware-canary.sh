#!/bin/bash

# Middleware Canary Test Script
# Tests critical endpoints to verify middleware stack is working
# Exit code 0 = success, non-zero = failure

set -e  # Exit on first error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Base URL (can be overridden)
BASE_URL="${BASE_URL:-http://localhost:8000}"
ORIGIN="https://velro-frontend-production.up.railway.app"

echo "🔍 Middleware Canary Tests"
echo "=========================="
echo "Base URL: $BASE_URL"
echo "Origin: $ORIGIN"
echo ""

# Track failures
FAILURES=0

# Function to test endpoint
test_endpoint() {
    local method="$1"
    local path="$2"
    local expected_status="$3"
    local description="$4"
    local extra_args="$5"
    
    echo -n "Testing: $description... "
    
    # Make request
    response=$(curl -s -w "\n%{http_code}" -X "$method" \
        -H "Origin: $ORIGIN" \
        $extra_args \
        "$BASE_URL$path" 2>/dev/null || true)
    
    # Extract status code (last line)
    status_code=$(echo "$response" | tail -1)
    
    # Extract CORS header
    cors_header=$(echo "$response" | grep -i "access-control-allow-origin" || true)
    
    # Check status code
    if [ "$status_code" = "$expected_status" ]; then
        # Check for CORS header
        if [ -z "$cors_header" ] && [ "$path" != "/__health" ]; then
            echo -e "${YELLOW}⚠️ Status OK but CORS missing${NC}"
            FAILURES=$((FAILURES + 1))
        else
            echo -e "${GREEN}✅ OK${NC}"
        fi
    else
        echo -e "${RED}❌ FAIL (got $status_code, expected $expected_status)${NC}"
        FAILURES=$((FAILURES + 1))
    fi
}

# Test health endpoint (should always work)
test_endpoint "GET" "/__health" "200" "Health check"

# Test version endpoint
test_endpoint "GET" "/__version" "200" "Version info"

# Test config endpoint
test_endpoint "GET" "/__config" "200" "Config info"

# Test diagnostic endpoints
test_endpoint "GET" "/__diag/request" "200" "Request diagnostics"
test_endpoint "GET" "/__diag/routes" "200" "Routes list"
test_endpoint "GET" "/__diag/middleware" "200" "Middleware status"

# Test ping endpoints (no auth required)
test_endpoint "GET" "/api/v1/credits/_ping" "200" "Credits ping"
test_endpoint "GET" "/api/v1/projects/_ping" "200" "Projects ping"

# Test protected endpoints without auth (should return 401)
test_endpoint "GET" "/api/v1/projects" "401" "Projects list (no auth)"
test_endpoint "GET" "/api/v1/credits/balance" "401" "Credits balance (no auth)"
test_endpoint "GET" "/api/v1/generations" "401" "Generations list (no auth)"

# Test non-existent endpoint (should return 404)
test_endpoint "GET" "/api/v1/nonexistent" "404" "Non-existent endpoint"

# Test OPTIONS preflight
echo -n "Testing: CORS preflight... "
response=$(curl -s -i -X OPTIONS \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: Authorization" \
    "$BASE_URL/api/v1/projects" 2>/dev/null || true)

if echo "$response" | grep -q "access-control-allow-origin"; then
    echo -e "${GREEN}✅ OK${NC}"
else
    echo -e "${RED}❌ FAIL (CORS headers missing)${NC}"
    FAILURES=$((FAILURES + 1))
fi

# Summary
echo ""
echo "=========================="
if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ $FAILURES test(s) failed${NC}"
    exit 1
fi