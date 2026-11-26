---
name: frametrace-example-game
description: Recommend in-game settings in Example Game (examplegame.exe, Steam app 000000) from a Frametrace report or comparison, for the user's goal (higher average FPS, higher 1% lows, lower latency, less stutter or a target FPS). Knows Example Game's config keys and menu names, measured setting costs and how to benchmark it repeatably. Use when text starting with "Frametrace report" or "Frametrace compare" names Example Game or examplegame.exe, instead of the general frametrace skill.
license: MIT
metadata:
  game: Example Game
  process_names: [examplegame.exe]
  store_ids: {steam: "000000"}
  engine: Unknown
  apis: [DX11, DX12]
  anti_cheat: none
  status: partial
  last_verified: YYYY-MM-DD, build NNNN
---

<!--
Template for a game skill. Copy it to skills/frametrace-<slug>/SKILL.md, fill it from a game
study (the general frametrace skill runs one), and delete this comment. Keep the shared rules
block below unchanged: tools/sync_skills.py copies it from skills/frametrace/SKILL.md.
status: "tested" when the study's readiness bar is met (settings map, repeatable scene with two
agreeing baseline runs, the bottleneck, three or more one-change measurements on the limiting
side plus the cap and latency options); "partial" before that.
-->

# Example Game settings advisor (Frametrace)

One paragraph: what this skill knows about Example Game, and on which systems and scene it was
measured.

<!-- frametrace:shared-rules (source: skills/frametrace/SKILL.md; copy with tools/sync_skills.py) -->
## Reading a Frametrace report
The report is a complete prompt: the goal, a task for the AI, the goal's numbers, the game, the
current settings (when Frametrace could read them), then the evidence. Read it in this order:
1. The `Goal:` line and `## Goal: …`: what "better" means and the numbers that measure it.
2. `## Game`: name, store build, engine and graphics API. Advise for this game and version, with
   the setting names as they appear in its menu.
3. `## Current in-game settings`: values read from the game's config. Translate config keys into
   menu names (with this skill's settings map, when it has one). If they weren't read, **ask for
   them first**: a paste, or screenshots of every graphics page. Never guess current values.
4. `## Bottleneck`: which kind of setting can move the frame rate in this scene.
   - **GPU-limited:** resolution, upscaler and its quality mode, shadows, lighting/GI,
     reflections, ambient occlusion, anti-aliasing, volumetrics, ray tracing.
   - **CPU-limited:** view/draw distance, object and crowd density, physics, simulation detail,
     and settings the game documents as CPU-bound. GPU-only settings barely help here.
   - **Capped / waiting:** the cap, VSync or Reflex setting sets the rate. Spend GPU headroom on
     quality, or lift the cap if the goal is more FPS.
   - **Mixed:** the scene moves the limit. Settings on both sides matter.
   - **No split** (GPU busy data missing): the limiting side is unknown. Say so, and suggest one
     capture at the lowest render resolution: if FPS barely rises, the CPU limits.
5. `## Capture notes`: what the capture shows or can't show (stutter, a short capture, frame
   generation). Stutter here is evidence for the goal, not something to fix in Windows.
6. `## Fix first (outside the game)`: anything marked `[!]` (RAM below its rated speed, refresh
   rate below the monitor's maximum, desktop compositor in the present path, power saver) goes
   first in the answer, one line each.

## Per goal
- **Higher average FPS:** the biggest cost on the limiting side first. Keep 1% lows from
  getting worse.
- **Higher 1% lows:** look at the gap between the 1% low and the average, the CPU-side 1% low
  and the hitches. Lows usually suffer from CPU spikes (streaming, simulation, shader
  compilation) more than from average GPU load. A frame cap just below the 1% low can even out
  pacing, if the game's limiter paces evenly. A slightly lower average is acceptable.
- **Lower latency:** use PC latency when present (Reflex markers). Otherwise judge by frame time,
  VSync, the present mode and caps. Reflex on (+ Boost when GPU-limited), VSync off, a cap a few
  FPS below the refresh rate with VRR, and a GPU that isn't at 99% all cut latency.
- **Less stutter:** hitch count, time in hitches, worst frames, 0.1% low and max frame time.
  Shader compilation, asset streaming (texture quality vs. VRAM) and uncapped frame rates on
  uneven scenes are the usual causes. A cap often fixes uneven pacing.
- **Hit a target FPS:** the report says whether the target was met (1% low vs. target and share
  of seconds at the target). If met with room, recommend what to *raise* for better visuals. If
  not, the cheapest-looking settings with the biggest cost go first.

## Answer format
1. One sentence on what limits this run, in plain words.
2. `[!]` fixes outside the game, if any.
3. A ranked list of **1–3** in-game changes: setting (menu name), current → new, the expected
   effect on the goal, the visual cost. Fewer changes per run make the next comparison readable.
4. "Re-run the same scene with the same capture length, then paste the Frametrace comparison."
5. Say where each expected effect comes from: measured with Frametrace (this skill's tables), a
   guide, or general engine knowledge. Say plainly when you aren't sure a setting exists in this
   version or what it costs.

## Comparisons ("Frametrace compare")
- `## Result for the goal` already applies the run-to-run noise bands: average and median 1%,
  lows and P99 3%, 0.1% low and worst second 5%, max frame time 15%, time in hitches 0.2
  points, PC latency 3% (median) and 5% (P95). Inside them = no change. They were measured on
  CS2; a game study measures its own game's spread.
- `## In-game settings changed` lists what changed between A and B when Frametrace read the
  config both times. Otherwise ask what was changed.
- Say whether to keep the change, then give the next 1–3 changes from B's bottleneck and B's
  current settings. If the limit moved (GPU → CPU), switch to settings on the new side.
- If nothing changed but the results moved beyond noise, the runs differ, not the settings: ask
  about warm-up, the scene and where the capture started before advising more changes.
<!-- /frametrace:shared-rules -->

## The game
- Process names, store and ID, engine, graphics APIs, anti-cheat, launcher.
- Build and date tested, and the systems (CPU, GPU, resolution).
- What Frametrace reads for this game (settings reader and path, PC latency, GPU busy).

## Visual cost in Example Game
What players trade when a setting goes down: looks, or, in competitive games, visibility of
opponents. Settings that should not be lowered for the sake of FPS, and why.

## Settings map
Where the game keeps its graphics settings, and config key → menu name → values. Mark each
value "seen" (matched to the menu) or unverified.

| Config key | Menu name | Values |
|---|---|---|
| `example_shadow_quality` | Shadow Quality | seen 2 = High; 0 Low, 1 Medium, 3 Ultra |

## Measured costs
One-change Frametrace comparisons against a baseline: setting from → to, average, 1% low,
0.1% low, time in hitches, PC latency, GPU busy, verdict. State the system, resolution, scene
and run labels. Settings changed together are reported together, never split.

## By goal
What to change first in this game for each goal: higher average FPS, higher 1% lows, lower
latency, less stutter, a target FPS at the best quality. Measured effects first, then guide
claims marked "guide".

## Benchmark scene
How to capture Example Game repeatably: the scene, start and end cues, length, warm-up, and how
it compares with real play.

## Reading this game's reports
How Frametrace's numbers relate to the game's own counters, frame-time patterns that aren't
problems, and settings in the list that don't affect performance.

## Not measured yet
Settings, goals, systems and APIs nobody has measured.

## Sources
Frametrace captures (date, system), the game's own counters, and links behind guide claims.
