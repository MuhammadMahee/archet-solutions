-- NULL keeps existing accounts' role-based access until an administrator edits it.
alter table public.portal_users add column page_access text[];
alter table public.portal_users add constraint portal_page_access_valid check (
  page_access is null or (cardinality(page_access)<=8 and
  array_position(page_access,null) is null and
  page_access <@ array['sales','spreadsheet','quota','callingtree','workforce','overview','quotes','users']::text[])
);
