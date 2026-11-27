"""Frametrace design tokens for Tkinter: colors, fonts and ttk styles.

Values come from design/frametrace-design/design-model.yaml ("bench instrument"):
warm graphite panels, one yellow trace, cyan for the GPU, magenta for the CPU, IBM Plex
Sans for words and IBM Plex Mono for every number. The scope screen and the channel
colors are the same in both modes.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # tkinter is imported where it's used, so the palette works without it
    import tkinter as tk
    import tkinter.font as tkfont

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
FR_PRIVATE = 0x10

DARK = {
    "background": "#141413", "surface1": "#1C1C1A", "surface2": "#252522", "surface3": "#3A3A36",
    "border": "#252522", "border_visible": "#3A3A36",
    "text1": "#ECEAE4", "text2": "#A8A59D", "text3": "#8C8A83", "text4": "#66645E",
    "accent": "#F5C518", "accent_hover": "#F6CB33", "accent_pressed": "#C9A10E",
    "accent_subtle": "#2B2203", "on_accent": "#141413", "trace": "#F5C518",
    "ch1": "#F5C518", "ch2": "#35C4DC", "ch3": "#E0559F",
    "screen": "#141413", "graticule": "#252522", "screen_text": "#8C8A83", "hitch": "#F0883E",
    "ref": "#A8A59D",
    "success": "#3FB950", "warning": "#F0883E", "error": "#F2555A",
    "success_bg": "#12381A", "warning_bg": "#4A2410", "error_bg": "#3D1113",
}  # fmt: skip
LIGHT = {
    **DARK,
    "background": "#F7F6F2", "surface1": "#ECEAE4", "surface2": "#DFDDD6", "surface3": "#C8C5BC",
    "border": "#DFDDD6", "border_visible": "#C8C5BC",
    "text1": "#141413", "text2": "#3A3A36", "text3": "#66645E", "text4": "#A8A59D",
    "accent": "#7F6100", "accent_hover": "#5E4800", "accent_subtle": "#FEF9E7",
    "success": "#1F7A33", "warning": "#A9541A", "error": "#B42328",
    "success_bg": "#EAF7EC", "warning_bg": "#FDF1E8", "error_bg": "#FDECEC",
}  # fmt: skip
PALETTES = {"dark": DARK, "light": LIGHT}

# GDI gives every static weight of IBM Plex its own family name, and Tk only knows
# normal and bold, so weights are picked by family. Fallbacks ship with Windows.
FAMILIES = {
    "sans": ("IBM Plex Sans", "Segoe UI"),
    "sans_medium": ("IBM Plex Sans Medm", "Segoe UI Semibold"),
    "sans_semibold": ("IBM Plex Sans SmBld", "Segoe UI Semibold"),
    "mono": ("IBM Plex Mono", "Consolas"),
    "mono_medium": ("IBM Plex Mono Medm", "Consolas"),
}
# (family key, points). Points at 96 DPI = px * 0.75; Tk scales points with the monitor.
TYPE = {
    "display": ("sans_semibold", 30),
    "heading": ("sans_semibold", 20),
    "subheading": ("sans_semibold", 13),
    "body": ("sans", 11),
    "body_sm": ("sans", 10),
    "caption": ("sans", 9),
    "label": ("sans_medium", 8),
    "group": ("sans_medium", 10),  # a heading in the captures list: body-sm at 500
    "button": ("sans_semibold", 10),
    "mono": ("mono", 10),
    "mono_sm": ("mono", 9),
    "mono_xs": ("mono", 8),
    "mono_head": ("mono_medium", 9),
    "readout": ("mono_medium", 22),
    "readout_sm": ("mono_medium", 16),  # a readout that would not fit its tile
    "wordmark": ("sans_semibold", 12),
}
SPACE = {"2xs": 2, "xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32, "2xl": 48}

# Tk scales fonts (points) with the monitor's DPI but not pixel sizes. px() scales the
# structural sizes (window, rail, scope, bars) by the same factor, so a 125% or 150%
# Windows display gets the same layout as 100%, only larger.
SCALE = 1.0
HAIR = " "  # hair space: about 0.08em in IBM Plex, the silk-screen tracking


def set_scale(root: tk.Misc) -> float:
    """Read the display scale from Tk (1.0 at 96 DPI) and remember it for px()."""
    global SCALE
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except Exception:  # noqa: BLE001 - no display: keep 1.0
        dpi = 96.0
    SCALE = scale_for(dpi)
    return SCALE


def scale_for(dpi: float) -> float:
    """96 DPI and anything close to it is 1.0; above that, steps of 0.25 (125%, 150%...)."""
    factor = dpi / 96.0
    if factor < 1.12:
        return 1.0
    return min(3.0, round(factor * 4) / 4)


def px(value: float) -> int:
    """A pixel size from the design, scaled for the display."""
    return round(value * SCALE)


def track(text: str) -> str:
    """Silk-screen tracking (0.08em) for uppercase labels: Tk has no letter-spacing."""
    return HAIR.join(text)


def untrack(text: str) -> str:
    return text.replace(HAIR, "")


def mix(fg: str, bg: str, alpha: float) -> str:
    """fg over bg at alpha, as an opaque color (Tk canvases have no transparency)."""
    a = [int(fg[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(bg[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(
        f"{round(x * alpha + y * (1 - alpha)):02X}" for x, y in zip(a, b, strict=True)
    )


def load_fonts() -> bool:
    """Register the bundled IBM Plex TTFs for this process only (Windows)."""
    if sys.platform != "win32":
        return False
    try:
        gdi32 = ctypes.windll.gdi32
    except AttributeError:
        return False
    ok = True
    for ttf in sorted(FONT_DIR.glob("*.ttf")):
        ok &= gdi32.AddFontResourceExW(str(ttf), FR_PRIVATE, 0) > 0
    return ok


@dataclass
class Theme:
    name: str
    c: dict
    fonts: dict

    @property
    def dark(self) -> bool:
        return self.name == "dark"


def make_fonts(root: tk.Misc) -> dict[str, tkfont.Font]:
    import tkinter.font as tkfont

    available = set(tkfont.families(root))
    chosen = {
        key: next((f for f in options if f in available), options[-1])
        for key, options in FAMILIES.items()
    }
    return {
        role: tkfont.Font(root, family=chosen[fam], size=size) for role, (fam, size) in TYPE.items()
    }


def apply(root: tk.Tk, name: str = "dark", fonts: dict | None = None) -> Theme:
    """Configure ttk for the palette and return the theme the widgets read from."""
    from tkinter import ttk

    c = PALETTES[name]
    fonts = fonts or make_fonts(root)
    root.configure(bg=c["background"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(
        ".",
        background=c["background"],
        foreground=c["text1"],
        fieldbackground=c["background"],
        bordercolor=c["border_visible"],
        lightcolor=c["background"],
        darkcolor=c["background"],
        troughcolor=c["background"],
        focuscolor=c["accent"],
        selectbackground=c["surface2"],
        selectforeground=c["text1"],
        insertcolor=c["text1"],
        arrowcolor=c["text3"],
        font=fonts["body_sm"],
    )
    field = {
        "fieldbackground": c["background"],
        "foreground": c["text1"],
        "bordercolor": c["border_visible"],
        "lightcolor": c["background"],
        "darkcolor": c["background"],
        "padding": (8, 5),
    }
    style.configure("TEntry", **field)
    style.map(
        "TEntry",
        bordercolor=[("focus", c["accent"]), ("hover", c["text4"])],
        lightcolor=[("focus", c["background"])],
    )
    style.configure("Mono.TEntry", **field, font=fonts["mono_sm"])
    style.map("Mono.TEntry", bordercolor=[("focus", c["accent"]), ("hover", c["text4"])])
    # the arrow is a chevron inside the field, not a raised button with its own border
    style.configure("TCombobox", **field, background=c["background"])
    style.map(
        "TCombobox",
        bordercolor=[("focus", c["accent"]), ("hover", c["text4"])],
        fieldbackground=[("readonly", c["background"]), ("disabled", c["surface1"])],
        foreground=[("disabled", c["text4"])],
        lightcolor=[("focus", c["background"])],
        darkcolor=[("focus", c["background"])],
    )
    chevron = _chevron_element(root, style, name, c)
    style.layout(
        "TCombobox",
        [
            (
                "Combobox.field",
                {
                    "sticky": "nswe",
                    "children": [
                        (chevron, {"side": "right", "sticky": "ns"}),
                        (
                            "Combobox.padding",
                            {
                                "expand": "1",
                                "sticky": "nswe",
                                "children": [("Combobox.textarea", {"sticky": "nswe"})],
                            },
                        ),
                    ],
                },
            )
        ],
    )
    style.configure(
        "Vertical.TScrollbar",
        background=c["surface2"],
        troughcolor=c["background"],
        bordercolor=c["background"],
        lightcolor=c["surface2"],
        darkcolor=c["surface2"],
        arrowcolor=c["text3"],
        gripcount=0,
        arrowsize=10,
    )
    style.map("Vertical.TScrollbar", background=[("active", c["surface3"])])
    root.option_add("*TCombobox*Listbox.background", c["surface1"])
    root.option_add("*TCombobox*Listbox.foreground", c["text1"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["surface2"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["text1"])
    root.option_add("*TCombobox*Listbox.font", fonts["mono_sm"])
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    return Theme(name, c, fonts)


def _chevron_image(root: tk.Misc, color: str):
    """A 1.5 px chevron-down, drawn pixel by pixel (Tk has no vector icons)."""
    import tkinter as tk

    size, arm = px(16), max(4, px(4))
    img = tk.PhotoImage(master=root, width=size, height=size)
    cx, cy = size // 2, size // 2 - arm // 2
    thick = max(2, px(2))
    for i in range(arm):
        for d in range(thick):
            img.put(color, (cx - arm + i, cy + i + d))
            img.put(color, (cx + arm - 1 - i, cy + i + d))
    return img


def _chevron_element(root: tk.Misc, style, name: str, c: dict) -> str:
    """Register the chevron element for this palette once per Tk interpreter."""
    element = f"Chevron{name.title()}.downarrow"
    if element not in style.element_names():
        images = [_chevron_image(root, c[k]) for k in ("text3", "text1", "text4")]
        style.element_create(
            element,
            "image",
            images[0],
            ("disabled", images[2]),
            ("pressed", images[1]),
            ("hover", images[1]),
            sticky="",
            padding=(px(4), 0, px(6), 0),
        )
        setattr(root, f"_frametrace_{element}", images)  # Tk keeps only a reference
    return element


def _colorref(hex_color: str) -> int:
    """#RRGGBB as a Windows COLORREF (0x00BBGGRR)."""
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (1, 3, 5))
    return r | (g << 8) | (b << 16)


def set_title_bar(root: tk.Tk, dark: bool, c: dict | None = None) -> None:
    """Title bar in the housing's colours: dark mode, plus caption, text and border colour.

    Windows 11 takes the exact colours (DWMWA_CAPTION_COLOR and friends); Windows 10 only
    the dark mode switch. DWM keeps drawing the old frame until the window is redrawn, so
    the frame is refreshed at once instead of at the next activation.
    """
    if sys.platform != "win32":
        return
    try:
        user32, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
        hwnd = user32.GetParent(root.winfo_id())
        if not hwnd:  # not mapped yet: the <Map> binding calls again
            return
        value = ctypes.c_int(1 if dark else 0)
        if dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4) != 0:
            dwm.DwmSetWindowAttribute(hwnd, 19, ctypes.byref(value), 4)  # Windows 10 < 20H1
        if c:
            for attr, key in ((35, "background"), (36, "text1"), (34, "border")):
                ref = ctypes.c_uint(_colorref(c[key]))
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(ref), 4)
        # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0037)
    except (AttributeError, OSError, ValueError):
        pass
