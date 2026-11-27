"""The captures list as a feed of setups, and each game's profile.

A setup is what the user tested: captures of the same game, one after another, with nothing
changed between them (same in-game settings, system and display, about the same length, no
new label). Those runs stack into one row, and the row's numbers are the runs combined. A
row is named after what changed from the setup before it, unless the user named it.

Every row is measured against a base: the oldest setup it can be compared with (same
display, about the same length), unless the user pinned another. So a game with benchmark
runs and longer live-match runs has one base for each kind of run. A row shows how it does
against its base for the goal, and says SAME when the difference is inside run-to-run noise.

A game's profile collects what was measured: the best setup for the goal (or the one the
user chose as theirs), the settings it differs from the base in, and what each tested
change did on this PC.

Nothing here is game-specific, and nothing touches Tk.
"""

from __future__ import annotations

import copy
import itertools
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from frametrace import goals, quality, summary

Capture = tuple[Path, dict]

NAMED = ("label", "settings", "system")  # setup kinds whose name says what the setup is
LENGTH_RATIO = 1.25  # runs this far apart in length are another scene (as in compare notes)

# Short silk names for the metric column; anything else is shown upper-cased.
METRIC_SHORT = {
    "Average": "AVERAGE",
    "1% low": "1% LOW",
    "0.1% low": "0.1% LOW",
    "CPU-side 1% low": "CPU 1% LOW",
    "PC latency, median": "LATENCY",
    "PC latency, P95": "P95 LATENCY",
    "Median": "MEDIAN",
    "Time in hitches": "HITCHES",
    "Max": "MAX",
    "Seconds at target": "AT TARGET",
}

_METRICS = {row[0]: row for _, rows in summary.COMPARE_GROUPS for row in rows}
# Stats that don't average: the longest frame stays the longest, per-second FPS is pooled.
_MAX_KEYS = {"max_ms", "max_cpu_ms"}
_POOLED_KEYS = {"second_fps"}


# --- small helpers ----------------------------------------------------------------------------


def exe(result: dict) -> str:
    return str(result["capture"].get("app") or "").lower()


def game_names(captures: list[Capture]) -> dict[str, str]:
    """exe (lower case) -> the game's name, from any capture where Frametrace found it.

    Captures made before Frametrace could name games only have the exe; with this map they
    land under the same heading as the newer ones.
    """
    out: dict[str, str] = {}
    for _, r in captures:  # newest first: the newest name wins
        n = (r.get("game") or {}).get("name")
        if n:
            out.setdefault(exe(r), n)
    return out


def game_of(result: dict, names: dict[str, str]) -> str:
    return (
        (result.get("game") or {}).get("name") or names.get(exe(result)) or result["capture"]["app"]
    )


def _settings(result: dict) -> list:
    return (result.get("game_settings") or {}).get("settings") or []


def _display(result: dict) -> tuple:
    d = quality.main_display(result)
    mode = result["analysis"]["display"].get("present_mode")
    return d.get("width"), d.get("height"), d.get("refresh_hz"), mode


def _length(result: dict) -> float:
    return result["analysis"]["stats"].get("duration_s") or 0.0


def same_length(a: dict, b: dict) -> bool:
    la, lb = _length(a), _length(b)
    return bool(la and lb) and max(la, lb) <= LENGTH_RATIO * min(la, lb)


def comparable(a: dict, b: dict) -> bool:
    """Same game, display and about the same length: the deltas mean something."""
    return exe(a) == exe(b) and _display(a) == _display(b) and same_length(a, b)


def metric_for(goal: goals.Goal, results: list[dict], target: int | None) -> str | None:
    """The first of the goal's deciding metrics that every result has."""
    for name in goal.decides:
        if all(metric_value(r, name, target) is not None for r in results):
            return name
    return None


def metric_value(result: dict, name: str, target: int | None) -> float | None:
    if name == "Seconds at target":
        return goals.seconds_at_target_pct(result["analysis"]["stats"], target)
    row = _METRICS.get(name)
    if not row:
        return None
    section, key = row[1]
    return result["analysis"][section].get(key)


def metric_text(name: str, value: float | None) -> tuple[str, str]:
    """(number, unit) for the list: digits and unit as in the comparison."""
    if value is None:
        return "---", ""
    if name == "Seconds at target":
        return f"{value:.0f}", "%"
    row = _METRICS[name]
    return f"{value:,.{row[2]}f}", row[3]


def _noise(name: str) -> tuple[float, bool]:
    """(band, absolute) for a metric: run-to-run noise from the comparison table."""
    if name == "Seconds at target":
        return 3.0, True
    row = _METRICS[name]
    return row[5], row[6]


def _apart(a: float, b: float, name: str) -> float:
    band, absolute = _noise(name)
    diff = abs(a - b) if absolute else (abs(a - b) / abs(b) * 100 if b else 0.0)
    return diff / band if band else 0.0


# --- setups -----------------------------------------------------------------------------------


@dataclass(eq=False)
class Setup:
    heading: str
    runs: list[Capture]  # oldest first
    name: str = ""
    kind: str = "time"  # label, settings, system, first or time: where the name came from
    changes: list[tuple[str, str, str]] = field(default_factory=list)  # from the setup before
    used: list[bool] = field(default_factory=list)  # False: left out of the combined numbers
    spread: bool = False  # the runs disagree beyond noise and none could be left out
    value: float | None = None  # the heading's metric, runs combined
    base: Setup | None = field(default=None, repr=False)  # what this row is measured against
    status: str = "na"  # against the base: base, better, worse, same, na; alone: no others
    change: str = ""  # "+3.1%", "SAME", "BASE" or "n/a"
    _combined: dict | None = None

    @property
    def folder(self) -> Path:
        """The newest run: how the list and the selection know this setup."""
        return self.runs[-1][0]

    @property
    def folders(self) -> list[Path]:
        return [f for f, _ in self.runs]

    @property
    def count(self) -> int:
        return len(self.runs)

    @property
    def used_runs(self) -> list[Capture]:
        return [run for run, ok in zip(self.runs, self.used or [True] * self.count) if ok]

    @property
    def trace_folder(self) -> Path:
        """The newest run that counts: its trace stands in for the setup on the scope."""
        return self.used_runs[-1][0]

    @property
    def label(self) -> str | None:
        return next((summary.label(r) for _, r in self.runs if summary.label(r)), None)

    @property
    def split(self) -> bool:
        """The user split this setup off from the one before."""
        return bool((self.runs[0][1].get("user") or {}).get("split"))

    @property
    def count_text(self) -> str:
        """×3, or ×2/3 when a run was left out; empty for a single run."""
        if self.count < 2:
            return ""
        used = len(self.used_runs)
        return f"×{used}/{self.count}" if used < self.count else f"×{self.count}"

    @property
    def result(self) -> dict:
        """The newest run, or the runs combined."""
        if self.count < 2:
            return self.runs[-1][1]
        if self._combined is None:
            self._combined = combine(self.used_runs, self.runs)
            if self.label:  # the setup's name, even when its newest run has none
                self._combined["user"] = {**(self._combined.get("user") or {}), "label": self.label}
        return self._combined


def continues(setup: Setup, result: dict) -> bool:
    """Is this capture another run of the setup (nothing changed since its newest run)?"""
    prev = setup.runs[-1][1]
    if (result.get("user") or {}).get("split"):
        return False
    if exe(prev) != exe(result):
        return False
    lab = summary.label(result)
    if lab and lab != setup.label:
        return False
    if bool(_settings(prev)) != bool(_settings(result)):
        return False
    if not _settings(result) and summary._limit(prev) != summary._limit(result):
        return False  # settings unread: a moved limit (GPU to CPU, a new cap) means a change
    if summary.settings_changes(prev, result):
        return False
    if _system_changes(prev, result):  # hardware, driver, Windows settings, display
        return False
    return same_length(prev, result)


def _system_changes(a: dict, b: dict) -> list[tuple[str, str, str]]:
    out = []
    for name, va, vb in summary.system_changes(a, b):
        if va.endswith(" MT/s") and vb.endswith(" MT/s"):
            va = va.removesuffix(" MT/s")  # "RAM speed 4800 → 5600 MT/s"
        out.append((name, va, vb))
    ma, mb = _display(a)[3], _display(b)[3]
    if ma != mb:
        short = summary.PRESENT_MODE_SHORT
        out.append(
            (
                "Present mode",
                short.get(ma, str(ma)).capitalize(),
                short.get(mb, str(mb)).capitalize(),
            )
        )
    return out


def short_key(key: str, keys: list[str]) -> str:
    """A setting's key without the namespace most of its game's keys share.

    "videocfg_shadow_quality" -> "shadow_quality" when the file has several videocfg_ keys,
    "sg.ShadowQuality" -> "ShadowQuality" for Unreal's scalability groups. Generic: a first
    segment counts as a namespace when at least three keys start with it.
    """
    for sep in ("_", "."):
        head, dot, rest = key.partition(sep)
        if dot and rest and sum(k.startswith(head + sep) for k in keys) >= 3:
            return rest
    return key


def _name(setup: Setup, before: Setup | None) -> None:
    """Name a setup: the user's label, else what changed from the setup before."""
    first, prev = setup.runs[0][1], before.runs[-1][1] if before else None
    if prev is not None:
        changes = summary.settings_changes(prev, first) or []
        setup.changes = changes or _system_changes(prev, first)
        kind = "settings" if changes else "system" if setup.changes else "time"
    else:
        setup.changes, kind = [], "first"
    if setup.label:
        setup.name, setup.kind = setup.label, "label"
        return
    setup.kind = kind
    if kind in ("settings", "system"):
        key, va, vb = setup.changes[0]
        if kind == "settings":
            key = short_key(key, [k for k, _ in _settings(first)])
        more = f" +{len(setup.changes) - 1}" if len(setup.changes) > 1 else ""
        setup.name = f"{key} {va} → {vb}{more}"
    else:  # the first setup, or one split off with nothing named: when it was captured
        setup.name = summary.when(first["capture"].get("started"))


def stack(captures: list[Capture], heading: str) -> list[Setup]:
    """Captures (oldest first) of one heading as setups, oldest first."""
    setups: list[Setup] = []
    for folder, result in captures:
        if setups and continues(setups[-1], result):
            setups[-1].runs.append((folder, result))
        else:
            setups.append(Setup(heading, [(folder, result)]))
    for i, s in enumerate(setups):
        _name(s, setups[i - 1] if i else None)
    return setups


def judge_runs(setup: Setup, metric: str | None, target: int | None) -> None:
    """Leave out a run that disagrees with the others beyond noise (with three or more runs).

    With two runs that disagree, or when most runs disagree, nothing can be left out: the
    setup is marked as spread instead.
    """
    setup.used, setup.spread, setup._combined = [True] * setup.count, False, None
    if setup.count < 2 or metric is None:
        return
    vals = [metric_value(r, metric, target) for _, r in setup.runs]
    if any(v is None for v in vals):
        return
    med = statistics.median(vals)
    off = [_apart(v, med, metric) > 1 for v in vals]
    if setup.count >= 3 and 0 < sum(off) < setup.count / 2:
        setup.used = [not o for o in off]
    elif any(_apart(a, b, metric) > 1 for a in vals for b in vals):
        setup.spread = True


def combine(used: list[Capture], runs: list[Capture] | None = None) -> dict:
    """One result for several runs of the same setup.

    The newest run that counts gives everything that isn't a number (game, settings, system,
    checks); frame rate, frame time, load and latency numbers are the mean of the runs, the
    longest frame the longest of them, and per-second FPS is pooled. "stack" says how many
    runs there were and which were left out.
    """
    results = [r for _, r in used]
    out = copy.deepcopy(results[-1])
    an = out["analysis"]
    for section in ("stats", "bottleneck", "display"):
        sec = an.get(section) or {}
        for key, v in list(sec.items()):
            if isinstance(v, bool):
                continue
            vals = [(r["analysis"].get(section) or {}).get(key) for r in results]
            if key in _POOLED_KEYS and all(isinstance(x, list) for x in vals):
                sec[key] = [s for x in vals for s in x]
            elif isinstance(v, (int, float)) and all(
                isinstance(x, (int, float)) and not isinstance(x, bool) for x in vals
            ):
                sec[key] = max(vals) if key in _MAX_KEYS else statistics.fmean(vals)
                if isinstance(v, int) and key not in _MAX_KEYS:
                    sec[key] = round(sec[key])
    runs = runs or used
    keep = {f for f, _ in used}
    out["stack"] = {
        "runs": len(runs),
        "used": len(used),
        "folders": [f.name for f, _ in runs],
        "left_out": [f.name for f, _ in runs if f not in keep],
        "started": [r["capture"].get("started") for _, r in runs],
        "per_run": [_run_numbers(r) for _, r in runs],
    }
    return out


def _run_numbers(r: dict) -> dict:
    s = r["analysis"]["stats"]
    return {
        k: s.get(k)
        for k in ("avg_fps", "p1_fps", "p01_fps", "cpu_p1_fps", "spike_time_pct", "duration_s")
    } | {"pc_latency_ms": r["analysis"]["display"].get("pc_latency_ms")}


# --- headings ---------------------------------------------------------------------------------


@dataclass
class Heading:
    key: str  # "game:Counter-Strike 2" or "group:Benchmark map"
    title: str
    custom: bool
    setups: list[Setup]  # newest first, as the list shows them
    base: Setup | None  # the base of the newest setup: the kind of run being tuned now
    metric: str | None  # the goal's metric for this heading

    @property
    def runs(self) -> int:
        return sum(s.count for s in self.setups)

    @property
    def oldest_first(self) -> list[Setup]:
        return list(reversed(self.setups))

    def setup_of(self, folder: Path) -> Setup | None:
        return next((s for s in self.setups if folder in s.folders), None)


def heading_key(result: dict, names: dict[str, str]) -> tuple[str, str, bool]:
    g = summary.group(result)
    if g:
        return f"group:{g}", g, True
    name = game_of(result, names)
    return f"game:{name}", name, False


def pins(bases: dict | None, key: str) -> list[str]:
    """The folder names the user pinned as bases under a heading (a name, or a list)."""
    v = (bases or {}).get(key)
    return [v] if isinstance(v, str) else list(v or [])


def pin(bases: dict | None, heading: Heading, setup: Setup) -> dict:
    """bases with this setup pinned: it replaces the pin of its own kind of run."""
    keep = [
        n for n in pins(bases, heading.key)
        if not any(n in {f.name for f in s.folders} and comparable(s.result, setup.result)
                   for s in heading.setups)
    ]  # fmt: skip
    return {**(bases or {}), heading.key: [*keep, setup.runs[0][0].name]}


def versus(setup: Setup, base: Setup, goal: goals.Goal, target: int | None) -> tuple[str, str]:
    """(status, text) of a setup against the base, for the goal."""
    if setup is base:
        return "base", "BASE"
    a, b = base.result, setup.result
    if not comparable(a, b):
        return "na", "n/a"
    status, decide = summary.goal_status(a, b, goal, target)
    if status == "na" or not decide:
        return "na", "n/a"
    if status == "same":
        return "same", "SAME"
    return status, decide[0].change_text()


def build(
    captures: list[Capture],
    goal: goals.Goal,
    target: int | None = None,
    bases: dict[str, str] | None = None,
) -> list[Heading]:
    """The list: headings ordered by their newest run, setups newest first.

    captures come newest first (as capture.list_captures gives them). bases maps a heading's
    key to the folder names of runs in setups the user pinned as bases (see pin()).
    """
    names = game_names(captures)
    order: dict[str, tuple[str, bool, list[Capture]]] = {}
    for folder, result in captures:
        key, title, custom = heading_key(result, names)
        order.setdefault(key, (title, custom, []))[2].append((folder, result))
    out = []
    for key, (title, custom, caps) in order.items():
        setups = stack(list(reversed(caps)), key)
        results = [r for _, r in caps]
        metric = metric_for(goal, results, target)
        for s in setups:
            judge_runs(s, metric, target)
        names_pinned = pins(bases, key)
        pinned = [s for s in setups if names_pinned and any(
            n in {f.name for f in s.folders} for n in names_pinned)]  # fmt: skip
        for s in setups:
            s.value = metric_value(s.result, metric, target) if metric else None
            mine = [p for p in pinned if comparable(p.result, s.result)]
            s.base = mine[-1] if mine else next(o for o in setups if comparable(o.result, s.result))
            s.status, s.change = versus(s, s.base, goal, target)
        for s in setups:  # a base nothing is measured against isn't worth a word
            if s.status == "base" and not any(o.base is s for o in setups if o is not s):
                s.status, s.change = "alone", ""
        out.append(Heading(key, title, custom, list(reversed(setups)), setups[-1].base, metric))
    return out


# --- the game's profile -----------------------------------------------------------------------


@dataclass
class Tested:
    """One change from a setup to the next, measured for the goal."""

    name: str
    kind: str
    changes: list[tuple[str, str, str]]
    status: str  # better, worse, same, na
    change: str  # "+3.1%"
    metric: str | None
    before: float | None
    after: float | None
    runs: tuple[int, int]


@dataclass
class Profile:
    heading: Heading
    goal: goals.Goal
    target: int | None
    best: Setup | None
    chosen: bool  # the user picked these settings; else the best measured
    best_status: str
    best_change: str
    differs: list[tuple[str, str, str]] | None  # best vs base settings; None: not read
    settings: list[tuple[str, str]]  # the best setup's in-game settings
    tested: list[Tested]  # newest first
    left_out: int  # runs left out of combined numbers
    others: int  # setups of another kind of run (other length or display), with their own base


def _better(a: float | None, b: float | None, metric: str | None) -> bool:
    """Is b better than a for the metric's direction?"""
    if a is None or b is None or metric is None:
        return False
    higher = True if metric == "Seconds at target" else _METRICS[metric][4]
    return b > a if higher else b < a


def profile(
    heading: Heading,
    goal: goals.Goal,
    target: int | None = None,
    chosen: str | None = None,
) -> Profile:
    """What the tests of one heading add up to.

    The best setup is the user's choice when they made one (the folder name of a run in it),
    else the setup that beats the base by the most for the goal, else the base. It's picked
    among the setups measured against the newest setup's base: the kind of run being tuned.
    """
    setups, base, metric = heading.oldest_first, heading.base, heading.metric
    current = [s for s in setups if s.base is base]
    pick = next((s for s in setups if chosen and chosen in {f.name for f in s.folders}), None)
    best = pick
    if best is None and base is not None:
        best = base
        for s in current:
            if s.status == "better" and (best is base or _better(best.value, s.value, metric)):
                best = s
    tested = []
    for before, after in itertools.pairwise(setups):
        if after.kind == "time" and not after.changes:
            continue  # nothing changed that Frametrace or the user named
        if not comparable(before.result, after.result):
            continue
        status, decide = summary.goal_status(before.result, after.result, goal, target)
        d = decide[0] if decide else None
        tested.append(
            Tested(
                after.name,
                after.kind,
                after.changes,
                status,
                "SAME" if status == "same" else d.change_text() if d else "n/a",
                d.label if d else metric,
                d.a if d else None,
                d.b if d else None,
                (len(before.used_runs), len(after.used_runs)),
            )
        )
    tested.reverse()
    differs = summary.settings_changes(base.result, best.result) if best and base else None
    if best is base:
        status, change = "base", "BASE"  # also when nothing else was measured against it
    else:
        status, change = (best.status, best.change) if best else ("na", "n/a")
    return Profile(
        heading=heading,
        goal=goal,
        target=target,
        best=best,
        chosen=pick is not None,
        best_status=status,
        best_change=change,
        differs=differs,
        settings=[tuple(kv) for kv in _settings(best.result)] if best else [],
        tested=tested,
        left_out=sum(s.count - len(s.used_runs) for s in setups),
        others=sum(1 for s in setups if s.base is not base),
    )


def profile_text(p: Profile) -> str:
    """The profile as text to paste into an AI with the next report."""
    h, goal = p.heading, p.goal
    title = goal.label if goal.key != "target" else f"{goal.label} ({p.target} FPS)"
    lines = [
        f"Frametrace profile · {h.title}",
        f"Goal: {title}",
        f"Measured on this PC: {len(h.setups)} setups, {h.runs} runs.",
        "",
    ]
    if p.best is None:
        return "\n".join(lines + ["No captures yet."])
    m = h.metric
    num, unit = metric_text(m, p.best.value) if m else ("---", "")
    what = "Your settings (chosen by you)" if p.chosen else f"Best measured for {goal.phrase}"
    vs = "" if p.best is h.base else f", {p.best_change} vs the base" if p.best_change else ""
    lines += [
        "## " + what,
        (
            f'"{p.best.name}": {m or "goal metric"} {num}{" " + unit if unit else ""}'
            f" over {len(p.best.used_runs)} run{'s' if len(p.best.used_runs) != 1 else ''}{vs}."
        ),
    ]
    if h.base is not None and p.best is not h.base:
        lines.append(f'Base: "{h.base.name}".')
    if p.differs:
        lines += ["", "## Settings that differ from the base"]
        lines += [f"- {k}: {a} -> {b}" for k, a, b in p.differs]
    if p.tested:
        lines += ["", "## Changes tested (from one setup to the next)"]
        for t in p.tested:
            word = {"better": "better", "worse": "worse", "same": "no change (inside noise)"}
            lines.append(
                f"- {t.name}: {t.metric or 'goal'} {t.change}, {word.get(t.status, t.status)}"
                f" ({t.runs[0]} vs {t.runs[1]} run{'s' if t.runs[1] != 1 else ''})"
            )
    if p.settings:
        lines += ["", "## All in-game settings of this setup"]
        lines += [f"- {k}: {v}" for k, v in p.settings]
    lines += [
        "",
        (
            "Use these measured results on my PC before guesses or general advice. Visual cost"
            " isn't measured: say what each kept change costs in looks."
        ),
    ]
    return "\n".join(lines)
