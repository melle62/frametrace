---
name: frametrace
description: Turn a Frametrace benchmark report into in-game settings to change for the user's goal (higher average FPS, higher 1% lows, lower latency, less stutter, or a target FPS at the best quality). Use when the user pastes a report that starts with "Frametrace report" or "Frametrace compare", or asks which game settings to change based on one.
---

# Frametrace settings advisor

The user benchmarked a game with Frametrace, picked a goal, and wants to know which **in-game
settings** to change to reach it. The report is already a complete prompt: it states the goal,
the game, the current settings (when Frametrace could read them) and the evidence. This skill
makes the answers sharper and consistent. Every report must work without it.

## Read the report in this order
1. **Goal** line and `## Goal` section: what "better" means and the numbers that measure it.
2. `## Game`: the real game name, store build, engine and graphics API. Advise for *this* game
   and version, with the setting names as they appear in its menu.
3. `## Current in-game settings`: values read from the game's config file. Translate config keys
   into menu names (a profile in `profiles/` may list them). If the section says they weren't
   read, **ask for them first**: a paste, or a screenshot of the graphics menu. Don't guess the
   current values.
4. `## Bottleneck`: which kind of setting can move the frame rate in this scene.
   - **GPU-limited** (≥ 70% of frames): resolution, upscaler and its quality mode, shadows,
     lighting/GI, reflections, ambient occlusion, anti-aliasing, volumetrics, ray tracing.
   - **CPU-limited**: view/draw distance, crowd and object density, physics, simulation detail,
     and settings the game documents as CPU-bound. GPU-only settings barely help here.
   - **Capped / waiting**: the cap, VSync or Reflex setting sets the rate. Spend GPU headroom on
     quality, or lift the cap if the goal is more FPS.
   - **Mixed**: the scene moves the limit. Settings on both sides matter.
5. `## Capture notes`: what the capture shows or can't show (stutter, a short capture, frame
   generation). Stutter here is evidence for the goal, not something to fix in Windows.
6. `## Fix first (outside the game)`: anything marked `[!]` (RAM below its rated speed,
   refresh rate below the monitor's maximum, desktop compositor in the present path, power saver)
   goes first in the answer, in one line each.

## Per goal
- **Higher average FPS:** the biggest cost on the limiting side first. Keep 1% lows from
  getting worse.
- **Higher 1% lows:** look at the gap between the 1% low and the average, the CPU-side 1% low
  and the hitches. Lows usually suffer from CPU spikes (streaming, simulation, shader
  compilation) more than from average GPU load. A frame cap just below the 1% low can also
  even out pacing. A slightly lower average is acceptable.
- **Lower latency:** use PC latency when present (Reflex markers). Otherwise judge by frame
  time, VSync, the present mode and caps. Reflex on (+ Boost when GPU-limited), VSync off, a
  cap a few FPS below the refresh rate with VRR, and a GPU that isn't at 99% all cut latency.
- **Less stutter:** hitch count, time in hitches, worst frames, 0.1% low and max frame time.
  Shader compilation, asset streaming (texture quality vs. VRAM), and uncapped frame rates on
  uneven scenes are the usual causes. A cap often fixes uneven pacing.
- **Hit a target FPS:** the report says whether the target was met (1% low vs. target and
  share of seconds at the target). If met with room, recommend what to *raise* for better
  visuals. If not, the cheapest-looking settings with the biggest cost go first.

## Answer format
1. One sentence on what limits this run, in plain words.
2. `[!]` fixes outside the game, if any.
3. A ranked list of **1–3** in-game changes: setting (menu name), current → new, the expected
   effect on the goal, the visual cost. Fewer changes per run make the next comparison readable.
4. "Re-run the same scene with the same capture length, then paste the Frametrace comparison."
5. Say plainly when you aren't sure a setting exists in this version or what it costs.

## Comparisons ("Frametrace compare")
- `## Result for the goal` already applies the run-to-run noise bands: average and median 1%,
  lows and P99 3%, 0.1% low and worst second 5%, max frame time 15%. Inside them = no change.
- `## In-game settings changed` lists what changed between A and B when Frametrace read the
  config both times. Otherwise ask what was changed.
- Say whether to keep the change, then give the next 1–3 changes from B's bottleneck and B's
  current settings. If the limit moved (GPU → CPU), switch to settings on the new side.

## Game profiles
When `profiles/<game>.md` lists the report's process name, use it: config key → menu name,
measured costs, repeatable benchmark scenes, quirks. Profiles add knowledge; without one, use
what you know about the game and the engine.
