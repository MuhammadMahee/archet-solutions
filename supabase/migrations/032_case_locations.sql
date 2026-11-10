-- Existing cases keep their original, unspecified location until an admin adds it.
alter table public.violation_cases add column dealer text not null default '';
alter table public.violation_cases add column store_id text not null default '';
alter table public.violation_cases add column store_name text not null default '';
