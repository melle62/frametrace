"""PresentMon probe: record a short capture in any game and check what Frametrace gets.

Run it from an *administrator* terminal (or as a member of Performance Log Users):

    python tools/probe_presentmon.py --label cs2-dx11
    python tools/probe_presentmon.py --label cyberpunk-dx12 --seconds 30
    python tools/probe_presentmon.py --label doom-vulkan --countdown 15

What it does:
  1. Counts down so you can switch to the game (play normally during the capture).
  2. Notes the foreground window's process at the start and end of the capture.
  3. Records ALL presenting processes with PresentMon for --seconds.
  4. Stops PresentMon the way capture.py will (a second PresentMon call with
     --terminate_existing_session) and checks the CSV was flushed.
  5. Detects the CSV schema, maps the columns, picks the game automatically and
     previews the CPU/GPU bottleneck signal.

Output goes to probe-results/: the raw CSV, a CSV with only the game's frames,
and a Markdown summary. Paste the summary back into the Frametrace chat.
"""

from __future__ import annotations

import argparse
import datetime as dt
import platform
import signal
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from frametrace import columns, presentmon, process

PROBE_SESSION = "FrametraceProbe"
KEY_FIELDS = (
    "ms_between_presents",
    "ms_frame_time",
    "ms_cpu_busy",
    "ms_cpu_wait",
    "ms_gpu_busy",
    "ms_gpu_time",
    "ms_between_display_change",
)


def countdown(seconds: int) -> None:
    print(f"Switch to the game now. Capture starts in {seconds} s.")
    for left in range(seconds, 0, -1):
        print(f"  {left}...", end="\r", flush=True)
        time.sleep(1)
    print("Recording.          ")


def stop_capture(exe: Path, proc: subprocess.Popen, timeout: float = 15.0) -> str:
    """Stop the recording. Returns which method worked."""
    t0 = time.monotonic()
    subprocess.run(
        presentmon.terminate_command(exe, PROBE_SESSION),
        capture_output=True,
        timeout=30,
        check=False,
    )
    try:
        proc.wait(timeout=timeout)
        return f"--terminate_existing_session (exited after {time.monotonic() - t0:.1f} s)"
    except subprocess.TimeoutExpired:
        pass
    proc.send_signal(signal.CTRL_BREAK_EVENT)  # handled by PresentMon's console Ctrl handler
    try:
        proc.wait(timeout=timeout)
        return "CTRL_BREAK_EVENT (terminate_existing_session did not stop it)"
    except subprocess.TimeoutExpired:
        proc.kill()
        return "KILLED (neither clean stop worked; CSV may be incomplete)"


def read_console_log(path: Path) -> str:
    """PresentMon writes UTF-16 to a redirected console, other tools write UTF-8."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    elif b"\x00" in raw[:200]:
        text = raw.decode("utf-16-le", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "n/a"


def fmt(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def bottleneck_preview(rows: list[dict]) -> list[str]:
    """First look at the GPU-busy / frame-time ratio. Thresholds are placeholders for analyze.py."""
    ratios = [
        r["ms_gpu_busy"] / r["ms_frame_time"]
        for r in rows
        if r.get("ms_gpu_busy") is not None and r.get("ms_frame_time")
    ]
    if not ratios:
        return ["- No GPU busy / frame time data: bottleneck detection not possible with this CSV."]
    n = len(ratios)
    lines = [
        f"- Frames with ratio data: {n}",
        (
            f"- GPU busy / frame time: median {statistics.median(ratios):.2f}, "
            f"p10 {quantile(ratios, 0.10):.2f}, p90 {quantile(ratios, 0.90):.2f}"
        ),
        f"- Ratio >= 0.90 (GPU-bound candidate): {pct(sum(r >= 0.90 for r in ratios), n)}",
        f"- Ratio 0.75-0.90 (mixed): {pct(sum(0.75 <= r < 0.90 for r in ratios), n)}",
        f"- Ratio < 0.75 (CPU-bound or capped candidate): {pct(sum(r < 0.75 for r in ratios), n)}",
    ]
    split = [
        abs(r["ms_frame_time"] - (r["ms_cpu_busy"] + r["ms_cpu_wait"]))
        for r in rows
        if None not in (r.get("ms_frame_time"), r.get("ms_cpu_busy"), r.get("ms_cpu_wait"))
    ]
    if split:
        lines.append(
            f"- Check frame_time == cpu_busy + cpu_wait: median deviation "
            f"{statistics.median(split):.4f} ms, max {max(split):.4f} ms"
        )
    waits = [r["ms_cpu_wait"] for r in rows if r.get("ms_cpu_wait") is not None]
    if waits:
        lines.append(
            f"- CPU wait: median {statistics.median(waits):.3f} ms, p90 {quantile(waits, 0.9):.3f} ms"
        )
    return lines


def quantile(values: list[float], q: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * (len(s) - 1))))]


def frame_stats(rows: list[dict]) -> list[str]:
    ft = [r["ms_between_presents"] for r in rows if r.get("ms_between_presents")]
    if not ft:
        return ["- No MsBetweenPresents data."]
    avg_ms = statistics.fmean(ft)
    worst = sorted(ft, reverse=True)
    one_pct = worst[: max(1, len(ft) // 100)]
    return [
        (
            f"- Frames: {len(ft)}, avg FPS {1000 / avg_ms:.1f}, "
            f"1% low (avg of worst 1%) {1000 / statistics.fmean(one_pct):.1f} FPS"
        ),
        (
            f"- Frame time: median {statistics.median(ft):.3f} ms, "
            f"p99 {quantile(ft, 0.99):.3f} ms, max {worst[0]:.3f} ms"
        ),
    ]


def write_target_csv(raw_csv: Path, out_csv: Path, pid: int, cmap: columns.ColumnMap) -> int:
    pid_col = cmap.index["pid"]
    kept = 0
    with (
        open(raw_csv, encoding="utf-8-sig", errors="replace") as src,
        open(out_csv, "w", encoding="utf-8", newline="") as dst,
    ):
        header = src.readline()
        dst.write(header)
        for line in src:
            parts = line.split(",")
            if len(parts) > pid_col and parts[pid_col].strip() == str(pid):
                dst.write(line)
                kept += 1
    return kept


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--label", required=True, help="short name, e.g. cs2-dx11 or cyberpunk-dx12")
    ap.add_argument("--seconds", type=int, default=20, help="capture length (default 20)")
    ap.add_argument(
        "--countdown", type=int, default=10, help="seconds to switch to the game (default 10)"
    )
    ap.add_argument("--presentmon", help="path to the PresentMon console exe")
    ap.add_argument(
        "--extra",
        nargs=argparse.REMAINDER,
        default=[],
        help="extra PresentMon options, e.g. --extra --track_frame_type",
    )
    args = ap.parse_args()

    if sys.platform != "win32":
        print("PresentMon only runs on Windows.")
        return 2

    try:
        exe = presentmon.find_presentmon(args.presentmon)
    except presentmon.PresentMonNotFound as e:
        print(e)
        return 2
    ok, why = presentmon.can_trace()
    pm_version = presentmon.identify(exe)
    print(f"PresentMon: {exe} (version {pm_version})")
    print(f"Privileges: {why}")
    if not ok:
        return 2

    out_dir = ROOT / "probe-results"
    out_dir.mkdir(exist_ok=True)
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    base = out_dir / f"{args.label}-{stamp}"
    raw_csv, log_path = base.with_suffix(".csv"), base.with_suffix(".log")

    countdown(args.countdown)
    fg_start = process.get_foreground_process()

    cmd = presentmon.capture_command(
        exe, raw_csv, session_name=PROBE_SESSION, extra=tuple(args.extra)
    )
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.Popen(
            cmd,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        time.sleep(args.seconds)
        fg_end = process.get_foreground_process()
        stop_method = stop_capture(exe, proc)
    print("Capture stopped. Analyzing...")

    log_tail = read_console_log(log_path).strip().splitlines()[-15:]
    if not raw_csv.is_file():
        print("No CSV was written. PresentMon output:\n" + "\n".join(log_tail))
        return 1

    cmap, rows = columns.read_frames(raw_csv)
    presenters = process.summarize_presenters(rows)
    target, reason = process.pick_target(presenters, fg_start.pid if fg_start else None)
    target_rows = [r for r in rows if target and r.get("pid") == target.pid]
    if target and target.main_swapchain:
        main_rows = [r for r in target_rows if r.get("swapchain") == target.main_swapchain]
    else:
        main_rows = target_rows

    def fg_line(fg: process.ForegroundProcess | None) -> str:
        if fg is None:
            return "none"
        return f'PID {fg.pid}, {fg.name or "<access denied>"}, window "{fg.window_title}"'

    md: list[str] = [
        f"# PresentMon probe: {args.label}",
        "",
        f"- Date: {dt.datetime.now().astimezone():%Y-%m-%d %H:%M}",
        f"- Windows: {platform.version()} ({platform.release()})",
        f"- PresentMon: {exe.name}, version {pm_version}",
        f"- Privileges: {why}",
        f"- Command: `{' '.join(cmd[1:])}`",
        f"- Stop method: {stop_method}",
        f"- Foreground at start: {fg_line(fg_start)}",
        f"- Foreground at end: {fg_line(fg_end)}",
        "",
        "## CSV format",
        f"- Detected schema: **{cmap.schema.value}**",
        "- Capabilities: "
        + ", ".join(f"{k}={'yes' if v else 'NO'}" for k, v in cmap.capabilities().items()),
        f"- Header ({len(cmap.headers)} columns): `{','.join(cmap.headers)}`",
        f"- Not mapped by Frametrace: {', '.join(cmap.unmapped_headers()) or 'none'}",
        "",
        "## Presenting processes",
        "| PID | Process | Frames | Avg FPS | Runtime | Present mode | Swapchains |",
        "|---|---|---|---|---|---|---|",
    ]
    for p in presenters[:10]:
        md.append(
            f"| {p.pid} | {p.name} | {p.frames} | {fmt(p.avg_fps, 1)} | "
            f"{', '.join(k for k, _ in p.runtimes.most_common(2))} | "
            f"{', '.join(k for k, _ in p.present_modes.most_common(2))} | {len(p.swapchains)} |"
        )
    md += ["", "## Auto-detected game"]
    if target is None:
        md.append(
            f"- **None**: {reason}. If the game was running, anti-cheat may block ETW tracing."
        )
    else:
        fg_match = bool(fg_start and fg_start.pid == target.pid)
        md += [
            f"- **{target.name}** (PID {target.pid}): {reason}",
            f"- Same process as the foreground window: {'yes' if fg_match else 'NO'}",
            f"- Main swapchain {target.main_swapchain}: {len(main_rows)} of {target.frames} frames",
            "",
            "### Missing values in the game's frames (NA or empty)",
        ]
        for f in KEY_FIELDS:
            if f in cmap.index:
                missing = sum(r.get(f) is None for r in main_rows)
                md.append(f"- {f} ({cmap.headers[cmap.index[f]]}): {pct(missing, len(main_rows))}")
            else:
                md.append(f"- {f}: column not present")
        md += ["", "### Frame time (MsBetweenPresents)", *frame_stats(main_rows)]
        md += ["", "### Bottleneck signal preview", *bottleneck_preview(main_rows)]
        target_csv = base.with_name(base.name + "-target.csv")
        kept = write_target_csv(raw_csv, target_csv, target.pid, cmap)
        md += ["", f"Game-only CSV: `{target_csv.name}` ({kept} rows)"]

    md += ["", "## PresentMon console output (last lines)", "```", *log_tail, "```", ""]
    md += [
        "## Your notes",
        "- API / settings / anything odd (kicked by anti-cheat? overlay on?):",
        "",
    ]

    summary = base.with_suffix(".md")
    summary.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    print(f"\nSaved: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
