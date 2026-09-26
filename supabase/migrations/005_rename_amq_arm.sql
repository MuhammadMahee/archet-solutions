-- Rename dealer labels in every Calling Tree version; retain source identities.
select pg_advisory_xact_lock(731044);
alter table public.calling_tree_stores
  drop constraint calling_tree_stores_dealer_check;

update public.calling_tree_stores
set dealer = case dealer when 'ARM1' then 'AMQ' when 'ARM2' then 'ARM' end
where dealer in ('ARM1', 'ARM2');

alter table public.calling_tree_stores add constraint calling_tree_stores_dealer_check
  check (dealer in ('Connect', 'California', 'SRH', 'AMQ', 'ARM', 'ARBF'));
