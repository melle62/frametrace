"""Instrument widgets for the Frametrace window: buttons, lamps, readouts, the scope.

Plain tk widgets with explicit colors from frametrace.theme, so the window looks the
same on every Windows version. Every widget takes the Theme it draws with; switching
between dark and light rebuilds the window.
"""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable
from tkinter import ttk

from frametrace.theme import Theme, mix
from frametrace.trace import Trace

LAMP = {"ok": "success", "warn": "warning", "error": "error", "info": "text3", "idle": "text4"}


def label(parent, t: Theme, text="", font="body_sm", fg="text1", bg="background", **kw) -> tk.Label:
    opts = {"bd": 0, "padx": 0, "pady": 0, **kw}
    return tk.Label(parent, text=text, font=t.fonts[font], fg=t.c[fg], bg=t.c[bg], **opts)


def silk(parent, t: Theme, text: str, bg="background", fg="text3", **kw) -> tk.Label:
    """A silk-screen label: small, uppercase, quiet."""
    return label(parent, t, text.upper(), font="label", fg=fg, bg=bg, **kw)


def frame(parent, t: Theme, bg="background", border: str | None = None, **kw) -> tk.Frame:
    extra = (
        {"highlightthickness": 1, "highlightbackground": t.c[border], "highlightcolor": t.c[border]}
        if border
        else {"highlightthickness": 0}
    )
    return tk.Frame(parent, bg=t.c[bg], bd=0, **extra, **kw)


def rule(parent, t: Theme, color="border", vertical=False) -> tk.Frame:
    f = tk.Frame(parent, bg=t.c[color], bd=0, highlightthickness=0)
    f.configure(width=1) if vertical else f.configure(height=1)
    return f


class Lamp(tk.Frame):
    """An 8 px square indicator. Always paired with a word."""

    def __init__(self, parent, t: Theme, level="idle", bg="background"):
        super().__init__(parent, width=8, height=8, bg=t.c[LAMP[level]], bd=0, highlightthickness=0)
        self.t = t
        self.pack_propagate(False)

    def set(self, level: str) -> None:
        self.configure(bg=self.t.c[LAMP[level]])


class KeyCap(tk.Label):
    """A keyboard key, e.g. F10."""

    def __init__(self, parent, t: Theme, text: str, on_accent=False):
        if on_accent:
            fg, bg, edge = t.c["on_accent"], t.c["trace"], mix(t.c["on_accent"], t.c["trace"], 0.35)
        else:
            fg, bg, edge = t.c["text1"], t.c["surface2"], t.c["border_visible"]
        super().__init__(
            parent, text=text, font=t.fonts["mono_xs"], fg=fg, bg=bg, padx=5, pady=1, bd=0,
            highlightthickness=1, highlightbackground=edge, highlightcolor=edge,
        )  # fmt: skip


class FlatButton(tk.Frame):
    """Flat button. variant: primary (one per screen), secondary, ghost."""

    def __init__(
        self,
        parent,
        t: Theme,
        text: str,
        command: Callable[[], None] | None = None,
        variant="secondary",
        key: str | None = None,
        small=False,
    ):
        self.t, self.variant, self.command = t, variant, command
        self.enabled, self.hover, self.pressed = True, False, False
        self.parent_bg = parent.cget("bg")
        c = t.c
        border = c["border_visible"] if variant == "secondary" else self._bg()
        super().__init__(
            parent, bg=self._bg(), bd=0, highlightthickness=1, highlightbackground=border,
            highlightcolor=c["accent"], takefocus=1, cursor="hand2",
        )  # fmt: skip
        pad = (10, 4) if small else (14, 7)
        self.text = tk.Label(
            self, text=text, font=t.fonts["button"], bg=self._bg(), fg=self._fg(), bd=0,
            padx=pad[0], pady=pad[1],
        )  # fmt: skip
        self.text.pack(side="left")
        self.key = None
        if key:
            self.key = KeyCap(self, t, key, on_accent=variant == "primary")
            self.key.pack(side="left", padx=(0, 10))
        for w in (self, self.text, *([self.key] if self.key else [])):
            w.bind("<Enter>", lambda _e: self._hover(True))
            w.bind("<Leave>", lambda _e: self._hover(False))
            w.bind("<ButtonPress-1>", lambda _e: self._press(True))
            w.bind("<ButtonRelease-1>", self._release)
        self.bind("<space>", lambda _e: self.invoke())
        self.bind("<Return>", lambda _e: self.invoke())

    def _bg(self) -> str:
        c, v = self.t.c, self.variant
        if not self.enabled:
            return c["surface1"] if v != "ghost" else self.parent_bg
        if v == "primary":
            return (
                c["accent_pressed"]
                if self.pressed
                else c["accent_hover"]
                if self.hover
                else c["trace"]
            )
        if v == "secondary":
            return c["surface1"] if self.pressed else c["surface3"] if self.hover else c["surface2"]
        return c["surface2"] if self.hover else self.parent_bg

    def _fg(self) -> str:
        c = self.t.c
        if not self.enabled:
            return c["text4"]
        if self.variant == "primary":
            return c["on_accent"]
        if self.variant == "ghost" and not self.hover:
            return c["text2"]
        return c["text1"]

    def _paint(self) -> None:
        bg, fg = self._bg(), self._fg()
        border = self.t.c["border_visible"] if self.variant == "secondary" and self.enabled else bg
        self.configure(bg=bg, highlightbackground=border)
        self.text.configure(bg=bg, fg=fg)
        if self.key is not None and self.variant == "primary":
            c = self.t.c
            if self.enabled:
                edge = mix(c["on_accent"], bg, 0.35)
                self.key.configure(bg=bg, fg=c["on_accent"], highlightbackground=edge)
            else:
                self.key.configure(bg=bg, fg=c["text4"], highlightbackground=c["border_visible"])

    def _hover(self, on: bool) -> None:
        self.hover = on and self.enabled
        if not on:
            self.pressed = False
        self._paint()

    def _press(self, on: bool) -> None:
        self.pressed = on and self.enabled
        self._paint()

    def _release(self, event) -> None:
        inside = self.winfo_containing(event.x_root, event.y_root) in (self, self.text, self.key)
        self._press(False)
        if inside:
            self.invoke()

    def invoke(self) -> None:
        if self.enabled and self.command:
            self.command()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow", takefocus=1 if enabled else 0)
        self._paint()

    def set_text(self, text: str) -> None:
        self.text.configure(text=text)


class Segmented(tk.Frame):
    """Two or three mutually exclusive options in a well."""

    def __init__(
        self,
        parent,
        t: Theme,
        options: list[tuple[str, object]],
        variable: tk.Variable,
        command=None,
    ):
        super().__init__(
            parent,
            bg=t.c["background"],
            highlightthickness=1,
            highlightbackground=t.c["border_visible"],
            padx=2,
            pady=2,
        )
        self.t, self.var, self.command, self.items = t, variable, command, []
        for text, value in options:
            item = tk.Label(
                self, text=text, font=t.fonts["caption"], bd=0, padx=10, pady=4, cursor="hand2"
            )
            item.pack(side="left", padx=(0, 2) if len(self.items) < len(options) - 1 else 0)
            item.bind("<Button-1>", lambda _e, v=value: self._pick(v))
            self.items.append((item, value))
        variable.trace_add("write", lambda *_: self._paint())
        self._paint()

    def _pick(self, value) -> None:
        self.var.set(value)
        if self.command:
            self.command()

    def _paint(self) -> None:
        for item, value in self.items:
            on = self.var.get() == value
            item.configure(
                bg=self.t.c["surface3" if on else "background"],
                fg=self.t.c["text1" if on else "text3"],
            )


class Check(tk.Frame):
    """Square checkbox drawn on a canvas, with a label."""

    def __init__(
        self, parent, t: Theme, text: str, variable: tk.BooleanVar, command=None, bg="background"
    ):
        super().__init__(parent, bg=t.c[bg], cursor="hand2")
        self.t, self.var, self.command, self.bgkey = t, variable, command, bg
        self.box = tk.Canvas(self, width=16, height=16, bg=t.c[bg], highlightthickness=0, bd=0)
        self.box.pack(side="left")
        lab = label(self, t, text, bg=bg)
        lab.pack(side="left", padx=(8, 0))
        for w in (self, self.box, lab):
            w.bind("<Button-1>", lambda _e: self.toggle())
        variable.trace_add("write", lambda *_: self._paint())
        self._paint()

    def toggle(self) -> None:
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def _paint(self) -> None:
        c, b = self.t.c, self.box
        b.delete("all")
        if self.var.get():
            b.create_rectangle(0, 0, 15, 15, fill=c["accent"], outline=c["accent"])
            b.create_line(
                4, 8, 7, 11, 12, 5, fill=c["on_accent"], width=2, capstyle="butt", joinstyle="miter"
            )
        else:
            b.create_rectangle(0, 0, 15, 15, fill=c["background"], outline=c["border_visible"])


class Readout(tk.Frame):
    """Silk-screen label, big mono value, small unit, one sub-line."""

    def __init__(self, parent, t: Theme, title: str, swatch: str | None = None):
        super().__init__(
            parent,
            bg=t.c["surface1"],
            highlightthickness=1,
            highlightbackground=t.c["border"],
            padx=14,
            pady=12,
        )
        self.t = t
        head = frame(self, t, "surface1")
        head.pack(fill="x")
        if swatch:
            tk.Frame(head, width=8, height=8, bg=t.c[swatch]).pack(side="left", padx=(0, 6))
        self.title = silk(head, t, title, bg="surface1")
        self.title.pack(side="left")
        row = frame(self, t, "surface1")
        row.pack(fill="x", pady=(10, 0))
        self.value = label(row, t, "---", font="readout", fg="text4", bg="surface1")
        self.value.pack(side="left")
        self.unit = label(row, t, "", font="mono_sm", fg="text3", bg="surface1")
        self.unit.pack(side="left", padx=(4, 0), anchor="s", pady=(0, 3))
        self.sub = label(self, t, "", font="mono_xs", fg="text3", bg="surface1", anchor="w")
        self.sub.pack(fill="x", pady=(8, 0))

    def set(
        self, value: str | None, unit: str = "", sub: str = "", title: str | None = None
    ) -> None:
        if title:
            self.title.configure(text=title.upper())
        self.value.configure(
            text=value if value is not None else "---",
            fg=self.t.c["text1" if value is not None else "text4"],
        )
        self.unit.configure(text=unit)
        self.sub.configure(text=sub)


class SplitBar(tk.Canvas):
    """Where the frames went: GPU cyan, CPU magenta, waiting grey."""

    def __init__(self, parent, t: Theme, bg="surface1"):
        super().__init__(parent, height=8, bg=t.c[bg], highlightthickness=0, bd=0)
        self.t, self.parts = t, (0.0, 0.0, 0.0)
        self.bind("<Configure>", lambda _e: self.draw())

    def set(self, gpu: float, cpu: float, wait: float) -> None:
        self.parts = (gpu, cpu, wait)
        self.draw()

    def draw(self) -> None:
        self.delete("all")
        w, total = self.winfo_width(), sum(self.parts)
        if w <= 1:
            return
        if total <= 0:
            self.create_rectangle(0, 0, w, 8, fill=self.t.c["surface2"], width=0)
            return
        x = 0.0
        for share, key in zip(self.parts, ("ch2", "ch3", "text4"), strict=True):
            seg = w * share / total
            if seg >= 0.5:
                self.create_rectangle(x, 0, x + seg - 1, 8, fill=self.t.c[key], width=0)
            x += seg


def nice_div(peak_ms: float) -> float:
    """ms per division so that 4 divisions show the trace with some headroom."""
    for step in (0.25, 0.5, 1, 1.5, 2, 2.5, 5, 10, 15, 20, 25, 50, 100, 250):
        if step * 4 >= peak_ms * 1.25:
            return step
    return 250.0


def nice_time_step(duration_s: float) -> float:
    for step in (1, 2, 5, 10, 15, 20, 30, 60, 120, 300, 600):
        if duration_s / step <= 6:
            return step
    return 600.0


def _fmt_num(v: float) -> str:
    return f"{v:g}"


class Scope(tk.Canvas):
    """The frame-time screen. Dark in both modes.

    CH1 frame time: 5th to 95th percentile band plus the median line.
    CH2 GPU busy and CH3 CPU busy: medians. Hitches: a dashed marker and a tick.
    """

    L, R, T, B = 46, 12, 14, 24  # plot margins

    def __init__(self, parent, t: Theme, height=200):
        super().__init__(parent, height=height, bg=t.c["screen"], highlightthickness=0, bd=0)
        self.t = t
        self.trace: Trace | None = None
        self.channels = {"ch1": True, "ch2": True, "ch3": True}
        self.message = "NO CAPTURE SELECTED"
        self.sweep: float | None = None  # 0..1 while recording
        self.bind("<Configure>", lambda _e: self.draw())

    def show(self, trace: Trace | None, message: str = "") -> None:
        self.trace, self.message, self.sweep = trace, message, None
        self.draw()

    def recording(self, progress: float) -> None:
        self.trace, self.sweep = None, progress % 1.0
        self.message = "RECORDING · THE TRACE APPEARS WHEN THE CAPTURE ENDS"
        self.draw()

    def toggle(self, channel: str) -> bool:
        self.channels[channel] = not self.channels[channel]
        self.draw()
        return self.channels[channel]

    def draw(self) -> None:
        self.delete("all")
        c, f = self.t.c, self.t.fonts
        w, h = self.winfo_width(), self.winfo_height()
        if w < 60 or h < 40:
            return
        x0, x1, y0, y1 = self.L, w - self.R, self.T, h - self.B
        pw, ph = x1 - x0, y1 - y0
        tr = self.trace
        div = nice_div(tr.peak_ms() if tr else 4.0)
        full = div * 4
        dur = tr.duration_s if tr else 100.0

        # graticule: 10 x 4 major divisions
        for i in range(11):
            x = x0 + pw * i / 10
            self.create_line(x, y0, x, y1, fill=c["graticule"])
        for j in range(5):
            y = y0 + ph * j / 4
            self.create_line(x0, y, x1, y, fill=c["graticule"])
            v = full * (4 - j) / 4
            self.create_text(
                x0 - 6,
                y,
                text=_fmt_num(v) + (" ms" if j == 0 else ""),
                anchor="e",
                fill=c["screen_text"],
                font=f["mono_xs"],
            )
        if tr:
            step = nice_time_step(dur)
            k = 0
            while k * step <= dur + 1e-9:
                x = x0 + pw * (k * step) / dur
                self.create_text(
                    x,
                    y1 + 12,
                    text=_fmt_num(k * step) + (" s" if k == 0 else ""),
                    anchor="n" if k else "nw",
                    fill=c["screen_text"],
                    font=f["mono_xs"],
                )
                k += 1

        if not tr:
            if self.sweep is not None:
                x = x0 + pw * self.sweep
                self.create_line(x, y0, x, y1, fill=c["ch1"], width=2)
                self.create_line(
                    x - 3, y0, x - 3, y1, fill=mix(c["ch1"], c["screen"], 0.25), width=4
                )
            if self.message:
                tid = self.create_text(
                    (x0 + x1) / 2,
                    (y0 + y1) / 2,
                    text=self.message,
                    fill=c["screen_text"],
                    font=f["mono_sm"],
                )
                bx = self.bbox(tid)
                if bx:
                    bg = self.create_rectangle(
                        bx[0] - 8, bx[1] - 3, bx[2] + 8, bx[3] + 3, fill=c["screen"], width=0
                    )
                    self.tag_lower(bg, tid)
            return

        n = tr.buckets

        def X(i: int) -> float:
            return x0 + pw * (i + 0.5) / n

        def Y(v: float) -> float:
            return y1 - ph * min(v, full) / full

        def polyline(values, color, width):
            seg: list[float] = []
            for i, v in enumerate(values):
                if v is None:
                    if len(seg) >= 4:
                        self.create_line(
                            *seg, fill=color, width=width, capstyle="butt", joinstyle="miter"
                        )
                    seg = []
                    continue
                seg += [X(i), Y(v)]
            if len(seg) >= 4:
                self.create_line(*seg, fill=color, width=width, capstyle="butt", joinstyle="miter")

        # hitch markers under everything
        hitch_dash = mix(c["hitch"], c["screen"], 0.7)
        if self.channels["ch1"]:
            for t_s, _ms in tr.hitches:
                x = x0 + pw * min(t_s, dur) / dur
                self.create_line(x, y0, x, y1, fill=hitch_dash, dash=(3, 3))
        if self.channels["ch3"]:
            polyline(tr.cpu, c["ch3"], 1)
        if self.channels["ch2"]:
            polyline(tr.gpu, c["ch2"], 1)
        if self.channels["ch1"]:
            up = [(X(i), Y(v)) for i, v in enumerate(tr.p95) if v is not None]
            dn = [(X(i), Y(v)) for i, v in reversed(list(enumerate(tr.p5))) if v is not None]
            if len(up) > 1:
                self.create_polygon(
                    *[p for xy in up + dn for p in xy],
                    fill=mix(c["ch1"], c["screen"], 0.18),
                    outline="",
                )
            polyline(tr.p50, mix(c["ch1"], c["screen"], 0.35), 4)  # phosphor bloom
            polyline(tr.p50, c["ch1"], 2)
            for t_s, ms in tr.hitches:
                x = x0 + pw * min(t_s, dur) / dur
                self.create_line(x, Y(ms), x, y1, fill=c["ch1"], width=2, capstyle="butt")
            if tr.hitches:
                t_s, ms = max(tr.hitches, key=lambda h: h[1])
                x = x0 + pw * min(t_s, dur) / dur
                right = x < x1 - 140
                tid = self.create_text(
                    x + 6 if right else x - 6,
                    y0 + 2,
                    text=f"{ms:.1f} ms @ {t_s:.1f} s",
                    anchor="nw" if right else "ne",
                    fill=c["hitch"],
                    font=f["mono_xs"],
                )
                bx = self.bbox(tid)
                if bx:
                    bg = self.create_rectangle(
                        bx[0] - 3, bx[1], bx[2] + 3, bx[3], fill=c["screen"], width=0
                    )
                    self.tag_lower(bg, tid)


class Tabs(tk.Frame):
    """Underline tabs with silk-screen labels."""

    def __init__(self, parent, t: Theme, names: list[str], command: Callable[[str], None]):
        super().__init__(parent, bg=t.c["background"])
        self.t, self.command, self.tabs, self.disabled = t, command, {}, set()
        self.current = names[0]
        row = frame(self, t)
        row.pack(fill="x")
        for name in names:
            cell = frame(row, t)
            cell.pack(side="left", padx=(0, 24))
            lab = silk(cell, t, name, cursor="hand2")
            lab.pack(pady=(8, 8))
            bar = tk.Frame(cell, height=2, bg=t.c["background"])
            bar.pack(fill="x")
            lab.bind("<Button-1>", lambda _e, n=name: self.select(n))
            self.tabs[name] = (lab, bar)
        self.extra = frame(row, t)
        self.extra.pack(side="right")
        rule(self, t).pack(fill="x")
        self._paint()

    def select(self, name: str, notify=True) -> None:
        if name in self.disabled:
            return
        self.current = name
        self._paint()
        if notify:
            self.command(name)

    def set_disabled(self, name: str, disabled: bool) -> None:
        (self.disabled.add if disabled else self.disabled.discard)(name)
        self._paint()

    def _paint(self) -> None:
        c = self.t.c
        for name, (lab, bar) in self.tabs.items():
            on = name == self.current
            lab.configure(fg=c["text1" if on else "text4" if name in self.disabled else "text3"])
            bar.configure(bg=c["accent"] if on else c["background"])


class ScrollFrame(tk.Frame):
    """A vertically scrolling frame; .inner is where children go."""

    def __init__(self, parent, t: Theme, bg="background"):
        super().__init__(parent, bg=t.c[bg])
        self.canvas = tk.Canvas(self, bg=t.c[bg], highlightthickness=0, bd=0)
        self.bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=t.c[bg])
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner.bind("<Configure>", lambda _e: self._resize())
        self.canvas.bind(
            "<Configure>",
            lambda e: (self.canvas.itemconfigure(self.window, width=e.width), self._resize()),
        )
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda _e: self._wheel(True))
            w.bind("<Leave>", lambda _e: self._wheel(False))

    def _resize(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_scroll(self, lo, hi) -> None:
        self.bar.set(lo, hi)
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            self.bar.pack_forget()
        elif not self.bar.winfo_ismapped():
            self.bar.pack(side="right", fill="y")

    def _wheel(self, on: bool) -> None:
        if on:
            self.bind_all(
                "<MouseWheel>",
                lambda e: self.canvas.yview_scroll(
                    int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units"
                ),
            )
            self.bind_all("<Button-4>", lambda _e: self.canvas.yview_scroll(-3, "units"))
            self.bind_all("<Button-5>", lambda _e: self.canvas.yview_scroll(3, "units"))
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.unbind_all(seq)

    def to_top(self) -> None:
        self.canvas.yview_moveto(0)


def wordmark(parent, t: Theme, bg="background", size=22) -> tk.Frame:
    """The trace glyph plus the name."""
    f = frame(parent, t, bg)
    glyph = tk.Canvas(
        f, width=size, height=math.ceil(size * 14 / 22), bg=t.c[bg], highlightthickness=0, bd=0
    )
    s = size / 22
    glyph.create_line(
        0,
        11 * s,
        6 * s,
        11 * s,
        8 * s,
        2 * s,
        10 * s,
        12 * s,
        12 * s,
        7 * s,
        22 * s,
        7 * s,
        fill=t.c["ch1"],
        width=2,
        capstyle="butt",
        joinstyle="miter",
    )
    glyph.pack(side="left", padx=(0, 8))
    label(f, t, "Frametrace", font="wordmark", bg=bg).pack(side="left")
    return f
