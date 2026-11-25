"""Command-line entry point. Capture, report and compare commands arrive in the next steps."""

from __future__ import annotations

import argparse
import sys

from frametrace import __version__, columns, process


def cmd_inspect(path: str) -> int:
    """Show how Frametrace reads an existing PresentMon CSV."""
    cmap, rows = columns.read_frames(path)
    print(f"Schema: {cmap.schema.value}")
    for feature, ok in cmap.capabilities().items():
        print(
            f"  {feature:15} {'yes' if ok else 'missing: ' + ', '.join(cmap.missing(columns.REQUIRED_FOR[feature]))}"
        )
    presenters = process.summarize_presenters(rows)
    target, reason = process.pick_target(presenters)
    print(f"Processes: {', '.join(f'{p.name} ({p.frames})' for p in presenters[:5]) or 'none'}")
    print(f"Target: {target.name if target else 'none'} ({reason})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="frametrace")
    ap.add_argument("--version", action="version", version=f"frametrace {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)
    p_inspect = sub.add_parser(
        "inspect", help="read a PresentMon CSV and show what Frametrace sees"
    )
    p_inspect.add_argument("csv")
    args = ap.parse_args(argv)
    if args.command == "inspect":
        return cmd_inspect(args.csv)
    return 1


if __name__ == "__main__":
    sys.exit(main())
