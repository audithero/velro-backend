#!/bin/bash

# Comprehensive Deployment Test Script
# Tests end-to-end functionality of Velro platform through Kong Gateway

set -e

echo "🚀 COMPREHENSIVE VELRO PLATFORM DEPLOYMENT TEST"
echo "================================================"

# Base URLs
KONG_URL="https://velro-kong-gateway-production.up.railway.app"
FRONTEND_URL="https://velro-frontend-production.up.railway.app"
BACKEND_URL="https://velro-003-backend-production.up.railway.app"

echo "📍 Testing URLs:"
echo "   Kong Gateway: $KONG_URL"
echo "   Frontend: $FRONTEND_URL"
echo "   Backend: $BACKEND_URL"
echo ""

# Test 1: Health Endpoints
echo "🔍 Test 1: Health Endpoints"
echo "----------------------------"

echo "✓ Testing Kong Gateway health..."
KONG_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$KONG_URL/health")
if [ "$KONG_HEALTH" = "200" ]; then
    echo "  ✅ Kong Gateway: HEALTHY ($KONG_HEALTH)"
else
    echo "  ❌ Kong Gateway: FAILED ($KONG_HEALTH)"
    exit 1
fi

echo "✓ Testing Frontend..."
FRONTEND_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL/")
if [ "$FRONTEND_HEALTH" = "200" ]; then
    echo "  ✅ Frontend: HEALTHY ($FRONTEND_HEALTH)"
else
    echo "  ❌ Frontend: FAILED ($FRONTEND_HEALTH)"
    exit 1
fi

echo "✓ Testing Backend via Kong..."
BACKEND_VIA_KONG=$(curl -s -o /dev/null -w "%{http_code}" "$KONG_URL/api/v1/auth/security-info")
if [ "$BACKEND_VIA_KONG" = "200" ]; then
    echo "  ✅ Backend via Kong: HEALTHY ($BACKEND_VIA_KONG)"
else
    echo "  ❌ Backend via Kong: FAILED ($BACKEND_VIA_KONG)"
    exit 1
fi

# Test 2: Authentication Flow
echo ""
echo "🔐 Test 2: Authentication Flow"
echo "-------------------------------"

echo "✓ Testing login endpoint..."
LOGIN_RESPONSE=$(curl -s -X POST "$KONG_URL/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "demo@example.com", "password": "demo123"}')

ACCESS_TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)

if [ -n "$ACCESS_TOKEN" ] && [ ${#ACCESS_TOKEN} -gt 50 ]; then
    echo "  ✅ Login: SUCCESS (token length: ${#ACCESS_TOKEN})"
else
    echo "  ❌ Login: FAILED"
    echo "  Response: $LOGIN_RESPONSE"
    exit 1
fi

echo "✓ Testing JWT token validation..."
ME_RESPONSE=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" \
  "$KONG_URL/api/v1/auth/me")

USER_ID=$(echo "$ME_RESPONSE" | grep -o '"id":"[^"]*"' | cut -d'"' -f4)

if [ -n "$USER_ID" ]; then
    echo "  ✅ JWT Validation: SUCCESS (User ID: $USER_ID)"
else
    echo "  ❌ JWT Validation: FAILED"
    echo "  Response: $ME_RESPONSE"
    exit 1
fi

# Test 3: AI Models Endpoint
echo ""
echo "🤖 Test 3: AI Models & Generation"
echo "----------------------------------"

echo "✓ Testing models endpoint..."
MODELS_RESPONSE=$(curl -s "$KONG_URL/api/v1/generations/models/supported")
MODEL_COUNT=$(echo "$MODELS_RESPONSE" | grep -o '"model_id"' | wc -l | tr -d ' ')

if [ "$MODEL_COUNT" -gt 0 ]; then
    echo "  ✅ Models Endpoint: SUCCESS ($MODEL_COUNT models available)"
else
    echo "  ❌ Models Endpoint: FAILED"
    echo "  Response: $MODELS_RESPONSE"
    exit 1
fi

# Test 4: Kong Gateway Routing
echo ""
echo "🌐 Test 4: Kong Gateway Routing"
echo "--------------------------------"

echo "✓ Testing Kong admin API..."
KONG_ADMIN_RESPONSE=$(curl -s "http://trolley.proxy.rlwy.net:34040/services")
SERVICE_COUNT=$(echo "$KONG_ADMIN_RESPONSE" | grep -o '"id"' | wc -l | tr -d ' ')

if [ "$SERVICE_COUNT" -gt 0 ]; then
    echo "  ✅ Kong Admin: SUCCESS ($SERVICE_COUNT services configured)"
else
    echo "  ❌ Kong Admin: FAILED"
    exit 1
fi

# Test 5: Security Headers
echo ""
echo "🛡️  Test 5: Security Headers"
echo "-----------------------------"

echo "✓ Testing security headers..."
SECURITY_HEADERS=$(curl -s -I "$KONG_URL/api/v1/auth/security-info")

if echo "$SECURITY_HEADERS" | grep -q "X-Content-Type-Options"; then
    echo "  ✅ Security Headers: PRESENT"
else
    echo "  ⚠️  Security Headers: MISSING (but Kong may be configured differently)"
fi

# Test 6: Performance Test
echo ""
echo "⚡ Test 6: Performance Test"
echo "---------------------------"

echo "✓ Testing response times..."
START_TIME=$(date +%s%N)
curl -s -o /dev/null "$KONG_URL/health"
END_TIME=$(date +%s%N)
RESPONSE_TIME=$(( (END_TIME - START_TIME) / 1000000 ))

if [ "$RESPONSE_TIME" -lt 1000 ]; then
    echo "  ✅ Performance: EXCELLENT (${RESPONSE_TIME}ms)"
elif [ "$RESPONSE_TIME" -lt 2000 ]; then
    echo "  ✅ Performance: GOOD (${RESPONSE_TIME}ms)"
else
    echo "  ⚠️  Performance: SLOW (${RESPONSE_TIME}ms)"
fi

# Final Summary
echo ""
echo "📋 DEPLOYMENT TEST SUMMARY"
echo "==========================="
echo "✅ All critical tests PASSED"
echo "🚀 Platform is READY FOR USE"
echo ""
echo "🌟 Production URLs:"
echo "   Frontend: $FRONTEND_URL"
echo "   API Gateway: $KONG_URL"
echo "   Health Check: $KONG_URL/health"
echo ""
echo "🔑 Test Credentials:"
echo "   Email: demo@example.com"
echo "   Password: demo123"
echo ""
echo "✨ Platform Status: FULLY OPERATIONAL"
echo "================================================"