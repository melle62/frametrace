# PresentMon setup and findings

Status: researched 2026-11-26 against PresentMon **v2.6.0**: the release notes, the source at the
`v2.6.0` tag, the strings in the released exe, then calibrated with real CS2 captures on the
developer's PC (benchmark map, VProf comparison, `fps_max 200`, Reflex Off / On / On + Boost, and
four goal-driven runs before and after a settings change). Updated after PR #3: the picked
process is also identified as a game (section 5), and captures should start at the same moment
in a run (section 8). Items still marked **verify** need captures from other games, made with
the Frametrace window or `tools/probe_presentmon.py`.

## 1. Which PresentMon

| | |
|---|---|
| Version | **2.6.0** (released 21 Sep 2026, the latest at the time of writing) |
| File | `PresentMon-2.6.0-x64.exe`, the standalone console app (957 KB, no installer, no service) |
| URL | https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/PresentMon-2.6.0-x64.exe |
| SHA-256 | `b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af` |
| Get it | the Frametrace window offers the download, or run `python tools/get_presentmon.py`; both check the hash |
| Flags | default CSV, `--session_name Frametrace --stop_existing_session --no_console_stats --track_pc_latency` |

We use the console app, not the `PresentMon-2.6.0.msi` "Intel PresentMon" package (162 MB:
service, overlay and GUI). Frametrace only needs CSV output.

**We pin the version** because the CSV format changes between releases (see section 4).
Upgrading should be a deliberate step: bump the constants in `frametrace/presentmon.py`,
rerun the probe, and update `tests/fixtures/headers/`. The exe has no version resource, so
`presentmon.identify()` recognises it by its SHA-256 (or the file name).

## 2. License and bundling

PresentMon is MIT-licensed (Copyright Intel Corporation). We can redistribute the exe as long
as Intel's copyright and license text go with it.

Proposed answer to the open question "bundle or download on first run":
- **Release zips bundle the exe**, together with `PresentMon-LICENSE.txt` and
  `PresentMon-THIRD_PARTY.txt` (copied verbatim from the `v2.6.0` tag). This works offline,
  needs no network call on first run, and it's one download for the user.
- **The git repo never contains the exe.** Developers run `tools/get_presentmon.py`, which also
  fetches both notice files. `bin/` is gitignored.
- Both paths check the same pinned SHA-256.
- If Python can't verify GitHub's certificate (seen on a debloated Windows 11 where automatic
  root-certificate updates are off), the download retries with Windows' own `curl.exe`, which
  still verifies the certificate. The hash check applies either way.

## 3. Permissions

PresentMon starts a real-time ETW trace session. The binary's own error message says it needs
**administrator rights or membership in the "Performance Log Users" group**. Nothing else is
required.

Without admin rights, processes that run under other accounts or that are short-lived appear
as `<unknown>` and can't be targeted with `--process_name`. Frametrace targets by PID and picks
the process afterwards, so this doesn't affect it.

The window handles it: if `presentmon.can_trace()` fails, a banner offers two options:
1. **One-time setup (preferred):** add the user to the group, then sign out and back in.
   After that, Frametrace runs without elevation: no UAC prompt per session, and normal
   hotkeys and clipboard. This also works on Windows Home, which has no Local Users and Groups
   console. Using the SID makes it work on non-English Windows:
   ```powershell
   # admin PowerShell
   Add-LocalGroupMember -SID "S-1-5-32-559" -Member $env:USERNAME
   ```
   Confirmed on the dev PC: Frametrace runs unelevated after this.
2. **Restart as administrator** for this session.

## 4. CSV formats: three schemas

PresentMon 2.6.0 can write three different CSV layouts. All frame times are in
**milliseconds**. The time axis is in milliseconds too in the 2.6 default (`TimeInMs`; 2.6 can't
write seconds any more), in seconds in 1.x (`TimeInSeconds`), and has no unit in its name in 2.x
(`CPUStartTime`). `columns.py` converts all of them to seconds (`time_s`) and works out the unit
from the data when the name doesn't say. We never pass `--qpc_time`, `--qpc_time_ms` or
`--date_time`. The file is UTF-8 with a BOM. Values that aren't available are written as `NA`.
A few metrics are written as `0` instead, so a GPU busy of exactly 0 deserves suspicion.

| What | 2.6 default ("v3") | `--v2_metrics` (2.0-2.5 default) | `--v1_metrics` (1.x) | Frametrace name |
|---|---|---|---|---|
| Frame time, Present to Present | `MsBetweenPresents` | n/a | `msBetweenPresents` | `ms_between_presents` |
| CPU frame interval | `MsBetweenAppStart` | `FrameTime` | n/a | `ms_frame_time` |
| CPU busy / wait | `MsCPUBusy` / `MsCPUWait` | `CPUBusy` / `CPUWait` | n/a | `ms_cpu_busy` / `ms_cpu_wait` |
| GPU busy | `MsGPUBusy` | `GPUBusy` | `msGPUActive` | `ms_gpu_busy` |
| GPU time / wait / latency | `MsGPUTime`, `MsGPUWait`, `MsGPULatency` | `GPUTime`, `GPUWait`, `GPULatency` | n/a | `ms_gpu_*` |
| Display interval | `MsBetweenDisplayChange` | `DisplayedTime` | `msBetweenDisplayChange` | `ms_between_display_change` / `ms_displayed_time` |
| Dropped (never shown) | `NA` in display columns | `NA` in `DisplayedTime` | `Dropped` = 1 | |
| PC latency (Reflex markers) | `MsPCLatency` with `--track_pc_latency` | n/a | n/a | `ms_pc_latency` |
| Time axis | `TimeInMs` (ms) | `CPUStartTime` (unit varies) | `TimeInSeconds` (s) | `time_s` (s) |
| API | `PresentRuntime` | `PresentRuntime` | `Runtime` | `runtime` |
| VSync / tearing / flip model | `SyncInterval`, `AllowsTearing`, `PresentMode` | same | same | same |

**We use the 2.6 default.** It's the only layout that has both `MsBetweenPresents` (the
standard frame time that reviewers and CapFrameX use) and the CPU/GPU busy split that the
bottleneck detection needs. `frametrace/columns.py` reads all three layouts anyway, so CSVs
from other PresentMon versions still work. It reports which features are missing instead of
failing. `MsCPUWait` equals `MsInPresentAPI` (time inside `Present()`).

Exact 2.6.0 default header (no extra options), confirmed by a real capture on Windows 11:
```
Application,ProcessID,SwapChainAddress,PresentRuntime,SyncInterval,PresentFlags,AllowsTearing,PresentMode,TimeInMs,MsBetweenSimulationStart,MsBetweenPresents,MsBetweenDisplayChange,MsInPresentAPI,MsRenderPresentLatency,MsUntilDisplayed,CPUStartTimeInMs,MsBetweenAppStart,MsCPUBusy,MsCPUWait,MsGPULatency,MsGPUTime,MsGPUBusy,MsGPUWait,MsAnimationError,AnimationTime,MsFlipDelay,MsAllInputToPhotonLatency,MsClickToPhotonLatency
```
With `--track_pc_latency`, `MsPCLatency` is added.

### Intel's README doesn't match the binary

The "Default metrics" table in `README-ConsoleApplication.md` (v2.6.0) lists `CPUStartTime`,
`DisplayLatency` and `DisplayedTime`. The exe actually writes `CPUStartTimeInMs` and doesn't
write the two display columns in the default layout. It also writes `MsFlipDelay`, which the
README doesn't list. The time columns are `TimeInMs` and `CPUStartTimeInMs`, because 2.6's
default time unit is milliseconds. `FrameType`, `VideoBusy`, `VidPnSourceId`, `LayerIndex`, `PresentId`,
`MsPCLatency` and `InstrumentedLatency` only appear with their opt-in flags. **Rule: trust the
header row, never the README.** That's why the schema is detected at runtime. The console log
PresentMon writes is UTF-16; `presentmon.read_console_log` decodes it.

## 5. Game auto-detection (no per-game config)

Implemented in `frametrace/process.py`:

1. **On the hotkey press**, read the foreground window's PID (`GetForegroundWindow` →
   `GetWindowThreadProcessId`). Only `PROCESS_QUERY_LIMITED_INFORMATION` is used to read the exe
   path. There's no injection and no memory reads, and if a protected (anti-cheat) process
   refuses even that, the PID is still valid.
2. **Capture all processes** (no `--process_id` / `--process_name` filter).
3. **Pick the target afterwards:**
   - the foreground PID, if it presented at least 30 frames;
   - otherwise the process with the most frames, ignoring a short list of non-game presenters
     (`dwm.exe`, shell, browsers, Discord, OBS, overlays) and Frametrace itself;
   - always overridable with the window's Game field or `--process-name`.
4. Within the target, use the **main swapchain** (the one with the most frames). Some games and
   overlays create a second one.
5. **Identify the game** (`capture.identify_game`, `game.py`): read the picked PID's image path
   (`process.image_path`, again only `PROCESS_QUERY_LIMITED_INFORMATION`; if that's refused, the
   foreground window's path when it's the same process), then the Steam app manifest (name, app
   ID, build), the exe's version resource and the engine's shipped files. The in-game settings
   readers (`gamesettings.py`) start from there. None of this touches PresentMon or the game.

Why not filter by PID up front? The fallback handles the cases where the foreground window
isn't the process that renders: launchers that hand off to a child process (for example
PrismLauncher → `javaw.exe`), Store/UWP games whose window belongs to
`ApplicationFrameHost.exe`, and games that render from a helper process. Capturing everything
costs only some extra rows from `dwm.exe` and browsers, which are dropped after the pick.
Filtering by name would need per-game config, and it breaks for `<unknown>` processes without
admin rights. Confirmed on CS2: starting from the window's button (Frametrace in front) fell back
to `cs2.exe` correctly, and step 5 named it Counter-Strike 2 (Steam app 730) on the dev PC.

**Starting and stopping.** Frametrace starts PresentMon on the first hotkey press with
`--session_name Frametrace --stop_existing_session`. On the second press (or when the fixed
length runs out) it runs `PresentMon --session_name Frametrace --terminate_existing_session`.
That stops the ETW session; the recording process's consumer thread then returns, and the
process flushes the CSV and exits. The fallback is `CTRL_BREAK_EVENT`: PresentMon's console
handler also stops cleanly on it. Killing the process is the last resort. Confirmed in the
first real probe: the recording exited 0.1 s after `--terminate_existing_session`. PresentMon is
started with `CREATE_NO_WINDOW`, so no console flashes up.

We don't use PresentMon's own `--hotkey`. It can't tell us which process is in front, it adds
`-1`, `-2` suffixes to file names, and it can't run together with our own hotkey on the same
key. Frametrace registers the hotkey with `RegisterHotKey` (not a low-level keyboard hook),
which is the least intrusive option with anti-cheat software running. Plain F12 is rejected
(Windows reserves it for debuggers).

## 6. Bottleneck signal (as implemented in analyze.py, calibrated on CS2)

The bottleneck is evidence for the AI, not the headline: it tells the report which kind of
in-game setting can move the frame rate (GPU-heavy or CPU-heavy settings, or the cap).

The first second of every capture is skipped (starting the trace and pressing the hotkey can
cause a hitch that isn't the game's fault). Each remaining frame gets one class:

- **GPU-limited:** `ms_gpu_busy / ms_frame_time >= 0.90` (`GPU_BOUND_RATIO`)
- **waiting:** otherwise, if the CPU was blocked in `Present()` for at least 25% of the frame
  (`ms_cpu_wait / ms_frame_time >= 0.25`, `WAIT_RATIO`). With **VSync off and no cap**, these
  frames count as GPU-limited instead: a full GPU queue is what blocks `Present()` then. On the
  first CS2 capture this moved 21% of frames from "waiting" to GPU-limited.
- **CPU-limited:** everything else

The verdict is "mostly X" when one class has at least 70% of the frames, otherwise "mixed,
leaning X".

**Caps.** A capture counts as capped when the GPU has headroom (median GPU ratio below 0.85) and
either per-second FPS is pinned (90% of seconds within 3% of the median and no second more than
1% above it, at least 10 s of data) or frame times are very uniform (P95 / P5 < 1.10). With a
cap, frames the GPU didn't limit count as waiting for the cap. CS2's `fps_max 200` was first read
as "mostly CPU-limited": the game holds the rate per second but paces frames as 7.2 / 3.0 /
4.8 ms, so the uniform rule missed it. The per-second rule fixed it; the top margin was widened
from 0.5% to 1% after a real run measured +0.41%.

**Ceilings.** The report gives one ceiling: 1000 / median GPU busy ("the GPU alone could do about
N FPS"). There is **no CPU ceiling**: PresentMon's CPU busy only covers the presenting (render)
thread, so a 1000 / CPU busy figure (about 1,486 FPS on CS2) was misleading and was removed.

**Lows.** Two 1% lows: present-to-present (`MsBetweenPresents`, comparable with CapFrameX and
reviews) and CPU-side (`MsBetweenAppStart`, comparable with in-game counters like CS2's VProf:
209.2 vs VProf 211.0).

**Hitches.** A frame is a hitch when it's longer than both 2x the median of its 30 neighbours
on each side and that median + 4 ms. The capture-wide median flagged heavy scenes as stutter.

All thresholds are module constants in `analyze.py`.

Caveats that matter on the developer's own system:

- **HAGS inflates GPU busy.** PresentMon's README warns that GPU execution metrics are less
  accurate with Hardware-Accelerated GPU Scheduling, by up to about 0.5 ms per frame. At CS2's
  ~430-500 FPS (~2 ms per frame) that's a quarter of the frame, enough to push CPU-bound frames
  over 90%. The report adds a note above 300 FPS. The HAGS registry value is missing on the dev
  PC, so the state shows as unknown; reading it through D3DKMT is a next step. **Verify:** CS2
  with HAGS on and off (needs a reboot).
- **Reflex sleep (verified on CS2).** GPU busy was unchanged at 2.08 ms with Reflex Off, On and
  On + Boost, so the GPU signal holds. Reflex shows up as less time blocked in `Present()`
  (1.36 / 1.23 / 0.95 ms) and lower PC latency (median 7.25 / 6.83 / 6.30 ms, P95 11.81 /
  10.49 / 9.22 ms), at 430.4 / 426.7 / 414.1 FPS. GPU-limited frames 95 / 93 / 88%.
- **DLSS Frame Generation isn't labelled.** `--track_frame_type` only identifies Intel XeSS-FG
  and AMD AFMF frames (PresentMon's `FrameType` enum). With DLSS FG on an RTX card, generated
  frames mix into the stats unlabelled. The report asks whether frame generation was on.
- **OpenGL and Vulkan have less instrumentation.** Intel's README says apps that report runtime
  `Other` (typical for OpenGL and Vulkan) get slightly less accurate CPU frame timing. On NVIDIA,
  the "Vulkan/OpenGL present method" setting can make those apps present through DXGI. The probe
  shows which runtime is reported.

## 7. Anti-cheat

PresentMon reads OS-level ETW events and never touches the game process. Some titles block ETW
tracing, though. Intel's v2.5.0 notes mention changes that let PresentMon "gather data from
certain titles that otherwise block ETW trace gathering", without saying which component they
apply to. Symptom: the game is in front but presents zero frames in the capture; the window
then reports that no game was found and lists the presenting processes. **Confirmed:** CS2 (VAC)
works. **Verify:** DayZ (BattlEye).

## 8. Test plan

Setup (once): Python 3.10 or newer and the repo, then `python -m frametrace` (or
`Frametrace.bat`). No packages to install. The window offers the PresentMon download and the
permission setup.

Pick a goal, then capture while playing a repeatable scene (press F10 in the game; 30 s by
default, Manual for benchmark maps, see below). Paste the report into any AI, or back into the
chat. The probe script (`python tools/probe_presentmon.py --label <name>`) still works for raw
diagnostics.

**Start every capture at the same moment.** A fixed-length capture started by hand on a
benchmark that runs longer than the capture covers a different part of it each time. Four CS2
runs on FPSfrequency's FPS Benchmark map (fixed 79 s, started by hand) came out either clean
(1% low 214.6 and 212.2, within 1–2% of each other) or hitchy (3–4% of the time in hitches),
independent of the settings. Use Manual length, press the hotkey on the same cue at the start
and the end of the run, and throw away the first pass after loading the map.

| # | Capture | What it tests | Status |
|---|---|---|---|
| 1 | `cs2-dx11-reflex-on` | baseline, very high FPS, VAC, Reflex | done |
| 2 | `cs2-dx11-reflex-off` | Reflex effect on CPU busy/wait | done (plus On + Boost) |
| 3 | `cs2-dx11-fpsmax-200` | cap detection (`fps_max 200`) | done, rule fixed |
| 4 | `cs2-goal-lows` | goal-driven report, game name, settings reader, compare | done (4 runs; clean vs hitchy runs) |
| 5 | `cs2-goal-lows-baseline` | two clean runs with the old settings, to measure the change | open |
| 6 | `dayz-dx11` | BattlEye, a typically CPU-heavy game | open |
| 7 | `fh6-dx12` | DX12, GPU-heavy (also the Store fallback if it's the Xbox app version) | open |
| 8 | `atm10-opengl` | OpenGL, `javaw.exe` started from PrismLauncher (launcher handoff) | open |
| 9 | `<game>-vulkan` | any Vulkan title you have; otherwise leave it to a contributor | open |
| 10 | `cs2-dx11-hags-off` | HAGS effect on GPU busy (after a reboot with HAGS off) | open |
| 11 | an Unreal and a Unity game | the engine settings readers on real installs | open |

The reports answer: whether auto-detect picked the right process for each API and launcher,
whether the clean stop works, where the GPU-busy ratio sits for each game (which calibrates the
thresholds), and whether the settings readers find the game's config. Use the window's Compare
view (Ctrl+click two captures, or label them first) for A/B tests like HAGS on/off: it marks
changes inside run-to-run noise as SAME and flags results that moved while the settings didn't.
