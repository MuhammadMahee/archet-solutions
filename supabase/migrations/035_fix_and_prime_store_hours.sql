-- Update the existing four stores in place, preserving identities and daily reviews.
update public.store_hours_directory
set schedules = schedules || '{
  "weekday": {"opening_time":"10:30:00","closing_time":"20:00:00"},
  "saturday": {"opening_time":"10:30:00","closing_time":"19:00:00"},
  "sunday": {"opening_time":"11:00:00","closing_time":"18:00:00"}
}'::jsonb,
updated_at = now()
where dealer in ('The Fix','California') and store_id in (
  'WB-19eb7cb164041a760fe55fcf', -- Harrisville
  'WB-2e007663729886bbb54cd4ba', -- Layton
  'WB-8a8b69c953dd842faf22e664', -- Riverdale
  'WB-d124d4044ff293446a2035c8'  -- Prime
);
