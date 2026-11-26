"""Frame statistics and CPU/GPU bottleneck classification.

Works only with canonical column names from columns.py, so it doesn't care which
PresentMon version wrote the CSV. All thresholds are module constants: they are first
estimates and get calibrated with real captures (see docs/presentmon.md, section 6).
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, field

# Per-frame bottleneck classes
GPU_BOUND_RATIO = 0.90  # GPU busy >= 90% of the frame time -> GPU-limited
WAIT_RATIO = 0.25  # CPU waited >= 25% of the frame time (blocked in Present) -> waiting
# Capture-level FPS cap detection, while the GPU has headroom (median GPU ratio below 0.85):
# - pinned: per-second FPS is steady (90% of whole seconds within 3% of the median second) and
#   never rises above it (max second <= median + 1%). In-game limiters such as CS2's fps_max
#   hold the rate per second exactly but pace individual frames unevenly (CS2 repeats
#   7.2/3.0/4.8 ms at fps_max 200), so frame-level uniformity alone misses them.
# - uniform: P95 / P5 frame time below 1.10 (driver limiters, VSync).
CAP_SPREAD = 1.10
CAP_MAX_GPU_RATIO = 0.85
CAP_STEADY_PCT = 90.0
CAP_STEADY_BAND = 0.03
CAP_TOP_MARGIN = 0.01
CAP_MIN_SECONDS = 10
# A spike (hitch) is a frame at least twice as long as the median of its neighbours and at
# least 4 ms longer. Comparing with neighbours instead of the whole capture keeps heavy scenes
# from counting as stutter: on the first CS2 capture the global rule flagged 2.1% of the time,
# the local one 0.1%.
SPIKE_FACTOR = 2.0
SPIKE_MIN_EXTRA_MS = 4.0
SPIKE_NEIGHBOURS = 30  # on each side
# High FPS where HAGS' GPU-busy overstatement matters (see docs)
HIGH_FPS = 300
# Leave out the start of a capture (trace start-up and the hotkey press can cause a hitch)
SKIP_START_S = 1.0
MIN_FOR_SKIP_S = 5.0


def quantile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated quantile of an already sorted list (same as numpy's default)."""
    if not sorted_values:
        return math.nan
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


@dataclass
class FrameStats:
    frames: int
    duration_s: float
    avg_fps: float
    p1_fps: float  # 1% low: FPS at the 99th percentile frame time
    p01_fps: float  # 0.1% low: FPS at the 99.9th percentile frame time
    low1_avg_fps: float  # average FPS of the slowest 1% of frames
    worst_1s_fps: float | None  # lowest average FPS in any whole second
    median_ms: float
    p5_ms: float
    p95_ms: float
    p99_ms: float
    p999_ms: float
    max_ms: float
    stdev_ms: float
    spikes: int
    spike_time_pct: float  # share of the capture spent in spike frames
    worst_spikes: list[tuple[float, float]] = field(default_factory=list)  # (ms, at second)
    # Same lows measured from the CPU side (MsBetweenAppStart). In-game counters such as
    # CS2's VProf measure this: on the first CS2 capture it gave P1 209.4 vs VProf's 211.0,
    # while present-to-present gave 183.7.
    cpu_p1_fps: float | None = None
    cpu_p99_ms: float | None = None
    # FPS per whole second (for cap detection); None with fewer than CAP_MIN_SECONDS seconds
    second_fps_median: float | None = None
    second_fps_max: float | None = None
    second_fps_steady_pct: float | None = None


@dataclass
class Bottleneck:
    available: bool
    frames: int = 0
    gpu_pct: float = 0.0
    cpu_pct: float = 0.0
    wait_pct: float = 0.0
    verdict: str = "unknown"
    median_gpu_busy_ms: float | None = None
    median_cpu_busy_ms: float | None = None
    median_cpu_wait_ms: float | None = None
    gpu_fps_ceiling: float | None = None
    cpu_fps_ceiling: float | None = None
    cap_fps: float | None = None  # set when the frame rate looks capped
    notes: list[str] = field(default_factory=list)


@dataclass
class Display:
    present_mode: str | None
    present_mode_pct: float
    tearing_allowed: bool | None
    sync_interval: int | None
    vsync: bool | None
    dropped_pct: float | None
    displayed_fps: float | None
    runtime: str | None
    input_to_photon_ms: float | None
    pc_latency_ms: float | None = None  # median, from NVIDIA PC Latency markers
    pc_latency_p95_ms: float | None = None


@dataclass
class Analysis:
    app: str
    pid: int
    stats: FrameStats
    bottleneck: Bottleneck
    display: Display
    skipped_start_s: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def _frame_times(rows: list[dict]) -> list[tuple[float, float]]:
    """(time_s, frame_ms) pairs, skipping the first frame and invalid values."""
    out = []
    for i, r in enumerate(rows):
        ft = r.get("ms_between_presents")
        if i == 0 or ft is None or ft <= 0:
            continue
        out.append((r.get("time_s") or 0.0, ft))
    return out


def frame_stats(rows: list[dict]) -> FrameStats:
    pairs = _frame_times(rows)
    if not pairs:
        raise ValueError("no frame times in this capture")
    times = [t for t, _ in pairs]
    ft = [f for _, f in pairs]
    s = sorted(ft)
    n = len(ft)
    mean = statistics.fmean(ft)
    median = quantile(s, 0.5)
    slowest = s[-max(1, n // 100) :]

    spike_frames = _spikes(pairs)
    worst = sorted(spike_frames or [(f, t) for t, f in pairs], reverse=True)[:3]
    cpu_ft = sorted(
        r["ms_frame_time"] for r in rows[1:] if r.get("ms_frame_time") and r["ms_frame_time"] > 0
    )

    # Lowest average FPS over whole seconds (the partial first and last second are skipped)
    worst_1s = None
    seconds: list[float] = []
    if times[-1] - times[0] >= 3:
        buckets: dict[int, list[float]] = {}
        for t, f in pairs:
            buckets.setdefault(int(t - times[0]), []).append(f)
        seconds = [
            1000 * len(b) / sum(b) for k, b in sorted(buckets.items()) if 0 < k < max(buckets)
        ]
        if seconds:
            worst_1s = min(seconds)
    sec_median = sec_max = steady = None
    if len(seconds) >= CAP_MIN_SECONDS:
        sec_median, sec_max = statistics.median(seconds), max(seconds)
        steady = (
            100
            * sum(abs(x - sec_median) <= CAP_STEADY_BAND * sec_median for x in seconds)
            / len(seconds)
        )

    return FrameStats(
        frames=n,
        duration_s=sum(ft) / 1000,
        avg_fps=1000 / mean,
        p1_fps=1000 / quantile(s, 0.99),
        p01_fps=1000 / quantile(s, 0.999),
        low1_avg_fps=1000 / statistics.fmean(slowest),
        worst_1s_fps=worst_1s,
        median_ms=median,
        p5_ms=quantile(s, 0.05),
        p95_ms=quantile(s, 0.95),
        p99_ms=quantile(s, 0.99),
        p999_ms=quantile(s, 0.999),
        max_ms=s[-1],
        stdev_ms=statistics.pstdev(ft),
        spikes=len(spike_frames),
        spike_time_pct=100 * sum(f for f, _ in spike_frames) / sum(ft),
        worst_spikes=[(round(f, 2), round(t - times[0], 1)) for f, t in worst],
        cpu_p1_fps=1000 / quantile(cpu_ft, 0.99) if len(cpu_ft) >= 100 else None,
        cpu_p99_ms=quantile(cpu_ft, 0.99) if len(cpu_ft) >= 100 else None,
        second_fps_median=sec_median,
        second_fps_max=sec_max,
        second_fps_steady_pct=steady,
    )


def _spikes(pairs: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """(frame_ms, time_s) of frames that are much longer than their neighbours."""
    ft = [f for _, f in pairs]
    out = []
    for i, (t, f) in enumerate(pairs):
        if f <= SPIKE_MIN_EXTRA_MS:  # can't be 4 ms longer than anything: skip the median
            continue
        lo, hi = max(0, i - SPIKE_NEIGHBOURS), min(len(ft), i + SPIKE_NEIGHBOURS + 1)
        local = statistics.median(ft[lo:i] + ft[i + 1 : hi]) if hi - lo > 1 else f
        if f > max(local * SPIKE_FACTOR, local + SPIKE_MIN_EXTRA_MS):
            out.append((f, t))
    return out


def bottleneck(
    rows: list[dict], stats: FrameStats | None = None, display: Display | None = None
) -> Bottleneck:
    gpu, cpu, wait, total = 0, 0, 0, 0
    gpu_busy, cpu_busy, cpu_wait, ratios = [], [], [], []
    for r in rows:
        frame = r.get("ms_frame_time") or r.get("ms_between_presents")
        g = r.get("ms_gpu_busy")
        if not frame or frame <= 0 or g is None:
            continue
        total += 1
        ratio = g / frame
        ratios.append(ratio)
        gpu_busy.append(g)
        w = r.get("ms_cpu_wait")
        if r.get("ms_cpu_busy") is not None:
            cpu_busy.append(r["ms_cpu_busy"])
        if w is not None:
            cpu_wait.append(w)
        if ratio >= GPU_BOUND_RATIO:
            gpu += 1
        elif w is not None and w / frame >= WAIT_RATIO:
            wait += 1
        else:
            cpu += 1

    usable = sum(1 for r in rows if r.get("ms_between_presents"))
    if total == 0 or total < 0.5 * max(usable, 1):
        return Bottleneck(
            available=False,
            notes=["GPU busy data missing for most frames, so the CPU/GPU split isn't available."],
        )

    b = Bottleneck(
        available=True,
        frames=total,
        median_gpu_busy_ms=_median(gpu_busy),
        median_cpu_busy_ms=_median(cpu_busy),
        median_cpu_wait_ms=_median(cpu_wait),
    )
    if b.median_gpu_busy_ms:
        b.gpu_fps_ceiling = 1000 / b.median_gpu_busy_ms
    # PresentMon's CPU busy covers only the thread that calls Present (often a render thread),
    # not the game logic on other threads, so it can't give a CPU FPS ceiling.
    b.cpu_fps_ceiling = None

    median_ratio = statistics.median(ratios)
    pinned = (
        stats is not None
        and stats.second_fps_steady_pct is not None
        and stats.second_fps_steady_pct >= CAP_STEADY_PCT
        and stats.second_fps_max <= stats.second_fps_median * (1 + CAP_TOP_MARGIN)
    )
    uniform = stats is not None and stats.p95_ms / stats.p5_ms < CAP_SPREAD
    if (pinned or uniform) and median_ratio < CAP_MAX_GPU_RATIO:
        b.cap_fps = stats.second_fps_median if pinned else 1000 / stats.median_ms
        how = "every second within 3% and none above it" if pinned else "very uniform frame times"
        b.notes.append(
            f"The frame rate is pinned at ~{b.cap_fps:.0f} FPS ({how}) while the GPU is busy only "
            f"~{100 * median_ratio:.0f}% of each frame: an FPS cap or VSync sets the pace, not the CPU "
            "or GPU. An in-game cap sleeps inside the game's frame, which PresentMon counts as CPU "
            "busy, so frames that look CPU-limited here are waiting for the cap."
        )
        b.notes.append(
            "Under a cap the GPU clocks down, so its busy time per frame rises and the GPU FPS "
            "estimate is conservative."
        )

    # Blocked in Present with VSync off and no cap: the only thing to wait for is the GPU
    # (the flip queue is full). Calibrated on CS2, where VProf showed the game's main thread
    # waiting too (LowLatencySleep and Frame Boundary).
    vsync = display.vsync if display else None
    if wait and not vsync and b.cap_fps is None:
        b.notes.append(
            f"{100 * wait / total:.0f}% of frames had the CPU blocked in Present with VSync off and no "
            "cap. That means the GPU queue was full, so they count as GPU-limited."
        )
        gpu, wait = gpu + wait, 0

    if b.cap_fps is not None:  # with a cap, frames the GPU didn't limit were waiting for it
        cpu, wait = 0, cpu + wait
    b.gpu_pct, b.cpu_pct, b.wait_pct = (100 * x / total for x in (gpu, cpu, wait))
    shares = {
        "GPU-limited": b.gpu_pct,
        "CPU-limited": b.cpu_pct,
        "waiting (VSync/cap)": b.wait_pct,
    }
    top, top_pct = max(shares.items(), key=lambda kv: kv[1])
    if b.cap_fps:
        b.verdict = f"capped at ~{b.cap_fps:.0f} FPS"
    elif top_pct >= 70:
        b.verdict = f"mostly {top} ({top_pct:.0f}%)"
    else:
        b.verdict = f"mixed, leaning {top} ({top_pct:.0f}%)"

    if stats and stats.avg_fps >= HIGH_FPS:
        b.notes.append(
            "At very high FPS, Hardware-Accelerated GPU Scheduling (HAGS) can overstate GPU busy "
            "by up to ~0.5 ms per frame, which inflates the GPU-limited share."
        )
    return b


def display_info(rows: list[dict]) -> Display:
    modes = Counter(r.get("present_mode") for r in rows if r.get("present_mode"))
    mode, mode_n = modes.most_common(1)[0] if modes else (None, 0)
    tearing = [r["allows_tearing"] for r in rows if r.get("allows_tearing") is not None]
    sync = [r["sync_interval"] for r in rows if r.get("sync_interval") is not None]
    sync_mode = Counter(sync).most_common(1)[0][0] if sync else None

    # Frames never shown on screen: V1 has a Dropped column, V2/V3 leave display columns NA
    dropped_pct = displayed_fps = None
    first = rows[0] if rows else {}
    if "dropped" in first:
        dropped_pct = 100 * sum(1 for r in rows if r.get("dropped")) / len(rows)
    else:
        col = next(
            (c for c in ("ms_between_display_change", "ms_displayed_time") if c in first), None
        )
        if col:
            dropped_pct = 100 * sum(1 for r in rows if r.get(col) is None) / len(rows)
    shown = [r["ms_between_display_change"] for r in rows if r.get("ms_between_display_change")]
    if shown:
        displayed_fps = 1000 / statistics.fmean(shown)

    latency = [
        r.get("ms_all_input_to_photon") or r.get("ms_click_to_photon")
        for r in rows
        if (r.get("ms_all_input_to_photon") or r.get("ms_click_to_photon"))
    ]
    pcl = [r["ms_pc_latency"] for r in rows if r.get("ms_pc_latency")]
    runtimes = Counter(r.get("runtime") for r in rows if r.get("runtime"))
    return Display(
        present_mode=mode,
        present_mode_pct=100 * mode_n / len(rows) if rows else 0.0,
        tearing_allowed=(sum(tearing) > len(tearing) / 2) if tearing else None,
        sync_interval=sync_mode,
        vsync=(sync_mode >= 1) if sync_mode is not None else None,
        dropped_pct=dropped_pct,
        displayed_fps=displayed_fps,
        runtime=runtimes.most_common(1)[0][0] if runtimes else None,
        input_to_photon_ms=statistics.median(latency) if len(latency) >= 10 else None,
        pc_latency_ms=statistics.median(pcl) if len(pcl) >= 10 else None,
        pc_latency_p95_ms=quantile(sorted(pcl), 0.95) if len(pcl) >= 10 else None,
    )


def analyze(rows: list[dict], app: str, pid: int, skip_start_s: float = SKIP_START_S) -> Analysis:
    """Analyze the frames of one process (ideally its main swapchain).

    The first skip_start_s seconds are left out: starting the trace and pressing the
    hotkey can cause a hitch that isn't the game's fault.
    """
    skipped = 0.0
    times = [r["time_s"] for r in rows if r.get("time_s") is not None]
    if skip_start_s and times and times[-1] - times[0] >= MIN_FOR_SKIP_S:
        cutoff = times[0] + skip_start_s
        rows = [r for r in rows if r.get("time_s") is None or r["time_s"] >= cutoff]
        skipped = skip_start_s
    stats = frame_stats(rows)
    display = display_info(rows)
    return Analysis(
        app=app,
        pid=pid,
        stats=stats,
        bottleneck=bottleneck(rows, stats, display),
        display=display,
        skipped_start_s=skipped,
    )
