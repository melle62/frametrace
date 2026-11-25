# Frametrace

**Answers instead of graphs.** Frametrace records frame times while you play, works out whether
your CPU or your GPU is holding you back, collects the system details that matter, and gives you
one compact text report. Paste the report into any AI. With the Frametrace skill, it turns into
concrete advice for your game and your hardware.

Works with **any** game: DirectX 11, DirectX 12, Vulkan and OpenGL, any engine, any launcher. No
per-game setup. Capture is based on Intel's [PresentMon](https://github.com/GameTechDev/PresentMon),
which reads frame events from Windows and doesn't touch the game.

> **Status: pre-alpha.** The repo structure, PresentMon integration research and a capture probe
> are in. The hotkey capture, analysis and report are next. See the [roadmap](#roadmap).

## How it will work

```
F10 in game ──► PresentMon records every frame ──► F10 again
                                                     │
          ┌──────────────────────────────────────────┘
          ▼
  pick the game automatically ──► stats + CPU/GPU bottleneck ──► + system info
                                                                     │
                       report copied to clipboard ◄──────────────────┘
                                 │
                                 ▼
                 paste into Claude / ChatGPT / … with the Frametrace skill
```

The report will cover average FPS, 1% and 0.1% lows, P99 frame time, frame-time consistency, and
the share of frames limited by the CPU and by the GPU. It also includes the checks that catch
real problems: RAM running below its rated speed (EXPO/XMP off), refresh rate mismatch, FPS cap
versus refresh rate, power plan, Game Mode and HAGS. Compare mode puts two reports side by side
(before and after an upgrade or a settings change).

## Try the probe (Windows)

The probe records a short capture in any game and shows what Frametrace sees. It needs Python
3.10+ and no other packages.

```powershell
python tools/get_presentmon.py                     # downloads PresentMon 2.6.0 to bin/ and checks its hash
python tools/probe_presentmon.py --label cs2-dx11  # run from an admin terminal, then switch to the game
```

PresentMon needs administrator rights or membership in the "Performance Log Users" group. See
[docs/presentmon.md](docs/presentmon.md).

## Repo layout

```
frametrace/          core package, game-agnostic (no game-specific code, ever)
  columns.py         PresentMon CSV schema detection → canonical column names
  process.py         foreground process + automatic game detection
  presentmon.py      locating and driving PresentMon
  capture.py         hotkey recording            (next)
  analyze.py         stats + bottleneck          (next)
  sysinfo.py         CPU/GPU/RAM/BIOS/display    (next)
  report.py          text report + compare mode  (next)
skill/               the AI skill (SKILL.md) and optional per-game profiles
tools/               setup and probe scripts
tests/               pytest suite and fixtures
docs/                design notes and findings
bin/                 PresentMon goes here (not committed)
```

## Roadmap

- [x] Repo, license, sponsor button
- [x] PresentMon version, CSV schemas, permissions, game auto-detection design
- [ ] Probe captures across DX11 / DX12 / Vulkan / OpenGL
- [ ] `capture.py` hotkey recording, `analyze.py` stats and bottleneck detection
- [ ] `sysinfo.py`
- [ ] `report.py` and compare mode
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
