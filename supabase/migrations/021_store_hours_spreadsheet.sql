alter table public.store_hours_employee_reviews
  add column custom_cells jsonb not null default '{}'::jsonb check(jsonb_typeof(custom_cells)='object'),
  add column cell_formats jsonb not null default '{}'::jsonb check(jsonb_typeof(cell_formats)='object');

create table public.store_hours_sheet_settings (
  id boolean primary key default true check(id),
  dealer text not null default '*' check(dealer='*'),
  store_id text not null default '__sheet__' check(store_id='__sheet__'),
  columns jsonb not null default '[]'::jsonb check(jsonb_typeof(columns)='array'),
  revision integer not null default 0,
  updated_by uuid references public.portal_users(id) on delete set null,
  updated_at timestamptz not null default now()
);
alter table public.store_hours_sheet_settings enable row level security;
revoke all on public.store_hours_sheet_settings from public,anon,authenticated;
insert into public.store_hours_sheet_settings(id) values(true);
alter table public.store_hours_versions drop constraint store_hours_versions_kind_check;
alter table public.store_hours_versions add constraint store_hours_versions_kind_check
  check(kind in ('review','legacy_review','employee','schedule','source','sheet'));
create trigger version_store_sheet_settings after insert or update or delete on public.store_hours_sheet_settings
for each row execute function public.capture_store_hours_version('sheet');
-- Removed custom columns remain in the settings archive; prior values and versions remain intact.
