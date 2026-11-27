---
name: frametrace-cs2
description: Recommend in-game settings for Counter-Strike 2 (cs2.exe, Steam app 730) from a Frametrace report or comparison, for the user's goal (higher average FPS, higher 1% lows, lower latency, less stutter or a target FPS). Knows CS2's config keys and menu names, measured setting costs, the Reflex trade-offs, which settings cost visibility, and how to benchmark CS2 repeatably. Use when text starting with "Frametrace report" or "Frametrace compare" names Counter-Strike 2 or cs2.exe, instead of the general frametrace skill.
license: MIT
metadata:
  game: Counter-Strike 2
  process_names: [cs2.exe]
  store_ids: {steam: "730"}
  engine: Source 2
  apis: [DX11, Vulkan]
  anti_cheat: VAC
  status: tested
  last_verified: 2026-11-26, build 26879581
---

# Counter-Strike 2 settings advisor (Frametrace)

Everything marked measured comes from Frametrace captures and CS2's own VProf counter on one PC
(Ryzen 7 7800X3D, RTX 4070 Ti Super), on FPSfrequency's FPS Benchmark workshop map, or from
community one-change pairs counted by `tools/aggregate.py` (tagged community, with the number of people). Claims
from guides are marked "guide". Anything else is listed under "Not measured yet".

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
   first in the answer, one line each. A report shows hitch time, not which apps were open.
   When more than 1% of the time is in hitches and the user hasn't said what else was open,
   ask whether Discord is running. If it is, turn off its Hardware Acceleration (Settings >
   Advanced) first, before any in-game change. It interrupts the game about 9 times a second
   (measured on one PC in CS2 (2026-11-27): 1% low 155 → 214 FPS with it off, 229 with
   Discord quit).

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
  When more than 1% of the time is in hitches and the user hasn't said what else was open, ask
  whether Discord is running. If it is, one line to turn off its Hardware Acceleration
  (Settings > Advanced), before NEXT. Leave out FIX when none apply.
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
- `cs2.exe`, Steam app 730, Source 2, DX11 (Vulkan with the `-vulkan` launch option), VAC.
  Frametrace captures it with VAC running.
- Tested: build 26879581, 2026-11-26. System: Ryzen 7 7800X3D, RTX 4070 Ti Super (driver
  621.40), 32 GB DDR5-5600, 280 Hz 1440p OLED. Goal runs at 1920 × 1440 (4:3); validation and
  Reflex runs at 2560 × 1440.
- Frametrace names it from Steam (cs2.exe has no version resource; the Steam build identifies
  it), reads `cs2_video.txt` and the rendering convars, and reports PC latency: CS2 sends NVIDIA
  PC Latency markers.

## Visual cost in CS2
Most CS2 players trade looks freely but not **visibility**. Rank by what a change does to seeing
opponents, not by how the game looks.
- **Keep on:** Boost Player Contrast (guide: clearer outline of player models, near-zero cost;
  guide A −0.1% avg; guide P2: 78.6%; P3: 83%) and Dynamic Shadows **All** (guide: player
  shadows from every light, not only the sun; they can show a player around a corner before
  the model is visible; guide A / B −0.6% / −2% avg; guide P2: 176/177). Never suggest
  "Sun Only".
- **Global Shadow Quality:** guide: at Low, player shadows are drawn over a shorter distance.
  Prefer Medium over Low when cutting shadows; say it may cost visibility. Guides disagree:
  A and P1 say Low shows the same player shadows when Dynamic Shadows is All; pros mostly run
  High (guide P2: 68.4%; P3: 66%; P4: 67.7%).
- **Anti-aliasing:** less AA makes thin and distant edges shimmer. Guide A: without MSAA,
  players behind grates (Vertigo catwalk) are hard to see. CMAA2 is cheap (guide A −1.1%) but
  is not MSAA: the grate problem applies to it too. Guide A recommends 2X MSAA.
- **Texture Filtering:** guide A, one run: Trilinear lowered the 1% low 284.7 → 266.1 while
  the 0.1% low barely moved; prefer Anisotropic. Mention the single source in NOTE when you
  suggest it. Guide A: Bilinear blurs distant heads; Anisotropic 2X is its recommended spot.
  Anisotropic 2X–16X is near free (guide A / B: −0.9% / −1%).
- **Resolution and FSR:** lower render resolution blurs distant models. Last resort.
- **Particle Detail:** guide A: higher detail gives no visibility through HE or molotov
  effects, only clutter. Ambient Occlusion, Shader Detail and HDR mode: mostly looks.
- **Pros (guide, popularity not a measured benefit):** V-Sync off 100% (guide P2, P3 and P4),
  Shader Low ~80% (guide P2: 79.2%; P4: 82.6%), Particle Low 89% (guide P4: 89.1%).
  Links and date (read 2026-11-27) are under Sources (A, B, P1–P4).

## Settings map
Frametrace reads `cs2_video.txt` from `Steam\userdata\<account>\730\local\cfg\` (the newest one
when several Steam accounts have played) and lists its `setting.*` entries. From the convar files
in the same folder (`cs2_user_convars_0_slot0.vcfg`) and the install's
`cs2_machine_convars.vcfg` it adds the rendering convars (names starting with `fps_max`, `r_`,
`mat_` or `engine_low_latency`); shipped defaults (`machine_convars_default.vcfg`) are skipped.

Checked against the Video settings page on the maintainer's PC (2026-11-26). "Seen" marks a value
matched to the menu; the rest of each range follows the menu's order and is unverified.

| Config key | Menu name | Values |
|---|---|---|
| `defaultres` × `defaultresheight` | Resolution | pixels; seen 1920 × 1440 |
| `aspectratiomode` | Aspect Ratio | seen 0 with 1920 × 1440 (4:3) |
| `fullscreen` / `nowindowborder` / `coop_fullscreen` | Display Mode | seen 0 / 1 / 1 |
| `mat_vsync` | V-Sync | seen 0 = Disabled |
| `msaa_samples` | Multisampling Anti-Aliasing Mode | seen 2 = 2X MSAA, 4 = 4X MSAA; 0 none, 8 = 8X |
| `r_csgo_cmaa_enable` | Multisampling Anti-Aliasing Mode: CMAA2 | 1 when CMAA2 is chosen; seen 0 |
| `videocfg_shadow_quality` | Global Shadow Quality | seen 2 = High; 0 Low, 1 Medium, 3 Very High |
| `videocfg_dynamic_shadows` | Dynamic Shadows | seen 1 = All; 0 = Sun Only |
| `videocfg_texture_detail` | Model / Texture Detail | seen 2 = High; 0 Low, 1 Medium |
| `r_texturefilteringquality` | Texture Filtering Mode | seen 3 = Anisotropic 4X; 0 Bilinear, 1 Trilinear, 2 2X, 4 8X, 5 16X |
| `shaderquality` | Shader Detail | seen 1 = High; 0 Low |
| `videocfg_particle_detail` | Particle Detail | seen 0 = Low; 2 was the default (High) |
| `videocfg_ao_detail` | Ambient Occlusion | seen 0 = Disabled; 2 was the default (likely High, 1 Medium) |
| `videocfg_parallax_detail` | Parallax Occlusion Mapping | seen 1 = Enabled; 0 Disabled |
| `videocfg_hdr_detail` | High Dynamic Range | seen -1 = Quality; 3 Performance |
| `videocfg_fsr_detail` | FidelityFX Super Resolution | seen 0 = Disabled (Highest Quality); 1 Ultra Quality … 4 Performance |
| `r_low_latency` | NVIDIA Reflex Low Latency | seen 0 = Disabled; 1 Enabled, 2 Enabled + Boost |
| `fps_max` (convar) | Maximum FPS In Game | 0 = no cap; seen 0 in the menu |
| `fps_max_ui` (convar) | Maximum FPS In Menus | seen 120 in the menu |
| `fps_max_tools` (convar) | not in the menu | seen 120 |
| `r_player_visibility_mode` (convar) | Boost Player Contrast | seen 1 = Enabled |
| `refreshrate_numerator` / `_denominator` | Refresh Rate | seen 0 / 0 |
| `monitor_index`, `high_dpi`, `fullscreen_min_on_focus_loss` | display options | no effect on FPS |
| `cpu_level`, `gpu_level`, `gpu_mem_level` | not in the menu | seen 3 / 3 / 3; meaning unknown |

## Measured costs
**NVIDIA Reflex**, Off / Enabled / Enabled + Boost, over the same 78.7 s of the benchmark (runs
aligned to within 0.25 s; 2560 × 1440, GPU-limited, uncapped):

| | Off | Enabled | Enabled + Boost |
|---|---|---|---|
| Average FPS | 430.4 | 426.7 | 414.1 |
| PC latency, median | 7.25 ms | 6.83 ms | 6.30 ms |
| PC latency, P95 | 11.8 ms | 10.5 ms | 9.2 ms |
| 1% low, present to present | 202 | 169 | 154 |
| 1% low, CPU-side | 205 | 199 | 191 |
| GPU busy per frame | 2.08 ms | 2.09 ms | 2.08 ms |
| Blocked in Present | 1.36 ms | 1.23 ms | 0.95 ms |
| GPU-limited frames | 95% | 93% | 88% |

Each step trades a little FPS and pacing evenness for lower latency, mostly in the worst moments
(P95 −2.6 ms from Off to Boost, about 0.7 of a refresh at 280 Hz). GPU time per frame didn't
change: with Boost the game holds frames back, the GPU queue stays shorter and the GPU idles a
little more. Under `fps_max` far below what the GPU can do, Reflex had no measurable effect.

**Particle Detail High → Low, MSAA 4X → 2X, Ambient Occlusion High → Disabled**, all three at
once (1920 × 1440, GPU-limited, fixed 79 s captures started by hand; goal "Higher 1% lows"):

| Run | Settings | 1% low | 0.1% low | Average | Time in hitches | GPU busy |
|---|---|---|---|---|---|---|
| 14:04 | before | 146.7 | 80.7 | 372.2 | 3.7% | 2.31 ms |
| 14:10 | after | 214.6 | 184.9 | 440.9 | 0.0% | 2.04 ms |
| 14:27 | after | 163.6 | 99.9 | 419.8 | 3.1% | 2.03 ms |
| 14:44 | after | 212.2 | 182.0 | 439.3 | 0.0% | 2.03 ms |

- Certain: GPU time per frame fell 12% (2.31 → 2.03 ms). Between the two hitchy runs (14:04,
  14:27) the change gave about +12% on the average and the 1% low.
- Open: the only "before" run was hitchy, so how much of the jump to a ~213 FPS 1% low the
  settings bought needs a clean "before" run. Don't quote +46% as the settings' effect.
- Which of the three did the work is unknown: they were changed together.

**Frame cap:** `fps_max 200` holds the rate exactly per second but paces single frames unevenly
(a repeating 7.2 / 3.0 / 4.8 ms pattern). Frametrace reports it as "capped at ~200 FPS".

**Frametrace itself:** 512.7 FPS with Frametrace capturing vs. 515.3 without (VProf): no cost.

**High Dynamic Range and Global Shadow Quality**, one change each, measured (community,
`aggregate.py`): "Dust Benchmark" (FPSfrequency map), 89 s, bundle vs bundle, RTX 4070 Ti
SUPER, display 2560×1440 (game 1920 × 1440), 1 person. Median change A → B:
- High Dynamic Range Quality → Performance: +3.0% avg, 1% low +0.9%, CPU-side 1% low
  −0.8%, GPU busy −3.9%, PC latency −4.4%. A `20261127-214028-cs2` "Claude OFF" → B
  `20261127-214630-cs2`.
- Global Shadow Quality Medium → Low: +3.2% avg, 1% low +1.5%, CPU-side 1% low +2.6%,
  GPU busy −3.2%, PC latency −3.4%. A `20261127-214630-cs2` → B `20261127-215757-cs2`.
- Global Shadow Quality Low → Medium: −3.3% avg, 1% low −2.4%, CPU-side 1% low −3.4%,
  GPU busy +3.3%, PC latency +3.1%. A `20261127-215757-cs2` → B `20261127-220240-cs2`.
Present-to-present 1% lows are inside the 3% noise band on all three pairs. Shadow Low may
cost visibility (see Visual cost). Don't suggest Dynamic Shadows "Sun Only"; keep Boost
Player Contrast on.

<!-- frametrace:community-data (generated by tools/aggregate.py from the Frametrace dataset; don't edit by hand) -->
No community data yet. One-change comparisons by trusted contributors in the [Frametrace dataset](https://github.com/melle62/frametrace-data) appear here (median change from A to B, with the GPUs they were measured on).
<!-- /frametrace:community-data -->

## Guide costs
Two independent one-setting guides, both at 1280 × 960 on a ~980 FPS benchmark map, read
2026-11-27. A: https://github.com/9Erza/CS2-Optimization-Guide (7800X3D + RX 9070 XT, CS2
FPS Benchmark map). B: https://bo3.gg/news/high-shadows-and-msaa-smoothing-reduce-your-fps-in-cs2
(9800X3D + RTX 5070, Dust2 Benchmark map). That scene is partly CPU-bound: percentage costs
are larger when GPU-limited (as on the reference PC at 1920 × 1440). These remain guide
figures. Community one-change measurements for High Dynamic Range Quality → Performance
and Global Shadow Quality Medium ↔ Low are in Measured costs (`aggregate.py`: 3 usable
pairs, Dust Benchmark, 1 person).

| Setting | Change | A / B, average FPS |
|---|---|---|
| Global Shadow Quality | Low → Very High | −10.2% / −22% (High −4.8% / −12.9%) |
| Multisampling Anti-Aliasing Mode | None → 8X MSAA | −11.6% / −17.9% |
| Multisampling Anti-Aliasing Mode | None → 4X MSAA | −5.6% / −12.2% |
| Multisampling Anti-Aliasing Mode | None → 2X MSAA | −3.9% / −10% |
| Multisampling Anti-Aliasing Mode | None → CMAA2 | −1.1% (A only) |
| Particle Detail | Low → Very High | −9.6% / −10% |
| Particle Detail | Low → High | −4.0% / −4.8% |
| Model / Texture Detail | Low → High | −5.5% / −8.6% |
| Shader Detail | Low → High | −1.5% / −5.4% |
| Ambient Occlusion | Disabled → High | −0.8% / −4.8% |
| High Dynamic Range | Performance → Quality | −1.2% / −2.7% |
| Texture Filtering Mode | Bilinear → Anisotropic 16X | −0.9% / −1% |
| Dynamic Shadows | Sun Only → All | −0.6% / −2% |
| Boost Player Contrast | Disabled → Enabled | −0.1% (A only) |

## By goal
- **Higher average FPS** (GPU-limited, as on the reference PC): MSAA one step down while
  above 2X (8X → 4X, then 4X → 2X). At 2X already, as on the reference PC, Ambient Occlusion
  Disabled and Particle Detail Low come before CMAA2 or None; say CMAA2 or None costs
  visibility behind grates (guide A). MSAA one step, Ambient Occlusion and Particle Detail
  together measured −12% GPU time; each one alone is unmeasured. Then High Dynamic Range
  Quality → Performance (community, 1 person: +3.0% avg, −3.9% GPU busy; see Measured
  costs). Then Model / Texture Detail, Shader Detail. Then Global Shadow Quality one
  step (community, 1 person: Medium → Low +3.2% avg, −3.2% GPU busy; see Measured costs);
  visibility at Low, see above. Then resolution or FSR. Guide percentages (and these
  settings at 1280 × 960) are in Guide costs. The MSAA rows there are from None,
  not one step (one step is smaller: guide A about +1.8% and +6.8%, guide B about +2.5%
  and +7.0%). Don't touch Boost Player Contrast
  or Dynamic Shadows; keep both on. Anisotropic 16X is near free — don't cut it. When
  CPU-limited, video settings barely move it; say so rather than cutting visuals.
- **Higher 1% lows:** first check the run is clean. Two runs with the same settings came out
  hitchy (3–4% of the time in hitches, worst frames 15–20 ms) or clean (~0%); a hitchy "before"
  makes any change look great. Ask for a repeat when only one run is hitchy. Then the GPU-heavy
  changes above. Guide A, one run: Particle Detail High or Very High lowers 0.1% lows
  in heavy utility (249.3 → 229.0 / 227.9). Trilinear: see Texture Filtering above.
  Reflex Off gave the highest present-to-present lows (202 vs 154 with Boost);
  CPU-side lows moved less (205 vs 191). Don't suggest `fps_max` to even out pacing: it paces
  single frames unevenly. An external limiter is unmeasured.
- **Lower latency:** NVIDIA Reflex Enabled + Boost (measured best: median 7.25 → 6.30 ms, P95
  11.8 → 9.2 ms, for about 4% average FPS and lower present-to-present lows). V-Sync off
  (guide: 100% of pros, P3). Check the report's present mode: "Hardware: Independent Flip"
  is the direct path; "Composed" means the desktop compositor is in the way (try Fullscreen).
  Under an `fps_max` cap well below what the GPU can do, Reflex made no difference (there was
  no GPU queue to remove); whether the cap itself costs latency is unmeasured.
- **Less stutter:** separate run state from settings first (clean vs hitchy runs, above), and
  throw away the first pass after loading the map. The regular ~4 ms frames on the benchmark map
  are the local server tick, not stutter (see below). Settings changes for stutter are
  unmeasured beyond the combined change above. Trilinear: see Texture Filtering above.
- **Hit a target FPS:** the target defaults to the monitor's refresh rate. When it's met with
  room, raise visibility-relevant settings first: Global Shadow Quality, then MSAA. Keep
  Dynamic Shadows All and Boost Player Contrast on. Shadow Low → Medium costs −3.3% avg
  and +3.3% GPU busy (community, 1 person; see Measured costs). Then cheap looks:
  Anisotropic 16X, Ambient Occlusion, Shader Detail High (each 0.8–5.4% avg in guides
  A / B at 1280 × 960, more when GPU-limited). High Dynamic Range Performance → Quality
  is not measured; Quality → Performance gave +3.0% avg (community, 1 person). Then
  Particle Detail. When it isn't met, use the average-FPS order above.

## Benchmark scene
- FPSfrequency's FPS Benchmark workshop map: a fly-through of about 2 minutes. CS2 prints its own
  summary at the end (`[VProf] -- Performance report --`). Two runs lined up at a correlation of
  0.996 and measured 440.3 vs 441.2 FPS over the same 100 s.
- **Start every capture on the same cue.** Two fixed 79 s captures with identical settings,
  started by hand, measured 214.6 vs 163.6 FPS 1% lows and 2 vs 316 hitch frames. Use Manual
  length and press the hotkey on the same cue at the start and the end, and throw away the first
  run after loading the map.
- The intro and outro run at 600–1,000 FPS. A capture that skips them reads a lower average than
  VProf: compare Frametrace with Frametrace, same start, same length.
- The map runs the 64-tick server on your PC. Online the server is remote, so CPU numbers from
  the map don't carry over to matches; GPU-side settings do.

## Reading this game's reports
- Frametrace's **CPU-side 1% low** matches VProf's `FrameTotal` within 1–1.5% (209.2 / 209.8 vs
  211.0 / 212.9). The standard present-to-present 1% low reads lower (about 180), because frames
  reach the GPU less evenly than the game loop runs. When the user quotes VProf, compare it with
  the CPU-side value.
- On the benchmark map at ~500 FPS, about every 8th frame takes ~4 ms instead of ~1.5 ms: the
  local server simulation (64 ticks a second). Not a hitch, and not there online.
- PresentMon's "CPU busy" only covers CS2's render thread (about 0.7 ms per frame); VProf shows
  over 1 ms of main-thread work. Don't read CPU busy as total CPU load.
- Convars in the list that don't affect frame rate: `r_fullscreen_gamma`,
  `r_drawtracers_firstperson`, `r_show_build_info`, `r_spectator_flashbang_opacity`,
  `r_icon_image_cache_to_disk`, `fps_max_tools`.

## Not measured yet
Ordered run plan (reference PC, FPSfrequency map, 1920 × 1440, Manual capture on the same
start/end cue, throw away the first pass after loading):
- Two baseline runs with the current settings (expect no change). If one is hitchy, repeat
  until two agree.
- One change per run, back to baseline after each, in this order:
  1. Particle Detail Low → High (separates the combined −12% GPU-time change)
  2. Multisampling Anti-Aliasing Mode 2X → 4X MSAA (and 2X → CMAA2)
  3. Ambient Occlusion Disabled → High
  4. Global Shadow Quality High → Medium (and → Very High). Medium ↔ Low average and
     GPU busy are measured (community, aggregate.py; see Measured costs). Still need a
     Low-vs-Medium screenshot pair for the player-shadow-distance dispute
  5. Model / Texture Detail High → Medium
  6. Shader Detail High → Low
  7. Texture Filtering Mode Anisotropic 4X → 16X, and one Trilinear run to check guide A's
     1% low (284.7 → 266.1)
  8. FidelityFX Super Resolution Disabled → Quality. High Dynamic Range Quality →
     Performance is measured (community, aggregate.py; see Measured costs)
- An external frame limiter (driver or RTSS) vs `fps_max`.
- What makes a run hitchy (candidates: the first pass after loading the map, where the
  capture starts).
- A CPU-limited system, online matches, Vulkan, AMD and Intel GPUs, HAGS off.
- Don't test Dynamic Shadows "Sun Only" or Boost Player Contrast off as advice
  candidates; their guide cost is already known (All ≤2%, Boost ~0%).

## Sources
- Frametrace captures and VProf output on the maintainer's PC, 2026-11-26 (`docs/presentmon.md`,
  section 6).
- Community one-change pairs in the [Frametrace dataset](https://github.com/melle62/frametrace-data),
  counted by `tools/aggregate.py` (export `5edc7d2`, as of 2026-11-27): Dust Benchmark bundles
  `20261127-214028-cs2` "Claude OFF" → `20261127-214630-cs2` (HDR Quality → Performance);
  `20261127-214630-cs2` → `20261127-215757-cs2` (Global Shadow Quality Medium → Low);
  `20261127-215757-cs2` → `20261127-220240-cs2` (Low → Medium). RTX 4070 Ti SUPER, display
  2560×1440, game 1920 × 1440, 89 s, 1 person.
- Guides (claims marked "guide"), all new links read 2026-11-27:
  - A: https://github.com/9Erza/CS2-Optimization-Guide (README tables; 7800X3D + RX 9070 XT,
    1280 × 960)
  - B: https://bo3.gg/news/high-shadows-and-msaa-smoothing-reduce-your-fps-in-cs2 (9800X3D +
    RTX 5070, 1280 × 960)
  - P1: https://prosettings.net/guides/cs2-options/
  - P2: https://gamegrids.io/cs2/blog/cs2-pro-video-settings-census/
  - P3: https://spawnsy.com/en/article/cs2-pro-settings-report-2026
  - P4: https://www.psamethod.com/blog/cs2-pro-video-settings-analysis/
  - https://csdb.gg/guides/best-cs2-video-settings/,
    https://csdb.gg/guides/fps-optimization-guide/,
    https://www.hotspawn.com/counter-strike/guide/best-cs2-video-settings,
    https://game-tournaments.com/en/csgo/news/59316 (the Dynamic Shadows option).
