# Production Issues Report

## Date: 2025-08-10

## Current Status
✅ **Backend is operational** - All endpoints except user creation are working

## Critical Issues

### 1. User Registration Timeout (60s) ❌
**Endpoint**: `POST /api/v1/auth/register`
**Issue**: Request times out after 60 seconds when creating new users
**Root Cause**: Database INSERT operations on users table are hanging
**Impact**: New users cannot register

### 2. E2E Test Session Timeout (28s) ❌  
**Endpoint**: `POST /api/v1/e2e/test-session`
**Issue**: Creating test users times out
**Root Cause**: Same as above - user INSERT operations hang
**Impact**: E2E tests cannot create test users

## Non-Issues (Working Fine)

✅ Database connection established successfully
✅ Service key (JWT) validated and working
✅ All READ operations working
✅ Authentication for existing users working
✅ Image generation working
✅ Storage operations working (Supabase Storage)

## Root Cause Analysis

The issue appears to be with Supabase's Row Level Security (RLS) policies or Auth system integration:

1. The service_role key validates successfully
2. READ operations work fine
3. INSERT operations on the users table hang indefinitely
4. This suggests RLS policies may be blocking service_role INSERTs

## Recommended Solutions

### Immediate Workaround
Use existing users for testing and production until the issue is resolved.

### Long-term Fixes

1. **Check Supabase RLS Policies**:
   - Review RLS policies on the `users` table
   - Ensure service_role can INSERT
   - Check if there are conflicting policies

2. **Use Supabase Auth API**:
   - Instead of direct database INSERTs, use Supabase Auth Admin API
   - This is the recommended approach for user creation
   - Example: `supabase.auth.admin.createUser()`

3. **Add Timeout Protection**:
   - Already implemented in database.py
   - Consider adding to auth endpoints as well

## Code Changes Needed

### Option 1: Use Supabase Auth Admin API (Recommended)
```python
# In auth_service.py
async def register_user_via_auth(email: str, password: str):
    """Use Supabase Auth Admin API instead of direct DB insert"""
    # Use supabase.auth.admin.createUser()
    # This bypasses RLS issues
```

### Option 2: Fix RLS Policies
```sql
-- Check current policies
SELECT * FROM pg_policies WHERE tablename = 'users';

-- Ensure service_role can INSERT
CREATE POLICY "Service role can insert users" ON users
FOR INSERT 
TO service_role
WITH CHECK (true);
```

## Monitoring

The following logs indicate the timeout issues:
- `[SECURITY] Slow request: POST /api/v1/auth/register (60.01s)`
- `[SECURITY] Slow request: POST /api/v1/e2e/test-session (28.89s)`

## Impact Assessment

- **Low Impact**: Existing users can still login and use the system
- **Medium Impact**: New user registration is blocked
- **Low Impact**: E2E tests need workarounds

## Next Steps

1. ✅ Document the issue (this report)
2. 🔄 Check Supabase RLS policies
3. 🔄 Implement Auth Admin API for user creation
4. 🔄 Test the fix
5. 🔄 Deploy to production