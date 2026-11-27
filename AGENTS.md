# AGENTS.md: Frametrace for AI agents

Read this before you change anything. Grok Build and other coding agents load this file on
their own. Grok Bot: read it from
`https://raw.githubusercontent.com/melle62/frametrace/main/AGENTS.md`.

Frametrace is built by one person, Melvin (GitHub `melle62`), working with two AIs: Claude and
Grok Bot. Section 9 says who does what. Melvin decides and merges; you propose.

## 1. What Frametrace is

An open-source, lightweight game benchmark for Windows that tells you **which in-game settings
to change** for a goal you pick. It is a tuning tool, not a bottleneck finder.

1. Pick a goal: higher average FPS, higher 1% lows, lower latency, less stutter, or a target
   FPS at the best quality (`goals.py`: `avg_fps`, `lows`, `latency`, `stutter`, `target`).
2. Benchmark a repeatable scene with a hotkey (Intel PresentMon records every frame).
3. Frametrace names the game, reads its current graphics settings where it can, and writes one
   report that is a **ready-made AI prompt**: goal, task, numbers, game, settings, evidence.
4. The user pastes it into any AI and gets one short answer block: 1-3 changes, one per run.
5. Change one setting, capture the same scene again, compare. The comparison says whether B is
   better for the goal (outside run-to-run noise) and asks the AI for the next step.

Stack: Python, **stdlib only** (the tkinter window, sharing and Windows APIs included),
wrapping the PresentMon console 2.6.0. MIT. Alpha.

## 2. Current state (2026-11-27)

- `main` has PR #13 (merged 2026-11-27). `pytest` on Linux: 143 pass, 6 skip (Tk and
  Windows-only).
- The captures list (`feed.py`): one row per run, named after what changed from the row
  before, measured against a base; each game has a profile page. Checked on Windows by Cursor
  (2026-11-27, PR #8): the right-click menus and the real CS2 list (no separate `CS2.EXE`
  heading). 125% and 150% were only simulated in code; real Windows scaling is still task 3.
- Since PR #11, runs don't stack on their own: the user drags a run onto another to bundle
  repeats (`user.bundle` in `result.json`), a bundle opens as a tree of its runs, and rows drag
  out of bundles and between groups. Not checked on Windows yet: dragging with a real mouse,
  the tree at 125% and 150%.
- Since PR #13, the rail reads as a tree (heading → runs and bundles → a bundle's runs), the
  goal sits in the action row next to Copy instead of the rail, RECORDING folds, names wrap,
  and the rail's width drags (280-640 px). Not checked on Windows yet: guide lines and chevrons
  at 100%, 125% and 150%, clicking a bundle's chevron, the goal controls at narrow widths,
  dragging the rail's edge, two- and three-line rows.
- Benchmark tags (`user.benchmark` in `result.json`): the rail's Benchmark field tags the next
  captures with the scene ("Mirage Benchmark"); its list holds every tag captures already have,
  and right-click › Benchmark retags runs. Each tag gets its own base, and a row is named after
  the change from the run of the same benchmark before it. Not checked on Windows yet.
- Live services: a Supabase inbox (project `frametrace`, eu-north-1) receives opt-in shared
  captures; a daily export (02:23 UTC) publishes them to `melle62/frametrace-data`; a weekly
  workflow (Mondays 04:41 UTC) opens a PR that updates the game skills' community-data tables.
- Skills: `frametrace` (general, runs game studies) and `frametrace-cs2` (tested on one PC).
- Not yet: game skills for DayZ and Forza Horizon 6, a settings reader for Forza Horizon 6
  (ForzaTech), settings readers checked on a real Unreal or Unity game, a packaged `.exe`.

## 3. Hard rules

CI, the tests and the PR template check most of these. Breaking one means the PR won't merge.

1. **No game-specific code in `frametrace/`.** The core works from PresentMon data and system
   info only. Settings readers are per engine (Source 2, Unreal, Unity), never per game. Game
   knowledge lives in `skills/frametrace-<game>/SKILL.md`.
2. **PresentMon column names only in `frametrace/columns.py`.** Everything else uses its
   canonical names. PresentMon has three CSV schemas; `columns.py` detects them from the header.
3. **Stdlib only at runtime.** Ask Melvin in an issue before adding any dependency. Dev-only
   tools may use `pytest`, `ruff`, `pillow`, `fonttools`, `uharfbuzz`.
4. **Python 3.10 compatible.** CI runs 3.10 and 3.13; the dev PC runs 3.15. No `tomllib`, no
   `ExceptionGroup`/`except*`, no `type X = ...`, no `def f[T]` generics.
5. **`result.json` is a contract.** Reports and comparisons render from saved result dicts only,
   so captures from older versions must still open, render and compare. New fields are
   optional; readers use `.get()` with a sensible default. Edits to a saved `result.json` go
   through `result.json.tmp` and `os.replace`.
6. **Generated files are never edited by hand:** `frametrace/skill_index.py` and the shared-rules
   copies in game skills (`python tools/sync_skills.py`), the `frametrace:community-data`
   tables (`tools/aggregate.py`), README images (`tools/window_shots.py`, `tools/brand.py`).
7. **The answer templates** `report.REPORT_ANSWER` and `report.COMPARE_ANSWER` must equal the
   templates in `skills/frametrace/SKILL.md`, every line under 56 characters
   (`tests/test_skills.py`).
8. **Privacy.** Settings readers drop keys that look like accounts, IDs, tokens or e-mail, and
   values with paths, `@` or over 60 characters; user folders become `%USERPROFILE%`. Changing
   what sharing sends means: the field in `share.capture_bundle()` or `comparison_bundle()`
   with a test, a line in `PRIVACY.md`, and `share.CONSENT_VERSION` raised if people would want
   to know first. Never commit keys, tokens or `.env` files.
9. **Only Melvin merges to `main`.** Work on a branch, open a PR, run `pytest` and
   `ruff check .` first.

Melvin's standing decisions (follow them, don't re-argue them):

- Skills change only through a PR Melvin merges. Measured numbers come from the daily shared
  data (`tools/aggregate.py`) or from runs Melvin names himself; research goes in tagged
  "guide" with a link. Don't put your own finding from one session into a skill; write it up
  and let Melvin decide.
- CS2: never suggest Dynamic Shadows "Sun Only" (a competitive disadvantage). Keep Boost
  Player Contrast on.
- Answers stay short: one code-fenced block, what to change and what the last change did.
- The UI stays "elegantly simple". Collect all shared data; only trusted data reaches skills.
- The goal stays out of the captures rail: it shapes the report for the AI, not the benchmark.
- Users will keep Discord running: recommend Discord settings that cut its cost, each one
  benchmarked first, instead of telling them to quit it.

## 4. Setup and commands (Windows, PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python tools/get_presentmon.py      # pinned PresentMon into bin/, SHA-256 checked
pytest
ruff check .                        # line length 100, target py310

python -m frametrace                # the window (or Frametrace.bat)
python -m frametrace report CAPTURE.csv --goal lows
python -m frametrace compare A B --goal target --target 144
python -m frametrace inspect CAPTURE.csv
python -m frametrace share-preview CAPTURE_FOLDER

python tools/sync_skills.py         # after editing the shared rules or a skill's process names
python tools/sync_skills.py --check
pip install pillow
python tools/window_shots.py shots  # every view, dark and light, from synthetic captures
```

Recording needs admin rights or membership of "Performance Log Users" (set up on the dev PC).
Captures are saved in `Documents\Frametrace\captures\<date>-<game>\` (raw CSV, `result.json`,
`report.md`, `trace.json`). Window settings: `%APPDATA%\Frametrace\settings.json`; sharing
state: `shared.json` next to it. `window_shots.py` never reads the user's real captures and
never talks to the server.

## 5. Code map

Data flow: hotkey → `capture` starts PresentMon → `process` picks the game → `columns` maps the
CSV → `analyze` computes stats → `game` and `gamesettings` identify the game and read its
settings → `report.build_result` saves `result.json` → `report` renders the prompt and
comparisons → `summary` words the window → `gui` shows it.

| Module | Job |
|---|---|
| `gui.py` | the window (2,850 lines, the main conflict hotspot) |
| `feed.py` | the captures list: rows, user bundles, names, bases, and the game profile |
| `theme.py`, `instruments.py` | design tokens; scope, readouts, lamps, buttons (`theme.px` scales for DPI) |
| `summary.py` | window wording, goal verdicts, settings changes, names and groups |
| `report.py` | the report as a prompt, checks, `result.json`, compare, answer templates |
| `goals.py` | the five goals: what each measures, asks for, and which metric decides "better" |
| `analyze.py` | frame stats, lows, hitches, bottleneck split, cap detection, PC latency |
| `columns.py`, `process.py`, `presentmon.py`, `download.py` | PresentMon schema, game pick, driving and downloading it |
| `capture.py`, `hotkey.py`, `trace.py` | recording controller, `RegisterHotKey`, the scope's compact trace |
| `game.py`, `gamesettings.py` | game name (Steam manifest, exe version, title), engine, settings readers |
| `sysinfo.py` | CPU, GPU, RAM vs kit, BIOS, displays, power plan, Game Mode, HAGS, memory integrity |
| `share.py`, `quality.py` | opt-in sharing (scrubbing, upload, delete); trust scores |
| `skill_index.py` | generated: process name → game skill, for the report's `Skill:` line |

Elsewhere: `skills/` (AI skills), `design/frametrace-design/` (design system), `server/supabase/`
(inbox: migrations and edge functions), `tools/` (setup, probe, sync, aggregate, images),
`docs/presentmon.md` (PresentMon findings, thresholds), `docs/data.md` (data pipeline).

Numbers to know: compare noise bands (from two identical CS2 runs) are 1% for average and
median, 3% for lows and P99, 5% for 0.1% low and worst second, 15% for max frame time, 0.2 pp
for hitch time, 3%/5% for PC latency median/P95, 3 pp for seconds at target. A hitch is a frame at least 2× the median of 30
neighbours on each side and at least 4 ms longer. GPU-limited means GPU busy ≥ 90% of the frame.

## 6. UI work

Read `design/frametrace-design/SKILL.md` and `references/components.md` first. The essentials:
warm graphite panels, **one yellow element per screen** (#F5C518: the trace, the primary button,
focus), cyan is always the GPU, magenta always the CPU, warnings orange (never yellow). IBM Plex
Sans for words, **Plex Mono for every number**. No gradients, no radius above 4 px, no shadows
on panels, no toasts, no hype words. Document a new component in `components.md`. Then run
`tools/window_shots.py shots` and look at every view in dark and light.

## 7. Skills and data

- `skills/frametrace/SKILL.md` holds the shared rules between `frametrace:shared-rules` markers.
  Edit them there only, then run `tools/sync_skills.py`.
- A new game gets a skill only after a game study meets the readiness bar in the general skill.
  Start from `skills/game-skill-template.md`. See `skills/README.md`.
- Measured numbers name the system, resolution, scene and runs. Guide claims say "guide" with a
  link. Everything else goes under "Not measured yet".
- Only one-change comparisons count as a setting's cost (`tools/aggregate.py`).

## 8. The dev PC

Ryzen 7 7800X3D, RTX 4070 Ti Super, 32 GB DDR5-5600, ASUS TUF B650-PLUS WIFI, a 1440p 280 Hz
OLED (primary) and a second monitor in portrait at 260 Hz, Windows 11 Home 26H2 (custom
debloated, memory integrity on), Python 3.15. On this debloated Windows, Python's HTTPS can fail
certificate checks: downloads and uploads fall back to `curl.exe` (hashes still checked). The
7800X3D's integrated Radeon shows up as a second GPU. CS2 is tested on FPSfrequency's FPS
Benchmark workshop map and on Anubis Deathmatch. Discord's Hardware Acceleration caused CS2's
hitchy runs (a hitch every ~105-110 ms; 1% low 229 FPS with Discord quit, 155 with it on, 214
with Hardware Acceleration off). The Grok Bot window draws ~224 frames/s: close it while
benchmarking.

## 9. Two AIs, one repo

| | Claude | Grok Bot |
|---|---|---|
| Runs in | claude.ai Project "Frametrace" and cloud sessions; on the dev PC (its files and screen) through the Claude desktop app while Melvin has it open | a cloud computer, also while the PC is off |
| Knows | the full history (the Project's handover doc), Melvin's skills, Supabase | this file, the public repo and dataset, the web |
| Does | big features end to end, design, skills, data analysis, reviews, the decision log, Windows checks on the dev PC | two Bots: Research (dataset + web → study logs) and Skills (study logs → PRs on `skills/`) |
| Can't | in a cloud session: run the window, PresentMon or a game (Linux, no GPU) | run Frametrace or a game; touch app code |

How work moves between them:

1. **The pull request is the handoff.** Its description says: what changed and why; how it was
   tested (commands, and "on Windows: yes/no"); **Not checked on Windows** (a list: Claude goes
   through it on the dev PC, or Melvin does); follow-ups; and `Made with: Claude | Grok Bot`.
2. **One agent per branch.** Never commit to another agent's branch unless Melvin asks.
   Branch names: `feature/<slug>` or `fix/<slug>`.
3. **Check before you start.** `git fetch`, then look at open PRs. If one touches the files you
   need (above all `gui.py`, `report.py`, `summary.py`, `skills/frametrace/SKILL.md`), stop and
   ask Melvin, or build on that branch with his OK.
4. **Small PRs, rebased on `main`** before review. Claude reviews big or risky PRs, and the
   Skills Bot's, when Melvin pastes the link into the Claude Project.
5. **Keep this file true.** A PR that changes the state in section 2, a rule or a command
   updates this file in the same PR. Claude keeps the long log in the Project's handover doc.
6. **Grok Bots stay in their lanes.** The Research Bot only reads (the dataset, the web) and
   keeps one study log per game in the general skill's format, every entry tagged measured
   (community), seen (dataset), guide (with a link) or unknown. The Skills Bot turns those logs
   into PRs that change `skills/` only (through a Cursor cloud agent, after Melvin's OK):
   never app code, never the community-data tables.
   Measured numbers in a skill still come only from `tools/aggregate.py`.

## 10. Task queue

**Windows and real hardware** (Claude on the dev PC through the Claude desktop app, or a
checklist Melvin runs; code-only Windows work is tested on CI's `windows-latest`), roughly in
order:

1. Windows checks of PRs: `pytest` (GUI tests included) on the dev PC's Python 3.15, then the
   PR's "Not checked on Windows" list, reported in the PR. Open now: PR #11's and PR #13's
   lists (section 2), plus bundling the 7800X3D baselines again.
2. Labels, groups and delete to the Recycle Bin (`SHFileOperationW`) on Windows; the
   `TextDialog` title bar.
3. The window on real hardware: light mode, 125% and 150% scaling, the Game tab, Compare with
   real captures, the sharing foot row.
4. Settings readers on a real Unreal game and a real Unity game installed on the PC: find the
   files, compare with what Frametrace reads, fix the reader (per engine, not per game).
5. CH2 drawn under CH1 on GPU-limited captures (check by toggling CH1 off).
6. HAGS state through D3DKMT (ctypes), since its registry value is missing on the dev PC.
7. Later: package as an `.exe` with PyInstaller (PresentMon, its notices, fonts, icon).

**Claude:** the Windows queue above; review the Skills Bot's PRs; game studies for DayZ and
Forza Horizon 6 with the general skill (Melvin does the runs); next engine readers (ForzaTech
for FH6 first: the file and its menu map are in the Project doc `claude/frametrace-fh6-config.md`);
data checks after exports; the handover doc.

**Grok Bot, Research:** a daily digest of the shared dataset (06:10 Stockholm, after the export)
and a weekly game-research run (Forza Horizon 6, then DayZ, then CS2 updates). Its "Not
measured yet" run plans are Melvin's benchmark queue. Engine findings go to its Reader notes,
which become per-engine settings readers here.

**Grok Bot, Skills:** plans changes to `skills/` from the study logs, waits for Melvin's OK in
chat, then hands each one to a Cursor cloud agent, which opens one PR per game (branch
`feature/skill-<slug>-<date>`) after `tools/sync_skills.py --check`, `pytest` and
`ruff check .`. Claude reviews each PR, then Melvin verifies and merges. No GitHub token sits
on the Bots' shared computer; a ruleset on `main` requires a pull request.

## 11. Ideas, not decided

Don't build these without Melvin's go. Open an issue or ask.

- A local MCP server in Frametrace that gives an AI a live performance feed while playing (F10
  start/stop): the AI suggests a setting, the run is captured, results go into the app's data
  and are shared if sharing is on. Meant especially for games like DayZ with no good benchmark.
- Typing or pasting in-game settings into Frametrace for games without a reader.
- A capture note when hitches repeat at a steady interval (seen in CS2: one every ~105 ms,
  from Discord's Hardware Acceleration), and an app check that names other apps drawing frames
  during a capture (already in PresentMon's CSV).
- Pinning a base in Compare; showing scene correlation and a contributor's quality level.
- Flagging an enabled integrated GPU; filtering cosmetic Source 2 `r_` convars.
- The AI's answer as a styled card; skills that read a pasted "Frametrace profile" (PR #8).
- Pro features later: built-in AI analysis with an API key, saved history and graphs.

## 12. Writing

Plain English, short sentences. Claim first, then the number, with its unit. No hype ("blazing",
"ultimate", "insane"). Commit subjects describe the outcome in sentence case, no prefix, no
trailing period, for example "Skip shipped convar defaults; correct the CS2 results".
