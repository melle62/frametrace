"""A compact frame-time trace of one capture, for the scope view.

A 100 s capture at 400 FPS has 40,000 frames; drawing them one by one would be slow and
would turn the screen into a wall of spikes. Instead the capture is cut into a fixed
number of time buckets, and each bucket keeps the 5th, 50th and 95th percentile frame
time, the median GPU busy and the median CPU busy (of the presenting thread). Hitches
are kept separately, so they stay visible however wide the bucket is.

The trace is saved next to result.json as trace.json. Captures made before trace.json
existed are rebuilt from presentmon.csv on demand.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from frametrace import analyze, columns

TRACE_FILE = "trace.json"
TRACE_FORMAT = 1
BUCKETS = 720
MAX_HITCHES = 40


@dataclass
class Trace:
    duration_s: float
    p5: list[float | None]  # frame time (present to present), ms
    p50: list[float | None]
    p95: list[float | None]
    gpu: list[float | None]  # median GPU busy, ms
    cpu: list[float | None]  # median CPU busy of the presenting thread, ms
    hitches: list[tuple[float, float]] = field(default_factory=list)  # (time_s, ms)
    format: int = TRACE_FORMAT

    @property
    def buckets(self) -> int:
        return len(self.p50)

    def peak_ms(self) -> float:
        """Largest P95 bucket: what the vertical scale has to show."""
        return max((v for v in self.p95 if v is not None), default=0.0)


def _pct(values: list[float], q: float) -> float:
    return analyze.quantile(sorted(values), q)


def _median(values: list[float]) -> float | None:
    return _pct(values, 0.5) if values else None


def build(
    rows: list[dict], skip_start_s: float = analyze.SKIP_START_S, buckets: int = BUCKETS
) -> Trace | None:
    """Bucket the frames of one process. None when there is nothing to draw."""
    rows, _ = analyze.trim_start(rows, skip_start_s)
    frames = [
        r
        for i, r in enumerate(rows)
        if i > 0 and r.get("time_s") is not None and (r.get("ms_between_presents") or 0) > 0
    ]
    if len(frames) < 2:
        return None
    t0, t1 = frames[0]["time_s"], frames[-1]["time_s"]
    span = max(t1 - t0, 1e-6)
    n = max(1, min(buckets, len(frames)))
    ft: list[list[float]] = [[] for _ in range(n)]
    gpu: list[list[float]] = [[] for _ in range(n)]
    cpu: list[list[float]] = [[] for _ in range(n)]
    for r in frames:
        i = min(n - 1, int((r["time_s"] - t0) / span * n))
        ft[i].append(r["ms_between_presents"])
        if r.get("ms_gpu_busy") is not None:
            gpu[i].append(r["ms_gpu_busy"])
        if r.get("ms_cpu_busy") is not None:
            cpu[i].append(r["ms_cpu_busy"])
    pairs = [(r["time_s"] - t0, r["ms_between_presents"]) for r in frames]
    spikes = sorted(analyze._spikes(pairs), reverse=True)[:MAX_HITCHES]
    return Trace(
        duration_s=round(span, 3),
        p5=[round(_pct(b, 0.05), 3) if b else None for b in ft],
        p50=[round(_pct(b, 0.5), 3) if b else None for b in ft],
        p95=[round(_pct(b, 0.95), 3) if b else None for b in ft],
        gpu=[round(m, 3) if (m := _median(b)) is not None else None for b in gpu],
        cpu=[round(m, 3) if (m := _median(b)) is not None else None for b in cpu],
        hitches=sorted((round(t, 3), round(ms, 2)) for ms, t in spikes),
    )


def save(trace: Trace, folder: Path) -> None:
    (folder / TRACE_FILE).write_text(json.dumps(asdict(trace), separators=(",", ":")), "utf-8")


def load(folder: Path) -> Trace | None:
    try:
        d = json.loads((folder / TRACE_FILE).read_text("utf-8"))
        if d.get("format") != TRACE_FORMAT:
            return None
        d["hitches"] = [tuple(h) for h in d.get("hitches", [])]
        return Trace(**d)
    except (OSError, ValueError, TypeError):
        return None


def from_csv(folder: Path, result: dict) -> Trace | None:
    """Rebuild the trace of an older capture from its presentmon.csv."""
    csv_path = folder / "presentmon.csv"
    pid = (result.get("capture") or {}).get("pid")
    if not csv_path.is_file() or pid is None:
        return None
    with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
        _, rows = columns.iter_frames(f)
        mine = [r for r in rows if r.get("pid") == pid]
    if not mine:
        return None
    counts: dict = {}
    for r in mine:
        counts[r.get("swapchain")] = counts.get(r.get("swapchain"), 0) + 1
    main = max(counts, key=counts.get)
    skip = (result.get("analysis") or {}).get("skipped_start_s", analyze.SKIP_START_S)
    return build([r for r in mine if r.get("swapchain") == main], skip_start_s=skip)


def get(folder: Path, result: dict) -> Trace | None:
    """trace.json if present, otherwise rebuilt from the CSV (and saved for next time)."""
    trace = load(folder)
    if trace is None:
        trace = from_csv(folder, result)
        if trace is not None:
            try:
                save(trace, folder)
            except OSError:
                pass
    return trace
