-- Server-side settings the edge functions read with the service role. The contributor salt is
-- generated here and never leaves the database: it turns an install ID into the contributor
-- key (HMAC-SHA256), so the public dataset can't be linked back to an install.
create table public.config (
  key text primary key,
  value text not null
);
alter table public.config enable row level security;
revoke all on public.config from anon, authenticated;

insert into public.config (key, value)
values ('contributor_salt', encode(extensions.gen_random_bytes(32), 'hex'));
