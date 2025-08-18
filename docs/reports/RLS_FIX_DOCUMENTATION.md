# RLS Fix Documentation - Generations Table

## Issue Summary
**Error**: "new row violates row-level security policy for table generations"

**Root Cause**: Missing INSERT policy for authenticated users on the `generations` table.

## Problem Analysis
The `generations` table had the following RLS policies:
- ✅ SELECT policy for authenticated users (view own generations)
- ✅ UPDATE policy for authenticated users and service role
- ✅ DELETE policy for authenticated users (delete own generations)  
- ❌ **MISSING** INSERT policy for authenticated users
- ⚠️ Only had INSERT policy for anonymous users (`anon_can_insert`)

## Solution Applied
Applied migration: `fix_generations_rls_insert_policy`

### Added Policies:
```sql
-- Policy 1: Allow authenticated users to insert generations
CREATE POLICY "Authenticated users can insert generations" ON public.generations
FOR INSERT
TO authenticated
WITH CHECK (auth.uid() IS NOT NULL AND auth.uid() = user_id);

-- Policy 2: Allow service role to insert (for backend operations)
CREATE POLICY "Service role can insert generations" ON public.generations
FOR INSERT
TO service_role
WITH CHECK (true);
```

## Current RLS Policies (After Fix)
The `generations` table now has 6 RLS policies:

### INSERT Policies:
1. **Authenticated users can insert generations** - `authenticated` role
2. **Service role can insert generations** - `service_role` role  
3. **anon_can_insert** - `anon` role (existing)

### SELECT Policies:
4. **Users can view own generations** - `public` role

### UPDATE Policies:
5. **Allow service role and authenticated users to update generation** - `public` role

### DELETE Policies:
6. **Users can delete own generations** - `public` role

## Test Results
✅ **FIXED**: Generation creation now works for authenticated users
✅ **VERIFIED**: Other tables' RLS policies remain intact
✅ **TESTED**: Successfully created test generation record

### Test Record Created:
- User ID: `8d089504-4659-4ea3-9b66-9e8734114bef`
- Prompt: "Test generation after RLS fix - SUCCESS!"
- Status: completed
- Model: fal-ai/flux-pro

## Security Impact
- ✅ **No security regression**: Only added necessary INSERT permissions
- ✅ **Maintains user isolation**: Users can only insert generations with their own user_id
- ✅ **Service role access**: Backend services can still create generations
- ✅ **Other tables unaffected**: No changes to users, projects, or style_stacks policies

## Files Modified
- Database: Applied migration `fix_generations_rls_insert_policy`
- Documentation: Created `RLS_FIX_DOCUMENTATION.md`

## Date Applied
- **Fix Applied**: 2025-07-30
- **Migration**: `fix_generations_rls_insert_policy`
- **Status**: ✅ RESOLVED

---

**Note**: The anonymous insert policy (`anon_can_insert`) remains active. Consider removing it if anonymous generation creation is not desired for security reasons.