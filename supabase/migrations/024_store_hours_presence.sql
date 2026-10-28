-- Ephemeral collaboration metadata, deliberately separate from saved versions.
create table public.store_hours_presence (
  user_id uuid not null references public.portal_users(id) on delete cascade,
  client_id uuid not null,
  session_hash text not null references public.portal_sessions(token_hash) on delete cascade,
  sequence bigint not null check(sequence>=0),
  active boolean not null default true,
  selection jsonb,
  editing boolean not null default false,
  last_seen timestamptz not null default clock_timestamp(),
  primary key(user_id,client_id)
);
create index store_hours_presence_seen on public.store_hours_presence(last_seen);
alter table public.store_hours_presence enable row level security;
revoke all on public.store_hours_presence from public,anon,authenticated,service_role;
