# Frametrace

**Answers instead of graphs.** Frametrace records frame times while you play, works out whether
your CPU or your GPU is holding you back, collects the system details that matter, and gives you
one compact text report. Paste the report into any AI. With the Frametrace skill, it turns into
concrete advice for your game and your hardware.

Works with **any** game: DirectX 11, DirectX 12, Vulkan and OpenGL, any engine, any launcher. No
per-game setup. Capture is based on Intel's [PresentMon](https://github.com/GameTechDev/PresentMon),
which reads frame events from Windows and doesn't touch the game.

> **Status: alpha.** Capture, analysis, system info, report and compare work. Thresholds for the
> CPU/GPU split are still being calibrated with real captures. See the [roadmap](#roadmap).

## How it works

```
F10 in game ──► PresentMon records every frame ──► F10 again (or after 30 s)
                                                     │
          ┌──────────────────────────────────────────┘
          ▼
  pick the game automatically ──► stats + CPU/GPU bottleneck ──► + system info + checks
                                                                     │
                       report copied to clipboard ◄──────────────────┘
                                 │
                                 ▼
                 paste into Claude / ChatGPT / … with the Frametrace skill
```

The report covers average FPS, 1% and 0.1% lows, the worst second, P99 frame time, stutter
spikes, and the share of frames limited by the CPU and by the GPU, with estimated FPS ceilings
for each. Automatic checks catch the classic problems: RAM running below its rated speed
(EXPO/XMP off), single-channel RAM, a display running below its maximum refresh rate, frames
going through the desktop compositor, VSync, FPS caps, and power plan, Game Mode, HAGS and
memory integrity. Compare mode puts two captures side by side (before and after an upgrade
or a settings change).

## Use it (Windows 10/11)

You need Python 3.10 or newer.

```powershell
python -m pip install sv-ttk      # Windows 11 look for the window (optional)
python -m frametrace              # or double-click Frametrace.bat
```

On first start the window offers to download PresentMon (Intel's free capture tool, checked
against a pinned SHA-256). Recording needs administrator rights or membership in the
"Performance Log Users" group, and the window offers both. Then:

1. Start a game and press **F10** (change it in the window). You'll hear a beep.
2. Play normally. Recording stops after the chosen length (30 s by default), or when you press
   F10 again in manual mode.
3. The report appears in the window and is already on your clipboard. Paste it into any AI.

Captures are saved in `Documents\Frametrace\captures`. Select two in the **Captures** tab to
compare them.

Command line: `python -m frametrace report capture.csv` analyzes an existing PresentMon CSV,
and `python -m frametrace compare before after` compares two saved captures.

For PresentMon details (CSV formats, permissions, anti-cheat), see
[docs/presentmon.md](docs/presentmon.md).

## Repo layout

```
frametrace/          core package, game-agnostic (no game-specific code, ever)
  gui.py             the window (tkinter + Sun Valley theme)
  capture.py         recording controller: PresentMon start/stop, game pick, saving
  hotkey.py          global hotkey (RegisterHotKey)
  analyze.py         frame stats + CPU/GPU bottleneck
  sysinfo.py         CPU/GPU/RAM/BIOS/display/Windows settings
  report.py          text report, checks, JSON result, compare mode
  columns.py         PresentMon CSV schema detection → canonical column names
  process.py         foreground process + automatic game detection
  presentmon.py      locating and driving PresentMon
  download.py        PresentMon download with hash check
skill/               the AI skill (SKILL.md) and optional per-game profiles
tools/               setup and probe scripts
tests/               pytest suite and fixtures
docs/                design notes and findings
bin/                 PresentMon goes here (not committed)
```

## Roadmap

- [x] Repo, license, sponsor button
- [x] PresentMon version, CSV schemas, permissions, game auto-detection design
- [x] Window with hotkey capture, fixed or manual length
- [x] Stats, bottleneck detection, system info, checks, report, compare
- [ ] Real captures across DX11 / DX12 / Vulkan / OpenGL to calibrate thresholds
- [ ] Skill (`skill/SKILL.md`) tested with real reports
- [ ] Packaged `.exe` release

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
