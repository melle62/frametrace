---
game: Counter-Strike 2
process_names: [cs2.exe]
apis: [DX11, Vulkan]
engine: Source 2
anti_cheat: VAC
last_verified: 2026-11-26
---

## Built-in benchmark
- The community "FPS Benchmark" workshop map gives a repeatable fly-through of about 2 minutes.
  CS2 prints its own summary at the end (`[VProf] -- Performance report --`).
- Two Frametrace runs on the same map lined up at a correlation of 0.996 and measured 440.3 vs
  441.2 FPS over the same 100 s: the map is very repeatable.
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
one when several Steam accounts have played) and lists its `setting.*` entries. `fps_max` and
other console variables aren't in that file, so the AI has to ask for them.

Menu names below are from the Video settings page. **Not yet checked against a real
`cs2_video.txt` on the maintainer's PC**: verify, then remove this line.

| Config key | Menu name | Values |
|---|---|---|
| `defaultres` × `defaultresheight` | Resolution | pixels |
| `fullscreen` / `nowindowborder` | Display Mode | 1 = fullscreen; 0 + borderless = fullscreen windowed |
| `mat_vsync` | Wait for Vertical Sync | 0 off, 1 on |
| `msaa_samples` | Multisample Anti-Aliasing Mode | 0 none, 2, 4, 8 |
| `r_csgo_cmaa_enable` | Multisample Anti-Aliasing Mode: CMAA2 | 1 when CMAA2 is chosen |
| `videocfg_shadow_quality` | Global Shadow Quality | 0 low … 3 very high |
| `videocfg_dynamic_shadows` | Dynamic Shadows | 0 sun only, 1 all |
| `videocfg_texture_detail` | Model / Texture Detail | 0 low … 2 high |
| `r_texturefilteringquality` | Texture Filtering Mode | 0 bilinear … 5 anisotropic 16x |
| `shaderquality` | Shader Detail | 0 low, 1 high |
| `videocfg_particle_detail` | Particle Detail | 0 low … 2 high |
| `videocfg_ao_detail` | Ambient Occlusion | 0 disabled … 3 high |
| `videocfg_hdr_detail` | High Dynamic Range | 3 performance, -1 quality |
| `videocfg_fsr_detail` | FidelityFX Super Resolution | 0 disabled, 1 ultra quality … 4 performance |
| `r_low_latency` | NVIDIA Reflex Low Latency | 0 disabled, 1 enabled, 2 enabled + boost |

## Settings by goal
- **Lower latency:** Reflex Enabled + Boost cut median PC latency 7.25 → 6.30 ms and P95
  11.8 → 9.2 ms, for about 4% average FPS and lower present-to-present 1% lows (measured above).
- **Higher 1% lows (present to present):** Reflex Off gave the highest (202 vs 154 with Boost).
  The CPU-side lows moved less (205 vs 191).
- Not measured yet: shadow, MSAA and FSR costs on the benchmark map.

## CPU-heavy settings
Not measured yet.

## GPU-heavy settings
Not measured yet.

## Sources
Frametrace captures and VProf output on the maintainer's PC, 2026-11-26 (see
`docs/presentmon.md`, section 6).
