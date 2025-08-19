#!/bin/bash

# 🚨 EMERGENCY API ENDPOINT TESTING WITH CURL
# Quick validation of critical endpoints

set -e

BASE_URL="https://velro-003-backend-production.up.railway.app"
OUTPUT_FILE="curl_test_results.json"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

echo "🚨 Emergency API Testing with cURL"
echo "=================================="
echo "Base URL: $BASE_URL"
echo "Timestamp: $TIMESTAMP"
echo ""

# Initialize results file
cat > "$OUTPUT_FILE" << EOF
{
  "timestamp": "$TIMESTAMP",
  "base_url": "$BASE_URL",
  "test_results": [
EOF

# Function to test endpoint
test_endpoint() {
    local method="$1"
    local path="$2"
    local auth_header="$3"
    local data="$4"
    local description="$5"
    
    echo "Testing: $method $path"
    
    local url="${BASE_URL}${path}"
    local curl_cmd="curl -s -w \"\\n%{http_code}|%{time_total}\" -X $method"
    
    if [[ -n "$auth_header" ]]; then
        curl_cmd="$curl_cmd -H \"Authorization: $auth_header\""
    fi
    
    if [[ -n "$data" ]]; then
        curl_cmd="$curl_cmd -H \"Content-Type: application/json\" -d '$data'"
    fi
    
    curl_cmd="$curl_cmd \"$url\""
    
    # Execute curl and capture output
    local start_time=$(date +%s.%N)
    local output
    output=$(eval "$curl_cmd" 2>&1) || true
    local end_time=$(date +%s.%N)
    
    # Parse response
    local last_line=$(echo "$output" | tail -n 1)
    local response_body=$(echo "$output" | head -n -1)
    local status_code=$(echo "$last_line" | cut -d'|' -f1)
    local curl_time=$(echo "$last_line" | cut -d'|' -f2)
    
    # Validate status code
    if [[ ! "$status_code" =~ ^[0-9]{3}$ ]]; then
        status_code="ERROR"
        response_body="$output"
    fi
    
    # Escape JSON
    local escaped_response=$(echo "$response_body" | sed 's/"/\\"/g' | tr '\n' ' ')
    
    # Determine status
    local test_status="PASS"
    if [[ "$status_code" == "ERROR" ]] || [[ "$status_code" -ge 400 ]]; then
        test_status="FAIL"
    fi
    
    # Add to results file
    cat >> "$OUTPUT_FILE" << EOF
    {
      "description": "$description",
      "method": "$method",
      "path": "$path",
      "url": "$url",
      "status_code": "$status_code",
      "response_time": "$curl_time",
      "test_status": "$test_status",
      "response_preview": "$escaped_response",
      "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    },
EOF
    
    # Print result
    local status_emoji="✅"
    if [[ "$test_status" == "FAIL" ]]; then
        status_emoji="❌"
    fi
    
    echo "$status_emoji $test_status - $method $path - Status: $status_code, Time: ${curl_time}s"
    
    if [[ "$test_status" == "FAIL" ]]; then
        echo "   Error: $escaped_response"
    fi
    
    echo ""
}

# Test system endpoints (no auth required)
echo "📊 Testing System Endpoints..."
test_endpoint "GET" "/health" "" "" "Health check endpoint"
test_endpoint "GET" "/" "" "" "Root endpoint"
test_endpoint "GET" "/security-status" "" "" "Security status endpoint"

# Test working endpoints (no auth)
echo "✅ Testing Working Endpoints (No Auth)..."
test_endpoint "GET" "/api/v1/generations/models/supported" "" "" "Supported models endpoint"

# Test auth endpoint
echo "🔑 Testing Authentication..."
AUTH_DATA='{"email": "test@example.com", "password": "testpassword123"}'
test_endpoint "POST" "/api/v1/auth/login" "" "$AUTH_DATA" "Login endpoint"

# Test failing endpoints (will fail without auth, but we want to see the error)
echo "❌ Testing Failing Endpoints (No Auth)..."
test_endpoint "GET" "/api/v1/generations/?limit=50" "" "" "List generations endpoint"
test_endpoint "GET" "/api/v1/projects/" "" "" "List projects endpoint"
test_endpoint "POST" "/api/v1/projects/" "" '{"title": "Test Project", "description": "Test"}' "Create project endpoint"
test_endpoint "GET" "/api/v1/credits/stats/?days=30" "" "" "Credit stats endpoint"
test_endpoint "GET" "/api/v1/credits/transactions/?limit=50" "" "" "Credit transactions endpoint"
test_endpoint "GET" "/api/v1/credits/balance/" "" "" "Credit balance endpoint"

# Test HTTP methods on failing endpoints
echo "🔧 Testing HTTP Methods..."
test_endpoint "POST" "/api/v1/projects/" "" '{"title": "Test", "description": "Test"}' "POST projects endpoint"
test_endpoint "GET" "/api/v1/projects/" "" "" "GET projects endpoint"
test_endpoint "PUT" "/api/v1/projects/" "" '{"title": "Test"}' "PUT projects endpoint"
test_endpoint "DELETE" "/api/v1/projects/" "" "" "DELETE projects endpoint"

# Test CORS preflight
echo "🌐 Testing CORS..."
test_endpoint "OPTIONS" "/api/v1/auth/login" "Origin: http://localhost:3000" "" "CORS preflight for auth"
test_endpoint "OPTIONS" "/api/v1/projects/" "Origin: http://localhost:3000" "" "CORS preflight for projects"

# Close JSON file
sed -i '' '$ s/,$//' "$OUTPUT_FILE"  # Remove trailing comma from last entry
cat >> "$OUTPUT_FILE" << EOF
  ],
  "summary": {
    "total_tests": $(grep -c '"method":' "$OUTPUT_FILE"),
    "timestamp_end": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  }
}
EOF

echo "🎯 Testing Complete!"
echo "Results saved to: $OUTPUT_FILE"
echo ""

# Quick summary
echo "📊 QUICK SUMMARY:"
echo "=================="

# Count results
TOTAL_TESTS=$(grep -c '"test_status":' "$OUTPUT_FILE")
PASSED_TESTS=$(grep -c '"test_status": "PASS"' "$OUTPUT_FILE")
FAILED_TESTS=$(grep -c '"test_status": "FAIL"' "$OUTPUT_FILE")

echo "Total Tests: $TOTAL_TESTS"
echo "Passed: $PASSED_TESTS"
echo "Failed: $FAILED_TESTS"

if [[ $FAILED_TESTS -gt 0 ]]; then
    echo ""
    echo "❌ FAILED ENDPOINTS:"
    grep -A 2 -B 2 '"test_status": "FAIL"' "$OUTPUT_FILE" | grep '"path":' | sed 's/.*"path": "\([^"]*\)".*/  \1/'
fi

echo ""
echo "📄 Full results in: $OUTPUT_FILE"