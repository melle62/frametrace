# PresentMon setup and findings

Status: researched 2026-11-26 against PresentMon **v2.6.0**: the release notes, the source at the
`v2.6.0` tag, the strings in the released exe, and a first real capture on Windows 11. The items
marked **verify** need real game captures, made with the Frametrace window or
`tools/probe_presentmon.py`.

## 1. Which PresentMon

| | |
|---|---|
| Version | **2.6.0** (released 21 Sep 2026, the latest at the time of writing) |
| File | `PresentMon-2.6.0-x64.exe`, the standalone console app (957 KB, no installer, no service) |
| URL | https://github.com/GameTechDev/PresentMon/releases/download/v2.6.0/PresentMon-2.6.0-x64.exe |
| SHA-256 | `b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af` |
| Get it | the Frametrace window offers the download, or run `python tools/get_presentmon.py`; both check the hash |

We use the console app, not the `PresentMon-2.6.0.msi` "Intel PresentMon" package (162 MB:
service, overlay and GUI). Frametrace only needs CSV output.

**We pin the version** because the CSV format changes between releases (see section 4).
Upgrading should be a deliberate step: bump the constants in `frametrace/presentmon.py`,
rerun the probe, and update `tests/fixtures/headers/`.

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

Recommendation: on first run, if `presentmon.can_trace()` fails, offer two options:
1. **One-time setup (preferred):** add the user to the group, then sign out and back in.
   After that, Frametrace runs without elevation: no UAC prompt per session, and normal
   hotkeys and clipboard. This also works on Windows Home, which has no Local Users and Groups
   console. Using the SID makes it work on non-English Windows:
   ```powershell
   # admin PowerShell
   Add-LocalGroupMember -SID "S-1-5-32-559" -Member $env:USERNAME
   ```
2. **Run elevated** for this session.

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
| Time axis | `TimeInMs` (ms) | `CPUStartTime` (unit varies) | `TimeInSeconds` (s) | `time_s` (s) |
| API | `PresentRuntime` | `PresentRuntime` | `Runtime` | `runtime` |
| VSync / tearing / flip model | `SyncInterval`, `AllowsTearing`, `PresentMode` | same | same | same |

**We use the 2.6 default.** It's the only layout that has both `MsBetweenPresents` (the
standard frame time that reviewers and CapFrameX use) and the CPU/GPU busy split that the
bottleneck detection needs. `frametrace/columns.py` reads all three layouts anyway, so CSVs
from other PresentMon versions still work. It reports which features are missing instead of
failing.

Exact 2.6.0 default header (no extra options), confirmed by a real capture on Windows 11:
```
Application,ProcessID,SwapChainAddress,PresentRuntime,SyncInterval,PresentFlags,AllowsTearing,PresentMode,TimeInMs,MsBetweenSimulationStart,MsBetweenPresents,MsBetweenDisplayChange,MsInPresentAPI,MsRenderPresentLatency,MsUntilDisplayed,CPUStartTimeInMs,MsBetweenAppStart,MsCPUBusy,MsCPUWait,MsGPULatency,MsGPUTime,MsGPUBusy,MsGPUWait,MsAnimationError,AnimationTime,MsFlipDelay,MsAllInputToPhotonLatency,MsClickToPhotonLatency
```

### Intel's README doesn't match the binary

The "Default metrics" table in `README-ConsoleApplication.md` (v2.6.0) lists `CPUStartTime`,
`DisplayLatency` and `DisplayedTime`. The exe actually writes `CPUStartTimeInMs` and doesn't
write the two display columns in the default layout. It also writes `MsFlipDelay`, which the
README doesn't list. The time columns are `TimeInMs` and `CPUStartTimeInMs`, because 2.6's
default time unit is milliseconds. `FrameType`, `VideoBusy`, `VidPnSourceId`, `LayerIndex`, `PresentId`,
`MsPCLatency` and `InstrumentedLatency` only appear with their opt-in flags. **Rule: trust the
header row, never the README.** That's why the schema is detected at runtime.

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
     (`dwm.exe`, shell, browsers, Discord, OBS, overlays);
   - always overridable with `--process-name` / `--pid`.
4. Within the target, use the **main swapchain** (the one with the most frames). Some games and
   overlays create a second one.

Why not filter by PID up front? The fallback handles the cases where the foreground window
isn't the process that renders: launchers that hand off to a child process (for example
PrismLauncher → `javaw.exe`), Store/UWP games whose window belongs to
`ApplicationFrameHost.exe`, and games that render from a helper process. Capturing everything
costs only some extra rows from `dwm.exe` and browsers, which are dropped after the pick.
Filtering by name would need per-game config, and it breaks for `<unknown>` processes without
admin rights.

**Starting and stopping.** Frametrace starts PresentMon on the first hotkey press with
`--session_name Frametrace --stop_existing_session`. On the second press it runs
`PresentMon --session_name Frametrace --terminate_existing_session`. That stops the ETW
session; the recording process's consumer thread then returns, and the process flushes the CSV
and exits. The fallback is `CTRL_BREAK_EVENT`: PresentMon's console handler also stops cleanly
on it. Killing the process is the last resort. Confirmed in the first real probe: the recording exited 0.1 s after `--terminate_existing_session`.

We don't use PresentMon's own `--hotkey`. It can't tell us which process is in front, it adds
`-1`, `-2` suffixes to file names, and it can't run together with our own hotkey on the same
key. Frametrace registers the hotkey with `RegisterHotKey` (not a low-level keyboard hook),
which is the least intrusive option with anti-cheat software running.

## 6. Bottleneck signal (as implemented in analyze.py)

Each frame gets one class:

- **GPU-limited:** `ms_gpu_busy / ms_frame_time >= 0.90`
- **waiting:** otherwise, if the CPU waited (blocked in `Present()`) for at least 25% of the
  frame (`ms_cpu_wait / ms_frame_time >= 0.25`). That points to VSync, a cap or a full queue.
- **CPU-limited:** everything else

The verdict is "mostly X" when one class has at least 70% of the frames, otherwise "mixed,
leaning X". On top of that, a capture counts as **capped** when frame times are very uniform
(P95 / P5 < 1.10) while the median GPU ratio is below 0.85. In-game limiters like `fps_max`
sleep inside the game's frame, so they look like CPU time; the uniform frame times are what
give them away. The report also gives FPS ceilings: 1000 / median GPU busy and
1000 / median CPU busy.

All thresholds are module constants in `analyze.py` and are first estimates until real
captures calibrate them.

Caveats that matter on the developer's own system:

- **HAGS inflates GPU busy.** PresentMon's README warns that GPU execution metrics are less
  accurate with Hardware-Accelerated GPU Scheduling. Its example: a GPU-bound frame's GPU active
  time reported about 0.5 ms too large. HAGS is commonly enabled on RTX 40 cards under
  Windows 11. CS2 runs at about 515 FPS (≈1.9 ms per frame), so 0.5 ms is roughly a quarter of
  the frame. That's enough to push CPU-bound frames over a 90% threshold. So `sysinfo.py` must
  record the HAGS state, and the thresholds need calibrating at very high FPS. **Verify:** CS2
  with HAGS on and off (needs a reboot).
- **Reflex / Anti-Lag sleep likely counts as CPU busy.** The latency sleep happens inside the
  game's frame, before simulation, not inside `Present()`. So it probably shows up in
  `MsCPUBusy` rather than `MsCPUWait`. That's why GPU busy, not CPU busy, is the primary signal.
  **Verify:** CS2 with Reflex on and off.
- **DLSS Frame Generation isn't labelled.** `--track_frame_type` only identifies Intel XeSS-FG
  and AMD AFMF frames (PresentMon's `FrameType` enum). With DLSS FG on an RTX card, generated
  frames mix into the stats unlabelled. For now, the report should ask whether frame generation
  was on.
- **OpenGL and Vulkan have less instrumentation.** Intel's README says apps that report runtime
  `Other` (typical for OpenGL and Vulkan) get slightly less accurate CPU frame timing. On NVIDIA,
  the "Vulkan/OpenGL present method" setting can make those apps present through DXGI. The probe
  shows which runtime is reported.

## 7. Anti-cheat

PresentMon reads OS-level ETW events and never touches the game process. Some titles block ETW
tracing, though. Intel's v2.5.0 notes mention changes that let PresentMon "gather data from
certain titles that otherwise block ETW trace gathering", without saying which component they
apply to. Symptom: the game is in front but presents zero frames in the capture. The probe flags
this. **Verify:** CS2 (VAC) and DayZ (BattlEye).

## 8. Test plan

Setup (once): Python 3.10 or newer, the repo, `python -m pip install sv-ttk`, then
`python -m frametrace` (or `Frametrace.bat`). The window offers the PresentMon download and
the permission setup.

Make each capture 30 s long while playing normally (press F10 in the game), then paste the
report back. The probe script (`python tools/probe_presentmon.py --label <name>`) still works
for raw diagnostics.

| # | Capture | What it tests |
|---|---|---|
| 1 | `cs2-dx11-reflex-on` | baseline, very high FPS, VAC, Reflex |
| 2 | `cs2-dx11-reflex-off` | Reflex effect on CPU busy/wait |
| 3 | `cs2-dx11-fpsmax-200` | cap detection (`fps_max 200`) |
| 4 | `dayz-dx11` | BattlEye, a typically CPU-heavy game |
| 5 | `fh6-dx12` | DX12, GPU-heavy (also the Store fallback if it's the Xbox app version) |
| 6 | `atm10-opengl` | OpenGL, `javaw.exe` started from PrismLauncher (launcher handoff) |
| 7 | `<game>-vulkan` | any Vulkan title you have; otherwise leave it to a contributor |
| 8 | `cs2-dx11-hags-off` | HAGS effect on GPU busy (after a reboot with HAGS off) |

The reports answer: whether auto-detect picked the right process for each API and launcher,
whether the clean stop works, and where the GPU-busy ratio sits for each game, which is what
calibrates the thresholds.
