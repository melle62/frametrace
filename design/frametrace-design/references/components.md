# frametrace-design: Components

All components are `source: derived`: Frametrace is a new brand with no prior UI to observe. Every value below comes from `design-model.yaml`.

## 1. BUTTONS

### Variants

| Variant | Background | Text | Border | Radius | Height |
|---------|-----------|------|--------|--------|--------|
| Primary | `--trace` (#F5C518) | `--on-accent` | none | 2px | 36px |
| Secondary | `--surface2` | `--text1` | 1px solid `--border-visible` | 2px | 36px |
| Ghost | transparent | `--text2` | none | 2px | 32px |
| Destructive | transparent | `--error` | 1px solid `--error` | 2px | 36px |

One primary button per screen. In the desktop app it is **Start capture** (it becomes **Stop** while recording); in the report view it is **Copy report**.

### Specs

| Property | Value |
|----------|-------|
| Height (large) | 36px |
| Height (small) | 28px |
| Padding (large) | 0px 16px |
| Padding (small) | 0px 12px |
| Font | `IBM Plex Sans` 600, 13px |
| Min touch target | 36px (desktop pointer app; 44px on touch) |
| Icon gap | 8px, icon 16px |
| Hotkey hint | Optional trailing mono key cap, e.g. `F10`, in `--on-accent` at 60% opacity |

### States

| State | Change |
|-------|--------|
| **Hover** | Primary: brand.400 fill. Secondary: `--surface3`. Ghost: `--text1` on `--surface2` |
| **Active / Pressed** | Primary: brand.600 fill. Secondary: `--surface1`. 100ms ease-out |
| **Disabled** | `--text4` text, `--surface1` fill, `--border` border; primary loses its yellow |
| **Focus** | 1px `--accent` outline, 2px offset |

---

## 2. CARDS / SURFACES

### Standard Card
- Background: `--surface1`
- Border: 1px solid `--border`
- Radius: 4px (machined corner, never more)
- Padding: 16px
- Shadow: none (light) / none (dark)

### Featured Card
- Background: `--surface1` + a 2px `--accent` top edge (used once per screen at most, for the selected capture summary)
- Radius: 4px
- Shadow: `0 0 0 1px #C8C5BC` (light) / `0 0 0 1px #3A3A36` (dark)

### Compact Card
- Radius: 4px
- Padding: 8px 12px
- Same background and border as standard

### Content Layout
- Title: `--subheading`, `--text1`; or a `--label` silk-screen legend for instrument panels
- Description: `--body-sm`, `--text2`
- Metadata: `--caption`, `--text3`, Plex Mono for any value
- Internal spacing between elements: `--space-sm`
- Press state: interactive cards go one surface step up on hover and show the 2px accent edge when selected

---

## 3. INPUTS

### Text Field

| Property | Value |
|----------|-------|
| Height | 36px |
| Background | `--background` (a well, one step below the panel) |
| Border | 1px solid `--border-visible` |
| Radius | 2px |
| Padding | 0 12px |
| Font | Plex Sans 400, 13px; Plex Mono when the value is technical (process names, hotkeys, seconds) |
| Placeholder | `--text4` |
| Text | `--text1` |

### Label
- `--label` style, 11px uppercase, 0.08em, `--text3`, 8px above the field
- Helper text below: `--caption`, `--text3`

### States

| State | Treatment |
|-------|-----------|
| Hover | Border `--text4` |
| Focus | Border `--accent`, no glow |
| Error | Border `--error`, helper text in `--error` with a warn lamp |
| Disabled | `--surface1` fill, `--text4` text |

### Multiline
- The report viewer is a read-only multiline field: `--background` well, Plex Mono 12px, line-height 1.5, 16px padding, 1px `--border`
- Editable textareas share the text field border and focus rules, min-height 96px

---

## 4. LISTS / DATA ROWS

### Standard Row

| Property | Value |
|----------|-------|
| Height | 40px (two-line capture rows: 52px) |
| Padding | 0 12px |
| Divider | 1px `--border` |
| Primary text | `--body-sm`, `--text1` |
| Secondary text | `--caption`, `--text3`, mono for times and durations |
| Trailing value | Plex Mono, right-aligned, `--text1` |
| Leading | 8px status lamp |

### Interaction States

| State | Treatment |
|-------|-----------|
| Hover | `--surface2` |
| Selected | `--surface2` + 2px `--accent` left edge |
| Multi-selected (compare) | Same as selected; a mono `A` / `B` marker replaces the lamp |

### Data Row (Label + Value)
- Label left in `--label` uppercase `--text3`, value right in Plex Mono `--text1`, unit in `--caption` `--text3`
- Used for the system block: `CPU  7800X3D 8C/16T`, `RAM  6000 MT/s`

---

## 5. NAVIGATION / TAB BAR

### Tab Bar
- Desktop app uses underline tabs at the top of the main column: `SUMMARY`, `REPORT`, `COMPARE`
- Height 36px, labels in `--label` style, gap 24px, bottom rule 1px `--border`

### Tab States

| State | Treatment |
|-------|-----------|
| Active | `--text1` + 2px `--accent` underline |
| Inactive | `--text3` |
| Hover | `--text2` |
| Disabled | `--text4` (COMPARE until two captures are selected) |

### Navigation Bar
- Window top bar: 48px, `--background`, wordmark left, status lamp and state text center-left, primary action right
- Marketing header: 64px, wordmark, four mono links, primary button

---

## 6. TAGS / CHIPS

| Property | Value |
|----------|-------|
| Height | 20px |
| Padding | 0 6px |
| Font | Plex Mono 500, 11px, uppercase, 0.04em |
| Background | `--surface2` |
| Text | `--text2` |
| Radius | 2px |
| Line height | 1 |

### Selected State
- `--accent-subtle` fill, `--accent` text (dark: yellow on deep brass; light: brass on cream)

### Status Variants
- `--success-bg` / `--success`, `--warning-bg` / `--warning`, `--error-bg` / `--error`
- Display-path tags (`DXGI`, `INDEPENDENT FLIP`, `VSYNC OFF`) are always neutral

---

## 7. OVERLAYS

### Modal / Dialog

| Property | Value |
|----------|-------|
| Width | 440px |
| Background | `--surface1` |
| Border / shadow | Level 3 |
| Radius | 4px |
| Padding | 24px |
| Title | `--subheading` |
| Backdrop | rgba(20,20,19,0.6) |
| Actions | Right-aligned, primary last |

### Bottom Sheet
- Not used in the desktop app. On narrow web layouts: full-width, top radius 4px, `--surface1`, level 3, 16px padding, a 32x2px `--border-visible` grabber

### Dropdown / Popover

| Property | Value |
|----------|-------|
| Background | `--surface1` |
| Border | Level 2 ring |
| Radius | 4px |
| Item height | 32px |
| Item padding | 0 12px |
| Item hover | `--surface2` |
| Checked item | Leading 8px square in `--accent` |
| Divider | 1px `--border`, 4px vertical margin |

---

## 8. STATE PATTERNS

### Empty State
- A flat scope screen with only the graticule and a centered mono line: `NO CAPTURES YET`
- Below: one sentence in `--text2` ("Start a game, press F10, play for 30 seconds.") and the primary button

### Loading
- Recording: the scope sweeps left to right (linear), the status lamp is `--error` with `REC`, and a determinate bar shows elapsed / length in mono
- Analysis: a determinate bar labelled `ANALYZING 312,400 FRAMES`; never a shimmer

### Error
- Alert banner in `--error-bg` with an error lamp, a one-line cause and one fix button ("Download PresentMon", "Restart as administrator")

### Disabled
- `--text4` text and icons, borders drop to `--border`, primary buttons lose the yellow fill

---

## 9. TOGGLE / SWITCH

### Specs

| Property | Value |
|----------|-------|
| Track | 34x18px, radius 2px |
| Thumb | 12x12px square, radius 1px, 3px inset |
| Off track | `--surface2`, 1px `--border-visible` |
| Off thumb | `--text3` |
| On track | `--accent` |
| On thumb | `--on-accent` |
| Label | `--body-sm` right of the track, 8px gap |
| Motion | thumb slides 100ms ease-out |

### States

| State | Treatment |
|-------|-----------|
| Hover | Off track `--surface3` |
| Focus | 1px `--accent` outline, 2px offset |
| Disabled off | `--surface1` track, `--text4` thumb |
| Disabled on | brand.600 track at 50% opacity |

---

## 10. CHECKBOX

### Specs

| Property | Value |
|----------|-------|
| Size | 16x16px |
| Radius | 2px |
| Border | 1px `--border-visible` |
| Checked fill | `--accent` |
| Checkmark | CSS shape, 2px `--on-accent` strokes, butt ends |
| Label | `--body-sm`, 8px gap |

### Variants
- Standalone (Beep on start/stop)
- Group (system checks to include in the report)

### States

| State | Treatment |
|-------|-----------|
| Hover | Border `--text3` |
| Focus | 1px `--accent` outline, 2px offset |
| Indeterminate | `--accent` fill, 8x2px `--on-accent` bar |
| Disabled | `--surface1` fill, `--text4` label |

---

## 11. RADIO

### Specs

| Property | Value |
|----------|-------|
| Size | 16x16px |
| Shape | Square, radius 2px (a round radio would be the only circle in the system) |
| Border | 1px `--border-visible` |
| Selected | 8x8px `--accent` square centered |
| Label | `--body-sm`, 8px gap |

### States

| State | Treatment |
|-------|-----------|
| Hover | Border `--text3` |
| Focus | 1px `--accent` outline |
| Disabled | `--text4` label, `--border` frame |

Prefer a segmented control over a radio group when there are two or three options (Fixed / Manual).

---

## 12. SLIDER / RANGE

### Specs

| Property | Value |
|----------|-------|
| Track | 4px tall, `--surface3`, butt ends |
| Fill | `--accent` |
| Thumb | 4x16px vertical bar in `--text1`, radius 1px (a cursor line, like a scope marker) |
| Value | Plex Mono readout above the thumb |
| Ticks | 1px `--border-visible` at labelled stops (30 s, 60 s, 100 s, 300 s) |

### States

| State | Treatment |
|-------|-----------|
| Hover | Thumb `--accent` |
| Active | Thumb 6px wide |
| Focus | 1px `--accent` outline around the thumb |
| Disabled | Fill `--text4`, thumb `--text4` |

---

## 13. SELECT / DROPDOWN TRIGGER

### Specs

| Property | Value |
|----------|-------|
| Height | 36px |
| Background | `--background` |
| Border | 1px `--border-visible` |
| Radius | 2px |
| Value | Plex Mono for hotkeys and seconds (`F10`, `100 s`) |
| Chevron | `ti-chevron-down` 16px, `--text3` |
| Menu | Dropdown / Popover spec |

### States

| State | Treatment |
|-------|-----------|
| Hover | Border `--text4` |
| Open | Border `--accent`, chevron rotates 180deg in 100ms |
| Focus | Border `--accent` |
| Disabled | `--surface1`, `--text4` |
| Error | Border `--error` ("F12 is reserved by Windows for debuggers.") |

---

## 14. TEXTAREA

Same as the Multiline input: `--background` well, 1px `--border-visible`, radius 2px, 12px padding, min-height 96px, Plex Mono 12px when the content is report text.

### States

| State | Treatment |
|-------|-----------|
| Focus | Border `--accent` |
| Read-only | Border `--border`, no caret, selection `--accent-subtle` |
| Disabled | `--surface1`, `--text4` |

---

## 15. DATA TABLE

### Header Row

| Property | Value |
|----------|-------|
| Height | 32px |
| Font | `--label` uppercase, `--text3` |
| Border | 1px `--border-visible` bottom |
| Alignment | Text columns left, numeric columns right |
| Sort indicator | `ti-arrow-down` 12px in `--text1` on the sorted column |

### Body Row

| Property | Value |
|----------|-------|
| Height | 36px |
| Text | `--body-sm`, `--text2` |
| Numbers | Plex Mono 13px, `--text1`, tabular figures, right-aligned |
| Divider | 1px `--border` |

### Row States

| State | Treatment |
|-------|-----------|
| Hover | `--surface2` |
| Selected | `--surface2` + 2px `--accent` left edge |
| Better / worse cells (compare) | `--success` / `--warning` mono delta beside the value: `+3.7`, `-12.1` |

---

## 16. TABS

### Specs

| Property | Value |
|----------|-------|
| Style | Underline only. No pill tabs. |
| Height | 36px |
| Font | `--label` uppercase |
| Gap | 24px |
| Indicator | 2px `--accent`, full label width, butt ends |

### States

| State | Treatment |
|-------|-----------|
| Active | `--text1` + indicator |
| Inactive | `--text3` |
| Hover | `--text2` |
| Focus | 1px `--accent` outline around the label |
| Disabled | `--text4` |

---

## 17. BREADCRUMB

### Specs

| Property | Value |
|----------|-------|
| Font | Plex Mono 12px |
| Separator | `/` in `--text4` |
| Links | `--text3`, hover `--text1` |
| Current | `--text1` |
| Example | `captures / 2026-11-26 / 211402-cs2` |

---

## 18. AVATAR

### Sizes

| Size | Dimensions |
|------|------------|
| sm | 20px |
| md | 28px |
| lg | 40px |

### Specs

| Property | Value |
|----------|-------|
| Shape | Square, radius 2px |
| Fill | `--surface2` |
| Content | Mono initials of the process (`CS`, `DZ`, `FH`) in `--text2` |
| Border | 1px `--border` |

Frametrace has no users, so avatars stand for games. They never show photos or logos of a game.

### Status Dot Colors

| State | Lamp |
|-------|------|
| Capture OK | `--success` |
| Capture with warnings | `--warning` |
| Capture failed | `--error` |
| Not analyzed | `--text4` |

---

## 19. BADGE / STATUS DOT

### Specs

| Property | Value |
|----------|-------|
| Height | 20px |
| Padding | 0 6px |
| Font | Plex Mono 500, 11px, uppercase |
| Radius | 2px |
| Line height | 1 |

### Semantic Variants

| Variant | Fill | Text | Label examples |
|---------|------|------|----------------|
| Neutral | `--surface2` | `--text2` | `DXGI`, `VSYNC OFF` |
| Info | `--accent-subtle` | `--accent` | `NEW` |
| Success | `--success-bg` | `--success` | `OK` |
| Warning | `--warning-bg` | `--warning` | `CHECK` |
| Error | `--error-bg` | `--error` | `FAILED` |

### Status Dot (icon-only)
- An 8x8px square lamp, radius 1px. Recording lamp `--error`; ready `--success`; idle `--text4`. A lamp is always followed by a word.

---

## 20. TOOLTIP

### Specs

| Property | Value |
|----------|-------|
| Background | `--text1` |
| Text | `--background`, `--caption` |
| Radius | 2px |
| Padding | 4px 8px |
| Max width | 240px |
| Delay | 400ms in, 0ms out |
| Arrow | none (instrument labels do not point) |

---

## 21. ALERT / BANNER

### Specs

| Property | Value |
|----------|-------|
| Layout | Lamp, one-line message, one action button right-aligned |
| Background | status `-bg` token |
| Border | 1px solid the status foreground at 40% opacity |
| Radius | 4px |
| Padding | 12px 16px |
| Text | `--body-sm`, `--text1` |

### Semantic Variants

| Variant | Example |
|---------|---------|
| Info | "Frame generation is on: PresentMon counts generated frames." |
| Success | "PresentMon 2.6.0 verified (SHA-256 matches)." |
| Warning | "RAM runs at 4800 MT/s. The kit is rated 6000. EXPO is off." |
| Error | "PresentMon needs trace permission. Restart as administrator or run the one-time setup." |

---

## 22. TOAST / NOTIFICATION

### Specs

| Property | Value |
|----------|-------|
| Use | Only for confirmations that have no other home: "Report copied" |
| Position | Bottom right of the window, 16px inset |
| Background | `--surface1`, level 2 ring |
| Radius | 4px |
| Duration | 2s, fades out 160ms |
| Font | `--body-sm` + lamp |

### Semantic Variants

| Variant | Lamp |
|---------|------|
| Success | `--success` ("Report copied. 2,184 characters.") |
| Warning | `--warning` |
| Error | `--error` |
| Info | `--text3` |

Capture results never use a toast. They open in the main column.

---

## 23. PROGRESS BAR

### Specs

| Property | Value |
|----------|-------|
| Height | 4px |
| Track | `--surface2` |
| Fill | `--accent` |
| Ends | Butt caps, radius 0 |
| Labels | Elapsed left, remaining right, Plex Mono `--caption` |

### Semantic Fill Colors

| Context | Fill |
|---------|------|
| Recording / analyzing | `--accent` |
| Download complete | `--success` |
| Download failed | `--error` |
| Bottleneck split | Segments in `--ch2` (GPU), `--ch3` (CPU), `--text4` (waiting) |

---

## 24. SPINNER

### Specs

| Property | Value |
|----------|-------|
| Form | A 16px square with a 2px `--accent` segment sweeping its perimeter (no circular spinners) |
| Speed | 900ms linear |
| Use | Only for indeterminate waits under 2 s (checking PresentMon, reading system info) |

---

## 25. SKELETON

### Specs

| Property | Value |
|----------|-------|
| Use | Not used. Frametrace shows real state or a determinate bar. |
| Substitute | Readouts show `---` in `--text4` mono until a value exists |

### Common Shapes

| Shape | Substitute |
|-------|-----------|
| Readout | `--- FPS` in `--text4` |
| Scope | Empty graticule |
| Table row | Not rendered until data exists |

---

## 26. ACCORDION

### Specs

| Property | Value |
|----------|-------|
| Header height | 40px |
| Header font | `--label` uppercase, `--text2` |
| Chevron | `ti-chevron-right`, rotates 90deg in 100ms |
| Body padding | 0 0 16px 24px |
| Divider | 1px `--border` |

### States

| State | Treatment |
|-------|-----------|
| Collapsed | `--text2` header |
| Expanded | `--text1` header |
| Hover | `--text1` |
| Focus | 1px `--accent` outline |
| Disabled | `--text4` |

Used for the System block and the raw notes in the report view.

---

## 27. READOUT (instrument part)

| Property | Value |
|----------|-------|
| Container | `--surface1`, 1px `--border`, radius 4px, padding 12px 16px |
| Label | `--label` uppercase `--text3`, with an optional 8px channel swatch |
| Value | `--readout` 32px Plex Mono 500, `--text1`, tabular figures |
| Unit | `--caption` `--text3`, 4px after the value |
| Sub-line | `--caption` `--text3` mono, e.g. `P95 10.5 ms` |
| Empty | `---` in `--text4` |

## 28. SCOPE (instrument part)

| Property | Value |
|----------|-------|
| Background | `--screen` in both modes |
| Graticule | 1px `--graticule`; 4 major divisions down. Across: 10 on the empty screen; with a trace, one per half time-label step (about 10), so every time label sits on a line. Minor ticks (five per division) on the horizontal centre line |
| Traces | CH1 frame time `--ch1`, CH2 GPU busy `--ch2`, CH3 CPU busy `--ch3`; 1.5px, butt caps |
| Phosphor bloom | CH1 only: a 4px blur copy at 35% opacity under the trace |
| Hitch marker | 1px dashed `--warning` vertical line, a 1px CH1 tick up to the value, and a mono label on the worst one: `14.8 ms @ 61.4 s` |
| Layers | bottom to top: hitch markers, CH1 band, CH3, CH2, REF, CH1 bloom and median, hitch ticks (the busy channels sit above the band so they never hide under it) |
| Legend | Top-left, `CH1 FRAME TIME` style labels with 8px swatches in `--text3` on the screen |
| Scale | Mono `--caption` beside the panel legend: `1 ms/div · 10 s/div · 99.0 s`; axis values on the screen in `--text3` |
| Radius | 4px |

## 29. LAMP (instrument part)

| Property | Value |
|----------|-------|
| Size | 8x8px |
| Radius | 1px |
| Colors | `--success` ok, `--warning` warn, `--error` error or recording, `--text4` idle |
| Pairing | Always followed by a word in `--label` style or a sentence in `--body-sm` |

## 30. SPLIT BAR (instrument part)

| Property | Value |
|----------|-------|
| Height | 8px |
| Segments | GPU-limited `--ch2`, CPU-limited `--ch3`, waiting `--text4`; 1px `--background` gap between segments |
| Ends | Butt, radius 0 |
| Legend | Below: swatch, label, mono percentage |

## 31. REFERENCE TRACE (instrument part)

| Property | Value |
|----------|-------|
| Use | Compare view: capture A as the stored reference (REF A) under capture B |
| Color | `--ref` `#A8A59D`, both modes (it sits on the dark screen) |
| Line | 1.5px median, butt caps, no band, no bloom |
| Legend | `REF A` with a neutral 8px swatch, then `CH1 B` with the yellow swatch |
| Time axis | Each capture on its own seconds; the axis spans the longer one |

## 32. DELTA ROW (instrument part)

| Column | Treatment |
|--------|-----------|
| Metric | `--body-sm`, `--text2` |
| A | Plex Mono, `--text2`, right-aligned |
| B | Plex Mono, `--text1`, right-aligned |
| Bar | 160 x 8px canvas, 1px `--text4` centre line, fill grows right for better and left for worse, full width at 25% |
| Bar fill | status color mixed 55% into `--surface1`: better `--success`, worse `--warning`, same and changed `--text4` |
| Change | Plex Mono: `+4.2%`, or `+0.12 pp` for shares |
| Status | Lamp + word: `BETTER`, `WORSE`, `SAME` (inside run-to-run noise), `CHANGED` (no better direction, e.g. GPU busy), `N/A` |

Rows sit in groups with a silk-screen group label: FRAME RATE, FRAME TIMES, LOAD PER FRAME, LATENCY.

## 33. COMPARE VIEW (pattern)

Read top to bottom like the summary view:

1. **Capture chips.** `A` (neutral swatch, the older capture) and `B` (yellow swatch), each with game, time, length and average FPS in mono.
2. **Verdict.** Headline from the average: "B is 4.2% faster on average." or "Same average FPS." Then one sentence: "Better: ... Worse: ..." with the key metrics (1% low, CPU-side 1% low, P99, PC latency) and their values. Notes below in `--text3`: the limit moved, different games, different lengths.
3. **Scope.** REF A under CH1 B, hitch markers of B only.
4. **Deltas.** Delta rows by group.
5. **Bottleneck.** Two split bars, A then B, each labelled and with percentages.
6. **System changes.** One row per difference (`RAM speed  5600 MT/s  6000 MT/s`) with an info lamp, or one ok lamp and "No system differences."

Run-to-run noise bands (measured on CS2): average and median 1%, lows and P99 3%, 0.1% low and worst second 5%, max frame time 15%, hitch time 0.2 pp, latency 3% (median) and 5% (P95).


## 34. NUMBERS IN PROSE

| Property | Value |
|----------|-------|
| Where | Verdict sentence, check rows, compare notes, alert banners |
| Words | Plex Sans, the line's own size and color |
| Numbers | Plex Mono at the matching size, `--text1`, unit included: `2.16 ms`, `93%`, `6000 MT/s`, `~200` |
| Not numbers | Digits inside names stay in the sans: `7800X3D`, `DDR5`, `P95`, `SHA-256` |
| Wrapping | A no-break space between number and unit, so `2.16 ms` never splits across lines |

## 35. SCROLLBAR

| Property | Value |
|----------|-------|
| Width | 6px, no arrows, no trough |
| Thumb | `--surface3`; `--text4` on hover or while dragging; square ends; min 24px |
| Gutter | Always reserved (8px gap + 6px), so a page's right edge does not move when it starts to scroll |
| Hidden | When everything fits, nothing is drawn |

## 36. SELECT CHEVRON

The select trigger's arrow is a `ti-chevron-down` drawn inside the field (`--text3`, `--text1` on hover), with no button, divider or border of its own. In Tk it is an image element in the combobox layout.
