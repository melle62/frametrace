"""Plain-text pieces of the summary view, computed from a saved result.

Kept apart from the Tk code so the wording can be tested without a display.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

PRESENT_MODE_SHORT = {
    "Hardware: Independent Flip": "INDEPENDENT FLIP",
    "Hardware Composed: Independent Flip": "COMPOSED FLIP",
    "Hardware: Legacy Flip": "LEGACY FLIP",
    "Hardware: Legacy Copy to front buffer": "LEGACY COPY",
    "Composed: Flip": "COMPOSED",
    "Composed: Copy with GPU GDI": "COMPOSED COPY",
    "Composed: Copy with CPU GDI": "COMPOSED COPY",
}


@dataclass
class ReadoutValue:
    title: str
    value: str | None
    unit: str
    sub: str
    swatch: str | None = None


def when(iso: str | None, fmt: str = "%d %b %H:%M") -> str:
    try:
        return dt.datetime.fromisoformat(iso).strftime(fmt) if iso else "?"
    except ValueError:
        return iso or "?"


def _num(v: float | None, digits: int = 1) -> str | None:
    return None if v is None else f"{v:,.{digits}f}"


def initials(app: str) -> str:
    stem = app.rsplit(".", 1)[0] if app.lower().endswith(".exe") else app
    letters = [ch for ch in stem if ch.isalnum()]
    return "".join(letters[:2]).upper() or "?"


def subtitle(result: dict) -> str:
    cap, an = result["capture"], result["analysis"]
    s = an["stats"]
    parts = [
        when(cap.get("started")),
        f"{s['duration_s']:.1f} s analyzed",
        f"{s['frames']:,} frames",
    ]
    if an.get("skipped_start_s"):
        parts.append(f"first {an['skipped_start_s']:.0f} s skipped")
    return " · ".join(parts)


def tags(result: dict) -> list[str]:
    d = result["analysis"]["display"]
    out = []
    if d.get("runtime"):
        out.append(str(d["runtime"]).upper())
    mode = d.get("present_mode")
    if mode:
        out.append(PRESENT_MODE_SHORT.get(mode, mode.upper()))
    if d.get("vsync") is not None:
        out.append("VSYNC ON" if d["vsync"] else "VSYNC OFF")
    if d.get("pc_latency_ms"):
        out.append("REFLEX")
    return out


def verdict(result: dict) -> tuple[str, str]:
    """(headline, one sentence) for the verdict panel."""
    b = result["analysis"]["bottleneck"]
    if not b.get("available"):
        return (
            "No bottleneck data.",
            "This capture has no GPU busy column, so the CPU and GPU can't be told apart.",
        )
    gpu, cpu, wait = b["gpu_pct"], b["cpu_pct"], b["wait_pct"]
    busy, ceiling = b.get("median_gpu_busy_ms"), b.get("gpu_fps_ceiling")
    gpu_note = f" Median GPU busy {busy:.2f} ms" if busy else ""
    if b.get("cap_fps"):
        return (
            f"Capped at {b['cap_fps']:.0f} FPS.",
            f"A frame cap or VSync holds the frame rate, so {wait:.0f}% of frames were waiting."
            + (
                f"{gpu_note}: the GPU alone could do about {ceiling:,.0f} FPS."
                if busy and ceiling
                else ""
            ),
        )
    top = max((gpu, "GPU"), (cpu, "CPU"), (wait, "wait"))
    if top[0] >= 70 and top[1] == "GPU":
        return (
            "GPU-limited.",
            f"{gpu:.0f}% of frames waited on the GPU."
            + (
                f"{gpu_note}: the GPU alone could do about {ceiling:,.0f} FPS."
                if busy and ceiling
                else ""
            ),
        )
    if top[0] >= 70 and top[1] == "CPU":
        return (
            "CPU-limited.",
            f"{cpu:.0f}% of frames waited on the CPU."
            + (
                f"{gpu_note}, so the GPU had room for about {ceiling:,.0f} FPS."
                if busy and ceiling
                else ""
            ),
        )
    if top[0] >= 70:
        return (
            "Waiting on VSync or a cap.",
            f"{wait:.0f}% of frames finished early and waited to be shown.",
        )
    lean = {"GPU": "the GPU", "CPU": "the CPU", "wait": "VSync or a cap"}[top[1]]
    return (
        f"Mixed, leaning {top[1] if top[1] != 'wait' else 'waiting'}.",
        f"GPU-limited {gpu:.0f}%, CPU-limited {cpu:.0f}%, waiting {wait:.0f}%. The scene moves the limit; {lean} wins most often.",
    )


def readouts(result: dict) -> list[ReadoutValue]:
    an = result["analysis"]
    s, d = an["stats"], an["display"]
    lat, lat95 = d.get("pc_latency_ms"), d.get("pc_latency_p95_ms")
    out = [
        ReadoutValue(
            "Average", _num(s["avg_fps"]), "FPS", f"median {s['median_ms']:.2f} ms", "ch1"
        ),
        ReadoutValue("1% low", _num(s["p1_fps"], 0), "FPS", f"P99 {s['p99_ms']:.2f} ms"),
        ReadoutValue(
            "CPU-side 1% low",
            _num(s.get("cpu_p1_fps"), 0),
            "FPS",
            "in-game counter" if s.get("cpu_p1_fps") else "not in this CSV",
        ),
        ReadoutValue(
            "PC latency", _num(lat), "ms", "Reflex markers" if lat else "needs NVIDIA Reflex"
        ),
    ]
    if lat95:
        out.append(ReadoutValue("P95 latency", _num(lat95), "ms", "input to frame sent"))
    else:
        out.append(
            ReadoutValue("0.1% low", _num(s["p01_fps"], 0), "FPS", f"P99.9 {s['p999_ms']:.2f} ms")
        )
    return out


def details(result: dict) -> list[tuple[str, str]]:
    an = result["analysis"]
    s, b, d = an["stats"], an["bottleneck"], an["display"]

    def ms(v):
        return f"{v:.2f} ms" if v is not None else "n/a"

    worst = f" · worst {s['worst_spikes'][0][0]:.1f} ms" if s.get("worst_spikes") else ""
    rows = [
        ("GPU busy, median", ms(b.get("median_gpu_busy_ms"))),
        ("CPU busy, median", ms(b.get("median_cpu_busy_ms"))),
        ("Blocked in Present", ms(b.get("median_cpu_wait_ms"))),
        ("Hitches", f"{s['spikes']}{worst}"),
        (
            "Not displayed",
            f"{d['dropped_pct']:.1f}%" if d.get("dropped_pct") is not None else "n/a",
        ),
    ]
    return rows


def rail_row(result: dict) -> tuple[str, str, str, str, str]:
    """(lamp level, name, meta, fps, sub) for the captures list."""
    cap, an = result["capture"], result["analysis"]
    s, b = an["stats"], an["bottleneck"]
    if b.get("cap_fps"):
        sub, level = f"cap {b['cap_fps']:.0f}", "info"
    elif b.get("available"):
        top = max((b["gpu_pct"], "GPU"), (b["cpu_pct"], "CPU"), (b["wait_pct"], "wait"))
        sub, level = f"{top[1]} {top[0]:.0f}%", "ok"
    else:
        sub, level = "no GPU data", "info"
    if s["duration_s"] < 10:
        sub, level = "short", "warn"
    meta = f"{when(cap.get('started'))} · {s['duration_s']:.0f} s"
    return level, cap["app"], meta, f"{s['avg_fps']:.1f}", sub


def system_rows(lines: list[str]) -> list[tuple[str, str]]:
    """'CPU: AMD ...' lines from report.render_system as (label, value) rows."""
    out = []
    for line in lines:
        key, sep, value = line.partition(": ")
        out.append((key, value) if sep else ("", line))
    return out
