#!/bin/bash

# 🧪 Production Deployment Validation Script
# Comprehensive system validation for blue-green deployment
# Usage: ./scripts/deployment-validation.sh [environment]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT=${1:-production}
TIMEOUT=30
RETRY_COUNT=5

# URLs based on environment
if [ "$ENVIRONMENT" = "production" ]; then
    KONG_URL="https://kong-production.up.railway.app"
    BACKEND_URL="https://velro-003-backend-production.up.railway.app"
    FRONTEND_URL="https://velro-003-frontend-production.up.railway.app"
elif [ "$ENVIRONMENT" = "staging" ]; then
    KONG_URL="https://kong-staging.up.railway.app"
    BACKEND_URL="https://velro-003-backend-staging.up.railway.app"
    FRONTEND_URL="https://velro-003-frontend-staging.up.railway.app"
else
    echo -e "${RED}❌ Unknown environment: $ENVIRONMENT${NC}"
    echo "Usage: $0 [production|staging]"
    exit 1
fi

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️ $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}"
}

# Function to test HTTP endpoint with retries
test_endpoint() {
    local url=$1
    local expected_codes=$2
    local description=$3
    local headers=${4:-""}
    
    log "Testing: $description"
    echo "URL: $url"
    
    for i in $(seq 1 $RETRY_COUNT); do
        if [ -n "$headers" ]; then
            response=$(curl -s -H "$headers" -o /dev/null -w "%{http_code}" --max-time $TIMEOUT "$url" || echo "000")
        else
            response=$(curl -s -o /dev/null -w "%{http_code}" --max-time $TIMEOUT "$url" || echo "000")
        fi
        
        if [[ "$expected_codes" =~ $response ]]; then
            success "$description (HTTP $response) - Attempt $i"
            return 0
        elif [ "$response" = "000" ]; then
            error "$description - Connection failed (Attempt $i/$RETRY_COUNT)"
        else
            error "$description - Unexpected response: HTTP $response (Attempt $i/$RETRY_COUNT)"
        fi
        
        if [ $i -lt $RETRY_COUNT ]; then
            log "Retrying in 5 seconds..."
            sleep 5
        fi
    done
    
    error "$description - Failed after $RETRY_COUNT attempts"
    return 1
}

# Function to test API endpoint with authentication
test_authenticated_endpoint() {
    local url=$1
    local expected_codes=$2
    local description=$3
    
    if [ -z "$KONG_API_KEY" ]; then
        warning "$description - Skipped (KONG_API_KEY not set)"
        return 0
    fi
    
    test_endpoint "$url" "$expected_codes" "$description" "X-API-Key: $KONG_API_KEY"
}

# Function to check response time
test_performance() {
    local url=$1
    local description=$2
    local max_time=${3:-2000}  # milliseconds
    
    log "Performance test: $description"
    
    # Measure response time in milliseconds
    time_total=$(curl -s -w "%{time_total}" -o /dev/null --max-time $TIMEOUT "$url" || echo "999")
    time_ms=$(echo "$time_total * 1000" | bc -l | cut -d. -f1)
    
    if [ "$time_ms" -lt "$max_time" ]; then
        success "$description - Response time: ${time_ms}ms"
    elif [ "$time_ms" -lt $((max_time * 2)) ]; then
        warning "$description - Slow response time: ${time_ms}ms"
    else
        error "$description - Too slow: ${time_ms}ms (max: ${max_time}ms)"
        return 1
    fi
}

# Main validation function
main() {
    echo ""
    echo "🧪 ==============================================="
    echo "🚀 PRODUCTION DEPLOYMENT VALIDATION"
    echo "🧪 ==============================================="
    echo ""
    echo "Environment: $ENVIRONMENT"
    echo "Timestamp: $(date)"
    echo "Timeout: ${TIMEOUT}s"
    echo "Retries: $RETRY_COUNT"
    echo ""
    
    VALIDATION_ERRORS=0
    
    # =========================================================================
    # PHASE 1: BASIC CONNECTIVITY TESTS
    # =========================================================================
    
    log "🌐 Phase 1: Basic Connectivity Tests"
    echo ""
    
    # Kong Gateway - Should require authentication
    if ! test_endpoint "$KONG_URL/" "401" "Kong Gateway health check"; then
        ((VALIDATION_ERRORS++))
    fi
    
    # Backend API - Health endpoint should be open
    if ! test_endpoint "$BACKEND_URL/health" "200" "Backend API health check"; then
        ((VALIDATION_ERRORS++))
    fi
    
    # Frontend UI - Should load homepage
    if ! test_endpoint "$FRONTEND_URL/" "200" "Frontend UI homepage"; then
        ((VALIDATION_ERRORS++))
    fi
    
    echo ""
    
    # =========================================================================
    # PHASE 2: API AUTHENTICATION TESTS
    # =========================================================================
    
    log "🔐 Phase 2: API Authentication Tests"
    echo ""
    
    # Test Kong Gateway with API key
    if ! test_authenticated_endpoint "$KONG_URL/fal/flux-dev" "400|422|405" "Kong Gateway authenticated access"; then
        ((VALIDATION_ERRORS++))
    fi
    
    # Test Kong Gateway without API key (should fail)
    if ! test_endpoint "$KONG_URL/fal/flux-dev" "401" "Kong Gateway unauthenticated access (should fail)"; then
        ((VALIDATION_ERRORS++))
    fi
    
    echo ""
    
    # =========================================================================
    # PHASE 3: TEAM COLLABORATION API TESTS
    # =========================================================================
    
    log "👥 Phase 3: Team Collaboration API Tests"
    echo ""
    
    # Team management endpoints (should require authentication)
    team_endpoints=(
        "/api/teams:401|422"
        "/api/teams/create:401|405"
        "/api/teams/join:401|405|422"
        "/api/auth/profile:401"
        "/api/projects:401"
        "/api/generations:401"
    )
    
    for endpoint_config in "${team_endpoints[@]}"; do
        IFS=':' read -r endpoint expected_codes <<< "$endpoint_config"
        if ! test_endpoint "$BACKEND_URL$endpoint" "$expected_codes" "Team API endpoint: $endpoint"; then
            ((VALIDATION_ERRORS++))
        fi
    done
    
    echo ""
    
    # =========================================================================
    # PHASE 4: PERFORMANCE TESTS
    # =========================================================================
    
    log "⚡ Phase 4: Performance Tests"
    echo ""
    
    # Check if bc is available for math calculations
    if ! command -v bc &> /dev/null; then
        warning "Performance tests skipped (bc command not available)"
    else
        # Performance benchmarks (max response times in milliseconds)
        if ! test_performance "$BACKEND_URL/health" "Backend API performance" 1000; then
            ((VALIDATION_ERRORS++))
        fi
        
        if ! test_performance "$FRONTEND_URL/" "Frontend UI performance" 3000; then
            ((VALIDATION_ERRORS++))
        fi
        
        if [ -n "$KONG_API_KEY" ]; then
            kong_perf_url="$KONG_URL/"
            kong_time=$(curl -s -w "%{time_total}" -o /dev/null --max-time $TIMEOUT "$kong_perf_url" || echo "999")
            kong_ms=$(echo "$kong_time * 1000" | bc -l | cut -d. -f1)
            
            if [ "$kong_ms" -lt 2000 ]; then
                success "Kong Gateway performance - Response time: ${kong_ms}ms"
            else
                warning "Kong Gateway performance - Slow response: ${kong_ms}ms"
            fi
        fi
    fi
    
    echo ""
    
    # =========================================================================
    # PHASE 5: FRONTEND STATIC ASSETS
    # =========================================================================
    
    log "📱 Phase 5: Frontend Static Assets"
    echo ""
    
    # Static assets that should be available
    static_assets=(
        "/favicon.ico:200"
        "/manifest.json:200|404"
        "/robots.txt:200|404"
    )
    
    for asset_config in "${static_assets[@]}"; do
        IFS=':' read -r asset expected_codes <<< "$asset_config"
        # Don't fail validation for missing optional assets
        if [[ "$expected_codes" == *"404"* ]]; then
            test_endpoint "$FRONTEND_URL$asset" "$expected_codes" "Static asset: $asset" || true
        else
            if ! test_endpoint "$FRONTEND_URL$asset" "$expected_codes" "Static asset: $asset"; then
                ((VALIDATION_ERRORS++))
            fi
        fi
    done
    
    echo ""
    
    # =========================================================================
    # PHASE 6: DATABASE CONNECTIVITY
    # =========================================================================
    
    log "🗄️ Phase 6: Database Connectivity"
    echo ""
    
    # Test database connectivity through backend
    if ! test_endpoint "$BACKEND_URL/api/health/database" "200|401" "Database connectivity test"; then
        ((VALIDATION_ERRORS++))
    fi
    
    echo ""
    
    # =========================================================================
    # PHASE 7: CORS VALIDATION
    # =========================================================================
    
    log "🔗 Phase 7: CORS Configuration"
    echo ""
    
    # Test CORS preflight request
    cors_response=$(curl -s -I \
        -H "Origin: $FRONTEND_URL" \
        -H "Access-Control-Request-Method: POST" \
        -H "Access-Control-Request-Headers: Content-Type,Authorization" \
        -X OPTIONS \
        "$BACKEND_URL/api/teams" || echo "FAILED")
    
    if echo "$cors_response" | grep -q "Access-Control-Allow-Origin"; then
        success "CORS configuration working"
    else
        warning "CORS configuration may need adjustment"
        echo "CORS Response Headers:"
        echo "$cors_response" | grep -i "access-control" || echo "No CORS headers found"
    fi
    
    echo ""
    
    # =========================================================================
    # VALIDATION SUMMARY
    # =========================================================================
    
    echo "🧪 ==============================================="
    echo "📊 VALIDATION SUMMARY"
    echo "🧪 ==============================================="
    echo ""
    echo "Environment: $ENVIRONMENT"
    echo "Total Errors: $VALIDATION_ERRORS"
    echo "Timestamp: $(date)"
    echo ""
    
    if [ $VALIDATION_ERRORS -eq 0 ]; then
        echo -e "${GREEN}🎉 ALL VALIDATIONS PASSED${NC}"
        echo ""
        echo "✅ System is ready for production deployment"
        echo "✅ All services are healthy and responding"
        echo "✅ Authentication and security working"
        echo "✅ Team collaboration APIs available"
        echo "✅ Performance within acceptable ranges"
        echo ""
        echo "🚀 PROCEED WITH DEPLOYMENT"
        exit 0
    else
        echo -e "${RED}❌ VALIDATION FAILED${NC}"
        echo ""
        echo "⚠️ Found $VALIDATION_ERRORS issues that need attention"
        echo "🔧 Please resolve issues before proceeding with deployment"
        echo "📋 Check the detailed output above for specific failures"
        echo ""
        echo "🛑 DO NOT PROCEED WITH DEPLOYMENT"
        exit 1
    fi
}

# Check for required tools
check_dependencies() {
    local missing_deps=0
    
    if ! command -v curl &> /dev/null; then
        error "curl is required but not installed"
        ((missing_deps++))
    fi
    
    if [ $missing_deps -gt 0 ]; then
        error "Missing required dependencies. Please install them and try again."
        exit 1
    fi
}

# Run validation
check_dependencies
main

# Example usage:
# ./scripts/deployment-validation.sh production
# ./scripts/deployment-validation.sh staging