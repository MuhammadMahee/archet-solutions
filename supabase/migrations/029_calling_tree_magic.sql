-- MAGIC stores can appear in the Calling Tree without an RT-POS source.
alter table public.calling_tree_stores drop constraint calling_tree_stores_dealer_check;
alter table public.calling_tree_stores add constraint calling_tree_stores_dealer_check
  check (dealer in ('Connect', 'California', 'SRH', 'AMQ', 'ARM', 'ARBF', 'MAGIC'));

alter table public.quota_uploads drop constraint quota_uploads_dealer_check;
alter table public.quota_uploads add constraint quota_uploads_dealer_check
  check (dealer in ('Connect', 'California', 'SRH', 'AMQ', 'ARM', 'ARBF', 'MAGIC'));
