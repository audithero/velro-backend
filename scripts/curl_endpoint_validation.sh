#!/bin/bash

# Comprehensive cURL-based Endpoint Validation Script
# ====================================================
# This script tests all backend endpoints using cURL to validate the API
# and identify specific issues with the production deployment.

BASE_URL="https://velro-003-backend-production.up.railway.app"
TEST_EMAIL="test@apostle.digital"
TEST_PASSWORD="TestPassword123!"
OUTPUT_FILE="curl_test_results_$(date +%s).json"

echo "🚀 Starting Comprehensive cURL Endpoint Validation"
echo "Target: $BASE_URL"
echo "Test User: $TEST_EMAIL"
echo "Output: $OUTPUT_FILE"
echo "=============================================="

# Initialize results file
echo "{" > $OUTPUT_FILE
echo "  \"test_run\": {" >> $OUTPUT_FILE
echo "    \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"," >> $OUTPUT_FILE
echo "    \"base_url\": \"$BASE_URL\"," >> $OUTPUT_FILE
echo "    \"test_user\": \"$TEST_EMAIL\"" >> $OUTPUT_FILE
echo "  }," >> $OUTPUT_FILE
echo "  \"results\": [" >> $OUTPUT_FILE

# Function to test endpoint and log result
test_endpoint() {
    local method="$1"
    local path="$2"
    local auth_header="$3"
    local data="$4"
    local description="$5"
    
    echo "Testing $method $path - $description"
    
    local start_time=$(date +%s.%N)
    
    # Build curl command
    local curl_cmd="curl -s -w '%{http_code}|%{time_total}|%{size_download}' -X $method"
    
    if [ ! -z "$auth_header" ]; then
        curl_cmd="$curl_cmd -H 'Authorization: Bearer $auth_header'"
    fi
    
    curl_cmd="$curl_cmd -H 'Content-Type: application/json'"
    curl_cmd="$curl_cmd -H 'Accept: application/json'"
    
    if [ ! -z "$data" ]; then
        curl_cmd="$curl_cmd -d '$data'"
    fi
    
    curl_cmd="$curl_cmd '$BASE_URL$path'"
    
    # Execute request
    local response=$(eval $curl_cmd)
    local exit_code=$?
    
    # Parse response
    local http_code=$(echo "$response" | tail -c 50 | grep -o '[0-9]\{3\}|[0-9.]*|[0-9]*' | cut -d'|' -f1)
    local time_total=$(echo "$response" | tail -c 50 | grep -o '[0-9]\{3\}|[0-9.]*|[0-9]*' | cut -d'|' -f2)
    local size_download=$(echo "$response" | tail -c 50 | grep -o '[0-9]\{3\}|[0-9.]*|[0-9]*' | cut -d'|' -f3)
    local response_body=$(echo "$response" | sed 's/[0-9]\{3\}|[0-9.]*|[0-9]*$//')
    
    # Determine success
    local success="false"
    if [ "$http_code" -ge 200 ] && [ "$http_code" -lt 400 ]; then
        success="true"
        echo "  ✅ $http_code (${time_total}s)"
    else
        echo "  ❌ $http_code (${time_total}s)"
    fi
    
    # Log to JSON file
    cat >> $OUTPUT_FILE << EOF
    {
      "endpoint": "$path",
      "method": "$method",
      "description": "$description",
      "status_code": $http_code,
      "response_time": $time_total,
      "response_size": $size_download,
      "success": $success,
      "response_body": $(echo "$response_body" | jq -R . 2>/dev/null || echo "\"$response_body\""),
      "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    },
EOF
    
    # Return token if this is login
    if [ "$path" = "/api/v1/auth/login" ] && [ "$success" = "true" ]; then
        echo "$response_body" | jq -r '.access_token' 2>/dev/null
    fi
}

# Test system endpoints
echo ""
echo "🔍 Testing System Endpoints"
echo "============================"
test_endpoint "GET" "/" "" "" "Root endpoint"
test_endpoint "GET" "/health" "" "" "Health check"
test_endpoint "GET" "/security-status" "" "" "Security status"
test_endpoint "GET" "/cors-test" "" "" "CORS test"
test_endpoint "GET" "/performance-metrics" "" "" "Performance metrics"

# Test authentication
echo ""
echo "🔐 Testing Authentication"
echo "=========================="
login_data="{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}"
ACCESS_TOKEN=$(test_endpoint "POST" "/api/v1/auth/login" "" "$login_data" "User login")

if [ ! -z "$ACCESS_TOKEN" ] && [ "$ACCESS_TOKEN" != "null" ]; then
    echo "  🔑 Access token obtained: ${ACCESS_TOKEN:0:20}..."
    
    # Test authenticated endpoints
    test_endpoint "GET" "/api/v1/auth/me" "$ACCESS_TOKEN" "" "Get current user"
    test_endpoint "GET" "/api/v1/auth/debug-auth" "$ACCESS_TOKEN" "" "Debug auth middleware"
else
    echo "  ❌ Failed to obtain access token - skipping authenticated tests"
    ACCESS_TOKEN=""
fi

# Test credits endpoints (investigating 405 errors)
echo ""
echo "💰 Testing Credits Endpoints (Investigating 405 Errors)"
echo "========================================================"
test_endpoint "GET" "/api/v1/credits/balance/" "$ACCESS_TOKEN" "" "Get credits balance"
test_endpoint "GET" "/api/v1/credits/transactions/" "$ACCESS_TOKEN" "" "List transactions"
test_endpoint "GET" "/api/v1/credits/stats/" "$ACCESS_TOKEN" "" "Get usage stats"

# Test projects endpoints (investigating 405 errors)
echo ""
echo "📁 Testing Projects Endpoints (Investigating 405 Errors)"
echo "========================================================="
test_endpoint "GET" "/api/v1/projects/" "$ACCESS_TOKEN" "" "List projects"

# Create test project
project_data="{\"title\":\"Test Project\",\"description\":\"Endpoint validation test project\",\"visibility\":\"private\"}"
test_endpoint "POST" "/api/v1/projects/" "$ACCESS_TOKEN" "$project_data" "Create project"

# Test generations endpoints (investigating 500 errors)
echo ""
echo "🎨 Testing Generations Endpoints (Investigating 500 Errors)"
echo "==========================================================="
test_endpoint "GET" "/api/v1/generations/" "$ACCESS_TOKEN" "" "List generations"
test_endpoint "GET" "/api/v1/generations/stats" "$ACCESS_TOKEN" "" "Get generation stats"
test_endpoint "GET" "/api/v1/generations/models/supported" "" "" "Get supported models"

# Test specific error conditions
echo ""
echo "🚨 Testing Error Conditions"
echo "============================"
test_endpoint "GET" "/api/v1/credits/balance/" "" "" "Credits balance without auth (expect 401)"
test_endpoint "GET" "/api/v1/projects/" "" "" "Projects without auth (expect 401)"
test_endpoint "GET" "/api/v1/generations/" "" "" "Generations without auth (expect 401)"

# Test non-existent endpoints
echo ""
echo "🔍 Testing Non-existent Endpoints"
echo "=================================="
test_endpoint "GET" "/api/v1/nonexistent" "$ACCESS_TOKEN" "" "Non-existent endpoint"
test_endpoint "GET" "/api/v2/test" "" "" "Non-existent API version"

# Close JSON file
sed -i '' '$ s/,$//' $OUTPUT_FILE  # Remove last comma
echo "  ]" >> $OUTPUT_FILE
echo "}" >> $OUTPUT_FILE

echo ""
echo "🎯 Test Results Summary"
echo "======================="

# Analyze results
total_tests=$(cat $OUTPUT_FILE | jq '.results | length')
successful_tests=$(cat $OUTPUT_FILE | jq '[.results[] | select(.success == true)] | length')
failed_tests=$(cat $OUTPUT_FILE | jq '[.results[] | select(.success == false)] | length')

echo "Total tests: $total_tests"
echo "Successful: $successful_tests"
echo "Failed: $failed_tests"

if [ "$failed_tests" -gt 0 ]; then
    echo ""
    echo "❌ Failed Tests:"
    cat $OUTPUT_FILE | jq -r '.results[] | select(.success == false) | "  • \(.method) \(.endpoint): \(.status_code) - \(.description)"'
fi

# Check for specific issues
echo ""
echo "🔍 Issue Analysis:"

# Check for 405 errors
method_not_allowed=$(cat $OUTPUT_FILE | jq '[.results[] | select(.status_code == 405)] | length')
if [ "$method_not_allowed" -gt 0 ]; then
    echo "  🚨 $method_not_allowed endpoints returning 405 Method Not Allowed"
    cat $OUTPUT_FILE | jq -r '.results[] | select(.status_code == 405) | "    - \(.method) \(.endpoint)"'
fi

# Check for 500 errors
server_errors=$(cat $OUTPUT_FILE | jq '[.results[] | select(.status_code == 500)] | length')
if [ "$server_errors" -gt 0 ]; then
    echo "  🚨 $server_errors endpoints returning 500 Internal Server Error"
    cat $OUTPUT_FILE | jq -r '.results[] | select(.status_code == 500) | "    - \(.method) \(.endpoint)"'
fi

# Check credits balance
credits_balance=$(cat $OUTPUT_FILE | jq -r '.results[] | select(.endpoint == "/api/v1/credits/balance/" and .success == true) | .response_body | fromjson | .balance // "unknown"')
if [ "$credits_balance" = "100" ]; then
    echo "  ⚠️ Credits balance is 100 (expected 1400)"
elif [ "$credits_balance" != "unknown" ] && [ "$credits_balance" != "null" ]; then
    echo "  ✅ Credits balance: $credits_balance"
fi

echo ""
echo "📊 Detailed results saved to: $OUTPUT_FILE"
echo "=============================================="

# Exit with error code if tests failed
if [ "$failed_tests" -gt 0 ]; then
    exit 1
else
    exit 0
fi