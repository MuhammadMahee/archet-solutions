-- Daily source snapshots. Account identity stays separate from dealer identity.
create table public.sales_imports (
  source_id text not null check (source_id in ('connect','california','srh','arm1','arm2','arbf')),
  report_date date not null,
  status text not null default 'pending' check (status in ('pending','complete','error')),
  attempted_at timestamptz,
  loaded_at timestamptz,
  retry_at timestamptz not null default now(),
  row_count integer not null default 0,
  retained_count integer not null default 0,
  error_code text,
  primary key (source_id, report_date)
);
create table public.sales_performance (
  source_id text not null,
  report_date date not null,
  store_id text not null,
  market text not null,
  store text not null,
  new_activation integer not null,
  upgrade integer not null,
  reactivation integer not null,
  bts integer not null,
  hsi integer not null,
  accessory numeric(14,2) not null,
  total_boxes integer not null,
  qpay integer not null,
  loaded_at timestamptz not null default now(),
  primary key (source_id, report_date, store_id),
  foreign key (source_id, report_date) references public.sales_imports(source_id, report_date)
);
create index sales_performance_date on public.sales_performance(report_date);
create index sales_imports_due on public.sales_imports(status, retry_at);
alter table public.sales_imports enable row level security;
alter table public.sales_performance enable row level security;
revoke all on public.sales_imports, public.sales_performance from public, anon, authenticated;
grant all on public.sales_imports, public.sales_performance to service_role;
