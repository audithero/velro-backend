# Profile Lookup Error - Root Cause Analysis

**User ID:** `22cb3917-57f6-49c6-ac96-ec266570081b`  
**Error Message:** `"Credit processing failed: Profile lookup error"`  
**Analysis Date:** 2025-08-02  

## 🎯 ROOT CAUSE IDENTIFIED

The "Profile lookup error" occurs **NOT during the profile lookup itself**, but during the **credit balance UPDATE operation** in the atomic credit deduction process.

## 🔍 DETAILED ANALYSIS

### 1. Database State Verification
✅ **User EXISTS in database**
- User ID: `22cb3917-57f6-49c6-ac96-ec266570081b`
- Email: `demo@velro.app`
- Credits Balance: `1200`
- Status: Active user profile

### 2. Service Key Issue
❌ **Service Key is INVALID**
- Current service key returns: `{'message': 'Invalid API key'}`
- This forces ALL operations to fallback to anon client
- Service key needs regeneration in Supabase dashboard

### 3. The EXACT Failure Point
🎯 **Credit balance UPDATE operation fails with RLS policies**

**Working Operations (READ-ONLY):**
- ✅ Profile lookup via SELECT: Works fine
- ✅ Credit balance check via SELECT: Works fine  
- ✅ User validation: Works fine

**Failing Operation (WRITE):**
- ❌ Credit balance UPDATE: Returns `0 rows updated`
- ❌ Anon client cannot UPDATE user credits due to RLS policies
- ❌ This triggers "User not found" error during deduction

## 🔬 Technical Flow Analysis

### Generation Service Flow:
1. **Credit Validation** → ✅ WORKS (SELECT query)
2. **Profile Lookup** → ✅ WORKS (SELECT query)  
3. **Atomic Credit Deduction** → ❌ FAILS (UPDATE query blocked by RLS)

### Database Operation Sequence:
```
GET /users?id=eq.{user_id}           → ✅ 200 OK (1 row)
PATCH /users?id=eq.{user_id}         → ❌ 200 OK (0 rows updated)
                                       ↑ RLS policy blocks UPDATE
```

### Error Translation:
```
UPDATE returns 0 rows → "User not found" → "Profile lookup error"
```

## 🛠️ SOLUTION

### Immediate Fix (Option 1): Fix Service Key
1. **Regenerate Service Key** in Supabase dashboard
2. **Update SUPABASE_SERVICE_ROLE_KEY** in Railway environment
3. Service key bypasses RLS and allows credit updates

### Alternative Fix (Option 2): RLS Policy Update  
1. **Update RLS policy** for `users` table to allow authenticated users to update their own credits
2. Ensure JWT token properly sets user context for RLS

### Alternative Fix (Option 3): Enhanced JWT Handling
1. **Improve JWT session setup** in database.py for anon client
2. Ensure proper Authorization header is set for authenticated operations

## 🚨 CRITICAL FINDINGS

1. **Error Message is MISLEADING**: 
   - Says "Profile lookup error" 
   - Actually "Profile UPDATE error"

2. **Service Key is BROKEN**:
   - Invalid/expired service key forces anon client fallback
   - Anon client works for reads but not writes

3. **RLS Policies Block Credit Updates**:
   - Anon client cannot update user credits
   - Even with valid JWT token, session setup may be incomplete

## 📋 RECOMMENDED ACTION PLAN

### Priority 1: Service Key Fix
```bash
# In Supabase Dashboard:
1. Go to Settings → API
2. Generate new service_role key
3. Update Railway environment variable

# In Railway:
SUPABASE_SERVICE_ROLE_KEY=<new_service_key>
```

### Priority 2: Verify RLS Policies
```sql
-- Check current RLS policy for users table
SELECT * FROM pg_policies WHERE tablename = 'users';

-- Ensure policy allows authenticated users to update own records
CREATE POLICY "Users can update own profile" ON users
FOR UPDATE USING (auth.uid()::text = id);
```

### Priority 3: Improve Error Messages
Update credit transaction service to provide more specific error messages:
- "Credit update failed due to RLS policy"
- "Service key invalid - contact support"
- NOT "Profile lookup error"

## 🔧 FILES TO MODIFY

1. **Railway Environment**: Fix `SUPABASE_SERVICE_ROLE_KEY`
2. **database.py**: Enhance JWT session setup (if needed)
3. **services/credit_transaction_service.py**: Better error messages
4. **repositories/user_repository.py**: Enhanced error handling

## ✅ VERIFICATION STEPS

After implementing the fix:
1. Run `python3 test_actual_credit_deduction.py` 
2. Verify UPDATE operations return proper row counts
3. Test generation creation via API
4. Confirm "Profile lookup error" is resolved

---

**This analysis definitively identifies that the issue is NOT a profile lookup problem, but a database write permission issue caused by an invalid service key and RLS policy restrictions.**