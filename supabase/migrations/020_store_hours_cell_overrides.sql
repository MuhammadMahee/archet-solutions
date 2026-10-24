-- Corrections stay attached to the original imported row and survive source re-syncs.
alter table public.store_hours_employee_reviews add column cell_overrides jsonb not null default '{}'::jsonb
  check(jsonb_typeof(cell_overrides)='object');
create index store_hours_review_corrected_date on public.store_hours_employee_reviews ((cell_overrides->>'date'));
-- The existing immutable version trigger captures the entire row, including corrections.
