# Velro Auth Hot-Path Optimization - Deployment Notes

**Date**: January 11, 2025  
**Deployment ID**: ddaf7fbd-b870-45f6-b1a3-6d5cd1369399  
**Railway Project**: velro-production (a6d6ccff-c1f6-425d-95b7-5ffcf4e02c16)

## 🚨 Current Status: CRITICAL ISSUE

The auth endpoint is experiencing severe performance degradation with **9-11 second response times**, far exceeding the <1.5s target.

## Changes Deployed

### 1. Auth Service Optimizations (auth_service_async.py)
- ✅ Forced HTTP/1.1 only (removed unsupported http1=True, kept http2=False)
- ✅ Minimal headers for password grant (apikey + Content-Type only)
- ✅ Added transport with retries=0 to eliminate retry delays
- ✅ Enhanced startup probe to warm DNS/TLS/connection pools
- ✅ AUTH_FAST_LOGIN=true enabled to skip profile I/O

### 2. Critical Bug Fix (routers/auth.py)
- ✅ Fixed undefined `service_time` variable (changed to `init_time`)
- This was causing 500 errors on all login attempts

### 3. Environment Variables Verified
```
AUTH_FAST_LOGIN=true
SUPABASE_PUBLISHABLE_KEY=eyJhbGc...
SUPABASE_SECRET_KEY=eyJhbGc...
SUPABASE_URL=https://ltspnsduziplpuqxczvy.supabase.co
AUTH_SUPABASE_TIMEOUT=5.0
HTTP1_FALLBACK=true
AUTH_TIMING_ENABLED=true
```

## Performance Results

### Direct Supabase Baseline (Expected)
- p50: ~250ms ✅
- p95: ~350ms ✅
- Max: ~750ms ✅

### Backend /api/v1/auth/login (Actual)
- **Current**: 9,000-11,000ms ❌❌❌
- **Target**: <1,500ms
- **Status**: FAILED - Requests timing out

## Issues Identified

1. **Service Key Authentication Failure**
   - PostgREST probe returning 401 Unauthorized
   - Error: "Invalid API key"
   - This may be causing fallback to slower auth path

2. **Redis Connection Issues**
   - Redis unavailable, falling back to in-memory cache
   - May impact performance but shouldn't cause 9s delays

3. **Middleware Timing**
   - production_optimized middleware showing auth taking 9-11s
   - Issue appears to be in the auth service itself, not network

## Root Cause Analysis

The dramatic increase in latency (from ~4s to 9-11s) after our changes suggests:

1. **Possible Deadlock**: The async auth service might be hitting a deadlock condition
2. **Service Key Issue**: The 401 errors on service key may be causing retries or fallbacks
3. **HTTP Client Issue**: The HTTP/1.1 forced mode might be incompatible with current setup

## Immediate Actions Required

1. **Rollback Option Available**: Set `AUTH_FAST_LOGIN=false` to disable fast path
2. **Check Supabase Keys**: Verify service_role key is correct for project
3. **Review HTTP Client**: May need to revert HTTP client changes
4. **Check for Blocking Code**: Look for synchronous calls in async context

## Rollback Commands

```bash
# Quick rollback via env var
railway variables set AUTH_FAST_LOGIN=false \
  --service velro-backend --environment production

# Restart service
railway restart --service velro-backend

# Full rollback to previous deployment
railway rollback --service velro-backend
```

## Next Steps

1. Investigate why auth requests are hanging for 9+ seconds
2. Fix service key authentication issues
3. Consider reverting to previous HTTP client configuration
4. Add more detailed timing logs to identify exact bottleneck

## Commits

- `1000a2e`: Auth hot-path v2 optimizations
- `c8b0c51`: Critical fix for undefined service_time variable

## Monitoring

Check logs with:
```bash
railway logs --service velro-backend | grep -E "(AUTH-TIMING|AUTH-PERF|ASYNC-AUTH)"
```

---

**⚠️ PRODUCTION IMPACT**: Auth is currently unusable with 9-11s response times. Immediate action required.# Force rebuild - Mon Aug 11 22:33:43 AEST 2025
