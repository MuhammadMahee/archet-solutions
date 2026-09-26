create table public.calling_tree_versions (
  id uuid primary key default gen_random_uuid(),
  filename text not null,
  worksheet text not null,
  uploaded_by uuid not null references public.portal_users(id),
  uploaded_at timestamptz not null default now(),
  activated_at timestamptz,
  status text not null default 'draft' check (status in ('draft','active','archived')),
  base_version_id uuid references public.calling_tree_versions(id),
  row_count integer not null check (row_count between 1 and 5000)
);
create unique index calling_tree_one_active on public.calling_tree_versions(status) where status='active';
create table public.calling_tree_stores (
  version_id uuid not null references public.calling_tree_versions(id) on delete cascade,
  row_number integer not null,
  dealer text not null check (dealer in ('Connect','California','SRH','ARM','ARBF')),
  original_dealer text not null,
  store_id text not null,
  market text not null,
  store text not null,
  carrier text not null default '',
  dm text not null default '',
  state text not null default '',
  dealer_code text not null default '',
  door_code text not null default '',
  sap_id text not null default '',
  address text not null default '',
  zip_code text not null default '',
  primary key (version_id,dealer,store_id)
);
alter table public.calling_tree_versions enable row level security;
alter table public.calling_tree_stores enable row level security;
revoke all on public.calling_tree_versions,public.calling_tree_stores from public,anon,authenticated;
grant all on public.calling_tree_versions,public.calling_tree_stores to service_role;
