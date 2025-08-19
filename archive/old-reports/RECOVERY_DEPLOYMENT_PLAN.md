# Recovery Deployment Plan

**Date**: August 15, 2025  
**Objective**: Deploy recovery middleware stack with binary search capability to isolate and fix authentication issues

## Phase 1: Deploy Recovery Main (Immediate)

### 1.1 Update main.py
```bash
# Backup current main.py
cp main.py main_backup_$(date +%s).py

# Use recovery main
cp main_recovery.py main.py
```

### 1.2 Set Environment Variables
```bash
# Start with everything disabled except CORS
railway variables set BYPASS_ALL_MIDDLEWARE=false
railway variables set CATCH_ALL_EXCEPTIONS=true
railway variables set AUTH_ENABLED=false
railway variables set RATE_LIMIT_ENABLED=false  
railway variables set DISABLE_HEAVY_MIDDLEWARE=true
railway variables set DEBUG_ENDPOINTS=true
railway variables set DEPLOYMENT_MODE=true
```

### 1.3 Deploy
```bash
git add -A
git commit -m "Deploy recovery middleware stack with binary search capability"
git push origin main
```

## Phase 2: Validate Baseline (5 mins after deploy)

### 2.1 Run Contract Tests
```bash
# Test production
BASE=https://velro-backend-production.up.railway.app ./tests/contract.sh

# Expected results:
# ✅ Health check: 200
# ✅ CORS preflight: 200/204 with ACAO
# ✅ Unauth GET: 401 with ACAO and JSON
# ⚠️ Login: May fail initially
# ✅ All responses have CORS headers
```

### 2.2 Check Debug Endpoint
```bash
curl https://velro-backend-production.up.railway.app/debug/request-info | jq
```

## Phase 3: Binary Search Middleware

### 3.1 Enable Auth Only
```bash
railway variables set AUTH_ENABLED=true
railway variables set RATE_LIMIT_ENABLED=false
railway variables set DISABLE_HEAVY_MIDDLEWARE=true

# Wait for deployment
sleep 120

# Test
./tests/contract.sh
```

**If tests pass**: Auth is OK, continue  
**If tests fail**: Auth is the problem - investigate

### 3.2 Add Rate Limiting
```bash
railway variables set AUTH_ENABLED=true
railway variables set RATE_LIMIT_ENABLED=true
railway variables set DISABLE_HEAVY_MIDDLEWARE=true

# Test
./tests/contract.sh
```

**If tests fail**: Rate limiting is the problem

### 3.3 Enable Heavy Middleware
```bash
railway variables set AUTH_ENABLED=true
railway variables set RATE_LIMIT_ENABLED=true
railway variables set DISABLE_HEAVY_MIDDLEWARE=false

# Test
./tests/contract.sh
```

**If tests fail**: Heavy middleware (SSRF, ACL, etc.) is the problem

## Phase 4: Fix Authentication

### 4.1 Run Supabase Verification
```bash
# Set test credentials
export VELRO_TEST_EMAIL="known-good-user@example.com"
export VELRO_TEST_PASSWORD="known-good-password"

# Run verification
python scripts/supabase_auth_check.py
```

### 4.2 Common Auth Fixes

#### JWT Secret Mismatch
```bash
# Get Supabase JWT secret
supabase secrets list

# Update Railway
railway variables set JWT_SECRET="<correct-secret>"
```

#### Wrong Supabase Keys
```bash
# Verify keys match your Supabase project
railway variables set SUPABASE_URL="https://xxx.supabase.co"
railway variables set SUPABASE_ANON_KEY="eyJ..."
railway variables set SUPABASE_SERVICE_ROLE_KEY="eyJ..."
```

## Phase 5: Deploy Baseline App (Optional)

If main app still has issues, deploy baseline to verify platform:

### 5.1 Deploy Baseline
```bash
cd baseline_app
railway up
```

### 5.2 Test Baseline
```bash
# Preflight
curl -i -X OPTIONS \
  -H "Origin: https://velro-frontend-production.up.railway.app" \
  https://<baseline-url>/echo

# Echo
curl -i -X POST \
  -H "Origin: https://velro-frontend-production.up.railway.app" \
  -H "Content-Type: application/json" \
  -d '{"test":"data"}' \
  https://<baseline-url>/echo
```

**If baseline fails**: Platform/edge issue  
**If baseline works**: App configuration issue

## Phase 6: Production Validation

### 6.1 Final Configuration
Once working combination found:
```bash
# Document working configuration
railway variables > working_config.txt

# Update main.py with permanent fixes
```

### 6.2 Success Criteria
- [ ] Contract tests pass (except auth if not fixed)
- [ ] All errors return JSON with CORS
- [ ] X-Request-ID present in logs
- [ ] Debug endpoint accessible
- [ ] No 500 errors without CORS

## Rollback Plan

If deployment causes issues:
```bash
# Immediate bypass
railway variables set BYPASS_ALL_MIDDLEWARE=true

# Or restore backup
cp main_backup_*.py main.py
git add main.py
git commit -m "Rollback to previous main.py"
git push origin main
```

## Monitoring

Watch logs during deployment:
```bash
# Terminal 1: Railway logs
railway logs -f

# Terminal 2: Contract tests in loop
while true; do
  ./tests/contract.sh
  sleep 30
done

# Terminal 3: Health check
watch -n 5 'curl -s https://velro-backend-production.up.railway.app/health'
```

## Decision Tree

```
Start → Deploy with all middleware disabled
  ↓
CORS working? 
  No → Platform issue, check baseline app
  Yes ↓
  
Enable Auth
  ↓
Auth working?
  No → Fix auth (JWT, Supabase keys)
  Yes ↓
  
Enable Rate Limit
  ↓
Rate limit working?
  No → Check Redis connection
  Yes ↓
  
Enable Heavy Middleware
  ↓
All working?
  No → Disable problematic middleware
  Yes → Success!
```

## Notes

1. **CORS must always be outermost** - Added last in FastAPI
2. **Global error handler second** - Catches all exceptions
3. **Auth can be public-path based** - Some endpoints don't need auth
4. **Rate limiting needs Redis** - Falls back to memory if Redis fails
5. **Debug endpoints help** - Use them liberally during debugging