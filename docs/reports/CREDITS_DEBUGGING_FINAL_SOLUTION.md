# Credits Balance Debugging - FINAL SOLUTION

## 🎯 EXECUTIVE SUMMARY

**Issue**: Frontend shows 100 credits instead of 1400 from database  
**Root Cause**: Invalid Supabase service key preventing backend database access  
**Impact**: Backend falls back to 100 credits when it cannot access database  
**Solution**: Fix service key configuration in Railway environment variables  

---

## 🔍 COMPLETE ROOT CAUSE ANALYSIS

### ❌ What We Initially Thought
- 405 Method Not Allowed error
- Frontend authentication issue
- Database query problem

### ✅ What We Actually Found

#### 🚨 PRIMARY ISSUE: Invalid Supabase Service Key
```
ERROR: {'message': 'Invalid API key', 'hint': 'Double check your Supabase `anon` or `service_role` API key.'}
```

**This is the root cause of everything:**

1. Backend tries to query database with service key
2. Service key is invalid/expired
3. Database query fails with 401 Unauthorized
4. Backend falls back to 100 credits (emergency fallback)
5. Frontend receives 100 instead of 1400

#### 🔄 SECONDARY ISSUE: Frontend Authentication
- User not currently logged in
- No valid token for API calls
- Frontend shows fallback user.credits_balance (100)

---

## 🛠️ STEP-BY-STEP SOLUTION

### 🔴 CRITICAL FIX: Update Service Key

#### Step 1: Get New Service Key from Supabase
1. Go to [Supabase Dashboard](https://supabase.com/dashboard)
2. Select your project: `ltspnsduziplpuqxczvy`
3. Navigate to Settings → API
4. Copy the **service_role** key (not anon key)
5. Verify it starts with `eyJ` or `sb-`

#### Step 2: Update Railway Environment Variables
1. Go to [Railway Dashboard](https://railway.app)
2. Select your `velro-003-backend-production` service
3. Go to Variables tab
4. Update `SUPABASE_SERVICE_ROLE_KEY` with new value
5. Deploy/restart the service

#### Step 3: Verify Fix
```bash
# Test the credits endpoint after service key update
curl -X GET "https://velro-003-backend-production.up.railway.app/api/v1/credits/balance/" \
  -H "Authorization: Bearer valid_jwt_token"

# Should return actual database value instead of 100
```

### 🟡 SECONDARY FIX: Frontend Authentication

#### For Production Users
Users need to log in through the frontend to get authenticated access:
1. User clicks login on frontend
2. Enters credentials
3. Backend returns valid JWT token
4. Frontend stores token and fetches real credits

#### For Development/Testing
Use the debug script to create a test user:
```python
# Run this to verify database access works
python3 test_direct_supabase_credits.py
```

---

## 🔧 TECHNICAL DETAILS

### Backend Flow (After Service Key Fix)
```
1. GET /api/v1/credits/balance/ with valid JWT
2. AuthMiddleware validates JWT ✅
3. get_current_user() extracts user from JWT ✅
4. user_service.get_user_credits() called ✅
5. user_repo.get_user_credits() with service key ✅
6. Database query succeeds ✅
7. Returns actual credits_balance: 1400 ✅
```

### Frontend Flow (After User Login)
```
1. User logs in via frontend ✅
2. authManager stores JWT token ✅
3. useCredits() hook calls API with token ✅
4. Backend returns 1400 credits ✅
5. Frontend displays correct balance ✅
```

---

## 🧪 VERIFICATION TESTS

### Test 1: Service Key Validation
```python
python3 test_direct_supabase_credits.py
# Expected: "✅ Service key is valid and functional"
```

### Test 2: Credits API with Authentication
```bash
# With valid token (after user login)
curl -X GET "https://velro-003-backend-production.up.railway.app/api/v1/credits/balance/" \
  -H "Authorization: Bearer eyJ..."
# Expected: {"balance": 1400}
```

### Test 3: Database Direct Query
```sql
-- Direct Supabase query to verify data
SELECT id, email, credits_balance 
FROM users 
WHERE id = '59269dbb-ca95-4c40-b739-ca9a7a1dcaf4';
-- Expected: credits_balance = 1400
```

---

## 📋 IMPLEMENTATION CHECKLIST

### ✅ Immediate (Critical)
- [ ] Update `SUPABASE_SERVICE_ROLE_KEY` in Railway
- [ ] Restart backend service
- [ ] Verify service key with test script
- [ ] Test credits API endpoint

### ✅ Short-term (User Experience)
- [ ] User authentication via frontend login
- [ ] Verify JWT token generation
- [ ] Test complete credit balance flow
- [ ] Monitor for any fallback to 100 credits

### ✅ Long-term (Prevention)
- [ ] Add service key validation alerts
- [ ] Implement better error messages for auth failures
- [ ] Add health check for database connectivity
- [ ] Monitor service key expiration

---

## 🎯 EXPECTED RESULTS AFTER FIX

### Before Fix
```
Frontend: 100 credits (fallback)
Backend: Database access fails → 100 fallback
Database: 1400 credits (correct value, inaccessible)
```

### After Fix
```
Frontend: 1400 credits (from API)
Backend: Database access works → returns 1400
Database: 1400 credits (correct value, accessible)
```

---

## 🚨 PREVENTION FOR FUTURE

### Monitoring
1. Add alerts for service key failures
2. Monitor 401 errors on credit endpoints
3. Track fallback credit usage patterns

### Error Handling
1. Better error messages for service key issues
2. Admin notifications for database access failures
3. User-friendly messages for authentication problems

### Documentation
1. Service key rotation procedures
2. Environment variable management
3. Debugging guides for similar issues

---

## 📞 SUPPORT CONTACT

If service key update doesn't resolve the issue:

1. **Check Supabase project status**: Ensure project isn't paused
2. **Verify Railway deployment**: Confirm environment variables saved
3. **Review logs**: Check backend logs for detailed error messages
4. **Test with curl**: Verify API responses match expectations

**This issue is 100% fixable with the service key update.**