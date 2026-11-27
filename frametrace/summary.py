"""Plain-text pieces of the summary view, computed from a saved result.

Kept apart from the Tk code so the wording can be tested without a display.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

from frametrace import goals

PRESENT_MODE_SHORT = {
    "Hardware: Independent Flip": "INDEPENDENT FLIP",
    "Hardware Composed: Independent Flip": "COMPOSED FLIP",
    "Hardware: Legacy Flip": "LEGACY FLIP",
    "Hardware: Legacy Copy to front buffer": "LEGACY COPY",
    "Composed: Flip": "COMPOSED",
    "Composed: Copy with GPU GDI": "COMPOSED COPY",
    "Composed: Copy with CPU GDI": "COMPOSED COPY",
}


@dataclass
class ReadoutValue:
    title: str
    value: str | None
    unit: str
    sub: str
    swatch: str | None = None


def when(iso: str | None, fmt: str = "%d %b %H:%M") -> str:
    try:
        return dt.datetime.fromisoformat(iso).strftime(fmt) if iso else "?"
    except ValueError:
        return iso or "?"


def _num(v: float | None, digits: int = 1) -> str | None:
    return None if v is None else f"{v:,.{digits}f}"


def initials(app: str) -> str:
    stem = app.rsplit(".", 1)[0] if app.lower().endswith(".exe") else app
    words = [w for w in re.split(r"[\s-]+", stem) if w and w[0].isalpha()]
    if len(words) >= 2:  # "Counter-Strike 2" -> CS
        return (words[0][0] + words[1][0]).upper()
    letters = [ch for ch in stem if ch.isalnum()]
    return "".join(letters[:2]).upper() or "?"


def name(result: dict) -> str:
    """The game's name when Frametrace found it, else the exe."""
    return (result.get("game") or {}).get("name") or result["capture"]["app"]


def label(result: dict) -> str | None:
    """The user's own name for this run ("MSAA 2x"), if they gave one."""
    return (result.get("user") or {}).get("label") or None


def benchmark(result: dict) -> str | None:
    """The user's tag for the run's scene ("Mirage Benchmark"), if they gave one."""
    return ((result.get("user") or {}).get("benchmark") or "").strip() or None


def same_benchmark(a: dict, b: dict) -> bool:
    """Both untagged, or the same tag (case and spaces don't matter)."""
    ta, tb = benchmark(a), benchmark(b)
    return " ".join((ta or "").casefold().split()) == " ".join((tb or "").casefold().split())


def group(result: dict) -> str | None:
    """The group the user put this run in, if any."""
    return (result.get("user") or {}).get("group") or None


def title(result: dict) -> str:
    """What a run is called in the list and the header: its label, else the game."""
    return label(result) or name(result)


def rail_groups(captures: list[tuple]) -> list[tuple[str, bool, list[tuple]]]:
    """(heading, custom, [(folder, result), ...]) for the captures list.

    Runs go in the group the user gave them, else under their game. Groups are ordered
    by their newest run (captures come in newest first), runs inside stay newest first.
    """
    order: dict[tuple[str, bool], list[tuple]] = {}
    for folder, result in captures:
        g = group(result)
        key = (g, True) if g else (name(result), False)
        order.setdefault(key, []).append((folder, result))
    return [(heading, custom, rows) for (heading, custom), rows in order.items()]


def subtitle(result: dict) -> str:
    cap, an = result["capture"], result["analysis"]
    s = an["stats"]
    st = result.get("stack")
    parts = [
        # a labelled run names its game here; otherwise the title is the game: show the exe
        *([name(result)] if label(result) else [cap["app"]] if name(result) != cap["app"] else []),
        *(
            [f"{st['used']} runs combined" + (f", {st['runs'] - st['used']} left out" if st["used"] < st["runs"] else ""),
             f"newest {when(cap.get('started'))}", f"{s['duration_s']:.0f} s each"]
            if st
            else [when(cap.get("started")), f"{s['duration_s']:.1f} s analyzed", f"{s['frames']:,} frames"]
        ),
    ]  # fmt: skip
    if an.get("skipped_start_s"):
        parts.append(f"first {an['skipped_start_s']:.0f} s skipped")
    return " · ".join(parts)


def tags(result: dict) -> list[str]:
    d = result["analysis"]["display"]
    out = []
    if d.get("runtime"):
        out.append(str(d["runtime"]).upper())
    mode = d.get("present_mode")
    if mode:
        out.append(PRESENT_MODE_SHORT.get(mode, mode.upper()))
    if d.get("vsync") is not None:
        out.append("VSYNC ON" if d["vsync"] else "VSYNC OFF")
    if d.get("pc_latency_ms"):
        out.append("REFLEX")
    return out


def verdict(result: dict) -> tuple[str, str]:
    """(headline, one sentence) for the verdict panel."""
    b = result["analysis"]["bottleneck"]
    if not b.get("available"):
        return (
            "No bottleneck data.",
            "This capture has no GPU busy column, so the CPU and GPU can't be told apart.",
        )
    gpu, cpu, wait = b["gpu_pct"], b["cpu_pct"], b["wait_pct"]
    busy, ceiling = b.get("median_gpu_busy_ms"), b.get("gpu_fps_ceiling")
    gpu_note = f" Median GPU busy {busy:.2f} ms" if busy else ""
    if b.get("cap_fps"):
        return (
            f"Capped at {b['cap_fps']:.0f} FPS.",
            f"A frame cap or VSync holds the frame rate, so {wait:.0f}% of frames were waiting."
            + (
                f"{gpu_note}: the GPU alone could do about {ceiling:,.0f} FPS."
                if busy and ceiling
                else ""
            ),
        )
    top = max((gpu, "GPU"), (cpu, "CPU"), (wait, "wait"))
    if top[0] >= 70 and top[1] == "GPU":
        return (
            "GPU-limited.",
            f"{gpu:.0f}% of frames waited on the GPU."
            + (
                f"{gpu_note}: the GPU alone could do about {ceiling:,.0f} FPS."
                if busy and ceiling
                else ""
            ),
        )
    if top[0] >= 70 and top[1] == "CPU":
        return (
            "CPU-limited.",
            f"{cpu:.0f}% of frames waited on the CPU."
            + (
                f"{gpu_note}, so the GPU had room for about {ceiling:,.0f} FPS."
                if busy and ceiling
                else ""
            ),
        )
    if top[0] >= 70:
        return (
            "Waiting on VSync or a cap.",
            f"{wait:.0f}% of frames finished early and waited to be shown.",
        )
    lean = {"GPU": "the GPU", "CPU": "the CPU", "wait": "VSync or a cap"}[top[1]]
    return (
        f"Mixed, leaning {top[1] if top[1] != 'wait' else 'waiting'}.",
        f"GPU-limited {gpu:.0f}%, CPU-limited {cpu:.0f}%, waiting {wait:.0f}%. The scene moves the limit; {lean} wins most often.",
    )


def readouts(result: dict) -> list[ReadoutValue]:
    an = result["analysis"]
    s, d = an["stats"], an["display"]
    lat, lat95 = d.get("pc_latency_ms"), d.get("pc_latency_p95_ms")
    out = [
        ReadoutValue(
            "Average", _num(s["avg_fps"]), "FPS", f"median {s['median_ms']:.2f} ms", "ch1"
        ),
        ReadoutValue("1% low", _num(s["p1_fps"], 0), "FPS", f"P99 {s['p99_ms']:.2f} ms"),
        ReadoutValue(
            "CPU-side 1% low",
            _num(s.get("cpu_p1_fps"), 0),
            "FPS",
            "in-game counter" if s.get("cpu_p1_fps") else "not in this CSV",
        ),
        ReadoutValue(
            "PC latency", _num(lat), "ms", "Reflex markers" if lat else "needs NVIDIA Reflex"
        ),
    ]
    if lat95:
        out.append(ReadoutValue("P95 latency", _num(lat95), "ms", "input to frame sent"))
    else:
        out.append(
            ReadoutValue("0.1% low", _num(s["p01_fps"], 0), "FPS", f"P99.9 {s['p999_ms']:.2f} ms")
        )
    return out


def details(result: dict) -> list[tuple[str, str]]:
    an = result["analysis"]
    s, b, d = an["stats"], an["bottleneck"], an["display"]

    def ms(v):
        return f"{v:.2f} ms" if v is not None else "n/a"

    worst = f" · worst {s['worst_spikes'][0][0]:.1f} ms" if s.get("worst_spikes") else ""
    rows = [
        ("GPU busy, median", ms(b.get("median_gpu_busy_ms"))),
        ("CPU busy, median", ms(b.get("median_cpu_busy_ms"))),
        ("Blocked in Present", ms(b.get("median_cpu_wait_ms"))),
        ("Hitches", f"{s['spikes']}{worst}"),
        (
            "Not displayed",
            f"{d['dropped_pct']:.1f}%" if d.get("dropped_pct") is not None else "n/a",
        ),
    ]
    return rows


def rail_row(result: dict) -> tuple[str, str, str, str, str]:
    """(lamp level, name, meta, fps, sub) for the captures list."""
    cap, an = result["capture"], result["analysis"]
    s, b = an["stats"], an["bottleneck"]
    if b.get("cap_fps"):
        sub, level = f"cap {b['cap_fps']:.0f}", "info"
    elif b.get("available"):
        top = max((b["gpu_pct"], "GPU"), (b["cpu_pct"], "CPU"), (b["wait_pct"], "wait"))
        sub, level = f"{top[1]} {top[0]:.0f}%", "ok"
    else:
        sub, level = "no GPU data", "info"
    if s["duration_s"] < 10:
        sub, level = "short", "warn"
    meta = f"{when(cap.get('started'))} · {s['duration_s']:.0f} s"
    return level, title(result), meta, f"{s['avg_fps']:.1f}", sub


def system_rows(lines: list[str]) -> list[tuple[str, str]]:
    """'CPU: AMD ...' lines from report.render_system as (label, value) rows."""
    out = []
    for line in lines:
        key, sep, value = line.partition(": ")
        out.append((key, value) if sep else ("", line))
    return out


SETTING_NAMES = {
    "power plan": "Power plan",
    "Game Mode": "Game Mode",
    "HAGS": "HAGS",
    "memory integrity": "Memory integrity",
    "windowed optimizations": "Windowed optimizations",
}


def system_sections(lines: list[str]) -> list[tuple[str, list[tuple[str, str]]]]:
    """The System tab: hardware rows, then one row per Windows setting."""
    hardware, settings = [], []
    for key, value in system_rows(lines):
        if key != "Settings":
            hardware.append((key, value))
            continue
        for part in value.split(" | "):
            for prefix, name in SETTING_NAMES.items():
                if part.startswith(prefix + " "):
                    shown = part[len(prefix) + 1 :].strip()
                    settings.append((name, "unknown" if shown == "?" else shown))
                    break
            else:
                settings.append(("", part))
    out = [("Hardware", hardware)]
    if settings:
        out.append(("Windows settings", settings))
    return out


# --- compare --------------------------------------------------------------------------------

# Run-to-run noise measured on CS2 (two identical 100 s runs): average 0.2% apart, present-to-
# present 1% low 2.8%, CPU-side 1% low 0.3%. Changes inside these bands are marked "same".
# (label, (section, key), digits, unit, higher_is_better, noise, absolute)
# absolute: the change is in the value's own unit (percentage points), not relative.
COMPARE_GROUPS: list[tuple[str, list[tuple]]] = [
    (
        "Frame rate",
        [
            ("Average", ("stats", "avg_fps"), 1, "FPS", True, 1.0, False),
            ("1% low", ("stats", "p1_fps"), 0, "FPS", True, 3.0, False),
            ("CPU-side 1% low", ("stats", "cpu_p1_fps"), 0, "FPS", True, 3.0, False),
            ("0.1% low", ("stats", "p01_fps"), 0, "FPS", True, 5.0, False),
            ("Worst second", ("stats", "worst_1s_fps"), 0, "FPS", True, 5.0, False),
        ],
    ),
    (
        "Frame times",
        [
            ("Median", ("stats", "median_ms"), 2, "ms", False, 1.0, False),
            ("P99", ("stats", "p99_ms"), 2, "ms", False, 3.0, False),
            ("Max", ("stats", "max_ms"), 1, "ms", False, 15.0, False),
            ("Time in hitches", ("stats", "spike_time_pct"), 2, "%", False, 0.2, True),
        ],
    ),
    (
        "Load per frame",
        [
            ("GPU busy, median", ("bottleneck", "median_gpu_busy_ms"), 2, "ms", None, 3.0, False),
            ("CPU busy, median", ("bottleneck", "median_cpu_busy_ms"), 2, "ms", None, 3.0, False),
        ],
    ),
    (
        "Latency",
        [
            ("PC latency, median", ("display", "pc_latency_ms"), 2, "ms", False, 3.0, False),
            ("PC latency, P95", ("display", "pc_latency_p95_ms"), 1, "ms", False, 5.0, False),
        ],
    ),
]
KEY_METRICS = ("Average", "1% low", "CPU-side 1% low", "P99", "PC latency, median")


@dataclass
class Delta:
    label: str
    unit: str
    a: float | None
    b: float | None
    digits: int
    higher_is_better: bool | None
    noise: float
    absolute: bool

    @property
    def change(self) -> float | None:
        """Percent (or points, when absolute) from A to B."""
        if self.a is None or self.b is None:
            return None
        if self.absolute:
            return self.b - self.a
        return 100 * (self.b - self.a) / self.a if self.a else None

    @property
    def status(self) -> str:
        """better, worse, same, changed (no direction) or na."""
        ch = self.change
        if ch is None:
            return "na"
        if abs(ch) <= self.noise:
            return "same"
        if self.higher_is_better is None:
            return "changed"
        return "better" if (ch > 0) == self.higher_is_better else "worse"

    def fmt(self, v: float | None) -> str:
        return "n/a" if v is None else f"{v:,.{self.digits}f}"

    def change_text(self) -> str:
        ch = self.change
        if ch is None:
            return "n/a"
        return f"{ch:+.{self.digits}f} pp" if self.absolute else f"{ch:+.1f}%"


def compare_deltas(a: dict, b: dict) -> list[tuple[str, list[Delta]]]:
    """Grouped deltas from A (the older capture) to B; rows missing in both are left out."""
    out = []
    for group, rows in COMPARE_GROUPS:
        deltas = []
        for label, (section, key), digits, unit, better, noise, absolute in rows:
            va = a["analysis"][section].get(key)
            vb = b["analysis"][section].get(key)
            if va is None and vb is None:
                continue
            deltas.append(Delta(label, unit, va, vb, digits, better, noise, absolute))
        if deltas:
            out.append((group, deltas))
    return out


def _limit(result: dict) -> str:
    b = result["analysis"]["bottleneck"]
    if not b.get("available"):
        return "unknown"
    if b.get("cap_fps"):
        return "cap"
    top = max((b["gpu_pct"], "GPU"), (b["cpu_pct"], "CPU"), (b["wait_pct"], "wait"))
    return top[1]


def _phrase(d: Delta) -> str:
    """Metric in words, numbers in `ticks` (the window sets them in Plex Mono)."""
    return f"{d.label}  `{d.change_text()}`  `{d.fmt(d.a)} to {d.fmt(d.b)} {d.unit}`"


def runs(text: str) -> list[tuple[str, bool]]:
    """'B is `4.2%` faster' -> [('B is ', False), ('4.2%', True), (' faster', False)]."""
    return [(part, i % 2 == 1) for i, part in enumerate(text.split("`")) if part]


def plain(text: str) -> str:
    return text.replace("`", "")


# A number in running text, with its unit: "426.7 FPS", "2.25 ms", "93%", "6000 MT/s".
# Not digits inside names: 7800X3D, DDR5, P95, SHA-256, 2x.
_NUMBER = re.compile(
    r"(?<![\w.~-])[-+~]?\d+(?:,\d{3})*(?:\.\d+)?"
    r"(?:\s?(?:FPS|ms|MT/s|Hz|GB|pp|s|%)(?![\w/])|%)?"
    r"(?![\w])"
)


def number_runs(text: str) -> list[tuple[str, bool]]:
    """Split prose so every number (and its unit) can be set in Plex Mono.

    Text with `ticks` is split on the ticks instead (see runs()).
    """
    if "`" in text:
        return runs(text)
    out: list[tuple[str, bool]] = []
    pos = 0
    for m in _NUMBER.finditer(text):
        if m.start() > pos:
            out.append((text[pos : m.start()], False))
        out.append((m.group(), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


def goal_deltas(a: dict, b: dict, target: int | None = None) -> dict[str, Delta]:
    """Every compare delta by label, plus "Seconds at target" when there is a target."""
    deltas = {d.label: d for _, rows in compare_deltas(a, b) for d in rows}
    if target:
        va = goals.seconds_at_target_pct(a["analysis"]["stats"], target)
        vb = goals.seconds_at_target_pct(b["analysis"]["stats"], target)
        if va is not None and vb is not None:
            deltas["Seconds at target"] = Delta(
                f"Seconds at {target} FPS", "%", va, vb, 0, True, 3.0, True
            )
    return deltas


def goal_status(a: dict, b: dict, goal: goals.Goal, target: int | None) -> tuple[str, list[Delta]]:
    """better, worse, same or na for the goal, and the deltas that decide it (first leads).

    The first deciding metric both captures have sets the verdict. When it stays inside
    run-to-run noise, the others can tip it, but only if they agree.
    """
    deltas = goal_deltas(a, b, target)
    decide = [deltas[k] for k in goal.decides if k in deltas and deltas[k].status != "na"]
    if not decide:
        return "na", []
    status = decide[0].status
    if status == "same":
        moved = {d.status for d in decide[1:] if d.status in ("better", "worse")}
        if len(moved) == 1:
            status = moved.pop()
    return status, decide


def compare_verdict(
    a: dict, b: dict, goal: goals.Goal | None = None, target: int | None = None
) -> tuple[str, list[tuple[str, str]], list[str]]:
    """(headline, [(status, phrase)], notes) for the compare view. A is the older capture.

    The headline answers "did it help my goal?"; the items are the goal's metrics, then
    other key metrics that moved beyond run-to-run noise (side effects). Numbers are wrapped
    in `ticks`: see runs() and plain().
    """
    if goal is None:
        goal, target = goals.from_result(b)
        if goal.key == "target":
            target = target or goals.default_target(b) or 60
    status, decide = goal_status(a, b, goal, target)
    phrase = goal.phrase if goal.key != "target" else f"holding {target} FPS"
    head = {
        "better": f"B is better for {phrase}.",
        "worse": f"B is worse for {phrase}.",
        "same": f"No clear change for {phrase}.",
        "na": f"{goal.label} can't be measured in both captures.",
    }[status]
    items = [(d.status if d.status != "na" else "same", _phrase(d)) for d in decide]
    deltas = goal_deltas(a, b, target)
    shown = {d.label for d in decide}
    side = [deltas[k] for k in KEY_METRICS if k in deltas and k not in shown]
    items += [("better", _phrase(d)) for d in side if d.status == "better"]
    items += [("worse", _phrase(d)) for d in side if d.status == "worse"]
    notes = []
    if settings_unchanged_but_moved(a, b, target):
        notes.append(
            "Same in-game settings in A and B, yet the results moved: the difference comes from"
            " the run itself (another start point, the first run after loading, background"
            " activity), not from settings."
        )
    if goal.key == "latency" and "PC latency, median" not in shown and decide:
        notes.append("No Reflex latency markers in both captures: judged by frame time.")
    la, lb = _limit(a), _limit(b)
    if la != lb and "unknown" not in (la, lb):
        word = {"GPU": "the GPU", "CPU": "the CPU", "wait": "VSync or a cap", "cap": "a frame cap"}
        notes.append(f"The limit moved from {word[la]} to {word[lb]}.")
    ca, cb = a["capture"], b["capture"]
    if ca.get("app") != cb.get("app"):
        notes.append(f"Different games: A is {name(a)}, B is {name(b)}.")
    ba, bb = benchmark(a), benchmark(b)
    if (ba or bb) and (ba or "").casefold() != (bb or "").casefold():
        notes.append(
            f"Different benchmarks: A is {ba or 'untagged'}, B is {bb or 'untagged'}."
            " Compare runs of the same scene."
        )
    da, db = a["analysis"]["stats"]["duration_s"], b["analysis"]["stats"]["duration_s"]
    if max(da, db) > 1.25 * min(da, db):
        notes.append(
            f"Different lengths ({da:.0f} s and {db:.0f} s): compare runs of the same scene."
        )
    return head, items, notes


def settings_changes(a: dict, b: dict) -> list[tuple[str, str, str]] | None:
    """(key, A, B) for in-game settings that differ; None when either capture has none.

    When the two were read by different readers (an older Frametrace read fewer files),
    only keys both have are compared, so a newly read file doesn't look like a change.
    """
    ga, gb = a.get("game_settings") or {}, b.get("game_settings") or {}
    sa, sb = ga.get("settings"), gb.get("settings")
    if not sa or not sb:
        return None
    da, db = dict(map(tuple, sa)), dict(map(tuple, sb))
    keys = [k for k, _ in sa] + [k for k, _ in sb if k not in da]
    if ga.get("reader") != gb.get("reader"):
        keys = [k for k in keys if k in da and k in db]
    return [(k, da.get(k, "-"), db.get(k, "-")) for k in keys if da.get(k) != db.get(k)]


def settings_unchanged_but_moved(a: dict, b: dict, target: int | None = None) -> bool:
    """Both captures' settings were read, none changed, and a key metric moved beyond noise."""
    changes = settings_changes(a, b)
    if changes is None or changes:
        return False
    deltas = goal_deltas(a, b, target)
    keys = ("Average", "1% low", "0.1% low", "P99", "Time in hitches")
    return any(deltas[k].status in ("better", "worse") for k in keys if k in deltas)


def system_changes(a: dict, b: dict) -> list[tuple[str, str, str]]:
    """(label, A, B) for system details that differ between the two captures."""
    from frametrace.report import SYSTEM_FIELDS

    def show(v) -> str:
        if isinstance(v, bool):
            return "on" if v else "off"
        return "unknown" if v is None else str(v)

    sa, sb = a.get("system") or {}, b.get("system") or {}
    out = []
    for label, key in SYSTEM_FIELDS:
        if sa.get(key) != sb.get(key):
            unit = " MT/s" if key == "ram_running_mts" and sa.get(key) and sb.get(key) else ""
            out.append((label, show(sa.get(key)) + unit, show(sb.get(key)) + unit))
    ga = [
        f"{g['name']} {g.get('nvidia_driver') or g.get('driver') or ''}".strip()
        for g in sa.get("gpus") or []
    ]
    gb = [
        f"{g['name']} {g.get('nvidia_driver') or g.get('driver') or ''}".strip()
        for g in sb.get("gpus") or []
    ]
    if ga != gb:
        out.append(("GPU / driver", ", ".join(ga) or "unknown", ", ".join(gb) or "unknown"))
    da = [f"{d['width']}x{d['height']} @ {d['refresh_hz']} Hz" for d in sa.get("displays") or []]
    db = [f"{d['width']}x{d['height']} @ {d['refresh_hz']} Hz" for d in sb.get("displays") or []]
    if da != db:
        out.append(("Display", ", ".join(da) or "unknown", ", ".join(db) or "unknown"))
    return out


# --- goal and game ---------------------------------------------------------------------------

SETTINGS_HINT = {
    "GPU": "GPU-heavy settings move it: resolution, upscaling, shadows, lighting.",
    "CPU": "CPU-heavy settings move it: view distance, crowds and objects, physics.",
    "cap": "The cap or VSync sets the rate: change that first, spend the headroom on quality.",
    "wait": "VSync or a cap sets the rate: change that first.",
}


def plain_verdict(result: dict) -> tuple[str, str]:
    """(headline, sentence) for the Summary panel: what limits the frame rate, and which kind
    of setting moves it. No goal: the goal only shapes the text for the AI."""
    head, sentence = verdict(result)
    hint = SETTINGS_HINT.get(_limit(result), "")
    return head, f"{sentence} {hint}".strip()


def goal_verdict(result: dict, goal: goals.Goal, target: int | None) -> tuple[str, str]:
    """(headline, sentence) for the Summary panel, led by the chosen goal.

    The target goal leads with whether the target was met; the others keep the
    bottleneck headline and add which kind of setting moves the goal.
    """
    head, sentence = verdict(result)
    limit = _limit(result)
    hint = SETTINGS_HINT.get(limit, "")
    if goal.key == "target" and target:
        s = result["analysis"]["stats"]
        status = goals.target_status(s, target)
        title = {
            "above": f"Target {target} FPS met, with room.",
            "met": f"Target {target} FPS met.",
            "close": f"Target {target} FPS almost met.",
            "short": f"Target {target} FPS not met.",
        }[status]
        at = goals.seconds_at_target_pct(s, target)
        lead = f"1% low {s['p1_fps']:.0f} FPS, average {s['avg_fps']:.0f} FPS"
        lead += f", {at:.0f}% of seconds at target." if at is not None else "."
        return title, f"{lead} {head} {hint}".strip()
    return head, f"{sentence} For {goal.phrase}: {hint}".strip() if hint else sentence


def game_sections(result: dict) -> list[tuple[str, list[tuple[str, str]]]]:
    """The Game tab: what was captured, then the in-game settings Frametrace could read."""
    g, cap = result.get("game") or {}, result["capture"]
    d = result["analysis"]["display"]
    rows = [("Game", g.get("name") or "unknown")]
    if g.get("store"):
        rows.append(
            ("Store", f"{g['store']} app {g.get('store_id') or '?'}"
             + (f", build {g['build']}" if g.get("build") else ""))
        )  # fmt: skip
    rows += [
        ("Executable", cap["app"]),
        ("Version", g.get("version") or "unknown"),
        ("Engine", g.get("engine") or "unknown"),
        ("Graphics API", str(d.get("runtime") or "unknown").upper()),
    ]
    out = [("Captured game", rows)]
    gs = result.get("game_settings") or {}
    if gs.get("settings"):
        out.append(
            (
                "In-game settings",
                [("Read from", f"{gs.get('reader')}"), ("Source", str(gs.get("source")))]
                + [(k, str(v)) for k, v in gs["settings"]],
            )
        )
    else:
        out.append(
            (
                "In-game settings",
                [
                    (
                        "",
                        (
                            "Not read automatically for this game. The report asks the AI to get "
                            "them from you: paste them or send a screenshot of the graphics menu."
                        ),
                    )
                ],
            )
        )
    return out
