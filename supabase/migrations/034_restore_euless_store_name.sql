-- Rename existing records in place. Keep the store IDs, schedules, and reviews.
update public.calling_tree_stores set store='EULESS'
  where upper(btrim(store)) in ('109 MARTHA ST SUITE 227','MARTHA');
update public.store_hours_directory set store='EULESS',updated_at=now()
  where upper(btrim(store)) in ('109 MARTHA ST SUITE 227','MARTHA');
update public.store_time_punches set store='EULESS'
  where upper(btrim(store)) in ('109 MARTHA ST SUITE 227','MARTHA');
update public.sales_performance set store='EULESS'
  where upper(btrim(store)) in ('109 MARTHA ST SUITE 227','MARTHA');
update public.store_hours_employee_reviews
  set cell_overrides=jsonb_set(cell_overrides,'{store}','"EULESS"'),revision=revision+1
  where upper(btrim(cell_overrides->>'store')) in ('109 MARTHA ST SUITE 227','MARTHA');
update public.compliance_employee_reviews
  set cell_overrides=jsonb_set(cell_overrides,'{store}','"EULESS"'),revision=revision+1
  where upper(btrim(cell_overrides->>'store')) in ('109 MARTHA ST SUITE 227','MARTHA');
update public.violation_cases set store_name='EULESS',revision=revision+1
  where upper(btrim(store_name)) in ('109 MARTHA ST SUITE 227','MARTHA');
