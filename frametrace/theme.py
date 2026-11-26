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
    "button": ("sans_semibold", 10),
    "mono": ("mono", 10),
    "mono_sm": ("mono", 9),
    "mono_xs": ("mono", 8),
    "readout": ("mono_medium", 22),
    "wordmark": ("sans_semibold", 12),
}
SPACE = {"2xs": 2, "xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32, "2xl": 48}


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
    style.configure("TCombobox", **field, arrowsize=13, background=c["surface2"])
    style.map(
        "TCombobox",
        bordercolor=[("focus", c["accent"]), ("hover", c["text4"])],
        fieldbackground=[("readonly", c["background"]), ("disabled", c["surface1"])],
        foreground=[("disabled", c["text4"])],
        background=[("active", c["surface3"]), ("pressed", c["surface3"])],
        arrowcolor=[("disabled", c["text4"])],
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


def set_title_bar(root: tk.Tk, dark: bool) -> None:
    """Dark or light Windows title bar (DWMWA_USE_IMMERSIVE_DARK_MODE)."""
    if sys.platform != "win32":
        return
    try:
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
    except (AttributeError, OSError):
        pass
