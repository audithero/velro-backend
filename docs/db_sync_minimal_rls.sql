-- Velro Auth-to-Users Sync & Minimal RLS
-- Generated: 2025-01-12
-- Purpose: Ensure auth.users are synced to public.users with minimal RLS

-- 1) Create or replace trigger function for auth.users → public.users sync
create or replace function public.handle_new_auth_user()
returns trigger language plpgsql security definer as $$
begin
  -- Insert into public.users on auth user creation
  -- Using ON CONFLICT to make it idempotent
  insert into public.users (
    id, 
    email, 
    created_at,
    role,
    is_active,
    credits_balance
  )
  values (
    new.id, 
    new.email, 
    now(),
    'user'::user_role,  -- Default role
    true,               -- Active by default
    0                   -- Starting credits
  )
  on conflict (id) do update set
    email = EXCLUDED.email,  -- Update email in case it changed
    updated_at = now();       -- Track update time
    
  return new;
end;
$$;

-- 2) Drop existing trigger if exists and create new one
drop trigger if exists on_auth_user_created on auth.users;

create trigger on_auth_user_created
  after insert on auth.users
  for each row 
  execute function public.handle_new_auth_user();

-- 3) Backfill existing auth users to public.users
insert into public.users (
  id, 
  email, 
  created_at,
  role,
  is_active,
  credits_balance
)
select 
  au.id, 
  au.email, 
  coalesce(au.created_at, now()),
  'user'::user_role,
  true,
  0
from auth.users au
left join public.users pu on pu.id = au.id
where pu.id is null;

-- 4) Enable RLS on public.users
alter table public.users enable row level security;

-- 5) Create minimal RLS policies
-- Drop existing policies first to avoid conflicts
drop policy if exists "Users can view self" on public.users;
drop policy if exists "Users can insert self" on public.users;
drop policy if exists "Users can update self" on public.users;

-- Policy: Users can view their own record
create policy "Users can view self" on public.users
  for select 
  using (id = auth.uid());

-- Policy: Users can insert their own record (for profile creation)
create policy "Users can insert self" on public.users
  for insert 
  with check (id = auth.uid());

-- Policy: Users can update their own record
create policy "Users can update self" on public.users
  for update
  using (id = auth.uid())
  with check (id = auth.uid());

-- 6) Grant necessary permissions
grant usage on schema public to anon, authenticated;
grant select, insert, update on public.users to authenticated;
grant select on public.users to anon;  -- For public profile viewing if needed

-- Result check
select 
  'Trigger created' as status,
  count(*) as users_synced
from public.users;