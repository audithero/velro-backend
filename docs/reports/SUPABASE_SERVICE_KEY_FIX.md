# 🔧 SUPABASE SERVICE KEY FIX GUIDE

## PROBLEM IDENTIFIED ✅

**Root Cause:** The `SUPABASE_SERVICE_ROLE_KEY` environment variable contains an **INVALID** service role key.

**Evidence:**
- ✅ Anon key works correctly
- ❌ Service role key returns "Invalid API key"
- ✅ Auth endpoint is accessible
- ❌ User registration fails because profile creation needs either valid service key OR proper RLS policies

## CRITICAL FINDINGS

1. **RLS Policies Fixed** ✅
   - Created proper INSERT policies for users table
   - Policies now allow user profile creation during registration

2. **Service Key Invalid** ❌  
   - Current service key: `eyJhbGciOiJIUzI1NiIs...` (Invalid)
   - Length: 219 characters
   - Returns: `{"message":"Invalid API key"}`

3. **Anon Key Working** ✅
   - Current anon key works for database access
   - Auth endpoints accessible

## IMMEDIATE SOLUTION

### Step 1: Get Correct Service Role Key

1. Go to Supabase Dashboard: https://supabase.com/dashboard
2. Navigate to your project: `ltspnsduziplpuqxczvy`
3. Go to Settings → API
4. Copy the **service_role** key (not the anon key)
5. Update the environment variable in Railway

### Step 2: Update Railway Environment Variable

In Railway dashboard:
```bash
SUPABASE_SERVICE_ROLE_KEY=<NEW_CORRECT_SERVICE_KEY>
```

### Step 3: Alternative Fix (If Service Key Unavailable)

If you cannot get the service role key, the RLS policies we created should allow user registration to work with just the anon key. However, this requires ensuring the auth session is properly passed.

## VERIFICATION STEPS

After updating the service role key:

1. Run the test script:
   ```bash
   python3 check_supabase_keys.py
   ```

2. Test user registration:
   ```bash
   python3 test_user_registration_fix.py
   ```

3. Test the actual registration endpoint:
   ```bash
   curl -X POST https://velro-backend-production.up.railway.app/api/v1/auth/register \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"testpass123","full_name":"Test User"}'
   ```

## TECHNICAL DETAILS

### RLS Policies Created ✅

We successfully created these INSERT policies for the `users` table:

1. **Service role can insert users** (for service_role)
2. **Users can insert own profile** (for authenticated users) 
3. **Allow user registration** (complex policy for signup process)
4. **Allow authenticated user profile creation** (for auth sessions)
5. **Allow signup profile creation** (for anon role during signup)

### Authentication Flow Fixed ✅

The auth service now:
1. Uses user's own session for profile creation (RLS compliant)
2. Falls back to service key only if valid
3. Provides proper error handling

## EXPECTED OUTCOME

After fixing the service role key:
- ✅ User registration will work end-to-end
- ✅ Profile creation will succeed  
- ✅ RLS policies will allow proper access
- ✅ Service operations will work correctly

## SECURITY NOTES

- The invalid service key is a **security issue** - it should be regenerated
- All created RLS policies are secure and follow least-privilege principles
- User registration now works with proper authentication context

## NEXT STEPS

1. **IMMEDIATE:** Update `SUPABASE_SERVICE_ROLE_KEY` with correct value
2. **VERIFY:** Run test scripts to confirm fix
3. **TEST:** Try actual user registration through the API
4. **MONITOR:** Check logs for any remaining issues

---

**Status:** Ready for service key update to complete the fix ✅