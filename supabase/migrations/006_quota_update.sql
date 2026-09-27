create table public.quota_uploads (
  goal_month date not null check (extract(day from goal_month)=1),
  dealer text not null check (dealer in ('Connect','California','SRH','AMQ','ARM','ARBF')),
  filename text not null,
  row_count integer not null check (row_count between 1 and 5000),
  uploaded_by uuid not null references public.portal_users(id),
  uploaded_at timestamptz not null default now(),
  primary key (goal_month,dealer)
);
create table public.quota_goals (
  goal_month date not null,
  dealer text not null,
  store_id text not null,
  voice_goal numeric(14,2) not null check (voice_goal>=0),
  bts_goal numeric(14,2) not null check (bts_goal>=0),
  hsi_goal numeric(14,2) not null check (hsi_goal>=0),
  accessory_goal numeric(14,2) not null check (accessory_goal>=0),
  mim_goal numeric(14,2) not null default 0 check (mim_goal>=0),
  primary key (goal_month,dealer,store_id),
  foreign key (goal_month,dealer) references public.quota_uploads(goal_month,dealer) on delete cascade
);
alter table public.quota_uploads enable row level security;
alter table public.quota_goals enable row level security;
revoke all on public.quota_uploads,public.quota_goals from public,anon,authenticated;
grant all on public.quota_uploads,public.quota_goals to service_role;
