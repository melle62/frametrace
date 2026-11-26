"""Generate the window and taskbar icon in frametrace/assets/ (design/frametrace-design).

The mark is the trace glyph from the wordmark (a flat line, one spike, settle) in the trace
yellow on a graphite screen with a machined edge. Square corners, butt caps, no gradient.
The app loads the PNGs at runtime with Tk (stdlib only); the .ico is for the packaged .exe.

    python -m pip install pillow
    python tools/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frametrace" / "assets"

SCREEN, EDGE, TRACE = "#141413", "#3A3A36", "#F5C518"
GLYPH = [(0, 11), (6, 11), (8, 2), (10, 12), (12, 7), (22, 7)]  # 22 x 14 design units


def icon(size: int) -> Image.Image:
    ss = 8  # draw large, then downsample: the only smoothing is antialiasing
    big = size * ss
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    edge = max(1, round(size / 64)) * ss
    d.rectangle([0, 0, big - 1, big - 1], fill=EDGE)
    d.rectangle([edge, edge, big - 1 - edge, big - 1 - edge], fill=SCREEN)
    # glyph: 76% of the width, centred; thicker strokes at small sizes so it survives 16 px
    gw = big * 0.76
    s = gw / 22
    ox, oy = (big - gw) / 2, (big - 14 * s) / 2 - s * 0.5
    stroke = big * (0.12 if size <= 16 else 0.09 if size <= 32 else 0.06)
    pts = [(ox + x * s, oy + y * s) for x, y in GLYPH]
    d.line(pts, fill=TRACE, width=round(stroke), joint="curve" if size <= 24 else None)
    return im.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = {s: icon(s) for s in sizes}
    for s in (16, 32, 48, 256):
        images[s].save(OUT / f"icon-{s}.png")
    images[256].save(OUT / "frametrace.ico", sizes=[(s, s) for s in sizes])
    print("wrote", ", ".join(f"icon-{s}.png" for s in (16, 32, 48, 256)), "and frametrace.ico")


if __name__ == "__main__":
    main()
