-- Invoice data is accessible only through the server's Mahee-only routes.
create table public.invoice_months (
  month text primary key check (month ~ '^20[0-9]{2}-(0[1-9]|1[0-2])$'),
  rows jsonb not null default '[]'::jsonb check (jsonb_typeof(rows) = 'array' and jsonb_array_length(rows) <= 100),
  revision uuid not null default gen_random_uuid(),
  updated_at timestamptz not null default now()
);
alter table public.invoice_months enable row level security;
revoke all on public.invoice_months from public, anon, authenticated;
grant select, insert, update on public.invoice_months to service_role;
