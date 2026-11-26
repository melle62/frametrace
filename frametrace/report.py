"""The compact, AI-ready text report, its JSON form, automatic checks and compare mode.

A capture produces one result dict (JSON-serializable, saved as result.json). The text
report and the compare table are rendered from result dicts only, so old captures can
always be re-rendered and compared.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from frametrace import __version__
from frametrace.analyze import HIGH_FPS, Analysis
from frametrace.sysinfo import SystemInfo

REPO_URL = "https://github.com/melle62/frametrace"
RESULT_FORMAT = 1


def build_result(analysis: Analysis, system: SystemInfo, meta: dict[str, Any]) -> dict:
    """Bundle everything about one capture. meta: started, requested_s, reason, presentmon, ..."""
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
        "analysis": analysis.to_dict(),
        "system": system.to_dict(),
    }
    result["checks"] = checks(result)
    return result


# --- automatic checks ------------------------------------------------------------------------


def checks(r: dict) -> list[dict]:
    """Problems worth fixing before tuning game settings. level: warn, info or ok."""
    out: list[dict] = []

    def add(level: str, text: str) -> None:
        out.append({"level": level, "text": text})

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
        add("info", "HAGS is on and FPS is very high: the GPU-limited share may be overstated.")

    # Capture quality
    if stats["spike_time_pct"] > 2:
        add(
            "warn",
            f"Stutter: {stats['spike_time_pct']:.1f}% of the time was spent in spike frames.",
        )
    if disp.get("dropped_pct") and disp["dropped_pct"] > 10:
        add("info", f"{disp['dropped_pct']:.0f}% of frames were never shown on screen.")
    if stats["duration_s"] < 10:
        add(
            "info",
            f"Short capture ({stats['duration_s']:.0f} s). 30 s or more gives steadier lows.",
        )
    if not bn.get("available"):
        add("info", "The CPU/GPU bottleneck split isn't available for this capture.")
    add("info", "Frame generation (DLSS/FSR) can't be detected. Say so if it was on.")
    return out


# --- rendering -------------------------------------------------------------------------------


def _f(x: float | None, digits: int = 1, unit: str = "") -> str:
    return "n/a" if x is None else f"{x:.{digits}f}{unit}"


def _when(iso: str | None) -> str:
    try:
        return dt.datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M") if iso else "?"
    except ValueError:
        return iso or "?"


def render(r: dict) -> str:
    cap, an, sysd = r["capture"], r["analysis"], r.get("system") or {}
    s, b, d = an["stats"], an["bottleneck"], an["display"]
    lines = [
        f"Frametrace report · {cap['app']} · {_when(cap.get('started'))} · {s['duration_s']:.1f} s analyzed"
        + (f" (first {an['skipped_start_s']:.0f} s skipped)" if an.get("skipped_start_s") else ""),
        f"(Paste into any AI. Frametrace skill: {REPO_URL})",
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
        f"Spikes (> {s['spike_threshold_ms']:.1f} ms): {s['spikes']} frames, {s['spike_time_pct']:.1f}% of the time"
        + (
            " | worst: " + ", ".join(f"{ms:.1f} ms @ {t:.1f} s" for ms, t in s["worst_spikes"])
            if s["worst_spikes"]
            else ""
        ),
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
    lines += [f"Note: {n}" for n in b["notes"]]
    lines += [
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
    if d.get("input_to_photon_ms"):
        lines.append(
            f"Input to photon (median, software-measured): {d['input_to_photon_ms']:.1f} ms"
        )
    lines += ["", "## System", *render_system(sysd), "", "## Checks"]
    marks = {"warn": "[!]", "info": "[i]", "ok": "[ok]"}
    lines += [f"{marks[c['level']]} {c['text']}" for c in r.get("checks", [])]
    lines += [
        "",
        f"Detected via: {cap.get('reason', '?')} | PresentMon {cap.get('presentmon', '?')} | Frametrace {r.get('frametrace')}",
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
    ("Time in spikes (%)", ("stats", "spike_time_pct"), 1, False),
    ("GPU-limited frames (%)", ("bottleneck", "gpu_pct"), 0, None),
    ("CPU-limited frames (%)", ("bottleneck", "cpu_pct"), 0, None),
    ("Median GPU busy (ms)", ("bottleneck", "median_gpu_busy_ms"), 2, False),
    ("Presenting-thread CPU busy (ms)", ("bottleneck", "median_cpu_busy_ms"), 2, False),
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


def compare(a: dict, b: dict) -> str:
    ca, cb = a["capture"], b["capture"]
    lines = [
        f"Frametrace compare · A: {ca['app']} {_when(ca.get('started'))} · B: {cb['app']} {_when(cb.get('started'))}",
        f"(Paste into any AI. Frametrace skill: {REPO_URL})",
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
    lines.append(
        f"| Bottleneck verdict | {a['analysis']['bottleneck']['verdict']} | {b['analysis']['bottleneck']['verdict']} | |"
    )

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
    lines += ["", "System differences:", *(diffs or ["- none detected"])]
    for name, r in (("A", a), ("B", b)):
        warns = [c["text"] for c in r.get("checks", []) if c["level"] == "warn"]
        if warns:
            lines += ["", f"Warnings in {name}:", *(f"- {w}" for w in warns)]
    return "\n".join(lines) + "\n"
