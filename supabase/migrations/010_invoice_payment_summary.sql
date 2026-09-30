-- Combine historical market advances into a single invoice-level payment.
alter table public.invoice_months
  add column advance_cents bigint not null default 0 check (advance_cents between 0 and 9999999999999),
  add column remark text not null default '' check (length(remark) <= 1000);
update public.invoice_months i
set advance_cents = coalesce((
      select sum(coalesce((r->>'advance_cents')::bigint, 0))
      from jsonb_array_elements(i.rows) r
    ), 0),
    revision = gen_random_uuid();
-- Days worked is stored in each JSON row. Missing historical values mean the full month.
