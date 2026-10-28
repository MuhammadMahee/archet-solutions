-- Copies are encrypted in application code; keys never enter the database.
create table public.portal_password_vault (
  user_id uuid primary key references public.portal_users(id) on delete cascade,
  ciphertext text not null,
  auth_fingerprint text not null,
  updated_at timestamptz not null default now()
);
create table public.portal_password_views (
  id bigint generated always as identity primary key,
  actor_id uuid not null references public.portal_users(id),
  target_id uuid not null references public.portal_users(id),
  available boolean not null,
  viewed_at timestamptz not null default now()
);
alter table public.portal_password_vault enable row level security;
alter table public.portal_password_views enable row level security;
revoke all on public.portal_password_vault,public.portal_password_views from public,anon,authenticated,service_role;
