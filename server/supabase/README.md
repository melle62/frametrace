# Frametrace data server

The inbox behind "Share captures" in the Frametrace window (see `docs/data.md` and
`PRIVACY.md`). It runs on Supabase, project `frametrace` (eu-north-1, Stockholm).

- `migrations/`: the tables (`submissions`, `deletions`, `config`) and the private `csv` bucket.
  Row level security is on with no policies: only the edge functions, which use the service
  role, can read or write.
- `functions/share`: the app uploads a capture or comparison bundle; for a capture's CSV it
  gets a signed upload URL.
- `functions/forget`: deletes everything one install shared and lists it for removal from
  the public dataset.
- `functions/export`: the daily export workflow of
  [melle62/frametrace-data](https://github.com/melle62/frametrace-data) pulls new rows and
  acknowledges them. It authenticates with a GitHub Actions OIDC token (no shared secret).

Deploy with the Supabase CLI (`supabase functions deploy <name> --no-verify-jwt`) or the
dashboard. All three run with JWT verification off: `share` and `forget` are public by
design (validated, size-capped, rate-limited per install), `export` checks its own token.
