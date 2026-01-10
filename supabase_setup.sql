-- 1. Create profiles table if it doesn't exist
create table if not exists public.profiles (
  id uuid references auth.users not null primary key,
  email text,
  role text default 'user',
  is_approved boolean default false,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- 2. Add deriv_api_key column if it doesn't exist
do $$
begin
  if not exists (select 1 from information_schema.columns where table_name = 'profiles' and column_name = 'deriv_api_key') then
    alter table public.profiles add column deriv_api_key text;
  end if;
end $$;

-- 3. Helper Function: is_admin (Safe & Cached)
create or replace function public.is_admin()
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  return exists (
    select 1 from public.profiles
    where id = (select auth.uid()) and role = 'admin'
  );
end;
$$;

-- Enable Row Level Security (RLS)
alter table public.profiles enable row level security;

-- 4. CLEANUP: Drop ALL existing/conflicting policies to fix "Multiple Permissive Policies"
drop policy if exists "Public profiles are viewable by everyone" on public.profiles;
drop policy if exists "Users can insert their own profile" on public.profiles;
drop policy if exists "Users can update own profile" on public.profiles;
drop policy if exists "Admins can delete profiles" on public.profiles;
drop policy if exists "Profiles visible to owner and admins" on public.profiles;
drop policy if exists "Admins or owners can update profile" on public.profiles;
drop policy if exists "Admins can update any profile" on public.profiles;

-- 5. CREATE NEW OPTIMIZED POLICIES
-- Use (select auth.uid()) for better performance (fixes auth_rls_initplan warning)

-- SELECT: Users see themselves, Admins see everyone
create policy "Profiles visible to owner and admins"
  on public.profiles for select
  using (
    (select auth.uid()) = id
    or
    (select public.is_admin())
  );

-- INSERT: Users can insert their own profile
create policy "Users can insert their own profile"
  on public.profiles for insert
  with check ( (select auth.uid()) = id );

-- UPDATE: Users update themselves, Admins update anyone
create policy "Admins or owners can update profile"
  on public.profiles for update
  using (
    (select auth.uid()) = id
    or
    (select public.is_admin())
  );

-- DELETE: Only Admins can delete
create policy "Admins can delete profiles"
  on public.profiles for delete
  using ( (select public.is_admin()) );


-- 6. Trigger for New Users
create or replace function public.handle_new_user()
returns trigger 
language plpgsql 
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, role, is_approved)
  values (new.id, new.email, 'user', false)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
