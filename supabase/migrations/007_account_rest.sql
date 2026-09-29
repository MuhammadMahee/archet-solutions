alter table public.portal_users
  add column rest_mode boolean not null default false,
  add column rest_version uuid not null default gen_random_uuid(),
  add constraint portal_owner_cannot_rest check (not is_owner or not rest_mode);
