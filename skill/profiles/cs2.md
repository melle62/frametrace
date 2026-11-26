---
game: Counter-Strike 2
process_names: [cs2.exe]
apis: [DX11, Vulkan]
engine: Source 2
anti_cheat: VAC
last_verified: 2026-11-26
---

## Built-in benchmark
- The community "FPS Benchmark" workshop map by FPSfrequency gives a repeatable fly-through of
  about 2 minutes. All the maintainer's CS2 captures so far were made on it.
  CS2 prints its own summary at the end (`[VProf] -- Performance report --`).
- Two Frametrace runs on the same map lined up at a correlation of 0.996 and measured 440.3 vs
  441.2 FPS over the same 100 s: the map is very repeatable.
- **Start every capture at the same moment.** Two fixed 79 s captures with identical settings,
  started by hand, measured a 1% low of 214.6 and 163.6 FPS and 2 vs 316 hitch frames: they
  covered different parts of the run (or one was the first pass after loading the map). Use
  Manual length and press the hotkey on the same cue at start and end, and throw away the
  first run after loading the map.
- The run's intro and outro are light scenes at 600–1,000 FPS. A Frametrace capture that doesn't
  cover the whole run therefore reads a lower average than VProf. Compare Frametrace with
  Frametrace, started at the same moment and with the same length.

## Matching CS2's own numbers
- VProf's `FrameTotal` measures the game's frame loop. It matches Frametrace's **CPU-side**
  1% low (`MsBetweenAppStart`): 209.2 / 209.8 vs VProf 211.0 / 212.9.
- Frametrace's standard 1% low (present to present) reads lower in CS2 (about 180), because
  frames reach the GPU less evenly than the game loop runs.

## Frame-time patterns
- In the benchmark map, about every 8th frame at ~500 FPS takes ~4 ms instead of ~1.5 ms. That's
  the 64-tick server simulation running locally (VProf: `Server Simulation` runs 64 times per
  second). Online, the server runs remotely, so this pattern doesn't apply there.
- `fps_max N` holds the rate exactly per second but paces single frames unevenly (at
  `fps_max 200`: a repeating 7.2 / 3.0 / 4.8 ms pattern). Frametrace detects it as "capped".

## NVIDIA Reflex
- CS2 sends NVIDIA PC Latency markers in both Reflex modes, so Frametrace reports PC latency.
- Measured Off / Enabled / Enabled + Boost over the same 78.7 s of the benchmark (runs aligned to
  within 0.25 s; 1440p, RTX 4070 Ti Super, GPU-limited, uncapped):

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

  Each step trades a little FPS and frame-pacing evenness for lower latency, mostly in the worst
  moments (P95 −2.6 ms from Off to Boost, about 0.7 of a refresh at 280 Hz). GPU time per frame
  didn't change, so Boost's higher clocks don't matter when the GPU is already the limit. What
  changed is pacing: with Boost the game holds frames back more, so the GPU queue stays shorter
  and the GPU sits idle a little more often.
- With `fps_max` capping well below what the GPU can do, Reflex had no measurable effect: the GPU
  was idle half of each frame, so there was no queue to remove.

## Where it's limited
- At 1440p on a Ryzen 7 7800X3D + RTX 4070 Ti Super, the benchmark is GPU-limited (93–95% of
  frames, GPU busy 97.6% of the time). The CPU has headroom.
- PresentMon's "CPU busy" only covers CS2's render thread (about 0.7 ms per frame). VProf shows
  over 1 ms of main-thread work per frame (`Client Rendering`, `Client Simulation`).

## Settings file
Frametrace reads `cs2_video.txt` from `Steam\userdata\<account>\730\local\cfg\` (the newest
one when several Steam accounts have played) and lists its `setting.*` entries. From the convar
files in the same folder (`cs2_user_convars_0_slot0.vcfg`) and the install's
`cs2_machine_convars.vcfg` it adds the rendering convars: names starting with `fps_max`, `r_`,
`mat_` or `engine_low_latency`. That covers **Maximum FPS In Game** and **In Menus**; crosshair,
binds, audio and HUD convars stay out.

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
| `r_player_visibility_mode` (convar) | Boost Player Contrast | 1 = Enabled (unverified key) |
| `refreshrate_numerator` / `_denominator` | Refresh Rate | seen 0 / 0 |
| `monitor_index`, `high_dpi`, `fullscreen_min_on_focus_loss` | display options | no effect on FPS |

## Settings by goal
- **Lower latency:** Reflex Enabled + Boost cut median PC latency 7.25 → 6.30 ms and P95
  11.8 → 9.2 ms, for about 4% average FPS and lower present-to-present 1% lows (measured above).
- **Higher 1% lows (present to present):** Reflex Off gave the highest (202 vs 154 with Boost).
  The CPU-side lows moved less (205 vs 191).
- **Particle Detail High → Low, MSAA 4X → 2X, Ambient Occlusion High → Disabled** (all three at
  once; 1920 × 1440, GPU-limited, 79 s captures in a scene that isn't repeatable): GPU busy per
  frame 2.31 → 2.03 ms (−12%), average 372 → 420 FPS, 1% low 147 → 164. The 1% low stayed at 39%
  of the average and hitch time stayed around 3%, so these settings make every frame cheaper but
  don't remove spikes. One run in between showed no hitches at all (1% low 215); a repeat with the
  same settings didn't, so that run was the scene, not the settings.
- Not measured yet: each of the three on its own, shadows, shader detail, HDR, FSR, a frame cap.

## CPU-heavy settings
Not measured yet.

## GPU-heavy settings
Not measured yet.

## Sources
Frametrace captures and VProf output on the maintainer's PC, 2026-11-26 (see
`docs/presentmon.md`, section 6).
