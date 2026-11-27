"""How much a shared capture, comparison and contributor can be trusted. Pure functions.

Everything shared is kept in the dataset; these scores decide what tools/aggregate.py lets
into the game skills' community tables. The rules are deliberately simple and written out,
so a contributor can see why a run did or didn't count (docs/data.md, "Quality").

A capture's score is the weighted share of its checks that pass (0-100). A comparison is
*usable for costs* when it isolates one settings change on one system in one scene; it's a
*baseline pair* when nothing changed, and an *agreeing* baseline pair when the results
stayed inside run-to-run noise too. A contributor is *trusted* once they've shown they can
benchmark repeatably (an agreeing baseline pair) or have three clean one-change comparisons,
and their captures average at least 60.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from frametrace import summary

MIN_SECONDS = 30
CLEAN_HITCH_PCT = 1.0  # time in hitches at or under this is a clean run
SCENE_CORRELATION = 0.8  # per-second FPS curves of the same scene correlate at least this well
MIN_OVERLAP_S = 10
LENGTH_TOLERANCE = 0.10
TRUSTED_CAPTURE_SCORE = 60
TRUSTED_ONE_CHANGE = 3

CAPTURE_CHECKS = (
    # name, weight
    ("game identified", 2),
    ("settings read", 3),
    ("long enough", 2),
    ("clean run", 2),
    ("complete capture", 1),
    ("labelled", 1),
    ("system read", 1),
)


@dataclass
class Check:
    name: str
    passed: bool
    weight: int = 1
    detail: str = ""


def _stats(r: dict) -> dict:
    return (r.get("analysis") or {}).get("stats") or {}


def capture_checks(r: dict) -> list[Check]:
    s, game, cap = _stats(r), r.get("game") or {}, r.get("capture") or {}
    settings = (r.get("game_settings") or {}).get("settings") or []
    system, user = r.get("system") or {}, r.get("user") or {}
    weight = dict(CAPTURE_CHECKS)
    dur = s.get("duration_s") or 0
    hitch = s.get("spike_time_pct")
    return [
        Check(
            "game identified",
            bool(game.get("store_id") or game.get("name_source") in ("steam", "version info")),
            weight["game identified"],
        ),
        Check("settings read", bool(settings), weight["settings read"], f"{len(settings)} keys"),
        Check("long enough", dur >= MIN_SECONDS, weight["long enough"], f"{dur:.0f} s"),
        Check(
            "clean run",
            hitch is not None and hitch <= CLEAN_HITCH_PCT,
            weight["clean run"],
            "n/a" if hitch is None else f"{hitch:.2f}% in hitches",
        ),
        Check(
            "complete capture",
            "killed" not in str(cap.get("stop_method") or "") and (s.get("frames") or 0) >= 1000,
            weight["complete capture"],
        ),
        Check(
            "labelled",
            bool(user.get("label") or user.get("group") or user.get("benchmark")),
            weight["labelled"],
        ),
        Check("system read", bool(system.get("cpu") and system.get("gpus")), weight["system read"]),
    ]


def capture_score(r: dict) -> int:
    checks = capture_checks(r)
    total = sum(c.weight for c in checks)
    return round(100 * sum(c.weight for c in checks if c.passed) / total) if total else 0


def is_clean(r: dict) -> bool:
    hitch = _stats(r).get("spike_time_pct")
    return hitch is not None and hitch <= CLEAN_HITCH_PCT


_DISCRETE = re.compile(r"\b(RTX|GTX|Radeon RX|RX \d|Arc [AB]\d)", re.IGNORECASE)


def main_gpu(r: dict) -> dict:
    gpus = (r.get("system") or {}).get("gpus") or []
    discrete = [g for g in gpus if _DISCRETE.search(g.get("name") or "")]
    return (discrete or gpus or [{}])[0]


def main_display(r: dict) -> dict:
    displays = (r.get("system") or {}).get("displays") or []
    primary = [d for d in displays if d.get("primary")]
    return (primary or displays or [{}])[0]


def system_key(r: dict) -> tuple:
    """What has to match for two runs to be on the same system."""
    s, gpu = r.get("system") or {}, main_gpu(r)
    return (s.get("cpu"), gpu.get("name"), gpu.get("driver"), s.get("ram_running_mts"))


def correlation(xs: list[float], ys: list[float]) -> float | None:
    """Pearson correlation of the overlapping start of two per-second FPS series."""
    n = min(len(xs), len(ys))
    if n < MIN_OVERLAP_S:
        return None
    x, y = xs[:n], ys[:n]
    try:
        return statistics.correlation(x, y)
    except statistics.StatisticsError:  # a flat series (a frame cap) has no correlation
        return None


@dataclass
class Pair:
    """One comparison, judged from the two captures themselves (never from the client's claims)."""

    checks: list[Check] = field(default_factory=list)
    changes: list[tuple[str, str, str]] | None = None
    scene_r: float | None = None
    deltas: dict = field(default_factory=dict)

    def passed(self, name: str) -> bool:
        return any(c.name == name and c.passed for c in self.checks)

    @property
    def comparable(self) -> bool:
        return all(
            self.passed(n)
            for n in (
                "same game",
                "same benchmark",
                "same system",
                "same display",
                "same length",
                "settings read",
            )
        ) and self.passed("same scene")

    @property
    def usable_for_costs(self) -> bool:
        """Isolates one settings change: same game, system, scene; both runs clean."""
        return self.comparable and self.passed("both clean") and len(self.changes or []) == 1

    @property
    def baseline(self) -> bool:
        return self.comparable and self.changes == []

    @property
    def agreeing_baseline(self) -> bool:
        if not self.baseline:
            return False
        keys = ("Average", "1% low")
        return all(self.deltas[k].status == "same" for k in keys if k in self.deltas)


def judge_pair(a: dict, b: dict) -> Pair:
    ga, gb = a.get("game") or {}, b.get("game") or {}
    ca, cb = a.get("capture") or {}, b.get("capture") or {}
    sa, sb = _stats(a), _stats(b)
    da, db = (
        (a.get("analysis") or {}).get("display") or {},
        (b.get("analysis") or {}).get("display") or {},
    )
    changes = summary.settings_changes(a, b)
    same_game = str(ca.get("app") or "").lower() == str(cb.get("app") or "").lower() and (
        not ga.get("build") or not gb.get("build") or ga.get("build") == gb.get("build")
    )
    dur_a, dur_b = sa.get("duration_s") or 0, sb.get("duration_s") or 0
    same_len = bool(dur_a and dur_b) and abs(dur_a - dur_b) <= LENGTH_TOLERANCE * max(dur_a, dur_b)
    disp_a, disp_b = main_display(a), main_display(b)
    same_display = (
        disp_a.get("width"),
        disp_a.get("height"),
        disp_a.get("refresh_hz"),
        da.get("present_mode"),
    ) == (
        disp_b.get("width"),
        disp_b.get("height"),
        disp_b.get("refresh_hz"),
        db.get("present_mode"),
    )
    r = correlation(sa.get("second_fps") or [], sb.get("second_fps") or [])
    pair = Pair(changes=changes, scene_r=r)
    pair.checks = [
        Check("same game", same_game),
        # the user's tag for the scene: runs of another benchmark are another scene, even when
        # their per-second curves happen to correlate (both untagged counts as the same)
        Check("same benchmark", summary.same_benchmark(a, b)),
        Check("same system", system_key(a) == system_key(b)),
        Check("same display", same_display),
        Check("same length", same_len, detail=f"{dur_a:.0f} s / {dur_b:.0f} s"),
        Check("settings read", changes is not None),
        Check(
            "same scene",
            r is not None and r >= SCENE_CORRELATION,
            detail="n/a" if r is None else f"r = {r:.2f}",
        ),
        Check("both clean", is_clean(a) and is_clean(b)),
        Check("one change", changes is not None and len(changes) == 1),
    ]
    pair.deltas = summary.goal_deltas(a, b)
    return pair


@dataclass
class Contributor:
    key: str
    captures: int = 0
    mean_capture_score: float = 0.0
    comparisons: int = 0
    one_change: int = 0
    baselines: int = 0
    agreeing_baselines: int = 0

    @property
    def level(self) -> str:
        if self.captures == 0:
            return "new"
        repeatable = self.agreeing_baselines >= 1 or self.one_change >= TRUSTED_ONE_CHANGE
        if repeatable and self.mean_capture_score >= TRUSTED_CAPTURE_SCORE:
            return "trusted"
        return "contributing"


def judge_contributor(key: str, captures: list[dict], pairs: list[Pair]) -> Contributor:
    scores = [capture_score(r) for r in captures]
    return Contributor(
        key=key,
        captures=len(captures),
        mean_capture_score=statistics.fmean(scores) if scores else 0.0,
        comparisons=len(pairs),
        one_change=sum(p.usable_for_costs for p in pairs),
        baselines=sum(p.baseline for p in pairs),
        agreeing_baselines=sum(p.agreeing_baseline for p in pairs),
    )
