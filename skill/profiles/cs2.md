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

## CPU-heavy settings
Not measured yet.

## GPU-heavy settings
Not measured yet.

## Sources
Frametrace captures and VProf output on the maintainer's PC, 2026-11-26 (see
`docs/presentmon.md`, section 6).
