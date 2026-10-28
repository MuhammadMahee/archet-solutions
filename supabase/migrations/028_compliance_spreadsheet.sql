-- Separate editable sheet data; RTPOS imports and the store directory stay shared.
create table public.compliance_reviews (like public.store_hours_reviews including all);
alter table public.compliance_reviews enable row level security;
revoke all on public.compliance_reviews from public, anon, authenticated, service_role;
create table public.compliance_employee_reviews (like public.store_hours_employee_reviews including all);
alter table public.compliance_employee_reviews enable row level security;
revoke all on public.compliance_employee_reviews from public, anon, authenticated, service_role;
create table public.compliance_manual_employees (like public.store_hours_manual_employees including all);
alter table public.compliance_manual_employees enable row level security;
revoke all on public.compliance_manual_employees from public, anon, authenticated, service_role;
create table public.compliance_sheet_settings (like public.store_hours_sheet_settings including all);
alter table public.compliance_sheet_settings enable row level security;
revoke all on public.compliance_sheet_settings from public, anon, authenticated, service_role;
create table public.compliance_versions (like public.store_hours_versions including all);
alter table public.compliance_versions enable row level security;
revoke all on public.compliance_versions from public, anon, authenticated, service_role;
create table public.compliance_live_revision (like public.store_hours_live_revision including all);
alter table public.compliance_live_revision enable row level security;
revoke all on public.compliance_live_revision from public, anon, authenticated, service_role;
create table public.compliance_presence (like public.store_hours_presence including all);
alter table public.compliance_presence enable row level security;
revoke all on public.compliance_presence from public, anon, authenticated, service_role;
alter table public.compliance_presence add foreign key(user_id) references public.portal_users(id) on delete cascade;
alter table public.compliance_presence add foreign key(session_hash) references public.portal_sessions(token_hash) on delete cascade;
insert into public.compliance_sheet_settings(id) values(true);
insert into public.compliance_live_revision(id) values(true);
revoke all on sequence public.compliance_versions_id_seq from public,anon,authenticated,service_role;
create trigger protect_compliance_versions before update or delete or truncate on public.compliance_versions
for each statement execute function public.block_store_hours_version_mutation();
alter table public.compliance_versions enable always trigger protect_compliance_versions;
create function public.record_compliance_version(p_kind text,p_operation text,p_before jsonb,p_after jsonb)
returns void language plpgsql security definer set search_path=pg_catalog,public as $$
declare
  doc jsonb := coalesce(p_after,p_before);
  actor text;
  actor_label text;
  store_label text;
  market_label text;
  employee_label text;
begin
  actor := coalesce(nullif(current_setting('archet.store_hours_actor',true),''),doc->>'updated_by',doc->>'created_by');
  select display_name || ' (@' || username || ')' into actor_label from public.portal_users where id::text=actor;
  select s.store,s.market into store_label,market_label from public.store_hours_directory s
    where s.dealer=doc->>'dealer' and s.store_id=doc->>'store_id';
  if store_label is null then
    select s.store,s.market into store_label,market_label from public.calling_tree_stores s
      join public.calling_tree_versions v on v.id=s.version_id and v.status='active'
      where s.dealer=doc->>'dealer' and s.store_id=doc->>'store_id' limit 1;
  end if;
  employee_label := coalesce(doc->>'employee',nullif(current_setting('archet.store_hours_employee',true),''),
    nullif(regexp_replace(coalesce(doc->>'employee_key',''),'^person:',''),''),'-');
  insert into public.compliance_versions(kind,operation,dealer,store_id,store,market,report_date,
    employee_key,employee,actor_id,actor_name,before_data,after_data)
    values(p_kind,p_operation,doc->>'dealer',doc->>'store_id',coalesce(doc->>'store',store_label,doc->>'store_id'),
      coalesce(doc->>'market',market_label,''),(doc->>'report_date')::date,doc->>'employee_key',employee_label,
      actor,coalesce(actor_label,case when p_operation='BASELINE' then 'Existing data' else 'Database change' end),p_before,p_after);
end;
$$;
revoke all on function public.record_compliance_version(text,text,jsonb,jsonb) from public,anon,authenticated,service_role;

create function public.capture_compliance_version() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
declare prior jsonb; current_doc jsonb;
begin
  if tg_op<>'INSERT' then prior:=to_jsonb(old); end if;
  if tg_op<>'DELETE' then current_doc:=to_jsonb(new); end if;
  -- Workbook reuploads with identical data do not create redundant versions.
  if tg_argv[0]='schedule' and prior-'updated_at'=current_doc-'updated_at' then return null; end if;
  perform public.record_compliance_version(tg_argv[0],tg_op,prior,current_doc);
  return null;
end;
$$;
revoke all on function public.capture_compliance_version() from public,anon,authenticated,service_role;
create trigger version_employee_review after insert or update or delete on public.compliance_employee_reviews
for each row execute function public.capture_compliance_version('review');
create trigger version_legacy_review after insert or update or delete on public.compliance_reviews
for each row execute function public.capture_compliance_version('legacy_review');
create trigger version_manual_employee after insert or update or delete on public.compliance_manual_employees
for each row execute function public.capture_compliance_version('employee');
create trigger version_compliance_store_schedule after insert or update or delete on public.store_hours_directory
for each row execute function public.capture_compliance_version('schedule');

-- Snapshot each store/day only after a successful source import. Identical syncs do not add versions.
create function public.capture_compliance_source(p_source text,p_day date,p_operation text default 'SYNC')
returns void language plpgsql security definer set search_path=pg_catalog,public as $$
declare
  dealer_label text := case p_source when 'connect' then 'Connect' when 'california' then 'California'
    when 'srh' then 'SRH' when 'arm1' then 'AMQ' when 'arm2' then 'ARM' when 'arbf' then 'ARBF' end;
  sid text; prior jsonb; current_doc jsonb; punches jsonb;
begin
  for sid in
    select p.store_id from public.store_time_punches p where p.source_id=p_source and p.report_date=p_day
    union select v.store_id from public.compliance_versions v where v.kind='source' and v.dealer=dealer_label and v.report_date=p_day
  loop
    prior:=null;
    select v.after_data into prior from public.compliance_versions v
      where v.kind='source' and v.dealer=dealer_label and v.store_id=sid and v.report_date=p_day order by v.id desc limit 1;
    select coalesce(jsonb_agg(jsonb_build_object('employee',p.employee,'clock_in',p.clock_in,'clock_out',p.clock_out,
      'store',p.store,'market',p.market) order by p.clock_in,p.employee,p.punch_key),'[]'::jsonb)
      into punches from public.store_time_punches p where p.source_id=p_source and p.store_id=sid and p.report_date=p_day;
    current_doc:=jsonb_build_object('source_id',p_source,'dealer',dealer_label,'store_id',sid,'report_date',p_day,
      'store',coalesce(punches->0->>'store',prior->>'store',sid),'market',coalesce(punches->0->>'market',prior->>'market',''),'punches',punches);
    if current_doc is distinct from prior then
      insert into public.compliance_versions(kind,operation,dealer,store_id,store,market,report_date,actor_name,before_data,after_data)
        values('source',p_operation,dealer_label,sid,current_doc->>'store',current_doc->>'market',p_day,
          case when p_operation='BASELINE' then 'Existing RT-POS data' else 'RT-POS sync' end,prior,current_doc);
    end if;
  end loop;
end;
$$;
revoke all on function public.capture_compliance_source(text,date,text) from public,anon,authenticated,service_role;
create function public.capture_compliance_import() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
begin
  if new.status='complete' then perform public.capture_compliance_source(new.source_id,new.report_date); end if;
  return null;
end;
$$;
revoke all on function public.capture_compliance_import() from public,anon,authenticated,service_role;
create trigger version_compliance_source_import after insert or update on public.store_hours_imports
for each row execute function public.capture_compliance_import();

create trigger version_compliance_sheet after insert or update or delete on public.compliance_sheet_settings
for each row execute function public.capture_compliance_version('sheet');
create function public.advance_compliance_live_revision() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
begin
  update public.compliance_live_revision set revision=revision+1 where id=true;
  return null;
end;
$$;
revoke all on function public.advance_compliance_live_revision() from public,anon,authenticated,service_role;
create trigger compliance_live_versions after insert on public.compliance_versions
for each statement execute function public.advance_compliance_live_revision();
create trigger compliance_live_imports after insert or update or delete on public.store_hours_imports
for each statement execute function public.advance_compliance_live_revision();
create trigger compliance_live_directory after insert or update or delete on public.calling_tree_versions
for each statement execute function public.advance_compliance_live_revision();
-- Include the shared source and store baseline without copying opening/closing reviews.
select public.record_compliance_version('schedule','BASELINE',null,to_jsonb(r)) from public.store_hours_directory r;
select public.capture_compliance_source(p.source_id,p.report_date,'BASELINE') from
  (select distinct source_id,report_date from public.store_time_punches) p;
alter table public.portal_users drop constraint portal_page_access_valid;
alter table public.portal_users add constraint portal_page_access_valid check (
  page_access is null or (cardinality(page_access)<=9 and array_position(page_access,null) is null and
  page_access <@ array['sales','spreadsheet','compliance','quota','callingtree','workforce','overview','quotes','users']::text[])
);
-- Existing spreadsheet users receive the matching new sheet; explicit denials stay denied.
update public.portal_users set page_access=array_append(page_access,'compliance')
where page_access is not null and 'spreadsheet'=any(page_access) and not ('compliance'=any(page_access));
