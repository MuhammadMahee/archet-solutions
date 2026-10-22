create table public.store_time_punches (
  source_id text not null,
  report_date date not null,
  punch_key text not null,
  store_id text not null,
  market text not null,
  store text not null,
  employee text not null,
  clock_in timestamp not null,
  clock_out timestamp,
  loaded_at timestamptz not null default now(),
  primary key(source_id,report_date,punch_key),
  check (report_date = clock_in::date)
);
create index store_time_punches_store_day on public.store_time_punches(report_date,source_id,store_id);
create table public.store_hours_imports (
  source_id text not null,
  report_date date not null,
  status text not null default 'pending' check(status in ('pending','complete','error')),
  loaded_at timestamptz,
  row_count integer not null default 0,
  error_code text,
  primary key(source_id,report_date)
);
create table public.store_hours_reviews (
  dealer text not null,
  store_id text not null,
  report_date date not null,
  opening_time time,
  closing_time time,
  camera_in time,
  camera_out time,
  revision integer not null default 1,
  updated_by uuid not null references public.portal_users(id),
  updated_at timestamptz not null default now(),
  primary key(dealer,store_id,report_date)
);
alter table public.store_time_punches enable row level security;
alter table public.store_hours_imports enable row level security;
alter table public.store_hours_reviews enable row level security;
revoke all on public.store_time_punches,public.store_hours_imports,public.store_hours_reviews from public,anon,authenticated;
grant all on public.store_time_punches,public.store_hours_imports,public.store_hours_reviews to service_role;
