# Middleware Crash Diagnosis Report

## Executive Summary

The Velro backend is experiencing a critical middleware crash that prevents ALL router-based endpoints from functioning. This affects credits, projects, generations, and all other API functionality except for the most basic inline endpoints.

## Current Status

### Working Endpoints
- `/__diag/ping` - Basic inline endpoint (works)
- Basic app is running and responding

### Failing Endpoints (ALL return 500)
- `/api/v1/credits/_ping` - Even though it's inline
- `/api/v1/projects/_ping` - Even though it's inline  
- `/api/v1/credits/stats` - Should return 401 without auth
- `/api/v1/projects` - Should return 401 without auth
- `/api/v1/nonexistent` - Should return 404
- ALL router-based endpoints

### Critical Finding
**CORS headers are missing from ALL error responses**, causing browser CORS errors as a secondary symptom.

## Root Cause Analysis

### 1. Middleware Stack Crash
The middleware is crashing BEFORE requests reach any routers or inline endpoints (except the earliest registered ones).

Evidence from logs:
```
ERROR:middleware.auth:Unexpected error in token verification: 'AsyncAuthService' object has no attribute 'verify_token_http'
ERROR:middleware.production_rate_limiter:Rate limiting middleware error after -1750492140843.7ms
anyio.EndOfStream
```

### 2. Authentication Service Method Missing
**FIXED**: Added missing `verify_token_http` method to AsyncAuthService.

### 3. Middleware Ordering Issue
The middleware stack has dependencies that cause cascading failures:
1. Rate limiter crashes when auth fails
2. Access control denies everything when auth crashes
3. CORS middleware doesn't get a chance to add headers

## Testing Performed

### 1. Minimal App Test (SUCCESS)
Created `main_minimal.py` with ONLY CORS middleware:
- ✅ All endpoints work
- ✅ CORS headers present on all responses
- ✅ Error responses have proper headers

### 2. Diagnostic Router (PARTIAL)
Created comprehensive diagnostic router but it also fails due to middleware crash.

### 3. Inline Fallbacks (FAILED)
Added inline ping endpoints but they still fail, confirming middleware crashes early.

## Recommended Solution

### Phase 1: Emergency Fix (IMMEDIATE)
1. **Disable problematic middleware temporarily**
   - Set environment variable: `DISABLE_HEAVY_MIDDLEWARE=true`
   - This will bypass the crashing middleware

2. **Fix the authentication flow**
   - ✅ Already added missing `verify_token_http` method
   - Need to verify all auth service methods are present

### Phase 2: Systematic Fix (TODAY)
1. **Create middleware bypass mode**
   ```python
   # Add to main.py
   BYPASS_MIDDLEWARE = os.getenv("BYPASS_MIDDLEWARE", "false").lower() == "true"
   
   if not BYPASS_MIDDLEWARE:
       # Add middleware
   else:
       # Only add CORS
   ```

2. **Test each middleware individually**
   - Start with CORS only
   - Add middleware one by one
   - Identify exact failure point

3. **Fix middleware dependencies**
   - Ensure auth middleware handles failures gracefully
   - Fix rate limiter time calculation bug
   - Ensure CORS is ALWAYS applied

### Phase 3: Long-term Solution
1. **Refactor middleware stack**
   - Separate critical (CORS) from optional (rate limiting)
   - Add circuit breakers to each middleware
   - Ensure failures don't cascade

2. **Add comprehensive monitoring**
   - Log each middleware entry/exit
   - Track middleware performance
   - Alert on middleware failures

## Testing Script

Use `scripts/test-diagnostic-endpoints.sh` to verify fixes:
```bash
./scripts/test-diagnostic-endpoints.sh
```

Success criteria:
- Ping endpoints return 200
- Auth endpoints return 401 (not 500) without token
- CORS headers present on ALL responses
- Non-existent endpoints return 404

## Environment Variables to Set

For emergency recovery:
```
DISABLE_HEAVY_MIDDLEWARE=true
DEPLOYMENT_MODE=true
```

For testing:
```
BYPASS_MIDDLEWARE=true
```

## Next Steps

1. **IMMEDIATE**: Deploy with `DISABLE_HEAVY_MIDDLEWARE=true`
2. **TODAY**: Implement middleware bypass mode
3. **TOMORROW**: Fix each middleware individually
4. **THIS WEEK**: Refactor middleware stack for resilience

## Files Changed

1. `services/auth_service_async.py` - Added missing `verify_token_http` method
2. `main.py` - Added inline ping endpoints and startup validation
3. `routers/diagnostics_deep.py` - Created comprehensive diagnostic router
4. `main_minimal.py` - Created minimal test app
5. `scripts/test-diagnostic-endpoints.sh` - Created testing script

## Deployment History

- Multiple failed deployments due to middleware crash
- Last successful deployment: 00bf6d8d-8c3a-4a70-b97f-05ab74218ed6
- Current issue: ALL router endpoints return 500

## Conclusion

The backend has a critical middleware crash that prevents normal operation. The fix requires either:
1. Emergency middleware bypass (quick fix)
2. Systematic middleware debugging and repair (proper fix)

The CORS issue is a symptom, not the cause. The real issue is middleware crashing before requests reach routers.