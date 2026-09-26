-- Keep existing Calling Tree versions and source sales history intact.
select pg_advisory_xact_lock(731044);
alter table public.calling_tree_stores
  drop constraint calling_tree_stores_dealer_check;

update public.calling_tree_stores
set dealer = case
  when regexp_replace(lower(original_dealer), '[^a-z0-9]', '', 'g') in ('dfwireless', 'arm1') then 'ARM1'
  when regexp_replace(lower(original_dealer), '[^a-z0-9]', '', 'g') in ('armwireless', 'arm2') then 'ARM2'
  else dealer end
where dealer = 'ARM';

-- Older uploads using the generic ARM label can be resolved only when the
-- store belongs to exactly one source account. Never guess for shared IDs.
with accounts as (
  select store_id, upper(min(source_id)) as dealer
  from public.sales_performance
  where source_id in ('arm1', 'arm2')
  group by store_id having count(distinct source_id) = 1
)
update public.calling_tree_stores s set dealer = a.dealer
from accounts a where s.dealer = 'ARM' and s.store_id = a.store_id;

do $$
begin
  if exists (select 1 from public.calling_tree_stores where dealer = 'ARM') then
    raise exception 'Cannot split ambiguous Calling Tree ARM rows; set original_dealer to ARM1 or ARM2 first.';
  end if;
end $$;

alter table public.calling_tree_stores add constraint calling_tree_stores_dealer_check
  check (dealer in ('Connect', 'California', 'SRH', 'ARM1', 'ARM2', 'ARBF'));
