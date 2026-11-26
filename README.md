<p align="center">
  <img src="docs/brand/banner.svg" width="100%" alt="Frametrace. Answers, not graphs. A frame-time trace on an oscilloscope screen with four readouts from a CS2 run: 426.7 FPS average, GPU-limited on 93% of frames, 199 FPS CPU-side 1% low, 6.8 ms PC latency.">
</p>

<p align="center">
  <a href="https://github.com/melle62/frametrace/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/melle62/frametrace/ci.yml?branch=main&style=flat-square&label=CI&labelColor=1C1C1A"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-3A3A36?style=flat-square&labelColor=1C1C1A"></a>
  <img alt="Windows 10 and 11" src="https://img.shields.io/badge/windows-10%20%7C%2011-3A3A36?style=flat-square&labelColor=1C1C1A">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-3A3A36?style=flat-square&labelColor=1C1C1A">
  <img alt="PresentMon 2.6.0" src="https://img.shields.io/badge/presentmon-2.6.0-3A3A36?style=flat-square&labelColor=1C1C1A">
</p>

Frametrace records every frame while you play, works out whether the CPU or the GPU is the
limit, and writes one short report. Paste it into any AI. With the Frametrace skill, the report
becomes concrete advice for your game and your hardware.

<table>
  <tr><td><b>Games</b></td><td>Any game PresentMon can see: <code>DX11</code>, <code>DX12</code>, <code>Vulkan</code>, <code>OpenGL</code>. Any engine, any launcher, no per-game setup.</td></tr>
  <tr><td><b>Capture</b></td><td>Intel <a href="https://github.com/GameTechDev/PresentMon">PresentMon</a> <code>2.6.0</code> reads frame events from Windows. No injection, no overlay.</td></tr>
  <tr><td><b>Accuracy</b></td><td>CS2 benchmark map: CPU-side 1% low within <code>1.5%</code> of the game's own VProf counter. Two runs of the same <code>100 s</code> came out <code>0.2%</code> apart.</td></tr>
  <tr><td><b>Overhead</b></td><td>CS2 ran <code>512.7</code> FPS while recording, <code>515.3</code> FPS in earlier runs without it.</td></tr>
</table>

> **Status: alpha.** Capture, analysis, system info, report and compare work. Thresholds for the
> CPU/GPU split are still being calibrated with real captures. See the [roadmap](#roadmap).

<picture>
  <source media="(prefers-color-scheme: light)" srcset="docs/images/window-light.png">
  <img src="docs/images/window-dark.png" width="100%" alt="The Frametrace window: verdict, frame-time scope, readouts and checks for a CS2 capture">
</picture>

<sub>The window with synthetic demo data shaped like a CS2 benchmark run. It follows your GitHub
theme: dark by default, light in light mode.</sub>

## How it works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/how-it-works-dark.svg">
  <img src="docs/brand/how-it-works-light.svg" width="100%" alt="How Frametrace works. 01 Capture: press F10 in game. 02 Measure: PresentMon records every frame for 30 s or until F10 again. 03 Verdict: GPU-limited, 93% of frames. 04 Report: one short report, copied to the clipboard, to paste into any AI.">
</picture>

Frametrace finds the game on its own: the window in front when you press the hotkey, or the
process that drew the most frames. One report holds everything below.

| Readout | What it answers |
|---|---|
| Average FPS, 1% low, 0.1% low, worst second | How fast, and how even |
| CPU-side 1% low | The same low an in-game counter such as VProf shows |
| P99 frame time, hitches | The frames you feel. A hitch is `2x` its neighbours and `4 ms` longer. |
| GPU-limited / CPU-limited / waiting | What each frame waited for, and how fast the GPU alone could go |
| PC latency, median and P95 | Input to frame sent, in games with NVIDIA Reflex |
| Display path | API, present mode, VSync, tearing, frames never shown |
| System | CPU, GPU and driver, RAM speed vs. the kit's rating, board, BIOS, displays |

Automatic checks flag what to fix before touching game settings: RAM below its rated speed
(EXPO/XMP off), single-channel RAM, a display below its maximum refresh rate, frames through the
desktop compositor, VSync, FPS caps, power plan, Game Mode, HAGS and memory integrity. Compare
mode lays two captures over each other, before and after an upgrade or a settings change: both
frame-time traces on one screen, every metric from A to B with its change and whether it's
outside run-to-run noise, and what changed in the system.

## Use it (Windows 10/11)

You need Python `3.10` or newer. Nothing else: the window is plain tkinter and bundles its fonts.

```powershell
python -m frametrace              # or double-click Frametrace.bat
```

On first start the window offers to download PresentMon (Intel's free capture tool, checked
against a pinned SHA-256). Recording needs administrator rights or membership in the
"Performance Log Users" group, and the window offers both. Then:

1. Start a game and press <kbd>F10</kbd> (change it in the window). You'll hear a beep.
2. Play normally. Recording stops after the chosen length (`30 s` by default), or when you press
   <kbd>F10</kbd> again in manual mode.
3. The verdict, the frame-time scope and the readouts appear in the window, and the report is
   already on your clipboard. Paste it into any AI.

Captures are saved in `Documents\Frametrace\captures` and listed on the left.
<kbd>Ctrl</kbd>+click a second capture to compare the two, or right-click a capture for its folder,
its report or a comparison with the selected one.

| Keys | |
|---|---|
| <kbd>F10</kbd> | start or stop a capture, in any game, even fullscreen |
| <kbd>↑</kbd> <kbd>↓</kbd> | previous or next capture |
| <kbd>Ctrl</kbd>+<kbd>C</kbd> | copy the report (or the comparison) |
| <kbd>Ctrl</kbd>+<kbd>Tab</kbd> | next tab: Summary, Report, System, Compare |
| <kbd>Ctrl</kbd>+<kbd>O</kbd> | open the capture's folder |

Command line: `python -m frametrace report capture.csv` analyzes an existing PresentMon CSV,
and `python -m frametrace compare before after` compares two saved captures.

For PresentMon details (CSV formats, permissions, anti-cheat), see
[docs/presentmon.md](docs/presentmon.md).

## Repo layout

```
frametrace/          core package, game-agnostic (no game-specific code, ever)
  gui.py             the window (tkinter, bench-instrument design)
  theme.py           design tokens: colors, IBM Plex fonts, ttk styles
  instruments.py     scope, readouts, lamps, buttons drawn with plain tk widgets
  summary.py         wording of the summary view (verdict, readouts, details)
  trace.py           compact frame-time trace for the scope (trace.json)
  capture.py         recording controller: PresentMon start/stop, game pick, saving
  hotkey.py          global hotkey (RegisterHotKey)
  analyze.py         frame stats + CPU/GPU bottleneck
  sysinfo.py         CPU/GPU/RAM/BIOS/display/Windows settings
  report.py          text report, checks, JSON result, compare mode
  columns.py         PresentMon CSV schema detection → canonical column names
  process.py         foreground process + automatic game detection
  presentmon.py      locating and driving PresentMon
  download.py        PresentMon download with hash check
  assets/            window icon; fonts/: IBM Plex Sans and Mono (SIL OFL 1.1)
design/              the Frametrace design system (hue skill: tokens, components, previews)
skill/               the AI skill (SKILL.md) and optional per-game profiles
tools/               setup, probe, icon and README image scripts (brand.py, window_shots.py)
tests/               pytest suite and fixtures
docs/                design notes, findings, README images (docs/brand)
bin/                 PresentMon goes here (not committed)
```

## Roadmap

- [x] Repo, license, sponsor button
- [x] PresentMon version, CSV schemas, permissions, game auto-detection design
- [x] Window with hotkey capture, fixed or manual length
- [x] Stats, bottleneck detection, system info, checks, report, compare
- [x] Brand and window redesign ([design system](design/frametrace-design/SKILL.md))
- [ ] Real captures across DX11 / DX12 / Vulkan / OpenGL to calibrate thresholds
- [ ] Skill (`skill/SKILL.md`) tested with real reports
- [ ] Packaged `.exe` release

## Design

Frametrace looks like a bench instrument: warm graphite panels, one yellow trace, cyan for the
GPU, magenta for the CPU, IBM Plex Sans for words and IBM Plex Mono for every number. The design
system lives in [design/frametrace-design](design/frametrace-design/SKILL.md), generated with the
[hue](https://github.com/dominikmartn/hue) skill from one `design-model.yaml`. Open
`preview.html`, `component-library.html`, `landing-page.html` or `app-screen.html` there to see
it in both modes.

## Contributing

The most valuable contributions don't need any Python:

- **Probe results** from games and APIs we haven't covered yet
- **Game profiles** for the skill: known CPU-heavy settings, engine quirks, built-in benchmarks

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Support

Frametrace is free and MIT-licensed. If it saved you time, you can
[sponsor the project](https://github.com/sponsors/melle62).

## License

[MIT](LICENSE). PresentMon is © Intel Corporation, MIT-licensed. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
