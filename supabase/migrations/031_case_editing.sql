-- Keep submitted_by as the original creator for retry deduplication and audit.
-- A null sender_id means the original creator is still the displayed sender.
alter table public.violation_cases add column sender_id uuid references public.portal_users(id);
alter table public.violation_cases add column edited_by uuid references public.portal_users(id);
alter table public.violation_cases add column edited_at timestamptz;
alter table public.violation_cases add column deleted_by uuid references public.portal_users(id);
alter table public.violation_cases add column deleted_at timestamptz;
create index violation_cases_current_sender on public.violation_cases
  ((coalesce(sender_id,submitted_by)),submitted_at desc);

create table public.case_edits (
  id bigint generated always as identity primary key,
  case_id uuid not null references public.violation_cases(id) on delete cascade,
  edited_by uuid not null references public.portal_users(id),
  edited_at timestamptz not null default now(),
  changed_fields text[] not null,
  before_state jsonb not null,
  after_state jsonb not null
);
create index case_edits_case on public.case_edits(case_id,id);
alter table public.case_edits enable row level security;
revoke all on public.case_edits from public,anon,authenticated;
grant all on public.case_edits to service_role;
grant usage,select on sequence public.case_edits_id_seq to service_role;
