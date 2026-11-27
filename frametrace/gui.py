"""Frametrace window, in the bench-instrument design (design/frametrace-design).

Layout: a top bar with the status lamp and the one yellow button, a left rail with the
capture controls and the list of captures, and a main column for the selected capture
(verdict, scope, readouts, checks) with Report, System and Compare tabs.

All slow work (PresentMon, analysis, system info, downloads, reading traces) runs on
worker threads. Workers never touch widgets: they put (kind, payload) on self.events,
and poll() handles them on the Tk thread every 100 ms.
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from frametrace import (
    capture,
    download,
    feed,
    goals,
    hotkey,
    presentmon,
    report,
    share,
    summary,
    sysinfo,
    theme,
)
from frametrace import trace as tracemod
from frametrace.instruments import (
    Check,
    DeltaBar,
    FlatButton,
    KeyCap,
    Lamp,
    Progress,
    Readout,
    RichText,
    Scope,
    ScrollFrame,
    Segmented,
    SplitBar,
    Tabs,
    ThinScrollbar,
    frame,
    label,
    placeholder,
    rule,
    set_silk,
    silk,
    swatch,
    wheel_steps,
    wordmark,
)
from frametrace.theme import px, track

SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "Frametrace" / "settings.json"
ASSETS = Path(__file__).parent / "assets"
APP_ID = "melle62.Frametrace"
DEFAULTS = {
    "hotkey": "F10",
    "length_s": 30,
    "manual": False,
    "process_name": "",
    "benchmark": "",  # the tag the next captures get ("Mirage Benchmark"); empty: none
    "sound": True,
    "theme": "dark",
    "goal": goals.DEFAULT_GOAL,
    "target_fps": "",
    "collapsed": [],  # capture groups folded shut in the list
    "capture_open": False,  # the recording settings (hotkey, length, game, beep) unfolded
    "bases": {},  # heading key -> a run of the setup the user pinned as that heading's base
    "chosen": {},  # heading key -> a run of the setup the user keeps as their settings
    "share": None,  # share captures with the dataset: None = not asked yet
}
LENGTHS = ["10", "20", "30", "60", "90", "100", "120", "180", "300"]
RAIL_MIN, RAIL_MAX = 280, 640  # the rail's width range, 100% pixels
TABS = ["Summary", "Report", "Game", "System", "Compare"]
GOAL_LABELS = {g.label: g.key for g in goals.GOALS.values()}
NOTE_MS = 2000  # how long a confirmation stays up


def load_settings() -> dict:
    try:
        return {**DEFAULTS, **json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(settings, indent=1), encoding="utf-8")
    except OSError:
        pass


def exe_of(s: feed.Setup) -> str:
    """The exe a row's runs come from (lower case)."""
    return feed.exe(s.runs[0][1])


def _clock(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


class App:
    def __init__(self, root: tk.Tk, captures_root: Path | None = None):
        self.root = root
        self.captures_root = captures_root
        self.events: queue.Queue = queue.Queue()
        self.settings = load_settings()
        self.system: sysinfo.SystemInfo | None = None
        self.recorder: capture.Recorder | None = None
        self.listener: hotkey.HotkeyListener | None = None
        self.captures: list[tuple[Path, dict]] = []
        self.selected: list[Path] = []
        self.traces: dict[Path, tracemod.Trace | None] = {}
        self.loading: set[Path] = set()
        self.setup_issue: tuple[str, str, list] | None = None  # (level, text, buttons)
        self.capture_error: str | None = None
        self.confirm: tuple[str, list] | None = None  # (text, buttons): a question in the banner
        self.rail_order: list[Path] = []  # setups as the list shows them, for the arrow keys
        self.feed: list[feed.Heading] = []  # the list: headings of setups (frametrace.feed)
        self.setups: dict[Path, feed.Setup] = {}  # every run's folder -> its setup
        self.profile_key: str | None = None  # a heading whose game profile is shown
        self.drag: dict | None = None  # a row being dragged in the list
        self.drop_targets: dict = {}  # list widgets a dragged row can land on
        self.record_info: dict = {}
        self.note_job: str | None = None
        self.poll_job: str | None = None
        self.closed = False
        self.pm_status = ("idle", "PresentMon", "checking")
        self.trace_status = ("idle", "Trace access", "checking")
        self.sharer = share.Sharer()
        self.share_busy = False  # a sync runs on a worker thread
        self.share_again = False  # something changed while it ran
        self.share_status = self._share_status()

        theme.set_scale(root)
        root.title("Frametrace")
        w, h = px(1200), px(820)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w, h = min(w, int(sw * 0.92)), min(h, int(sh * 0.88))
        root.geometry(f"{w}x{h}")
        root.minsize(min(px(1000), w), min(px(680), h))
        self._set_icon()
        # the native frame exists only once the window is mapped (and again after restore)
        root.bind(
            "<Map>",
            lambda e: e.widget is root and theme.set_title_bar(root, self.t.dark, self.t.c),
            add="+",
        )
        self.fonts = theme.make_fonts(root)
        # state shared by both themes: the variables survive a rebuild
        self.hotkey_var = tk.StringVar(value=self.settings["hotkey"])
        self.manual_var = tk.BooleanVar(value=self.settings["manual"])
        self.length_var = tk.StringVar(value=str(self.settings["length_s"]))
        self.process_var = tk.StringVar(value=self.settings["process_name"])
        self.benchmark_var = tk.StringVar(value=self.settings.get("benchmark") or "")
        self.sound_var = tk.BooleanVar(value=self.settings["sound"])
        self.theme_var = tk.StringVar(value=self.settings.get("theme", "dark"))
        self.goal_var = tk.StringVar(value=goals.get(self.settings.get("goal")).label)
        self.target_var = tk.StringVar(value=str(self.settings.get("target_fps") or ""))
        self.share_var = tk.BooleanVar(value=self.sharing())
        self.hotkey_note = ("", "text3")

        self.build()
        self.manual_var.trace_add("write", lambda *_: self._paint_length())
        self._bind_keys()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        threading.Thread(target=self._load_system, daemon=True).start()
        self.check_setup()
        self.refresh_history(select_first=True)
        self.kick_share()
        self.poll_job = root.after(100, self.poll)

    def _set_icon(self) -> None:
        try:
            images = [tk.PhotoImage(file=str(ASSETS / f"icon-{s}.png")) for s in (256, 48, 32, 16)]
            self.root.iconphoto(True, *images)
            self._icons = images  # Tk keeps only a reference
        except (tk.TclError, OSError):
            pass

    def _bind_keys(self) -> None:
        r = self.root
        r.bind_all("<Control-c>", self._key_copy, add="+")
        r.bind_all("<Control-o>", lambda _e: self.open_selected(), add="+")
        r.bind_all("<Control-Tab>", lambda _e: (self.tabs.cycle(1), "break")[1], add="+")
        for seq in ("<Control-Shift-Tab>", "<Control-ISO_Left_Tab>"):
            try:
                r.bind_all(seq, lambda _e: (self.tabs.cycle(-1), "break")[1], add="+")
            except tk.TclError:  # ISO_Left_Tab is an X11 keysym
                pass
        r.bind_all("<Up>", lambda e: self._key_move(e, -1), add="+")
        r.bind_all("<Down>", lambda e: self._key_move(e, 1), add="+")
        r.bind_all("<F2>", lambda e: self._key_selected(e, self.rename_capture), add="+")
        r.bind_all("<Delete>", lambda e: self._key_all(e, self.ask_delete), add="+")
        for seq in ("<Control-g>", "<Control-G>"):
            r.bind_all(seq, lambda e: self._key_all(e, self.ask_group), add="+")
        r.bind_all("<Escape>", self._key_escape, add="+")

    @staticmethod
    def _typing(widget) -> bool:
        return isinstance(widget, (tk.Entry, ttk.Entry, ttk.Combobox, tk.Text)) and not isinstance(
            widget, RichText
        )

    def _key_copy(self, e) -> str | None:
        w = e.widget
        if self._typing(w):
            try:  # let a text field copy its own selection
                if (
                    w.selection_present()
                    if hasattr(w, "selection_present")
                    else w.tag_ranges("sel")
                ):
                    return None
            except tk.TclError:
                pass
        self.copy_shown()
        return "break"

    def _key_selected(self, e, action) -> str | None:
        """F2 / Delete on the selected capture, unless a text field has the keys."""
        if self._typing(e.widget) or not self.selected:
            return None
        action(self.selected[-1])
        return "break"

    def _key_all(self, e, action) -> str | None:
        """Delete / Ctrl+G on every selected row's runs, unless a text field has the keys."""
        if self._typing(e.widget) or not self._in_main(e) or not self.selected or self.profile_key:
            return None
        action(self.selected_folders())
        return "break"

    def _key_escape(self, e) -> str | None:
        """Esc drops a multiple selection back to the row clicked last."""
        if self._typing(e.widget) or not self._in_main(e) or len(self.selected) < 2 or self.confirm:
            return None
        self.select(self.selected[-1], add=False)
        return "break"

    def _in_main(self, e) -> bool:
        """The key went to the main window, not a dialog over it."""
        try:
            return e.widget.winfo_toplevel() is self.root
        except (AttributeError, KeyError, tk.TclError):
            return False

    def selected_rows(self) -> list[feed.Setup]:
        return [self.setups[k] for k in self.selected if k in self.setups]

    def selected_folders(self) -> list[Path]:
        """Every run of the selected rows, once (a bundle and one of its runs can both be
        selected)."""
        out: list[Path] = []
        for r in self.selected_rows():
            out += [f for f in r.folders if f not in out]
        return out

    def _runs_of(self, folder: Path) -> list[Path]:
        s = self.setup_for(folder)
        return s.folders if s else [folder]

    def _key_move(self, e, step: int) -> str | None:
        if self._typing(e.widget) or not self.captures:
            return None
        folders = self.rail_order or [f for f, _ in self.captures]
        cur = self.selected[-1] if self.selected else None
        i = folders.index(cur) + step if cur in folders else 0
        if 0 <= i < len(folders):
            self.select(folders[i], add=False)
        return "break"

    # --- building -----------------------------------------------------------------------------

    def build(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.t = t = theme.apply(self.root, self.settings.get("theme", "dark"), self.fonts)
        theme.set_title_bar(self.root, t.dark, t.c)  # a rebuild: the window is already shown

        self._build_topbar()
        self.progress = tk.Canvas(
            self.root, height=px(2), bg=t.c["background"], highlightthickness=0, bd=0
        )
        self.progress.pack(fill="x")
        rule(self.root, t).pack(fill="x")
        body = frame(self.root, t)
        body.pack(fill="both", expand=True)
        self._build_rail(body)
        self._build_sash(body)
        self._build_main(body)
        self.render_rail()
        self.render_setup()
        self.render_main()
        self.set_status()

    def _build_topbar(self) -> None:
        t = self.t
        bar = frame(self.root, t, height=px(52))
        bar.pack(fill="x")
        bar.pack_propagate(False)
        wordmark(bar, t).pack(side="left", padx=(px(20), 0))
        rule(bar, t, vertical=True).pack(side="left", fill="y", padx=px(24), pady=px(14))
        self.status_lamp = Lamp(bar, t, "idle")
        self.status_lamp.pack(side="left")
        self.status_word = silk(bar, t, "Ready", fg="text1")
        self.status_word.pack(side="left", padx=(px(8), px(12)))
        self.status_hint = frame(bar, t)
        self.status_hint.pack(side="left")

        self.start_btn = FlatButton(
            bar, t, "Start capture", self.toggle_capture, "primary", key=self.hotkey_var.get()
        )
        self.start_btn.pack(side="right", padx=(px(16), px(16)))
        self.theme_var.set(t.name)
        Segmented(
            bar, t, [("Dark", "dark"), ("Light", "light")], self.theme_var, self.toggle_theme
        ).pack(side="right")

    def default_rail_width(self) -> int:
        """A fifth of the screen (in 100% pixels), within 320 to 440: long run names get room
        on a big monitor without crowding a laptop."""
        screen = self.root.winfo_screenwidth() / theme.SCALE
        return int(max(320, min(440, screen * 0.2)))

    def _build_rail(self, body: tk.Frame) -> None:
        t = self.t
        logical = int(self.settings.get("rail_width") or self.default_rail_width())
        self.rail_w = px(max(RAIL_MIN, min(RAIL_MAX, logical)))
        rail = frame(body, t, width=self.rail_w)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)
        self.rail = rail

        # recording settings are set once: they fold away under their own section title, with a
        # one-line summary. (The goal isn't here: it only shapes the text for the AI, so it sits
        # by the Copy button.)
        sec = frame(rail, t)
        sec.pack(fill="x", padx=px(16), pady=(px(14), px(12)))
        key_w = px(12) + max(
            t.fonts["body_sm"].measure(w) for w in ("Hotkey", "Length", "Game", "Benchmark")
        )
        fold = tk.Frame(sec, bg=t.c["background"], cursor="hand2")
        fold.pack(fill="x")
        self.fold_chev = frame(fold, t, width=px(10), height=px(10))
        self.fold_chev.pack(side="left", padx=(0, px(8)))
        fold_name = silk(fold, t, "Recording")
        fold_name.pack(side="left")
        self.fold_sum = label(fold, t, "", font="mono_xs", fg="text3", anchor="e")
        self.fold_sum.pack(side="right")
        for w in (fold, self.fold_chev, fold_name, self.fold_sum):
            w.bind("<Button-1>", lambda _e: self.toggle_capture_settings())
        # the benchmark is the one recording setting that changes with the scene: it stays open
        # under RECORDING's title while the rest folds. Type one, or pick a tag a capture has
        bench = frame(sec, t)
        bench.pack(fill="x", pady=(px(8), 0))
        bench.columnconfigure(0, minsize=key_w)
        bench.columnconfigure(1, weight=1)
        label(bench, t, "Benchmark", fg="text2").grid(row=0, column=0, sticky="w")
        self.benchmark_box = ttk.Combobox(
            bench,
            textvariable=self.benchmark_var,
            values=self.benchmark_tags(),
            postcommand=self._fill_benchmarks,
            font=t.fonts["body_sm"],
        )
        self.benchmark_box.grid(row=0, column=1, sticky="ew")
        self.benchmark_box.bind("<<ComboboxSelected>>", lambda _e: self.apply_benchmark())
        self.benchmark_box.bind("<Return>", lambda _e: self.apply_benchmark())
        self.benchmark_box.bind("<FocusOut>", lambda _e: self.apply_benchmark(), add="+")
        placeholder(
            self.benchmark_box, t, self.benchmark_var, "e.g. Mirage Benchmark", font="body_sm"
        )
        self.capture_more = frame(sec, t)
        grid = frame(self.capture_more, t)
        grid.pack(fill="x", pady=(px(4), 0))
        grid.columnconfigure(0, minsize=key_w)
        grid.columnconfigure(1, weight=1)

        label(grid, t, "Hotkey", fg="text2").grid(row=0, column=0, sticky="w", pady=px(4))
        combo = ttk.Combobox(
            grid,
            textvariable=self.hotkey_var,
            values=hotkey.SUGGESTED,
            width=12,
            font=t.fonts["mono_sm"],
        )
        combo.grid(row=0, column=1, sticky="ew", pady=px(4))
        combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_hotkey())
        combo.bind("<Return>", lambda _e: self.apply_hotkey())
        combo.bind("<FocusOut>", lambda _e: self.apply_hotkey())
        self.hotkey_label = label(
            grid, t, "", font="caption", fg="warning", wraplength=px(190), justify="left"
        )
        self.hotkey_label.grid(row=1, column=1, sticky="w", pady=(0, px(4)))
        self._show_hotkey_note()

        label(grid, t, "Length", fg="text2").grid(row=2, column=0, sticky="w", pady=px(4))
        ln = frame(grid, t)
        ln.grid(row=2, column=1, sticky="ew", pady=px(4))
        Segmented(ln, t, [("Fixed", False), ("Manual", True)], self.manual_var, self.save).pack(
            side="left"
        )
        self.length_box = ttk.Combobox(
            ln, textvariable=self.length_var, values=LENGTHS, width=4, font=t.fonts["mono_sm"]
        )
        self.length_box.pack(side="left", padx=(px(6), px(4)), fill="x", expand=True)
        self.length_box.bind("<<ComboboxSelected>>", lambda _e: self.save())
        self.length_box.bind("<Return>", lambda _e: self.save())
        self.length_box.bind("<FocusOut>", lambda _e: self.save())
        label(ln, t, "s", font="mono_sm", fg="text3").pack(side="left")
        self._paint_length()

        label(grid, t, "Game", fg="text2").grid(row=3, column=0, sticky="w", pady=px(4))
        entry = ttk.Entry(
            grid, textvariable=self.process_var, style="Mono.TEntry", font=t.fonts["mono_sm"]
        )
        entry.grid(row=3, column=1, sticky="ew", pady=px(4))
        entry.bind("<FocusOut>", lambda _e: self.save(), add="+")
        entry.bind("<Return>", lambda _e: self.save(), add="+")
        placeholder(entry, t, self.process_var, "empty = auto-detect")
        Check(self.capture_more, t, "Beep on start and stop", self.sound_var, self.save).pack(
            anchor="w", pady=(px(8), 0)
        )
        if self.sharer.available:
            Check(
                self.capture_more, t, "Share captures with the dataset", self.share_var,
                self.apply_share,
            ).pack(anchor="w", pady=(px(6), 0))  # fmt: skip
        self._paint_capture_more()

        rule(rail, t).pack(fill="x")
        foot = frame(rail, t)
        foot.pack(side="bottom", fill="x", padx=px(16), pady=px(12))
        self.foot = foot
        rule(rail, t).pack(side="bottom", fill="x")

        # the list's header: CAPTURES and its count, then the column heads over the rows'
        # value and change columns (right edges matched to the rows below)
        head = frame(rail, t)
        head.pack(fill="x", padx=(px(16), px(16)), pady=(px(16), px(4)))
        silk(head, t, "Captures").pack(side="left")
        self.count_label = label(head, t, "", font="mono_xs", fg="text4")
        self.count_label.pack(side="left", padx=(px(6), 0))
        _, delta_w = self._rail_widths()
        self.col_delta_name = silk(head, t, "vs base", fg="text4")
        # as wide as the rows' change column, or the head if that's wider; the value head
        # then still ends where the rows' value column ends
        wide = max(delta_w, self.col_delta_name.winfo_reqwidth())
        self.col_pad = (max(0, px(10) - (wide - delta_w)), px(11))
        self.col_delta_name.destroy()
        tall = t.fonts["label"].metrics("linespace")
        self.col_delta = frame(head, t, width=wide, height=tall)
        self.col_delta.pack(side="right", padx=self.col_pad)
        self.col_delta.pack_propagate(False)
        self.col_delta_name = silk(self.col_delta, t, "vs base", fg="text4")
        self.col_delta_name.pack(side="right")
        self.col_value = silk(head, t, "", fg="text4")
        self.col_value.pack(side="right")
        self.drag_hint = label(head, t, "", font="mono_xs", fg="text1", anchor="e")
        self.list = ScrollFrame(rail, t)
        self.list.pack(fill="both", expand=True, padx=(px(8), px(2)))

    def _build_sash(self, body: tk.Frame) -> None:
        """The rail's right edge: a 1px rule in a 7px grip. Drag it to widen the list (long run
        names need it), double-click for the default width. The width is remembered."""
        t = self.t
        sash = tk.Frame(body, bg=t.c["background"], width=px(7), cursor="sb_h_double_arrow")
        sash.pack(side="left", fill="y")
        line = tk.Frame(sash, bg=t.c["border"], width=1, cursor="sb_h_double_arrow")
        line.place(relx=0.5, y=0, relheight=1)
        for w in (sash, line):
            w.bind("<ButtonPress-1>", self._sash_press)
            w.bind("<B1-Motion>", self._sash_move)
            w.bind("<ButtonRelease-1>", self._sash_release)
            w.bind("<Double-1>", lambda _e: self.set_rail_width(None))
        self.sash = sash

    def _sash_press(self, e) -> None:
        self._sash_from = (e.x_root, self.rail_w)

    def _sash_move(self, e) -> None:
        start = getattr(self, "_sash_from", None)
        if not start:
            return
        most = min(px(RAIL_MAX), max(px(RAIL_MIN), self.root.winfo_width() // 2))
        self.rail_w = max(px(RAIL_MIN), min(most, start[1] + e.x_root - start[0]))
        self.rail.configure(width=self.rail_w)

    def _sash_release(self, _e) -> None:
        if getattr(self, "_sash_from", None):
            self._sash_from = None
            self.set_rail_width(round(self.rail_w / theme.SCALE))

    def set_rail_width(self, logical: int | None) -> None:
        """Remember the rail's width (100% pixels; None: the default) and redraw the list."""
        if logical is None:
            self.settings.pop("rail_width", None)
            logical = self.default_rail_width()
        else:
            self.settings["rail_width"] = int(max(RAIL_MIN, min(RAIL_MAX, logical)))
        save_settings(self.settings)
        self.rail_w = px(max(RAIL_MIN, min(RAIL_MAX, logical)))
        self.rail.configure(width=self.rail_w)
        self.render_rail()

    def benchmark_tags(self) -> list[str]:
        """Benchmark tags to pick from: the one being typed, then every tag a capture has,
        the newest used first."""
        tags = feed.benchmarks(getattr(self, "captures", []) or [])
        mine = (self.settings.get("benchmark") or "").strip()
        if mine and mine.casefold() not in {g.casefold() for g in tags}:
            tags.insert(0, mine)
        return tags

    def _fill_benchmarks(self) -> None:
        try:
            self.benchmark_box.configure(values=self.benchmark_tags())
        except (tk.TclError, AttributeError):
            pass

    def apply_benchmark(self) -> None:
        """The typed or picked tag goes on the next captures. A tag that matches an existing
        one apart from case takes that one's spelling, so "mirage benchmark" stays one tag."""
        text = " ".join(self.benchmark_var.get().split())[:80]
        same = next((g for g in self.benchmark_tags() if g.casefold() == text.casefold()), None)
        if same and same != text:
            text = same
        if text != self.benchmark_var.get():
            self.benchmark_var.set(text)
        if text != (self.settings.get("benchmark") or ""):
            self.settings["benchmark"] = text
            save_settings(self.settings)
            self.set_status()
        self._fill_benchmarks()

    def _capture_summary(self) -> str:
        """The folded recording settings in one mono line: F10 · 30 s · auto."""
        length = "manual" if self.manual_var.get() else f"{self.length_seconds()} s"
        game = self.process_var.get().strip() or "auto"
        return f"{self.hotkey_var.get() or '?'} · {length} · {self._fit(game, 'mono_xs', px(70))}"

    def _paint_capture_more(self) -> None:
        """Open the recording settings when asked, or when the hotkey needs attention."""
        try:
            opened = bool(self.settings.get("capture_open")) or bool(self.hotkey_note[0])
            for child in self.fold_chev.winfo_children():
                child.destroy()
            self._chevron(self.fold_chev, not opened, "background").pack()
            if opened:
                self.capture_more.pack(fill="x")
                self.fold_sum.configure(text="")
            else:
                self.capture_more.pack_forget()
                self.fold_sum.configure(text=self._capture_summary())
        except (tk.TclError, AttributeError):
            pass

    def toggle_capture_settings(self) -> None:
        self.settings["capture_open"] = not self.settings.get("capture_open")
        save_settings(self.settings)
        self._paint_capture_more()

    def _paint_target(self) -> None:
        """The target FPS field shows only for "Hit a target FPS" (empty: the refresh rate)."""
        try:
            if self.goal_key() == "target":
                self.target_row.pack(side="left", after=self.goal_box)
            else:
                self.target_row.pack_forget()
        except (tk.TclError, IndexError, AttributeError):
            pass

    def goal_key(self) -> str:
        return GOAL_LABELS.get(self.goal_var.get(), goals.DEFAULT_GOAL)

    def target_fps(self) -> int | None:
        """The typed target, or None (the report then uses the display's refresh rate)."""
        try:
            v = int(float(self.target_var.get()))
        except ValueError:
            return None
        return v if 10 <= v <= 1000 else None

    def apply_goal(self) -> None:
        """A new goal re-renders the list, the shown capture, comparison or profile."""
        self._paint_target()
        self.save()
        self.render_rail()
        if self.current_result() or len(self.selected) == 2 or self.profile_key:
            self.render_main()

    def _paint_length(self) -> None:
        try:
            self.length_box.configure(state="disabled" if self.manual_var.get() else "normal")
        except tk.TclError:
            pass

    def _build_main(self, body: tk.Frame) -> None:
        t = self.t
        main = frame(body, t)
        main.pack(side="left", fill="both", expand=True)
        self.main = main
        gutter = (px(24), px(24))

        self.banner = frame(main, t)
        self.header = frame(main, t)
        self.header.pack(fill="x", padx=gutter, pady=(px(18), px(10)))
        self.tabs = Tabs(main, t, TABS, self.show_tab)
        self.tabs.pack(fill="x", padx=gutter)
        self.tab_hint = silk(self.tabs.extra, t, "", fg="text4")
        self.tab_hint.pack(side="right")

        actions = frame(main, t)
        actions.pack(side="bottom", fill="x", padx=gutter, pady=(px(10), px(16)))
        # the goal only shapes what the AI is asked (the report, the comparison, the profile),
        # so it's picked right where that text is copied
        silk(actions, t, "Goal").pack(side="left", padx=(0, px(8)))
        goal_box = ttk.Combobox(
            actions,
            textvariable=self.goal_var,
            values=list(GOAL_LABELS),
            state="readonly",
            font=t.fonts["body_sm"],
            width=max(len(g) for g in GOAL_LABELS),
        )
        goal_box.pack(side="left")
        goal_box.bind("<<ComboboxSelected>>", lambda _e: self.apply_goal())
        self.goal_box = goal_box
        self.target_row = frame(actions, t)
        tentry = ttk.Entry(
            self.target_row,
            textvariable=self.target_var,
            style="Mono.TEntry",
            font=t.fonts["mono_sm"],
            width=6,
        )
        tentry.pack(side="left", padx=(px(8), px(4)))
        tentry.bind("<FocusOut>", lambda _e: self.apply_goal(), add="+")
        tentry.bind("<Return>", lambda _e: self.apply_goal(), add="+")
        placeholder(tentry, t, self.target_var, "Hz")
        label(self.target_row, t, "FPS", font="mono_sm", fg="text3").pack(side="left")
        self.target_widgets = (self.target_row,)
        self.goal_rule = rule(actions, t, vertical=True)
        self.goal_rule.pack(side="left", fill="y", padx=px(16), pady=px(4))
        self._paint_target()
        self.copy_btn = FlatButton(actions, t, "Copy report", self.copy_shown, "secondary")
        self.copy_btn.pack(side="left")
        self.folder_btn = FlatButton(actions, t, "Open folder", self.open_selected, "ghost")
        self.folder_btn.pack(side="left", padx=(px(8), 0))
        self.compare_btn = FlatButton(
            actions, t, "Compare", lambda: self.tabs.select("Compare"), "ghost"
        )
        self.compare_btn.pack(side="left", padx=(px(4), 0))
        self.note = frame(actions, t)
        self.note.pack(side="right")

        # the thin scrollbar sits in the right gutter, so content keeps a 24 px edge
        self.pages = frame(main, t)
        self.pages.pack(fill="both", expand=True, padx=(px(24), px(10)), pady=(px(12), 0))
        self.page_summary = ScrollFrame(self.pages, t)
        self._build_summary(self.page_summary.inner)
        self.page_text = frame(self.pages, t)
        well = frame(self.page_text, t, border="border")
        sb = ThinScrollbar(self.page_text, t, lambda *a: self.text.yview(*a))
        sb.pack(side="right", fill="y", padx=(px(8), 0))
        well.pack(side="left", fill="both", expand=True)
        self.text = tk.Text(
            well, wrap="word", font=t.fonts["mono_sm"], bg=t.c["background"], fg=t.c["text1"],
            insertbackground=t.c["text1"], selectbackground=t.c["accent_subtle"],
            selectforeground=t.c["text1"], inactiveselectbackground=t.c["surface2"],
            relief="flat", bd=0, padx=px(16), pady=px(14), highlightthickness=0,
            spacing1=px(2), spacing2=px(2), spacing3=px(2), cursor="arrow",
        )  # fmt: skip
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(fill="both", expand=True)
        self.text.bind(
            "<MouseWheel>",
            lambda e: (self.text.yview_scroll(wheel_steps(e) * 3, "units"), "break")[1],
        )
        self.text.tag_configure("head", foreground=t.c["text1"], font=t.fonts["mono_head"])
        self.text.tag_configure("title", foreground=t.c["text1"], font=t.fonts["mono_head"])
        self.text.tag_configure("warn", foreground=t.c["warning"], font=t.fonts["mono_head"])
        self.text.tag_configure("ok", foreground=t.c["success"], font=t.fonts["mono_head"])
        self.text.tag_configure("dim", foreground=t.c["text3"])
        self.page_system = ScrollFrame(self.pages, t)
        self.page_game = ScrollFrame(self.pages, t)
        self.page_compare = ScrollFrame(self.pages, t)
        self.page_profile = ScrollFrame(self.pages, t)
        self.compare_scope: Scope | None = None
        self.shown = "Summary"
        self.shown_text = ""

    def _build_summary(self, page: tk.Frame) -> None:
        t = self.t
        # verdict: headline, one sentence, and the split bar (or the capture progress)
        v = frame(page, t, "surface1", border="border")
        v.pack(fill="x", pady=(0, px(8)))
        v.columnconfigure(0, weight=1)
        self.verdict_head = frame(v, t, "surface1")
        self.verdict_head.grid(row=0, column=0, sticky="w", padx=px(16), pady=(px(14), px(4)))
        self.verdict_text = RichText(v, t, "", font="body_sm", mono="mono_sm")
        self.verdict_text.grid(
            row=1, column=0, sticky="ew", padx=(px(16), px(24)), pady=(0, px(14))
        )
        side = frame(v, t, "surface1", width=px(330))
        side.grid(row=0, column=1, rowspan=2, sticky="sew", padx=px(16), pady=px(16))
        v.columnconfigure(1, minsize=px(330))
        self.split_box = frame(side, t, "surface1")
        self.split = SplitBar(self.split_box, t)
        self.split.pack(fill="x")
        self.split_legend = frame(self.split_box, t, "surface1")
        self.split_legend.pack(fill="x", pady=(px(8), 0))
        self.rec_progress = Progress(side, t)
        self.split_box.pack(fill="x")

        # scope
        s = frame(page, t, "surface1", border="border")
        s.pack(fill="x", pady=(0, px(8)))
        sh = frame(s, t, "surface1")
        sh.pack(fill="x", padx=px(16), pady=(px(12), px(10)))
        self.scope_title = silk(sh, t, "Frame time", bg="surface1")
        self.scope_title.pack(side="left")
        self.scope_scale = label(sh, t, "", font="mono_xs", fg="text3", bg="surface1")
        self.scope_scale.pack(side="left", padx=(px(12), 0))
        self.channel_chips: dict[str, tuple] = {}
        for key, name in (("ch3", "CH3 CPU"), ("ch2", "CH2 GPU"), ("ch1", "CH1 FRAME")):
            self._channel_toggle(sh, key, name).pack(side="right", padx=(px(6), 0))
        self.scope = Scope(s, t, height=184)
        self.scope.pack(fill="x", padx=px(16), pady=(0, px(16)))

        # readouts
        row = frame(page, t)
        row.pack(fill="x", pady=(0, px(8)))
        self.readouts: list[Readout] = []
        for i in range(5):
            row.columnconfigure(i, weight=1, uniform="ro")
            r = Readout(
                row,
                t,
                ["Average", "1% low", "CPU-side 1% low", "PC latency", "P95 latency"][i],
                "ch1" if i == 0 else None,
            )
            r.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else px(8), 0))
            self.readouts.append(r)

        # checks and details
        low = frame(page, t)
        low.pack(fill="x", pady=(0, px(8)))
        low.columnconfigure(0, weight=4, uniform="low")
        low.columnconfigure(1, weight=3, uniform="low")
        self.low_row = low
        self.runs_panel = frame(page, t, "surface1", border="border")  # packed for stacks
        self.checks_panel = frame(low, t, "surface1", border="border")
        self.checks_panel.grid(row=0, column=0, sticky="nsew")
        self.details_panel = frame(low, t, "surface1", border="border")
        self.details_panel.grid(row=0, column=1, sticky="nsew", padx=(px(8), 0))

    def _channel_toggle(self, parent, key: str, name: str) -> tk.Frame:
        t = self.t
        f = tk.Frame(parent, highlightthickness=1, cursor="hand2", padx=px(7), pady=px(3))
        sw = swatch(f, t, key)
        sw.pack(side="left", padx=(0, px(6)))
        lab = label(f, t, name, font="mono_xs", bg="surface2")
        lab.pack(side="left")
        self.channel_chips[key] = (f, sw, lab)

        def flip(_e=None):
            if self.scope.has(key):
                self.scope.toggle(key)
                self._paint_channels()

        for w in (f, sw, lab):
            w.bind("<Button-1>", flip)
        return f

    def _paint_channels(self) -> None:
        """Lit when shown, dim when hidden, and inert when the capture has no data for it."""
        c = self.t.c
        for key, (f, sw, lab) in self.channel_chips.items():
            has = self.scope.has(key)
            on = has and self.scope.channels[key]
            bg = c["surface2"] if on else c["surface1"]
            f.configure(
                bg=bg,
                highlightbackground=c["text3" if on else "border_visible"],
                cursor="hand2" if has else "arrow",
            )
            lab.configure(bg=bg, fg=c["text1" if on else "text3" if has else "text4"])
            sw.configure(bg=c[key] if on else c["text4" if has else "surface3"])

    # --- rendering ----------------------------------------------------------------------------

    def render_rail(self) -> None:
        t = self.t
        inner = self.list.inner
        for child in inner.winfo_children():
            child.destroy()
        self._rebuild_feed()
        self.count_label.configure(text=str(len(self.captures)))
        self.rail_metric = next((h.metric for h in self.feed if h.metric), None)
        self.col_value.configure(text=track(feed.metric_column(self.rail_metric).upper()))
        self._show_drag_hint(None)
        self.rail_order = []
        self.drop_targets: dict[tk.Widget, tuple] = {}
        if not self.captures:
            box = frame(inner, t)
            box.pack(fill="x", padx=px(8), pady=px(8))
            label(box, t, "No captures yet.", fg="text2").pack(anchor="w")
            label(
                box, t, "Each capture is saved here, newest first.", font="caption", fg="text3"
            ).pack(anchor="w", pady=(px(2), 0))
        folded = set(self.settings.get("collapsed") or [])
        opened = set(self.settings.get("open_bundles") or [])
        for i, h in enumerate(self.feed):
            shut = h.title in folded
            self._group_head(inner, h, shut, first=i == 0)
            if shut:
                continue
            for s in h.setups:
                self.rail_order.append(s.key)
                self._rail_row(inner, h, s)
                if s.is_bundle and s.bundle in opened:
                    for i, c in enumerate(reversed(s.children)):  # newest first, like the list
                        self.rail_order.append(c.key)
                        self._rail_row(inner, h, c, last=i == s.count - 1)
        self._render_foot()

    # the list's columns: name | count | value | change against the base
    def _rail_widths(self) -> tuple[int, int]:
        """(value, change): wide enough for 1,000 FPS and a two-digit change."""
        sm, xs = self.t.fonts["mono_sm"], self.t.fonts["mono_xs"]
        return sm.measure("0000.0"), px(13) + xs.measure("-00.0%")

    def _group_head(self, parent, h: feed.Heading, shut: bool, first: bool = False) -> None:
        """A heading: the list's strongest line. Chevron (folds it), the game or group name in
        Plex Sans Medium (opens its profile, and looks selected while the profile is shown),
        the row count in mono; the metric only when it differs from the list's column head."""
        t = self.t
        shown = self.profile_key == h.key
        bg = "surface2" if shown else "background"
        head = tk.Frame(parent, bg=t.c[bg], cursor="hand2")
        head.pack(fill="x", pady=(px(4) if first else px(16), px(2)))
        edge = tk.Frame(head, width=2, bg=t.c["accent"] if shown else t.c[bg])
        edge.pack(side="left", fill="y")
        chev = self._chevron(head, shut, bg)
        chev.pack(side="left", padx=(px(6), px(8)))
        name = label(head, t, self._fit(h.title, "group", self.rail_w - px(110)), font="group",
                     bg=bg)  # fmt: skip
        name.pack(side="left", pady=px(5))
        own = h.metric and h.metric != getattr(self, "rail_metric", h.metric)
        if own:  # this heading's runs can't show the list's metric (no Reflex markers, say)
            right = silk(head, t, feed.metric_column(h.metric), bg=bg, fg="text4")
        else:
            right = label(head, t, str(len(h.setups)), font="mono_xs", fg="text4", bg=bg)
        right.pack(side="right", padx=(0, px(11)))
        chev.bind("<Button-1>", lambda _e, k=h.title: self.toggle_group(k))
        for wdg in (head, edge, name, right):
            wdg.bind("<Button-1>", lambda _e, k=h.key: self.open_profile(k))
        for wdg in (head, edge, chev, name, right):
            wdg.bind("<Button-3>", lambda e, hh=h: self._group_menu(e, hh))
        self.drop_targets[head] = ("heading", h, [name])

    def _chevron(self, parent, shut: bool, bg: str, color: str = "text3") -> tk.Canvas:
        """10px chevron, 1.5px stroke, square caps: right when shut, down when open."""
        t = self.t
        size = px(10)
        chev = tk.Canvas(parent, width=size, height=size, bg=t.c[bg], highlightthickness=0, bd=0)
        c, w = px(5), px(3)
        pts = (
            (c - 1, c - w, c + w - 1, c, c - 1, c + w)
            if shut
            else (c - w, c - 1, c, c + w - 1, c + w, c - 1)
        )
        chev.create_line(*pts, fill=t.c[color], width=max(1, px(1.5)), capstyle="projecting")
        return chev

    def toggle_group(self, heading: str) -> None:
        folded = list(self.settings.get("collapsed") or [])
        if heading in folded:
            folded.remove(heading)
        else:
            folded.append(heading)
        self.settings["collapsed"] = folded
        save_settings(self.settings)
        self.render_rail()

    def toggle_bundle(self, bundle: str, open_: bool | None = None) -> None:
        """Open a bundle to show its runs (as a tree under it), or close it."""
        opened = list(self.settings.get("open_bundles") or [])
        now = bundle in opened
        if open_ is None:
            open_ = not now
        if open_ and not now:
            opened.append(bundle)
        elif not open_ and now:
            opened.remove(bundle)
        self.settings["open_bundles"] = opened
        save_settings(self.settings)
        self.render_rail()

    def _wrap(self, text: str, font: str, width: int, lines: int = 2) -> list[str] | None:
        """Wrap text at spaces into at most `lines` lines of `width`; None if it won't fit."""
        f = self.t.fonts[font]
        out, cur = [], ""
        for word in text.split(" "):
            trial = f"{cur} {word}" if cur else word
            if f.measure(trial) <= width:
                cur = trial
                continue
            if not cur or f.measure(word) > width:
                return None  # a word longer than a line
            out.append(cur)
            cur = word
        out.append(cur)
        return out if len(out) <= lines else None

    def _row_lines(self, s: feed.Setup, font: str, width: int) -> list[str]:
        """A row's name as one line, or two when it's long (benchmark names often carry the
        settings). Only when two lines aren't enough is it shortened: a change drops its old
        value first, then the last line ends with an ellipsis."""
        name = s.name
        if self.t.fonts[font].measure(name) <= width:
            return [name]
        most = 3 if s.kind in feed.TYPED else 2  # the user's own names get a third line
        change = s.kind in ("settings", "system")
        wrapped = self._wrap(self._keep_together(name) if change else name, font, width, most)
        if wrapped:
            return [w.replace("\u00a0", " ") for w in wrapped]
        short = self._row_name(s, font, 10**6)  # the change without its old value
        if short != name:
            left, _, right = short.partition(" → ")
            for cand in (short, f"{left} → {right.replace(' more', '')}"):
                wrapped = self._wrap(self._keep_together(cand), font, width)
                if wrapped:
                    return [w.replace("\u00a0", " ") for w in wrapped]
        out, rest = [], name
        f = self.t.fonts[font]
        while rest and len(out) < most - 1:  # fill each line; the last one ends with "…"
            first, tail = rest, ""
            while first and f.measure(first) > width:
                first, _, word = first.rpartition(" ")
                tail = f"{word} {tail}".strip()
            if not first:  # one word longer than a line
                break
            out.append(first)
            rest = tail
        return [*out, self._fit(rest, font, width)] if rest else out

    @staticmethod
    def _keep_together(name: str) -> str:
        """A change name with no-break spaces in "4 → 2" and "+2 more", so a wrap falls only
        between the key and its values ("msaa_samples" / "4 → 2")."""
        left, arrow, right = name.partition(" → ")
        if not arrow:
            return name
        key, _, old = left.rpartition(" ")
        nb = "\u00a0"
        return f"{key} {old}{nb}→{nb}{right.replace(' ', nb)}" if key else name

    def _row_name(self, s: feed.Setup, font: str, width: int) -> str:
        """A row's name cut to fit. A change keeps its new value: the old one goes first
        ("shadow_quality → 1"), then "+2 more" shortens to "+2", then the key is cut."""
        name = s.name
        if s.kind not in ("settings", "system"):
            return self._fit(name, font, width)
        if width < 10**6 and self.t.fonts[font].measure(name) <= width:
            return name
        left, arrow, right = name.partition(" → ")
        if arrow:
            key = left.rsplit(" ", 1)[0] if " " in left else left
            for tail in (right, right.replace(" more", "")):
                if self.t.fonts[font].measure(f"{key} → {tail}") <= width:
                    return f"{key} → {tail}"
            tail = right.replace(" more", "")
            room = width - self.t.fonts[font].measure(f" → {tail}")
            return f"{self._fit(key, font, room)} → {tail}"
        return self._fit(name, font, width)

    def _fit(self, text: str, font: str, width: int) -> str:
        """Cut text to a pixel width with an ellipsis (Tk labels don't)."""
        f = self.t.fonts[font]
        if f.measure(text) <= width:
            return text
        while text and f.measure(text + "…") > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def _rail_row(self, parent, h: feed.Heading, s: feed.Setup, last: bool = False) -> None:
        """One row on one line: tree, name, ×runs, the goal's number, the change against the base.

        The tree: a heading's rows (single runs and bundles alike) sit one step in under it,
        with a guide line under the heading's chevron; an open bundle's runs sit one more step
        in, with a second guide under the bundle's chevron. A bundle's own chevron sits at its
        step, under its heading's name, like a folder in a layers panel.
        """
        t = self.t
        key = s.key
        child = s.parent is not None
        level = 2 if child else 1
        sel = key in self.selected and not self.profile_key
        bg = "surface2" if sel else "background"
        row = tk.Frame(parent, bg=t.c[bg], cursor="hand2")
        row.pack(fill="x")
        # one yellow edge: on the row the main column shows. Two compared rows both keep it
        # (A and B are both shown); in a larger selection the others get a neutral edge
        lit = sel and (len(self.selected) <= 2 or key == self.selected[-1])
        edge = tk.Frame(
            row, width=2, bg=t.c["accent" if lit else "border_visible" if sel else bg]
        )
        edge.pack(side="left", fill="y")
        value_w, delta_w = self._rail_widths()
        widgets: list[tk.Widget] = [row]

        # the name first: it decides the row's height (one line, or two when it's long)
        font = "body_sm" if s.kind in feed.TYPED else "mono_sm"  # keys and times are mono
        fg = "text3" if child else "text1" if s.kind in feed.NAMED else "text2"
        step, first = px(16), px(6)  # the heading's chevron starts 6px in
        gutter_w = first + step * level + px(18)  # then a chevron's width and an 8px gap
        count_w = t.fonts["mono_xs"].measure(s.count_text) + px(6) if s.count_text else 0
        room = (
            self.rail_w - px(10 + 14) - px(2) - gutter_w - value_w - px(4) - delta_w - px(16)
            - count_w
        )  # fmt: skip
        lines = self._row_lines(s, font, room)
        line_h = t.fonts[font].metrics("linespace")
        tall = t.fonts["mono_sm"].metrics("linespace")
        pad = px(6)
        high = line_h * len(lines) + 2 * pad  # a 28px row, or taller for a two-line name
        y0 = pad + line_h // 2  # the first line's middle: chevron, tick and numbers line up
        cell_top = pad + (line_h - tall) // 2

        # the gutter: one 16px step per level; guides at the chevron centres of the levels above
        gutter = tk.Canvas(row, width=gutter_w, height=high, bg=t.c[bg], highlightthickness=0,
                           bd=0)  # fmt: skip
        gutter.pack(side="left", anchor="n")
        widgets.append(gutter)
        line = t.c["border_visible"]
        for k in range(level):  # under the heading's chevron, then under the bundle's
            x = first + px(5) + step * k
            gutter.create_line(x, 0, x, y0 if (k == level - 1 and last) else high,
                               fill=line, width=1)  # fmt: skip
        if child:  # a tick from the bundle's guide to the run
            x = first + px(5) + step
            gutter.create_line(x, y0, gutter_w - px(2), y0, fill=line, width=1)
        if s.is_bundle:  # its chevron at its own step, under the heading's name
            opened = s.bundle in (self.settings.get("open_bundles") or [])
            c, w = first + step + px(5), px(3)
            pts = (
                (c - 1, y0 - w, c + w - 1, y0, c - 1, y0 + w)
                if not opened
                else (c - w, y0 - 1, c, y0 + w - 1, c + w, y0 - 1)
            )
            gutter.create_line(*pts, fill=t.c["text3"], width=max(1, px(1.5)),
                               capstyle="projecting")  # fmt: skip
        if sel and len(self.selected) == 2:  # A and B on the heading's guide
            mark = "A" if s.trace_folder == self.compare_pair()[0][0] else "B"
            x = first + px(5)
            gutter.create_rectangle(x - px(5), y0 - px(7), x + px(5), y0 + px(7),
                                    fill=t.c[bg], outline="")  # fmt: skip
            gutter.create_text(x, y0, text=mark, fill=t.c["text1"], font=t.fonts["mono_xs"])
        chev = None

        def cell(width: int, pad: tuple[int, int]) -> tk.Frame:
            box = tk.Frame(row, bg=t.c[bg], width=width, height=tall)
            box.pack(side="right", padx=pad, anchor="n", pady=(cell_top, 0))
            box.pack_propagate(False)
            widgets.append(box)
            return box

        # right to left: the numbers keep their columns, the name takes what's left
        delta = cell(delta_w, (px(6), px(10)))
        if child:  # a counted run: its difference from the bundle; a left-out one: a lamp
            out = s.status == "out"
            label(delta, t, "out" if out else s.change, font="mono_xs",
                  fg="text2" if out else "text3", bg=bg).pack(side="right")  # fmt: skip
            if out:
                Lamp(delta, t, "warn").pack(side="right", padx=(0, px(5)))
        elif s.status == "base":
            silk(delta, t, "Base", bg=bg, fg="text3").pack(side="right")
        elif s.status == "na":
            label(delta, t, "n/a", font="mono_xs", fg="text4", bg=bg).pack(side="right")
        elif s.status != "alone":  # the lamp carries the status, the number stays neutral
            lamp = {"better": "ok", "worse": "warn"}.get(s.status, "idle")
            tone = "text3" if s.status == "same" else "text2"
            label(delta, t, s.change, font="mono_xs", fg=tone, bg=bg).pack(side="right")
            Lamp(delta, t, lamp).pack(side="right", padx=(0, px(5)))
        num, _unit = feed.metric_text(h.metric, s.value) if h.metric else ("---", "")
        value = cell(value_w, (px(4), 0))
        dim = s.value is None or child
        label(value, t, num, font="mono_sm", fg="text3" if dim else "text1", bg=bg).pack(
            side="right"
        )
        # what the user named or changed is text1; a time (nothing named) text2; a run text3
        name = label(row, t, "\n".join(lines), font=font, bg=bg, anchor="nw", fg=fg,
                     justify="left")  # fmt: skip
        name.pack(side="left", anchor="n", pady=(pad, pad))
        widgets.append(name)
        if s.count_text:  # ×3 right after the name's first line, quiet
            cnt = label(row, t, s.count_text, font="mono_xs", bg=bg, fg="text3")
            xs = t.fonts["mono_xs"].metrics("linespace")
            cnt.pack(side="left", anchor="n", padx=(px(6), 0), pady=(pad + (line_h - xs) // 2, 0))
            widgets.append(cnt)

        def paint(hover: bool) -> None:
            if sel or self.drag:
                return
            col = t.c["surface2" if hover else "background"]
            for wdg in widgets:
                wdg.configure(bg=col)
                for c in wdg.winfo_children():
                    if not isinstance(c, Lamp):
                        c.configure(bg=col)
            edge.configure(bg=col)

        def press(e, k=key) -> None:
            # a bundle's chevron (in the gutter) opens it; anywhere else starts a click or drag
            if e.widget is gutter and s.is_bundle and abs(e.x - (first + step + px(5))) <= px(9):
                self.drag = None
                self.toggle_bundle(s.bundle)
                return
            self._drag_start(e, k)

        for wdg in [*widgets, *(c for w in widgets for c in w.winfo_children())]:
            if wdg is chev:
                continue
            wdg.bind("<ButtonPress-1>", press)
            wdg.bind("<B1-Motion>", self._drag_move)
            wdg.bind("<ButtonRelease-1>", self._drag_end)
            wdg.bind("<Control-Button-1>", lambda _e, k=key: self.select(k, add=True))
            wdg.bind("<Shift-Button-1>", lambda _e, k=key: self.select(k, add=True))
            wdg.bind("<Double-1>", lambda _e, f=s.folder: _open(f))
            wdg.bind("<Button-3>", lambda e, hh=h, ss=s: self._row_menu(e, hh, ss))
            wdg.bind("<Enter>", lambda _e: paint(True), add="+")
            wdg.bind("<Leave>", lambda _e: paint(False), add="+")
        self.drop_targets[row] = ("row", s, [row, edge])

    # --- dragging rows: bundle, unbundle, move between groups ------------------------------------

    def _drag_start(self, e, key: Path) -> None:
        self.drag = {"key": key, "x": e.x_root, "y": e.y_root, "moving": False, "lit": None}

    def _drop_target(self, x: int, y: int) -> tuple | None:
        w = self.root.winfo_containing(x, y)
        while w is not None:
            if w in self.drop_targets:
                return self.drop_targets[w]
            w = getattr(w, "master", None)
        return None

    def _drag_move(self, e) -> None:
        d = self.drag
        if not d:
            return
        if not d["moving"]:
            if abs(e.x_root - d["x"]) + abs(e.y_root - d["y"]) < px(6):
                return
            d["moving"] = True
        target = self._drop_target(e.x_root, e.y_root)
        if d["lit"] is not None and (target is None or target[1] is not d["lit"][0]):
            self._light(None)
        action = self.drop_action(d["key"], target) if target else None
        if action and (d["lit"] is None or d["lit"][0] is not target[1]):
            self._light(target)
        self._show_drag_hint(action[0] if action else "Drop on a run, a bundle or a heading")

    def _show_drag_hint(self, text: str | None) -> None:
        """While a row is dragged, the column heads make room for what the drop will do."""
        try:
            if text:
                self.col_value.pack_forget()
                self.col_delta.pack_forget()
                self.drag_hint.configure(
                    text=self._fit(text, "mono_xs", self.rail_w - px(110))
                )
                self.drag_hint.pack(side="right")
            else:
                self.drag_hint.pack_forget()
                if not self.col_delta.winfo_manager():
                    self.col_delta.pack(side="right", padx=self.col_pad)
                    self.col_value.pack(side="right")
        except (tk.TclError, AttributeError):
            pass

    def _light(self, target: tuple | None) -> None:
        """Show (or clear) where a dragged row would land: a 1px yellow ring around a row (the
        focus colour), or a heading's name in yellow."""
        d, t = self.drag, self.t
        if d is None:
            return
        for w, opts in d.get("undo") or []:
            try:
                w.configure(**opts)
            except tk.TclError:
                pass
        for bar in d.get("bars") or []:
            bar.destroy()
        d["undo"], d["bars"], d["lit"] = [], [], None
        if target is None:
            return
        kind, thing, parts = target
        if kind == "heading":
            for w in parts:
                d["undo"].append((w, {"fg": w.cget("fg")}))
                w.configure(fg=t.c["accent"])
        else:  # a 1px yellow ring laid over the row's edges (no layout shift, guides unbroken)
            row = parts[0]
            for place in (
                {"x": 0, "y": 0, "relwidth": 1, "height": 1},
                {"x": 0, "rely": 1, "y": -1, "relwidth": 1, "height": 1},
                {"x": 0, "y": 0, "width": 1, "relheight": 1},
                {"relx": 1, "x": -1, "y": 0, "width": 1, "relheight": 1},
            ):
                bar = tk.Frame(row, bg=t.c["accent"], bd=0, highlightthickness=0)
                bar.place(**place)
                d.setdefault("bars", []).append(bar)
        d["lit"] = (thing,)

    def _drag_end(self, e) -> None:
        d, self.drag = self.drag, None
        if not d:
            return
        if not d["moving"]:  # a click
            self.select(d["key"], add=False)
            return
        target = self._drop_target(e.x_root, e.y_root)
        action = self.drop_action(d["key"], target) if target else None
        if action:
            action[1]()
        else:
            self.render_rail()  # clears the highlight and the hint

    def drop_action(self, key: Path, target: tuple | None):
        """(what it does, do it) for dropping the row `key` on a target, or None.

        On a run or a bundle of the same game: bundle them. On its own heading: take a run out
        of its bundle. On another group's heading: move it there. On its game's heading: take it
        out of its group. A bundle moves whole; a run dragged out of a bundle leaves it.
        """
        s = self.setups.get(key)
        if s is None or target is None:
            return None
        if key in self.selected and len(self.selected) > 1:
            return self._drop_many(target)
        kind, thing, _ = target
        src = s.parent or s  # where the dragged row lives now
        if kind == "row":
            dst = thing.parent or thing
            if dst is src or exe_of(dst) != exe_of(s):
                return None
            return (f"Bundle with {dst.name}", lambda: self.bundle_rows(s, dst))
        h: feed.Heading = thing
        names = feed.game_names(self.captures)
        game = feed.game_of(s.runs[0][1], names)
        here = s.heading == h.key
        if here and s.parent is None:
            return None
        if here:
            return ("Take out of the bundle", lambda: self._save_user(s.folders, bundle=None))
        if h.custom:
            return (f"Move to {h.title}", lambda: self._move_rows(s, h.title))
        if h.key == f"game:{game}":
            return (f"Out of the group, under {h.title}", lambda: self._move_rows(s, None))
        return None

    def _drop_many(self, target: tuple):
        """Dropping several selected rows: on a run or bundle of the same game, bundle them all
        with it; on a group's heading, move them there; on their game's heading, back under it."""
        rows = self.selected_rows()
        kind, thing, _ = target
        n = len(rows)
        if kind == "row":
            dst = thing.parent or thing
            if any(exe_of(r) != exe_of(dst) for r in rows):
                return None
            others = [r for r in rows if (r.parent or r) is not dst]
            if not others:
                return None
            return (f"Bundle {n} with {dst.name}", lambda: self.bundle_many([dst, *others]))
        h: feed.Heading = thing
        if h.custom and any(r.heading != h.key or r.parent is not None for r in rows):
            return (f"Move {n} to {h.title}", lambda: self.move_rows_to(rows, h.title))
        names = feed.game_names(self.captures)
        same_game = all(f"game:{feed.game_of(r.runs[0][1], names)}" == h.key for r in rows)
        moves = any(r.heading != h.key or r.parent is not None for r in rows)
        if same_game and moves:  # out of a group, or a picked run out of its bundle
            return (f"Move {n} under {h.title}", lambda: self.move_rows_to(rows, None))
        return None

    def bundle_rows(self, s: feed.Setup, dst: feed.Setup) -> None:
        """Put a row's runs (a run, or a whole bundle) in another row's bundle."""
        bundle = dst.bundle or dst.runs[0][0].name
        group = summary.group(dst.runs[0][1])
        folders = [f for f in dst.folders if dst.bundle is None] + s.folders
        self._save_user(folders, bundle=bundle, group=group)
        self.toggle_bundle(bundle, True)
        found = next(
            (r for h in self.feed for r in h.setups if r.bundle == bundle and r.is_bundle), None
        )
        if found:
            self.select(found.key, add=False)

    def unbundle(self, s: feed.Setup) -> None:
        self._save_user(s.folders, bundle=None)

    def _move_rows(self, s: feed.Setup, group: str | None) -> None:
        """Move a row to a group (None: back under its game). A run leaves its bundle."""
        if s.parent is not None:
            self._save_user(s.folders, group=group, bundle=None)
        else:
            self._save_user(s.folders, group=group)

    def _row_menu(self, event, h: feed.Heading, s: feed.Setup) -> None:
        m = self._menu()
        key, folder = s.key, s.folder
        if s.parent is not None:  # a run inside a bundle
            m.add_command(label="Open folder", command=lambda: _open(folder))
            m.add_command(
                label="Copy this run's report",
                command=lambda: self._copy_report_of(folder, True),
            )
            m.add_cascade(label="Benchmark", menu=self._benchmark_menu(m, [folder]))
            m.add_separator()
            m.add_command(label="Take out of the bundle", command=lambda: self.unbundle(s))
            m.add_command(label="Delete this run…", command=lambda: self.ask_delete([folder]))
            try:
                m.tk_popup(event.x_root, event.y_root)
            finally:
                m.grab_release()
            return
        if key in self.selected and len(self.selected) > 2:
            self._many_menu(event)
            return
        other = [k for k in self.selected if k != key]
        # with two rows selected and the click on one of them, group and delete act on both
        rows = [s]
        if key in self.selected:
            rows = [self.setups[k] for k in self.selected if k in self.setups]
        targets = [f for r in rows for f in r.folders]
        many = f" ({len(targets)} runs)" if len(targets) > 1 else ""
        m.add_command(label="Open folder", command=lambda: _open(folder))
        m.add_command(label="Copy report", command=lambda: self._copy_report_of(key))
        m.add_separator()
        m.add_command(label="Rename…", command=lambda: self.rename_capture(key))
        m.add_command(
            label="Set as base",
            command=lambda: self.set_base(h, s),
            state="disabled" if s.status == "base" else "normal",
        )
        mine = self._chosen_setup(h) is s
        m.add_command(
            label="Stop using as my settings" if mine else "Use as my settings",
            command=lambda: self.choose_settings(h, None if mine else s),
        )
        m.add_separator()
        mate = self.setups.get(other[-1]) if other else None
        mate = (mate.parent or mate) if mate else None
        can = mate is not None and mate is not s and exe_of(mate) == exe_of(s)
        m.add_command(
            label=f"Bundle with {self._fit(mate.name, 'body_sm', px(200))}" if can else
            "Bundle with selected",
            command=lambda: self.bundle_rows(s, mate),
            state="normal" if can else "disabled",
        )  # fmt: skip
        if s.is_bundle:
            m.add_command(label="Unbundle", command=lambda: self.unbundle(s))
        sub = self._menu(m)
        for g in self.custom_groups():
            sub.add_command(label=g, command=lambda g=g: self.move_to_group(targets, g))
        if self.custom_groups():
            sub.add_separator()
        sub.add_command(label="New group…", command=lambda: self.ask_group(targets))
        sub.add_command(
            label="Back under its game",
            command=lambda: self.move_to_group(targets, None),
            state="normal" if any(self._group_of(f) for f in targets) else "disabled",
        )
        m.add_cascade(label="Move to group", menu=sub)
        m.add_cascade(label="Benchmark", menu=self._benchmark_menu(m, targets))
        m.add_separator()
        m.add_command(
            label="Compare with selected",
            command=lambda: self._compare_with(key),
            state="normal" if other else "disabled",
        )
        m.add_separator()
        m.add_command(label=f"Delete{many}…", command=lambda: self.ask_delete(targets))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def _many_menu(self, event) -> None:
        """The menu for three or more selected rows: what acts on all of them at once."""
        m = self._menu()
        rows = self.selected_rows()
        folders = self.selected_folders()
        runs = f"{len(folders)} run{'s' if len(folders) != 1 else ''}"
        m.add_command(label=f"{len(rows)} selected · {runs}", state="disabled")
        m.add_separator()
        can = len({exe_of(r) for r in rows}) == 1 and len({id(r.parent or r) for r in rows}) > 1
        m.add_command(
            label="Bundle the selected", command=lambda: self.bundle_many(rows),
            state="normal" if can else "disabled",
        )  # fmt: skip
        m.add_command(
            label="Take out of their bundles",
            command=lambda: self._save_user(folders, bundle=None),
            state="normal" if any(r.is_bundle or r.parent for r in rows) else "disabled",
        )
        m.add_cascade(label="Benchmark", menu=self._benchmark_menu(m, folders))
        sub = self._menu(m)
        for g in self.custom_groups():
            sub.add_command(label=g, command=lambda g=g: self.move_rows_to(rows, g))
        if self.custom_groups():
            sub.add_separator()
        sub.add_command(label="New group…", command=lambda: self.ask_group(folders),
                        accelerator="Ctrl+G")  # fmt: skip
        sub.add_command(
            label="Back under their games",
            command=lambda: self.move_rows_to(rows, None),
            state="normal" if any(self._group_of(f) for f in folders) else "disabled",
        )
        m.add_cascade(label="Move to group", menu=sub)
        m.add_separator()
        m.add_command(label=f"Delete {runs}…", command=lambda: self.ask_delete(folders),
                      accelerator="Del")  # fmt: skip
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    def bundle_many(self, rows: list[feed.Setup]) -> None:
        """Put every selected row's runs in one bundle: the oldest row's, if it is one."""
        tops: list[feed.Setup] = []
        for r in rows:
            top = r.parent or r
            if top not in tops:
                tops.append(top)
        dst = min(tops, key=lambda r: r.runs[0][1]["capture"].get("started") or "")
        bundle = dst.bundle or dst.runs[0][0].name
        group = summary.group(dst.runs[0][1])
        folders = list(dict.fromkeys(f for r in tops for f in r.folders))
        self._save_user(folders, bundle=bundle, group=group)
        self.toggle_bundle(bundle, True)
        found = next(
            (r for h in self.feed for r in h.setups if r.bundle == bundle and r.is_bundle), None
        )
        if found:
            self.select(found.key, add=False)

    def move_rows_to(self, rows: list[feed.Setup], group: str | None) -> None:
        """Move rows to a group (None: back under their games). A bundle moves whole; a run
        picked out of a bundle leaves it."""
        whole = [f for r in rows if r.parent is None for f in r.folders]
        loose = [f for r in rows if r.parent is not None for f in r.folders if f not in whole]
        if whole:
            self._save_user(whole, group=group)
        if loose:
            self._save_user(loose, group=group, bundle=None)

    def _benchmark_menu(self, parent: tk.Menu, folders: list[Path]) -> tk.Menu:
        """Tag runs with a benchmark: an existing tag, a new one, or none. A tick marks the
        tag every one of these runs already has."""
        sub = self._menu(parent)
        have = {summary.benchmark(self.result_for(f)) for f in folders if self._has(f)}
        now = next(iter(have)) if len(have) == 1 else ""
        for g in self.benchmark_tags():
            sub.add_command(
                label=("✓ " if g == now else "    ") + g,
                command=lambda g=g: self._save_user(folders, benchmark=g),
            )
        if self.benchmark_tags():
            sub.add_separator()
        sub.add_command(label="New benchmark…", command=lambda: self.ask_benchmark(folders))
        sub.add_command(
            label="No benchmark",
            command=lambda: self._save_user(folders, benchmark=None),
            state="normal" if any(have) else "disabled",
        )
        return sub

    def _has(self, folder: Path) -> bool:
        return any(f == folder for f, _ in self.captures)

    def ask_benchmark(self, folders: list[Path]) -> None:
        runs = f"{len(folders)} runs" if len(folders) > 1 else "this run"
        text = TextDialog.ask(
            self,
            "Benchmark",
            f"The scene {runs} benchmarked, like a map or a built-in benchmark. Runs of one"
            " benchmark are measured against each other.",
            "",
            choices=self.benchmark_tags(),
        )
        if text is not None and text.strip():
            text = " ".join(text.split())
            same = next((g for g in self.benchmark_tags() if g.casefold() == text.casefold()), text)
            self._save_user(folders, benchmark=same)

    def _menu(self, parent=None) -> tk.Menu:
        t = self.t
        return tk.Menu(
            parent or self.root, tearoff=0, bg=t.c["surface1"], fg=t.c["text1"], bd=1,
            relief="flat", activebackground=t.c["surface2"], activeforeground=t.c["text1"],
            disabledforeground=t.c["text4"], font=t.fonts["body_sm"], activeborderwidth=0,
        )  # fmt: skip

    def _group_menu(self, event, h: feed.Heading) -> None:
        m = self._menu()
        folders = [f for s in h.setups for f in s.folders]
        m.add_command(label="Open game profile", command=lambda: self.open_profile(h.key))
        m.add_separator()
        if h.custom:
            m.add_command(label="Rename group…", command=lambda: self.ask_group(folders, h.title))
            m.add_command(
                label="Ungroup (back under each game)",
                command=lambda: self.move_to_group(folders, None),
            )
        else:
            m.add_command(label="Move all to a group…", command=lambda: self.ask_group(folders))
        m.add_separator()
        m.add_command(
            label=f"Delete all {len(folders)} captures…",
            command=lambda: self.ask_delete(folders, h.title),
        )
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    # --- the feed: setups, base, profile -------------------------------------------------------

    def goal_and_target(self) -> tuple[goals.Goal, int | None]:
        """The rail's goal; the target falls back to the newest capture's refresh rate."""
        goal = goals.get(self.goal_key())
        target = self.target_fps()
        if goal.key == "target" and not target:
            newest = self.captures[0][1] if self.captures else {}
            target = (goals.default_target(newest) if newest else None) or 60
        return goal, target

    def _rebuild_feed(self) -> None:
        goal, target = self.goal_and_target()
        self.feed = feed.build(self.captures, goal, target, self.settings.get("bases") or {})
        self.setups = {}
        for h in self.feed:
            for s in h.setups:
                self.setups[s.key] = s
                for c in s.children:  # a bundle's runs, each selectable on its own
                    self.setups[c.key] = c
        self.selected = [k for k in self.selected if k in self.setups]
        if self.profile_key and not any(h.key == self.profile_key for h in self.feed):
            self.profile_key = None

    def setup_for(self, key: Path) -> feed.Setup | None:
        return self.setups.get(key)

    def heading_for(self, key: str) -> feed.Heading | None:
        return next((h for h in self.feed if h.key == key), None)

    def view_for(self, key: Path) -> dict:
        """What a row stands for: a bundle's runs combined, or the one run."""
        s = self.setups.get(key)
        return s.result if s else self.result_for(key)

    def folder_of(self, key: Path) -> Path:
        """A real folder for a row: a bundle's newest run."""
        s = self.setups.get(key)
        return s.folder if s else key

    def _pin(self, setting: str, key: str, s: feed.Setup | None) -> None:
        pins = dict(self.settings.get(setting) or {})
        if s is None:
            pins.pop(key, None)
        else:
            pins[key] = s.runs[0][0].name
        self.settings[setting] = pins
        save_settings(self.settings)
        self.render_rail()
        self.render_main()

    def set_base(self, h: feed.Heading, s: feed.Setup) -> None:
        """Pin a base: it replaces the base of its own kind of run (same length and display)."""
        self.settings["bases"] = feed.pin(self.settings.get("bases"), h, s)
        save_settings(self.settings)
        self.render_rail()
        self.render_main()

    def choose_settings(self, h: feed.Heading, s: feed.Setup | None) -> None:
        self._pin("chosen", h.key, s)

    def _chosen_setup(self, h: feed.Heading) -> feed.Setup | None:
        name = (self.settings.get("chosen") or {}).get(h.key)
        return next((s for s in h.setups if name in {f.name for f in s.folders}), None)

    def open_profile(self, key: str) -> None:
        self.profile_key = key
        self.render_rail()
        self.render_main()


    # --- organizing captures -------------------------------------------------------------------

    def custom_groups(self) -> list[str]:
        """Groups the user made, newest first."""
        seen: list[str] = []
        for _, r in self.captures:
            g = summary.group(r)
            if g and g not in seen:
                seen.append(g)
        return seen

    def _group_of(self, folder: Path) -> str | None:
        try:
            return summary.group(self.result_for(folder))
        except StopIteration:
            return None

    def _save_user(self, folders: list[Path], **fields) -> None:
        """Write label/group/bundle/benchmark into each capture and refresh the list and views."""
        failed = 0
        for folder in folders:
            try:
                updated = capture.save_user(folder, **fields)
            except (OSError, ValueError):
                failed += 1
                continue
            self.captures = [(f, updated if f == folder else r) for f, r in self.captures]
        self.render_rail()
        self.render_main()
        self.kick_share()
        if failed:
            self.show_note(f"Couldn't save {failed} of {len(folders)}.", "")

    def rename_capture(self, key: Path) -> None:
        s = self.setup_for(key)
        if s is not None and s.parent is not None:
            s = s.parent  # a run inside a bundle: the bundle carries the name
        try:
            result = s.result if s else self.result_for(key)
        except StopIteration:
            return
        folders = s.folders if s else [key]
        runs = f" ({len(folders)} runs)" if len(folders) > 1 else ""
        text = TextDialog.ask(
            self,
            f"Rename{runs}",
            "A name for this row, like the settings you changed. It shows in the list, the"
            " report and comparisons. Leave it empty to name it after what changed.",
            (s.label if s else summary.label(result)) or "",
        )
        if text is not None:
            self._save_user(folders, label=text)

    def ask_group(self, folders: list[Path], current: str | None = None) -> None:
        text = TextDialog.ask(
            self,
            "Rename group" if current else "New group",
            f"A name for the group of {len(folders)} capture{'s' if len(folders) > 1 else ''},"
            " like a test session or the setting you're tuning.",
            current or "",
            choices=[g for g in self.custom_groups() if g != current],
        )
        if text:
            if current:  # keep a renamed group folded or open as it was
                folded = [text if g == current else g for g in self.settings.get("collapsed", [])]
                self.settings["collapsed"] = folded
                save_settings(self.settings)
            self.move_to_group(folders, text)

    def move_to_group(self, folders: list[Path], group: str | None) -> None:
        self._save_user(folders, group=group)

    def ask_delete(self, folders: Path | list[Path], heading: str | None = None) -> None:
        """Ask in the banner before deleting; the captures go to the Recycle Bin."""
        folders = [folders] if isinstance(folders, Path) else list(folders)
        if not folders:
            return
        setup = self.setup_for(folders[0])
        setup = (setup.parent or setup) if setup else None
        if heading:
            what = f"all {len(folders)} captures in {heading}"
        elif len(folders) == 1:
            r = self.result_for(folders[0])
            what = f"{summary.title(r)} from {summary.when(r['capture'].get('started'))}"
        elif setup and set(folders) == set(setup.folders):
            what = f"{setup.name} ({len(folders)} runs)"
        else:
            what = f"these {len(folders)} captures"
        many = len(folders) > 1
        if os.name == "nt":
            where = f"The folder{'s go' if many else ' goes'} to the Recycle Bin."
        else:
            where = f"The folder{'s are' if many else ' is'} deleted for good."
        self.confirm = (
            f"Delete {what}? {where}",
            [("Delete", lambda: self.delete_captures(folders)), ("Cancel", self.cancel_confirm)],
        )
        self.render_setup()

    def cancel_confirm(self) -> None:
        self.confirm = None
        self.render_setup()

    def delete_captures(self, folders: list[Path]) -> None:
        self.confirm = None
        root = self.captures_root or capture.DEFAULT_ROOT
        done, failed = 0, 0
        for folder in folders:
            try:
                capture.delete_capture(folder, root)
                done += 1
            except (OSError, capture.CaptureError):
                failed += 1
            self.traces.pop(folder, None)
        self.selected = [f for f in self.selected if f not in folders]
        self.render_setup()
        self.refresh_history()
        note = f"Deleted {done} capture{'s' if done != 1 else ''}."
        self.show_note(note + (f" {failed} couldn't be deleted." if failed else ""), "")

    def _compare_with(self, folder: Path) -> None:
        other = [f for f in self.selected if f != folder]
        if other:
            self.selected = [other[-1], folder]
            self.render_rail()
            self.render_main()
            self.tabs.select("Compare")

    def _copy_report_of(self, folder: Path, single: bool = False) -> None:
        try:
            r = self.result_for(folder) if single else self.view_for(folder)
            text = report.render(r, self.goal_key(), self.target_fps())
        except StopIteration:
            return
        self._to_clipboard(text)
        self.show_note("Report copied to the clipboard.", f"{len(text):,} chars")

    def _render_foot(self) -> None:
        t = self.t
        for child in self.foot.winfo_children():
            child.destroy()
        rows = [self.pm_status, self.trace_status]
        if self.sharer.available:
            rows.append(self.share_status)
        for level, name, value in rows:
            r = frame(self.foot, t)
            r.pack(fill="x", pady=px(2))
            Lamp(r, t, level).pack(side="left", padx=(0, px(8)))
            label(r, t, name, font="caption", fg="text2").pack(side="left")
            label(r, t, value, font="mono_xs", fg="text3").pack(side="right")
        if self.sharer.available and self.sharer.has_shared:
            FlatButton(
                self.foot, t, "Delete my shared data", self.ask_forget, "ghost", small=True
            ).pack(anchor="w", pady=(px(6), 0))

    def system_line(self) -> str:
        info = self.system
        if not info:
            return "Reading system info..."
        parts = [
            info.cpu
            and info.cpu.replace("AMD ", "").replace(" Processor", "").replace("-Core", "C")
        ]
        gpu = info.main_gpu
        if gpu:
            parts.append(gpu.name.replace("NVIDIA GeForce ", "").replace("AMD Radeon ", "Radeon "))
        if info.ram_total_gb:
            parts.append(
                f"{info.ram_total_gb:.0f} GB {info.ram_type or ''} @ {info.ram_running_mts or '?'}"
            )
        disp = info.main_display
        if disp:
            parts.append(f"{disp.width}x{disp.height} @ {disp.refresh_hz} Hz")
        # one fact per line, like a spec plate: CPU, GPU, RAM, display
        return "\n".join(p for p in parts if p)

    def render_setup(self) -> None:
        t = self.t
        for child in self.banner.winfo_children():
            child.destroy()
        issue = (
            ("warn", self.confirm[0], self.confirm[1])
            if self.confirm
            else self.setup_issue
            or (
                ("error", self.capture_error, [("Dismiss", self.dismiss_error)])
                if self.capture_error
                else self.consent_issue()
            )
        )
        if not issue:
            self.banner.pack_forget()
            return
        level, text, buttons = issue
        bgkey = {"error": "error_bg", "warn": "warning_bg"}.get(level, "surface1")
        fgkey = {"error": "error", "warn": "warning"}.get(level, "text3")
        box = tk.Frame(
            self.banner,
            bg=t.c[bgkey],
            highlightthickness=1,
            highlightbackground=theme.mix(t.c[fgkey], t.c[bgkey], 0.4),
        )
        box.pack(fill="x")
        Lamp(box, t, level).pack(side="left", anchor="n", padx=(px(16), px(12)), pady=(px(17), 0))
        msg = RichText(box, t, text, font="body_sm", mono="mono_sm", fg="text1", bg=bgkey)
        for name, cmd in reversed(buttons):
            FlatButton(box, t, name, cmd, "secondary", small=True).pack(
                side="right", padx=(0, px(12)), pady=px(8)
            )
        msg.pack(side="left", fill="x", expand=True, pady=px(12), padx=(0, px(12)))
        self.banner.pack(fill="x", padx=px(24), pady=(px(16), 0), before=self.header)

    def dismiss_error(self) -> None:
        self.capture_error = None
        self.render_setup()

    def render_main(self) -> None:
        """Header, summary and tabs for the selected capture (or the empty/recording view)."""
        for child in self.header.winfo_children():
            child.destroy()
        result = self.current_result()
        state = self.recorder.state if self.recorder else "idle"
        busy = state in ("recording", "stopping", "analyzing")
        if busy:
            self._header(
                "REC",
                "Recording" if state == "recording" else "Analyzing",
                self.record_info.get("sub", ""),
                [],
            )
        elif self.profile_key and self.heading_for(self.profile_key):
            self.render_profile()
            return
        elif result:
            s = self.setup_for(self.selected[-1])
            sub = summary.subtitle(result)
            if s and s.parent is not None:  # a run inside a bundle
                i = s.parent.children.index(s) + 1
                out = ", left out of the bundle" if s.status == "out" else ""
                sub = f"Run {i} of {s.parent.count}{out} · {sub}"
                s = s.parent
            title = s.name if s and s.kind in feed.NAMED else summary.title(result)
            tag = summary.benchmark(result)
            if tag and tag != title:  # the scene, unless the title already says it
                sub = f"{tag} · {sub}"
            self._header(
                summary.initials(summary.name(result)),
                title,
                sub,
                summary.tags(result),
            )
        else:
            where = self.captures_root or capture.DEFAULT_ROOT
            self._header("--", "Ready when you are", f"Captures are saved to {where}", [])
        if not self.tabs.winfo_manager():
            self.tabs.pack(fill="x", padx=(px(24), px(24)), after=self.header)
        self.page_profile.pack_forget()
        two = len(self.selected) == 2
        self.tabs.set_disabled("Compare", not two)
        self.tabs.set_disabled("Report", not result)
        self.tabs.set_disabled("System", not result)
        self.tabs.set_disabled("Game", not result)
        if not self.captures:
            hint = ""
        elif len(self.selected) > 2:
            hint = f"{len(self.selected)} selected · Ctrl+G group · Del · Esc"
        elif two:
            hint = "Ctrl+click a selected capture to leave the comparison"
        else:
            hint = "Ctrl+click a second capture to compare"
        set_silk(self.tab_hint, hint)
        self.folder_btn.set_enabled(True)
        self.copy_btn.set_enabled(bool(result))
        if self.tabs.current not in ("Summary",) and (
            not result or (self.tabs.current == "Compare" and not two)
        ):
            self.tabs.select("Summary", notify=False)
        self.fill_summary(result, state if busy else None)
        self.show_tab(self.tabs.current)

    def _header(self, initials: str, title: str, sub: str, tags: list[str]) -> None:
        t = self.t
        av = frame(self.header, t, "surface2", border="border", width=px(36), height=px(36))
        av.pack_propagate(False)
        av.pack(side="left", padx=(0, px(12)))
        label(av, t, initials, font="mono_sm", fg="text2", bg="surface2").pack(expand=True)
        for tag in reversed(tags):  # packed before the title, so a narrow window clips the title
            label(
                self.header, t, tag, font="mono_xs", fg="text2", bg="surface2", padx=px(7),
                pady=px(3),
            ).pack(side="right", padx=(px(6), 0))  # fmt: skip
        mid = frame(self.header, t)
        mid.pack(side="left", fill="x", expand=True)
        label(mid, t, title, font="subheading", anchor="w").pack(fill="x")
        label(mid, t, sub, font="mono_xs", fg="text3", anchor="w").pack(fill="x", pady=(px(2), 0))

    def _set_verdict(self, head: str, sentence: str) -> None:
        self.headline = summary.plain(head)
        for child in self.verdict_head.winfo_children():
            child.destroy()
        self._rich(self.verdict_head, head, "heading", "readout", "text1", "text1").pack(anchor="w")
        self.verdict_text.set(sentence)

    def _show_split(self, recording: bool) -> None:
        if recording:
            self.split_box.pack_forget()
            self.rec_progress.pack(fill="x")
        else:
            self.rec_progress.pack_forget()
            self.split_box.pack(fill="x")

    def fill_summary(self, result: dict | None, busy: str | None) -> None:
        t = self.t
        for child in self.split_legend.winfo_children():
            child.destroy()
        if busy:
            key = self.hotkey_var.get()
            length = self.recorder.length_s if self.recorder else None
            if busy == "recording":
                self._set_verdict(
                    "Recording.",
                    f"Play normally. Press {key} to stop"
                    + (f", or wait for {length} s." if length else "."),
                )
            else:
                self._set_verdict("Analyzing.", "Stopping PresentMon and reading the frames.")
            self._show_split(True)
            self.update_recording()
            for r in self.readouts:
                r.set(None, "", "recording" if busy == "recording" else "analyzing")
            self._fill_checks([], "Checks run when the capture ends.")
            self._fill_details([])
            self.runs_panel.pack_forget()
            set_silk(self.scope_title, "Frame time · live")
            self.scope_scale.configure(text="")
            self._paint_channels()
            return
        self._show_split(False)
        if not result:
            key = self.hotkey_var.get()
            length = (
                "until you press it again"
                if self.manual_var.get()
                else f"for {self.length_seconds()} s"
            )
            self._set_verdict(
                "No captures yet.",
                f"Start a game, press {key} and play normally. Frametrace records {length}, "
                "then shows the verdict here and copies the report to your clipboard.",
            )
            self.split.set(0, 0, 0)
            for r in self.readouts:
                r.set(None, "", "no data")
            self.scope.show(None, "NO CAPTURES YET")
            self._fill_checks(
                [],
                "Play the same scene each time (a benchmark map, replay or fixed route) so "
                "captures compare.",
            )
            self._fill_details([])
            self.runs_panel.pack_forget()
            set_silk(self.scope_title, "Frame time")
            self.scope_scale.configure(text="")
            self._paint_channels()
            return

        head, sentence = summary.plain_verdict(result)
        self._set_verdict(head, sentence)
        b = result["analysis"]["bottleneck"]
        if b.get("available"):
            self.split.set(b["gpu_pct"], b["cpu_pct"], b["wait_pct"])
            for key, name, pct in (
                ("ch2", "GPU", b["gpu_pct"]),
                ("ch3", "CPU", b["cpu_pct"]),
                ("text4", "Waiting", b["wait_pct"]),
            ):
                item = frame(self.split_legend, t, "surface1")
                item.pack(side="left", padx=(0, px(14)))
                swatch(item, t, key).pack(side="left", padx=(0, px(6)))
                label(item, t, name, font="caption", fg="text3", bg="surface1").pack(side="left")
                label(item, t, f"{pct:.0f}%", font="mono_xs", bg="surface1").pack(
                    side="left", padx=(px(4), 0)
                )
        else:
            self.split.set(0, 0, 0)
            silk(self.split_legend, t, "No GPU busy data", bg="surface1", fg="text4").pack(
                side="left"
            )
        for r, v in zip(self.readouts, summary.readouts(result), strict=True):
            r.set(v.value, v.unit, v.sub, title=v.title)
        set_silk(self.scope_title, "Frame time")
        self._fill_checks(result.get("checks", []), "")
        self._fill_details(summary.details(result))
        self._fill_runs()
        set_silk(
            self.scope_title,
            "Frame time · newest run that counts" if result.get("stack") else "Frame time",
        )
        self.load_trace()

    def update_recording(self) -> None:
        """Progress bar, top line and scope sweep while a capture runs."""
        rec = self.recorder
        if not rec or rec.state not in ("recording", "stopping", "analyzing"):
            return
        key = self.hotkey_var.get() or "the hotkey"
        if rec.state != "recording":
            self.rec_progress.set(1.0, "ANALYZING", "reading frames")
            self.scope.recording(1.0, "ANALYZING · READING THE FRAMES")
            return
        elapsed, length = rec.elapsed(), rec.length_s
        if length:
            left = max(0.0, length - elapsed)
            self.rec_progress.set(
                elapsed / length, f"{_clock(elapsed)} / {_clock(length)}", f"{_clock(left)} left"
            )
            self.scope.recording(elapsed / length, "RECORDING · THE TRACE APPEARS WHEN IT ENDS")
        else:
            self.rec_progress.set(None, f"{_clock(elapsed)} elapsed", f"manual · {key} stops")
            self.scope.recording(elapsed / 10, "RECORDING · THE TRACE APPEARS WHEN IT ENDS")

    def _fill_checks(self, checks: list[dict], empty: str) -> None:
        t = self.t
        p = self.checks_panel
        for child in p.winfo_children():
            child.destroy()
        head = frame(p, t, "surface1")
        head.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        silk(head, t, "Checks", bg="surface1").pack(side="left")
        if checks:
            ok = sum(1 for c in checks if c["level"] == "ok")
            warn = sum(1 for c in checks if c["level"] == "warn")
            label(
                head, t, f"{ok} ok · {warn} to look at", font="mono_xs", fg="text3", bg="surface1"
            ).pack(side="right")
        if not checks:
            RichText(p, t, empty, fg="text3").pack(fill="x", padx=px(16), pady=(0, px(14)))
            return
        order = {"warn": 0, "info": 1, "ok": 2}
        for i, c in enumerate(sorted(checks, key=lambda c: order.get(c["level"], 3))):
            if i:
                rule(p, t).pack(fill="x", padx=px(16))
            r = frame(p, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=px(7))
            Lamp(r, t, c["level"]).pack(side="left", anchor="n", pady=(px(6), 0), padx=(0, px(10)))
            RichText(r, t, c["text"]).pack(side="left", fill="x", expand=True)
        frame(p, t, "surface1", height=px(8)).pack()

    def _fill_details(self, rows: list[tuple[str, str]]) -> None:
        t = self.t
        p = self.details_panel
        for child in p.winfo_children():
            child.destroy()
        head = frame(p, t, "surface1")
        head.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        silk(head, t, "Details", bg="surface1").pack(side="left")
        label(head, t, "presenting thread", font="mono_xs", fg="text3", bg="surface1").pack(
            side="right"
        )
        if not rows:
            label(p, t, "---", font="mono_sm", fg="text4", bg="surface1").pack(
                anchor="w", padx=px(16), pady=(0, px(14))
            )
        for i, (k, v) in enumerate(rows):
            if i:
                rule(p, t).pack(fill="x", padx=px(16))
            r = frame(p, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=px(7))
            label(r, t, k, fg="text2", bg="surface1").pack(side="left")
            label(
                r, t, v, font="mono_sm", fg="text1" if v != "n/a" else "text4", bg="surface1"
            ).pack(side="right")

    def show_tab(self, name: str) -> None:
        if self.profile_key:  # the profile has no tabs
            return
        self.shown = name
        for page in (
            self.page_summary,
            self.page_text,
            self.page_game,
            self.page_system,
            self.page_compare,
            self.page_profile,
        ):
            page.pack_forget()
        result = self.current_result()
        if name == "Summary":
            self.page_summary.pack(fill="both", expand=True)
            self.shown_text = self.report_text(result) if result else ""
        elif name == "Report" and result:
            self.set_text(self.report_text(result))
            self.page_text.pack(fill="both", expand=True)
        elif name == "Compare" and len(self.selected) == 2:
            (fa, a), (fb, b) = self.compare_pair()
            self.fill_compare(fa, a, fb, b)
            self.page_compare.pack(fill="both", expand=True)
            self.shown_text = report.compare(a, b, self.goal_key(), self.target_fps())
        elif name == "System" and result:
            self.fill_system(result)
            self.page_system.pack(fill="both", expand=True)
            self.shown_text = self.report_text(result)
        elif name == "Game" and result:
            self.fill_game(result)
            self.page_game.pack(fill="both", expand=True)
            self.shown_text = self.report_text(result)
        self.copy_btn.set_text("Copy comparison" if name == "Compare" else "Copy report")
        self.compare_btn.set_enabled(len(self.selected) == 2 and name != "Compare")

    def compare_pair(self) -> list[tuple[Path, dict]]:
        """The two selected rows, older first: A is the reference, B the new run.

        Each is (the run whose trace stands for the row, the row's result, runs combined).
        """
        pair = [(self.trace_folder(f), self.view_for(f)) for f in self.selected]
        return sorted(pair, key=lambda fr: fr[1]["capture"].get("started", ""))

    def fill_compare(self, fa: Path, a: dict, fb: Path, b: dict) -> None:
        t = self.t
        page = self.page_compare.inner
        for child in page.winfo_children():
            child.destroy()

        # capture chips: A is the stored reference, B the live trace
        chips = frame(page, t)
        chips.pack(fill="x", pady=(0, px(8)))
        chips.columnconfigure(0, weight=1, uniform="chip")
        chips.columnconfigure(1, weight=1, uniform="chip")
        for col, (name, res, key, role, f) in enumerate(
            (("A", a, "ref", "Reference", fa), ("B", b, "ch1", "New run", fb))
        ):
            chip = frame(chips, t, "surface1", border="border")
            chip.grid(row=0, column=col, sticky="nsew", padx=(0, px(8)) if col == 0 else 0)
            head = frame(chip, t, "surface1")
            head.pack(fill="x", padx=px(16), pady=(px(12), px(6)))
            swatch(head, t, key).pack(side="left", padx=(0, px(8)))
            silk(head, t, f"{name} · {role}", bg="surface1").pack(side="left")
            cap, s = res["capture"], res["analysis"]["stats"]
            line = frame(chip, t, "surface1")
            line.pack(fill="x", padx=px(16))
            setup = self.setup_for(f)
            if setup and setup.parent is not None and res.get("stack"):
                setup = setup.parent  # the bundle, shown by its newest run's trace
            named = setup and setup.kind in feed.NAMED
            mono = setup and setup.kind in ("settings", "system")
            label(
                line, t, setup.name if named else summary.title(res),
                font="mono_sm" if mono else "body_sm", bg="surface1",
            ).pack(side="left")  # fmt: skip
            label(line, t, f"{s['avg_fps']:.1f}", font="mono_sm", bg="surface1").pack(side="right")
            st = res.get("stack")
            when, secs = summary.when(cap.get("started")), f"{s['duration_s']:.0f} s"
            meta = (
                f"{st['used']} runs · newest {when} · {secs} each"
                if st
                else f"{when} · {secs} · {s['frames']:,} frames"
            )
            row2 = frame(chip, t, "surface1")
            row2.pack(fill="x", padx=px(16), pady=(px(2), px(12)))
            label(row2, t, meta, font="mono_xs", fg="text3", bg="surface1").pack(side="left")
            label(row2, t, "avg FPS", font="mono_xs", fg="text3", bg="surface1").pack(side="right")

        # verdict
        goal, target = report.resolve_goal(b, self.goal_key(), self.target_fps())
        head, items, notes = summary.compare_verdict(a, b, goal, target)
        v = frame(page, t, "surface1", border="border")
        v.pack(fill="x", pady=(0, px(8)))
        self._rich(v, head, "heading", "readout", "text1", "text1").pack(
            anchor="w", padx=px(16), pady=(px(14), px(10))
        )
        for status, phrase in items:
            r = frame(v, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=(0, px(6)))
            level, word = {"better": ("ok", "Better"), "worse": ("warn", "Worse")}.get(
                status, ("idle", "Same")
            )
            Lamp(r, t, level).pack(side="left", anchor="n", pady=(px(5), 0), padx=(0, px(8)))
            silk(r, t, word, bg="surface1", fg="text1", width=8, anchor="w").pack(
                side="left", anchor="n", pady=(px(2), 0)
            )
            self._rich(r, phrase, "body_sm", "mono_sm", "text2", "text1").pack(side="left")
        for note in notes:
            r = frame(v, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=(0, px(6)))
            Lamp(r, t, "info").pack(side="left", anchor="n", pady=(px(5), 0), padx=(0, px(8)))
            RichText(r, t, note, font="caption", mono="mono_xs", fg="text3", mono_fg="text2").pack(
                side="left", fill="x", expand=True
            )
        frame(v, t, "surface1", height=px(8)).pack()

        # what changed in the game between A and B
        self._fill_settings_changes(page, a, b, fb)

        # scope: REF A under CH1 B
        sp = frame(page, t, "surface1", border="border")
        sp.pack(fill="x", pady=(0, px(8)))
        sh = frame(sp, t, "surface1")
        sh.pack(fill="x", padx=px(16), pady=(px(12), px(10)))
        silk(sh, t, "Frame time · A vs B", bg="surface1").pack(side="left")
        self.compare_scale = label(sh, t, "", font="mono_xs", fg="text3", bg="surface1")
        self.compare_scale.pack(side="left", padx=(px(12), 0))
        for key, name in (("ch1", "CH1 B"), ("ref", "REF A")):
            chip = tk.Frame(
                sh,
                bg=t.c["surface2"],
                highlightthickness=1,
                highlightbackground=t.c["text3"],
                padx=px(7),
                pady=px(3),
            )
            chip.pack(side="right", padx=(px(6), 0))
            swatch(chip, t, key).pack(side="left", padx=(0, px(6)))
            label(chip, t, name, font="mono_xs", bg="surface2").pack(side="left")
        self.compare_scope = Scope(sp, t, height=184)
        self.compare_scope.channels.update(ch2=False, ch3=False)
        self.compare_scope.pack(fill="x", padx=px(16), pady=(0, px(16)))
        self.compare_folders = (fa, fb)
        self.draw_compare_scope()
        self.note_comparison(fa, fb)

        # deltas
        d = frame(page, t, "surface1", border="border")
        d.pack(fill="x", pady=(0, px(8)))
        dh = frame(d, t, "surface1")
        dh.pack(fill="x", padx=px(16), pady=(px(12), px(4)))
        silk(dh, t, "Changes from A to B", bg="surface1").pack(side="left")
        label(
            dh, t, "SAME = inside run-to-run noise", font="mono_xs", fg="text3", bg="surface1"
        ).pack(side="right")
        grid = frame(d, t, "surface1")
        grid.pack(fill="x", padx=px(16), pady=(0, px(12)))
        grid.columnconfigure(0, weight=1)
        heads = ("A", "B", "", "Change", "")
        row = 0
        for col, text in enumerate(heads, start=1):
            if text:
                silk(grid, t, text, bg="surface1", fg="text4", anchor="e").grid(
                    row=row,
                    column=col,
                    sticky="e" if col != 5 else "w",
                    padx=(0, px(16) if col == 2 else px(12) if col == 4 else 0),
                )
        row += 1
        for group, deltas in summary.compare_deltas(a, b):
            silk(grid, t, group, bg="surface1", fg="text4").grid(
                row=row, column=0, columnspan=6, sticky="w", pady=(px(12), px(4))
            )
            row += 1
            for i, delta in enumerate(deltas):
                if i:
                    rule(grid, t).grid(row=row, column=0, columnspan=6, sticky="ew")
                    row += 1
                self._delta_row(grid, row, delta)
                row += 1

        # where the frames went
        bn = frame(page, t, "surface1", border="border")
        bn.pack(fill="x", pady=(0, px(8)))
        silk(bn, t, "Where the frames waited", bg="surface1").pack(
            anchor="w", padx=px(16), pady=(px(12), px(10))
        )
        for name, res in (("A", a), ("B", b)):
            bk = res["analysis"]["bottleneck"]
            r = frame(bn, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=(0, px(10)))
            label(r, t, name, font="mono_sm", fg="text2", bg="surface1", width=2, anchor="w").pack(
                side="left"
            )
            if bk.get("available"):
                legend = frame(r, t, "surface1")
                legend.pack(side="right")
                for key, word, pct in (
                    ("ch2", "GPU", bk["gpu_pct"]),
                    ("ch3", "CPU", bk["cpu_pct"]),
                    ("text4", "waiting", bk["wait_pct"]),
                ):
                    swatch(legend, t, key).pack(side="left", padx=(px(12), px(5)))
                    label(legend, t, word, font="caption", fg="text3", bg="surface1").pack(
                        side="left"
                    )
                    label(
                        legend, t, f"{pct:.0f}%", font="mono_xs", bg="surface1", width=4, anchor="e"
                    ).pack(side="left", padx=(px(4), 0))
                bar = SplitBar(r, t)
                bar.pack(side="left", fill="x", expand=True, padx=(px(8), px(8)))
                bar.set(bk["gpu_pct"], bk["cpu_pct"], bk["wait_pct"])
            else:
                label(r, t, "no GPU busy data", font="mono_xs", fg="text3", bg="surface1").pack(
                    side="left", padx=px(8)
                )
        frame(bn, t, "surface1", height=px(4)).pack()

        # system changes
        sy = frame(page, t, "surface1", border="border")
        sy.pack(fill="x", pady=(0, px(8)))
        silk(sy, t, "System changes", bg="surface1").pack(
            anchor="w", padx=px(16), pady=(px(12), px(8))
        )
        changes = summary.system_changes(a, b)
        if not changes:
            r = frame(sy, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=(0, px(14)))
            Lamp(r, t, "ok").pack(side="left", padx=(0, px(10)))
            label(
                r,
                t,
                "No system differences: same hardware, drivers and Windows settings.",
                fg="text2",
                bg="surface1",
            ).pack(side="left")
        key_w = self._silk_width(name for name, _, _ in changes) + px(24)
        for i, (name, va, vb) in enumerate(changes):
            if i:
                rule(sy, t).pack(fill="x", padx=px(16))
            r = frame(sy, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=px(7))
            Lamp(r, t, "info").pack(side="left", padx=(0, px(10)))
            cell = frame(r, t, "surface1", width=key_w, height=px(16))
            cell.pack(side="left")
            cell.pack_propagate(False)
            silk(cell, t, name, bg="surface1", anchor="w").pack(side="left")
            label(r, t, va, font="mono_sm", fg="text3", bg="surface1").pack(side="left")
            label(r, t, "  →  ", font="mono_sm", fg="text4", bg="surface1").pack(side="left")
            label(r, t, vb, font="mono_sm", bg="surface1").pack(side="left")
        if changes:
            frame(sy, t, "surface1", height=px(6)).pack()
        self.page_compare.to_top()

    def _fill_settings_changes(self, page, a: dict, b: dict, fb: Path | None = None) -> None:
        """In-game settings that differ between A and B, read from the game's config."""
        t = self.t
        box = frame(page, t, "surface1", border="border")
        box.pack(fill="x", pady=(0, px(8)))
        silk(box, t, "In-game settings changed", bg="surface1").pack(
            anchor="w", padx=px(16), pady=(px(12), px(8))
        )
        changes = summary.settings_changes(a, b)
        if not changes:
            text = (
                "Not read for this game: tell the AI what you changed."
                if changes is None
                else "No change in the game's settings file."
            )
            r = frame(box, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=(0, px(14)))
            Lamp(r, t, "info" if changes is None else "ok").pack(side="left", padx=(0, px(10)))
            label(r, t, text, fg="text2", bg="surface1").pack(side="left")
            if changes is None and fb is not None:
                self._advice_row(box, fb, b)
            return
        mono = t.fonts["mono_sm"]
        key_w = max(mono.measure(k) for k, _, _ in changes) + px(24)
        for i, (key, va, vb) in enumerate(changes):
            if i:
                rule(box, t).pack(fill="x", padx=px(16))
            r = frame(box, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=px(7))
            Lamp(r, t, "info").pack(side="left", padx=(0, px(10)))
            cell = frame(r, t, "surface1", width=key_w, height=px(18))
            cell.pack(side="left")
            cell.pack_propagate(False)
            label(cell, t, key, font="mono_sm", fg="text2", bg="surface1", anchor="w").pack(
                side="left"
            )
            label(r, t, va, font="mono_sm", fg="text3", bg="surface1").pack(side="left")
            label(r, t, "  →  ", font="mono_sm", fg="text4", bg="surface1").pack(side="left")
            label(r, t, vb, font="mono_sm", bg="surface1").pack(side="left")
        frame(box, t, "surface1", height=px(6)).pack()
        if fb is not None:
            self._advice_row(box, fb, b)

    def _advice_row(self, box, fb: Path, b: dict) -> None:
        """Who suggested the changes: kept with B, and shared with the dataset when sharing is on
        (which AI's advice works is one of the things the data should show)."""
        t = self.t
        rule(box, t).pack(fill="x", padx=px(16))
        r = frame(box, t, "surface1")
        r.pack(fill="x", padx=px(16), pady=(px(8), px(12)))
        label(r, t, "Changes suggested by", fg="text2", bg="surface1").pack(
            side="left", padx=(0, px(12))
        )
        current = (b.get("user") or {}).get("advice") or ""
        var = tk.StringVar(value=current or "—")
        box_ = ttk.Combobox(
            r,
            textvariable=var,
            values=["—", *share.ADVICE],
            state="readonly",
            width=18,
            font=t.fonts["body_sm"],
        )
        box_.pack(side="left")

        def chosen(_e=None) -> None:
            value = var.get()
            self._save_user([fb], advice=None if value == "—" else value)

        box_.bind("<<ComboboxSelected>>", chosen)

    def _silk_width(self, names) -> int:
        """Widest silk-screen label among names, in pixels (column for label/value rows)."""
        font = self.t.fonts["label"]
        return max((font.measure(track(str(n).upper())) for n in names), default=0)

    def _rich(self, parent, text: str, font: str, mono: str, fg: str, mono_fg: str) -> tk.Frame:
        """One line with words in Plex Sans and the numbers in Plex Mono."""
        t, bg = self.t, parent.cget("bg")
        line = tk.Frame(parent, bg=bg)
        for part, is_num in summary.number_runs(text):
            tk.Label(
                line,
                text=part.replace(" ", "\u00a0") if is_num else part,
                font=t.fonts[mono if is_num else font],
                fg=t.c[mono_fg if is_num else fg],
                bg=bg,
                bd=0,
                padx=0,
                pady=0,
            ).pack(side="left", anchor="s")
        return line

    def _delta_row(self, grid: tk.Frame, row: int, d: summary.Delta) -> None:
        t = self.t
        status = d.status
        level, word = {
            "better": ("ok", "BETTER"),
            "worse": ("warn", "WORSE"),
            "same": ("idle", "SAME"),
            "changed": ("info", "CHANGED"),
        }.get(status, ("idle", "N/A"))
        unit = f" {d.unit}" if d.unit != "%" else "%"
        label(grid, t, d.label, fg="text2", bg="surface1", anchor="w").grid(
            row=row, column=0, sticky="w", pady=px(6)
        )
        label(
            grid, t, d.fmt(d.a) + unit, font="mono_sm", fg="text3", bg="surface1", anchor="e",
            width=11,
        ).grid(row=row, column=1, sticky="e")  # fmt: skip
        label(grid, t, d.fmt(d.b) + unit, font="mono_sm", bg="surface1", anchor="e", width=11).grid(
            row=row, column=2, sticky="e", padx=(px(8), px(16))
        )
        span = 1.0 if d.absolute else 25.0
        DeltaBar(grid, t, d.change, status, span=span).grid(row=row, column=3)
        label(
            grid,
            t,
            d.change_text(),
            font="mono_sm",
            fg="text1" if status in ("better", "worse") else "text3",
            bg="surface1",
            anchor="e",
            width=9,
        ).grid(row=row, column=4, sticky="e", padx=(px(12), px(12)))
        cell = frame(grid, t, "surface1")
        cell.grid(row=row, column=5, sticky="w")
        Lamp(cell, t, level).pack(side="left", padx=(0, px(6)))
        silk(
            cell,
            t,
            word,
            bg="surface1",
            fg="text1" if status in ("better", "worse") else "text3",
            width=9,
            anchor="w",
        ).pack(side="left")

    def draw_compare_scope(self) -> None:
        if not self.compare_scope or not getattr(self, "compare_folders", None):
            return
        fa, fb = self.compare_folders
        for f in (fa, fb):
            if f not in self.traces:
                self._request_trace(f)
        ta, tb = self.traces.get(fa), self.traces.get(fb)
        if fa in self.traces and fb in self.traces:
            if tb is None:
                self.compare_scope.show(None, "NO TRACE FOR CAPTURE B")
            else:
                self.compare_scope.show(tb, ref=ta)
        else:
            self.compare_scope.show(None, "READING FRAMES")
        try:
            self.compare_scale.configure(text=self.compare_scope.scale_text())
        except (AttributeError, tk.TclError):
            pass

    def set_text(self, text: str) -> None:
        """The report, as copied: section heads brighter, status markers coloured."""
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for i, line in enumerate(text.splitlines()):
            if i == 0 or line.startswith(("Frametrace report", "Frametrace compare")):
                self.text.insert("end", line + "\n", ("title",))
            elif line.startswith("## "):
                self.text.insert("end", line + "\n", ("head",))
            elif line.startswith(("[!]", "[ok]")):
                marker, _, rest = line.partition("]")
                tag = "warn" if marker == "[!" else "ok"
                self.text.insert("end", marker + "]", (tag,))
                self.text.insert("end", rest + "\n")
            elif line.startswith(("(", "Detected via")):
                self.text.insert("end", line + "\n", ("dim",))
            else:
                self.text.insert("end", line + "\n")
        self.text.configure(state="disabled")
        self.text.yview_moveto(0)
        self.shown_text = text

    def report_text(self, result: dict) -> str:
        return report.render(result, self.goal_key(), self.target_fps())

    def fill_system(self, result: dict) -> None:
        lines = report.render_system(result.get("system") or {})
        self._fill_sections(self.page_system, summary.system_sections(lines))

    def fill_game(self, result: dict) -> None:
        self._fill_sections(
            self.page_game, summary.game_sections(result), mono_keys={"In-game settings"}
        )

    def _fill_sections(self, page, sections, mono_keys: set[str] = frozenset()) -> None:
        """Bordered sections of key/value rows (System and Game tabs)."""
        inner = page.inner
        for child in inner.winfo_children():
            child.destroy()
        mono = self.t.fonts["mono_sm"]
        key_w = px(24) + max(
            self._silk_width(
                k for title, rows in sections if title not in mono_keys for k, _ in rows
            ),
            max(
                (
                    mono.measure(k)
                    for title, rows in sections
                    if title in mono_keys
                    for k, _ in rows
                ),
                default=0,
            ),
        )
        for title, rows in sections:
            note = "at capture time" if title == "Hardware" else ""
            self._section_box(inner, title, rows, key_w, title in mono_keys, note)
        page.to_top()

    def _section_box(
        self, parent, title: str, rows, key_w: int, mono: bool = False, note: str = ""
    ) -> tk.Frame:
        """A bordered panel of key/value rows."""
        t = self.t
        box = frame(parent, t, "surface1", border="border")
        box.pack(fill="x", pady=(0, px(8)))
        head = frame(box, t, "surface1")
        head.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        silk(head, t, title, bg="surface1").pack(side="left")
        if note:
            label(head, t, note, font="mono_xs", fg="text3", bg="surface1").pack(side="right")
        for i, (k, v) in enumerate(rows):
            if i:
                rule(box, t).pack(fill="x", padx=px(16))
            r = frame(box, t, "surface1")
            r.pack(fill="x", padx=px(16), pady=px(8))
            r.columnconfigure(0, minsize=key_w)
            r.columnconfigure(1, weight=1)
            if mono and k not in ("Read from", "Source"):
                key = label(r, t, k, font="mono_sm", fg="text2", bg="surface1", anchor="w")
            else:
                key = silk(r, t, k, bg="surface1", anchor="w")
            key.grid(row=0, column=0, sticky="nw", pady=(px(2), 0))
            fg = "text4" if v in ("unknown", "?") else "text1"
            prose = "body_sm" if not k else "mono_sm"  # a note, not a value
            RichText(r, t, v, font=prose, mono="mono_sm", fg=fg, mono_fg=fg).grid(
                row=0, column=1, sticky="ew"
            )
        frame(box, t, "surface1", height=px(6)).pack()
        return box

    # --- the game profile and a stack's runs ---------------------------------------------------

    def render_profile(self) -> None:
        """A heading's profile in the main column: no tabs, one page."""
        h = self.heading_for(self.profile_key)
        goal, target = self.goal_and_target()
        prof = feed.profile(h, goal, target, (self.settings.get("chosen") or {}).get(h.key))
        n, runs = len(h.setups), h.runs
        sub = (
            f"{'Group' if h.custom else 'Game'} profile · {n} setup{'s' if n != 1 else ''}"
            f" · {runs} run{'s' if runs != 1 else ''} · {goal.label}"
        )
        self._header(summary.initials(h.title), h.title, sub, [])
        self.tabs.pack_forget()
        for page in (
            self.page_summary, self.page_text, self.page_game, self.page_system,
            self.page_compare,
        ):  # fmt: skip
            page.pack_forget()
        self.fill_profile(prof)
        self.page_profile.pack(fill="both", expand=True)
        self.shown = "Profile"
        self.shown_text = feed.profile_text(prof)
        self.copy_btn.set_text("Copy profile")
        self.copy_btn.set_enabled(True)
        self.folder_btn.set_enabled(False)
        self.compare_btn.set_enabled(False)

    def fill_profile(self, prof: feed.Profile) -> None:
        t = self.t
        page = self.page_profile.inner
        for child in page.winfo_children():
            child.destroy()
        h, best, goal = prof.heading, prof.best, prof.goal
        if best is None:
            return

        # the setup to play with
        box = frame(page, t, "surface1", border="border")
        box.pack(fill="x", pady=(0, px(8)))
        head = frame(box, t, "surface1")
        head.pack(fill="x", padx=px(16), pady=(px(12), px(6)))
        silk(head, t, "Your settings" if prof.chosen else "Best measured", bg="surface1").pack(
            side="left"
        )
        used = len(best.used_runs)
        label(
            head, t, f"{used} run{'s' if used != 1 else ''}", font="mono_xs", fg="text3",
            bg="surface1",
        ).pack(side="right")  # fmt: skip
        body = frame(box, t, "surface1")
        body.pack(fill="x", padx=px(16), pady=(0, px(14)))
        mono = best.kind not in feed.TYPED
        label(
            body, t, best.name, font="mono" if mono else "subheading", bg="surface1", anchor="w"
        ).pack(fill="x")
        nums = frame(body, t, "surface1")
        nums.pack(fill="x", pady=(px(10), px(8)))
        if h.metric:
            num, unit = feed.metric_text(h.metric, best.value)
            silk(nums, t, feed.METRIC_SHORT.get(h.metric, h.metric), bg="surface1").pack(
                side="left", anchor="s", pady=(0, px(5)), padx=(0, px(10))
            )
            label(nums, t, num, font="readout", bg="surface1").pack(side="left", anchor="s")
            label(nums, t, " " + unit, font="mono_xs", fg="text3", bg="surface1").pack(
                side="left", anchor="s", pady=(0, px(4))
            )
        if prof.best_status not in ("base", "na"):
            level = {"better": "ok", "worse": "warn"}.get(prof.best_status, "idle")
            fg = {"better": "success", "worse": "warning"}.get(prof.best_status, "text3")
            vs = frame(nums, t, "surface1")
            vs.pack(side="left", anchor="s", padx=(px(16), 0), pady=(0, px(5)))
            Lamp(vs, t, level).pack(side="left", padx=(0, px(6)))
            label(vs, t, prof.best_change, font="mono_sm", fg=fg, bg="surface1").pack(side="left")
            label(vs, t, "  vs the base", font="caption", fg="text3", bg="surface1").pack(
                side="left"
            )
        if prof.chosen:
            why = (
                "You chose this setup. To change it, right-click another row in the list and"
                " pick Use as my settings."
            )
        elif best is h.base:
            why = (
                f"Nothing you tested beat the base for {goal.phrase} yet. Change one setting,"
                " capture the same scene again, and the best setup shows up here."
            )
        else:
            why = (
                f"The setup that beats the base by the most for {goal.phrase}. Visual cost isn't"
                " measured: if it looks worse than you accept, right-click another row and"
                " pick Use as my settings."
            )
        RichText(body, t, why, fg="text2", bg="surface1").pack(fill="x")

        keyw = px(24) + max(
            [t.fonts["mono_sm"].measure(k) for k, _ in prof.settings]
            + [t.fonts["mono_sm"].measure(k) for k, _, _ in prof.differs or []]
            + [px(120)]
        )
        if best is not h.base:
            if prof.differs is None:
                why = "In-game settings aren't read for this game: the name says what changed."
                rows = [("", why)]
            elif not prof.differs:
                why = "Same in-game settings as the base: the difference is the system or display."
                rows = [("", why)]
            else:
                rows = [(k, f"{a} → {b}") for k, a, b in prof.differs]
            self._section_box(
                page, "Changes from the base", rows, keyw, mono=True, note=h.base.name
            )

        # each tested change, from the setup before
        p = frame(page, t, "surface1", border="border")
        p.pack(fill="x", pady=(0, px(8)))
        ph = frame(p, t, "surface1")
        ph.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        silk(ph, t, "Changes tested", bg="surface1").pack(side="left")
        label(
            ph, t, "against the setup before", font="mono_xs", fg="text3", bg="surface1"
        ).pack(side="right")
        if not prof.tested:
            RichText(
                p, t,
                "Change one setting at a time and capture the same scene again: each change"
                " and what it did on this PC shows up here.",
                fg="text3", bg="surface1",
            ).pack(fill="x", padx=px(16), pady=(0, px(14)))  # fmt: skip
        grid = frame(p, t, "surface1")
        grid.pack(fill="x", padx=px(16), pady=(0, px(10)))
        grid.columnconfigure(1, weight=1)
        for i, tc in enumerate(prof.tested):
            level = {"better": "ok", "worse": "warn"}.get(tc.status, "idle")
            fg = {"better": "success", "worse": "warning"}.get(tc.status, "text3")
            Lamp(grid, t, level).grid(row=i, column=0, sticky="w", padx=(0, px(10)), pady=px(5))
            font = "body_sm" if tc.kind in feed.TYPED else "mono_sm"
            label(grid, t, tc.name, font=font, bg="surface1", anchor="w").grid(
                row=i, column=1, sticky="ew"
            )
            label(grid, t, tc.change, font="mono_sm", fg=fg, bg="surface1", anchor="e").grid(
                row=i, column=2, sticky="e", padx=(px(12), 0)
            )
            label(
                grid, t, f"×{tc.runs[0]} → ×{tc.runs[1]}", font="mono_xs", fg="text3",
                bg="surface1", anchor="e",
            ).grid(row=i, column=3, sticky="e", padx=(px(16), 0))  # fmt: skip

        if prof.settings:
            self._section_box(
                page, "In-game settings of this setup", list(prof.settings), keyw, mono=True,
                note=f"{len(prof.settings)} read",
            )  # fmt: skip
        notes = []
        if prof.left_out:
            notes.append(
                f"{prof.left_out} run{'s were' if prof.left_out != 1 else ' was'} left out of"
                " the combined numbers: far from the other runs of the same setup."
            )
        if prof.others:
            notes.append(
                f"{prof.others} setup{'s are' if prof.others != 1 else ' is'} another kind of run"
                " (another length or display), measured against its own base and not part of"
                " this profile."
            )
        for n in notes:
            RichText(page, t, n, font="caption", fg="text3", bg="background").pack(
                fill="x", pady=(px(2), 0)
            )
        self.page_profile.to_top()

    def _fill_runs(self) -> None:
        """A bundle's runs on the Summary page: which count, and each one's numbers."""
        t = self.t
        p = self.runs_panel
        for child in p.winfo_children():
            child.destroy()
        s = self.setup_for(self.selected[-1]) if self.selected else None
        if not s or s.count < 2:
            p.pack_forget()
            return
        head = frame(p, t, "surface1")
        head.pack(fill="x", padx=px(16), pady=(px(12), px(8)))
        silk(head, t, "Runs", bg="surface1").pack(side="left")
        used = len(s.used_runs)
        note = (
            f"mean of {used} · {s.count - used} left out" if used < s.count else f"mean of {used}"
        )
        label(head, t, note, font="mono_xs", fg="text3", bg="surface1").pack(side="right")
        grid = frame(p, t, "surface1")
        grid.pack(fill="x", padx=px(16), pady=(0, px(10)))
        cols = ("", "Started", "Length", "Average", "1% low", "Hitches", "")
        for c, name in enumerate(cols):
            grid.columnconfigure(c, weight=1 if c == 6 else 0)
            if name:
                silk(grid, t, name, bg="surface1").grid(
                    row=0, column=c, sticky="w" if c < 3 else "e", padx=(0, px(20)), pady=(0, px(4))
                )
        for i, ((folder, r), ok) in enumerate(zip(reversed(s.runs), reversed(s.used)), start=1):
            st = r["analysis"]["stats"]
            cells = [
                summary.when(r["capture"].get("started")),
                f"{st['duration_s']:.0f} s",
                f"{st['avg_fps']:,.1f}",
                f"{st['p1_fps']:,.1f}",
                f"{st.get('spike_time_pct') or 0:.2f}%",
            ]
            lamp = Lamp(grid, t, "ok" if ok else "warn")
            lamp.grid(row=i, column=0, sticky="w", padx=(0, px(10)), pady=px(4))
            widgets: list[tk.Widget] = [lamp]
            for c, text in enumerate(cells, start=1):
                w = label(grid, t, text, font="mono_sm", fg="text1" if ok else "text3",
                          bg="surface1")  # fmt: skip
                w.grid(row=i, column=c, sticky="w" if c < 3 else "e", padx=(0, px(20)))
                widgets.append(w)
            word = label(
                grid, t, "" if ok else "left out", font="caption", fg="warning", bg="surface1"
            )
            word.grid(row=i, column=6, sticky="w")
            widgets.append(word)
            for w in widgets:
                w.bind("<Button-3>", lambda e, f=folder: self._run_menu(e, s, f))
                w.bind("<Double-1>", lambda _e, f=folder: _open(f))
        if s.spread:
            RichText(
                p, t,
                "These runs disagree beyond run-to-run noise and none stands out. Run the scene"
                " once more, or take a run out if something changed between them.",
                fg="warning", bg="surface1",
            ).pack(fill="x", padx=px(16), pady=(0, px(12)))  # fmt: skip
        if s.mixed:
            what = ", ".join(f"{k} {a} → {b}" for k, a, b in s.mixed[:3])
            more = f" and {len(s.mixed) - 3} more" if len(s.mixed) > 3 else ""
            RichText(
                p, t,
                f"Not the same in every run: {what}{more}. A bundle's numbers mean most when its"
                " runs are repeats of one setup.",
                fg="warning", bg="surface1",
            ).pack(fill="x", padx=px(16), pady=(0, px(12)))  # fmt: skip
        p.pack(fill="x", pady=(0, px(8)), before=self.low_row)

    def _run_menu(self, event, s: feed.Setup, folder: Path) -> None:
        m = self._menu()
        m.add_command(label="Open folder", command=lambda: _open(folder))
        m.add_command(
            label="Copy this run's report", command=lambda: self._copy_report_of(folder, True)
        )
        m.add_separator()
        m.add_command(
            label="Take out of the bundle",
            command=lambda: self._save_user([folder], bundle=None),
        )
        m.add_command(label="Delete this run…", command=lambda: self.ask_delete([folder]))
        try:
            m.tk_popup(event.x_root, event.y_root)
        finally:
            m.grab_release()

    # --- data ---------------------------------------------------------------------------------

    def result_for(self, folder: Path) -> dict:
        return next(r for f, r in self.captures if f == folder)

    def current_result(self) -> dict | None:
        if not self.selected or self.profile_key:
            return None
        try:
            return self.view_for(self.selected[-1])
        except StopIteration:
            return None

    def trace_folder(self, folder: Path) -> Path:
        """The run whose trace stands for a row (the newest run that counts)."""
        s = self.setup_for(folder)
        return s.trace_folder if s else folder

    def refresh_history(self, select_first=False, select: Path | None = None) -> None:
        self.captures = [
            (f, r)
            for f, r in capture.list_captures(self.captures_root)
            if isinstance(r, dict) and "analysis" in r
        ]
        known = {f for f, _ in self.captures}
        self.selected = [f for f in self.selected if f in known]
        if select and select in known:
            self.selected = [select]
            self.profile_key = None
        elif (select_first or not self.selected) and self.captures:
            self.selected = [self.captures[0][0]]
        self.render_rail()
        self.render_main()

    def select(self, folder: Path, add: bool) -> None:
        if self.profile_key:  # leaving the profile: a plain click shows the row
            self.profile_key = None
            if not add:
                self.selected = []
        if add and self.selected and folder not in self.selected:
            self.selected = [*self.selected, folder]  # Ctrl+click adds; two rows compare
        elif add and folder in self.selected and len(self.selected) > 1:
            self.selected.remove(folder)  # Ctrl+click on a selected row takes it out
        elif not add and self.selected == [folder]:
            return
        else:
            self.selected = [folder]
        self.render_rail()
        self.render_main()
        if len(self.selected) == 2:
            self.tabs.select("Compare")

    def load_trace(self) -> None:
        folder = self.trace_folder(self.selected[-1]) if self.selected else None
        if folder is None:
            return
        if folder in self.traces:
            self._show_trace(self.traces[folder])
            return
        self.scope.show(None, "READING FRAMES")
        self.scope_scale.configure(text="")
        self._request_trace(folder)

    def _show_trace(self, tr: tracemod.Trace | None) -> None:
        self.scope.show(tr, "" if tr else "NO TRACE FOR THIS CAPTURE")
        self.scope_scale.configure(text=self.scope.scale_text())
        self._paint_channels()

    def _request_trace(self, folder: Path) -> None:
        if folder in self.loading:
            return
        self.loading.add(folder)
        result = self.result_for(folder)

        def work() -> None:
            try:
                tr = tracemod.get(folder, result)
            except Exception:  # a broken CSV must not break the window  # noqa: BLE001
                tr = None
            self.events.put(("trace", {"folder": folder, "trace": tr}))

        threading.Thread(target=work, daemon=True).start()

    # --- sharing with the dataset -------------------------------------------------------------

    def sharing(self) -> bool:
        """On, and agreed to for what this version shares."""
        return (
            self.sharer.available
            and self.settings.get("share") is True
            and int(self.settings.get("share_version") or 0) >= share.CONSENT_VERSION
        )

    def _share_status(self, outcome: share.Outcome | None = None) -> tuple[str, str, str]:
        if not self.sharing():
            return ("idle", "Sharing", "off")
        if outcome and outcome.error:
            return ("warn", "Sharing", "retries later")
        if self.share_busy:
            return ("info", "Sharing", "sending")
        total = outcome.total if outcome else self.sharer.total
        return ("ok", "Sharing", f"{total} shared")

    def consent_issue(self) -> tuple[str, str, list] | None:
        """Asked once: share captures and comparisons with the Frametrace dataset?"""
        if not self.sharer.available or self.sharing() or self.settings.get("share") is False:
            return None
        return (
            "info",
            (
                "Help build Frametrace's game skills: share your captures and comparisons,"
                " the ones already saved included, with the open Frametrace dataset? Sent:"
                " frame times, the game and its settings, your hardware and Windows settings."
                " Never sent: names, account IDs, file paths or the other apps you had open."
                " Turn it off or delete what you shared at any time."
            ),
            [("Share", self.consent_yes), ("Don't share", self.consent_no),
             ("What's sent", self.open_privacy)],
        )  # fmt: skip

    def consent_yes(self) -> None:
        self.share_var.set(True)
        self.apply_share()
        self.show_note("Sharing is on. Thank you!", "")

    def consent_no(self) -> None:
        self.share_var.set(False)
        self.apply_share()

    def open_privacy(self) -> None:
        import webbrowser

        webbrowser.open(share.PRIVACY_URL)

    def apply_share(self) -> None:
        self.settings["share"] = bool(self.share_var.get())
        if self.settings["share"]:
            self.settings["share_version"] = share.CONSENT_VERSION
        save_settings(self.settings)
        self.share_status = self._share_status()
        self.render_setup()
        self._render_foot()
        self.kick_share()

    def kick_share(self) -> None:
        """Send whatever changed since the last sync, on a worker thread."""
        if not self.sharing():
            return
        if self.share_busy:
            self.share_again = True
            return
        self.share_busy, self.share_again = True, False
        captures = list(self.captures)

        def work() -> None:
            outcome = self.sharer.sync(captures)
            self.events.put(("shared", {"outcome": outcome}))

        threading.Thread(target=work, daemon=True).start()

    def note_comparison(self, fa: Path, fb: Path, copied: bool = False) -> None:
        if self.sharing():
            self.sharer.note_pair(fa, fb, self.goal_key(), self.target_fps(), copied=copied)
            self.kick_share()

    def ask_forget(self) -> None:
        self.confirm = (
            (
                "Delete everything you've shared and turn sharing off? It's removed from the"
                " inbox now and from the public dataset at its next daily export. Copies other"
                " people already downloaded can't be recalled, but they can't be linked to you."
            ),
            [("Delete", self.do_forget), ("Cancel", self.cancel_confirm)],
        )
        self.render_setup()

    def do_forget(self) -> None:
        self.confirm = None
        self.render_setup()

        def work() -> None:
            try:
                n = self.sharer.forget()
                self.events.put(("forgot", {"deleted": n, "error": None}))
            except Exception as e:  # a failed delete must be reported, never lost  # noqa: BLE001
                self.events.put(("forgot", {"deleted": 0, "error": str(e)}))

        threading.Thread(target=work, daemon=True).start()

    # --- setup checks ------------------------------------------------------------------------

    def check_setup(self) -> None:
        try:
            exe = presentmon.find_presentmon()
        except presentmon.PresentMonNotFound:
            self.pm_status = ("error", "PresentMon", "not downloaded")
            self.trace_status = ("idle", "Trace access", "unknown")
            self.setup_issue = (
                "warn",
                (
                    "PresentMon (Intel's free frame-capture tool) isn't downloaded yet. "
                    "Frametrace fetches it from GitHub and checks its SHA-256."
                ),
                [("Download PresentMon", self.download_presentmon)],
            )
            self.start_btn.set_enabled(False)
            self.render_setup()
            self._render_foot()
            self.set_status()
            return
        self.pm_status = ("ok", "PresentMon", presentmon.identify(exe))
        ok, _why = presentmon.can_trace()
        if not ok:
            self.trace_status = ("error", "Trace access", "needs admin")
            self.setup_issue = (
                "error",
                (
                    "Recording needs administrator rights, or your account in the Performance Log "
                    "Users group (one-time setup, then sign out and back in)."
                ),
                [
                    ("Restart as administrator", self.restart_as_admin),
                    ("One-time setup", self.add_to_perf_log_users),
                ],
            )
            self.start_btn.set_enabled(False)
        else:
            self.trace_status = ("ok", "Trace access", "granted")
            self.setup_issue = None
            self.start_btn.set_enabled(True)
        self.render_setup()
        self._render_foot()
        self.set_status()
        self.recorder = capture.Recorder(
            exe,
            lambda kind, payload: self.events.put((kind, payload)),
            root=self.captures_root,
            system_provider=self.system_for_capture,
        )
        self.apply_hotkey()

    def download_presentmon(self) -> None:
        self.setup_issue = ("info", "Downloading PresentMon 2.6.0 and checking its SHA-256...", [])
        self.render_setup()
        self.set_status()

        def work() -> None:
            lines: list[str] = []
            ok = download.ensure_presentmon(say=lines.append)
            self.events.put(("download", {"ok": ok, "log": "\n".join(lines)}))

        threading.Thread(target=work, daemon=True).start()

    def restart_as_admin(self) -> None:
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        cwd = str(Path(__file__).resolve().parent.parent)
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", str(pyw if pyw.exists() else exe), "-m frametrace", cwd, 1
        )
        if rc > 32:
            self.on_close()

    def add_to_perf_log_users(self) -> None:
        member = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
        cmd = f"Add-LocalGroupMember -SID 'S-1-5-32-559' -Member '{member}'"
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe", f'-NoProfile -Command "{cmd}"', None, 0
        )
        if rc > 32:
            self.setup_issue = (
                "info",
                (
                    "Added your account to Performance Log Users (if you approved the prompt). "
                    "Sign out of Windows and back in, then start Frametrace again."
                ),
                [],
            )
            self.render_setup()

    # --- system info -------------------------------------------------------------------------

    def _load_system(self) -> None:
        info = sysinfo.collect()
        self.events.put(("system", {"info": info}))

    def system_for_capture(self) -> sysinfo.SystemInfo:
        """Called on the analysis thread: hardware from startup, settings read fresh."""
        return sysinfo.refresh_settings(self.system) if self.system else sysinfo.collect()

    # --- hotkey and capture ------------------------------------------------------------------

    def apply_hotkey(self) -> None:
        key = self.hotkey_var.get().strip()
        if self.listener and self.listener.hotkey == key and self.listener.is_alive():
            self.set_hotkey_note("", "text3")
            return
        try:
            new = hotkey.HotkeyListener(key, lambda: self.events.put(("hotkey", {})))
        except ValueError as e:
            self.set_hotkey_note(str(e), "warning")
            return
        if self.listener:
            self.listener.stop()
        error = new.start_and_wait()
        if error:
            self.listener = None
            self.set_hotkey_note(error, "warning")
        else:
            self.listener = new
            self.set_hotkey_note("", "text3")
            self.save()
        if self.start_btn.key:
            self.start_btn.key.configure(text=key)
        self.set_status()

    def set_hotkey_note(self, text: str, color: str) -> None:
        self.hotkey_note = (text, color)
        self._show_hotkey_note()

    def _show_hotkey_note(self) -> None:
        text, color = self.hotkey_note
        try:
            self.hotkey_label.configure(text=text, fg=self.t.c[color])
            if text:
                self.hotkey_label.grid()
            else:
                self.hotkey_label.grid_remove()
        except tk.TclError:
            pass
        self._paint_capture_more()

    def current_settings(self) -> capture.CaptureSettings:
        length = None if self.manual_var.get() else self.length_seconds()
        return capture.CaptureSettings(
            length_s=length,
            process_name=self.process_var.get().strip() or None,
            goal=self.goal_key(),
            target_fps=self.target_fps(),
            benchmark=self.benchmark_var.get().strip() or None,
        )

    def length_seconds(self) -> int:
        try:
            return max(5, min(3600, int(float(self.length_var.get()))))
        except ValueError:
            return DEFAULTS["length_s"]

    def toggle_capture(self) -> None:
        if not self.recorder or not self.start_btn.enabled:
            return
        self.recorder.toggle(self.current_settings())

    def set_status(self) -> None:
        t = self.t
        state = self.recorder.state if self.recorder else "idle"
        for child in self.status_hint.winfo_children():
            child.destroy()
        key = self.hotkey_var.get() or "the hotkey"
        hint = frame(self.status_hint, t)
        hint.pack(side="left")
        if self.setup_issue and self.setup_issue[0] in ("error", "warn", "info"):
            busy = self.setup_issue[0] == "info"
            self.status_lamp.set("info" if busy else "warn")
            set_silk(self.status_word, "Setup")
            label(
                hint,
                t,
                self.setup_issue[1] if busy else "Finish the setup below to record.",
                font="caption",
                fg="text3",
            ).pack(side="left")
            self.start_btn.set_text("Start capture")
        elif state == "recording" and self.recorder:
            secs, length = self.recorder.elapsed(), self.recorder.length_s
            self.status_lamp.set("error")
            set_silk(self.status_word, "Rec")
            label(
                hint, t, _clock(secs) + (f" / {_clock(length)}" if length else ""), font="mono_sm"
            ).pack(side="left")
            label(hint, t, "   press ", font="caption", fg="text3").pack(side="left")
            KeyCap(hint, t, key).pack(side="left")
            label(hint, t, " to stop", font="caption", fg="text3").pack(side="left")
            self.start_btn.set_text("Stop capture")
        elif state in ("stopping", "analyzing"):
            self.status_lamp.set("info")
            set_silk(self.status_word, "Analyzing")
            label(
                hint, t, "Stopping PresentMon and reading the frames.", font="caption", fg="text3"
            ).pack(side="left")
            self.start_btn.set_text("Analyzing")
        else:
            self.status_lamp.set("ok")
            set_silk(self.status_word, "Ready")
            label(hint, t, "Press ", font="caption", fg="text3").pack(side="left")
            KeyCap(hint, t, key).pack(side="left")
            what = (
                "until you press it again"
                if self.manual_var.get()
                else f"a {self.length_seconds()} s capture"
            )
            tag = self.benchmark_var.get().strip()
            if tag:
                what += " of "
            label(hint, t, f" in game to start {what}", font="caption", fg="text3").pack(
                side="left"
            )
            if tag:  # the tag the run will get, in the user's words
                label(hint, t, self._fit(tag, "caption", px(220)), font="caption",
                      fg="text1").pack(side="left")  # fmt: skip
            self.start_btn.set_text("Start capture")
        self.draw_progress()

    def draw_progress(self) -> None:
        c = self.progress
        c.delete("all")
        if not (self.recorder and self.recorder.state == "recording"):
            return
        length, w = self.recorder.length_s, c.winfo_width()
        if not length:  # manual: no end to measure against, so no bar
            return
        frac = min(1.0, self.recorder.elapsed() / length)
        c.create_rectangle(0, 0, w * frac, px(2), fill=self.t.c["accent"], width=0)

    def save(self) -> None:
        self.settings.update(
            hotkey=self.listener.hotkey if self.listener else self.settings["hotkey"],
            length_s=self.length_seconds(),
            manual=self.manual_var.get(),
            process_name=self.process_var.get().strip(),
            benchmark=" ".join(self.benchmark_var.get().split())[:80],
            sound=self.sound_var.get(),
            goal=self.goal_key(),
            target_fps=self.target_fps() or "",
        )
        save_settings(self.settings)
        self._paint_capture_more()
        if self.recorder is None or self.recorder.state == "idle":
            self.set_status()
            if not self.current_result():
                self.fill_summary(None, None)

    def toggle_theme(self) -> None:
        name = self.theme_var.get()
        if name == self.t.name:  # called directly, not from the switch: flip
            name = "light" if self.t.dark else "dark"
            self.theme_var.set(name)
        self.settings["theme"] = name
        save_settings(self.settings)
        tab = self.tabs.current
        self.build()
        if tab != "Summary":
            self.tabs.select(tab)

    # --- events ------------------------------------------------------------------------------

    def poll(self) -> None:
        if self.closed:
            return
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.handle(kind, payload)
        except queue.Empty:
            pass
        if self.recorder and self.recorder.state == "recording":
            self.set_status()
            self.update_recording()
        self.poll_job = self.root.after(100, self.poll)

    def handle(self, kind: str, p: dict) -> None:
        if kind == "hotkey":
            self.toggle_capture()
        elif kind == "started":
            self.profile_key = None
            if self.sound_var.get():
                capture.beep("start")
            self.capture_error = None
            self.render_setup()
            who = p.get("foreground") or "?"
            self.record_info = {"sub": f"window in front: {who}"}
            self.tabs.select("Summary", notify=False)
            self.render_main()
            self.set_status()
        elif kind == "stopping":
            if self.sound_var.get():
                capture.beep("stop")
            self.render_main()
            self.set_status()
        elif kind == "done":
            self.record_info = {}
            folder = p.get("folder")
            self.traces.pop(folder, None)
            self.refresh_history(select=folder)
            self.set_status()
            self.shown_text = p["report"]
            self.copy_shown(note="Report copied to the clipboard.")
            self.kick_share()
        elif kind == "error":
            if self.sound_var.get():
                capture.beep("error")
            self.record_info = {}
            self.capture_error = "Capture failed. " + p["message"]
            self.render_setup()
            self.render_main()
            self.set_status()
        elif kind == "system":
            self.system = p["info"]
            self._render_foot()
        elif kind == "shared":
            self.share_busy = False
            self.share_status = self._share_status(p["outcome"])
            self._render_foot()
            if self.share_again:
                self.kick_share()
        elif kind == "forgot":
            if p["error"]:
                self.capture_error = "Couldn't delete your shared data: " + p["error"]
                self.render_setup()
            else:
                n = p["deleted"]
                self.share_var.set(False)  # turning it on again starts over with a new ID
                self.settings["share"] = False
                save_settings(self.settings)
                self.show_note(f"Deleted {n} shared item{'s' if n != 1 else ''}. Sharing is off.", "")
            self.share_status = self._share_status()
            self._render_foot()
        elif kind == "trace":
            self.traces[p["folder"]] = p["trace"]
            self.loading.discard(p["folder"])
            if (
                self.selected
                and self.trace_folder(self.selected[-1]) == p["folder"]
                and not self.profile_key
                and not (
                    self.recorder and self.recorder.state in ("recording", "stopping", "analyzing")
                )
            ):
                self._show_trace(p["trace"])
            if self.shown == "Compare" and p["folder"] in getattr(self, "compare_folders", ()):
                self.draw_compare_scope()
        elif kind == "download":
            if p["ok"]:
                self.check_setup()
            else:
                self.setup_issue = (
                    "error",
                    "Download failed: " + p["log"][-400:],
                    [("Retry", self.download_presentmon)],
                )
                self.render_setup()
            self.set_status()

    # --- actions ------------------------------------------------------------------------------

    def _to_clipboard(self, text: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def copy_shown(self, note: str = "") -> None:
        if not self.shown_text:
            return
        self._to_clipboard(self.shown_text)
        what = {"Compare": "Comparison", "Profile": "Profile"}.get(self.shown, "Report")
        if self.shown == "Compare" and len(getattr(self, "compare_folders", ())) == 2:
            self.note_comparison(*self.compare_folders, copied=True)
        self.show_note(
            note or f"{what} copied to the clipboard.", f"{len(self.shown_text):,} chars"
        )

    def show_note(self, text: str, detail: str = "") -> None:
        t = self.t
        for child in self.note.winfo_children():
            child.destroy()
        box = tk.Frame(
            self.note,
            bg=t.c["surface1"],
            highlightthickness=1,
            highlightbackground=t.c["border_visible"],
            padx=px(12),
            pady=px(7),
        )
        box.pack()
        Lamp(box, t, "ok").pack(side="left", padx=(0, px(10)))
        label(box, t, text, bg="surface1").pack(side="left")
        if detail:
            label(box, t, detail, font="mono_xs", fg="text3", bg="surface1").pack(
                side="left", padx=(px(10), 0)
            )
        if self.note_job:
            self.root.after_cancel(self.note_job)
        self.note_job = self.root.after(NOTE_MS, self._clear_note)

    def _clear_note(self) -> None:
        self.note_job = None
        try:
            for child in self.note.winfo_children():
                child.destroy()
        except tk.TclError:
            pass

    def open_selected(self) -> None:
        if self.selected:
            _open(self.folder_of(self.selected[-1]))
        else:
            root = self.captures_root or capture.DEFAULT_ROOT
            root.mkdir(parents=True, exist_ok=True)
            _open(root)

    # --- shutdown ----------------------------------------------------------------------------

    def on_close(self) -> None:
        self.closed = True
        for job in (self.poll_job, self.note_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except tk.TclError:
                    pass
        if self.listener:
            self.listener.stop()
        if self.recorder and self.recorder.state == "recording":
            try:  # don't leave an ETW session running
                subprocess.run(
                    presentmon.terminate_command(self.recorder.exe),
                    timeout=10,
                    capture_output=True,
                    check=False,
                    creationflags=capture.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        self.root.destroy()


class TextDialog:
    """A small modal question with one text field, in the window's theme."""

    @staticmethod
    def ask(
        app: App, title: str, prompt: str, initial: str = "", choices: list[str] | None = None
    ) -> str | None:
        """The text entered (may be empty), or None when cancelled."""
        t, root = app.t, app.root
        win = tk.Toplevel(root, bg=t.c["background"])
        win.title(title)
        win.transient(root)
        win.resizable(False, False)
        win.bind("<Map>", lambda e: e.widget is win and theme.set_title_bar(win, t.dark, t.c))
        body = frame(win, t)
        body.pack(fill="both", padx=px(20), pady=(px(18), px(16)))
        label(body, t, title, font="subheading", anchor="w").pack(fill="x")
        label(body, t, prompt, fg="text2", wraplength=px(380), justify="left", anchor="w").pack(
            fill="x", pady=(px(6), px(14))
        )
        var = tk.StringVar(value=initial)
        if choices:
            field = ttk.Combobox(body, textvariable=var, values=choices, font=t.fonts["body_sm"])
        else:
            field = ttk.Entry(body, textvariable=var, font=t.fonts["body_sm"])
        field.pack(fill="x")
        out: dict[str, str | None] = {"value": None}

        def done(value: str | None) -> None:
            out["value"] = value
            win.grab_release()
            win.destroy()

        row = frame(body, t)
        row.pack(fill="x", pady=(px(16), 0))
        FlatButton(row, t, "Save", lambda: done(var.get().strip()), "primary", small=True).pack(
            side="right"
        )
        FlatButton(row, t, "Cancel", lambda: done(None), "ghost", small=True).pack(
            side="right", padx=(0, px(8))
        )
        win.bind("<Return>", lambda _e: done(var.get().strip()))
        win.bind("<Escape>", lambda _e: done(None))
        win.protocol("WM_DELETE_WINDOW", lambda: done(None))
        win.update_idletasks()
        x = root.winfo_rootx() + (root.winfo_width() - win.winfo_reqwidth()) // 2
        y = root.winfo_rooty() + (root.winfo_height() - win.winfo_reqheight()) // 3
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        field.focus_set()
        field.select_range(0, "end")
        field.icursor("end")
        try:
            win.grab_set()
        except tk.TclError:  # another grab (a menu) is still active
            pass
        root.wait_window(win)
        return out["value"]


def _open(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
        try:  # group the window under Frametrace's own icon in the taskbar, not Python's
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass
    theme.load_fonts()  # before Tk enumerates fonts
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
