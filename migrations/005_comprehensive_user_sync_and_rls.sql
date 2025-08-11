-- Migration 005: Comprehensive User Synchronization and RLS Policies
-- Purpose: Fix critical user sync issues and ensure proper RLS policies
-- Date: 2025-07-30
-- Author: Database Analysis Agent

-- Part 1: Fix User Schema Alignment
-- The user model expects specific column names that don't match current schema

-- First, let's ensure the users table has the correct schema to match the user models
-- Based on analysis of user.py, we need: credits_balance, full_name, etc.

-- Check if users table needs schema updates to match user.py model expectations
DO $$ 
BEGIN
    -- Add missing columns if they don't exist
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'users' AND column_name = 'credits_balance') THEN
        ALTER TABLE users ADD COLUMN credits_balance INTEGER DEFAULT 1000;
        -- Copy data from credits column if it exists
        IF EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'users' AND column_name = 'credits') THEN
            UPDATE users SET credits_balance = COALESCE(credits, 1000);
        END IF;
    END IF;

    -- Ensure full_name column exists (maps to display_name in some migrations)
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'users' AND column_name = 'full_name') THEN
        ALTER TABLE users ADD COLUMN full_name TEXT;
        -- Copy data from display_name if it exists
        IF EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'users' AND column_name = 'display_name') THEN
            UPDATE users SET full_name = display_name;
        END IF;
    END IF;

    -- Ensure current_plan column exists 
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'users' AND column_name = 'current_plan') THEN
        ALTER TABLE users ADD COLUMN current_plan TEXT DEFAULT 'free';
    END IF;

    -- Ensure metadata column exists
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'users' AND column_name = 'metadata') THEN
        ALTER TABLE users ADD COLUMN metadata JSONB DEFAULT '{}';
    END IF;
END $$;

-- Part 2: Create/Update User Synchronization Function
-- This function handles the sync between auth.users and public.users tables

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  -- Only insert if user doesn't already exist in public.users
  IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = NEW.id) THEN
    INSERT INTO public.users (
        id, 
        email, 
        full_name,
        display_name,
        credits_balance, 
        current_plan,
        is_active,
        metadata,
        created_at, 
        updated_at
    )
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(
            NEW.raw_user_meta_data->>'full_name',
            NEW.raw_user_meta_data->>'display_name', 
            split_part(NEW.email, '@', 1), 
            'User'
        ),
        COALESCE(
            NEW.raw_user_meta_data->>'display_name',
            NEW.raw_user_meta_data->>'full_name', 
            split_part(NEW.email, '@', 1), 
            'User'
        ),
        1000, -- Default credits for new users
        'free', -- Default plan
        true, -- Active by default
        '{}', -- Empty metadata
        NEW.created_at,
        NEW.updated_at
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Part 3: Create/Update User Synchronization Trigger
-- Drop and recreate trigger to ensure clean state
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Part 4: Sync Existing Users
-- Sync all existing auth.users that don't exist in public.users
INSERT INTO public.users (
    id, 
    email, 
    full_name,
    display_name,
    credits_balance, 
    current_plan,
    is_active,
    metadata,
    created_at, 
    updated_at
)
SELECT 
    au.id,
    au.email,
    COALESCE(
        au.raw_user_meta_data->>'full_name',
        au.raw_user_meta_data->>'display_name', 
        split_part(au.email, '@', 1), 
        'User'
    ),
    COALESCE(
        au.raw_user_meta_data->>'display_name',
        au.raw_user_meta_data->>'full_name', 
        split_part(au.email, '@', 1), 
        'User'
    ),
    1000, -- Default credits
    'free', -- Default plan  
    true, -- Active by default
    '{}', -- Empty metadata
    au.created_at,
    au.updated_at
FROM auth.users au
WHERE au.id NOT IN (SELECT id FROM public.users)
  AND au.deleted_at IS NULL -- Only sync active users
ON CONFLICT (id) DO NOTHING; -- Prevent duplicates

-- Part 5: Enable RLS on All Critical Tables
-- Ensure RLS is enabled on all tables that need it

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.generations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_models ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.style_stacks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.credit_transactions ENABLE ROW LEVEL SECURITY;

-- Part 6: Comprehensive RLS Policies
-- Drop existing policies and create comprehensive ones

-- Users table policies
DROP POLICY IF EXISTS "Users can view own profile" ON public.users;
DROP POLICY IF EXISTS "Users can update own profile" ON public.users;

CREATE POLICY "Users can view own profile" ON public.users
    FOR SELECT USING (auth.uid() = id);

CREATE POLICY "Users can update own profile" ON public.users
    FOR UPDATE USING (auth.uid() = id);

-- Projects table policies
DROP POLICY IF EXISTS "Users can view own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can create own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can insert own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can update own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can delete own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can view public projects" ON public.projects;

CREATE POLICY "Users can view own projects" ON public.projects
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own projects" ON public.projects
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own projects" ON public.projects
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own projects" ON public.projects
    FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Users can view public projects" ON public.projects
    FOR SELECT USING (visibility = 'public');

-- Generations table policies  
DROP POLICY IF EXISTS "Users can view own generations" ON public.generations;
DROP POLICY IF EXISTS "Users can create own generations" ON public.generations;
DROP POLICY IF EXISTS "Users can insert own generations" ON public.generations;
DROP POLICY IF EXISTS "Users can update own generations" ON public.generations;
DROP POLICY IF EXISTS "Users can delete own generations" ON public.generations;

CREATE POLICY "Users can view own generations" ON public.generations
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own generations" ON public.generations
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own generations" ON public.generations
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own generations" ON public.generations
    FOR DELETE USING (auth.uid() = user_id);

-- AI Models table policies (read-only for users)
DROP POLICY IF EXISTS "All users can view active models" ON public.ai_models;
DROP POLICY IF EXISTS "Users can view active models" ON public.ai_models;

CREATE POLICY "All users can view active models" ON public.ai_models
    FOR SELECT USING (is_active = true);

-- Style Stacks table policies
DROP POLICY IF EXISTS "Users can view own style stacks" ON public.style_stacks;
DROP POLICY IF EXISTS "Users can create own style stacks" ON public.style_stacks;
DROP POLICY IF EXISTS "Users can update own style stacks" ON public.style_stacks;
DROP POLICY IF EXISTS "Users can delete own style stacks" ON public.style_stacks;
DROP POLICY IF EXISTS "Users can view public style stacks" ON public.style_stacks;
DROP POLICY IF EXISTS "Users can view featured style stacks" ON public.style_stacks;

CREATE POLICY "Users can view own style stacks" ON public.style_stacks
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create own style stacks" ON public.style_stacks
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own style stacks" ON public.style_stacks
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own style stacks" ON public.style_stacks
    FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Users can view public style stacks" ON public.style_stacks
    FOR SELECT USING (is_public = true);

CREATE POLICY "Users can view featured style stacks" ON public.style_stacks
    FOR SELECT USING (is_featured = true);

-- Credit Transactions table policies
DROP POLICY IF EXISTS "Users can view own credit transactions" ON public.credit_transactions;

CREATE POLICY "Users can view own credit transactions" ON public.credit_transactions
    FOR SELECT USING (auth.uid() = user_id);

-- Part 7: Create Performance Indexes
-- Add indexes for improved query performance

CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_users_active ON public.users(is_active) WHERE is_active = true;
CREATE INDEX IF NOT EXISTS idx_users_created_at ON public.users(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_projects_user_id ON public.projects(user_id);
CREATE INDEX IF NOT EXISTS idx_projects_visibility ON public.projects(visibility);
CREATE INDEX IF NOT EXISTS idx_projects_created_at ON public.projects(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_generations_user_id ON public.generations(user_id);
CREATE INDEX IF NOT EXISTS idx_generations_project_id ON public.generations(project_id);
CREATE INDEX IF NOT EXISTS idx_generations_status ON public.generations(status);
CREATE INDEX IF NOT EXISTS idx_generations_created_at ON public.generations(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_credit_transactions_user_id ON public.credit_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_transactions_created_at ON public.credit_transactions(created_at DESC);

-- Part 8: Update Existing Records
-- Ensure all existing records have proper default values

-- Update users with missing values
UPDATE public.users 
SET 
    credits_balance = COALESCE(credits_balance, 1000),
    current_plan = COALESCE(current_plan, 'free'),
    is_active = COALESCE(is_active, true),
    metadata = COALESCE(metadata, '{}'),
    full_name = COALESCE(full_name, display_name, 'User')
WHERE credits_balance IS NULL 
   OR current_plan IS NULL 
   OR is_active IS NULL 
   OR metadata IS NULL
   OR full_name IS NULL;

-- Part 9: Data Validation and Cleanup
-- Add constraints to ensure data integrity

-- Ensure credits_balance is non-negative
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'users_credits_balance_check') THEN
        ALTER TABLE public.users ADD CONSTRAINT users_credits_balance_check 
        CHECK (credits_balance >= 0);
    END IF;
END $$;

-- Ensure current_plan has valid values
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.table_constraints 
                   WHERE constraint_name = 'users_current_plan_check') THEN
        ALTER TABLE public.users ADD CONSTRAINT users_current_plan_check 
        CHECK (current_plan IN ('free', 'basic', 'pro', 'enterprise'));
    END IF;
END $$;

-- Part 10: Verification Queries
-- These help verify the migration worked correctly

-- Count users in both tables to check sync
DO $$
DECLARE
    auth_count INTEGER;
    public_count INTEGER;
BEGIN
    SELECT COUNT(*) FROM auth.users WHERE deleted_at IS NULL INTO auth_count;
    SELECT COUNT(*) FROM public.users INTO public_count;
    
    RAISE NOTICE 'Migration 005 Complete:';
    RAISE NOTICE 'Auth users: %, Public users: %', auth_count, public_count;
    
    IF auth_count != public_count THEN
        RAISE WARNING 'User count mismatch detected! Auth: %, Public: %', auth_count, public_count;
    ELSE
        RAISE NOTICE 'User synchronization successful!';
    END IF;
END $$;

-- Check RLS status on critical tables
DO $$
DECLARE
    rls_status RECORD;
BEGIN
    RAISE NOTICE 'RLS Status Check:';
    FOR rls_status IN 
        SELECT tablename, rowsecurity 
        FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename IN ('users', 'projects', 'generations', 'ai_models', 'style_stacks', 'credit_transactions')
        ORDER BY tablename
    LOOP
        RAISE NOTICE 'Table %: RLS %', rls_status.tablename, 
                     CASE WHEN rls_status.rowsecurity THEN 'ENABLED' ELSE 'DISABLED' END;
    END LOOP;
END $$;

-- Migration 005 completed successfully
COMMENT ON SCHEMA public IS 'Migration 005: Comprehensive user sync and RLS policies applied - 2025-07-30';