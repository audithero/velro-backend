-- Fix user sync trigger to use correct column names
-- This corrects the mismatch between auth.users and public.users table schema

-- Drop the existing incorrect trigger and function
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
DROP FUNCTION IF EXISTS public.handle_new_user();

-- Create corrected function to handle new user creation with proper column mapping
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  -- Only insert if user doesn't already exist
  IF NOT EXISTS (SELECT 1 FROM public.users WHERE id = NEW.id) THEN
    INSERT INTO public.users (id, email, display_name, credits, role, created_at, updated_at)
    VALUES (
      NEW.id,
      NEW.email,
      COALESCE(NEW.raw_user_meta_data->>'display_name', 
               NEW.raw_user_meta_data->>'full_name',
               split_part(NEW.email, '@', 1), 
               'User'),
      10, -- Default credits for new users
      'viewer', -- Default role
      NEW.created_at,
      NEW.updated_at
    );
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create trigger on auth.users
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Sync existing auth users to public.users with correct column names
INSERT INTO public.users (id, email, display_name, credits, role, created_at, updated_at)
SELECT 
  au.id,
  au.email,
  COALESCE(au.raw_user_meta_data->>'display_name', 
           au.raw_user_meta_data->>'full_name',
           split_part(au.email, '@', 1), 
           'User'),
  10, -- Default credits
  'viewer', -- Default role
  au.created_at,
  au.updated_at
FROM auth.users au
WHERE au.id NOT IN (SELECT id FROM public.users)
  AND au.deleted_at IS NULL; -- Only sync active users

-- Update any existing users that may have NULL values
UPDATE public.users 
SET 
  display_name = COALESCE(display_name, 'User'),
  credits = COALESCE(credits, 10),
  role = COALESCE(role, 'viewer'::user_role)
WHERE display_name IS NULL 
   OR credits IS NULL 
   OR role IS NULL;