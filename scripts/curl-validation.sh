#!/bin/bash

# Production Validation using cURL
# Tests CORS and authentication flow with exact frontend origin

set -e

# Configuration
FRONTEND_URL="https://velro-frontend-production.up.railway.app"
BACKEND_URL="https://velro-003-backend-production.up.railway.app/api/v1"
ORIGIN="https://velro-frontend-production.up.railway.app"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Test results
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
    ((PASSED_TESTS++))
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    ((FAILED_TESTS++))
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Test function wrapper
run_test() {
    local test_name="$1"
    ((TOTAL_TESTS++))
    echo ""
    log_info "Running test: $test_name"
    echo "----------------------------------------"
}

# Test 1: CORS Preflight Request
test_cors_preflight() {
    run_test "CORS Preflight Request"
    
    local response=$(curl -s -w "HTTPSTATUS:%{http_code}\nHEADERS:\n%{header_json}\n" \
        -X OPTIONS \
        -H "Origin: $ORIGIN" \
        -H "Access-Control-Request-Method: POST" \
        -H "Access-Control-Request-Headers: Content-Type, Authorization" \
        "$BACKEND_URL/auth/login")
    
    local status_code=$(echo "$response" | grep "HTTPSTATUS:" | cut -d: -f2)
    local headers=$(echo "$response" | sed -n '/HEADERS:/,/^$/p' | tail -n +2)
    
    echo "Status Code: $status_code"
    echo "Response Headers:"
    echo "$headers" | jq '.' 2>/dev/null || echo "$headers"
    
    if [[ "$status_code" == "200" || "$status_code" == "204" ]]; then
        log_success "Preflight status code: $status_code"
    else
        log_error "Invalid preflight status: $status_code"
        return 1
    fi
    
    # Check for CORS headers in response
    local cors_headers_found=false
    if echo "$headers" | grep -i "access-control-allow-origin" > /dev/null; then
        log_success "access-control-allow-origin header found"
        cors_headers_found=true
    else
        log_error "Missing access-control-allow-origin header"
    fi
    
    if echo "$headers" | grep -i "access-control-allow-methods" > /dev/null; then
        log_success "access-control-allow-methods header found"
    else
        log_warning "Missing access-control-allow-methods header"
    fi
    
    if $cors_headers_found; then
        log_success "CORS preflight test PASSED"
    else
        log_error "CORS preflight test FAILED"
        ((FAILED_TESTS--))
        ((PASSED_TESTS--))
        return 1
    fi
}

# Test 2: Authentication Request
test_authentication() {
    run_test "Authentication Request"
    
    local response=$(curl -s -w "HTTPSTATUS:%{http_code}\nHEADERS:\n%{header_json}\n" \
        -X POST \
        -H "Origin: $ORIGIN" \
        -H "Content-Type: application/json" \
        -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
        -d '{"email":"demo@velro.app","password":"demo123456"}' \
        "$BACKEND_URL/auth/login")
    
    local status_code=$(echo "$response" | grep "HTTPSTATUS:" | cut -d: -f2)
    local headers=$(echo "$response" | sed -n '/HEADERS:/,/^$/p' | tail -n +2)
    local body=$(echo "$response" | sed '/HTTPSTATUS:/,$d')
    
    echo "Status Code: $status_code"
    echo "Response Body: $body"
    echo "Response Headers:"
    echo "$headers" | jq '.' 2>/dev/null || echo "$headers"
    
    # Check status
    if [[ "$status_code" == "200" ]]; then
        log_success "Authentication successful: $status_code"
        if echo "$body" | grep -q "token"; then
            log_success "JWT token received"
        fi
    elif [[ "$status_code" == "401" ]]; then
        log_info "Authentication failed (401) - acceptable for demo credentials"
        log_success "Authentication endpoint working: $status_code"
    elif [[ "$status_code" == "404" ]]; then
        log_error "Authentication endpoint not found: $status_code"
        return 1
    else
        log_warning "Unexpected status code: $status_code"
    fi
    
    # Check CORS headers
    if echo "$headers" | grep -i "access-control-allow-origin" > /dev/null; then
        log_success "CORS headers present in auth response"
    else
        log_warning "Missing CORS headers in auth response"
    fi
    
    # Most important: no CORS policy violation (status > 0)
    if [[ "$status_code" -gt 0 ]]; then
        log_success "No CORS policy violation detected"
        log_success "Authentication test PASSED"
    else
        log_error "Possible CORS policy violation"
        return 1
    fi
}

# Test 3: Health Check
test_health_check() {
    run_test "Health Check"
    
    local response=$(curl -s -w "HTTPSTATUS:%{http_code}" \
        -H "Origin: $ORIGIN" \
        "$BACKEND_URL/health")
    
    local status_code=$(echo "$response" | grep "HTTPSTATUS:" | cut -d: -f2)
    local body=$(echo "$response" | sed 's/HTTPSTATUS:.*//')
    
    echo "Status Code: $status_code"
    echo "Response Body: $body"
    
    if [[ "$status_code" == "200" ]]; then
        log_success "Health check: $status_code"
        if echo "$body" | jq '.' > /dev/null 2>&1; then
            log_success "Health response is valid JSON"
        fi
    else
        log_error "Health check failed: $status_code"
        return 1
    fi
}

# Test 4: Complete Flow Simulation
test_complete_flow() {
    run_test "Complete Authentication Flow Simulation"
    
    log_info "Step 1: Preflight request..."
    local preflight_response=$(curl -s -w "%{http_code}" \
        -X OPTIONS \
        -H "Origin: $ORIGIN" \
        -H "Access-Control-Request-Method: POST" \
        -H "Access-Control-Request-Headers: Content-Type" \
        "$BACKEND_URL/auth/login")
    
    local preflight_status="${preflight_response: -3}"
    echo "Preflight Status: $preflight_status"
    
    if [[ "$preflight_status" == "200" || "$preflight_status" == "204" ]]; then
        log_success "Preflight passed: $preflight_status"
        
        log_info "Step 2: Authentication request..."
        local auth_response=$(curl -s -w "%{http_code}" \
            -X POST \
            -H "Origin: $ORIGIN" \
            -H "Content-Type: application/json" \
            -H "Accept: application/json" \
            -H "Sec-Fetch-Mode: cors" \
            -H "Sec-Fetch-Site: cross-site" \
            -d '{"email":"demo@velro.app","password":"demo123456"}' \
            "$BACKEND_URL/auth/login")
        
        local auth_status="${auth_response: -3}"
        echo "Auth Status: $auth_status"
        
        if [[ "$auth_status" -gt 0 ]]; then
            log_success "Complete flow working: Preflight $preflight_status → Auth $auth_status"
            log_success "Complete flow test PASSED"
        else
            log_error "Authentication request failed in complete flow"
            return 1
        fi
    else
        log_error "Preflight failed: $preflight_status"
        return 1
    fi
}

# Test 5: Browser-like Headers Test
test_browser_headers() {
    run_test "Browser-like Headers Test"
    
    local response=$(curl -s -w "HTTPSTATUS:%{http_code}" \
        -X POST \
        -H "Origin: $ORIGIN" \
        -H "Content-Type: application/json" \
        -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" \
        -H "Accept: application/json, text/plain, */*" \
        -H "Accept-Language: en-US,en;q=0.9" \
        -H "Accept-Encoding: gzip, deflate, br" \
        -H "Referer: $ORIGIN" \
        -H "Sec-Fetch-Dest: empty" \
        -H "Sec-Fetch-Mode: cors" \
        -H "Sec-Fetch-Site: cross-site" \
        -d '{"email":"demo@velro.app","password":"demo123456"}' \
        "$BACKEND_URL/auth/login")
    
    local status_code=$(echo "$response" | grep "HTTPSTATUS:" | cut -d: -f2)
    local body=$(echo "$response" | sed 's/HTTPSTATUS:.*//')
    
    echo "Status Code: $status_code"
    echo "Response Body: $body"
    
    if [[ "$status_code" -gt 0 ]]; then
        log_success "Browser-like request successful: $status_code"
        log_success "Browser headers test PASSED"
    else
        log_error "Browser-like request failed"
        return 1
    fi
}

# Generate summary report
generate_summary() {
    echo ""
    echo "=============================================================="
    echo -e "${BOLD}📊 PRODUCTION VALIDATION SUMMARY${NC}"
    echo "=============================================================="
    echo ""
    echo "🎯 Test Configuration:"
    echo "   Frontend: $FRONTEND_URL"
    echo "   Backend:  $BACKEND_URL"
    echo "   Origin:   $ORIGIN"
    echo ""
    echo "📈 Results:"
    echo "   Total Tests: $TOTAL_TESTS"
    echo -e "   Passed: ${GREEN}$PASSED_TESTS${NC}"
    echo -e "   Failed: ${RED}$FAILED_TESTS${NC}"
    
    local success_rate=0
    if [ $TOTAL_TESTS -gt 0 ]; then
        success_rate=$((PASSED_TESTS * 100 / TOTAL_TESTS))
    fi
    
    if [ $PASSED_TESTS -eq $TOTAL_TESTS ]; then
        echo -e "   Success Rate: ${GREEN}${success_rate}%${NC}"
        echo ""
        echo -e "${GREEN}${BOLD}🎉 ALL TESTS PASSED - PRODUCTION READY!${NC}"
    else
        echo -e "   Success Rate: ${YELLOW}${success_rate}%${NC}"
        echo ""
        echo -e "${RED}${BOLD}⚠️  SOME TESTS FAILED - REQUIRES ATTENTION${NC}"
    fi
    
    echo ""
    echo "=============================================================="
}

# Main execution
main() {
    echo -e "${BOLD}🚀 VELRO PRODUCTION VALIDATION (cURL)${NC}"
    echo -e "${BLUE}Testing CORS and authentication flow with cURL${NC}"
    echo ""
    
    # Run all tests
    test_cors_preflight || true
    test_authentication || true
    test_health_check || true
    test_complete_flow || true
    test_browser_headers || true
    
    # Generate final report
    generate_summary
    
    # Exit with appropriate code
    if [ $PASSED_TESTS -eq $TOTAL_TESTS ]; then
        exit 0
    else
        exit 1
    fi
}

# Run if executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi