# frametrace-design: Platform Mapping

Frametrace ships as a Windows desktop app built with Python and Tkinter, plus a website and README. Section 1 covers the web, section 2 the desktop app (the primary platform), section 3 Tailwind for any React surface.

## 1. HTML / CSS / WEB

### Font Loading

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.41.1/dist/tabler-icons-300.min.css">
```

### CSS Custom Properties: Primary Mode (dark)

```css
:root {
  /* Colors */
  --background: #141413;
  --bg: var(--background);
  --surface1: #1C1C1A;
  --surface2: #252522;
  --surface3: #3A3A36;
  --border: #252522;
  --border-visible: #3A3A36;
  --text1: #ECEAE4;
  --text2: #A8A59D;
  --text3: #8C8A83;
  --text4: #66645E;
  --accent: #F5C518;
  --accent-hover: #F6CB33;
  --accent-subtle: #2B2203;
  --on-accent: #141413;
  --trace: #F5C518;
  --success: #3FB950;
  --success-bg: #12381A;
  --warning: #F0883E;
  --warning-bg: #4A2410;
  --error: #F2555A;
  --error-bg: #3D1113;

  /* Instrument */
  --ch1: #F5C518;
  --ch2: #35C4DC;
  --ch3: #E0559F;
  --screen: #141413;
  --graticule: #252522;
  --ref: #A8A59D;

  /* Fonts */
  --font-display: "IBM Plex Sans", 'Segoe UI', system-ui, sans-serif;
  --font-body: "IBM Plex Sans", 'Segoe UI', system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", Consolas, 'Cascadia Mono', ui-monospace, monospace;

  /* Type Scale */
  --text-display: 48px;
  --text-heading: 28px;
  --text-subheading: 18px;
  --text-body: 15px;
  --text-body-sm: 13px;
  --text-caption: 12px;
  --text-label: 11px;
  --text-readout: 32px;

  /* Spacing */
  --space-2xs: 2px;
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 32px;
  --space-2xl: 48px;
  --space-3xl: 64px;
  --space-4xl: 96px;

  /* Radii */
  --radius-cards: 4px;
  --radius-buttons: 2px;
  --radius-buttons-sm: 2px;
  --radius-inputs: 2px;
  --radius-tags: 2px;
  --radius-modals: 4px;

  /* Motion */
  --ease-fast: ease-out;
  --ease-medium: ease-out;
  --ease-slow: cubic-bezier(0.2, 0, 0, 1);
  --duration-fast: 100ms;
  --duration-medium: 160ms;
  --duration-slow: 220ms;

  /* Shadows */
  --shadow-1: none;
  --shadow-2: 0 0 0 1px #3A3A36;
  --shadow-3: 0 0 0 1px #3A3A36, 0 12px 32px rgba(0,0,0,0.45);
}
```

### Secondary Mode (light, "bench daylight")

```css
@media (prefers-color-scheme: light) {
  :root {
    --background: #F7F6F2;
    --bg: var(--background);
    --surface1: #ECEAE4;
    --surface2: #DFDDD6;
    --surface3: #C8C5BC;
    --border: #DFDDD6;
    --border-visible: #C8C5BC;
    --text1: #141413;
    --text2: #3A3A36;
    --text3: #66645E;
    --text4: #A8A59D;
    --accent: #7F6100;
    --accent-hover: #5E4800;
    --accent-subtle: #FEF9E7;
    --success: #1F7A33;
    --success-bg: #EAF7EC;
    --warning: #A9541A;
    --warning-bg: #FDF1E8;
    --error: #B42328;
    --error-bg: #FDECEC;
    --shadow-1: none;
    --shadow-2: 0 0 0 1px #C8C5BC;
    --shadow-3: 0 0 0 1px #C8C5BC, 0 12px 32px rgba(20,20,19,0.14);
    /* --trace, --ch1..3, --screen and --graticule do not change: the scope stays dark */
  }
}

/* Class-based toggle alternative */
[data-theme="light"] {
  --background: #F7F6F2;
  --bg: var(--background);
  --surface1: #ECEAE4;
  --surface2: #DFDDD6;
  --surface3: #C8C5BC;
  --border: #DFDDD6;
  --border-visible: #C8C5BC;
  --text1: #141413;
  --text2: #3A3A36;
  --text3: #66645E;
  --text4: #A8A59D;
  --accent: #7F6100;
  --accent-hover: #5E4800;
  --accent-subtle: #FEF9E7;
  --success: #1F7A33;
  --success-bg: #EAF7EC;
  --warning: #A9541A;
  --warning-bg: #FDF1E8;
  --error: #B42328;
  --error-bg: #FDECEC;
}
```

### Readout and lamp utilities

```css
.readout-value { font: 500 var(--text-readout)/1 var(--font-mono); letter-spacing: -0.01em; font-variant-numeric: tabular-nums; color: var(--text1); }
.readout-unit  { font: 400 var(--text-caption)/1.4 var(--font-mono); color: var(--text3); margin-left: var(--space-xs); }
.label         { font: 500 var(--text-label)/1.2 var(--font-body); letter-spacing: 0.08em; text-transform: uppercase; color: var(--text3); }
.lamp          { width: 8px; height: 8px; border-radius: 1px; display: inline-block; }
```

---

## 2. TKINTER / TTK (Windows desktop app)

The desktop app is the shipping product. It lives in `frametrace/theme.py` (tokens, fonts, ttk styles) and `frametrace/instruments.py` (scope, readout, lamp, split bar on `tk.Canvas`).

### Font Registration

Bundle the OFL-licensed TTFs in `frametrace/assets/fonts/` and load them privately before creating the `Tk` root. `FR_PRIVATE` keeps them out of the user's font list and frees them when the process exits.

```python
import ctypes
from pathlib import Path

FONT_DIR = Path(__file__).parent / "assets" / "fonts"
FR_PRIVATE = 0x10


def load_fonts() -> bool:
    """Register IBM Plex for this process only. Returns False when not on Windows."""
    try:
        gdi32 = ctypes.windll.gdi32
    except AttributeError:
        return False
    ok = True
    for ttf in sorted(FONT_DIR.glob("*.ttf")):
        ok &= gdi32.AddFontResourceExW(str(ttf), FR_PRIVATE, 0) > 0
    return ok
```

GDI exposes each static weight as its own family name. Tk only knows `normal` and `bold`, so pick weights by family:

| Role | Tk family | Weight |
|------|-----------|--------|
| Body 400 | `IBM Plex Sans` | normal |
| Label 500 | `IBM Plex Sans Medm` | normal |
| Display / button 600 | `IBM Plex Sans SmBld` | normal |
| Mono 400 | `IBM Plex Mono` | normal |
| Readout 500 | `IBM Plex Mono Medm` | normal |

Fallbacks when the TTFs are missing: `Segoe UI` / `Segoe UI Semibold` and `Consolas`.

### Color Tokens

```python
DARK = {
    "background": "#141413",
    "surface1": "#1C1C1A",
    "surface2": "#252522",
    "surface3": "#3A3A36",
    "border": "#252522",
    "border_visible": "#3A3A36",
    "text1": "#ECEAE4",
    "text2": "#A8A59D",
    "text3": "#8C8A83",
    "text4": "#66645E",
    "accent": "#F5C518",
    "accent_hover": "#F6CB33",
    "accent_pressed": "#C9A10E",
    "accent_subtle": "#2B2203",
    "on_accent": "#141413",
    "trace": "#F5C518",
    "ch1": "#F5C518",
    "ch2": "#35C4DC",
    "ch3": "#E0559F",
    "screen": "#141413",
    "graticule": "#252522",
    "success": "#3FB950",
    "warning": "#F0883E",
    "error": "#F2555A",
    "success_bg": "#12381A",
    "warning_bg": "#4A2410",
    "error_bg": "#3D1113",
}
LIGHT = {
    **DARK,
    "background": "#F7F6F2",
    "surface1": "#ECEAE4",
    "surface2": "#DFDDD6",
    "surface3": "#C8C5BC",
    "border": "#DFDDD6",
    "border_visible": "#C8C5BC",
    "text1": "#141413",
    "text2": "#3A3A36",
    "text3": "#66645E",
    "text4": "#A8A59D",
    "accent": "#7F6100",
    "accent_hover": "#5E4800",
    "accent_subtle": "#FEF9E7",
    "success": "#1F7A33",
    "warning": "#A9541A",
    "error": "#B42328",
    "success_bg": "#EAF7EC",
    "warning_bg": "#FDF1E8",
    "error_bg": "#FDECEC",
}
```

### ttk Styles

Build on the `clam` theme: it is the only built-in theme whose every element color can be set. Flatten bevels by setting `lightcolor` and `darkcolor` to the fill. The excerpt below shows the pattern; `frametrace/theme.py` has the full version (entries, comboboxes, scrollbars, the combobox dropdown).

```python
def apply(root, c=DARK):
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
        troughcolor=c["surface2"],
        focuscolor=c["accent"],
        selectbackground=c["surface2"],
        selectforeground=c["text1"],
        font=("IBM Plex Sans", 10),
    )
    style.configure("Panel.TFrame", background=c["surface1"])
    style.configure(
        "Primary.TButton",
        background=c["trace"],
        foreground=c["on_accent"],
        bordercolor=c["trace"],
        lightcolor=c["trace"],
        darkcolor=c["trace"],
        font=("IBM Plex Sans SmBld", 10),
        padding=(16, 7),
    )
    style.map(
        "Primary.TButton",
        background=[
            ("disabled", c["surface1"]),
            ("pressed", c["accent_pressed"]),
            ("active", c["accent_hover"]),
        ],
        foreground=[("disabled", c["text4"])],
    )
    style.configure("Label.TLabel", font=("IBM Plex Sans Medm", 8), foreground=c["text3"])
    root.option_add("*TCombobox*Listbox.background", c["surface1"])
    root.option_add("*TCombobox*Listbox.foreground", c["text1"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["surface2"])
```

Tk point sizes (`TYPE` in `frametrace/theme.py`): label 8 pt, caption 9, body-sm 10 (and `group`, body-sm at Plex Sans Medium for the captures list's headings), body 11, subheading 13, heading 20, readout 22, display 30. At 96 DPI a point is 1.33 px, and Tk scales points with the monitor's DPI; heading and readout sit a step below the web sizes because a desktop window is read closer than a web page.

### Spacing & Radius Constants

```python
SPACE = {"2xs": 2, "xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32, "2xl": 48, "3xl": 64, "4xl": 96}
RADIUS = {"element": 2, "control": 2, "component": 4, "container": 4}
```

ttk draws square corners. That is inside the machined spec (0 to 4 px); do not fake rounded corners with images.

### Instruments on Canvas

- **Scope:** `tk.Canvas(bg=c["screen"], highlightthickness=0)`. Draw the graticule with `create_line(..., fill=c["graticule"])`, each channel with one `create_line(*points, fill=c["ch1"], width=1.5, capstyle="butt")`. Downsample frames to two points per pixel column (min and max) so a 40,000-frame capture draws instantly and hitches survive.
- **Lamp:** a `tk.Frame(width=8, height=8, bg=color)` with `pack_propagate(False)`.
- **Split bar:** a Canvas 8 px tall with three rectangles (`ch2`, `ch3`, `text4`), 1 px gaps.
- **Readout:** a `Panel.TFrame` with a label (`Label.TLabel`), a value label in `IBM Plex Mono Medm` 24 pt and a unit label in `IBM Plex Mono` 9 pt.

### Display Scaling

Tk scales point sizes with the monitor's DPI but not pixel sizes. `theme.set_scale(root)` reads the DPI once (1.0 at 96 DPI, then 1.25, 1.5 ...) and `theme.px(n)` scales every structural size: window, rail, scope height and margins, bars, lamps, paddings. A 150% display gets the same layout, only larger.

### Silk-screen Tracking

Tk has no letter-spacing. `theme.track(text)` puts a hair space (U+200A, about 0.08em in Plex) between letters of uppercase labels; `theme.untrack()` removes it again for tests and comparisons.

### Numbers in Prose, Scrollbars, Select

- `RichText` (a read-only `tk.Text`) sets prose in Plex Sans and every number with its unit in Plex Mono (`summary.number_runs`), and grows to the lines it needs.
- `ThinScrollbar` (a Canvas) replaces `ttk.Scrollbar` in pages and the report: 6px thumb, no arrows, gutter always reserved.
- The combobox arrow is an image element (`ChevronDark.downarrow`) inside `Combobox.field`, so the field has one border and no divider.

### Window Icon

`frametrace/assets/icon-*.png` (generated by `tools/make_icon.py`) are set with `iconphoto`, and `SetCurrentProcessExplicitAppUserModelID` groups the window under that icon in the taskbar instead of Python's. `frametrace.ico` is for the packaged .exe.

### Dark/Light Mode

Dark is the default. The top bar's Dark / Light segmented switch re-runs `apply(root, LIGHT)` and redraws the canvases; the scope keeps `screen`, `graticule` and the channel colors. Set the Windows title bar to dark with `DwmSetWindowAttribute(hwnd, 20, 1)` only in dark mode.

---

## 3. REACT / TAILWIND

### tailwind.config.js

```js
module.exports = {
  darkMode: ['class', '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        background: 'var(--background)',
        surface1: 'var(--surface1)',
        surface2: 'var(--surface2)',
        surface3: 'var(--surface3)',
        border: 'var(--border)',
        'border-visible': 'var(--border-visible)',
        text1: 'var(--text1)',
        text2: 'var(--text2)',
        text3: 'var(--text3)',
        text4: 'var(--text4)',
        accent: 'var(--accent)',
        'accent-subtle': 'var(--accent-subtle)',
        'on-accent': 'var(--on-accent)',
        trace: 'var(--trace)',
        ch1: 'var(--ch1)',
        ch2: 'var(--ch2)',
        ch3: 'var(--ch3)',
        screen: 'var(--screen)',
        graticule: 'var(--graticule)',
        ref: 'var(--ref)',
        success: 'var(--success)',
        'success-bg': 'var(--success-bg)',
        warning: 'var(--warning)',
        'warning-bg': 'var(--warning-bg)',
        error: 'var(--error)',
        'error-bg': 'var(--error-bg)',
      },
      fontFamily: {
        display: ['"IBM Plex Sans"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        body: ['"IBM Plex Sans"', '"Segoe UI"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'Consolas', '"Cascadia Mono"', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        display: ['48px', { lineHeight: '1.05', letterSpacing: '-0.02em', fontWeight: '600' }],
        heading: ['28px', { lineHeight: '1.2', letterSpacing: '-0.01em', fontWeight: '600' }],
        subheading: ['18px', { lineHeight: '1.35', fontWeight: '600' }],
        body: ['15px', { lineHeight: '1.55' }],
        'body-sm': ['13px', { lineHeight: '1.5' }],
        caption: ['12px', { lineHeight: '1.4', letterSpacing: '0.01em' }],
        label: ['11px', { lineHeight: '1.2', letterSpacing: '0.08em', fontWeight: '500' }],
        readout: ['32px', { lineHeight: '1', letterSpacing: '-0.01em', fontWeight: '500' }],
      },
      spacing: {
        '2xs': '2px', xs: '4px', sm: '8px', md: '16px', lg: '24px',
        xl: '32px', '2xl': '48px', '3xl': '64px', '4xl': '96px',
      },
      borderRadius: {
        element: '2px',
        control: '2px',
        component: '4px',
        container: '4px',
      },
      boxShadow: {
        1: 'var(--shadow-1)',
        2: 'var(--shadow-2)',
        3: 'var(--shadow-3)',
      },
      transitionTimingFunction: {
        fast: 'ease-out',
        medium: 'ease-out',
        slow: 'cubic-bezier(0.2, 0, 0, 1)',
      },
      transitionDuration: {
        fast: '100ms',
        medium: '160ms',
        slow: '220ms',
      },
    },
  },
};
```

### Font Loading

```tsx
// app/layout.tsx (Next.js)
import { IBM_Plex_Sans, IBM_Plex_Mono } from 'next/font/google';

const sans = IBM_Plex_Sans({ subsets: ['latin'], weight: ['400', '500', '600'], variable: '--font-body' });
const mono = IBM_Plex_Mono({ subsets: ['latin'], weight: ['400', '500'], variable: '--font-mono' });

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="dark" className={`${sans.variable} ${mono.variable}`}>
      <body className="bg-background text-text1 font-body">{children}</body>
    </html>
  );
}
```

### CSS Variables

Use the `:root` and `[data-theme="light"]` blocks from section 1 verbatim in `globals.css`. Tailwind classes resolve through those variables, so a theme switch is one attribute change on `<html>`.
