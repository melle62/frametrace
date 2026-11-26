---
name: frametrace
description: Turn a Frametrace benchmark report into in-game settings to change for the user's goal (higher average FPS, higher 1% lows, lower latency, less stutter, or a target FPS at the best quality) for any game that has no Frametrace game skill of its own, and run a game study that gathers the settings, a repeatable scene and measured captures needed to build one. Use when text starting with "Frametrace report" or "Frametrace compare" is pasted for such a game, or when the user wants to study a game, build a Frametrace skill for it, or pastes a Frametrace study log.
license: MIT
---

# Frametrace: settings advisor and game study

The user benchmarks a game with Frametrace, picks a goal, and wants to know which **in-game
settings** to change to reach it. This skill does two jobs:

1. **Advise** for any game that has no game skill yet, from the report and general knowledge.
2. **Study** a new game: gather its settings, a repeatable scene and measured captures until there
   is enough to write a game skill (`frametrace-<game>`), which then takes over for that game.

Game skills so far: `frametrace-cs2` (Counter-Strike 2). When a report is for one of these games
and its skill is available, follow that skill instead. Every report also works with no skill at
all: it is a complete prompt.

## Which job
- **A report or comparison is pasted** → advise (rules below). At the end of the first answer
  for a game without a skill, offer the study once, in one line: every capture the user makes
  for advice counts as study data.
- **The user asks to study, profile or "make a skill for" a game, or pastes a study log** → run
  the game study. Keep advising on each report along the way: the study is the same loop, with
  more care and a log.

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

## Advising without a game skill
- Use what you know about this game and its engine, and label it as such. If you can search the
  web, check the game's current graphics options: patches add, rename and remove settings.
  Guide claims about cost are "from a guide" until a Frametrace comparison confirms them.
- If `## Game` says only the process name is known, ask which game, version and store it is.
- Frame generation can't be detected, and PresentMon doesn't label generated frames: if it was
  on, FPS numbers aren't comparable with runs without it. Ask, and compare latency instead.

## Game study
The aim: enough measured data to write a game skill that gives better advice than general
knowledge. A study spans sessions, so everything goes into one **study log** (template below).

### The study log
- Update it after every step and give the user the updated log, or write it to a file or project
  doc when you can. A new session continues when the user pastes it back.
- Every entry says where it comes from: **measured** (a Frametrace capture or comparison, by run
  label or time), **seen** (a screenshot, the menu or a config file), **guide** (with a link) or
  **unknown**. Never log a guess as a fact.
- Log Frametrace's own gaps too (name not found, settings not read, no GPU busy, no PC latency):
  each one is a possible contribution to Frametrace.

### Steps
1. **Identify the game.** From `## Game`: name and where it came from, store and ID, build, exe,
   version, engine, graphics API. Ask what the report can't show: anti-cheat, launcher, store
   (Steam, Xbox app, Epic…), and whether an upscaler or frame generation was on.
2. **Settings inventory.** Ask for screenshots of every graphics and display page, including
   advanced pages and the preset. Log each setting: page, menu name, options in menu order,
   current value, and its config key once known. Note settings that need a restart, the frame
   cap, VSync, upscalers and their modes, frame generation, Reflex or Anti-Lag, dynamic
   resolution.
   - **Frametrace read the settings:** map the keys whose names are obvious and mark the rest
     unmapped. Step 6 maps them for free: each one-change comparison names the key that moved.
   - **Not read:** find where the game keeps them (look it up, or ask the user to look in
     Documents, Saved Games, `%LOCALAPPDATA%`, the install folder, or for the file whose date
     changes right after applying a setting). Ask for a paste with account names and IDs
     removed. Log the path and format: a reader for it is a Frametrace contribution (an engine
     reader when it's a standard engine format).
3. **A repeatable scene.** Best first: a built-in benchmark, a replay or timedemo, a fixed route
   offline or on an empty private server, a fixed spot (least like real play). It must repeat
   exactly: same route, time of day and weather (locked if possible), no other players, no
   changing AI. At least 60 s. Write start and end cues anyone can follow, and capture the same
   way every time (Manual length with the hotkey on the cues, or Fixed length started on the
   cue). Note how the scene compares with real play: busy multiplayer is usually more CPU-bound
   than an empty benchmark.
4. **Baseline and noise.** Play the scene once to warm up (the first pass after loading compiles
   shaders and streams assets), then two captures with identical settings. Compare them: every
   goal metric should come back "no change". If not, find out why before measuring settings
   (warm-up, capture start, background tasks, temperature, the route) and repeat until two runs
   agree. Log both runs. If this game's spread is wider than Frametrace's noise bands, log the
   measured spread: the game skill needs it.
5. **Find the limit.** Log the bottleneck at the user's usual resolution. Then one capture at the
   lowest render resolution or render scale, everything else unchanged: if FPS barely rises, the
   CPU limits this scene and the FPS reached is its CPU ceiling. When GPU busy data is missing,
   this test is the only way to tell the sides apart.
6. **One change at a time.** Change one setting, capture, compare with the baseline, change it
   back. Order by expected cost on the limiting side (engine knowledge and guides); 5–8 settings
   usually cover most of the cost. Then the frame cap, VSync and latency options, and upscaler
   modes. Re-run the baseline every ~5 captures and after any game or driver update; if it moved
   beyond noise, measure from the new baseline. Per run, log: setting from → to, config key (from
   the comparison), change in average, 1% low, 0.1% low, time in hitches, PC latency and GPU
   busy, the verdict (inside noise or not), and what the user saw (visual cost, visibility).
7. **Ready for a game skill?** Draft it when the log has all of:
   - the game identified, with the build that was tested;
   - a settings map for every graphics setting (menu name, options, config key when read, or
     the settings file's location when not);
   - a documented scene with two baseline runs that agree;
   - the bottleneck on at least one system at a stated resolution;
   - at least three settings on the limiting side measured one at a time, plus the frame cap and
     latency options the game has.
   Short of that, say what's missing and keep going. More systems improve a skill later; they
   don't block the first version.
8. **Write the game skill** with the outline below. Copy the shared rules block above unchanged
   (between the `frametrace:shared-rules` markers). Measured numbers name the system,
   resolution, scene and runs; guide claims say "guide" and link it; everything else goes under
   "Not measured yet". The description must name the game, the exe and the store ID, so it is
   picked for the right reports. Offer it as a pull request to `melle62/frametrace`
   (`skills/frametrace-<slug>/SKILL.md`) and, for Claude users, as a skill to add.

### Study log template
```markdown
# Frametrace study: <game>
Step <n> of 8 · updated <date>

## Game
Name, store and ID, build, exe, engine, graphics API, anti-cheat, launcher
Frametrace: name from … · settings read: yes (reader, path) / no · GPU busy: yes/no · PC latency: yes/no

## Systems
CPU, GPU and driver, RAM, display and refresh rate, resolution tested

## Settings map
| Page | Menu name | Options (menu order) | Current | Config key | Source |
|---|---|---|---|---|---|

## Settings file
Path, format, how it was found · Frametrace reader: yes / no / needed

## Scene
Where, route, start cue, end cue, length, warm-up, how it compares with real play

## Baseline runs
| Run | Date | Length | Average | 1% low | 0.1% low | Time in hitches | PC latency | GPU busy | Bottleneck |
|---|---|---|---|---|---|---|---|---|---|
Spread between runs: …

## Measured changes
| Run | Setting: from → to | Config key | Average | 1% low | 0.1% low | Hitches | Latency | GPU busy | Verdict | Looks |
|---|---|---|---|---|---|---|---|---|---|---|

## Quirks seen
## Open questions
## Not measured yet
```

### Game skill outline
The full template is `skills/game-skill-template.md` in the Frametrace repo. Its parts:
- Frontmatter: `name: frametrace-<slug>`; a `description` naming the game, exe, store ID and the
  five goals, saying to use it instead of the general frametrace skill for this game; `license:
  MIT`; `metadata` with `game`, `process_names`, `store_ids`, `engine`, `apis`, `anti_cheat`,
  `status` (`tested` when step 7's bar is met) and `last_verified` (date and build).
- `# <Game> settings advisor (Frametrace)` and one paragraph on what was measured, and where.
- The shared rules block, unchanged.
- `## The game`: names, exe, store, engine, APIs, anti-cheat, the build tested, the systems.
- `## Visual cost in <game>`: what players trade (looks, or visibility in competitive games).
- `## Settings map`: config key → menu name → values, marked seen or unverified.
- `## Measured costs`: the one-change results, with system, resolution and scene.
- `## By goal`: the five goals, what to change first in this game, measured first.
- `## Benchmark scene`: how to capture this game repeatably, the warm-up, the cues.
- `## Reading this game's reports`: how Frametrace's numbers relate to the game's own counters,
  patterns that aren't problems, settings in the list that don't affect performance.
- `## Not measured yet` and `## Sources`.
