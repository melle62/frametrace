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
- The core (everything except `gui.py`) is **stdlib-only**. The GUI uses `sv-ttk` for its
  Windows 11 theme and still runs without it. Ask in an issue before adding a dependency.
- Run `pytest` and `ruff check .` before opening a PR.

Setup:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python tools/get_presentmon.py
pytest
```

## Reporting bugs

Attach the report, or the probe summary, and say which game, API and Windows build you used.
Don't attach raw CSVs bigger than a few MB. The `-target.csv` the probe writes is usually enough.
