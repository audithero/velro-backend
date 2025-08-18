#!/usr/bin/env bash
set -euo pipefail

# Contract tests for Velro API
# Tests critical endpoints for CORS and proper responses

# Configuration
ORIGIN="${ORIGIN:-https://velro-frontend-production.up.railway.app}"
BASE="${BASE:-https://velro-backend-production.up.railway.app}"

# Test credentials (set via environment for CI)
TEST_EMAIL="${VELRO_TEST_EMAIL:-}"
TEST_PASSWORD="${VELRO_TEST_PASSWORD:-}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
pass() { echo -e "${GREEN}✅ $1${NC}"; }
fail() { echo -e "${RED}❌ $1${NC}"; exit 1; }
warn() { echo -e "${YELLOW}⚠️ $1${NC}"; }
info() { echo -e "${BLUE}ℹ️ $1${NC}"; }

echo -e "${BLUE}🔍 Velro API Contract Tests${NC}"
echo "================================"
echo "Base URL: $BASE"
echo "Origin: $ORIGIN"
echo ""

# Track failures
FAILURES=0
TESTS=0

# Test function
run_test() {
    local name="$1"
    local result="$2"
    TESTS=$((TESTS + 1))
    if [ "$result" = "0" ]; then
        pass "$name"
    else
        fail "$name"
        FAILURES=$((FAILURES + 1))
    fi
}

# ============================================================================
# TEST 1: OPTIONS Preflight
# ============================================================================
info "Test 1: OPTIONS preflight for /api/v1/projects"

PREFLIGHT_RESPONSE=$(curl -s -i -X OPTIONS \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: GET" \
    -H "Access-Control-Request-Headers: Authorization" \
    "$BASE/api/v1/projects" 2>/dev/null || true)

# Check status code
if echo "$PREFLIGHT_RESPONSE" | head -n1 | grep -q "200\|204"; then
    pass "Preflight returns 200/204"
else
    fail "Preflight did not return 200/204"
    echo "$PREFLIGHT_RESPONSE" | head -n5
fi

# Check CORS headers
if echo "$PREFLIGHT_RESPONSE" | grep -qi "access-control-allow-origin"; then
    pass "ACAO header present on preflight"
else
    fail "ACAO header missing on preflight"
fi

echo ""

# ============================================================================
# TEST 2: Unauthenticated GET (should return 401 with CORS)
# ============================================================================
info "Test 2: GET /api/v1/projects without auth (expect 401 + CORS)"

UNAUTH_RESPONSE=$(curl -s -i -H "Origin: $ORIGIN" "$BASE/api/v1/projects" 2>/dev/null || true)

# Check status code
if echo "$UNAUTH_RESPONSE" | head -n1 | grep -q "401"; then
    pass "Returns 401 for unauthenticated request"
else
    fail "Did not return 401 for unauthenticated request"
    echo "$UNAUTH_RESPONSE" | head -n5
fi

# Check CORS headers on error
if echo "$UNAUTH_RESPONSE" | grep -qi "access-control-allow-origin: $ORIGIN"; then
    pass "ACAO header present on 401 response"
else
    fail "ACAO header missing on 401 response"
    echo "Headers received:"
    echo "$UNAUTH_RESPONSE" | head -n20 | grep -i "access-control" || echo "  No access-control headers found"
fi

# Check JSON response
if echo "$UNAUTH_RESPONSE" | tail -n1 | grep -q "{"; then
    pass "Returns JSON on 401"
else
    fail "Does not return JSON on 401"
fi

echo ""

# ============================================================================
# TEST 3: Login (if credentials provided)
# ============================================================================
if [[ -n "$TEST_EMAIL" && -n "$TEST_PASSWORD" ]]; then
    info "Test 3: POST /api/v1/auth/login with valid credentials"
    
    LOGIN_RESPONSE=$(curl -s -i -X POST \
        -H "Origin: $ORIGIN" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" \
        "$BASE/api/v1/auth/login" 2>/dev/null || true)
    
    # Check for success
    if echo "$LOGIN_RESPONSE" | grep -q "\"access_token\"\|\"token\""; then
        pass "Login successful - token received"
        
        # Extract token for further tests
        TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
        if [ -z "$TOKEN" ]; then
            TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
        fi
    else
        warn "Login failed - no token received"
        echo "Response:"
        echo "$LOGIN_RESPONSE" | tail -n5
        TOKEN=""
    fi
    
    # Check CORS on login
    if echo "$LOGIN_RESPONSE" | grep -qi "access-control-allow-origin"; then
        pass "ACAO header present on login response"
    else
        fail "ACAO header missing on login response"
    fi
else
    warn "Test 3: Skipping login test (no credentials provided)"
    echo "  Set VELRO_TEST_EMAIL and VELRO_TEST_PASSWORD to test login"
    TOKEN=""
fi

echo ""

# ============================================================================
# TEST 4: Models endpoint (should work or return 503 with CORS)
# ============================================================================
info "Test 4: GET /api/v1/models/supported"

MODELS_RESPONSE=$(curl -s -i -H "Origin: $ORIGIN" "$BASE/api/v1/models/supported" 2>/dev/null || true)

# Get status code
STATUS_CODE=$(echo "$MODELS_RESPONSE" | head -n1 | grep -oE "[0-9]{3}")

# Check CORS headers
if echo "$MODELS_RESPONSE" | grep -qi "access-control-allow-origin"; then
    pass "ACAO header present on models endpoint"
else
    fail "ACAO header missing on models endpoint"
fi

# Check response type
if [ "$STATUS_CODE" = "200" ]; then
    pass "Models endpoint returns 200"
elif [ "$STATUS_CODE" = "503" ]; then
    warn "Models endpoint returns 503 (service unavailable)"
elif [ "$STATUS_CODE" = "401" ]; then
    warn "Models endpoint requires auth (401)"
else
    fail "Models endpoint returns unexpected status: $STATUS_CODE"
fi

echo ""

# ============================================================================
# TEST 5: Health check
# ============================================================================
info "Test 5: GET /health (should always work)"

HEALTH_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/health" 2>/dev/null || true)

if [ "$HEALTH_RESPONSE" = "200" ]; then
    pass "Health check returns 200"
else
    fail "Health check returns $HEALTH_RESPONSE"
fi

echo ""

# ============================================================================
# TEST 6: Debug endpoint (if available)
# ============================================================================
info "Test 6: GET /debug/request-info (diagnostic endpoint)"

DEBUG_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" -H "Origin: $ORIGIN" "$BASE/debug/request-info" 2>/dev/null || true)

if [ "$DEBUG_RESPONSE" = "200" ]; then
    pass "Debug endpoint available"
elif [ "$DEBUG_RESPONSE" = "404" ]; then
    warn "Debug endpoint not found (may be disabled in production)"
else
    warn "Debug endpoint returns $DEBUG_RESPONSE"
fi

echo ""

# ============================================================================
# TEST 7: Authenticated request (if we have a token)
# ============================================================================
if [ -n "$TOKEN" ]; then
    info "Test 7: GET /api/v1/projects with auth token"
    
    AUTH_RESPONSE=$(curl -s -i \
        -H "Origin: $ORIGIN" \
        -H "Authorization: Bearer $TOKEN" \
        "$BASE/api/v1/projects" 2>/dev/null || true)
    
    STATUS=$(echo "$AUTH_RESPONSE" | head -n1 | grep -oE "[0-9]{3}")
    
    if [ "$STATUS" = "200" ]; then
        pass "Authenticated request successful"
    else
        warn "Authenticated request returned $STATUS"
    fi
    
    if echo "$AUTH_RESPONSE" | grep -qi "access-control-allow-origin"; then
        pass "ACAO header present on authenticated response"
    else
        fail "ACAO header missing on authenticated response"
    fi
else
    warn "Test 7: Skipping authenticated test (no token)"
fi

echo ""

# ============================================================================
# SUMMARY
# ============================================================================
echo "================================"
echo -e "${BLUE}Test Summary${NC}"
echo ""

if [ $FAILURES -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}❌ $FAILURES test(s) failed${NC}"
    exit 1
fi