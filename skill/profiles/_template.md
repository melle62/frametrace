---
game: Example Game
process_names: [examplegame.exe]
apis: [DX11, DX12]
engine: Unknown
anti_cheat: none
last_verified: YYYY-MM-DD
---

## Built-in benchmark
How to run a repeatable test (benchmark mode, workshop map, replay, fixed route).

## Settings file
Where the game keeps its graphics settings, if Frametrace reads them (Unreal
GameUserSettings.ini, Unity PlayerPrefs, Source 2 video config), and a table of config key →
name in the game's menu → what the values mean. The AI uses it to turn the report's
"Current in-game settings" into menu advice.

| Config key | Menu name | Values |
|---|---|---|
| `example_shadow_quality` | Shadow Quality | 0 low … 3 ultra |

## CPU-heavy settings
Settings whose cost scales with CPU load (draw distance, crowd density, physics, simulation rate).

## GPU-heavy settings
Settings whose cost scales with GPU load (resolution, upscaler, shadows, ray tracing, AA).

## Settings by goal
Measured or well-known effects, per goal: higher average FPS, higher 1% lows, lower latency,
less stutter, best quality at a target FPS. Mark anything not measured.

## Known quirks
FPS caps, launch options, console commands, frame-generation behaviour, known stutter sources.

## Sources
Links or Frametrace reports backing the claims above.
