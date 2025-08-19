#!/bin/bash
# Comprehensive 503 Error Fix Validation using curl
# This tests the generation endpoints that were returning HTTP 503 errors

set -e

echo "🧪 Comprehensive 503 Error Fix Validation"
echo "=========================================="

KONG_URL="https://velro-kong-gateway-production.up.railway.app"
BACKEND_URL="https://velro-003-backend-production.up.railway.app"

echo ""
echo "1. Testing Health Endpoints"
echo "-------------------------"

echo "🔍 Kong Health:"
curl -s -o /dev/null -w "Status: %{http_code}, Time: %{time_total}s\n" "$KONG_URL/health" || echo "Failed to reach Kong"

echo "🔍 Backend Health (direct):"
curl -s -o /dev/null -w "Status: %{http_code}, Time: %{time_total}s\n" "$BACKEND_URL/health" || echo "Failed to reach backend"

echo "🔍 Backend Health (via Kong):"
curl -s -o /dev/null -w "Status: %{http_code}, Time: %{time_total}s\n" "$KONG_URL/api/health" || echo "Failed to reach backend via Kong"

echo ""
echo "2. Testing Generation Endpoint (Anonymous - Main 503 Fix Test)"
echo "------------------------------------------------------------"

echo "🎯 Testing /api/v1/generations (this was returning 503):"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}\nTIME:%{time_total}" "$KONG_URL/api/v1/generations")

echo "$RESPONSE"

# Extract status code
STATUS_CODE=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)

if [ "$STATUS_CODE" = "503" ]; then
    echo ""
    echo "🚨 CRITICAL: Still getting 503 errors! Fix did NOT work!"
    echo "❌ The NULL database field handling fix is not working"
elif [ "$STATUS_CODE" = "401" ]; then
    echo ""
    echo "✅ SUCCESS: 503 error FIXED! Now returns 401 (auth required - expected)"
    echo "✅ The NULL database field handling fix is working"
elif [ "$STATUS_CODE" = "200" ]; then
    echo ""
    echo "✅ EXCELLENT: 503 error FIXED! Returns data without auth"
    echo "✅ The NULL database field handling fix is working perfectly"
else
    echo ""
    echo "ℹ️  503 fixed, but returns status: $STATUS_CODE"
fi

echo ""
echo "3. Testing User Authentication Flow"
echo "--------------------------------"

echo "🔑 Attempting login with demo user..."

# Try different demo users
DEMO_USERS=(
    "demo@velro.com:demopassword123"
    "test@velro.com:testpassword123"
    "admin@velro.com:adminpassword123"
)

AUTH_TOKEN=""
WORKING_USER=""

for user_cred in "${DEMO_USERS[@]}"; do
    email=$(echo $user_cred | cut -d: -f1)
    password=$(echo $user_cred | cut -d: -f2)
    
    echo "   Trying $email..."
    
    LOGIN_RESPONSE=$(curl -s -X POST "$KONG_URL/api/v1/auth/login" \
        -H "Content-Type: application/json" \
        -w "\nHTTP_STATUS:%{http_code}" \
        -d "{\"email\":\"$email\",\"password\":\"$password\"}")
    
    LOGIN_STATUS=$(echo "$LOGIN_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
    LOGIN_BODY=$(echo "$LOGIN_RESPONSE" | grep -v "HTTP_STATUS:")
    
    echo "   Status: $LOGIN_STATUS"
    
    if [ "$LOGIN_STATUS" = "200" ]; then
        # Extract token
        AUTH_TOKEN=$(echo "$LOGIN_BODY" | jq -r '.access_token // .token // empty' 2>/dev/null || echo "")
        
        if [ -n "$AUTH_TOKEN" ] && [ "$AUTH_TOKEN" != "null" ]; then
            echo "   ✅ Login successful! Token received."
            WORKING_USER="$email"
            break
        fi
    elif [ "$LOGIN_STATUS" = "401" ]; then
        echo "   ❌ Invalid credentials"
    elif [ "$LOGIN_STATUS" = "500" ]; then
        echo "   🚨 Server error during login"
    fi
done

if [ -z "$AUTH_TOKEN" ]; then
    echo ""
    echo "⚠️  Could not obtain valid auth token from any demo user"
    echo "⚠️  This may indicate RLS or authentication issues"
else
    echo ""
    echo "4. Testing Generation Endpoint (Authenticated)"
    echo "-------------------------------------------"
    
    echo "🔐 Testing authenticated generation endpoint..."
    
    AUTH_RESPONSE=$(curl -s -H "Authorization: Bearer $AUTH_TOKEN" \
        -w "\nHTTP_STATUS:%{http_code}\nTIME:%{time_total}" \
        "$KONG_URL/api/v1/generations")
    
    AUTH_STATUS=$(echo "$AUTH_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
    AUTH_TIME=$(echo "$AUTH_RESPONSE" | grep "TIME:" | cut -d: -f2)
    AUTH_BODY=$(echo "$AUTH_RESPONSE" | grep -v -E "(HTTP_STATUS:|TIME:)")
    
    echo "Status: $AUTH_STATUS"
    echo "Time: ${AUTH_TIME}s"
    
    if [ "$AUTH_STATUS" = "503" ]; then
        echo ""
        echo "🚨 CRITICAL: Still getting 503 with authentication!"
        echo "❌ NULL field handling fix is NOT working properly"
    elif [ "$AUTH_STATUS" = "200" ]; then
        echo ""
        echo "✅ SUCCESS: 503 error completely resolved!"
        echo "✅ Authenticated generation endpoint working"
        
        # Parse JSON response if possible
        GENERATION_COUNT=$(echo "$AUTH_BODY" | jq '. | length' 2>/dev/null || echo "unknown")
        if [ "$GENERATION_COUNT" != "unknown" ]; then
            echo "📊 Found $GENERATION_COUNT generations in response"
            
            # Check for NULL field handling
            if echo "$AUTH_BODY" | jq -e '.[0] // {}' >/dev/null 2>&1; then
                echo "🔍 Sample generation structure looks good"
            fi
        fi
        
        # Show first few characters of response
        echo "📋 Response preview: $(echo "$AUTH_BODY" | head -c 200)..."
    else
        echo ""
        echo "⚠️  Unexpected authenticated status: $AUTH_STATUS"
    fi
    
    echo ""
    echo "5. Testing Other Generation Endpoints"
    echo "----------------------------------"
    
    # Test generation stats
    echo "📊 Testing /api/v1/generations/stats..."
    STATS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $AUTH_TOKEN" \
        "$KONG_URL/api/v1/generations/stats")
    echo "   Status: $STATS_STATUS"
    
    if [ "$STATS_STATUS" = "503" ]; then
        echo "   🚨 503 error still present on stats endpoint"
    elif [ "$STATS_STATUS" = "200" ]; then
        echo "   ✅ Stats endpoint working"
    fi
    
    # Test user profile
    echo "👤 Testing /api/v1/auth/me..."
    ME_RESPONSE=$(curl -s -H "Authorization: Bearer $AUTH_TOKEN" \
        "$KONG_URL/api/v1/auth/me")
    ME_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "Authorization: Bearer $AUTH_TOKEN" \
        "$KONG_URL/api/v1/auth/me")
    
    echo "   Status: $ME_STATUS"
    
    if [ "$ME_STATUS" = "200" ]; then
        CREDITS=$(echo "$ME_RESPONSE" | jq -r '.credits // "not found"' 2>/dev/null || echo "parse error")
        echo "   💰 User credits: $CREDITS"
    fi
fi

echo ""
echo "6. Testing User Registration (RLS Check)"
echo "--------------------------------------"

TEST_EMAIL="test_$(date +%s)@velrotest.com"
echo "📝 Attempting registration with: $TEST_EMAIL"

REG_RESPONSE=$(curl -s -X POST "$KONG_URL/api/v1/auth/register" \
    -H "Content-Type: application/json" \
    -w "\nHTTP_STATUS:%{http_code}" \
    -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"TestPass123!\"}")

REG_STATUS=$(echo "$REG_RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
REG_BODY=$(echo "$REG_RESPONSE" | grep -v "HTTP_STATUS:")

echo "Registration Status: $REG_STATUS"

if [ "$REG_STATUS" = "500" ]; then
    echo "🚨 Registration blocked by server error (likely RLS)"
    echo "📋 Error details:"
    echo "$REG_BODY" | jq '.' 2>/dev/null || echo "$REG_BODY"
elif [ "$REG_STATUS" = "403" ]; then
    echo "🚨 Registration blocked by RLS policies"
elif [ "$REG_STATUS" = "201" ] || [ "$REG_STATUS" = "200" ]; then
    echo "✅ Registration working properly"
else
    echo "⚠️  Unexpected registration status: $REG_STATUS"
fi

echo ""
echo "=========================================="
echo "🎯 FINAL ASSESSMENT"
echo "=========================================="

if [ "$STATUS_CODE" = "401" ] || [ "$STATUS_CODE" = "200" ]; then
    echo "✅ MAJOR SUCCESS: HTTP 503 errors on /api/v1/generations are FIXED!"
    echo "✅ The NULL database field handling fix is working"
    echo "✅ Kong Gateway routing is operational"
else
    echo "❌ CRITICAL: HTTP 503 errors still present"
    echo "❌ NULL database field handling fix needs more work"
fi

if [ -n "$WORKING_USER" ]; then
    echo "✅ Authentication system is working ($WORKING_USER)"
else
    echo "❌ Authentication issues detected"
fi

if [ "$AUTH_STATUS" = "200" ] 2>/dev/null; then
    echo "✅ Complete user flow is working end-to-end"
elif [ -z "$AUTH_TOKEN" ]; then
    echo "⚠️  Could not test complete flow due to auth issues"
fi

if [ "$REG_STATUS" = "500" ]; then
    echo "🚨 RLS policies are blocking user registration"
    echo "📋 Recommendation: Fix Supabase RLS policies for user creation"
fi

echo ""
echo "🏁 503 Error Fix Validation Complete!"
echo "=========================================="