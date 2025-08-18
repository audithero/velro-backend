# 🚨 Critical Fixes Application Guide

## Overview
This guide provides step-by-step instructions to fix the critical issues identified during the Velro platform audit:

1. **User synchronization gap** between `auth.users` and `public.users`
2. **Missing RLS policies** on `projects` and `generations` tables
3. **Foreign key constraint failures** when creating generations

## 📋 Prerequisites

- PostgreSQL client (`psql`) or database management tool
- Access to your Supabase project
- Environment variables configured in `.env`

## 🔧 Fix Application Steps

### Step 1: Apply Database Migration

**Option A: Using psql (Recommended)**
```bash
# Connect to your database
psql $DATABASE_URL

# Run the migration
\i velro-backend/migrations/005_user_sync_trigger.sql
```

**Option B: Using Python script**
```bash
# Install dependencies if needed
pip install psycopg2-binary python-dotenv

# Run the fixes
python velro-backend/apply_critical_fixes.py
```

### Step 2: Verify Fixes Applied

**Check user synchronization:**
```sql
-- Should show equal counts
SELECT 'auth.users' as table_name, COUNT(*) as count FROM auth.users
UNION ALL
SELECT 'public.users' as table_name, COUNT(*) as count FROM public.users;
```

**Check RLS policies:**
```sql
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public' 
AND tablename IN ('projects', 'generations');
```

**Check foreign key integrity:**
```sql
-- Should return 0 rows
SELECT COUNT(*) as invalid_refs
FROM public.generations g
LEFT JOIN public.users u ON g.user_id = u.id
WHERE u.id IS NULL;
```

### Step 3: Test the Fix

**Test user registration flow:**
```bash
python velro-backend/test_user_sync_fix.py
```

This will:
1. Test RLS policies are active
2. Verify foreign key constraints
3. Register a new test user
4. Create a generation with the new user
5. Verify everything works end-to-end

## 🧪 Manual Testing

### Test 1: New User Registration
1. Register a new user via the frontend or API
2. Check that the user appears in both `auth.users` and `public.users`
3. Verify the user has 100 credits and 'viewer' role

### Test 2: Generation Creation
1. Log in as the new user
2. Create a new project
3. Create a generation
4. Verify no foreign key constraint errors

### Test 3: RLS Policies
1. Create a user and some projects/generations
2. Try to access another user's data (should fail)
3. Verify users can only access their own data

## 🐛 Troubleshooting

### Issue: User sync not working
```sql
-- Check if trigger exists
SELECT * FROM pg_trigger WHERE tgname = 'on_auth_user_created';

-- Check if function exists
SELECT * FROM pg_proc WHERE proname = 'handle_new_user';

-- Manually trigger sync for missing users
INSERT INTO public.users (id, display_name, credits, role)
SELECT 
  au.id,
  COALESCE(au.raw_user_meta_data->>'display_name', 'User'),
  100,
  'viewer'
FROM auth.users au
WHERE au.id NOT IN (SELECT id FROM public.users);
```

### Issue: RLS policies not working
```sql
-- Check RLS status
SELECT tablename, rowsecurity 
FROM pg_tables 
WHERE schemaname = 'public';

-- Re-enable RLS if needed
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.generations ENABLE ROW LEVEL SECURITY;
```

### Issue: Foreign key constraint errors
```sql
-- Find orphaned records
SELECT g.id, g.user_id, u.id as user_exists
FROM public.generations g
LEFT JOIN public.users u ON g.user_id = u.id
WHERE u.id IS NULL;

-- Fix orphaned records (if any)
DELETE FROM public.generations WHERE user_id NOT IN (SELECT id FROM public.users);
DELETE FROM public.projects WHERE user_id NOT IN (SELECT id FROM public.users);
```

## ✅ Verification Checklist

After applying fixes, verify:

- [ ] User counts match: `auth.users` = `public.users`
- [ ] RLS enabled on `projects` and `generations`
- [ ] All RLS policies created and active
- [ ] Foreign key constraints valid
- [ ] New user registration creates public.users record
- [ ] Generation creation works without foreign key errors
- [ ] Users can only access their own data (RLS working)

## 🚀 Deployment

Once all fixes are verified:

1. **Update PRD.MD status** to "Production Ready"
2. **Deploy to Railway**:
   ```bash
   railway up
   ```
3. **Monitor for any issues** in production

## 📊 Expected Results

After applying these fixes:
- ✅ User synchronization: 100% (auth.users ↔ public.users)
- ✅ RLS coverage: 100% (all tables protected)
- ✅ Foreign key constraints: 100% valid
- ✅ Generation creation: No more constraint errors
- ✅ Security: Proper user isolation via RLS

## 🎯 Next Steps

1. Run the verification script
2. Test with real users
3. Monitor for 24-48 hours
4. Proceed with full production deployment

**Estimated time to complete fixes: 15-30 minutes**
