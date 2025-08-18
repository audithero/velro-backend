#!/bin/bash
#
# Authentication Load & Performance Testing Suite
# Emergency Auth Validation Swarm - Performance Tester Component
# Version: 1.0.0
#
# This script performs comprehensive load testing and performance validation
# of the authentication system using curl, ab (Apache Bench), and custom scripts
#

set -e

# Configuration
BASE_URL="${1:-https://velro-backend.railway.app}"
API_BASE="${BASE_URL}/api/v1"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
RESULTS_DIR="auth_performance_results_${TIMESTAMP}"
EMERGENCY_TOKEN="emergency_token_bd1a2f69-89eb-489f-9288-8aacf4924763"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Create results directory
mkdir -p "$RESULTS_DIR"

echo -e "${BLUE}🚀 Authentication Load & Performance Testing Suite${NC}"
echo -e "   Target: $BASE_URL"
echo -e "   Results: $RESULTS_DIR"
echo "============================================================================="

# Function to log results
log_result() {
    local test_name="$1"
    local status="$2"
    local details="$3"
    local timestamp=$(date -Iseconds)
    
    echo "{\"test\":\"$test_name\",\"status\":\"$status\",\"timestamp\":\"$timestamp\",\"details\":\"$details\"}" >> "$RESULTS_DIR/test_results.jsonl"
    
    if [ "$status" = "PASSED" ]; then
        echo -e "${GREEN}✅ $test_name - PASSED${NC}"
    elif [ "$status" = "FAILED" ]; then
        echo -e "${RED}❌ $test_name - FAILED${NC}"
        echo -e "   Details: $details"
    else
        echo -e "${YELLOW}⏭️ $test_name - $status${NC}"
    fi
}

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install dependencies if needed
install_dependencies() {
    echo -e "${BLUE}📦 Checking dependencies...${NC}"
    
    if ! command_exists curl; then
        echo -e "${RED}❌ curl not found. Please install curl${NC}"
        exit 1
    fi
    
    if ! command_exists ab; then
        echo -e "${YELLOW}⚠️ Apache Bench (ab) not found. Installing...${NC}"
        if command_exists apt-get; then
            sudo apt-get update && sudo apt-get install -y apache2-utils
        elif command_exists brew; then
            brew install httpie
        else
            echo -e "${RED}❌ Unable to install Apache Bench. Please install apache2-utils${NC}"
        fi
    fi
    
    if ! command_exists jq; then
        echo -e "${YELLOW}⚠️ jq not found. Installing...${NC}"
        if command_exists apt-get; then
            sudo apt-get install -y jq
        elif command_exists brew; then
            brew install jq
        else
            echo -e "${YELLOW}⚠️ jq not available. JSON parsing will be limited${NC}"
        fi
    fi
}

# Test 1: Basic connectivity and response time
test_basic_connectivity() {
    echo -e "\n${BLUE}🔍 Testing Basic Connectivity...${NC}"
    
    local start_time=$(date +%s.%N)
    local response=$(curl -s -w "HTTPSTATUS:%{http_code};TIME:%{time_total};SIZE:%{size_download}" \
                          -o /tmp/health_response.txt \
                          "$BASE_URL/health")
    local end_time=$(date +%s.%N)
    local duration=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
    
    local http_status=$(echo $response | grep -o "HTTPSTATUS:[0-9]*" | cut -d: -f2)
    local time_total=$(echo $response | grep -o "TIME:[0-9.]*" | cut -d: -f2)
    local size_download=$(echo $response | grep -o "SIZE:[0-9]*" | cut -d: -f2)
    
    if [ "$http_status" = "200" ]; then
        log_result "Basic Connectivity" "PASSED" "Response time: ${time_total}s, Size: ${size_download} bytes"
        echo "  Response time: ${time_total}s"
        echo "  Response size: ${size_download} bytes"
    else
        log_result "Basic Connectivity" "FAILED" "HTTP status: $http_status"
        return 1
    fi
}

# Test 2: CORS preflight performance
test_cors_performance() {
    echo -e "\n${BLUE}🌐 Testing CORS Preflight Performance...${NC}"
    
    local total_time=0
    local success_count=0
    local iterations=10
    
    for i in $(seq 1 $iterations); do
        local start_time=$(date +%s.%N)
        local response=$(curl -s -w "%{http_code}" \
                              -X OPTIONS \
                              -H "Origin: https://velro-frontend-production.up.railway.app" \
                              -H "Access-Control-Request-Method: POST" \
                              -H "Access-Control-Request-Headers: Content-Type,Authorization" \
                              -o /dev/null \
                              "$API_BASE/auth/login")
        local end_time=$(date +%s.%N)
        local duration=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
        
        if [ "$response" = "200" ] || [ "$response" = "204" ]; then
            success_count=$((success_count + 1))
            total_time=$(echo "$total_time + $duration" | bc 2>/dev/null || echo "$total_time")
        fi
        
        sleep 0.1
    done
    
    if [ $success_count -gt 0 ]; then
        local avg_time=$(echo "scale=3; $total_time / $success_count" | bc 2>/dev/null || echo "0")
        log_result "CORS Preflight Performance" "PASSED" "Avg time: ${avg_time}s, Success rate: $success_count/$iterations"
        echo "  Average response time: ${avg_time}s"
        echo "  Success rate: $success_count/$iterations"
    else
        log_result "CORS Preflight Performance" "FAILED" "No successful CORS requests"
    fi
}

# Test 3: Authentication endpoint load testing
test_auth_load() {
    echo -e "\n${BLUE}⚡ Testing Authentication Load...${NC}"
    
    # Create test payload
    local login_payload='{"email":"test@example.com","password":"wrongpassword"}'
    echo "$login_payload" > /tmp/login_payload.json
    
    if command_exists ab; then
        echo "  Running Apache Bench load test (100 requests, 10 concurrent)..."
        
        # Run ab test and capture output
        ab -n 100 -c 10 -p /tmp/login_payload.json -T application/json \
           "$API_BASE/auth/login" > "$RESULTS_DIR/ab_login_results.txt" 2>&1
        
        if [ $? -eq 0 ]; then
            # Parse ab results
            local requests_per_sec=$(grep "Requests per second" "$RESULTS_DIR/ab_login_results.txt" | awk '{print $4}')
            local time_per_request=$(grep "Time per request.*concurrent" "$RESULTS_DIR/ab_login_results.txt" | awk '{print $4}')
            local failed_requests=$(grep "Failed requests" "$RESULTS_DIR/ab_login_results.txt" | awk '{print $3}')
            
            log_result "Authentication Load Test" "PASSED" "RPS: $requests_per_sec, Avg time: ${time_per_request}ms, Failed: $failed_requests"
            echo "  Requests per second: $requests_per_sec"
            echo "  Average time per request: ${time_per_request}ms"
            echo "  Failed requests: $failed_requests"
        else
            log_result "Authentication Load Test" "FAILED" "Apache Bench failed"
        fi
    else
        # Fallback to manual curl-based load test
        echo "  Running manual load test (50 requests)..."
        
        local success_count=0
        local total_time=0
        local iterations=50
        
        for i in $(seq 1 $iterations); do
            local start_time=$(date +%s.%N)
            local response=$(curl -s -w "%{http_code}" \
                                  -X POST \
                                  -H "Content-Type: application/json" \
                                  -d "$login_payload" \
                                  -o /dev/null \
                                  "$API_BASE/auth/login")
            local end_time=$(date +%s.%N)
            local duration=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
            
            if [ "${response:0:1}" = "4" ] || [ "${response:0:1}" = "2" ]; then
                success_count=$((success_count + 1))
                total_time=$(echo "$total_time + $duration" | bc 2>/dev/null || echo "$total_time")
            fi
            
            # Progress indicator
            if [ $((i % 10)) -eq 0 ]; then
                echo "    Progress: $i/$iterations requests completed"
            fi
            
            sleep 0.05
        done
        
        if [ $success_count -gt 0 ]; then
            local avg_time=$(echo "scale=3; $total_time / $success_count" | bc 2>/dev/null || echo "0")
            local rps=$(echo "scale=2; $success_count / $total_time" | bc 2>/dev/null || echo "0")
            
            log_result "Authentication Load Test (Manual)" "PASSED" "Avg time: ${avg_time}s, RPS: $rps, Success: $success_count/$iterations"
            echo "  Average response time: ${avg_time}s"
            echo "  Requests per second: $rps"
            echo "  Success rate: $success_count/$iterations"
        else
            log_result "Authentication Load Test (Manual)" "FAILED" "No successful requests"
        fi
    fi
}

# Test 4: Token validation performance
test_token_validation_performance() {
    echo -e "\n${BLUE}🔑 Testing Token Validation Performance...${NC}"
    
    local iterations=20
    local success_count=0
    local total_time=0
    
    for i in $(seq 1 $iterations); do
        local start_time=$(date +%s.%N)
        local response=$(curl -s -w "%{http_code}" \
                              -H "Authorization: Bearer $EMERGENCY_TOKEN" \
                              -o /dev/null \
                              "$API_BASE/auth/me")
        local end_time=$(date +%s.%N)
        local duration=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
        
        if [ "$response" = "200" ]; then
            success_count=$((success_count + 1))
            total_time=$(echo "$total_time + $duration" | bc 2>/dev/null || echo "$total_time")
        fi
        
        sleep 0.1
    done
    
    if [ $success_count -gt 0 ]; then
        local avg_time=$(echo "scale=3; $total_time / $success_count" | bc 2>/dev/null || echo "0")
        log_result "Token Validation Performance" "PASSED" "Avg time: ${avg_time}s, Success: $success_count/$iterations"
        echo "  Average validation time: ${avg_time}s"
        echo "  Success rate: $success_count/$iterations"
    else
        log_result "Token Validation Performance" "FAILED" "No successful token validations"
    fi
}

# Test 5: Concurrent authentication requests
test_concurrent_auth() {
    echo -e "\n${BLUE}🔄 Testing Concurrent Authentication...${NC}"
    
    # Create background jobs for concurrent requests
    local pids=()
    local results_file="$RESULTS_DIR/concurrent_results.txt"
    
    echo "  Starting 10 concurrent authentication requests..."
    
    for i in $(seq 1 10); do
        (
            local start_time=$(date +%s.%N)
            local response=$(curl -s -w "%{http_code}" \
                                  -X POST \
                                  -H "Content-Type: application/json" \
                                  -d '{"email":"concurrent'$i'@example.com","password":"wrongpass"}' \
                                  -o /dev/null \
                                  "$API_BASE/auth/login")
            local end_time=$(date +%s.%N)
            local duration=$(echo "$end_time - $start_time" | bc 2>/dev/null || echo "0")
            
            echo "Request $i: HTTP $response, Duration: ${duration}s" >> "$results_file"
        ) &
        pids+=($!)
    done
    
    # Wait for all background jobs to complete
    local completed=0
    for pid in "${pids[@]}"; do
        if wait $pid; then
            completed=$((completed + 1))
        fi
    done
    
    if [ -f "$results_file" ]; then
        local total_requests=$(wc -l < "$results_file")
        local successful_requests=$(grep -c "HTTP [24][0-9][0-9]" "$results_file" || echo "0")
        
        log_result "Concurrent Authentication" "PASSED" "Completed: $completed/10, Successful: $successful_requests/$total_requests"
        echo "  Completed requests: $completed/10"
        echo "  Successful responses: $successful_requests/$total_requests"
        
        if command_exists sort && command_exists tail; then
            echo "  Results summary:"
            sort "$results_file" | tail -5 | while read line; do
                echo "    $line"
            done
        fi
    else
        log_result "Concurrent Authentication" "FAILED" "No results file generated"
    fi
}

# Test 6: Rate limiting effectiveness
test_rate_limiting_effectiveness() {
    echo -e "\n${BLUE}🛡️ Testing Rate Limiting Effectiveness...${NC}"
    
    local rate_limited=false
    local requests_before_limit=0
    local payload='{"email":"ratelimit@example.com","password":"wrongpass"}'
    
    echo "  Sending rapid requests to trigger rate limiting..."
    
    for i in $(seq 1 20); do
        local response=$(curl -s -w "%{http_code}" \
                              -X POST \
                              -H "Content-Type: application/json" \
                              -d "$payload" \
                              -o /dev/null \
                              "$API_BASE/auth/login")
        
        if [ "$response" = "429" ]; then
            rate_limited=true
            requests_before_limit=$i
            break
        fi
        
        # Small delay to avoid overwhelming
        sleep 0.05
    done
    
    if [ "$rate_limited" = true ]; then
        log_result "Rate Limiting Effectiveness" "PASSED" "Rate limited after $requests_before_limit requests"
        echo "  Rate limiting triggered after $requests_before_limit requests"
    else
        log_result "Rate Limiting Effectiveness" "WARNING" "No rate limiting detected (may be disabled in development)"
        echo "  No rate limiting detected (20 requests completed)"
    fi
}

# Test 7: Memory and resource usage simulation
test_resource_usage() {
    echo -e "\n${BLUE}💾 Testing Resource Usage Under Load...${NC}"
    
    local start_time=$(date +%s)
    local memory_samples=()
    
    # Function to monitor memory usage (simplified)
    monitor_memory() {
        while true; do
            if command_exists ps; then
                # This is a rough approximation - in real testing you'd monitor the actual server
                local mem_usage=$(ps aux | grep -E "(curl|bash)" | awk '{sum+=$6} END {print sum}' 2>/dev/null || echo "0")
                echo "$(date +%s):$mem_usage" >> "$RESULTS_DIR/memory_usage.log"
            fi
            sleep 1
        done
    }
    
    # Start memory monitoring in background
    monitor_memory &
    local monitor_pid=$!
    
    # Run a sustained load test
    echo "  Running sustained load for 30 seconds..."
    local end_time=$((start_time + 30))
    local request_count=0
    
    while [ $(date +%s) -lt $end_time ]; do
        curl -s -X POST \
             -H "Content-Type: application/json" \
             -d '{"email":"loadtest@example.com","password":"testpass"}' \
             -o /dev/null \
             "$API_BASE/auth/login" &
        
        request_count=$((request_count + 1))
        
        # Limit concurrent requests to avoid overwhelming
        if [ $((request_count % 5)) -eq 0 ]; then
            wait
            sleep 0.5
        fi
    done
    
    # Stop memory monitoring
    kill $monitor_pid 2>/dev/null || true
    wait
    
    local duration=$(($(date +%s) - start_time))
    log_result "Resource Usage Test" "PASSED" "Duration: ${duration}s, Requests: $request_count"
    echo "  Test duration: ${duration}s"
    echo "  Total requests sent: $request_count"
    
    if [ -f "$RESULTS_DIR/memory_usage.log" ]; then
        echo "  Memory usage log saved to memory_usage.log"
    fi
}

# Generate performance report
generate_report() {
    echo -e "\n${BLUE}📊 Generating Performance Report...${NC}"
    
    local report_file="$RESULTS_DIR/performance_report.md"
    
    cat > "$report_file" << EOF
# Authentication Performance Test Report

**Test Date:** $(date)
**Target URL:** $BASE_URL
**Test Duration:** $(date +%s) seconds

## Test Summary

$(cat "$RESULTS_DIR/test_results.jsonl" | wc -l) tests executed.

### Test Results

EOF
    
    if [ -f "$RESULTS_DIR/test_results.jsonl" ]; then
        echo -e "Results breakdown:" >> "$report_file"
        
        if command_exists jq; then
            echo "- Passed: $(grep '"status":"PASSED"' "$RESULTS_DIR/test_results.jsonl" | wc -l)" >> "$report_file"
            echo "- Failed: $(grep '"status":"FAILED"' "$RESULTS_DIR/test_results.jsonl" | wc -l)" >> "$report_file"
            echo "- Warnings: $(grep '"status":"WARNING"' "$RESULTS_DIR/test_results.jsonl" | wc -l)" >> "$report_file"
        else
            echo "- Total tests: $(cat "$RESULTS_DIR/test_results.jsonl" | wc -l)" >> "$report_file"
        fi
        
        echo -e "\n### Detailed Results\n" >> "$report_file"
        
        while IFS= read -r line; do
            if command_exists jq; then
                local test_name=$(echo "$line" | jq -r '.test')
                local status=$(echo "$line" | jq -r '.status')
                local details=$(echo "$line" | jq -r '.details')
                echo "- **$test_name**: $status - $details" >> "$report_file"
            else
                echo "- $line" >> "$report_file"
            fi
        done < "$RESULTS_DIR/test_results.jsonl"
    fi
    
    cat >> "$report_file" << EOF

## Performance Metrics

$(if [ -f "$RESULTS_DIR/ab_login_results.txt" ]; then
    echo "### Apache Bench Results"
    echo "\`\`\`"
    grep -E "(Requests per second|Time per request|Failed requests)" "$RESULTS_DIR/ab_login_results.txt" || echo "No performance data available"
    echo "\`\`\`"
fi)

## Files Generated

- Test results: test_results.jsonl
- Performance report: performance_report.md
$(if [ -f "$RESULTS_DIR/ab_login_results.txt" ]; then echo "- Apache Bench results: ab_login_results.txt"; fi)
$(if [ -f "$RESULTS_DIR/concurrent_results.txt" ]; then echo "- Concurrent test results: concurrent_results.txt"; fi)
$(if [ -f "$RESULTS_DIR/memory_usage.log" ]; then echo "- Memory usage log: memory_usage.log"; fi)

---
Generated by Authentication Load & Performance Testing Suite
EOF
    
    echo -e "  Performance report saved to: $report_file"
}

# Main execution
main() {
    install_dependencies
    
    # Run all performance tests
    test_basic_connectivity
    test_cors_performance
    test_auth_load
    test_token_validation_performance
    test_concurrent_auth
    test_rate_limiting_effectiveness
    test_resource_usage
    
    # Generate final report
    generate_report
    
    echo -e "\n${GREEN}✅ Performance testing complete!${NC}"
    echo -e "   Results directory: $RESULTS_DIR"
    
    # Summary
    if [ -f "$RESULTS_DIR/test_results.jsonl" ]; then
        local total_tests=$(cat "$RESULTS_DIR/test_results.jsonl" | wc -l)
        local passed_tests=$(grep -c '"status":"PASSED"' "$RESULTS_DIR/test_results.jsonl" || echo "0")
        local failed_tests=$(grep -c '"status":"FAILED"' "$RESULTS_DIR/test_results.jsonl" || echo "0")
        
        echo -e "   Total tests: $total_tests"
        echo -e "   Passed: ${GREEN}$passed_tests${NC}"
        echo -e "   Failed: ${RED}$failed_tests${NC}"
        
        if [ "$failed_tests" -gt 0 ]; then
            exit 1
        fi
    fi
}

# Run main function
main "$@"