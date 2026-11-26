# Contributing to Frametrace

Thanks for helping! There are four ways in, from easiest to most involved.

## 0. Share your captures (one click)

Turn on **Share captures with the dataset** in the window (it asks on first start). Every
capture and comparison goes to the public [Frametrace dataset](https://github.com/melle62/frametrace-data);
see [PRIVACY.md](PRIVACY.md) for what is and isn't sent. All of it is kept, but only runs that
pass the quality checks reach the game skills' **Community data** tables
([docs/data.md](docs/data.md), "Quality"). To make yours count:

- Label your runs (right-click > Rename, or <kbd>F2</kbd>), so a person and a script can tell a
  baseline from a change.
- Benchmark a repeatable scene, same length every time, at least 30 s.
- Start with two runs at the same settings: an agreeing baseline pair is what makes you a
  *trusted* contributor.
- Then change **one** setting per run. Several changes at once are kept but never counted as a
  setting's cost.
- In Compare, answer "Changes suggested by", so the data can show whose advice works.

## 1. Share a probe result (no coding)

Run the probe in a game we haven't covered yet. Different graphics APIs, anti-cheats, launchers
and Store/Game Pass titles are especially useful.

```powershell
python tools/get_presentmon.py
python tools/probe_presentmon.py --label <game>-<api>
```

Open an issue with the **Probe result** template and paste the generated `.md` summary. Add your
notes: was the right game detected, any anti-cheat warnings, overlays on or off.

## 2. Study a game and write its skill (no coding)

Game skills live in `skills/frametrace-<game>/SKILL.md` and give the AI measured knowledge about
one game: config key → menu name, what each setting costs, how to benchmark it repeatably, and
its quirks. They come from a **game study**, which the general skill (`skills/frametrace`) runs
with you: paste a report for the game, ask for a study, and follow its steps. It keeps a study log
you can paste back in a later session, and drafts the skill from
`skills/game-skill-template.md` once the data is there. See [skills/README.md](skills/README.md).

A skill must be **optional**: Frametrace and its reports must give useful advice without one.
Good skills are factual and testable. Write "Grass quality is CPU-bound in cities, measured with
Frametrace (run labels)", not "turn everything to low". Mark guide claims as "guide" with a link.
The shared rules block in each skill is copied from the general skill: edit it there and run
`python tools/sync_skills.py`.

## 3. Code

Ground rules:

- **No game-specific code in `frametrace/`.** Game knowledge belongs in game skills. The core works
  from PresentMon data and system info only.
- **Never hardcode PresentMon column names outside `frametrace/columns.py`.** Use the canonical
  names it defines.
- Frametrace is **stdlib-only**, the window included (plain tkinter, fonts bundled). Ask in an
  issue before adding a dependency.
- UI changes follow the design system in `design/frametrace-design`: tokens in
  `frametrace/theme.py`, instrument widgets in `frametrace/instruments.py`. One yellow element
  per screen, numbers in IBM Plex Mono, cyan for the GPU and magenta for the CPU.
- Run `pytest` and `ruff check .` before opening a PR.

Setup:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python tools/get_presentmon.py
pytest
```

Changed the window? Regenerate the README screenshots from synthetic demo captures (nothing on
your PC is read) and look at every view in both modes:

```powershell
pip install pillow
python tools/window_shots.py shots            # every view, dark and light
python tools/window_shots.py docs\images --readme
```

## Reporting bugs

Attach the report, or the probe summary, and say which game, API and Windows build you used.
Don't attach raw CSVs bigger than a few MB. The `-target.csv` the probe writes is usually enough.
