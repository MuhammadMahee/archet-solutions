-- Applied automatically by scripts/migrate.py inside a transaction.

create table public.portal_users (
  id uuid primary key references auth.users(id) on delete cascade,
  username text not null check (username ~ '^[A-Za-z0-9_]{3,32}$'),
  username_key text generated always as (lower(username)) stored unique,
  display_name text not null check (length(display_name) between 1 and 100),
  role text not null default 'member' check (role in ('admin', 'member')),
  active boolean not null default true,
  is_owner boolean not null default false,
  session_version uuid not null default gen_random_uuid(),
  created_at timestamptz not null default now(),
  check (not is_owner or (role = 'admin' and active and username = 'Mahee'))
);
create unique index portal_username on public.portal_users (lower(username));
create unique index portal_one_owner on public.portal_users (is_owner) where is_owner;

create table public.portal_sessions (
  token_hash text primary key,
  user_id uuid not null references public.portal_users(id) on delete cascade,
  session_version uuid not null,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null
);
create index portal_sessions_user on public.portal_sessions(user_id);
create index portal_sessions_expiry on public.portal_sessions(expires_at);

create table public.quote_requests (
  id uuid primary key default gen_random_uuid(),
  received_at timestamptz not null default now(),
  full_name text not null,
  company text not null,
  email text not null,
  phone text not null default '',
  brand text not null,
  stores text not null default '',
  message text not null default '',
  status text not null default 'new' check (status in ('new', 'contacted', 'closed')),
  notes text not null default '',
  updated_at timestamptz not null default now(),
  updated_by uuid references public.portal_users(id) on delete set null,
  notification_status text not null default 'pending' check (notification_status in ('pending', 'sent', 'failed'))
);
create index quote_requests_received on public.quote_requests(received_at desc);

create table public.portal_rate_limits (
  key text primary key,
  window_start timestamptz not null default now(),
  attempts integer not null default 1
);

-- No browser/anonymous access, even with a Supabase public key or Auth JWT.
alter table public.portal_users enable row level security;
alter table public.portal_sessions enable row level security;
alter table public.quote_requests enable row level security;
alter table public.portal_rate_limits enable row level security;
revoke all on public.portal_users, public.portal_sessions, public.quote_requests,
  public.portal_rate_limits from anon, authenticated;
grant all on public.portal_users, public.portal_sessions, public.quote_requests,
  public.portal_rate_limits to service_role;

create function public.protect_portal_owner() returns trigger
language plpgsql set search_path = '' as $$
begin
  if OLD.is_owner then
    if TG_OP = 'DELETE' then
      raise exception 'The permanent owner cannot be deleted';
    end if;
    if not NEW.is_owner or not NEW.active or NEW.role <> 'admin' or NEW.username <> 'Mahee' then
      raise exception 'The permanent owner cannot be disabled, renamed or demoted';
    end if;
  end if;
  if TG_OP = 'DELETE' then return OLD; end if;
  return NEW;
end;
$$;
create trigger protect_portal_owner before update or delete on public.portal_users
  for each row execute function public.protect_portal_owner();

-- A single database transaction enforces limits across serverless instances.
create function public.portal_check_rate(p_key text, p_limit integer, p_seconds integer)
returns boolean language plpgsql security definer set search_path = '' as $$
declare current_attempts integer;
begin
  delete from public.portal_rate_limits where window_start < now() - interval '1 day';
  delete from public.portal_sessions where expires_at <= now();
  insert into public.portal_rate_limits as limits(key, attempts, window_start)
    values(p_key, 1, now())
  on conflict(key) do update set
    attempts = case when limits.window_start < now() - make_interval(secs => p_seconds)
      then 1 else limits.attempts + 1 end,
    window_start = case when limits.window_start < now() - make_interval(secs => p_seconds)
      then now() else limits.window_start end
  returning attempts into current_attempts;
  return current_attempts <= p_limit;
end;
$$;
revoke all on function public.portal_check_rate(text, integer, integer) from public, anon, authenticated;
grant execute on function public.portal_check_rate(text, integer, integer) to service_role;
