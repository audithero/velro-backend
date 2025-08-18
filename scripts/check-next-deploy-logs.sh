#!/bin/bash

# Railway Service Deployment Verification Script
# Generated: 2025-08-11T15:50:00Z

echo "🔍 Railway Service Deployment Verification"
echo "=========================================="
echo

# Service URLs
FRONTEND_URL="https://velro-frontend-production.up.railway.app"
BACKEND_URL="https://velro-backend-production.up.railway.app" 
BACKEND_WORKING_URL="https://velro-backend-working-production.up.railway.app"
KONG_URL="https://velro-kong-gateway-production.up.railway.app"

# Test Frontend
echo "📱 Testing Frontend Service..."
FRONTEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL/health")
if [ "$FRONTEND_STATUS" = "200" ]; then
    echo "✅ Frontend: HEALTHY ($FRONTEND_STATUS)"
else
    echo "❌ Frontend: FAILED ($FRONTEND_STATUS)"
fi

# Test Canonical Backend
echo "🔧 Testing Canonical Backend Service..."
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_URL/health")
if [ "$BACKEND_STATUS" = "200" ]; then
    echo "✅ Backend: HEALTHY ($BACKEND_STATUS)"
else
    echo "❌ Backend: FAILED ($BACKEND_STATUS)"
fi

# Test Working Backend (temporary)
echo "🔧 Testing Working Backend Service..."
BACKEND_WORKING_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BACKEND_WORKING_URL/health")
if [ "$BACKEND_WORKING_STATUS" = "200" ]; then
    echo "✅ Backend Working: HEALTHY ($BACKEND_WORKING_STATUS)"
    echo "📋 Backend Working Response:"
    curl -s "$BACKEND_WORKING_URL/health" | jq '.' 2>/dev/null || curl -s "$BACKEND_WORKING_URL/health"
else
    echo "❌ Backend Working: FAILED ($BACKEND_WORKING_STATUS)"
fi

# Test Kong Gateway
echo "🦍 Testing Kong Gateway Service..."
KONG_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$KONG_URL/health")
if [ "$KONG_STATUS" = "200" ]; then
    echo "✅ Kong Gateway: HEALTHY ($KONG_STATUS)"
else
    echo "❌ Kong Gateway: FAILED ($KONG_STATUS)"
fi

echo
echo "🎯 Service Summary:"
echo "- Frontend: $([[ "$FRONTEND_STATUS" = "200" ]] && echo "✅ WORKING" || echo "❌ FAILED")"
echo "- Backend (canonical): $([[ "$BACKEND_STATUS" = "200" ]] && echo "✅ WORKING" || echo "❌ FAILED")"
echo "- Backend (working): $([[ "$BACKEND_WORKING_STATUS" = "200" ]] && echo "✅ WORKING" || echo "❌ FAILED")"
echo "- Kong Gateway: $([[ "$KONG_STATUS" = "200" ]] && echo "✅ WORKING" || echo "❌ FAILED")"

echo
echo "🔗 Service URLs:"
echo "- Frontend: $FRONTEND_URL"
echo "- Backend: $BACKEND_URL"
echo "- Backend Working: $BACKEND_WORKING_URL" 
echo "- Kong Gateway: $KONG_URL"

# Test API endpoints
echo
echo "🧪 API Endpoint Tests:"
echo "----------------------"

# Test auth ping on working backend
echo "Testing auth ping..."
AUTH_PING=$(curl -s "$BACKEND_WORKING_URL/api/v1/auth/ping" 2>/dev/null)
if [ $? -eq 0 ]; then
    echo "✅ Auth Ping Response:"
    echo "$AUTH_PING" | jq '.' 2>/dev/null || echo "$AUTH_PING"
else
    echo "❌ Auth Ping: FAILED"
fi

echo
echo "🎬 Deployment Check Complete!"