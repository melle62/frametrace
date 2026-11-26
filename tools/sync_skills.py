"""Keep the shared rules identical in every Frametrace skill.

The block between the `frametrace:shared-rules` markers in skills/frametrace/SKILL.md is the
source. Every game skill (skills/frametrace-*/SKILL.md) and skills/game-skill-template.md carry
a copy, so each skill works on its own (installed alone, or pasted into any AI).

    python tools/sync_skills.py          # copy the block into every game skill and the template
    python tools/sync_skills.py --check  # list copies that differ, exit 1 if any (tests run it)

Edit the rules in skills/frametrace/SKILL.md only, then run this.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"
SOURCE = SKILLS / "frametrace" / "SKILL.md"
TEMPLATE = SKILLS / "game-skill-template.md"

# The opening marker line (with its note) through the closing marker, inclusive.
BLOCK = re.compile(
    r"^<!-- frametrace:shared-rules\b[^\n]*-->\n.*?^<!-- /frametrace:shared-rules -->$",
    re.DOTALL | re.MULTILINE,
)


def shared_block(text: str) -> str:
    m = BLOCK.search(text)
    if not m:
        raise ValueError("no frametrace:shared-rules block")
    return m.group(0)


def targets() -> list[Path]:
    return sorted(SKILLS.glob("frametrace-*/SKILL.md")) + [TEMPLATE]


def synced(text: str, block: str) -> str:
    if not BLOCK.search(text):
        raise ValueError("no frametrace:shared-rules markers")
    return BLOCK.sub(lambda _: block, text, count=1)


def check() -> list[Path]:
    """Skills whose copy of the shared block differs from the source."""
    block = shared_block(SOURCE.read_text(encoding="utf-8"))
    return [
        p
        for p in targets()
        if not BLOCK.search(t := p.read_text(encoding="utf-8")) or shared_block(t) != block
    ]


def sync() -> list[Path]:
    """Copy the source block into every target; returns the files that changed."""
    block = shared_block(SOURCE.read_text(encoding="utf-8"))
    changed = []
    for p in targets():
        text = p.read_text(encoding="utf-8")
        new = synced(text, block)
        if new != text:
            p.write_text(new, encoding="utf-8", newline="\n")
            changed.append(p)
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="only report copies that differ")
    args = ap.parse_args()
    root = SKILLS.parent
    try:
        paths = check() if args.check else sync()
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    verb = "out of sync" if args.check else "updated"
    for p in paths:
        print(f"{verb}: {p.relative_to(root)}")
    if not paths:
        print("all skills in sync")
    return 1 if args.check and paths else 0


if __name__ == "__main__":
    sys.exit(main())
