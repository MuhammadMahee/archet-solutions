-- A committed, transactional change token. Unlike max(version id), this cannot
-- miss an earlier-started writer that commits after another writer.
create table public.store_hours_live_revision (
  id boolean primary key default true check(id),
  revision bigint not null default 0
);
insert into public.store_hours_live_revision(id) values(true);
alter table public.store_hours_live_revision enable row level security;
revoke all on public.store_hours_live_revision from public,anon,authenticated,service_role;

create function public.advance_store_hours_live_revision() returns trigger
language plpgsql security definer set search_path=pg_catalog,public as $$
begin
  update public.store_hours_live_revision set revision=revision+1 where id=true;
  return null;
end;
$$;
revoke all on function public.advance_store_hours_live_revision() from public,anon,authenticated,service_role;
create trigger store_hours_live_versions after insert on public.store_hours_versions
for each statement execute function public.advance_store_hours_live_revision();
create trigger store_hours_live_imports after insert or update or delete on public.store_hours_imports
for each statement execute function public.advance_store_hours_live_revision();
create trigger store_hours_live_directory after insert or update or delete on public.calling_tree_versions
for each statement execute function public.advance_store_hours_live_revision();
