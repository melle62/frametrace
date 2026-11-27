"""Instrument widgets for the Frametrace window: buttons, lamps, readouts, the scope.

Plain tk widgets with explicit colors from frametrace.theme, so the window looks the
same on every Windows version. Every widget takes the Theme it draws with; switching
between dark and light rebuilds the window. Pixel sizes go through theme.px() so the
layout keeps its proportions on 125% and 150% displays.
"""

from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable

from frametrace.summary import number_runs
from frametrace.theme import Theme, mix, px, track
from frametrace.trace import Trace

NBSP = "\u00a0"
LAMP = {"ok": "success", "warn": "warning", "error": "error", "info": "text3", "idle": "text4"}


def label(parent, t: Theme, text="", font="body_sm", fg="text1", bg="background", **kw) -> tk.Label:
    opts = {"bd": 0, "padx": 0, "pady": 0, **kw}
    return tk.Label(parent, text=text, font=t.fonts[font], fg=t.c[fg], bg=t.c[bg], **opts)


def silk(parent, t: Theme, text: str, bg="background", fg="text3", **kw) -> tk.Label:
    """A silk-screen label: small, uppercase, tracked, quiet."""
    return label(parent, t, track(text.upper()), font="label", fg=fg, bg=bg, **kw)


def set_silk(widget: tk.Label, text: str) -> None:
    widget.configure(text=track(text.upper()))


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


def swatch(parent, t: Theme, key: str) -> tk.Frame:
    """An 8 px channel swatch (legend chip). Square like a lamp, but it names a signal."""
    return tk.Frame(parent, width=px(8), height=px(8), bg=t.c[key], bd=0, highlightthickness=0)


class Lamp(tk.Frame):
    """An 8 px square indicator. Always paired with a word."""

    def __init__(self, parent, t: Theme, level="idle", bg="background"):
        size = px(8)
        super().__init__(
            parent, width=size, height=size, bg=t.c[LAMP[level]], bd=0, highlightthickness=0
        )
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
            parent, text=text, font=t.fonts["mono_xs"], fg=fg, bg=bg, padx=px(5), pady=px(1),
            bd=0, highlightthickness=1, highlightbackground=edge, highlightcolor=edge,
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
        super().__init__(
            parent, bg=self._bg(), bd=0, highlightthickness=1, highlightbackground=self._edge(),
            highlightcolor=c["accent"], takefocus=1, cursor="hand2",
        )  # fmt: skip
        pad = (px(10), px(4)) if small else (px(14), px(7))
        self.text = tk.Label(
            self, text=text, font=t.fonts["button"], bg=self._bg(), fg=self._fg(), bd=0,
            padx=pad[0], pady=pad[1],
        )  # fmt: skip
        self.text.pack(side="left")
        self.key = None
        if key:
            self.key = KeyCap(self, t, key, on_accent=variant == "primary")
            self.key.pack(side="left", padx=(0, px(10)))
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

    def _edge(self) -> str:
        c = self.t.c
        if self.variant == "ghost":
            return self._bg()
        if not self.enabled:
            return c["border"]
        return c["border_visible"] if self.variant == "secondary" else self._bg()

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
        self.configure(bg=bg, highlightbackground=self._edge())
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
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if not enabled:
            self.hover = self.pressed = False
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
        font="caption",
    ):
        super().__init__(
            parent,
            bg=t.c["background"],
            highlightthickness=1,
            highlightbackground=t.c["border_visible"],
            padx=px(2),
            pady=px(2),
        )
        self.t, self.var, self.command, self.items = t, variable, command, []
        self.hover = None
        for text, value in options:
            item = tk.Label(
                self, text=text, font=t.fonts[font], bd=0, padx=px(10), pady=px(4), cursor="hand2"
            )
            item.pack(side="left", padx=(0, px(2)) if len(self.items) < len(options) - 1 else 0)
            item.bind("<Button-1>", lambda _e, v=value: self._pick(v))
            item.bind("<Enter>", lambda _e, v=value: self._hover(v))
            item.bind("<Leave>", lambda _e: self._hover(None))
            self.items.append((item, value))
        self._trace = variable.trace_add("write", lambda *_: self._paint())
        self.bind("<Destroy>", self._untrace, add="+")
        self._paint()

    def _untrace(self, event) -> None:
        if event.widget is self:
            try:
                self.var.trace_remove("write", self._trace)
            except tk.TclError:
                pass

    def _pick(self, value) -> None:
        if self.var.get() == value:
            return
        self.var.set(value)
        if self.command:
            self.command()

    def _hover(self, value) -> None:
        self.hover = value
        self._paint()

    def _paint(self) -> None:
        c = self.t.c
        for item, value in self.items:
            on = self.var.get() == value
            item.configure(
                bg=c["surface3" if on else "surface2" if value == self.hover else "background"],
                fg=c["text1" if on or value == self.hover else "text3"],
            )


class Check(tk.Frame):
    """Square checkbox drawn on a canvas, with a label."""

    def __init__(
        self, parent, t: Theme, text: str, variable: tk.BooleanVar, command=None, bg="background"
    ):
        super().__init__(parent, bg=t.c[bg], cursor="hand2", takefocus=1, highlightthickness=1)
        self.configure(highlightbackground=t.c[bg], highlightcolor=t.c["accent"])
        self.t, self.var, self.command, self.bgkey, self.hover = t, variable, command, bg, False
        self.size = px(16)
        self.box = tk.Canvas(
            self, width=self.size, height=self.size, bg=t.c[bg], highlightthickness=0, bd=0
        )
        self.box.pack(side="left")
        lab = label(self, t, text, bg=bg)
        lab.pack(side="left", padx=(px(8), 0))
        for w in (self, self.box, lab):
            w.bind("<Button-1>", lambda _e: self.toggle())
            w.bind("<Enter>", lambda _e: self._set_hover(True))
            w.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<space>", lambda _e: self.toggle())
        self._trace = variable.trace_add("write", lambda *_: self._paint())
        self.bind("<Destroy>", self._untrace, add="+")
        self._paint()

    def _untrace(self, event) -> None:
        if event.widget is self:
            try:
                self.var.trace_remove("write", self._trace)
            except tk.TclError:
                pass

    def toggle(self) -> None:
        self.var.set(not self.var.get())
        if self.command:
            self.command()

    def _set_hover(self, on: bool) -> None:
        self.hover = on
        self._paint()

    def _paint(self) -> None:
        c, b, s = self.t.c, self.box, self.size - 1
        b.delete("all")
        if self.var.get():
            # neutral, not yellow: yellow is the trace, the primary button and focus only
            b.create_rectangle(0, 0, s, s, fill=c["text1"], outline=c["text1"])
            k = self.size / 16
            b.create_line(
                4 * k, 8 * k, 7 * k, 11 * k, 12 * k, 5 * k,
                fill=c["background"], width=max(2, px(2)), capstyle="butt", joinstyle="miter",
            )  # fmt: skip
        else:
            edge = c["text3"] if self.hover else c["border_visible"]
            b.create_rectangle(0, 0, s, s, fill=c["background"], outline=edge)


class Readout(tk.Frame):
    """Silk-screen label, big mono value, small unit, one sub-line."""

    def __init__(self, parent, t: Theme, title: str, swatch_key: str | None = None):
        super().__init__(
            parent,
            bg=t.c["surface1"],
            highlightthickness=1,
            highlightbackground=t.c["border"],
            padx=px(16),
            pady=px(12),
        )
        self.t = t
        head = frame(self, t, "surface1")
        head.pack(fill="x")
        self.swatch = None
        if swatch_key:
            self.swatch = swatch(head, t, swatch_key)
            self.swatch.pack(side="left", padx=(0, px(6)))
        self.title = silk(head, t, title, bg="surface1", anchor="w", justify="left")
        self.title.pack(side="left")
        row = frame(self, t, "surface1")
        row.pack(fill="x", pady=(px(10), 0))
        self.value = label(row, t, "---", font="readout", fg="text4", bg="surface1")
        self.value.pack(side="left")
        self.unit = label(row, t, "", font="mono_sm", fg="text3", bg="surface1")
        self.unit.pack(side="left", padx=(px(4), 0), anchor="s", pady=(0, px(3)))
        self.sub = label(
            self, t, "", font="mono_xs", fg="text3", bg="surface1", anchor="w", justify="left"
        )
        self.sub.pack(fill="x", pady=(px(8), 0))
        self.bind("<Configure>", self._wrap)

    def _wrap(self, e) -> None:
        room = max(60, e.width - px(34))
        self.sub.configure(wraplength=room)
        self.title.configure(wraplength=room - (px(14) if self.swatch else 0))
        self._fit(e.width)

    def _fit(self, width: int | None = None) -> None:
        """Step the value down a size when it and its unit would not fit the tile."""
        f = self.t.fonts
        width = width or self.winfo_width()
        if width <= 1:
            return
        room = width - 2 * px(16) - 2
        text, unit = self.value.cget("text"), self.unit.cget("text")
        need = f["readout"].measure(text) + px(4) + f["mono_sm"].measure(unit)
        self.value.configure(font=f["readout"] if need <= room else f["readout_sm"])

    def set(
        self, value: str | None, unit: str = "", sub: str = "", title: str | None = None
    ) -> None:
        if title:
            set_silk(self.title, title)
        empty = value is None
        self.value.configure(
            text="---" if empty else value, fg=self.t.c["text4" if empty else "text1"]
        )
        self.unit.configure(text=unit, fg=self.t.c["text4" if empty else "text3"])
        self.sub.configure(text=sub)
        self._fit()


class RichText(tk.Text):
    """Wrapping prose with every number (and its unit) set in Plex Mono.

    Grows to as many lines as the text needs at the current width.
    """

    def __init__(
        self,
        parent,
        t: Theme,
        text: str = "",
        font="body_sm",
        mono="mono_sm",
        fg="text2",
        mono_fg="text1",
        bg="surface1",
    ):
        super().__init__(
            parent, height=1, width=1, wrap="word", bd=0, padx=0, pady=0, relief="flat",
            highlightthickness=0, bg=t.c[bg], fg=t.c[fg], font=t.fonts[font], cursor="arrow",
            takefocus=0, spacing1=0, spacing2=px(3), spacing3=0, exportselection=False,
            selectbackground=t.c["accent_subtle"], selectforeground=t.c["text1"],
            inactiveselectbackground=t.c["accent_subtle"], insertwidth=0,
        )  # fmt: skip
        self.tag_configure("num", font=t.fonts[mono], foreground=t.c[mono_fg])
        self.bind("<Configure>", lambda _e: self._fit())
        self.set(text)

    def set(self, text: str) -> None:
        self.configure(state="normal")
        self.delete("1.0", "end")
        for part, is_num in number_runs(text):
            # a number and its unit never wrap apart: "2.25 ms" keeps a no-break space
            self.insert(
                "end", part.replace(" ", NBSP) if is_num else part, ("num",) if is_num else ()
            )
        self.configure(state="disabled")
        self._fit()

    def _fit(self) -> None:
        try:
            n = self.count("1.0", "end", "update", "displaylines")
        except tk.TclError:
            return
        if isinstance(n, tuple):
            n = n[0]
        n = max(1, n or 1)
        # height counts lines at the font's line height; the gap between wrapped lines
        # (spacing2) comes on top, so add enough lines to cover it or the last one is cut
        gap = int(self.cget("spacing2")) * (n - 1)
        line = tkfont.Font(font=self.cget("font")).metrics("linespace") or 1
        n += -(-gap // line)
        if int(self.cget("height")) != n:
            self.configure(height=n)


class SplitBar(tk.Canvas):
    """Where the frames went: GPU cyan, CPU magenta, waiting grey."""

    def __init__(self, parent, t: Theme, bg="surface1"):
        self.h = px(8)
        super().__init__(parent, width=1, height=self.h, bg=t.c[bg], highlightthickness=0, bd=0)
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
            self.create_rectangle(0, 0, w, self.h, fill=self.t.c["surface2"], width=0)
            return
        x = 0.0
        for share, key in zip(self.parts, ("ch2", "ch3", "text4"), strict=True):
            seg = w * share / total
            if seg >= 0.5:
                self.create_rectangle(x, 0, x + seg - 1, self.h, fill=self.t.c[key], width=0)
            x += seg


class Progress(tk.Frame):
    """A determinate 4 px bar with elapsed on the left and remaining on the right."""

    def __init__(self, parent, t: Theme, bg="surface1"):
        super().__init__(parent, bg=t.c[bg])
        self.t, self.frac = t, 0.0
        self.bar = tk.Canvas(
            self, width=1, height=px(4), bg=t.c["surface2"], highlightthickness=0, bd=0
        )
        self.bar.pack(fill="x")
        row = frame(self, t, bg)
        row.pack(fill="x", pady=(px(8), 0))
        self.left = label(row, t, "", font="mono_xs", fg="text2", bg=bg)
        self.left.pack(side="left")
        self.right = label(row, t, "", font="mono_xs", fg="text3", bg=bg)
        self.right.pack(side="right")
        self.bar.bind("<Configure>", lambda _e: self._draw())

    def set(self, frac: float | None, left: str, right: str) -> None:
        self.frac = frac
        self.left.configure(text=left)
        self.right.configure(text=right)
        self._draw()

    def _draw(self) -> None:
        b = self.bar
        b.delete("all")
        if self.frac is None:
            return
        w = b.winfo_width()
        b.create_rectangle(
            0, 0, w * max(0.0, min(1.0, self.frac)), px(4), fill=self.t.c["accent"], width=0
        )


class DeltaBar(tk.Canvas):
    """A diverging bar: right for better, left for worse, full width at `span` percent."""

    def __init__(
        self,
        parent,
        t: Theme,
        change: float | None,
        status: str,
        bg="surface1",
        width=160,
        span=25.0,
    ):
        self.h = px(10)
        super().__init__(
            parent, width=px(width), height=self.h, bg=t.c[bg], highlightthickness=0, bd=0
        )
        self.t, self.change, self.status, self.span, self.bgkey = t, change, status, span, bg
        self.bind("<Configure>", lambda _e: self.draw())

    def draw(self) -> None:
        self.delete("all")
        c = self.t.c
        w, h = self.winfo_width(), self.h
        mid = w // 2
        top, bottom = px(1), h - px(1)
        # the track shows the full scale, so a short bar reads as a small change
        self.create_rectangle(
            0, top, w, bottom, fill=mix(c["surface2"], c[self.bgkey], 0.6), width=0
        )
        if self.change is not None:
            key = {"better": "success", "worse": "warning"}.get(self.status, "text4")
            fill = mix(c[key], c[self.bgkey], 0.55) if key != "text4" else c["text4"]
            half = (w / 2 - 1) * min(1.0, abs(self.change) / self.span)
            if half >= 1:
                if self.status in ("better", "worse"):
                    right = self.status == "better"
                else:
                    right = self.change > 0
                left = mid if right else mid - half
                self.create_rectangle(left, top, left + half, bottom, fill=fill, width=0)
        self.create_line(mid, 0, mid, h, fill=c["text4"])


def nice_div(peak_ms: float) -> float:
    """ms per division so that 4 divisions show the trace with a little headroom.

    Steps between 2.5 and 5 matter: a CS2 run peaking near 9 ms would otherwise get a
    20 ms screen and sit in its bottom quarter.
    """
    for step in (0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 7.5, 10, 15, 20, 25, 50, 100, 250):
        if step * 4 >= peak_ms * 1.15:
            return step
    return 250.0


def nice_time_step(duration_s: float) -> float:
    """Seconds between time labels: at most six labels across."""
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
    Compare view: a second capture drawn underneath as the stored reference (REF, neutral).
    Vertical divisions sit at half the labelled time step, so labels land on lines.
    """

    def __init__(self, parent, t: Theme, height=200):
        super().__init__(parent, height=px(height), bg=t.c["screen"], highlightthickness=0, bd=0)
        self.t = t
        self.L, self.R, self.T, self.B = px(46), px(12), px(14), px(26)  # plot margins
        self.trace: Trace | None = None
        self.ref: Trace | None = None
        self.channels = {"ch1": True, "ch2": True, "ch3": True}
        self.message = "NO CAPTURE SELECTED"
        self.sweep: float | None = None  # 0..1 while recording
        self.bind("<Configure>", lambda _e: self.draw())

    def show(self, trace: Trace | None, message: str = "", ref: Trace | None = None) -> None:
        self.trace, self.ref, self.message, self.sweep = trace, ref, message, None
        self.draw()

    def recording(self, progress: float, message: str) -> None:
        self.trace, self.ref, self.sweep = None, None, progress % 1.0
        self.message = message
        self.draw()

    def toggle(self, channel: str) -> bool:
        self.channels[channel] = not self.channels[channel]
        self.draw()
        return self.channels[channel]

    def has(self, channel: str) -> bool:
        """Whether the shown capture has data for a channel (CH2/CH3 need busy columns)."""
        tr = self.trace
        if tr is None:
            return True
        values = {"ch1": tr.p50, "ch2": tr.gpu, "ch3": tr.cpu}[channel]
        return any(v is not None for v in values)

    def scale(self) -> tuple[float, float, float]:
        """(ms per division, seconds per division, seconds across) for the caption."""
        tr, ref = self.trace, self.ref
        peak = max((x.peak_ms() for x in (tr, ref) if x), default=4.0)
        dur = max((x.duration_s for x in (tr, ref) if x), default=100.0)
        return nice_div(peak), nice_time_step(dur) / 2, dur

    def scale_text(self) -> str:
        if self.trace is None:
            return ""
        div, tdiv, dur = self.scale()
        return f"{_fmt_num(div)} ms/div · {_fmt_num(tdiv)} s/div · {dur:.1f} s"

    def draw(self) -> None:
        self.delete("all")
        c, f = self.t.c, self.t.fonts
        w, h = self.winfo_width(), self.winfo_height()
        if w < 60 or h < 40:
            return
        x0, x1, y0, y1 = self.L, w - self.R, self.T, h - self.B
        pw, ph = x1 - x0, y1 - y0
        tr, ref = self.trace, self.ref
        div, tdiv, dur = self.scale()
        full = div * 4
        tick = mix(c["screen_text"], c["screen"], 0.45)

        # graticule: 4 divisions down; across, one line per half time step
        if tr:  # no sliver of a division at the right edge
            n = math.ceil(dur / tdiv)
            xs = [x0 + pw * k * tdiv / dur for k in range(n) if k * tdiv < dur - 0.3 * tdiv]
            xs.append(x1)
        else:
            xs = [x0 + pw * i / 10 for i in range(11)]
        for x in xs:
            self.create_line(x, y0, x, y1, fill=c["graticule"])
        for j in range(5):
            y = y0 + ph * j / 4
            self.create_line(x0, y, x1, y, fill=c["graticule"])
        # minor ticks on the centre lines, five per division
        ym = y0 + ph / 2
        for k in range(1, 50):
            x = x0 + pw * k / 50
            self.create_line(x, ym - px(2), x, ym + px(3), fill=tick)
        if not tr:  # the empty screen has a vertical centre line too
            xm = (x0 + x1) / 2
            for k in range(1, 20):
                y = y0 + ph * k / 20
                self.create_line(xm - px(2), y, xm + px(3), y, fill=tick)

        if not tr:
            if self.sweep is not None:
                x = x0 + pw * self.sweep
                self.create_line(
                    x - px(3), y0, x - px(3), y1, fill=mix(c["ch1"], c["screen"], 0.25), width=px(4)
                )
                self.create_line(x, y0, x, y1, fill=c["ch1"], width=max(2, px(2)))
            if self.message:
                tid = self.create_text(
                    (x0 + x1) / 2, (y0 + y1) / 2, text=self.message, fill=c["screen_text"],
                    font=f["mono_sm"],
                )  # fmt: skip
                bx = self.bbox(tid)
                if bx:
                    bg = self.create_rectangle(
                        bx[0] - px(8), bx[1] - px(3), bx[2] + px(8), bx[3] + px(3),
                        fill=c["screen"], width=0,
                    )  # fmt: skip
                    self.tag_lower(bg, tid)
            return

        # axis labels
        for j in range(5):
            v = full * (4 - j) / 4
            self.create_text(
                x0 - px(6), y0 + ph * j / 4, text=_fmt_num(v) + (" ms" if j == 0 else ""),
                anchor="e", fill=c["screen_text"], font=f["mono_xs"],
            )  # fmt: skip
        step = tdiv * 2
        k = 0
        while k * step <= dur + 1e-9:
            x = x0 + pw * (k * step) / dur
            if k == 0 or x < x1 - px(18):
                self.create_text(
                    x, y1 + px(7), text=_fmt_num(k * step) + (" s" if k == 0 else ""),
                    anchor="n" if k else "nw", fill=c["screen_text"], font=f["mono_xs"],
                )  # fmt: skip
            k += 1

        def X(i: int, of: Trace = tr) -> float:
            # each capture on its own seconds; the axis spans the longer one
            return x0 + pw * ((i + 0.5) / of.buckets * of.duration_s) / dur

        def Y(v: float) -> float:
            return y1 - ph * min(v, full) / full

        def polyline(values, color, width, of: Trace = tr):
            seg: list[float] = []
            for i, v in enumerate(values):
                if v is None:
                    if len(seg) >= 4:
                        self.create_line(
                            *seg, fill=color, width=width, capstyle="butt", joinstyle="miter"
                        )
                    seg = []
                    continue
                seg += [X(i, of), Y(v)]
            if len(seg) >= 4:
                self.create_line(*seg, fill=color, width=width, capstyle="butt", joinstyle="miter")

        line = max(2, px(2))
        # layers, bottom to top: hitch markers, CH1 band, CH3, CH2, REF, CH1 median
        if self.channels["ch1"]:
            dash = mix(c["hitch"], c["screen"], 0.7)
            for t_s, _ms in tr.hitches:
                x = x0 + pw * min(t_s, dur) / dur
                self.create_line(x, y0, x, y1, fill=dash, dash=(3, 3))
            up = [(X(i), Y(v)) for i, v in enumerate(tr.p95) if v is not None]
            dn = [(X(i), Y(v)) for i, v in reversed(list(enumerate(tr.p5))) if v is not None]
            if len(up) > 1:
                self.create_polygon(
                    *[p for xy in up + dn for p in xy],
                    fill=mix(c["ch1"], c["screen"], 0.18),
                    outline="",
                )
        if self.channels["ch3"]:
            polyline(tr.cpu, c["ch3"], px(1))
        if self.channels["ch2"]:
            polyline(tr.gpu, c["ch2"], px(1))
        if ref is not None:  # over B's band, under B's line: where they differ, both show
            polyline(ref.p50, c["ref"], line, of=ref)
        if self.channels["ch1"]:
            polyline(tr.p50, mix(c["ch1"], c["screen"], 0.35), line * 2)  # phosphor bloom
            polyline(tr.p50, c["ch1"], line)
            for t_s, ms in tr.hitches:
                x = x0 + pw * min(t_s, dur) / dur
                self.create_line(x, Y(ms), x, y1, fill=c["ch1"], width=px(1), capstyle="butt")
            if tr.hitches:
                t_s, ms = max(tr.hitches, key=lambda hh: hh[1])
                x = x0 + pw * min(t_s, dur) / dur
                right = x < x1 - px(140)
                tid = self.create_text(
                    x + px(6) if right else x - px(6), y0 + px(2),
                    text=f"{ms:.1f} ms @ {t_s:.1f} s", anchor="nw" if right else "ne",
                    fill=c["hitch"], font=f["mono_xs"],
                )  # fmt: skip
                bx = self.bbox(tid)
                if bx:
                    bg = self.create_rectangle(
                        bx[0] - px(3), bx[1], bx[2] + px(3), bx[3], fill=c["screen"], width=0
                    )
                    self.tag_lower(bg, tid)


class Tabs(tk.Frame):
    """Underline tabs with silk-screen labels."""

    def __init__(self, parent, t: Theme, names: list[str], command: Callable[[str], None]):
        super().__init__(parent, bg=t.c["background"])
        self.t, self.command, self.tabs, self.disabled = t, command, {}, set()
        self.current, self.hover = names[0], None
        self.names = names
        row = frame(self, t)
        row.pack(fill="x")
        for name in names:
            cell = frame(row, t)
            cell.pack(side="left", padx=(0, px(24)))
            lab = silk(cell, t, name, cursor="hand2")
            lab.pack(pady=(px(8), px(8)))
            bar = tk.Frame(cell, height=2, bg=t.c["background"])
            bar.pack(fill="x")
            lab.bind("<Button-1>", lambda _e, n=name: self.select(n))
            lab.bind("<Enter>", lambda _e, n=name: self._hover(n))
            lab.bind("<Leave>", lambda _e: self._hover(None))
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

    def cycle(self, step: int) -> None:
        """Next or previous enabled tab (Ctrl+Tab)."""
        names = [n for n in self.names if n not in self.disabled]
        if self.current in names:
            self.select(names[(names.index(self.current) + step) % len(names)])

    def set_disabled(self, name: str, disabled: bool) -> None:
        (self.disabled.add if disabled else self.disabled.discard)(name)
        self._paint()

    def _hover(self, name: str | None) -> None:
        self.hover = name
        self._paint()

    def _paint(self) -> None:
        c = self.t.c
        for name, (lab, bar) in self.tabs.items():
            on = name == self.current
            if on:
                fg = "text1"
            elif name in self.disabled:
                fg = "text4"
            else:
                fg = "text2" if name == self.hover else "text3"
            lab.configure(fg=c[fg], cursor="arrow" if name in self.disabled else "hand2")
            bar.configure(bg=c["accent"] if on else c["background"])


class ThinScrollbar(tk.Canvas):
    """A 6 px scrollbar: a flat thumb, no arrows, drawn only when there is more to see.

    Takes the same set(lo, hi) calls as a Tk scrollbar and calls command("moveto", f).
    """

    def __init__(self, parent, t: Theme, command: Callable, bg="background", width=6):
        super().__init__(parent, width=px(width), bg=t.c[bg], highlightthickness=0, bd=0)
        self.t, self.command = t, command
        self.lo, self.hi = 0.0, 1.0
        self.grab: float | None = None
        self.hot = False
        self.bind("<Configure>", lambda _e: self.draw())
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<ButtonRelease-1>", lambda _e: self._release())
        self.bind("<Enter>", lambda _e: self._set_hot(True))
        self.bind("<Leave>", lambda _e: self._set_hot(False))

    @property
    def needed(self) -> bool:
        return not (self.lo <= 0.0 and self.hi >= 1.0)

    def set(self, lo, hi) -> None:
        self.lo, self.hi = float(lo), float(hi)
        self.draw()

    def _thumb(self) -> tuple[float, float]:
        h = self.winfo_height()
        size = max(px(24), (self.hi - self.lo) * h)
        top = self.lo * h if self.hi < 1.0 else h - size
        return min(top, h - size), min(top, h - size) + size

    def draw(self) -> None:
        self.delete("all")
        if not self.needed:
            return
        top, bottom = self._thumb()
        key = "text4" if self.hot or self.grab is not None else "surface3"
        self.create_rectangle(0, top, self.winfo_width(), bottom, fill=self.t.c[key], width=0)

    def _set_hot(self, on: bool) -> None:
        self.hot = on
        self.draw()

    def _press(self, e) -> None:
        if not self.needed:
            return
        top, bottom = self._thumb()
        if not top <= e.y <= bottom:  # jump so the thumb centres on the click
            span = (self.hi - self.lo) * self.winfo_height()
            self.command("moveto", (e.y - span / 2) / max(1, self.winfo_height()))
            top, _ = self._thumb()
        self.grab = e.y - top
        self.draw()

    def _drag(self, e) -> None:
        if self.grab is not None:
            self.command("moveto", (e.y - self.grab) / max(1, self.winfo_height()))

    def _release(self) -> None:
        self.grab = None
        self.draw()


def wheel_steps(event) -> int:
    """Scroll units for one mouse-wheel event (Windows deltas of 120, X11 buttons 4/5)."""
    if getattr(event, "num", None) == 4:
        return -1
    if getattr(event, "num", None) == 5:
        return 1
    d = getattr(event, "delta", 0)
    return int(-d / 120) or (-1 if d > 0 else 1 if d < 0 else 0)


class ScrollFrame(tk.Frame):
    """A vertically scrolling frame; .inner is where children go.

    The thin scrollbar always keeps its gutter, so the content's right edge does not move
    when the page gets long enough to scroll.
    """

    def __init__(self, parent, t: Theme, bg="background"):
        super().__init__(parent, bg=t.c[bg])
        self.canvas = tk.Canvas(
            self, bg=t.c[bg], highlightthickness=0, bd=0, yscrollincrement=px(24)
        )
        self.bar = ThinScrollbar(self, t, self.canvas.yview, bg=bg)
        self.inner = tk.Frame(self.canvas, bg=t.c[bg])
        self.window = self.canvas.create_window(0, 0, window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y", padx=(px(8), 0))
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
        bbox = self.canvas.bbox("all")
        if bbox:
            # never scroll above the top, and never past the content
            h = max(bbox[3], self.canvas.winfo_height())
            self.canvas.configure(scrollregion=(0, 0, bbox[2], h))

    def scroll(self, units: int) -> None:
        if self.bar.needed and units:
            self.canvas.yview_scroll(units * 2, "units")

    def _wheel(self, on: bool) -> None:
        if on:
            self.bind_all("<MouseWheel>", lambda e: self.scroll(wheel_steps(e)))
            self.bind_all("<Button-4>", lambda e: self.scroll(wheel_steps(e)))
            self.bind_all("<Button-5>", lambda e: self.scroll(wheel_steps(e)))
        else:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                self.unbind_all(seq)

    def to_top(self) -> None:
        self.canvas.yview_moveto(0)


def placeholder(entry: tk.Widget, t: Theme, variable: tk.StringVar, text: str, bg="background"):
    """Quiet hint text inside an empty entry; it hides while the entry has focus or a value."""
    hint = tk.Label(
        entry, text=text, font=t.fonts["mono_sm"], fg=t.c["text4"], bg=t.c[bg], bd=0,
        padx=0, pady=0, cursor="xterm",
    )  # fmt: skip

    def update(*_) -> None:
        try:
            focused = entry.focus_get() is entry
        except (KeyError, tk.TclError):
            focused = False
        if variable.get() or focused:
            hint.place_forget()
        else:
            hint.place(x=px(9), rely=0.5, anchor="w")

    def focus(_e=None) -> None:
        entry.focus_set()

    hint.bind("<Button-1>", focus)
    entry.bind("<FocusIn>", update, add="+")
    entry.bind("<FocusOut>", update, add="+")
    trace_id = variable.trace_add("write", update)

    def untrace(event) -> None:
        if event.widget is entry:
            try:
                variable.trace_remove("write", trace_id)
            except tk.TclError:
                pass

    entry.bind("<Destroy>", untrace, add="+")
    update()
    return hint


def wordmark(parent, t: Theme, bg="background", size=22) -> tk.Frame:
    """The trace glyph plus the name."""
    f = frame(parent, t, bg)
    size = px(size)
    glyph = tk.Canvas(
        f, width=size, height=math.ceil(size * 14 / 22), bg=t.c[bg], highlightthickness=0, bd=0
    )
    s = size / 22
    glyph.create_line(
        0, 11 * s, 6 * s, 11 * s, 8 * s, 2 * s, 10 * s, 12 * s, 12 * s, 7 * s, 22 * s, 7 * s,
        fill=t.c["ch1"], width=max(2, px(2)), capstyle="butt", joinstyle="miter",
    )  # fmt: skip
    glyph.pack(side="left", padx=(0, px(8)))
    label(f, t, "Frametrace", font="wordmark", bg=bg).pack(side="left")
    return f
