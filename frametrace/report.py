"""The compact, AI-ready text report, its JSON form, automatic checks and compare mode.

A capture produces one result dict (JSON-serializable, saved as result.json). The text
report and the compare table are rendered from result dicts only, so old captures can
always be re-rendered and compared.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from frametrace import __version__, goals
from frametrace.analyze import HIGH_FPS, Analysis
from frametrace.game import GameInfo
from frametrace.gamesettings import GameSettings
from frametrace.sysinfo import SystemInfo

REPO_URL = "https://github.com/melle62/frametrace"
RESULT_FORMAT = 1


def build_result(
    analysis: Analysis,
    system: SystemInfo,
    meta: dict[str, Any],
    *,
    game: GameInfo | None = None,
    settings: GameSettings | None = None,
    goal: dict | None = None,
) -> dict:
    """Bundle everything about one capture. meta: started, requested_s, reason, presentmon, ...

    goal: {"key": one of goals.GOALS, "target_fps": int or None}.
    """
    result = {
        "format": RESULT_FORMAT,
        "frametrace": __version__,
        "capture": {
            "app": analysis.app,
            "pid": analysis.pid,
            "started": meta.get("started")
            or dt.datetime.now().astimezone().isoformat(timespec="seconds"),
            **{k: v for k, v in meta.items() if k != "started"},
        },
        "goal": {"key": goals.DEFAULT_GOAL, "target_fps": None, **(goal or {})},
        "game": (game or GameInfo(exe=analysis.app)).to_dict(),
        "game_settings": settings.to_dict() if settings else None,
        "analysis": analysis.to_dict(),
        "system": system.to_dict(),
    }
    result["checks"] = checks(result)
    return result


# --- automatic checks ------------------------------------------------------------------------


def checks(r: dict) -> list[dict]:
    """Automatic checks. level: warn, info or ok.

    kind "system": something to fix outside the game (hardware, Windows, display).
    kind "capture": a note on what the capture shows or can't show (stutter, length).
    """
    out: list[dict] = []

    def add(level: str, text: str, kind: str = "system") -> None:
        out.append({"level": level, "text": text, "kind": kind})

    sysd, an = r.get("system") or {}, r["analysis"]
    stats, bn, disp = an["stats"], an["bottleneck"], an["display"]

    # RAM speed and channels
    running, kit, rtype = sysd.get("ram_running_mts"), sysd.get("ram_kit_mts"), sysd.get("ram_type")
    if running and kit and running < kit - 200:
        add(
            "warn",
            f"RAM runs at {running} MT/s but the kit is rated {kit} MT/s: EXPO/XMP is probably off in the BIOS.",
        )
    elif running and (rtype == "DDR5" and running <= 4800 or rtype == "DDR4" and running <= 2666):
        add(
            "warn",
            f"RAM runs at {running} MT/s, the {rtype} JEDEC default. If the kit is rated higher, enable EXPO/XMP in the BIOS.",
        )
    elif running:
        add("ok", f"RAM runs at {running} MT/s" + (f" (kit rated {kit})." if kit else "."))
    if sysd.get("ram_modules") == 1:
        add(
            "warn",
            "Only one RAM module: memory runs single-channel, which costs FPS in CPU-limited games.",
        )

    # Display
    display = (
        next((d for d in sysd.get("displays") or [] if d.get("primary")), None)
        or ((sysd.get("displays") or [None])[0])
    )
    refresh = display.get("refresh_hz") if display else None
    if (
        display
        and display.get("max_refresh_hz")
        and refresh
        and refresh < display["max_refresh_hz"] - 1
    ):
        add(
            "warn",
            f"Display runs at {refresh} Hz but supports {display['max_refresh_hz']} Hz at this resolution.",
        )
    if disp.get("vsync"):
        add(
            "info",
            "VSync is on (sync interval {}). It adds latency; with G-Sync/FreeSync, a frame cap a few FPS below the refresh rate is the usual alternative.".format(
                disp.get("sync_interval")
            ),
        )
    if bn.get("cap_fps") and refresh and bn["cap_fps"] < refresh - 4 and not disp.get("vsync"):
        add(
            "info",
            f"FPS looks capped at ~{bn['cap_fps']:.0f}, below the {refresh} Hz refresh rate.",
        )
    mode = disp.get("present_mode") or ""
    if mode.startswith("Composed"):
        hint = (
            " 'Optimizations for windowed games' is off."
            if sysd.get("windowed_optimizations") is False
            else ""
        )
        add(
            "warn",
            f"Frames go through the desktop compositor ({mode}), which adds latency. Fullscreen or a flip-model borderless window avoids it.{hint}",
        )
    elif mode:
        add("ok", f"Present mode: {mode}.")

    # Windows settings
    plan = sysd.get("power_plan")
    if plan and "saver" in plan.lower():
        add("warn", f"Power plan is '{plan}', which limits CPU clocks.")
    if sysd.get("game_mode") is False:
        add("info", "Windows Game Mode is off.")
    if sysd.get("memory_integrity"):
        add("info", "Memory integrity (VBS/HVCI) is on. It can cost a few percent in some games.")
    if sysd.get("hags") and stats["avg_fps"] >= HIGH_FPS and bn.get("available"):
        add(
            "info",
            "HAGS is on and FPS is very high: the GPU-limited share may be overstated.",
            "capture",
        )

    # Capture quality
    if stats["spike_time_pct"] > 2:
        add(
            "warn",
            f"Stutter: {stats['spike_time_pct']:.1f}% of the time was spent in hitches (frames twice as long as their neighbours).",
            "capture",
        )
    if disp.get("dropped_pct") and disp["dropped_pct"] > 10:
        add("info", f"{disp['dropped_pct']:.0f}% of frames were never shown on screen.", "capture")
    if stats["duration_s"] < 10:
        add(
            "info",
            f"Short capture ({stats['duration_s']:.0f} s). 30 s or more gives steadier lows.",
            "capture",
        )
    if not bn.get("available"):
        add("info", "The CPU/GPU bottleneck split isn't available for this capture.", "capture")
    add("info", "Frame generation (DLSS/FSR) can't be detected. Say so if it was on.", "capture")
    return out


# Captures saved before checks had a kind: their capture notes, by how the text starts
_CAPTURE_NOTES = (
    "Stutter:",
    "Short capture",
    "HAGS is on and FPS is very high",
    "The CPU/GPU bottleneck split",
    "Frame generation",
)


def check_kind(c: dict) -> str:
    """system or capture, also for checks saved before the kind existed."""
    if c.get("kind"):
        return c["kind"]
    text = c.get("text", "")
    if text.startswith(_CAPTURE_NOTES) or text.endswith("were never shown on screen."):
        return "capture"
    return "system"


# --- rendering -------------------------------------------------------------------------------


def _f(x: float | None, digits: int = 1, unit: str = "") -> str:
    return "n/a" if x is None else f"{x:.{digits}f}{unit}"


def _when(iso: str | None) -> str:
    try:
        return dt.datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M") if iso else "?"
    except ValueError:
        return iso or "?"


def resolve_goal(
    r: dict, goal_key: str | None = None, target_fps: int | None = None
) -> tuple[goals.Goal, int | None]:
    """The goal to render with: an explicit one, else the capture's own. Target defaults to Hz."""
    saved, saved_target = goals.from_result(r)
    goal = goals.get(goal_key) if goal_key else saved
    target = target_fps or (saved_target if goal.key == saved.key else None)
    if goal.key == "target" and not target:
        target = goals.default_target(r) or 60
    return goal, target if goal.key == "target" else None


def game_name(r: dict) -> str:
    g = r.get("game") or {}
    return g.get("name") or r["capture"]["app"]


def goal_title(goal: goals.Goal, target: int | None) -> str:
    return f"{goal.label} ({target} FPS)" if target else goal.label


def bottleneck_hint(b: dict) -> str | None:
    """Which kind of in-game setting can move the frame rate, from the limit."""
    if not b.get("available"):
        return None
    if b.get("cap_fps"):
        return (
            "A cap or VSync sets the frame rate: raising or removing the cap (or the VSync/Reflex "
            "setting) moves it, and the GPU headroom can go into visual quality."
        )
    if b["gpu_pct"] >= 70:
        return (
            "GPU-heavy settings move the frame rate here: resolution and upscaling (DLSS/FSR/XeSS "
            "and their quality mode), shadows, lighting/global illumination, reflections, ambient "
            "occlusion, anti-aliasing, volumetrics and ray tracing."
        )
    if b["cpu_pct"] >= 70:
        return (
            "CPU-heavy settings move the frame rate here: view/draw distance, object and crowd "
            "density, physics and simulation detail, and anything the game says is CPU-bound. "
            "GPU-only settings (resolution, anti-aliasing) will barely change it."
        )
    if b["wait_pct"] >= 70:
        return "Frames mostly waited on VSync or a cap: the sync or cap setting sets the rate."
    return (
        "The limit moves between the CPU and GPU with the scene: settings on both sides matter, "
        "and the side that limits most often matters more."
    )


def goal_lines(r: dict, goal: goals.Goal, target: int | None) -> list[str]:
    """The numbers that measure the chosen goal, first in the report."""
    an = r["analysis"]
    s, b, d = an["stats"], an["bottleneck"], an["display"]
    avg, p1 = s["avg_fps"], s["p1_fps"]
    if goal.key == "avg_fps":
        out = [
            f"Average {avg:.1f} FPS | 1% low {p1:.1f} FPS | median frame time {s['median_ms']:.2f} ms"
        ]
        if b.get("gpu_fps_ceiling"):
            out.append(
                f"The GPU alone could do about {b['gpu_fps_ceiling']:.0f} FPS in this scene."
            )
        if b.get("cap_fps"):
            out.append(
                f"The frame rate looks capped at ~{b['cap_fps']:.0f} FPS: the cap limits the average."
            )
        return out
    if goal.key == "lows":
        return [
            (
                f"1% low {p1:.1f} FPS ({100 * p1 / avg:.0f}% of the {avg:.1f} FPS average)"
                f" | 0.1% low {s['p01_fps']:.1f} | 1% low avg {s['low1_avg_fps']:.1f}"
            ),
            (
                f"P99 frame time {s['p99_ms']:.2f} ms vs median {s['median_ms']:.2f} ms"
                f" | CPU-side 1% low {_f(s.get('cpu_p1_fps'))} (what in-game counters show)"
            ),
        ]
    if goal.key == "latency":
        if d.get("pc_latency_ms"):
            out = [
                (
                    f"PC latency (NVIDIA Reflex markers): median {d['pc_latency_ms']:.1f} ms"
                    f" | P95 {_f(d.get('pc_latency_p95_ms'), 1, ' ms')}"
                )
            ]
        else:
            out = [
                (
                    "PC latency: not measured (the game sent no NVIDIA Reflex markers). Use frame time, "
                    "VSync, the present mode and any cap as the latency signals."
                )
            ]
        out.append(
            f"Frame time median {s['median_ms']:.2f} ms | VSync {'on' if d.get('vsync') else 'off' if d.get('vsync') is False else '?'}"
            f" | present mode {d.get('present_mode') or '?'}"
            + (f" | capped at ~{b['cap_fps']:.0f} FPS" if b.get("cap_fps") else "")
            + (
                f" | GPU-limited {b['gpu_pct']:.0f}% of frames (a full GPU queue adds latency)"
                if b.get("available")
                else ""
            )
        )
        return out
    if goal.key == "stutter":
        return [
            f"Hitches: {s['spikes']} frames, {s['spike_time_pct']:.1f}% of the time"
            + (
                " | worst: " + ", ".join(f"{ms:.1f} ms @ {t:.1f} s" for ms, t in s["worst_spikes"])
                if s["worst_spikes"]
                else ""
            ),
            (
                f"0.1% low {s['p01_fps']:.1f} FPS | max frame time {s['max_ms']:.1f} ms"
                f" | frame time stdev {s['stdev_ms']:.2f} ms | worst second {_f(s.get('worst_1s_fps'))} FPS"
            ),
        ]
    # target
    at = goals.seconds_at_target_pct(s, target)
    status = goals.target_status(s, target)
    return [
        f"Target {target} FPS: {goals.TARGET_WORDS[status]}.",
        f"Average {avg:.1f} FPS ({100 * (avg - target) / target:+.0f}% vs target)"
        f" | 1% low {p1:.1f} ({100 * (p1 - target) / target:+.0f}%)"
        f" | 5% low {1000 / s['p95_ms']:.1f}"
        + (f" | {at:.0f}% of seconds at or above the target" if at is not None else ""),
    ]


def task_lines(r: dict, goal: goals.Goal, target: int | None) -> list[str]:
    """Instructions for the AI. The report is the prompt: it works without the skill."""
    name = game_name(r)
    has_settings = bool((r.get("game_settings") or {}).get("settings"))
    aim = (
        goal.aim
        if goal.key != "target"
        else f"hold {target} FPS at the best visual quality possible"
    )
    lines = [
        f"I benchmarked {name} with Frametrace. My goal: {aim} ({goal.trade_off}).",
        f"Recommend which in-game settings in {name} to change to reach this goal:",
        (
            "1. Base it on the data below. The bottleneck says which kind of setting can move the"
            " frame rate in this scene; use what you know about this game's settings and their cost."
        ),
    ]
    if has_settings:
        lines.append(
            "2. Start from my current settings (read from the game's config, listed below)."
            " Translate config names into the names in the game's menu."
        )
    else:
        lines.append(
            "2. My current settings couldn't be read automatically. Before recommending, ask me"
            " to paste them or send a screenshot of the graphics settings menu."
        )
    lines += [
        (
            "3. Give a ranked list of 1-3 changes to try first: setting, current value -> new value,"
            " the expected effect on the goal, and the visual cost."
        ),
        '4. If anything under "Fix first" is marked [!], mention it before the in-game changes.',
        (
            "5. I'll re-run the same scene after the change and paste the Frametrace comparison."
            " Say so if you aren't sure a setting exists in this version of the game."
        ),
    ]
    if goal.key == "target":
        lines.append(
            "If the target is met with room to spare, recommend which settings to raise for"
            " better visuals while staying above it."
        )
    return lines


def game_lines(r: dict) -> list[str]:
    g, cap, d = r.get("game") or {}, r["capture"], r["analysis"]["display"]
    src = {
        "steam": "from Steam",
        "version info": "from the exe",
        "window title": "from the window title",
    }
    name = g.get("name")
    out = [
        f"Game: {name} ({src.get(g.get('name_source'), g.get('name_source'))})"
        if name
        else f"Game: unknown, only the process name is known: {cap['app']}"
    ]
    if g.get("store"):
        out.append(
            f"Store: {g['store']} app {g.get('store_id') or '?'}"
            + (f", build {g['build']}" if g.get("build") else "")
        )
    exe = f"Executable: {cap['app']}"
    if g.get("version"):
        exe += f", version {g['version']}"
    if g.get("engine"):
        exe += f" | engine {g['engine']}"
    if d.get("runtime"):
        exe += f" | graphics API {d['runtime']}"
    out.append(exe)
    if g.get("window_title") and g.get("window_title") != name:
        out.append(f"Window title: {g['window_title']}")
    return out


def settings_lines(r: dict) -> list[str]:
    gs = r.get("game_settings") or {}
    if not gs.get("settings"):
        return [
            "Not read automatically for this game (no supported settings file found).",
            "AI: ask me for them first, pasted or as a screenshot of the graphics menu.",
        ]
    out = [f"Read from: {gs.get('reader')} ({gs.get('source')})"]
    if gs.get("modified"):
        changed = dt.datetime.fromtimestamp(gs["modified"]).astimezone().strftime("%Y-%m-%d %H:%M")
        out[0] += f", last saved {changed}"
    out += [f"{k} = {v}" for k, v in gs["settings"]]
    return out


def render(r: dict, goal_key: str | None = None, target_fps: int | None = None) -> str:
    """The report: a ready-made prompt for any AI. The goal leads, the evidence follows."""
    cap, an, sysd = r["capture"], r["analysis"], r.get("system") or {}
    s, b, d = an["stats"], an["bottleneck"], an["display"]
    goal, target = resolve_goal(r, goal_key, target_fps)
    lines = [
        f"Frametrace report · {game_name(r)} · {_when(cap.get('started'))} · {s['duration_s']:.1f} s analyzed"
        + (f" (first {an['skipped_start_s']:.0f} s skipped)" if an.get("skipped_start_s") else ""),
        f"Goal: {goal_title(goal, target)}",
        "",
        "## Task for the AI",
        *task_lines(r, goal, target),
        "",
        f"## Goal: {goal_title(goal, target)}",
        *goal_lines(r, goal, target),
        "",
        "## Game",
        *game_lines(r),
        "",
        "## Current in-game settings",
        *settings_lines(r),
        "",
        "## Bottleneck",
    ]
    if b["available"]:
        lines += [
            f"Verdict: {b['verdict']}",
            (
                f"Frames: GPU-limited {b['gpu_pct']:.0f}% | CPU-limited {b['cpu_pct']:.0f}%"
                f" | waiting (VSync/cap) {b['wait_pct']:.0f}%"
            ),
            (
                f"Median GPU busy {_f(b['median_gpu_busy_ms'], 2, ' ms')} (GPU alone could do ~{_f(b['gpu_fps_ceiling'], 0)} FPS)"
                f" | presenting thread: CPU busy {_f(b['median_cpu_busy_ms'], 2, ' ms')},"
                f" blocked in Present {_f(b['median_cpu_wait_ms'], 2, ' ms')}"
                " (game threads that don't present aren't measured)"
            ),
        ]
        hint = bottleneck_hint(b)
        if hint:
            lines.append(f"For settings: {hint}")
    lines += [f"Note: {n}" for n in b["notes"]]
    lines += [
        "",
        "## Performance",
        (
            f"Average {s['avg_fps']:.1f} FPS | 1% low (P1) {s['p1_fps']:.1f} | 0.1% low {s['p01_fps']:.1f}"
            f" | 1% low avg {s['low1_avg_fps']:.1f} | worst 1 s {_f(s.get('worst_1s_fps'))}"
        ),
        (
            f"Frame time: median {s['median_ms']:.2f} ms | P95 {s['p95_ms']:.2f} | P99 {s['p99_ms']:.2f}"
            f" | P99.9 {s['p999_ms']:.2f} | max {s['max_ms']:.2f} | stdev {s['stdev_ms']:.2f}"
        ),
        (
            f"CPU-side frame pacing (what in-game counters measure): 1% low {_f(s.get('cpu_p1_fps'))}"
            f" | P99 {_f(s.get('cpu_p99_ms'), 2, ' ms')}"
        ),
        f"Hitches (frames 2x longer than their neighbours and +4 ms): {s['spikes']} frames, {s['spike_time_pct']:.1f}% of the time"
        + (
            " | worst: " + ", ".join(f"{ms:.1f} ms @ {t:.1f} s" for ms, t in s["worst_spikes"])
            if s["worst_spikes"]
            else ""
        ),
        "",
        "## Display path",
        (
            f"API: {d.get('runtime') or '?'} | Present mode: {d.get('present_mode') or '?'} ({d['present_mode_pct']:.0f}%)"
            f" | tearing {'allowed' if d.get('tearing_allowed') else 'not allowed' if d.get('tearing_allowed') is False else '?'}"
            f" | VSync {'on' if d.get('vsync') else 'off' if d.get('vsync') is False else '?'}"
            f" | not displayed {_f(d.get('dropped_pct'), 1, '%')}"
            f" | displayed {_f(d.get('displayed_fps'), 1, ' FPS')}"
        ),
    ]
    if d.get("pc_latency_ms"):
        lines.append(
            f"PC latency (NVIDIA Reflex markers, input to frame sent to display): median "
            f"{d['pc_latency_ms']:.1f} ms | P95 {_f(d.get('pc_latency_p95_ms'), 1, ' ms')}"
        )
    if d.get("input_to_photon_ms"):
        lines.append(
            f"Input to photon (median, software-measured): {d['input_to_photon_ms']:.1f} ms"
        )
    marks = {"warn": "[!]", "info": "[i]", "ok": "[ok]"}
    found = r.get("checks", [])
    notes = [c for c in found if check_kind(c) == "capture"]
    fixes = [c for c in found if check_kind(c) == "system"]
    if notes:
        lines += ["", "## Capture notes"]
        lines += [f"{marks[c['level']]} {c['text']}" for c in notes]
    lines += ["", "## Fix first (outside the game)"]
    lines += [f"{marks[c['level']]} {c['text']}" for c in fixes] or ["[ok] Nothing found."]
    lines += [
        "",
        "## System",
        *render_system(sysd),
        "",
        (
            f"Detected via: {cap.get('reason', '?')} | PresentMon {cap.get('presentmon', '?')}"
            f" | Frametrace {r.get('frametrace')} ({REPO_URL})"
        ),
    ]
    return "\n".join(lines) + "\n"


def render_system(sysd: dict) -> list[str]:
    if not sysd or not sysd.get("cpu"):
        return ["(system info not available)"]
    out = [f"CPU: {sysd['cpu']} ({sysd.get('cpu_cores')}C/{sysd.get('cpu_threads')}T)"]
    gpus = sysd.get("gpus") or []
    for g in gpus:
        drv = g.get("nvidia_driver") or g.get("driver") or "?"
        out.append(
            f"GPU: {g['name']}, driver {drv}"
            + (f" ({g['driver_date']})" if g.get("driver_date") else "")
        )
    ram = f"RAM: {_f(sysd.get('ram_total_gb'), 0)} GB {sysd.get('ram_type') or ''}".rstrip()
    ram += (
        f" ({sysd.get('ram_modules')} modules), running {sysd.get('ram_running_mts') or '?'} MT/s"
    )
    if sysd.get("ram_kit_mts"):
        ram += f", kit rated {sysd['ram_kit_mts']}"
    if sysd.get("ram_part"):
        ram += f" ({sysd['ram_part']})"
    out.append(ram)
    if sysd.get("board") or sysd.get("bios"):
        out.append(
            f"Board: {sysd.get('board') or '?'}, BIOS {sysd.get('bios') or '?'}"
            + (f" ({sysd['bios_date']})" if sysd.get("bios_date") else "")
        )
    out.append(
        f"OS: {sysd.get('os_name') or 'Windows'} {sysd.get('os_release') or ''}, build {sysd.get('os_build') or '?'}".replace(
            "  ", " "
        )
    )
    for disp in sysd.get("displays") or []:
        out.append(
            f"Display{' (primary)' if disp.get('primary') and len(sysd['displays']) > 1 else ''}: "
            f"{disp['width']}x{disp['height']} @ {disp['refresh_hz']} Hz (max {disp.get('max_refresh_hz') or '?'} Hz), {disp.get('name')}"
        )

    def onoff(v: bool | None) -> str:
        return "?" if v is None else "on" if v else "off"

    out.append(
        f"Settings: power plan {sysd.get('power_plan') or '?'} | Game Mode {onoff(sysd.get('game_mode'))}"
        f" | HAGS {onoff(sysd.get('hags'))} | memory integrity {onoff(sysd.get('memory_integrity'))}"
        f" | windowed optimizations {onoff(sysd.get('windowed_optimizations'))}"
    )
    return out


# --- compare mode ----------------------------------------------------------------------------

COMPARE_ROWS = [
    # label, path, digits, higher_is_better
    ("Average FPS", ("stats", "avg_fps"), 1, True),
    ("1% low (P1) FPS", ("stats", "p1_fps"), 1, True),
    ("0.1% low FPS", ("stats", "p01_fps"), 1, True),
    ("Worst 1 s FPS", ("stats", "worst_1s_fps"), 1, True),
    ("Median frame time (ms)", ("stats", "median_ms"), 2, False),
    ("P99 frame time (ms)", ("stats", "p99_ms"), 2, False),
    ("Max frame time (ms)", ("stats", "max_ms"), 2, False),
    ("CPU-side 1% low FPS", ("stats", "cpu_p1_fps"), 1, True),
    ("Time in hitches (%)", ("stats", "spike_time_pct"), 1, False),
    ("GPU-limited frames (%)", ("bottleneck", "gpu_pct"), 0, None),
    ("CPU-limited frames (%)", ("bottleneck", "cpu_pct"), 0, None),
    ("Median GPU busy (ms)", ("bottleneck", "median_gpu_busy_ms"), 2, False),
    ("Presenting-thread CPU busy (ms)", ("bottleneck", "median_cpu_busy_ms"), 2, False),
    ("PC latency, median (ms)", ("display", "pc_latency_ms"), 1, False),
]

SYSTEM_FIELDS = [
    ("CPU", "cpu"),
    ("RAM speed", "ram_running_mts"),
    ("BIOS", "bios"),
    ("OS build", "os_build"),
    ("Power plan", "power_plan"),
    ("Game Mode", "game_mode"),
    ("HAGS", "hags"),
    ("Memory integrity", "memory_integrity"),
]


def compare(a: dict, b: dict, goal_key: str | None = None, target_fps: int | None = None) -> str:
    """Before (A) and after (B) for the goal, as a follow-up prompt for the AI."""
    from frametrace import summary

    ca, cb = a["capture"], b["capture"]
    goal, target = resolve_goal(b, goal_key, target_fps)
    head, _, notes = summary.compare_verdict(a, b, goal, target)
    _, decide = summary.goal_status(a, b, goal, target)
    deltas = summary.goal_deltas(a, b, target)
    shown = {d.label for d in decide}
    side = [
        deltas[k]
        for k in summary.KEY_METRICS
        if k in deltas and k not in shown and deltas[k].status in ("better", "worse")
    ]
    word = {"better": "better", "worse": "worse", "same": "no change (inside noise)"}

    def item(d) -> str:
        return (
            f"- {d.label}: {d.fmt(d.a)} -> {d.fmt(d.b)}{'' if d.unit == '%' else ' '}{d.unit}"
            f" ({d.change_text()}),"
            f" {word.get(d.status, d.status)}"
        )

    name = game_name(b)
    lines = [
        (
            f"Frametrace compare · {name} · A (before): {_when(ca.get('started'))}"
            f" · B (after): {_when(cb.get('started'))}"
        ),
        f"Goal: {goal_title(goal, target)}",
        "",
        "## Result for the goal",
        summary.plain(head),
        *(item(d) for d in decide),
        *(["Side effects:", *(item(d) for d in side)] if side else []),
        *(f"Note: {n}" for n in notes),
        (
            "(Run-to-run noise: average and median 1%, lows and P99 3%, 0.1% low and worst second"
            " 5%, max frame time 15%. Changes inside it count as no change.)"
        ),
        "",
        "## In-game settings changed (A -> B)",
    ]
    changes = summary.settings_changes(a, b)
    if changes is None:
        lines.append(
            "Not read automatically for this game. AI: ask me what I changed between A and B."
        )
    elif changes:
        lines += [f"- {k}: {va} -> {vb}" for k, va, vb in changes]
    else:
        lines.append(
            "None in the settings file. If I changed something, it may not be saved there"
            " (or it's a console command): ask me."
        )
    lines += [
        "",
        "## Task for the AI",
        f"A is before and B is after I changed settings in {name}. My goal: "
        + (
            f"hold {target} FPS at the best visual quality possible."
            if goal.key == "target"
            else f"{goal.aim} ({goal.trade_off})."
        ),
        "1. Tell me whether to keep the change, counting run-to-run noise.",
        (
            "2. Recommend the next 1-3 settings to try, from B's bottleneck and current settings"
            " below; same format as before (setting, current -> new, effect on the goal, visual cost)."
        ),
        "3. If the change made things worse, say whether to undo it before trying the next one.",
        "",
        "| Metric | A | B | Change |",
        "|---|---|---|---|",
    ]
    for label, (section, key), digits, _better in COMPARE_ROWS:
        va, vb = a["analysis"][section].get(key), b["analysis"][section].get(key)
        if va is None and vb is None:
            continue
        if va is not None and vb is not None and section == "bottleneck" and key.endswith("_pct"):
            change = f"{vb - va:+.0f} pp"
        elif va and vb is not None:
            change = f"{100 * (vb - va) / va:+.1f}%"
        else:
            change = "n/a"
        lines.append(f"| {label} | {_f(va, digits)} | {_f(vb, digits)} | {change} |")
    if target:
        va = goals.seconds_at_target_pct(a["analysis"]["stats"], target)
        vb = goals.seconds_at_target_pct(b["analysis"]["stats"], target)
        if va is not None and vb is not None:
            lines.append(
                f"| Seconds at or above {target} FPS (%) | {va:.0f} | {vb:.0f} | {vb - va:+.0f} pp |"
            )
    lines.append(
        f"| Bottleneck verdict | {a['analysis']['bottleneck']['verdict']} | {b['analysis']['bottleneck']['verdict']} | |"
    )
    hint = bottleneck_hint(b["analysis"]["bottleneck"])
    if hint:
        lines += ["", f"B for settings: {hint}"]

    lines += [
        "",
        "## Game",
        *game_lines(b),
        "",
        "## Current in-game settings (B)",
        *settings_lines(b),
    ]

    diffs = []
    sa, sb = a.get("system") or {}, b.get("system") or {}
    for label, key in SYSTEM_FIELDS:
        if sa.get(key) != sb.get(key):
            diffs.append(f"- {label}: {sa.get(key)} -> {sb.get(key)}")
    ga = [(g["name"], g.get("nvidia_driver") or g.get("driver")) for g in sa.get("gpus") or []]
    gb = [(g["name"], g.get("nvidia_driver") or g.get("driver")) for g in sb.get("gpus") or []]
    if ga != gb:
        diffs.append(f"- GPU/driver: {ga} -> {gb}")
    da = [(d["width"], d["height"], d["refresh_hz"]) for d in sa.get("displays") or []]
    db = [(d["width"], d["height"], d["refresh_hz"]) for d in sb.get("displays") or []]
    if da != db:
        diffs.append(f"- Display mode: {da} -> {db}")
    lines += ["", "## System differences", *(diffs or ["- none detected"])]
    for label, r in (("A", a), ("B", b)):
        warns = [
            c["text"]
            for c in r.get("checks", [])
            if c["level"] == "warn" and check_kind(c) == "system"
        ]
        if warns:
            lines += ["", f"Fix first, flagged in {label}:", *(f"- {w}" for w in warns)]
    lines += ["", f"Frametrace {b.get('frametrace')} ({REPO_URL})"]
    return "\n".join(lines) + "\n"
