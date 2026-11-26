"""Generate the README brand images in docs/brand/ (design/frametrace-design).

GitHub renders README images without web fonts, so every word is set in the bundled IBM Plex
TTFs, shaped with HarfBuzz and written as SVG outlines. The frame-time trace in the banner is
decorative: a deterministic synthetic capture shaped like a CS2 benchmark run. The readout
values are from the real CS2 Reflex On run in docs/presentmon.md.

    python -m pip install fonttools uharfbuzz
    python tools/brand.py
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "frametrace" / "assets" / "fonts"
OUT = ROOT / "docs" / "brand"

DARK = {
    "background": "#141413", "surface1": "#1C1C1A", "surface2": "#252522", "surface3": "#3A3A36",
    "border": "#252522", "border_visible": "#3A3A36",
    "text1": "#ECEAE4", "text2": "#A8A59D", "text3": "#8C8A83", "text4": "#66645E",
}  # fmt: skip
LIGHT = {
    "background": "#F7F6F2", "surface1": "#ECEAE4", "surface2": "#DFDDD6", "surface3": "#C8C5BC",
    "border": "#DFDDD6", "border_visible": "#C8C5BC",
    "text1": "#141413", "text2": "#3A3A36", "text3": "#66645E", "text4": "#A8A59D",
}  # fmt: skip
# The scope screen and the signals are the same in both modes.
SIG = {
    "screen": "#141413", "graticule": "#252522", "screen_text": "#8C8A83",
    "ch1": "#F5C518", "ch2": "#35C4DC", "ch3": "#E0559F", "hitch": "#F0883E",
    "trace": "#F5C518", "on_accent": "#141413", "error": "#F2555A", "success": "#3FB950",
}  # fmt: skip


class Face:
    """One static IBM Plex weight: shapes a string and returns it as an SVG path."""

    def __init__(self, name: str):
        path = FONTS / name
        self.tt = TTFont(path)
        self.glyphs = self.tt.getGlyphSet()
        self.order = self.tt.getGlyphOrder()
        self.upm = self.tt["head"].unitsPerEm
        self.font = hb.Font(hb.Face(hb.Blob.from_file_path(str(path))))

    def _shape(self, text: str):
        buf = hb.Buffer()
        buf.add_str(text)
        buf.guess_segment_properties()
        hb.shape(self.font, buf, {"kern": True, "liga": False})
        return list(zip(buf.glyph_infos, buf.glyph_positions, strict=True))

    def width(self, text: str, size: float, tracking: float = 0.0) -> float:
        runs = self._shape(text)
        return sum(p.x_advance + tracking * self.upm for _, p in runs) * size / self.upm

    def path(
        self, text: str, size: float, x: float, y: float, fill: str, tracking=0.0, anchor="start"
    ) -> str:
        """y is the baseline. tracking in em. anchor: start, middle, end."""
        w = self.width(text, size, tracking)
        x -= {"start": 0, "middle": w / 2, "end": w}[anchor]
        s = size / self.upm
        pen = SVGPathPen(self.glyphs, ntos=lambda v: f"{v:.1f}".rstrip("0").rstrip("."))
        cx = 0.0
        for info, pos in self._shape(text):
            tp = TransformPen(pen, (s, 0, 0, -s, x + (cx + pos.x_offset) * s, y - pos.y_offset * s))
            self.glyphs[self.order[info.codepoint]].draw(tp)
            cx += pos.x_advance + tracking * self.upm
        return f'<path fill="{fill}" d="{pen.getCommands()}"/>'


SANS = Face("IBMPlexSans-Regular.ttf")
SANS_MED = Face("IBMPlexSans-Medium.ttf")
SANS_SEMI = Face("IBMPlexSans-SemiBold.ttf")
MONO = Face("IBMPlexMono-Regular.ttf")
MONO_MED = Face("IBMPlexMono-Medium.ttf")


def label(text, x, y, fill, size=11, anchor="start"):
    """Silk-screen label: uppercase Plex Sans 500 at 0.08em."""
    return SANS_MED.path(text.upper(), size, x, y, fill, tracking=0.08, anchor=anchor)


def rect(x, y, w, h, fill, r=0, stroke=None):
    s = f' stroke="{stroke}" stroke-width="1"' if stroke else ""
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}"{s}/>'


def line(x1, y1, x2, y2, stroke, w=1.0, extra=""):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{w}" stroke-linecap="butt"{extra}/>'


def glyph_mark(x, y, size, color):
    """The trace mark: a flat line, one spike, settle."""
    s = size / 22
    pts = [(0, 11), (6, 11), (8, 2), (10, 12), (12, 7), (22, 7)]
    d = " ".join(f"{x + px * s:.1f},{y + py * s:.1f}" for px, py in pts)
    return f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{max(1.75, 2 * s):.2f}" stroke-linecap="butt" stroke-linejoin="miter"/>'


# --- a deterministic CS2-shaped capture -------------------------------------------------------

HITCHES = [(23.0, 9.6), (61.4, 14.8), (84.2, 11.2)]


def capture(seed=7, seconds=100.0):
    rnd = random.Random(seed)
    t, frames = 0.0, []
    while t < seconds:
        scene = (
            2.2 + 0.45 * math.sin(t / 7.3) + 0.25 * math.sin(t / 2.1 + 1.3)
            + 0.35 * math.exp(-(((t - 38) / 6) ** 2)) - 0.5 * math.exp(-(((t - 91) / 3) ** 2))
        )  # fmt: skip
        gpu = max(0.9, scene * 0.9 + rnd.gauss(0, 0.07))
        cpu = max(0.4, 0.95 + 0.25 * math.sin(t / 5.1) + rnd.gauss(0, 0.06))
        ft = gpu + 0.22 + abs(rnd.gauss(0, 0.12))
        if rnd.random() < 0.013:
            ft += rnd.uniform(3.0, 5.6)
            cpu += rnd.uniform(0.8, 2.5)
        for ht, hv in HITCHES:
            if abs(t - ht) < 0.0015:
                ft, cpu = hv, hv - 1.9
        frames.append((t, ft, gpu, cpu))
        t += ft / 1000
    return frames


def _pct(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]


def trace_svg(frames, x0, y0, w, h, full_ms, cols=None):
    """Band (P5..P95) and median of CH1, medians of CH2/CH3, hitch markers."""
    cols = cols or int(w / 2)
    t1 = frames[-1][0]
    buckets = [[] for _ in range(cols)]
    for f in frames:
        buckets[min(cols - 1, int(f[0] / t1 * cols))].append(f)

    def X(i):
        return x0 + w * (i + 0.5) / cols

    def Y(v):
        return y0 + h - h * min(v, full_ms) / full_ms

    def pts(values):
        return " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(values))

    p5 = [_pct([f[1] for f in b], 0.05) for b in buckets]
    p50 = [_pct([f[1] for f in b], 0.5) for b in buckets]
    p95 = [_pct([f[1] for f in b], 0.95) for b in buckets]
    gpu = [_pct([f[2] for f in b], 0.5) for b in buckets]
    cpu = [_pct([f[3] for f in b], 0.5) for b in buckets]
    band = (
        pts(p95)
        + " "
        + " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in reversed(list(enumerate(p5))))
    )
    out = []
    for ht, hv in HITCHES:
        x = x0 + w * ht / t1
        out.append(
            line(
                f"{x:.1f}",
                y0,
                f"{x:.1f}",
                y0 + h,
                SIG["hitch"],
                1,
                ' stroke-dasharray="3 3" opacity="0.7"',
            )
        )
    out += [
        f'<polyline points="{pts(cpu)}" fill="none" stroke="{SIG["ch3"]}" stroke-width="1.25" stroke-linecap="butt"/>',
        f'<polyline points="{pts(gpu)}" fill="none" stroke="{SIG["ch2"]}" stroke-width="1.25" stroke-linecap="butt"/>',
        f'<polygon points="{band}" fill="{SIG["ch1"]}" opacity="0.18"/>',
        f'<polyline points="{pts(p50)}" fill="none" stroke="{SIG["ch1"]}" stroke-width="3.5" stroke-linecap="butt" opacity="0.35" filter="url(#bloom)"/>',
        f'<polyline points="{pts(p50)}" fill="none" stroke="{SIG["ch1"]}" stroke-width="1.75" stroke-linecap="butt"/>',
    ]
    for ht, hv in HITCHES:
        x = x0 + w * ht / t1
        out.append(line(f"{x:.1f}", f"{Y(hv):.1f}", f"{x:.1f}", y0 + h, SIG["ch1"], 1.75))
    return "\n".join(out)


def svg(w, h, body, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">\n'
        f"<title>{title}</title>\n"
        '<defs><filter id="bloom" x="-5%" y="-50%" width="110%" height="200%"><feGaussianBlur stdDeviation="2"/></filter></defs>\n'
        f"{body}\n</svg>\n"
    )


# --- banner -----------------------------------------------------------------------------------


def readout_chip(x, y, title, value, unit, swatch=None, w=176):
    c = DARK
    parts = [rect(x + 0.5, y + 0.5, w, 72, c["surface1"], 4, c["border_visible"])]
    lx = x + 16
    if swatch:
        parts.append(rect(lx, y + 15, 8, 8, swatch, 1))
        lx += 14
    parts.append(label(title, lx, y + 23, c["text3"]))
    parts.append(MONO_MED.path(value, 26, x + 16, y + 56, c["text1"]))
    vw = MONO_MED.width(value, 26)
    parts.append(MONO.path(unit, 12, x + 16 + vw + 5, y + 56, c["text3"]))
    return "\n".join(parts)


def banner() -> str:
    W, H = 1280, 440
    c = DARK
    body = [rect(0, 0, W, H, SIG["screen"], 4)]
    # graticule: 10 x 5 major divisions, minor ticks on the centre lines
    gx0, gy0, gw, gh = 0, 0, W, H
    for i in range(1, 10):
        x = gx0 + gw * i / 10
        body.append(line(x, gy0, x, gy0 + gh, SIG["graticule"]))
    for j in range(1, 5):
        y = gy0 + gh * j / 5
        body.append(line(gx0, y, gx0 + gw, y, SIG["graticule"]))
    cy, cx = gy0 + gh * 3 / 5, gx0 + gw / 2
    for k in range(1, 50):
        x = gx0 + gw * k / 50
        body.append(line(x, cy - 3, x, cy + 3, SIG["graticule"]))
    for k in range(1, 25):
        y = gy0 + gh * k / 25
        body.append(line(cx - 3, y, cx + 3, y, SIG["graticule"]))

    # header
    body.append(glyph_mark(56, 52, 30, SIG["ch1"]))
    body.append(SANS_SEMI.path("Frametrace", 26, 98, 72, c["text1"]))
    body.append(label("Open source · MIT · Windows 10 and 11", W - 56, 70, c["text3"], 12, "end"))

    # claim
    plate = rect(48, 112, 640, 132, SIG["screen"])  # keeps the graticule from crossing the type
    body.append(plate)
    body.append(SANS_SEMI.path("Answers, not graphs.", 60, 56, 176, c["text1"], tracking=-0.02))
    body.append(
        SANS.path("Frame times, a CPU or GPU verdict and one report", 20, 58, 214, c["text2"])
    )
    body.append(SANS.path("you can paste into any AI.", 20, 58, 240, c["text2"]))

    # readouts (CS2 benchmark map, Reflex On, from the validation runs)
    rx = W - 56 - 176
    body.append(readout_chip(rx - 188, 112, "Average", "426.7", "FPS", SIG["ch1"]))
    body.append(readout_chip(rx, 112, "GPU-limited", "93", "% of frames", SIG["ch2"]))
    body.append(readout_chip(rx - 188, 192, "CPU-side 1% low", "199", "FPS"))
    body.append(readout_chip(rx, 192, "PC latency", "6.8", "ms"))

    # the trace across the lower screen
    body.append(trace_svg(capture(), 0, 276, W, 132, 7.5))
    body.append(rect(0, 408, W, 32, SIG["screen"]))
    lx = 56
    for key, name in (("ch1", "CH1 frame time"), ("ch2", "CH2 GPU busy"), ("ch3", "CH3 CPU busy")):
        body.append(rect(lx, 418, 8, 8, SIG[key], 1))
        body.append(label(name, lx + 14, 426, c["text3"]))
        lx += 14 + SANS_MED.width(name.upper(), 11, 0.08) + 28
    body.append(
        MONO.path(
            "10 s/div · CS2 benchmark map, Reflex on", 11, W - 56, 426, c["text3"], anchor="end"
        )
    )
    hx = W * 61.4 / 100
    body.append(rect(hx + 6, 282, MONO.width("14.8 ms @ 61.4 s", 11) + 8, 16, SIG["screen"]))
    body.append(MONO.path("14.8 ms @ 61.4 s", 11, hx + 10, 294, SIG["hitch"]))
    return svg(W, H, "\n".join(body), "Frametrace. Answers, not graphs.")


# --- how it works -----------------------------------------------------------------------------


def _runs(text):
    """'Press `F10` now' -> [('Press ', False), ('F10', True), (' now', False)]."""
    return [(part, i % 2 == 1) for i, part in enumerate(text.split("`")) if part]


def rich_width(text, face, mono, size):
    return sum((mono if m else face).width(t, size) for t, m in _runs(text))


def rich(text, face, mono, size, x, y, fill, mono_fill=None):
    """Words in the sans, `ticked` parts in Plex Mono."""
    out = []
    for t, m in _runs(text):
        f = mono if m else face
        out.append(f.path(t, size, x, y, (mono_fill or fill) if m else fill))
        x += f.width(t, size)
    return "\n".join(out)


def wrap(face, text, size, width, mono=None):
    mono = mono or MONO
    words, lines, cur = text.split(" "), [], ""
    for wd in words:
        trial = (cur + " " + wd).strip()
        if rich_width(trial, face, mono, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = wd
    return lines + ([cur] if cur else [])


def how_it_works(c: dict) -> str:
    W, H, gap, pad = 1280, 286, 16, 20
    pw = (W - 3 * gap) / 4
    steps = [
        (
            "01 · Capture",
            "Press `F10` in game",
            "Any `DX11`, `DX12`, `Vulkan` or `OpenGL` game. No overlay, no injection.",
        ),
        (
            "02 · Measure",
            "Every frame, recorded",
            "Intel PresentMon reads frame events from Windows for `30 s`, or until `F10` again.",
        ),
        (
            "03 · Verdict",
            "GPU-limited.",
            "Frame by frame: was the GPU busy, or the CPU? Plus lows, hitches, PC latency.",
        ),
        (
            "04 · Report",
            "Paste into any AI",
            "One short report with the system checks, copied to the clipboard.",
        ),
    ]
    body = []
    for i, (eyebrow, title, text) in enumerate(steps):
        x = i * (pw + gap)
        body.append(rect(x + 0.5, 0.5, pw - 1, H - 1, c["surface1"], 4, c["border"]))
        body.append(label(eyebrow, x + pad, 32, c["text3"]))
        body.append(rich(title, SANS_SEMI, MONO_MED, 18, x + pad, 62, c["text1"]))
        for k, ln in enumerate(wrap(SANS, text, 13, pw - 2 * pad)):
            body.append(rich(ln, SANS, MONO, 13, x + pad, 90 + k * 20, c["text2"], c["text1"]))
        vy, vw, vh = 150, pw - 2 * pad, 112  # visual well
        vx = x + pad
        if i == 0:  # key cap and a recording lamp
            kw = MONO.width("F10", 15) + 24
            body.append(rect(vx + 0.5, vy + 22.5, kw, 34, c["surface2"], 2, c["border_visible"]))
            body.append(line(vx + 1, vy + 56.5, vx + kw, vy + 56.5, c["border_visible"], 2))
            body.append(MONO.path("F10", 15, vx + 12, vy + 45, c["text1"]))
            body.append(rect(vx, vy + 80, 8, 8, c["error_lamp"], 1))
            body.append(label("REC", vx + 14, vy + 88, c["text1"]))
            body.append(MONO.path("00:42 / 01:40", 12, vx + 46, vy + 88, c["text3"]))
        elif i == 1:  # a small scope (stays dark)
            body.append(rect(vx, vy, vw, vh, SIG["screen"], 2))
            for k in range(1, 6):
                gx = vx + vw * k / 6
                body.append(line(gx, vy, gx, vy + vh, SIG["graticule"]))
            for k in range(1, 3):
                gy = vy + vh * k / 3
                body.append(line(vx, gy, vx + vw, gy, SIG["graticule"]))
            body.append(trace_svg(capture(), vx, vy + 8, vw, vh - 16, 7.0, cols=int(vw / 3)))
        elif i == 2:  # split bar with legend
            sx, sw = vx, vw
            parts = ((0.93, SIG["ch2"]), (0.04, SIG["ch3"]), (0.03, c["text4"]))
            px = sx
            for share, color in parts:
                seg = sw * share
                body.append(rect(f"{px:.1f}", vy + 30, f"{max(seg - 1, 1):.1f}", 8, color))
                px += seg
            lx = sx
            for name, pct, color in (
                ("GPU", "93%", SIG["ch2"]),
                ("CPU", "4%", SIG["ch3"]),
                ("Waiting", "3%", c["text4"]),
            ):
                body.append(rect(lx, vy + 56, 8, 8, color, 1))
                body.append(SANS.path(name, 12, lx + 14, vy + 64, c["text3"]))
                nx = lx + 14 + SANS.width(name, 12) + 5
                body.append(MONO.path(pct, 12, nx, vy + 64, c["text1"]))
                lx = nx + MONO.width(pct, 12) + 16
            body.append(MONO.path("median GPU busy 2.08 ms", 12, sx, vy + 94, c["text3"]))
        else:  # report lines and a copied lamp
            lines = [
                ("## Performance", c["text1"]),
                ("Average 426.7 FPS", c["text2"]),
                ("1% low 169 | P99 5.92 ms", c["text2"]),
            ]
            for k, (ln, col) in enumerate(lines):
                body.append(MONO.path(ln, 12, vx, vy + 26 + k * 20, col))
            body.append(rect(vx, vy + 80, 8, 8, c["success_lamp"], 1))
            body.append(label("Copied", vx + 14, vy + 88, c["text1"]))
        if i < 3:  # connector
            ax = x + pw + gap / 2
            body.append(
                f'<polyline points="{ax - 3:.1f},{H / 2 - 5} {ax + 2:.1f},{H / 2} {ax - 3:.1f},{H / 2 + 5}" fill="none" stroke="{c["text4"]}" stroke-width="1.5" stroke-linecap="butt" stroke-linejoin="miter"/>'
            )
    return svg(W, H, "\n".join(body), "How Frametrace works: capture, measure, verdict, report")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "banner.svg").write_text(banner(), encoding="utf-8")
    (OUT / "how-it-works-dark.svg").write_text(
        how_it_works({**DARK, "success_lamp": "#3FB950", "error_lamp": "#F2555A"}), encoding="utf-8"
    )
    (OUT / "how-it-works-light.svg").write_text(
        how_it_works({**LIGHT, "success_lamp": "#1F7A33", "error_lamp": "#B42328"}),
        encoding="utf-8",
    )
    for f in sorted(OUT.glob("*.svg")):
        print(f.relative_to(ROOT), f"{f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
