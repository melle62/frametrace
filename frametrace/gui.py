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
    hotkey,
    presentmon,
    report,
    summary,
    sysinfo,
    theme,
)
from frametrace import trace as tracemod
from frametrace.instruments import (
    Check,
    FlatButton,
    KeyCap,
    Lamp,
    Readout,
    Scope,
    ScrollFrame,
    Segmented,
    SplitBar,
    Tabs,
    frame,
    label,
    rule,
    silk,
    wordmark,
)

SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "Frametrace" / "settings.json"
DEFAULTS = {
    "hotkey": "F10",
    "length_s": 30,
    "manual": False,
    "process_name": "",
    "sound": True,
    "theme": "dark",
}
LENGTHS = ["10", "20", "30", "60", "90", "100", "120", "180", "300"]
TABS = ["Summary", "Report", "System", "Compare"]


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
        self.setup_issue: tuple[str, str, list] | None = None  # (level, text, buttons)
        self.capture_error: str | None = None
        self.record_info: dict = {}
        self.note_job: str | None = None
        self.pm_status = ("idle", "PresentMon", "checking")
        self.trace_status = ("idle", "Trace access", "checking")

        root.title("Frametrace")
        root.geometry("1200x820")
        root.minsize(1000, 700)
        self.fonts = theme.make_fonts(root)
        # state shared by both themes: the variables survive a rebuild
        self.hotkey_var = tk.StringVar(value=self.settings["hotkey"])
        self.manual_var = tk.BooleanVar(value=self.settings["manual"])
        self.length_var = tk.StringVar(value=str(self.settings["length_s"]))
        self.process_var = tk.StringVar(value=self.settings["process_name"])
        self.sound_var = tk.BooleanVar(value=self.settings["sound"])
        self.hotkey_note = ("", "text3")

        self.build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        threading.Thread(target=self._load_system, daemon=True).start()
        self.check_setup()
        self.refresh_history(select_first=True)
        root.after(100, self.poll)

    # --- building -----------------------------------------------------------------------------

    def build(self) -> None:
        for child in self.root.winfo_children():
            child.destroy()
        self.t = t = theme.apply(self.root, self.settings.get("theme", "dark"), self.fonts)
        self.root.after(50, lambda: theme.set_title_bar(self.root, t.dark))

        self._build_topbar()
        self.progress = tk.Canvas(
            self.root, height=2, bg=t.c["background"], highlightthickness=0, bd=0
        )
        self.progress.pack(fill="x")
        rule(self.root, t).pack(fill="x")
        body = frame(self.root, t)
        body.pack(fill="both", expand=True)
        self._build_rail(body)
        rule(body, t, vertical=True).pack(side="left", fill="y")
        self._build_main(body)
        self.render_rail()
        self.render_setup()
        self.render_main()
        self.set_status()

    def _build_topbar(self) -> None:
        t = self.t
        bar = frame(self.root, t, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        wordmark(bar, t).pack(side="left", padx=(20, 0))
        rule(bar, t, vertical=True).pack(side="left", fill="y", padx=24, pady=14)
        self.status_lamp = Lamp(bar, t, "idle")
        self.status_lamp.pack(side="left")
        self.status_word = silk(bar, t, "Ready", fg="text1")
        self.status_word.pack(side="left", padx=(8, 12))
        self.status_hint = frame(bar, t)
        self.status_hint.pack(side="left")

        self.start_btn = FlatButton(
            bar, t, "Start capture", self.toggle_capture, "primary", key=self.hotkey_var.get()
        )
        self.start_btn.pack(side="right", padx=(8, 16))
        mode = "Light" if t.dark else "Dark"
        FlatButton(bar, t, mode, self.toggle_theme, "ghost", small=True).pack(side="right")

    def _build_rail(self, body: tk.Frame) -> None:
        t = self.t
        rail = frame(body, t, width=296)
        rail.pack(side="left", fill="y")
        rail.pack_propagate(False)

        sec = frame(rail, t)
        sec.pack(fill="x", padx=16, pady=(16, 12))
        silk(sec, t, "Capture").pack(anchor="w", pady=(0, 12))
        grid = frame(sec, t)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)

        label(grid, t, "Hotkey", fg="text2").grid(row=0, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(
            grid,
            textvariable=self.hotkey_var,
            values=hotkey.SUGGESTED,
            width=12,
            font=t.fonts["mono_sm"],
        )
        combo.grid(row=0, column=1, sticky="ew", pady=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_hotkey())
        combo.bind("<Return>", lambda _e: self.apply_hotkey())
        combo.bind("<FocusOut>", lambda _e: self.apply_hotkey())
        self.hotkey_label = label(
            grid,
            t,
            self.hotkey_note[0],
            font="caption",
            fg=self.hotkey_note[1],
            wraplength=190,
            justify="left",
        )
        self.hotkey_label.grid(row=1, column=1, sticky="w")

        label(grid, t, "Length", fg="text2").grid(
            row=2, column=0, sticky="w", pady=(8, 4), padx=(0, 12)
        )
        ln = frame(grid, t)
        ln.grid(row=2, column=1, sticky="ew", pady=(8, 4))
        Segmented(ln, t, [("Fixed", False), ("Manual", True)], self.manual_var, self.save).pack(
            side="left"
        )
        self.length_box = ttk.Combobox(
            ln, textvariable=self.length_var, values=LENGTHS, width=5, font=t.fonts["mono_sm"]
        )
        self.length_box.pack(side="left", padx=(6, 4))
        self.length_box.bind("<<ComboboxSelected>>", lambda _e: self.save())
        self.length_box.bind("<FocusOut>", lambda _e: self.save())
        label(ln, t, "s", font="mono_sm", fg="text3").pack(side="left")

        label(grid, t, "Game", fg="text2").grid(row=3, column=0, sticky="w", pady=(8, 4))
        entry = ttk.Entry(
            grid, textvariable=self.process_var, style="Mono.TEntry", font=t.fonts["mono_sm"]
        )
        entry.grid(row=3, column=1, sticky="ew", pady=(8, 2))
        entry.bind("<FocusOut>", lambda _e: self.save())
        label(grid, t, "exe name, or empty to auto-detect", font="caption", fg="text3").grid(
            row=4, column=1, sticky="w"
        )
        Check(sec, t, "Beep on start and stop", self.sound_var, self.save).pack(
            anchor="w", pady=(12, 0)
        )

        rule(rail, t).pack(fill="x")
        foot = frame(rail, t)
        foot.pack(side="bottom", fill="x", padx=16, pady=12)
        self.foot = foot
        rule(rail, t).pack(side="bottom", fill="x")

        head = frame(rail, t)
        head.pack(fill="x", padx=16, pady=(14, 6))
        silk(head, t, "Captures").pack(side="left")
        self.count_label = label(head, t, "", font="mono_xs", fg="text3")
        self.count_label.pack(side="right")
        self.list = ScrollFrame(rail, t)
        self.list.pack(fill="both", expand=True, padx=(8, 0))

    def _build_main(self, body: tk.Frame) -> None:
        t = self.t
        main = frame(body, t)
        main.pack(side="left", fill="both", expand=True)
        self.main = main

        self.banner = frame(main, t)
        self.header = frame(main, t)
        self.header.pack(fill="x", padx=24, pady=(18, 10))
        self.tabs = Tabs(main, t, TABS, self.show_tab)
        self.tabs.pack(fill="x", padx=24)
        self.tab_hint = silk(
            self.tabs.extra, t, "Ctrl+click a second capture to compare", fg="text4"
        )
        self.tab_hint.pack(side="right")

        actions = frame(main, t)
        actions.pack(side="bottom", fill="x", padx=24, pady=(10, 16))
        self.copy_btn = FlatButton(actions, t, "Copy report", self.copy_shown, "secondary")
        self.copy_btn.pack(side="left")
        self.folder_btn = FlatButton(actions, t, "Open folder", self.open_selected, "ghost")
        self.folder_btn.pack(side="left", padx=(8, 0))
        self.compare_btn = FlatButton(
            actions, t, "Compare", lambda: self.tabs.select("Compare"), "ghost"
        )
        self.compare_btn.pack(side="left", padx=(4, 0))
        self.note = frame(actions, t)
        self.note.pack(side="right")

        self.pages = frame(main, t)
        self.pages.pack(fill="both", expand=True, padx=24, pady=(12, 0))
        self.page_summary = ScrollFrame(self.pages, t)
        self._build_summary(self.page_summary.inner)
        self.page_text = frame(self.pages, t, border="border_visible")
        self.text = tk.Text(
            self.page_text, wrap="word", font=t.fonts["mono"], bg=t.c["background"], fg=t.c["text1"],
            insertbackground=t.c["text1"], selectbackground=t.c["surface3"], selectforeground=t.c["text1"],
            relief="flat", bd=0, padx=16, pady=14, highlightthickness=0, spacing1=1, spacing3=1,
        )  # fmt: skip
        sb = ttk.Scrollbar(self.page_text, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("head", foreground=t.c["text1"], font=t.fonts["mono"])
        self.text.tag_configure("warn", foreground=t.c["warning"])
        self.text.tag_configure("ok", foreground=t.c["success"])
        self.text.tag_configure("dim", foreground=t.c["text2"])
        self.page_system = ScrollFrame(self.pages, t)
        self.shown = "Summary"
        self.shown_text = ""

    def _build_summary(self, page: tk.Frame) -> None:
        t = self.t
        # verdict
        v = frame(page, t, "surface1", border="border")
        v.pack(fill="x", pady=(0, 8))
        v.columnconfigure(0, weight=1)
        self.verdict_head = label(v, t, "", font="heading", bg="surface1", anchor="w")
        self.verdict_head.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 2))
        self.verdict_text = label(
            v, t, "", fg="text2", bg="surface1", anchor="w", justify="left", wraplength=470
        )
        self.verdict_text.grid(row=1, column=0, sticky="w", padx=16, pady=(0, 14))
        v.bind(
            "<Configure>",
            lambda e: self.verdict_text.configure(wraplength=max(240, e.width - 330 - 72)),
        )
        split = frame(v, t, "surface1", width=330)
        split.grid(row=0, column=1, rowspan=2, sticky="se", padx=16, pady=16)
        self.split = SplitBar(split, t)
        self.split.configure(width=330)
        self.split.pack(fill="x")
        self.split_legend = frame(split, t, "surface1")
        self.split_legend.pack(fill="x", pady=(8, 0))

        # scope
        s = frame(page, t, "surface1", border="border")
        s.pack(fill="x", pady=(0, 8))
        sh = frame(s, t, "surface1")
        sh.pack(fill="x", padx=16, pady=(12, 10))
        self.scope_title = silk(sh, t, "Frame time", bg="surface1")
        self.scope_title.pack(side="left")
        for key, name in (("ch3", "CH3 CPU"), ("ch2", "CH2 GPU"), ("ch1", "CH1 FRAME")):
            self._channel_toggle(sh, key, name).pack(side="right", padx=(6, 0))
        self.scope = Scope(s, t, height=184)
        self.scope.pack(fill="x", padx=16, pady=(0, 16))

        # readouts
        row = frame(page, t)
        row.pack(fill="x", pady=(0, 8))
        self.readouts: list[Readout] = []
        for i in range(5):
            row.columnconfigure(i, weight=1, uniform="ro")
            r = Readout(
                row,
                t,
                ["Average", "1% low", "CPU-side 1% low", "PC latency", "P95 latency"][i],
                "ch1" if i == 0 else None,
            )
            r.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0))
            self.readouts.append(r)

        # checks and details
        low = frame(page, t)
        low.pack(fill="x", pady=(0, 8))
        low.columnconfigure(0, weight=4, uniform="low")
        low.columnconfigure(1, weight=3, uniform="low")
        self.checks_panel = frame(low, t, "surface1", border="border")
        self.checks_panel.grid(row=0, column=0, sticky="nsew")
        self.details_panel = frame(low, t, "surface1", border="border")
        self.details_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    def _channel_toggle(self, parent, key: str, name: str) -> tk.Frame:
        t = self.t
        f = tk.Frame(
            parent,
            bg=t.c["surface2"],
            highlightthickness=1,
            highlightbackground=t.c["text3"],
            cursor="hand2",
            padx=7,
            pady=3,
        )
        sw = tk.Frame(f, width=8, height=8, bg=t.c[key])
        sw.pack(side="left", padx=(0, 6))
        lab = label(f, t, name, font="mono_xs", bg="surface2")
        lab.pack(side="left")

        def flip(_e=None):
            visible = self.scope.toggle(key)
            bg = t.c["surface2"] if visible else t.c["surface1"]
            f.configure(bg=bg, highlightbackground=t.c["text3" if visible else "border_visible"])
            lab.configure(bg=bg, fg=t.c["text1" if visible else "text3"])
            sw.configure(bg=t.c[key] if visible else t.c["text4"])

        for w in (f, sw, lab):
            w.bind("<Button-1>", flip)
        return f

    # --- rendering ----------------------------------------------------------------------------

    def render_rail(self) -> None:
        t = self.t
        inner = self.list.inner
        for child in inner.winfo_children():
            child.destroy()
        self.count_label.configure(text=str(len(self.captures)))
        if not self.captures:
            label(inner, t, "Captures appear here.", fg="text3").pack(anchor="w", padx=8, pady=8)
        for folder, result in self.captures:
            try:
                level, name, meta, fps, sub = summary.rail_row(result)
            except (KeyError, TypeError):
                continue
            self._rail_row(inner, folder, level, name, meta, fps, sub)
        self._render_foot()

    def _rail_row(self, parent, folder: Path, level, name, meta, fps, sub) -> None:
        t = self.t
        sel = folder in self.selected
        bg = "surface2" if sel else "background"
        row = tk.Frame(parent, bg=t.c[bg], cursor="hand2")
        row.pack(fill="x", padx=(0, 8), pady=(0, 1))
        edge = tk.Frame(row, width=2, bg=t.c["accent"] if sel else t.c[bg])
        edge.pack(side="left", fill="y")
        if sel and len(self.selected) == 2:
            mark = "A" if folder == self.selected[0] else "B"
            lamp = label(row, t, mark, font="mono_xs", fg="text1", bg=bg)
            lamp.pack(side="left", padx=(8, 10))
        else:
            lamp = Lamp(row, t, level)
            lamp.pack(side="left", padx=(8, 10))
        mid = tk.Frame(row, bg=t.c[bg])
        mid.pack(side="left", fill="x", expand=True, pady=8)
        a = label(mid, t, name, bg=bg, anchor="w")
        a.pack(fill="x")
        b = label(mid, t, meta, font="mono_xs", fg="text3", bg=bg, anchor="w")
        b.pack(fill="x")
        right = tk.Frame(row, bg=t.c[bg])
        right.pack(side="right", padx=(4, 8))
        c = label(right, t, fps, font="mono_sm", bg=bg, anchor="e")
        c.pack(fill="x")
        d = label(right, t, sub, font="mono_xs", fg="text3", bg=bg, anchor="e")
        d.pack(fill="x")
        widgets = (row, mid, right, a, b, c, d, lamp)

        def paint(hover: bool) -> None:
            if folder in self.selected:
                return
            col = t.c["surface1" if hover else "background"]
            for w in widgets:
                w.configure(bg=col)
            edge.configure(bg=col)

        for w in widgets:
            w.bind("<Button-1>", lambda _e, f=folder: self.select(f, add=False))
            w.bind("<Control-Button-1>", lambda _e, f=folder: self.select(f, add=True))
            w.bind("<Double-1>", lambda _e, f=folder: _open(f))
            if not isinstance(w, Lamp):
                w.bind("<Enter>", lambda _e: paint(True), add="+")
                w.bind("<Leave>", lambda _e: paint(False), add="+")

    def _render_foot(self) -> None:
        t = self.t
        for child in self.foot.winfo_children():
            child.destroy()
        for level, name, value in (self.pm_status, self.trace_status):
            r = frame(self.foot, t)
            r.pack(fill="x", pady=2)
            Lamp(r, t, level).pack(side="left", padx=(0, 8))
            label(r, t, name, font="caption", fg="text2").pack(side="left")
            label(r, t, value, font="mono_xs", fg="text3").pack(side="right")
        line = self.system_line()
        if line:
            label(
                self.foot,
                t,
                line,
                font="mono_xs",
                fg="text3",
                wraplength=260,
                justify="left",
                anchor="w",
            ).pack(fill="x", pady=(8, 0))

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
        return " · ".join(p for p in parts if p)

    def render_setup(self) -> None:
        t = self.t
        for child in self.banner.winfo_children():
            child.destroy()
        issue = self.setup_issue or (
            ("error", self.capture_error, []) if self.capture_error else None
        )
        if not issue:
            self.banner.pack_forget()
            return
        level, text, buttons = issue
        bgkey = {"error": "error_bg", "warn": "warning_bg"}.get(level, "surface2")
        box = tk.Frame(
            self.banner,
            bg=t.c[bgkey],
            highlightthickness=1,
            highlightbackground=theme.mix(
                t.c[{"error": "error", "warn": "warning"}.get(level, "text3")], t.c[bgkey], 0.4
            ),
        )
        box.pack(fill="x")
        Lamp(box, t, level).pack(side="left", padx=(16, 12))
        label(box, t, text, bg=bgkey, justify="left", anchor="w", wraplength=560).pack(
            side="left", fill="x", expand=True, pady=12
        )
        for name, cmd in reversed(buttons):
            FlatButton(box, t, name, cmd, "secondary", small=True).pack(side="right", padx=(0, 12))
        self.banner.pack(fill="x", padx=24, pady=(16, 0), before=self.header)

    def render_main(self) -> None:
        """Header, summary and tabs for the selected capture (or the empty/recording view)."""
        for child in self.header.winfo_children():
            child.destroy()
        result = self.current_result()
        recording = self.recorder is not None and self.recorder.state in (
            "recording",
            "stopping",
            "analyzing",
        )
        if recording:
            self._header("REC", "Recording", self.record_info.get("sub", ""), [])
        elif result:
            cap = result["capture"]
            self._header(
                summary.initials(cap["app"]),
                cap["app"],
                summary.subtitle(result),
                summary.tags(result),
            )
        else:
            where = self.captures_root or capture.DEFAULT_ROOT
            self._header("--", "Ready when you are", f"Captures are saved to {where}", [])
        two = len(self.selected) == 2
        self.tabs.set_disabled("Compare", not two)
        self.tabs.set_disabled("Report", not result)
        self.tabs.set_disabled("System", not result)
        self.tab_hint.configure(text="" if two else "CTRL+CLICK A SECOND CAPTURE TO COMPARE")
        self.compare_btn.set_enabled(two)
        self.folder_btn.set_enabled(bool(result))
        self.copy_btn.set_enabled(bool(result))
        if self.tabs.current not in ("Summary",) and (
            not result or (self.tabs.current == "Compare" and not two)
        ):
            self.tabs.select("Summary", notify=False)
        self.fill_summary(result, recording)
        self.show_tab(self.tabs.current)

    def _header(self, initials: str, title: str, sub: str, tags: list[str]) -> None:
        t = self.t
        av = label(
            self.header, t, initials, font="mono_sm", fg="text2", bg="surface2", width=4, height=2
        )
        av.configure(highlightthickness=1, highlightbackground=t.c["border"])
        av.pack(side="left", padx=(0, 12))
        mid = frame(self.header, t)
        mid.pack(side="left", fill="x", expand=True)
        label(mid, t, title, font="subheading", anchor="w").pack(fill="x")
        label(mid, t, sub, font="mono_xs", fg="text3", anchor="w").pack(fill="x", pady=(2, 0))
        for tag in reversed(tags):
            label(
                self.header, t, tag, font="mono_xs", fg="text2", bg="surface2", padx=7, pady=3
            ).pack(side="right", padx=(6, 0))

    def fill_summary(self, result: dict | None, recording: bool) -> None:
        t = self.t
        for child in self.split_legend.winfo_children():
            child.destroy()
        if recording:
            key = self.hotkey_var.get()
            self.verdict_head.configure(text="Recording.")
            length = self.recorder.length_s if self.recorder else None
            self.verdict_text.configure(
                text=f"Play normally. Press {key} to stop"
                + (f", or wait for {length} s." if length else ".")
            )
            self.split.set(0, 0, 0)
            for r in self.readouts:
                r.set(None, "", "recording")
            self._fill_checks([], "Checks run when the capture ends.")
            self._fill_details([])
            self.scope_title.configure(text="FRAME TIME · LIVE")
            return
        if not result:
            key = self.hotkey_var.get()
            self.verdict_head.configure(text="No captures yet.")
            length = (
                "until you press it again"
                if self.manual_var.get()
                else f"for {self.length_seconds()} s"
            )
            self.verdict_text.configure(
                text=f"Start a game, press {key} and play normally. Frametrace records {length}, "
                "then shows the verdict here and copies the report to your clipboard."
            )
            self.split.set(0, 0, 0)
            for r in self.readouts:
                r.set(None, "", "no data")
            self.scope.show(None, "NO CAPTURES YET")
            self._fill_checks(
                [],
                "Play the same scene each time (a benchmark map, replay or fixed route) so captures compare.",
            )
            self._fill_details([])
            self.scope_title.configure(text="FRAME TIME")
            return

        head, sentence = summary.verdict(result)
        self.verdict_head.configure(text=head)
        self.verdict_text.configure(text=sentence)
        b = result["analysis"]["bottleneck"]
        if b.get("available"):
            self.split.set(b["gpu_pct"], b["cpu_pct"], b["wait_pct"])
            for key, name, pct in (
                ("ch2", "GPU", b["gpu_pct"]),
                ("ch3", "CPU", b["cpu_pct"]),
                ("text4", "Waiting", b["wait_pct"]),
            ):
                item = frame(self.split_legend, t, "surface1")
                item.pack(side="left", padx=(0, 14))
                tk.Frame(item, width=8, height=8, bg=t.c[key]).pack(side="left", padx=(0, 6))
                label(item, t, name, font="caption", fg="text3", bg="surface1").pack(side="left")
                label(item, t, f"{pct:.0f}%", font="mono_xs", bg="surface1").pack(
                    side="left", padx=(4, 0)
                )
        else:
            self.split.set(0, 0, 0)
        for r, v in zip(self.readouts, summary.readouts(result), strict=True):
            r.set(v.value, v.unit, v.sub, title=v.title)
        dur = result["analysis"]["stats"]["duration_s"]
        self.scope_title.configure(text=f"FRAME TIME · {dur:.0f} S")
        self._fill_checks(result.get("checks", []), "")
        self._fill_details(summary.details(result))
        self.load_trace()

    def _fill_checks(self, checks: list[dict], empty: str) -> None:
        t = self.t
        p = self.checks_panel
        for child in p.winfo_children():
            child.destroy()
        head = frame(p, t, "surface1")
        head.pack(fill="x", padx=16, pady=(12, 8))
        silk(head, t, "Checks", bg="surface1").pack(side="left")
        if checks:
            ok = sum(1 for c in checks if c["level"] == "ok")
            warn = sum(1 for c in checks if c["level"] == "warn")
            label(
                head, t, f"{ok} ok · {warn} to look at", font="mono_xs", fg="text3", bg="surface1"
            ).pack(side="right")
        if not checks:
            label(
                p, t, empty, fg="text3", bg="surface1", wraplength=420, justify="left", anchor="w"
            ).pack(fill="x", padx=16, pady=(0, 14))
            return
        order = {"warn": 0, "info": 1, "ok": 2}
        for i, c in enumerate(sorted(checks, key=lambda c: order.get(c["level"], 3))):
            if i:
                rule(p, t).pack(fill="x", padx=16)
            r = frame(p, t, "surface1")
            r.pack(fill="x", padx=16, pady=6)
            Lamp(r, t, c["level"]).pack(side="left", anchor="n", pady=(5, 0), padx=(0, 10))
            label(
                r,
                t,
                c["text"],
                fg="text2",
                bg="surface1",
                wraplength=400,
                justify="left",
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
        frame(p, t, "surface1", height=8).pack()

    def _fill_details(self, rows: list[tuple[str, str]]) -> None:
        t = self.t
        p = self.details_panel
        for child in p.winfo_children():
            child.destroy()
        head = frame(p, t, "surface1")
        head.pack(fill="x", padx=16, pady=(12, 8))
        silk(head, t, "Details", bg="surface1").pack(side="left")
        label(head, t, "presenting thread", font="mono_xs", fg="text3", bg="surface1").pack(
            side="right"
        )
        for i, (k, v) in enumerate(rows):
            if i:
                rule(p, t).pack(fill="x", padx=16)
            r = frame(p, t, "surface1")
            r.pack(fill="x", padx=16, pady=6)
            label(r, t, k, fg="text2", bg="surface1").pack(side="left")
            label(r, t, v, font="mono_sm", bg="surface1").pack(side="right")

    def show_tab(self, name: str) -> None:
        self.shown = name
        for page in (self.page_summary, self.page_text, self.page_system):
            page.pack_forget()
        result = self.current_result()
        if name == "Summary":
            self.page_summary.pack(fill="both", expand=True)
            self.shown_text = report.render(result) if result else ""
        elif name == "Report" and result:
            self.set_text(report.render(result))
            self.page_text.pack(fill="both", expand=True)
        elif name == "Compare" and len(self.selected) == 2:
            pair = [self.result_for(f) for f in self.selected]
            older, newer = sorted(pair, key=lambda r: r["capture"].get("started", ""))
            self.set_text(report.compare(older, newer))
            self.page_text.pack(fill="both", expand=True)
        elif name == "System" and result:
            self.fill_system(result)
            self.page_system.pack(fill="both", expand=True)
            self.shown_text = report.render(result)
        self.copy_btn.set_text("Copy comparison" if name == "Compare" else "Copy report")

    def set_text(self, text: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        for line in text.splitlines():
            tag = ()
            if line.startswith(("## ", "Frametrace report", "Frametrace compare")):
                tag = ("head",)
            elif line.startswith("[!]"):
                tag = ("warn",)
            elif line.startswith("[ok]"):
                tag = ("ok",)
            elif line.startswith(("(", "Detected via")):
                tag = ("dim",)
            self.text.insert("end", line + "\n", tag)
        self.text.configure(state="disabled")
        self.shown_text = text

    def fill_system(self, result: dict) -> None:
        t = self.t
        inner = self.page_system.inner
        for child in inner.winfo_children():
            child.destroy()
        box = frame(inner, t, "surface1", border="border")
        box.pack(fill="x")
        silk(box, t, "System at capture time", bg="surface1").pack(
            anchor="w", padx=16, pady=(12, 8)
        )
        for i, (k, v) in enumerate(
            summary.system_rows(report.render_system(result.get("system") or {}))
        ):
            if i:
                rule(box, t).pack(fill="x", padx=16)
            r = frame(box, t, "surface1")
            r.pack(fill="x", padx=16, pady=7)
            label(r, t, k, fg="text3", bg="surface1", width=10, anchor="w").pack(side="left")
            label(
                r, t, v, font="mono_sm", bg="surface1", anchor="w", justify="left", wraplength=640
            ).pack(side="left", fill="x", expand=True)
        frame(box, t, "surface1", height=6).pack()

    # --- data ---------------------------------------------------------------------------------

    def result_for(self, folder: Path) -> dict:
        return next(r for f, r in self.captures if f == folder)

    def current_result(self) -> dict | None:
        if not self.selected:
            return None
        try:
            return self.result_for(self.selected[-1])
        except StopIteration:
            return None

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
        elif (select_first or not self.selected) and self.captures:
            self.selected = [self.captures[0][0]]
        self.render_rail()
        self.render_main()

    def select(self, folder: Path, add: bool) -> None:
        if add and self.selected and folder not in self.selected:
            self.selected = [self.selected[-1], folder]
        elif add and folder in self.selected and len(self.selected) == 2:
            self.selected.remove(folder)
        else:
            self.selected = [folder]
        self.render_rail()
        self.render_main()
        if len(self.selected) == 2:
            self.tabs.select("Compare")

    def load_trace(self) -> None:
        folder = self.selected[-1] if self.selected else None
        if folder is None:
            return
        if folder in self.traces:
            tr = self.traces[folder]
            self.scope.show(tr, "" if tr else "NO TRACE FOR THIS CAPTURE")
            return
        self.scope.show(None, "READING FRAMES")
        result = self.result_for(folder)

        def work() -> None:
            try:
                tr = tracemod.get(folder, result)
            except Exception:  # a broken CSV must not break the window  # noqa: BLE001
                tr = None
            self.events.put(("trace", {"folder": folder, "trace": tr}))

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
                "PresentMon (Intel's free frame-capture tool) isn't downloaded yet.",
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
        self.setup_issue = ("info", "Downloading PresentMon...", [])
        self.render_setup()

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
            self.set_hotkey_note("Works in any game, even fullscreen.", "text3")
            self.save()
        if self.start_btn.key:
            self.start_btn.key.configure(text=key)
        self.set_status()

    def set_hotkey_note(self, text: str, color: str) -> None:
        self.hotkey_note = (text, color)
        self.hotkey_label.configure(text=text, fg=self.t.c[color])

    def current_settings(self) -> capture.CaptureSettings:
        length = None if self.manual_var.get() else self.length_seconds()
        return capture.CaptureSettings(
            length_s=length, process_name=self.process_var.get().strip() or None
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
        if self.setup_issue and self.setup_issue[0] in ("error", "warn"):
            self.status_lamp.set("warn")
            self.status_word.configure(text="SETUP")
            label(hint, t, "Finish the setup below to record.", font="caption", fg="text3").pack(
                side="left"
            )
            self.start_btn.set_text("Start capture")
        elif state == "recording" and self.recorder:
            secs, length = self.recorder.elapsed(), self.recorder.length_s
            self.status_lamp.set("error")
            self.status_word.configure(text="REC")
            label(
                hint, t, _clock(secs) + (f" / {_clock(length)}" if length else ""), font="mono_sm"
            ).pack(side="left")
            label(hint, t, f"   press {key} to stop", font="caption", fg="text3").pack(side="left")
            self.start_btn.set_text("Stop capture")
        elif state in ("stopping", "analyzing"):
            self.status_lamp.set("info")
            self.status_word.configure(text="ANALYZING")
            label(
                hint, t, "Stopping PresentMon and reading the frames.", font="caption", fg="text3"
            ).pack(side="left")
            self.start_btn.set_text("Analyzing")
        else:
            self.status_lamp.set("ok")
            self.status_word.configure(text="READY")
            label(hint, t, "Press ", font="caption", fg="text3").pack(side="left")
            KeyCap(hint, t, key).pack(side="left")
            what = (
                "until you press it again"
                if self.manual_var.get()
                else f"a {self.length_seconds()} s capture"
            )
            label(hint, t, f" in game to start {what}", font="caption", fg="text3").pack(
                side="left"
            )
            self.start_btn.set_text("Start capture")
        self.draw_progress()

    def draw_progress(self) -> None:
        c = self.progress
        c.delete("all")
        if not (self.recorder and self.recorder.state == "recording"):
            return
        length, w = self.recorder.length_s, c.winfo_width()
        frac = (
            min(1.0, self.recorder.elapsed() / length)
            if length
            else (self.recorder.elapsed() % 10) / 10
        )
        c.create_rectangle(0, 0, w * frac, 2, fill=self.t.c["accent"], width=0)

    def save(self) -> None:
        self.settings.update(
            hotkey=self.listener.hotkey if self.listener else self.settings["hotkey"],
            length_s=self.length_seconds(),
            manual=self.manual_var.get(),
            process_name=self.process_var.get().strip(),
            sound=self.sound_var.get(),
        )
        save_settings(self.settings)
        if self.recorder is None or self.recorder.state == "idle":
            self.set_status()
            if not self.current_result():
                self.fill_summary(None, False)

    def toggle_theme(self) -> None:
        self.settings["theme"] = "light" if self.settings.get("theme", "dark") == "dark" else "dark"
        save_settings(self.settings)
        tab = self.tabs.current
        self.build()
        if tab != "Summary":
            self.tabs.select(tab)

    # --- events ------------------------------------------------------------------------------

    def poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.handle(kind, payload)
        except queue.Empty:
            pass
        if self.recorder and self.recorder.state == "recording":
            self.set_status()
            length = self.recorder.length_s
            elapsed = self.recorder.elapsed()
            self.scope.recording(elapsed / length if length else elapsed / 10)
        self.root.after(100, self.poll)

    def handle(self, kind: str, p: dict) -> None:
        if kind == "hotkey":
            self.toggle_capture()
        elif kind == "started":
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
            self.set_status()
        elif kind == "done":
            self.record_info = {}
            folder = p.get("folder")
            self.traces.pop(folder, None)
            self.refresh_history(select=folder)
            self.set_status()
            self.shown_text = p["report"]
            self.copy_shown(note="Report copied to the clipboard.")
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
        elif kind == "trace":
            self.traces[p["folder"]] = p["trace"]
            if self.selected and self.selected[-1] == p["folder"]:
                tr = p["trace"]
                self.scope.show(tr, "" if tr else "NO TRACE FOR THIS CAPTURE")
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

    def copy_shown(self, note: str = "") -> None:
        if not self.shown_text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.shown_text)
        self.root.update()
        what = "Comparison" if self.shown == "Compare" else "Report"
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
            padx=12,
            pady=7,
        )
        box.pack()
        Lamp(box, t, "ok").pack(side="left", padx=(0, 10))
        label(box, t, text, bg="surface1").pack(side="left")
        if detail:
            label(box, t, detail, font="mono_xs", fg="text3", bg="surface1").pack(
                side="left", padx=(10, 0)
            )
        if self.note_job:
            self.root.after_cancel(self.note_job)
        self.note_job = self.root.after(
            4000, lambda: [c.destroy() for c in self.note.winfo_children()]
        )

    def open_selected(self) -> None:
        if self.selected:
            _open(self.selected[-1])
        else:
            root = self.captures_root or capture.DEFAULT_ROOT
            root.mkdir(parents=True, exist_ok=True)
            _open(root)

    # --- shutdown ----------------------------------------------------------------------------

    def on_close(self) -> None:
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
    theme.load_fonts()  # before Tk enumerates fonts
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
