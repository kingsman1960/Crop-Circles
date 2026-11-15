-- Saved crop plans, shared between planners. Run once in the Supabase SQL editor.
-- The app reads and writes with the secret key on the Streamlit server; RLS is on with no public policies,
-- so the publishable key in a browser cannot read or change anything.

create table if not exists public.crop_plans (
  id          bigint generated always as identity primary key,
  user_id     text        not null,                 -- the account that saved it (accounts.user() id or e-mail)
  field_id    text        not null,                 -- demo block (F1, F2 ...) or another field id
  year        int         not null check (year between 2026 and 2040),
  plots       jsonb       not null,                 -- GeoJSON features: geometry + {id, ha, plan}
  updated_at  timestamptz not null default now(),
  unique (user_id, field_id, year)
);

create index if not exists crop_plans_year on public.crop_plans (year);

alter table public.crop_plans enable row level security;
-- no policies: only the server's secret key (which bypasses RLS) can read and write
