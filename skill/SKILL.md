---
name: frametrace
description: Read a Frametrace benchmark report and turn it into concrete game-optimization advice. Use when the user pastes a report that starts with "Frametrace report", or asks how to improve FPS, stutter or 1% lows based on one.
---

# Frametrace report analysis

> Draft placeholder (handover step 6). The structure below is the plan. The content gets written
> once real reports exist.

## Inputs
- A Frametrace report (summary statistics, bottleneck split, system info), or two for compare mode.
- Optionally a game profile from `profiles/` matching the report's process name. Always useful
  without one.

## Steps (planned)
1. Sanity checks on system info: RAM running speed below rated (EXPO/XMP off), refresh rate
   vs. monitor maximum, FPS cap vs. refresh rate, power plan, Game Mode, HAGS, frame generation.
2. Read the bottleneck split: GPU-bound, CPU-bound, capped or mixed, with caveats (HAGS, Reflex).
3. Advice per bottleneck type: settings that move load off the limiting part.
4. Compare mode: interpret the before/after deltas, especially lows and P99, not just average FPS.

## Output
Short, ranked list of changes, each with the expected effect and how to verify it with another
Frametrace run.
