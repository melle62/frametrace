# Data collection

Frametrace collects every capture and comparison its users agree to share, keeps all of it in
a public dataset, and lets only the reliable part into the game skills. Collecting is cheap and
a run nobody kept can't be collected later; judging quality happens afterwards, with all the
data in view. What's sent and how to delete it, in plain words: [PRIVACY.md](../PRIVACY.md).

```
Frametrace window ── share ──▶ inbox (Supabase, Stockholm)
  asks once, then every          submissions, deletions, private CSV bucket
  capture and comparison                │
                                        │ daily export (GitHub Actions, OIDC)
                                        ▼
                         melle62/frametrace-data
                           data branch: one JSON per submission (no history)
                           releases csv-YYYY-MM: the CSVs
                                        │
                                        │ weekly: tools/aggregate.py (frametrace/quality.py)
                                        ▼
                         skills/frametrace-<game>/SKILL.md
                           "Community data" table, as a PR to main
```

## 1. In the window (`frametrace/share.py`)

- **Consent.** The banner asks once (`settings.json` `share`: null → true/false, plus
  `share_version`). Raising `share.CONSENT_VERSION` asks people who said yes again; people who
  said no aren't asked again. The rail has the toggle, the foot shows the state ("12 shared",
  "retries later") and **Delete my shared data**.
- **What's sent.** `capture_bundle(result)` is `result.json` with these changes: the start time
  in UTC; `capture.other_presenters` becomes a count; `capture.foreground` becomes
  `foreground_is_game`; `game.window_title` and the CLI's `capture.source` go; `system.errors`
  becomes a count; then every string is scrubbed (user folders → `<user>`, e-mail addresses,
  Steam IDs and `userdata\<id>` → `<account>`). Labels, groups, benchmark tags (`user.benchmark`, the scene the user named), `user.bundle` (the bundle the user dragged a run
  into in the captures list) and `user.advice` ("Changes suggested by" in Compare) are kept. `filtered_csv()` keeps the header and the rows of the
  game's process ID, gzipped, at most 50 MB.
- **Comparisons.** Opening a pair in Compare (or copying its prompt) notes it.
  `comparison_bundle()` holds both capture IDs, the game, the goal and target, the goal's status
  and verdict, the notes, every delta (A, B, change, status), the settings changed, whether
  they changed nothing yet results moved, the advice, whether it was copied, and each side's
  benchmark tag. A side that is a bundle is shared as the Compare view showed it, its runs
  combined: `a` / `b` is its newest run that counts, `a_runs` / `b_runs` every run that counts
  (oldest first; `null` for a single run), and the comparison's ID uses `bundle.<bundle id>`
  for that side.
- **Sending.** `Sharer.sync()` runs on a worker thread after start, after each capture, after
  label, group, bundle and advice edits, and after a comparison is noted. For each capture and
  comparison it compares the SHA-256 of the bundle with what it sent last (`shared.json`) and
  sends only what changed; a CSV is sent once. When the inbox answers `csv_deferred` (too many
  CSVs waiting for the export), the bundles keep going but CSVs wait 6 hours. A network or
  server error stops the round, and the rest goes next time (there is no separate queue). A
  refused bundle (HTTP 400/413) is skipped. HTTP 410 means the install's data was deleted: the
  state resets and a new random ID is used. **Delete my shared data** calls `forget`, resets
  the state and turns sharing off.
- **Transport.** urllib; when Python can't verify the certificate (debloated Windows), Windows'
  `curl.exe`, as the PresentMon download does. `FRAMETRACE_SHARE_URL` overrides the endpoint
  (empty turns sharing off, and the window then never asks).

## 2. The inbox (`server/supabase`)

Supabase project `frametrace` (eu-north-1). Tables `submissions`, `deletions` and `config`
have row level security on and no policies, so only the edge functions (service role) can
touch them. The `csv` bucket is private, 50 MB per file, `application/gzip` only.

| Function | Who calls it | What it does |
|---|---|---|
| `POST /functions/v1/share` | the app | `{install, kind, id, schema, app, data, csv?}`: validates (UUID v4, id pattern, schema 1, JSON ≤ 512 KB, CSV ≤ 50 MB), refuses deleted installs (410), allows 2,000 submissions per contributor per day (429), upserts by (contributor, kind, id), and for a new CSV returns a signed upload URL (2 h) that the app PUTs the gzip to, unless 40 of the contributor's or 250 CSVs in all from the last day are still waiting for the export (`csv_deferred`) |
| `POST /functions/v1/forget` | the app | `{install}`: deletes the install's rows and CSVs, puts its key on the deletions list |
| `POST /functions/v1/export` | the export workflow | `pull` (rows not exported yet, paged with an `after` cursor, signed CSV download URLs) and `ack` (marks rows exported if they didn't change since; archived CSVs are removed from the bucket). Accepts only a GitHub Actions OIDC token for `melle62/frametrace-data` on `refs/heads/main` |

**Contributor key**: HMAC-SHA256 of the install ID with a salt generated inside the database
(`config.contributor_salt`, never shown). The install ID itself isn't stored. The public
dataset uses the key's first 16 hex characters.

Free plan limits worth knowing: 500 MB database and 1 GB file storage. CSVs leave the bucket
at the daily export, and the caps above keep a day's worth (about 3 MB each) under the limit,
even when someone with hundreds of saved captures turns sharing on. Supabase pauses free
projects with too little database activity over 7 days (a few queries a day is enough, and it
e-mails a warning first); the daily export's queries keep it active.

## 3. The dataset (`melle62/frametrace-data`)

Its `tools/export.py` runs daily (and when the export's own code changes): pulls new rows,
writes `captures/<game>/<contributor>/<id>.json` and `comparisons/…/<a>~<b>.json`, uploads
each CSV as an asset of the month's `csv-YYYY-MM` release (900 assets per release, then
`csv-YYYY-MM-2`), removes deleted contributors' files and assets, writes `stats.json`,
commits the tree as a single new root commit and force-pushes `data`, then acknowledges. The
branch therefore has no history. The run fails (and GitHub sends a notice) if most
acknowledgements are refused. See that repository's README for the record format.

## 4. Quality (`frametrace/quality.py`)

All of these are computed from the captures themselves, never from what a client claims.

**Capture score** (0–100, weighted share of passed checks):

| Check | Weight | Passes when |
|---|---|---|
| settings read | 3 | the game's settings were read from its config |
| game identified | 2 | a store ID, or the name from Steam or the exe's version info |
| long enough | 2 | at least 30 s |
| clean run | 2 | at most 1% of the time in hitches |
| complete capture | 1 | PresentMon wasn't killed, at least 1,000 frames |
| labelled | 1 | the user gave a label, a group or a benchmark tag |
| system read | 1 | CPU and GPU known |

**A pair** (A, B) is *comparable* when it's the same game (and build, when both have one), the
same system (CPU, main GPU and driver, RAM speed), the same display mode (primary display
resolution and refresh, present mode), lengths within 10%, settings read in both, the same
benchmark tag (`user.benchmark`, case and spaces ignored; both untagged counts as the same), and
the same scene: the per-second FPS curves correlate at r ≥ 0.8 over at least 10 s. A comparable
pair is **usable for costs** when exactly one setting changed and both runs are clean; a
**baseline** when nothing changed; an **agreeing baseline** when the average and 1% low also
stayed inside run-to-run noise.

**A contributor** is *trusted* when they have at least one agreeing baseline pair or three
usable one-change pairs, and their captures average at least 60. Otherwise *contributing*
(or *new* without captures).

## 5. Into the skills (`tools/aggregate.py`)

Pairs come from three places, all per contributor:

- **Comparisons people opened**, with a bundled side combined from its `a_runs` / `b_runs`.
- **Consecutive setups of the same game and benchmark.** A setup is a row of the captures list:
  a single run, or a bundle (`user.bundle`) with its runs combined as the window combines them
  (`feed.combine`, a run that disagrees with the rest beyond noise left out). A bundle whose
  runs differ in settings, system, display, length or benchmark counts as its single runs.
  Runs of another benchmark are another scene, so Mirage runs never pair with Dust runs.
- **The runs inside each bundle**, one after another: repeats of one setup, so baselines.

Only usable pairs from trusted contributors count, grouped by
(setting, A value, B value). Per group, each contributor's runs are reduced to their median
first, then the median across contributors goes in the table, so one prolific contributor
can't outvote the rest. The table (between the `frametrace:community-data` markers in each
game skill and the template) shows runs, people, the change in average FPS, 1% low, CPU-side
1% low, GPU busy and PC latency, and the GPUs and resolutions behind it. The shared rules tell
the AI how to weigh it (similar hardware and more people first).

```
python tools/aggregate.py --data <checkout of the data branch>            # write the tables
python tools/aggregate.py --data <checkout> --check                       # exit 1 if stale
python tools/aggregate.py --data <checkout> --report                      # levels, pairs per benchmark
```

`.github/workflows/aggregate.yml` runs it every Monday and opens a PR when a table changed.
It needs **Settings → Actions → General → Allow GitHub Actions to create and approve pull
requests** turned on in this repository.

## Changing what's collected

Add the field to `capture_bundle()` or `comparison_bundle()` (and its test), describe it in
PRIVACY.md, and raise `share.CONSENT_VERSION` if people would want to know before it's sent.
Bump `share.SCHEMA` (and the server's `SCHEMA`) only for a change old readers can't handle.
