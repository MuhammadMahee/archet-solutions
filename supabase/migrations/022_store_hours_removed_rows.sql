-- Row removal is reversible and captured by the existing append-only review audit trigger.
alter table public.store_hours_employee_reviews
  add column removed boolean not null default false;
