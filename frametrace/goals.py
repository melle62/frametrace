"""Tuning goals: what the user wants to improve, and how a capture measures it.

The user picks a goal before (or after) a capture. The goal decides which numbers lead the
report, what the AI is asked to do, and which metric decides "better" in a comparison.
Nothing here is game-specific.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_GOAL = "avg_fps"


@dataclass(frozen=True)
class Goal:
    key: str
    label: str  # short, for the window: "Higher 1% lows"
    aim: str  # one sentence for the AI: what "better" means
    trade_off: str  # what the user accepts in exchange
    # Compare: the metrics that decide the verdict, by label in summary.COMPARE_GROUPS
    # (or one of the goal metrics below), most important first.
    decides: tuple[str, ...]
    phrase: str = ""  # "B is better for {phrase}"


GOALS: dict[str, Goal] = {
    g.key: g
    for g in (
        Goal(
            "avg_fps",
            "Higher average FPS",
            "raise the average frame rate",
            "visual quality may drop; keep the 1% lows from getting worse",
            ("Average", "1% low"),
            "a higher average FPS",
        ),
        Goal(
            "lows",
            "Higher 1% lows",
            "raise the 1% and 0.1% lows so the slowest frames come closer to the average",
            "a slightly lower average FPS is fine if the lows improve",
            ("1% low", "0.1% low", "CPU-side 1% low"),
            "higher 1% lows",
        ),
        Goal(
            "latency",
            "Lower latency",
            "cut the time from input to frame on screen",
            "visual quality and some average FPS may drop",
            ("PC latency, median", "PC latency, P95", "Median"),
            "lower latency",
        ),
        Goal(
            "stutter",
            "Less stutter",
            "remove hitches and uneven frame pacing",
            "a lower average or a frame cap is fine if pacing gets even",
            ("Time in hitches", "0.1% low", "Max"),
            "less stutter",
        ),
        Goal(
            "target",
            "Hit a target FPS",
            "hold the target frame rate at the best visual quality possible",
            "spend any headroom above the target on visual quality",
            ("Seconds at target", "1% low"),
            "hitting the target FPS",
        ),
    )
}


def get(key: str | None) -> Goal:
    return GOALS.get(key or "", GOALS[DEFAULT_GOAL])


def from_result(result: dict) -> tuple[Goal, int | None]:
    """The goal saved with a capture (older captures get the default)."""
    g = result.get("goal") or {}
    return get(g.get("key")), g.get("target_fps")


def default_target(result: dict) -> int | None:
    """Without an explicit target: the primary display's refresh rate."""
    displays = (result.get("system") or {}).get("displays") or []
    primary = next((d for d in displays if d.get("primary")), displays[0] if displays else None)
    hz = primary.get("refresh_hz") if primary else None
    return int(hz) if hz else None


def seconds_at_target_pct(stats: dict, target: float | None) -> float | None:
    """Share of whole seconds that averaged at least the target (within 1%)."""
    secs = stats.get("second_fps") or []
    if not target or not secs:
        return None
    return 100 * sum(s >= 0.99 * target for s in secs) / len(secs)


def target_status(stats: dict, target: float) -> str:
    """met, close, short or above (enough headroom to raise quality)."""
    p1, avg = stats["p1_fps"], stats["avg_fps"]
    at = seconds_at_target_pct(stats, target)
    if p1 >= 1.15 * target:
        return "above"
    if p1 >= 0.97 * target or (at is not None and at >= 99):
        return "met"
    if avg >= target:
        return "close"
    return "short"


TARGET_WORDS = {
    "above": "met with room to spare: the 1% low is well above the target, so quality can go up",
    "met": "met: the 1% low is at the target",
    "close": "almost: the average is above the target but the slowest frames fall below it",
    "short": "not met: the average is below the target",
}
