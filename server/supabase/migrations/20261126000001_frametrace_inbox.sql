-- Frametrace data inbox. Only the edge functions (service role) read or write these tables:
-- RLS is on and there are no policies, so the anon and authenticated roles get nothing.

create table public.submissions (
  id uuid primary key default gen_random_uuid(),
  contributor text not null check (contributor ~ '^[0-9a-f]{64}$'),  -- HMAC of the install ID
  kind text not null check (kind in ('capture', 'comparison')),
  local_id text not null check (local_id ~ '^[A-Za-z0-9._~-]{1,170}$'),
  schema int not null,
  app_version text,
  game text,
  exe text,
  store_id text,
  build text,
  gpu text,
  cpu text,
  data jsonb not null,
  data_sha256 text not null,
  csv_path text,
  csv_sha256 text,
  csv_bytes bigint,
  csv_state text not null default 'none' check (csv_state in ('none', 'pending', 'stored', 'archived')),
  csv_archive text,  -- where the export put the CSV (release and asset name)
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  exported_at timestamptz,
  unique (contributor, kind, local_id)
);

create index submissions_to_export on public.submissions (updated_at) where exported_at is null;
create index submissions_contributor_recent on public.submissions (contributor, updated_at);
create index submissions_exe on public.submissions (exe);

-- Contributors who asked for their data to be deleted; the export removes them from the
-- public dataset. Only the HMAC is kept, never the install ID.
create table public.deletions (
  contributor text primary key check (contributor ~ '^[0-9a-f]{64}$'),
  deleted_at timestamptz not null default now(),
  rows_deleted int not null default 0
);

alter table public.submissions enable row level security;
alter table public.deletions enable row level security;
revoke all on public.submissions from anon, authenticated;
revoke all on public.deletions from anon, authenticated;

-- Private bucket for the gzipped PresentMon CSVs (the game's rows only), 50 MB each.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('csv', 'csv', false, 52428800, array['application/gzip']);
