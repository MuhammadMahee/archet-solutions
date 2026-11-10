create table public.violation_cases (
  id uuid primary key default gen_random_uuid(),
  submitted_by uuid not null references public.portal_users(id),
  sender_name text not null,
  request_id uuid not null,
  violation_date date not null,
  employee_ntid text not null check (length(employee_ntid) between 1 and 80),
  employee_name text not null check (length(employee_name) between 1 and 150),
  case_type text not null check (length(case_type) between 1 and 150),
  subject text not null check (length(subject) between 1 and 200),
  body text not null check (length(body) between 1 and 20000),
  status text not null default 'pending' check (status in ('pending','approved','not_approved')),
  submitted_at timestamptz not null default now(),
  reviewed_by uuid references public.portal_users(id),
  reviewed_at timestamptz,
  revision integer not null default 1,
  unique (submitted_by,request_id)
);
create index violation_cases_date on public.violation_cases(violation_date,submitted_at desc);
create index violation_cases_sender on public.violation_cases(submitted_by,submitted_at desc);

create table public.case_recipients (
  case_id uuid not null references public.violation_cases(id) on delete cascade,
  user_id uuid not null references public.portal_users(id),
  kind text not null check (kind in ('to','cc')),
  recipient_name text not null,
  read_at timestamptz,
  primary key(case_id,user_id)
);
create index case_recipients_inbox on public.case_recipients(user_id,read_at,case_id);

create table public.case_attachments (
  id uuid primary key default gen_random_uuid(),
  case_id uuid not null references public.violation_cases(id) on delete cascade,
  filename text not null,
  content_type text not null check (content_type in ('image/jpeg','image/png','image/webp')),
  data bytea not null check (octet_length(data) between 1 and 2097152)
);
create index case_attachments_case on public.case_attachments(case_id);

create table public.case_reviews (
  id bigint generated always as identity primary key,
  case_id uuid not null references public.violation_cases(id) on delete cascade,
  reviewed_by uuid not null references public.portal_users(id),
  status text not null check (status in ('approved','not_approved')),
  reviewed_at timestamptz not null default now()
);

alter table public.violation_cases enable row level security;
alter table public.case_recipients enable row level security;
alter table public.case_attachments enable row level security;
alter table public.case_reviews enable row level security;
revoke all on public.violation_cases,public.case_recipients,public.case_attachments,public.case_reviews from public,anon,authenticated;
grant all on public.violation_cases,public.case_recipients,public.case_attachments,public.case_reviews to service_role;
grant usage,select on sequence public.case_reviews_id_seq to service_role;
