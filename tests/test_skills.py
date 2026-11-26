"""The AI skills in skills/: frontmatter, required sections, shared rules in sync."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
sys.path.insert(0, str(ROOT / "tools"))

import sync_skills

GENERAL = SKILLS / "frametrace" / "SKILL.md"
TEMPLATE = SKILLS / "game-skill-template.md"
GAME_SKILLS = sorted(SKILLS.glob("frametrace-*/SKILL.md"))
ALL_SKILLS = sorted(SKILLS.glob("*/SKILL.md"))

# Sections every game skill has, in this order (the template and the general skill's outline
# use the same list).
GAME_SECTIONS = [
    "## The game",
    "## Visual cost in",
    "## Settings map",
    "## Measured costs",
    "## By goal",
    "## Benchmark scene",
    "## Reading this game's reports",
    "## Not measured yet",
    "## Sources",
]


def frontmatter(path: Path) -> dict:
    """The YAML frontmatter's top-level keys and the `metadata` map (flat, stdlib only)."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    assert m, f"{path}: no frontmatter"
    out: dict = {"metadata": {}}
    for line in m.group(1).splitlines():
        if line.startswith("  "):
            key, _, value = line.strip().partition(":")
            out["metadata"][key] = value.strip()
        elif ":" in line and not line.startswith("metadata:"):
            key, _, value = line.partition(":")
            out[key] = value.strip()
    return out


def headings(path: Path) -> list[str]:
    """`## ` headings outside the shared rules block and outside code fences."""
    text = sync_skills.BLOCK.sub("", path.read_text(encoding="utf-8"))
    text = re.sub(r"^```.*?^```", "", text, flags=re.DOTALL | re.MULTILINE)
    return [line for line in text.splitlines() if line.startswith("## ")]


def listed(value: str) -> list[str]:
    return [v.strip() for v in value.strip("[]").split(",") if v.strip()]


def test_there_is_a_general_skill_and_at_least_one_game_skill():
    assert GENERAL.exists()
    assert GAME_SKILLS


def test_shared_rules_are_in_sync():
    assert sync_skills.check() == [], "run: python tools/sync_skills.py"


@pytest.mark.parametrize("path", ALL_SKILLS, ids=lambda p: p.parent.name)
def test_frontmatter(path):
    fm = frontmatter(path)
    assert fm.get("name") == path.parent.name
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", fm["name"]) and len(fm["name"]) <= 64
    desc = fm.get("description", "")
    assert 0 < len(desc) <= 1024
    assert "<" not in desc and ">" not in desc
    assert "Frametrace report" in desc and "Frametrace compare" in desc


@pytest.mark.parametrize("path", GAME_SKILLS, ids=lambda p: p.parent.name)
def test_game_skill_names_its_game(path):
    fm = frontmatter(path)
    meta, desc = fm["metadata"], fm["description"]
    assert meta.get("game") and meta["game"] in desc
    names = listed(meta.get("process_names", ""))
    assert names, "metadata.process_names is empty"
    for exe in names:
        assert exe in desc, f"{exe} missing from the description"
    assert meta.get("status") in {"tested", "partial"}
    assert re.match(r"\d{4}-\d{2}-\d{2}", meta.get("last_verified", ""))
    assert "general frametrace skill" in desc


@pytest.mark.parametrize("path", GAME_SKILLS + [TEMPLATE], ids=lambda p: p.parent.name)
def test_game_skill_sections(path):
    found = headings(path)
    positions = []
    for section in GAME_SECTIONS:
        hits = [i for i, h in enumerate(found) if h.startswith(section)]
        assert hits, f"{path.name}: missing {section!r}"
        positions.append(hits[0])
    assert positions == sorted(positions), f"{path}: sections out of order"


def test_general_skill_knows_every_game_skill():
    text = GENERAL.read_text(encoding="utf-8")
    for path in GAME_SKILLS:
        assert f"`{path.parent.name}`" in text, f"list {path.parent.name} in {GENERAL}"


def test_general_skill_outline_matches_the_template():
    text = GENERAL.read_text(encoding="utf-8")
    for section in GAME_SECTIONS:
        assert f"`{section}" in text, f"outline in {GENERAL} lacks {section!r}"


def test_sync_replaces_only_the_block():
    block = sync_skills.shared_block(GENERAL.read_text(encoding="utf-8"))
    stale = (
        "before\n<!-- frametrace:shared-rules (old note) -->\nold rules\n"
        "<!-- /frametrace:shared-rules -->\nafter\n"
    )
    assert sync_skills.synced(stale, block) == f"before\n{block}\nafter\n"
    with pytest.raises(ValueError):
        sync_skills.synced("no markers here\n", block)
