# frametrace-design: Tokens

## 0. PRIMITIVES

Raw scales derived from the brand. These are the building blocks: semantic tokens reference them.

### Color Ramps

**Neutral** (warm graphite, slightly olive, like painted instrument housings)

| Step | Hex | Use |
|------|-----|-----|
| 50 | `#F7F6F2` | Light-mode housing (page background) |
| 100 | `#ECEAE4` | Light panels; dark-mode primary text |
| 200 | `#DFDDD6` | Light borders, light wells |
| 300 | `#C8C5BC` | Strong light borders, light raised controls |
| 400 | `#A8A59D` | Dark-mode secondary text; light disabled text |
| 500 | `#8C8A83` | Dark-mode tertiary text and silk-screen labels |
| 600 | `#66645E` | Light-mode tertiary text; dark disabled text |
| 700 | `#3A3A36` | Dark strong borders, dark raised controls; light secondary text |
| 800 | `#252522` | Dark controls, dark borders, graticule lines |
| 900 | `#1C1C1A` | Dark panels |
| 950 | `#141413` | Dark housing and the scope screen in both modes |

**Brand** (CH1 trace yellow, the phosphor of the scope)

| Step | Hex |
|------|-----|
| 50 | `#FEF9E7` |
| 100 | `#FDF0C2` |
| 200 | `#FBE38A` |
| 300 | `#F8D553` |
| 400 | `#F6CB33` |
| 500 | `#F5C518`: primary accent, the trace |
| 600 | `#C9A10E` |
| 700 | `#7F6100`: light-mode accent for text and borders |
| 800 | `#5E4800` |
| 900 | `#3D2F02` |
| 950 | `#2B2203` |

**Channel colors** (signals only, never decoration)

| Channel | Signal | On the screen (both modes) | As text on light surfaces |
|---------|--------|----------------------------|---------------------------|
| CH1 | Frame time | `#F5C518` (brand.500) | `#7F6100` (brand.700) |
| CH2 | GPU busy | `#35C4DC` (cyan.400) | `#0B7385` (cyan.700) |
| CH3 | CPU busy, presenting thread | `#E0559F` (magenta.400) | `#B02F74` (magenta.700) |

**Status Colors**

| Color | 50 (bg tint) | 500 (foreground) | 700 (light-mode foreground) | 900 (dark tint) |
|-------|-------------|-----------------|-----------------------------|-----------------|
| Red | `#FDECEC` | `#F2555A` | `#B42328` | `#3D1113` |
| Green | `#EAF7EC` | `#3FB950` | `#1F7A33` | `#12381A` |
| Amber (orange on purpose) | `#FDF1E8` | `#F0883E` | `#A9541A` | `#4A2410` |

Light mode uses the 700 step as the foreground because the 500 steps fall under 4.5:1 on `#F7F6F2`. Amber is pushed to orange so a warning never reads as the yellow trace.

### Spacing Primitives

`0, 2, 4, 8, 12, 16, 24, 32, 48, 64, 96`

### Radii Primitives

`0, 2, 4`

---

## 1. TYPOGRAPHY

### Font Stack

| Role | Font | Fallback | Weight | Use |
|------|------|----------|--------|-----|
| **Display** | `"IBM Plex Sans"` | `'Segoe UI', system-ui, sans-serif` | 600 | Verdicts, screen titles, landing headlines |
| **Body / UI** | `"IBM Plex Sans"` | `'Segoe UI', system-ui, sans-serif` | 400 (500 for labels, 600 for buttons) | Body text, descriptions, UI labels |
| **Mono / Code** | `"IBM Plex Mono"` | `Consolas, 'Cascadia Mono', ui-monospace, monospace` | 400 (500 for readouts) | Every number, unit, hotkey, path, process name, the report text |

### Mono Font Rules

**`mono_for_code`: true** · **`mono_for_metrics`: true**

Frametrace is an instrument: the numbers are the product. FPS, frame times, latencies, percentages, MT/s, timestamps, durations, hotkeys (`F10`), process names (`cs2.exe`) and file paths are all Plex Mono. The copyable report itself renders in Plex Mono because it is the artifact users paste into an AI.

- **`mono_for_code: true`:** Use the mono font for code blocks, file paths, shell commands, and inline technical tokens.
- **`mono_for_metrics: true`:** Use the mono font for every measured or counted value, including table cells and axis ticks.

IBM Plex was designed for IBM's technical documentation: a grotesque with engineered, slightly mechanical terminals and a mono that shares its skeleton. That shared skeleton is the point: labels in Sans and values in Mono sit on one rhythm, like silk-screen and LCD on the same faceplate. Plex is OFL-licensed, so the desktop app can bundle it.

### Type Scale

| Token | Size | Line Height | Letter Spacing | Weight | Use |
|-------|------|-------------|----------------|--------|-----|
| `--display` | 48px | 1.05 | -0.02em | 600 | Hero numbers, screen titles |
| `--heading` | 28px | 1.2 | -0.01em | 600 | Section headings, the verdict line |
| `--subheading` | 18px | 1.35 | 0em | 600 | Panel titles, card titles |
| `--body` | 15px | 1.55 | 0em | 400 | Body text, descriptions |
| `--body-sm` | 13px | 1.5 | 0em | 400 | Secondary text, table cells, check text |
| `--caption` | 12px | 1.4 | 0.01em | 400 | Units, timestamps, footnotes |
| `--label` | 11px | 1.2 | 0.08em | 500 | Silk-screen labels, uppercase |
| `--readout` | 32px | 1.0 | -0.01em | 500 | Instrument readouts, Plex Mono |

### Typographic Rules

- Labels are uppercase at `--label` in `--text3`. Nothing else is uppercase except channel names (`CH1`) and tags.
- Readout values use `--readout` in Plex Mono with `font-variant-numeric: tabular-nums`; the unit follows at `--caption` in `--text3`.
- Verdicts are sentence case at `--heading`, ending with a period. The first clause names the limit, the second gives the number.
- Body copy never exceeds 68 characters per line.
- No italics. Emphasis comes from weight 600 or from a lamp.

---

## 2. COLOR SYSTEM (Semantic Tokens)

Semantic tokens reference the primitives above. Components use semantic tokens, never primitives directly.

### Primary Mode (Dark, "bench at night")

| Token | Primitive | Hex | Role |
|-------|-----------|-----|------|
| `--background` | `{neutral.950}` | `#141413` | Page background, window housing |
| `--bg` | alias | `var(--background)` | Shorthand alias for `--background` |
| `--surface1` | `{neutral.900}` | `#1C1C1A` | Panels, readout tiles |
| `--surface2` | `{neutral.800}` | `#252522` | Controls, selected rows, segmented tracks |
| `--surface3` | `{neutral.700}` | `#3A3A36` | Raised controls, hover on controls |
| `--border` | `{neutral.800}` | `#252522` | Panel edges, row dividers |
| `--border-visible` | `{neutral.700}` | `#3A3A36` | Input and control borders |
| `--text1` | `{neutral.100}` | `#ECEAE4` | Primary text, readout values |
| `--text2` | `{neutral.400}` | `#A8A59D` | Secondary text, descriptions |
| `--text3` | `{neutral.500}` | `#8C8A83` | Labels, units, timestamps |
| `--text4` | `{neutral.600}` | `#66645E` | Disabled text, idle lamps |
| `--accent` | `{brand.500}` | `#F5C518` | The trace, the primary action, focus rings |
| `--accent-hover` | `{brand.400}` | `#F6CB33` | Primary button hover |
| `--accent-subtle` | `{brand.950}` | `#2B2203` | Tinted background behind accent tags |
| `--on-accent` | `{neutral.950}` | `#141413` | Text on a yellow fill |
| `--trace` | `{brand.500}` | `#F5C518` | Primary button fill, CH1 trace |
| `--ch1` | `{brand.500}` | `#F5C518` | Frame-time channel |
| `--ch2` | `{cyan.400}` | `#35C4DC` | GPU channel |
| `--ch3` | `{magenta.400}` | `#E0559F` | CPU channel |
| `--screen` | `{neutral.950}` | `#141413` | Scope screen |
| `--graticule` | `{neutral.800}` | `#252522` | Scope grid lines |
| `--success` | `{green.500}` | `#3FB950` | OK lamps, passing checks |
| `--warning` | `{amber.500}` | `#F0883E` | Warn lamps, checks worth fixing |
| `--error` | `{red.500}` | `#F2555A` | Failed capture, missing PresentMon |

### Secondary Mode (Light, "bench daylight")

| Token | Primitive | Hex | Role |
|-------|-----------|-----|------|
| `--background` | `{neutral.50}` | `#F7F6F2` | Page background |
| `--bg` | alias | `var(--background)` | Shorthand alias for `--background` |
| `--surface1` | `{neutral.100}` | `#ECEAE4` | Panels, readout tiles |
| `--surface2` | `{neutral.200}` | `#DFDDD6` | Controls, selected rows |
| `--surface3` | `{neutral.300}` | `#C8C5BC` | Raised controls, hover on controls |
| `--border` | `{neutral.200}` | `#DFDDD6` | Panel edges, row dividers |
| `--border-visible` | `{neutral.300}` | `#C8C5BC` | Input and control borders |
| `--text1` | `{neutral.950}` | `#141413` | Primary text |
| `--text2` | `{neutral.700}` | `#3A3A36` | Secondary text |
| `--text3` | `{neutral.600}` | `#66645E` | Labels, units |
| `--text4` | `{neutral.400}` | `#A8A59D` | Disabled text |
| `--accent` | `{brand.700}` | `#7F6100` | Accent text, focus ring, selected edge |
| `--accent-hover` | `{brand.800}` | `#5E4800` | Accent text hover |
| `--accent-subtle` | `{brand.50}` | `#FEF9E7` | Tinted background for accent tags |
| `--on-accent` | `{neutral.950}` | `#141413` | Text on a yellow fill |
| `--trace` | `{brand.500}` | `#F5C518` | Primary button fill stays yellow |
| `--ch1` / `--ch2` / `--ch3` | unchanged | `#F5C518` / `#35C4DC` / `#E0559F` | On the scope screen, which stays dark |
| `--screen` | `{neutral.950}` | `#141413` | The scope screen never turns light |
| `--graticule` | `{neutral.800}` | `#252522` | Scope grid lines |
| `--success` | `{green.700}` | `#1F7A33` | OK lamps |
| `--warning` | `{amber.700}` | `#A9541A` | Warn lamps |
| `--error` | `{red.700}` | `#B42328` | Errors |

The primary button keeps its `#F5C518` fill (`--trace`, brand.500) in light mode; only accent *text* switches to brass.

### Accent & Status Tints

| Token | Primary (dark) | Secondary (light) | Usage |
|-------|---------|-----------|-------|
| `--accent-subtle` | `#2B2203` | `#FEF9E7` | Tinted backgrounds for accent tags |
| `--success-bg` | `#12381A` | `#EAF7EC` | Success alerts and tags |
| `--warning-bg` | `#4A2410` | `#FDF1E8` | Warning alerts and tags |
| `--error-bg` | `#3D1113` | `#FDECEC` | Error alerts and tags |

### Color Usage Rules

- Yellow budget: the trace, one primary button, the focus ring, the selected-row edge. Count them; more than that is a violation.
- Channel colors appear only inside the scope, beside a channel label as an 8 px swatch, and in the bottleneck split bar (GPU cyan, CPU magenta, waiting `--text4`).
- Status colors appear only in lamps, alerts and tag tints. Never color a paragraph of text.
- Measured contrast: dark text1 on background 15.3:1, text2 7.5:1, text3 5.3:1, CH2 8.9:1, CH3 5.2:1; light text1 17.0:1, text2 10.6:1, text3 4.9:1, accent 5.4:1, success 5.0:1, warning 4.9:1, error 6.1:1.

---

## 3. SPACING

### Scale (8px base)

| Token | Value | Use |
|-------|-------|-----|
| `--space-2xs` | 2px | Optical adjustments, lamp-to-edge insets |
| `--space-xs` | 4px | Icon-to-label gaps, unit-to-value gap |
| `--space-sm` | 8px | Label-to-value, gaps between readout tiles |
| `--space-md` | 16px | Panel padding, gaps between panels |
| `--space-lg` | 24px | Rail-to-main gutter, card padding on marketing pages |
| `--space-xl` | 32px | Section spacing inside a page |
| `--space-2xl` | 48px | Major section breaks |
| `--space-3xl` | 64px | Landing feature padding |
| `--space-4xl` | 96px | Hero breathing room |

---

## 4. BORDERS & RADII

### Radii Scale (Semantic to Primitive)

| Token | Value | Primitive | Use |
|-------|-------|-----------|-----|
| `--radius-element` | 2px | `{radii[1]}` | Lamps, checkboxes, tags |
| `--radius-control` | 2px | `{radii[1]}` | Buttons, inputs, segmented controls, toggles |
| `--radius-component` | 4px | `{radii[2]}` | Panels, readout tiles, cards, the scope |
| `--radius-container` | 4px | `{radii[2]}` | Modals, popovers, the window frame |
| `--radius-pill` | not used | none | Frametrace has no pills; tags use `--radius-element` |

### Border Treatment

| Element | Border |
|---------|--------|
| Cards / Surfaces | 1px solid `--border` |
| Buttons | Primary none; secondary 1px solid `--border-visible`; ghost none |
| Inputs | 1px solid `--border-visible`, 1px solid `--accent` on focus |
| Tags / Chips | none, tinted fill only |
| Modals / Sheets | 1px solid `--border-visible` ring plus the level 3 drop |

Corners are machined, not molded: 2 px on anything you press, 4 px on anything that holds things. A radius above 4 px reads as consumer software and is never used.

---

## 5. ELEVATION & SHADOWS

| Level | Light Mode | Dark Mode | Use |
|-------|-----------|----------|-----|
| **0** | None | None | Flat, inline elements |
| **1** | `none` | `none` | Panels and readout tiles (border only) |
| **2** | `0 0 0 1px #C8C5BC` | `0 0 0 1px #3A3A36` | Menus, popovers |
| **3** | `0 0 0 1px #C8C5BC, 0 12px 32px rgba(20,20,19,0.14)` | `0 0 0 1px #3A3A36, 0 12px 32px rgba(0,0,0,0.45)` | Modals, dialogs |

Strategy: flat. Depth comes from surface steps and 1 px borders. Only overlays get a hard ring, and only modals add a soft drop to separate from the backdrop.

### Strokes

Traces are 1.5 px, rules are 1 px, and every bar, gauge and trace ends with a butt cap. This is a deliberate exception to round-cap defaults: printed scale marks end square.

---

## 6. MOTION & INTERACTION

### Personality

Mechanical. Click, not swoosh. No overshoot, no spring, no stagger. The only continuous motion in the product is the trace sweep while recording, which is linear.

### Timing

| Type | Duration | Easing | Use |
|------|----------|--------|-----|
| **Micro** | 100ms | `ease-out` | Button press, toggle, lamp change, color change |
| **Standard** | 160ms | `ease-out` | Tab switch, panel content swap, popover in |
| **Emphasis** | 220ms | `cubic-bezier(0.2, 0, 0, 1)` | Modal present, report appearing after a capture |

### Interaction States

| State | Treatment |
|-------|-----------|
| Hover | One surface step up (`--surface2` to `--surface3`), or text `--text2` to `--text1` |
| Pressed | One surface step down; primary darkens to brand.600 |
| Focus | 1 px `--accent` outline at 2 px offset; never a glow |
| Selected | `--surface2` fill plus 2 px `--accent` left edge |
| Disabled | `--text4` text, `--border` borders, no fill change |
| Recording | Status lamp `--error`, label `REC`, elapsed timer in mono |

---

## 7. ICONOGRAPHY

> **Fallback disclosure.** The icons rendered in the generated preview come from a freely-licensed kit selected as the closest match to the brand's intended icons. Frametrace has no proprietary icon set. Tabler Icons are MIT licensed.

### Observed style (the brand's intended icons)

| Attribute | Value |
|-----------|-------|
| Description | Thin geometric outline icons like panel engravings, used sparingly next to labels. Labels and numbers do the work. |
| Stroke weight | regular (1.5 px) |
| Corner treatment | soft |
| Fill style | outline |
| Form language | geometric |
| Visual density | balanced |

### Fallback kit (what the preview actually renders)

- **Kit:** Tabler Icons
- **Weight / variant:** outline, the 300 webfont build (1.5px stroke; the default build is 2px)
- **Match score:** high
- **Why this kit:** Tabler's 1.5 px outline matches the thin, technical engraving feel and it has the hardware glyphs this domain needs (cpu, device-desktop, activity, wave-square, keyboard, clock). Lucide would be second choice, but its 2 px stroke reads heavier than panel legends and it lacks several hardware glyphs.
- **CDN:** `https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.41.1/dist/tabler-icons-300.min.css`
- **Usage:** `<i class="ti ti-activity"></i>`

### Sizes

| Context | Size |
|---------|------|
| Inline with body text | 16px |
| Buttons | 16px |
| Navigation | 18px |

### Color rule

Icons inherit `--text2`, or `--text1` when their control is active. An icon never takes a channel or status color; the lamp beside it carries status.

### Don't

- Never use an icon without a text label in the desktop app, except the caption buttons and the copy button in the report header (which has a tooltip).
- Never claim these are the brand's real icons: they are a best-match fallback.
