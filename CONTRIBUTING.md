# Contributing to Frametrace

Thanks for helping! There are three ways in, from easiest to most involved.

## 1. Share a probe result (no coding)

Run the probe in a game we haven't covered yet. Different graphics APIs, anti-cheats, launchers
and Store/Game Pass titles are especially useful.

```powershell
python tools/get_presentmon.py
python tools/probe_presentmon.py --label <game>-<api>
```

Open an issue with the **Probe result** template and paste the generated `.md` summary. Add your
notes: was the right game detected, any anti-cheat warnings, overlays on or off.

## 2. Write a game profile (no coding)

Profiles live in `skill/profiles/` and give the AI game-specific knowledge: which settings load
the CPU and which load the GPU, engine quirks, built-in benchmarks and console commands. Start
from `skill/profiles/_template.md`. A profile must be **optional**: Frametrace and the skill must
give useful advice without one.

Good profiles are factual and testable. Write "Grass quality is CPU-bound in cities, measured
with Frametrace", not "turn everything to low".

## 3. Code

Ground rules:

- **No game-specific code in `frametrace/`.** Game knowledge belongs in profiles. The core works
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
