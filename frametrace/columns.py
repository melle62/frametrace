"""PresentMon CSV schema detection and column mapping.

PresentMon has renamed its CSV columns twice, and its README does not always match
what the binary writes. So Frametrace never hardcodes a PresentMon column name
outside this module: it reads the header row, works out which schema it is, and
maps the columns to the canonical names below. Everything downstream (analysis,
report) only uses canonical names.

Schemas, verified against the PresentMon v2.6.0 source (PresentMon/CsvOutput.cpp)
and the strings in the released PresentMon-2.6.0-x64.exe:

    V1  PresentMon 1.x, or 2.x with --v1_metrics
        Runtime, Dropped, TimeInSeconds, msBetweenPresents, msGPUActive, ...
    V2  PresentMon 2.0-2.5 default, or 2.6+ with --v2_metrics
        PresentRuntime, CPUStartTime, FrameTime, CPUBusy, CPUWait, GPUBusy, ...
    V3  PresentMon 2.6+ default
        TimeInMs, MsBetweenPresents, CPUStartTimeInMs, MsBetweenAppStart,
        MsCPUBusy, MsCPUWait, MsGPUBusy, ...

All canonical time values are milliseconds except time_s, which is seconds since the
capture started. PresentMon 2.6 writes its time axis in milliseconds by default
(TimeInMs), 1.x in seconds (TimeInSeconds), and 2.x as CPUStartTime, whose unit
depends on the version; time_s is converted from whichever unit the file uses.
Captures made with --qpc_time or --date_time are not supported.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import Enum
from itertools import pairwise
from pathlib import Path


class Schema(str, Enum):
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"
    UNKNOWN = "unknown"


# Canonical name -> candidate PresentMon headers, matched case-insensitively.
# The first candidate present in the header row wins.
CANDIDATES: dict[str, tuple[str, ...]] = {
    # identity
    "app": ("Application",),
    "pid": ("ProcessID",),
    "swapchain": ("SwapChainAddress",),
    "runtime": ("PresentRuntime", "Runtime"),
    "sync_interval": ("SyncInterval",),
    "present_flags": ("PresentFlags",),
    "allows_tearing": ("AllowsTearing",),
    "present_mode": ("PresentMode",),
    "frame_type": ("FrameType",),
    "dropped": ("Dropped",),  # V1 only; V2/V3 mark undisplayed frames with NA instead
    # time axis, converted to seconds since capture start (see TIME_SCALE)
    "time_s": (
        "TimeInMs",
        "TimeInSeconds",
        "CPUStartTimeInMs",
        "CPUStartTimeInSeconds",
        "CPUStartTime",
    ),
    # classic frame time: interval between Present() calls (what CapFrameX etc. use)
    "ms_between_presents": ("MsBetweenPresents",),
    "ms_in_present_api": ("MsInPresentAPI",),
    "ms_between_display_change": ("MsBetweenDisplayChange",),
    "ms_until_displayed": ("MsUntilDisplayed",),
    "ms_displayed_time": ("DisplayedTime",),  # V2 only
    "ms_display_latency": ("DisplayLatency",),  # V2 only
    # CPU-side frame interval and its busy/wait split (V2/V3 only)
    "ms_frame_time": ("MsBetweenAppStart", "FrameTime"),
    "ms_cpu_busy": ("MsCPUBusy", "CPUBusy"),
    "ms_cpu_wait": ("MsCPUWait", "CPUWait"),
    # GPU work for the frame
    "ms_gpu_latency": ("MsGPULatency", "GPULatency"),
    "ms_gpu_time": ("MsGPUTime", "GPUTime"),
    "ms_gpu_busy": ("MsGPUBusy", "GPUBusy", "msGPUActive"),  # msGPUActive = V1 equivalent
    "ms_gpu_wait": ("MsGPUWait", "GPUWait"),
    # pacing and latency
    "ms_animation_error": ("MsAnimationError", "AnimationError"),
    "ms_flip_delay": ("MsFlipDelay",),
    "ms_click_to_photon": ("MsClickToPhotonLatency", "ClickToPhotonLatency"),
    "ms_all_input_to_photon": ("MsAllInputToPhotonLatency", "AllInputToPhotonLatency"),
    "ms_pc_latency": ("MsPCLatency",),
}

# Factor that converts each time-axis column to seconds. None = unit not in the name,
# worked out from the data (see _infer_time_scale).
TIME_SCALE: dict[str, float | None] = {
    "timeinms": 0.001,
    "cpustarttimeinms": 0.001,
    "timeinseconds": 1.0,
    "cpustarttimeinseconds": 1.0,
    "cpustarttime": None,
}

INT_FIELDS = frozenset({"pid", "sync_interval", "allows_tearing", "dropped"})
TEXT_FIELDS = frozenset(
    {"app", "swapchain", "runtime", "present_flags", "present_mode", "frame_type"}
)

# What each Frametrace feature needs. Used to report gaps clearly instead of failing late.
REQUIRED_FOR = {
    "frame_stats": ("app", "pid", "time_s", "ms_between_presents"),
    "bottleneck": ("ms_frame_time", "ms_gpu_busy"),
    "cpu_split": ("ms_cpu_busy", "ms_cpu_wait"),
    "display_checks": ("present_mode", "allows_tearing", "sync_interval"),
}


def detect_schema(headers: Sequence[str]) -> Schema:
    """Work out which PresentMon CSV format a header row belongs to."""
    exact = {h.strip() for h in headers}
    if "MsBetweenAppStart" in exact:
        return Schema.V3
    if {"FrameTime", "CPUBusy"} <= exact:
        return Schema.V2
    # V1 uses lowercase "ms" prefixes and "Runtime"/"Dropped" instead of "PresentRuntime"
    if "msBetweenPresents" in exact or "Dropped" in exact or "Runtime" in exact:
        return Schema.V1
    return Schema.UNKNOWN


@dataclass(frozen=True)
class ColumnMap:
    schema: Schema
    headers: tuple[str, ...]
    index: dict[str, int]  # canonical name -> column position

    def has(self, *names: str) -> bool:
        return all(n in self.index for n in names)

    def missing(self, names: Sequence[str]) -> list[str]:
        return [n for n in names if n not in self.index]

    def capabilities(self) -> dict[str, bool]:
        return {feature: self.has(*cols) for feature, cols in REQUIRED_FOR.items()}

    def unmapped_headers(self) -> list[str]:
        used = set(self.index.values())
        return [h for i, h in enumerate(self.headers) if i not in used]


def map_columns(headers: Sequence[str]) -> ColumnMap:
    headers = tuple(h.strip().lstrip("\ufeff") for h in headers)
    lower = {h.lower(): i for i, h in enumerate(headers)}
    index: dict[str, int] = {}
    for canonical, candidates in CANDIDATES.items():
        for cand in candidates:
            pos = lower.get(cand.lower())
            if pos is not None:
                index[canonical] = pos
                break
    return ColumnMap(schema=detect_schema(headers), headers=headers, index=index)


def _convert(name: str, raw: str):
    raw = raw.strip()
    if raw == "" or raw.upper() == "NA":
        return None
    if name in TEXT_FIELDS:
        return raw
    try:
        return int(raw) if name in INT_FIELDS else float(raw)
    except ValueError:
        return None


def _infer_time_scale(rows: list[dict]) -> float:
    """Seconds-per-unit of a time column whose name doesn't say its unit.

    Compares the step between consecutive frames of the same process with the
    frame time in milliseconds: equal steps mean the column is in ms.
    """
    by_pid: dict[object, list[float]] = {}
    frame_ms: list[float] = []
    for r in rows:
        if r.get("time_s") is not None:
            by_pid.setdefault(r.get("pid"), []).append(r["time_s"])
        ft = r.get("ms_frame_time") or r.get("ms_between_presents")
        if ft:
            frame_ms.append(ft)
    steps = sorted(b - a for times in by_pid.values() for a, b in pairwise(times) if b > a)
    if not steps or not frame_ms:
        return 0.001  # PresentMon 2.6+ default is milliseconds
    median_step = steps[len(steps) // 2]
    median_frame = sorted(frame_ms)[len(frame_ms) // 2]
    return 0.001 if median_step / median_frame > 0.1 else 1.0


def iter_frames(stream: io.TextIOBase) -> tuple[ColumnMap, Iterator[dict]]:
    """Return the column map and an iterator of rows keyed by canonical name.

    Missing values ("NA" or empty) become None. Rows shorter than the header
    (e.g. a capture cut off mid-write) are skipped. time_s is in seconds.
    """
    reader = csv.reader(stream)
    try:
        headers = next(reader)
    except StopIteration:
        raise ValueError("empty CSV: no header row") from None
    cmap = map_columns(headers)
    width = len(cmap.headers)
    time_pos = cmap.index.get("time_s")
    scale = TIME_SCALE.get(cmap.headers[time_pos].lower(), 1.0) if time_pos is not None else 1.0

    def parse(raw: list[str]) -> dict:
        return {name: _convert(name, raw[pos]) for name, pos in cmap.index.items()}

    def scaled(row: dict, factor: float) -> dict:
        if factor != 1.0 and row.get("time_s") is not None:
            row["time_s"] *= factor
        return row

    def rows() -> Iterator[dict]:
        factor = scale
        buffered: list[dict] = []
        if factor is None:  # unit not in the column name: look at the first rows
            for raw in reader:
                if len(raw) >= width:
                    buffered.append(parse(raw))
                    if len(buffered) >= 500:
                        break
            factor = _infer_time_scale(buffered)
        for row in buffered:
            yield scaled(row, factor)
        for raw in reader:
            if len(raw) >= width:
                yield scaled(parse(raw), factor)

    return cmap, rows()


def read_frames(path: str | Path) -> tuple[ColumnMap, list[dict]]:
    with open(path, newline="", encoding="utf-8-sig", errors="replace") as f:
        cmap, rows = iter_frames(f)
        return cmap, list(rows)
