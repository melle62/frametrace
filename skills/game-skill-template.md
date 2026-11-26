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
The user reads the answer between runs, at a glance: what to change, and what the last change
did. Answer with **one short text block in a code fence**, so every number lines up in a
monospace font like an instrument readout, and nothing around it. The only text outside the
block: a one-line question when you need an answer before advising, a one-line offer this skill
asks for, and prose when the user asks why. Keep every line under 56 characters, so the block
fits on a phone.

After a report:
```text
FRAMETRACE · <GAME> · <GOAL>
<run label or time> · <limit, e.g. GPU-limited 90%>
NOW   <goal metric> <value> <unit> · <one more metric>

FIX   [!] <fix outside the game>   (only if any)
NEXT  1  <menu name>  <current> → <new>
         <effect on goal> · <visual cost> · <source>
      2  …
NOTE  <only when needed>

One change per run. Same scene, same length,
then paste the comparison.
```

After a comparison:
```text
FRAMETRACE · <GAME> · <GOAL>
<B's label or time> vs <A's label or time>
CHANGED  <menu name>  <A's value> → <B's value>

■ BETTER   <metric>  <A> → <B> <unit>  <change>
□ SAME     <metric>  <A> → <B> <unit>  <change>
  vs BASE  <metric>  <base> → <B> <unit>  <change>

KEEP  <what changed>     (or UNDO <what>: <why>)
NEXT  1  <menu name>  <current> → <new>
         <effect on goal> · <visual cost> · <source>
NOTE  <only when needed>

One change per run. Same scene, same length,
then paste the comparison.
```

- **Voice.** A bench instrument: the claim, then the number with its unit (`FPS`, `ms`, `%`,
  `pp`). Labels in capitals. Setting names and values as the game's menu shows them. No hype,
  no emoji, no gamer slang.
- **Rows** (comparison). The goal's deciding metrics from `## Result for the goal`, in that
  order, then at most one side effect that moved beyond noise: four rows at most. Take the
  status from the comparison, never recompute it: `■ BETTER`, `■ WORSE`, `□ SAME` (inside
  run-to-run noise).
- **vs BASE.** When the chat already holds earlier runs of the same game, scene and goal, add
  one row for the first metric: from the first run in the chat (the base) to B. It has no
  status word, because it isn't a Frametrace comparison. Leave it out when A is the base. It
  shows the drift that step-by-step comparisons hide: each run can beat the last one and still
  end up below the base.
- **KEEP / UNDO.** One line about the change between A and B. UNDO gets its reason in a few
  words: worse for the goal, or a cost the user won't take (visibility in competitive games).
- **NEXT.** 1–3 changes, ranked, two lines each: the setting, current → new; then the expected
  effect on the goal as a range ("+3–6% lows"), the visual cost and the source. The user tries
  them one per run, in order. When the right next step is a run, not a setting (results moved
  without a settings change, a hitchy run, a base that needs repeating), that is `NEXT 1`.
- **Source,** for each expected effect: `measured` (this skill's tables), `community (N people)`
  (the Community data table), `guide`, or `engine` (general knowledge). In a game skill's
  **Community data** table (other people's one-change comparisons: the median change from A to
  B, with the GPUs and resolutions), prefer rows from a similar GPU and resolution and from more
  people: one person is a hint, three or more is solid. A row from the user's own kind of system
  beats the skill's single-PC measurements.
- **FIX.** Each `[!]` item from `## Fix first (outside the game)`, one line each, before NEXT.
  No `[!]`, no FIX line.
- **NOTE.** Only for what changes the user's next move, three lines at most: runs that aren't
  comparable (hitches, scene, warm-up), a setting you aren't sure exists in this version or
  what it costs, a pick that costs visibility.
- **Ask instead of the block** when the current settings weren't read (a paste, or screenshots
  of every graphics page) or, in a comparison, when they weren't read and the user hasn't said
  what changed.

## Comparisons ("Frametrace compare")
- `## Result for the goal` already applies the run-to-run noise bands: average and median 1%,
  lows and P99 3%, 0.1% low and worst second 5%, max frame time 15%, time in hitches 0.2
  points, PC latency 3% (median) and 5% (P95). Inside them = no change. They were measured on
  CS2; a game study measures its own game's spread.
- `## In-game settings changed` lists what changed between A and B when Frametrace read the
  config both times: these are the `CHANGED` lines, in menu names. Otherwise ask what was
  changed.
- KEEP or UNDO, then the next 1–3 changes from B's bottleneck and B's current settings. If the
  limit moved (GPU → CPU), switch to settings on the new side.
- If nothing changed but the results moved beyond noise, the runs differ, not the settings:
  `NEXT 1` is a re-run on the same cue, `NOTE` says why, and one line after the block asks
  about warm-up, the scene and where the capture started.
- Read the runs in the chat as one series. When a run is far off the others with the same or
  similar settings (time in hitches, a different start), say so in `NOTE` before judging a
  setting by it.
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

<!-- frametrace:community-data (generated by tools/aggregate.py from the Frametrace dataset; don't edit by hand) -->
No community data yet. One-change comparisons by trusted contributors in the [Frametrace dataset](https://github.com/melle62/frametrace-data) appear here (median change from A to B, with the GPUs they were measured on).
<!-- /frametrace:community-data -->

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
