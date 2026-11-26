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
(Ryzen 7 7800X3D, RTX 4070 Ti Super), on FPSfrequency's FPS Benchmark workshop map. Claims
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
- **Keep on:** Boost Player Contrast (guide: clearer outline of player models, near-zero cost)
  and Dynamic Shadows **All** (guide: player shadows from every light, not only the sun; they
  can show a player around a corner before the model is visible).
- **Global Shadow Quality:** guide: at Low, player shadows are drawn over a shorter distance.
  Prefer Medium over Low when cutting shadows; say it costs visibility.
- **Anti-aliasing:** less AA makes thin and distant edges shimmer. CMAA2 is the cheap option.
- **Resolution and FSR:** lower render resolution blurs distant models. Last resort.
- Ambient Occlusion, Particle Detail, HDR mode: mostly looks (unmeasured for visibility).

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

## By goal
- **Higher average FPS** (GPU-limited, as on the reference PC): MSAA one step down or CMAA2,
  Ambient Occlusion Disabled, Particle Detail Low first: together measured at −12% GPU time,
  single costs unmeasured (guide: 4X MSAA can cost 10–20%). Then Global Shadow Quality one step
  (visibility cost at Low, see above), then resolution or FSR. Don't touch Boost Player Contrast
  or Dynamic Shadows for FPS. When CPU-limited (low resolution, fast GPU), video settings barely
  move it; say so rather than cutting visuals.
- **Higher 1% lows:** first check the run is clean. Two runs with the same settings came out
  hitchy (3–4% of the time in hitches, worst frames 15–20 ms) or clean (~0%); a hitchy "before"
  makes any change look great. Ask for a repeat when only one run is hitchy. Then the GPU-heavy
  changes above. Reflex Off gave the highest present-to-present lows (202 vs 154 with Boost);
  CPU-side lows moved less (205 vs 191). Don't suggest `fps_max` to even out pacing: it paces
  single frames unevenly. An external limiter is unmeasured.
- **Lower latency:** NVIDIA Reflex Enabled + Boost (measured best: median 7.25 → 6.30 ms, P95
  11.8 → 9.2 ms, for about 4% average FPS and lower present-to-present lows). V-Sync off. Check
  the report's present mode: "Hardware: Independent Flip" is the direct path; "Composed" means
  the desktop compositor is in the way (try Fullscreen). Under an `fps_max` cap well below what
  the GPU can do, Reflex made no difference (there was no GPU queue to remove); whether the cap
  itself costs latency is unmeasured.
- **Less stutter:** separate run state from settings first (clean vs hitchy runs, above), and
  throw away the first pass after loading the map. The regular ~4 ms frames on the benchmark map
  are the local server tick, not stutter (see below). Settings changes for stutter are
  unmeasured beyond the combined change above.
- **Hit a target FPS:** the target defaults to the monitor's refresh rate. When it's met with
  room, raise visibility-relevant settings first (Global Shadow Quality, MSAA), then looks
  (Ambient Occlusion, Particle Detail). When it isn't, use the average-FPS order above.

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
- Particle Detail, MSAA and Ambient Occlusion each on its own; a clean "before" run for the
  combined change.
- Global Shadow Quality, Dynamic Shadows, Shader Detail, HDR, FSR, Texture Filtering, Boost
  Player Contrast, Model / Texture Detail.
- An external frame limiter (driver or RTSS) vs `fps_max`.
- What makes a run hitchy (candidates: the first pass after loading the map, where the capture
  starts).
- A CPU-limited system, online matches, Vulkan, AMD and Intel GPUs, HAGS off.

## Sources
- Frametrace captures and VProf output on the maintainer's PC, 2026-11-26 (`docs/presentmon.md`,
  section 6).
- Guides (claims marked "guide"): https://csdb.gg/guides/best-cs2-video-settings/,
  https://csdb.gg/guides/fps-optimization-guide/,
  https://www.hotspawn.com/counter-strike/guide/best-cs2-video-settings,
  https://game-tournaments.com/en/csgo/news/59316 (the Dynamic Shadows option).
