alter table public.quota_goals
  add column upgrade_goal numeric(14,2) not null default 0 check (upgrade_goal >= 0);
