-- EMERGENCY FIX: RLS Policies for Projects Table
-- Purpose: Fix "new row violates row-level security policy" error
-- Date: 2025-08-04
-- Issue: Project creation failing due to missing RLS policies

-- Enable RLS on projects table if not already enabled
ALTER TABLE public.projects ENABLE ROW LEVEL SECURITY;

-- Drop existing policies to avoid conflicts
DROP POLICY IF EXISTS "Users can view own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can create own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can insert own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can update own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can delete own projects" ON public.projects;
DROP POLICY IF EXISTS "Users can view public projects" ON public.projects;

-- Create comprehensive RLS policies for projects table
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

-- Verify policies are created
SELECT tablename, policyname, cmd, qual 
FROM pg_policies 
WHERE tablename = 'projects' 
ORDER BY policyname;