---
name: frametrace-design
description: "This skill should be used when the user explicitly says 'Frametrace style', 'Frametrace design', '/frametrace-design', or directly asks to use/apply the Frametrace design system. NEVER trigger automatically for generic UI or design tasks."
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep]
---

# frametrace-design

You are a senior product designer. When this skill is active, every UI decision follows this design language.

**Before starting any design work, declare which fonts are required and how to load them** (see `references/platform-mapping.md`). Never assume fonts are already available. The desktop app bundles IBM Plex Sans and IBM Plex Mono and loads them privately; the web loads them from Google Fonts.

---

## 1. DESIGN PHILOSOPHY

Frametrace is a bench instrument for game performance. Warm graphite panels, silk-screened labels, every number in mono, and one yellow trace of light that is the measurement itself. The tension is clinical lab precision against a single live, warm signal: everything around the trace is quiet so the trace can be loud.

Lineage: bench oscilloscopes (graticule screens, CH1/CH2/CH3 channel colors, square indicator lamps), IBM-era technical documentation (Plex, plain declaratives, tables over prose), motorsport telemetry readouts (big mono numbers with small units). The product's promise is "answers, not graphs", so the UI earns trust the way an instrument does: by labelling every value, showing its unit, and never decorating.

### Design principles

1. **One trace, one yellow.** `--accent` yellow appears on the trace (CH1), the single primary action, and the focus ring. Nowhere else on the screen.
2. **Channels mean signals.** Cyan is always the GPU, magenta is always the CPU. A channel color never decorates, never marks status, never fills a button.
3. **Every number is a readout.** Numbers are set in IBM Plex Mono with a small unit beside them in `--text3`. A number without a unit or label is a bug.
4. **Labels are silk-screen.** Field and panel labels are 11 px uppercase Plex Sans 500 at 0.08em, in `--text3`. Sentence case is for prose and verdicts only.
5. **Depth comes from panels, not light.** Surfaces step up one neutral level at a time with a 1 px border. No shadows except overlays.
6. **The screen stays dark.** The scope screen is `--screen` in both modes, like a real instrument face. Light mode changes the housing, never the screen.
7. **Status is a lamp.** State is shown by an 8 px square lamp plus a word. No round dots, no colored text paragraphs.

---

## 2. CRAFT RULES: HOW TO COMPOSE

### 2.1 Hierarchy layers

| Layer | What sits there | Treatment |
|-------|-----------------|-----------|
| **Housing** | Page background, title bar, rails | `--background`, no border |
| **Panel** | Groups of controls, readout tiles, lists | `--surface1`, 1 px `--border`, radius 4 |
| **Control** | Inputs, segmented controls, secondary buttons | `--surface2` or `--background` well, 1 px `--border-visible`, radius 2 |
| **Screen** | The scope: frame-time trace on a graticule | `--screen`, graticule `--graticule`, never light |
| **Signal** | Trace, channel swatches, the one primary button | `--accent` / `--ch2` / `--ch3` only |

Squint test: with the screen blurred, the only bright things left must be the trace and the primary button. If a third thing glows, remove its color.

### 2.2 Typography discipline

- Two families per screen, always: Plex Sans for words, Plex Mono for every number, unit, identifier, path and hotkey.
- Font budget: at most one display-size element per screen (the verdict or the hero number). Readouts use the 32 px mono readout size; everything else is 15 px or smaller.
- Units sit on the baseline of the value at `--caption` size in `--text3`, separated by a thin space: `426.7 FPS`, `6.8 ms`.
- Never bold a number to emphasize it. Emphasis on a number comes from size (readout) or from its lamp.

### 2.3 Spacing semantics

8 px grid. Inside panels: 16 px padding, 8 px between label and value. Between panels: 16 px. Between major regions (rail and main): 24 px. Readout tiles sit in a row with 8 px gaps, like modules in a rack.

### 2.4 Color strategy

- Max three chromatic colors per screen, and they must be the three channels. Status colors (green, orange, red) appear only inside lamps, alerts and tag tints.
- Warning is orange, never yellow. Yellow belongs to the trace; a yellow warning would read as "this is the measurement".
- In light mode the accent text color is `--accent` (#7F6100, dark brass) because #F5C518 fails contrast on paper. The trace and the primary button fill stay #F5C518 in both modes.

### 2.5 Composition

- Desktop windows use a left rail (about 300 px) for controls and history and a main column for the selected capture. The main column always reads top to bottom: header, verdict, screen, readouts, split bar, checks, actions.
- The verdict is a sentence, not a badge: "GPU-limited. 93% of frames wait on the GPU."
- Data tables right-align numbers and use mono. Selected rows get `--surface2` plus a 2 px `--accent` left edge.

### 2.6 Quick validation

Cover the labels: can you still tell which number is FPS and which is latency from the unit alone? Cover the numbers: do the labels still describe a complete instrument panel? Both must pass.

---

## 3. ANTI-PATTERNS: WHAT TO NEVER DO

- No gradients on surfaces, buttons or text. The only soft light allowed is the trace's phosphor bloom.
- No border-radius above 4 px anywhere. No pills, no circles for status, no rounded avatars.
- No drop shadows on panels or cards. Shadows exist only on popovers and modals.
- No yellow except the trace, the primary button and the focus ring. Not for warnings, not for highlights, not for links.
- No cyan or magenta outside signal contexts (traces, channel swatches, the bottleneck split bar).
- No numbers in the sans font. FPS, ms, MT/s, percentages, timestamps and hotkeys are always Plex Mono.
- No round stroke caps. Bars, gauges, traces and progress fills end square.
- No gamer styling: no RGB gradients, no neon glows, no angular "esports" shapes, no italic speed type.
- No hype copy. No "blazing", "ultimate", "insane". Write the claim, then the number.
- No toast popups for capture results. A finished capture opens its report in the main column; the status lamp and a short beep confirm it.
- No skeleton shimmer. Loading shows a determinate progress bar with the elapsed and remaining seconds.
- No spring or overshoot motion. Transitions are 100 to 220 ms ease-out, and the only continuous motion is the trace sweep while recording.

---

## 4. WORKFLOW

1. **Declare fonts**: check `references/platform-mapping.md` for loading instructions (web and Tkinter)
2. **Set tokens**: apply variables from `references/tokens.md`
3. **Build components**: use specs from `references/components.md`
4. **Check hierarchy**: squint test: only the trace and the primary action stay bright
5. **Verify both modes**: dark is primary; light ("bench daylight") must keep the scope screen dark
6. **Test extremes**: 30 FPS and 1000 FPS readouts, a 3600 s capture, zero captures, a capture with no GPU columns
7. **Platform-adapt**: consult `references/platform-mapping.md` for CSS, Tkinter/ttk and Tailwind

---

## 5. REFERENCE FILES

| File | Contains |
|------|----------|
| `references/tokens.md` | Fonts, type scale, color system (light + dark), spacing, radii, elevation, motion, iconography |
| `references/components.md` | Cards, buttons, inputs, lists, navigation, tags, overlays, state patterns, plus the instrument parts: readout, scope, lamp, split bar |
| `references/platform-mapping.md` | HTML/CSS, Tkinter/ttk (the shipping desktop app), React/Tailwind: platform-specific code and loading instructions |
| `design-model.yaml` | The single source of truth every other file is generated from |
| `preview.html`, `component-library.html`, `landing-page.html`, `app-screen.html` | The four visual proofs of the language |
