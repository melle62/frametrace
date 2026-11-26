"""Command line entry point.

python -m frametrace                     open the Frametrace window
python -m frametrace inspect CAPTURE.csv show how Frametrace reads a PresentMon CSV
python -m frametrace report CAPTURE.csv  analyze a PresentMon CSV and print the report
python -m frametrace compare A B         compare two captures (result.json or folders)
python -m frametrace share-preview DIR   show exactly what sharing would send for a capture

Both take --goal (avg_fps, lows, latency, stutter, target) and --target FPS.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from frametrace import __version__, analyze, columns, goals, process, report, sysinfo


def cmd_inspect(path: str) -> int:
    """Show how Frametrace reads an existing PresentMon CSV."""
    cmap, rows = columns.read_frames(path)
    print(f"Schema: {cmap.schema.value}")
    for feature, ok in cmap.capabilities().items():
        missing = ", ".join(cmap.missing(columns.REQUIRED_FOR[feature]))
        print(f"  {feature:15} {'yes' if ok else 'missing: ' + missing}")
    presenters = process.summarize_presenters(rows)
    target, reason = process.pick_target(presenters)
    print(f"Processes: {', '.join(f'{p.name} ({p.frames})' for p in presenters[:5]) or 'none'}")
    print(f"Target: {target.name if target else 'none'} ({reason})")
    return 0


def cmd_report(
    path: str,
    process_name: str | None,
    with_system: bool,
    goal: str | None = None,
    target: int | None = None,
) -> int:
    """Analyze an existing PresentMon CSV (for example from an older capture)."""
    cmap, rows = columns.read_frames(path)
    presenters = process.summarize_presenters(rows)
    target, reason = process.pick_target(presenters, process_name=process_name)
    if target is None:
        print(f"No target process: {reason}")
        return 1
    main = [
        r
        for r in rows
        if r.get("pid") == target.pid and r.get("swapchain") == target.main_swapchain
    ]
    result = report.build_result(
        analyze.analyze(main, target.name, target.pid),
        sysinfo.collect() if with_system else sysinfo.SystemInfo(),
        {"reason": reason, "csv_schema": cmap.schema.value, "source": str(path)},
    )
    print(report.render(result, goal, target))
    return 0


def _load_result(path: str) -> dict:
    p = Path(path)
    if p.is_dir():
        p = p / "result.json"
    return json.loads(p.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="frametrace", description="Game benchmarking with answers.")
    ap.add_argument("--version", action="version", version=f"frametrace {__version__}")
    sub = ap.add_subparsers(dest="command")
    p_inspect = sub.add_parser("inspect", help="show how Frametrace reads a PresentMon CSV")
    p_inspect.add_argument("csv")
    p_report = sub.add_parser("report", help="analyze a PresentMon CSV and print the report")
    p_report.add_argument("csv")
    p_report.add_argument("--process-name", help="analyze this process instead of auto-detecting")
    p_report.add_argument("--no-system", action="store_true", help="skip system info")
    goal_help = "goal to write the report for: " + ", ".join(goals.GOALS)
    p_report.add_argument("--goal", choices=list(goals.GOALS), help=goal_help)
    p_report.add_argument("--target", type=int, help="target FPS for --goal target")
    p_compare = sub.add_parser(
        "compare", help="compare two captures (result.json files or folders)"
    )
    p_compare.add_argument("before")
    p_compare.add_argument("after")
    p_compare.add_argument("--goal", choices=list(goals.GOALS), help=goal_help)
    p_compare.add_argument("--target", type=int, help="target FPS for --goal target")
    p_preview = sub.add_parser(
        "share-preview", help="show exactly what sharing would send for a capture folder"
    )
    p_preview.add_argument("folder")
    sub.add_parser("gui", help="open the Frametrace window (the default)")
    args = ap.parse_args(argv)
    # The prompts carry a few non-ASCII marks (→ ■ □). A redirected stdout on an older Python
    # may use a legacy code page; don't fail on them there.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    if args.command == "inspect":
        return cmd_inspect(args.csv)
    if args.command == "report":
        return cmd_report(args.csv, args.process_name, not args.no_system, args.goal, args.target)
    if args.command == "compare":
        a, b = _load_result(args.before), _load_result(args.after)
        print(report.compare(a, b, args.goal, args.target))
        return 0
    if args.command == "share-preview":
        from frametrace import share

        print(share.preview(Path(args.folder)))
        return 0
    from frametrace import gui

    return gui.main()


if __name__ == "__main__":
    sys.exit(main())
