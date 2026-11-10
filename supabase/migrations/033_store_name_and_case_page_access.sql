-- Keep store identities and schedules intact when correcting the display name.
update public.calling_tree_stores set store='109 MARTHA ST SUITE 227' where upper(btrim(store))='EULESS';
update public.store_hours_directory set store='109 MARTHA ST SUITE 227',updated_at=now() where upper(btrim(store))='EULESS';
update public.store_time_punches set store='109 MARTHA ST SUITE 227' where upper(btrim(store))='EULESS';
update public.sales_performance set store='109 MARTHA ST SUITE 227' where upper(btrim(store))='EULESS';
update public.store_hours_employee_reviews set cell_overrides=jsonb_set(cell_overrides,'{store}','"109 MARTHA ST SUITE 227"'),revision=revision+1
  where upper(btrim(cell_overrides->>'store'))='EULESS';
update public.compliance_employee_reviews set cell_overrides=jsonb_set(cell_overrides,'{store}','"109 MARTHA ST SUITE 227"'),revision=revision+1
  where upper(btrim(cell_overrides->>'store'))='EULESS';

alter table public.portal_users drop constraint portal_page_access_valid;
alter table public.portal_users add constraint portal_page_access_valid check (
  page_access is null or (cardinality(page_access)<=12 and array_position(page_access,null) is null and
  page_access <@ array['sales','spreadsheet','compliance','quota','callingtree','workforce','overview','quotes','users','cases','inbox','case-report']::text[])
);
-- Preserve everyone's current case access as these pages become configurable.
update public.portal_users set page_access=array(select distinct p from unnest(
  page_access || array['cases','inbox']::text[] || case when role='admin' then array['case-report']::text[] else array[]::text[] end
) as p) where page_access is not null;
