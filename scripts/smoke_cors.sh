#!/bin/bash

# CORS & Error Response Smoke Tests
# Tests that all endpoints return proper CORS headers, even on errors

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Base URL - can be overridden by environment variable
BASE_URL="${BASE_URL:-https://velro-backend-production.up.railway.app}"
ORIGIN="https://velro-frontend-production.up.railway.app"

echo "🔍 CORS & Error Response Smoke Tests"
echo "===================================="
echo "Base URL: $BASE_URL"
echo "Origin: $ORIGIN"
echo ""

# Track test results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Function to test an endpoint
test_endpoint() {
    local method="$1"
    local path="$2"
    local expected_status="$3"
    local description="$4"
    local auth_header="$5"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    echo -e "${YELLOW}Test $TOTAL_TESTS:${NC} $description"
    echo "  Method: $method $path"
    echo "  Expected: $expected_status"
    
    # Build curl command
    local curl_cmd="curl -s -i -X $method \"$BASE_URL$path\" -H \"Origin: $ORIGIN\""
    
    if [ ! -z "$auth_header" ]; then
        curl_cmd="$curl_cmd -H \"$auth_header\""
    fi
    
    # Execute request
    local response=$(eval $curl_cmd)
    
    # Extract status code
    local status_code=$(echo "$response" | grep -E "^HTTP" | tail -1 | awk '{print $2}')
    
    # Check for CORS headers
    local cors_origin=$(echo "$response" | grep -i "^access-control-allow-origin:" | cut -d' ' -f2 | tr -d '\r')
    local cors_methods=$(echo "$response" | grep -i "^access-control-allow-methods:" | cut -d' ' -f2- | tr -d '\r')
    local cors_headers=$(echo "$response" | grep -i "^access-control-allow-headers:" | cut -d' ' -f2- | tr -d '\r')
    
    # Validate results
    local test_passed=true
    
    # Check status code
    if [ "$status_code" = "$expected_status" ]; then
        echo -e "  ✅ Status: ${GREEN}$status_code${NC}"
    else
        echo -e "  ❌ Status: ${RED}$status_code (expected $expected_status)${NC}"
        test_passed=false
    fi
    
    # Check CORS headers
    if [ ! -z "$cors_origin" ]; then
        echo -e "  ✅ CORS Origin: ${GREEN}$cors_origin${NC}"
    else
        echo -e "  ❌ CORS Origin: ${RED}MISSING${NC}"
        test_passed=false
    fi
    
    # Update counters
    if [ "$test_passed" = true ]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo -e "  ${GREEN}PASSED${NC}"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo -e "  ${RED}FAILED${NC}"
    fi
    
    echo ""
}

# Test OPTIONS preflight
test_preflight() {
    local path="$1"
    local description="$2"
    
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    
    echo -e "${YELLOW}Test $TOTAL_TESTS:${NC} $description"
    echo "  Method: OPTIONS $path"
    
    local response=$(curl -s -i -X OPTIONS "$BASE_URL$path" \
        -H "Origin: $ORIGIN" \
        -H "Access-Control-Request-Method: GET" \
        -H "Access-Control-Request-Headers: Authorization")
    
    # Extract status code
    local status_code=$(echo "$response" | grep -E "^HTTP" | tail -1 | awk '{print $2}')
    
    # Check for CORS headers
    local cors_origin=$(echo "$response" | grep -i "^access-control-allow-origin:" | cut -d' ' -f2 | tr -d '\r')
    local cors_methods=$(echo "$response" | grep -i "^access-control-allow-methods:" | cut -d' ' -f2- | tr -d '\r')
    local cors_headers=$(echo "$response" | grep -i "^access-control-allow-headers:" | cut -d' ' -f2- | tr -d '\r')
    
    local test_passed=true
    
    # Check status (200 or 204 is acceptable for OPTIONS)
    if [ "$status_code" = "200" ] || [ "$status_code" = "204" ]; then
        echo -e "  ✅ Status: ${GREEN}$status_code${NC}"
    else
        echo -e "  ❌ Status: ${RED}$status_code${NC}"
        test_passed=false
    fi
    
    # Check CORS headers
    if [ ! -z "$cors_origin" ]; then
        echo -e "  ✅ CORS Origin: ${GREEN}$cors_origin${NC}"
    else
        echo -e "  ❌ CORS Origin: ${RED}MISSING${NC}"
        test_passed=false
    fi
    
    if [ ! -z "$cors_methods" ]; then
        echo -e "  ✅ CORS Methods: ${GREEN}Present${NC}"
    else
        echo -e "  ❌ CORS Methods: ${RED}MISSING${NC}"
        test_passed=false
    fi
    
    if [ ! -z "$cors_headers" ]; then
        echo -e "  ✅ CORS Headers: ${GREEN}Present${NC}"
    else
        echo -e "  ❌ CORS Headers: ${RED}MISSING${NC}"
        test_passed=false
    fi
    
    # Update counters
    if [ "$test_passed" = true ]; then
        PASSED_TESTS=$((PASSED_TESTS + 1))
        echo -e "  ${GREEN}PASSED${NC}"
    else
        FAILED_TESTS=$((FAILED_TESTS + 1))
        echo -e "  ${RED}FAILED${NC}"
    fi
    
    echo ""
}

echo "🏓 Testing Ping Endpoints (No Auth)"
echo "------------------------------------"
test_endpoint "GET" "/api/v1/credits/_ping" "200" "Credits ping endpoint" ""
test_endpoint "GET" "/api/v1/projects/_ping" "200" "Projects ping endpoint" ""

echo "🔒 Testing Endpoints Without Auth (Should Return 401 with CORS)"
echo "----------------------------------------------------------------"
test_endpoint "GET" "/api/v1/credits/stats?days=30" "401" "Credits stats without auth" ""
test_endpoint "GET" "/api/v1/credits/transactions?limit=50" "401" "Credits transactions without auth" ""
test_endpoint "GET" "/api/v1/projects?limit=10" "401" "Projects list without auth" ""
test_endpoint "GET" "/api/v1/credits/balance" "401" "Credits balance without auth" ""

echo "🔀 Testing Preflight OPTIONS Requests"
echo "--------------------------------------"
test_preflight "/api/v1/credits/stats" "Credits stats preflight"
test_preflight "/api/v1/projects" "Projects preflight"
test_preflight "/api/v1/generations" "Generations preflight"

echo "🔑 Testing With Invalid JWT (Should Return 401 with CORS)"
echo "----------------------------------------------------------"
INVALID_JWT="Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkludmFsaWQiLCJpYXQiOjE1MTYyMzkwMjJ9.invalid"
test_endpoint "GET" "/api/v1/credits/stats?days=30" "401" "Credits stats with invalid JWT" "Authorization: $INVALID_JWT"
test_endpoint "GET" "/api/v1/projects?limit=10" "401" "Projects with invalid JWT" "Authorization: $INVALID_JWT"

echo "📊 Testing Non-Existent Endpoints (Should Return 404 with CORS)"
echo "---------------------------------------------------------------"
test_endpoint "GET" "/api/v1/nonexistent" "404" "Non-existent endpoint" ""
test_endpoint "POST" "/api/v1/fake/endpoint" "404" "Non-existent POST endpoint" ""

# Summary
echo "======================================"
echo "📊 Test Summary"
echo "======================================"
echo -e "Total Tests: $TOTAL_TESTS"
echo -e "Passed: ${GREEN}$PASSED_TESTS${NC}"
echo -e "Failed: ${RED}$FAILED_TESTS${NC}"

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "\n${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "\n${RED}❌ Some tests failed. Please review the CORS configuration.${NC}"
    exit 1
fi