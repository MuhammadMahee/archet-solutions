-- Preserve every monthly invoice while allowing multiple named invoices per month.
alter table public.invoice_months add column id uuid not null default gen_random_uuid();
alter table public.invoice_months add column name text;
alter table public.invoice_months add column legacy_month text unique;
update public.invoice_months
set name = 'Invoice - ' || to_char(to_date(month || '-01', 'YYYY-MM-DD'), 'FMMonth YYYY'),
    legacy_month = month;
alter table public.invoice_months alter column name set not null;
alter table public.invoice_months add constraint invoice_name_length check (length(btrim(name)) between 1 and 120);
alter table public.invoice_months drop constraint invoice_months_pkey;
alter table public.invoice_months add primary key (id);
create index invoice_months_updated_idx on public.invoice_months (updated_at desc, id desc);

-- Literal, case-insensitive name search; invoice rows never enter list responses.
create function public.list_saved_invoices(p_query text, p_month text, p_offset integer)
returns table (id uuid, name text, month text, updated_at timestamptz)
language sql stable security invoker set search_path = '' as $$
  select i.id, i.name, i.month, i.updated_at
  from public.invoice_months i
  where strpos(lower(i.name), lower(p_query)) > 0
    and (p_month = '' or i.month = p_month)
  order by i.updated_at desc, i.id desc
  limit 21 offset greatest(p_offset, 0)
$$;
revoke all on function public.list_saved_invoices(text, text, integer) from public, anon, authenticated;
grant execute on function public.list_saved_invoices(text, text, integer) to service_role;
