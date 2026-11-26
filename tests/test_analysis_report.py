"""Tests for analysis, checks, report rendering, compare, sysinfo helpers, hotkeys and the recorder."""

from __future__ import annotations

import json
import random
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from frametrace import analyze, capture, hotkey, process, report, sysinfo


def make_rows(
    n=3000,
    ft=2.0,
    gpu_frac=(0.5, 0.7),
    cpu_wait_frac=0.05,
    jitter=0.1,
    sync=0,
    seed=1,
    mode="Hardware: Independent Flip",
    spikes_every=0,
):
    rnd = random.Random(seed)
    rows, t = [], 0.0
    for i in range(n):
        f = max(0.1, rnd.gauss(ft, ft * jitter))
        if spikes_every and i and i % spikes_every == 0:
            f = ft * 6
        g = f * rnd.uniform(*gpu_frac)
        rows.append(
            {
                "app": "game.exe",
                "pid": 7,
                "swapchain": "0x1",
                "runtime": "DXGI",
                "present_mode": mode,
                "allows_tearing": 1,
                "sync_interval": sync,
                "time_s": t,
                "ms_between_presents": f,
                "ms_frame_time": f,
                "ms_cpu_busy": f * (1 - cpu_wait_frac),
                "ms_cpu_wait": f * cpu_wait_frac,
                "ms_gpu_busy": g,
                "ms_between_display_change": f,
            }
        )
        t += f / 1000
    return rows


def fake_system(**overrides) -> sysinfo.SystemInfo:
    si = sysinfo.SystemInfo()
    sysinfo.apply_hardware(
        si,
        {
            "os": {"Caption": "Microsoft Windows 11 Pro"},
            "cpu": {
                "Name": "AMD Ryzen 7 7800X3D 8-Core Processor",
                "NumberOfCores": 8,
                "NumberOfLogicalProcessors": 16,
            },
            "gpu": {
                "Name": "NVIDIA GeForce RTX 4070 Ti SUPER",
                "DriverVersion": "32.0.15.8180",
                "AdapterCompatibility": "NVIDIA",
            },
            "ram": [
                {
                    "Capacity": 17179869184,
                    "Speed": 4800,
                    "ConfiguredClockSpeed": 6000,
                    "SMBIOSMemoryType": 34,
                    "PartNumber": "F5-6000J3038F16G",
                }
            ]
            * 2,
            "board": {
                "Manufacturer": "ASUSTeK COMPUTER INC.",
                "Product": "TUF GAMING B650-PLUS WIFI",
            },
            "bios": {"SMBIOSBIOSVersion": "3287", "ReleaseDate": "2025-08-12"},
            "vbs_services": [0],
        },
    )
    si.power_plan, si.game_mode, si.hags = "Balanced", True, False
    si.displays = [sysinfo.Display("Monitor", 2560, 1440, 280, 280, True)]
    for k, v in overrides.items():
        setattr(si, k, v)
    return si


def result_for(rows, **sys_overrides) -> dict:
    a = analyze.analyze(rows, "game.exe", 7)
    return report.build_result(
        a, fake_system(**sys_overrides), {"reason": "test", "started": "2026-11-26T20:00:00+01:00"}
    )


def levels(result) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in result["checks"]:
        out.setdefault(c["level"], []).append(c["text"])
    return out


# --- analysis --------------------------------------------------------------------------------


def test_quantile_matches_numpy_linear():
    assert analyze.quantile([1, 2, 3, 4], 0.5) == 2.5
    assert analyze.quantile([10.0], 0.99) == 10.0


def test_frame_stats_basics():
    rows = make_rows(n=5000, ft=4.0, jitter=0.0, spikes_every=500)
    s = analyze.frame_stats(rows)
    assert s.frames == 4999  # first frame skipped
    assert s.median_ms == pytest.approx(4.0)
    assert s.spikes == 9 and s.max_ms == pytest.approx(24.0)
    assert s.p01_fps < s.avg_fps  # 0.1% low catches the spikes; P1 (0.18% spikes) does not
    assert s.worst_1s_fps is not None and s.worst_1s_fps < 250
    assert s.worst_spikes[0][0] == pytest.approx(24.0)


@pytest.mark.parametrize(
    "gpu_frac,cpu_wait,sync,expected",
    [
        ((0.95, 0.99), 0.02, 0, "GPU-limited"),
        ((0.4, 0.6), 0.02, 0, "CPU-limited"),
        # blocked in Present with VSync off: the GPU queue is full -> GPU-limited
        ((0.4, 0.6), 0.4, 0, "GPU-limited"),
        # blocked in Present with VSync on: waiting for the display
        ((0.4, 0.6), 0.4, 1, "waiting"),
    ],
)
def test_bottleneck_verdicts(gpu_frac, cpu_wait, sync, expected):
    rows = make_rows(gpu_frac=gpu_frac, cpu_wait_frac=cpu_wait, jitter=0.2, sync=sync)
    b = analyze.analyze(rows, "g", 1).bottleneck
    assert b.available and expected in b.verdict
    assert b.gpu_fps_ceiling and b.cpu_fps_ceiling is None  # no CPU ceiling: see analyze.py


def test_first_second_is_skipped():
    rows = make_rows(n=3000, ft=2.0, jitter=0.0)
    rows[10]["ms_between_presents"] = 33.0  # start-up hitch
    a = analyze.analyze(rows, "g", 1)
    assert a.skipped_start_s == 1.0 and a.stats.max_ms == pytest.approx(2.0)
    assert analyze.analyze(rows, "g", 1, skip_start_s=0).stats.max_ms == pytest.approx(33.0)
    assert "first 1 s skipped" in report.render(report.build_result(a, sysinfo.SystemInfo(), {}))


def test_cap_detected_when_frame_times_are_uniform():
    b = analyze.analyze(
        make_rows(ft=1000 / 237, jitter=0.01, gpu_frac=(0.3, 0.4)), "g", 1
    ).bottleneck
    assert b.cap_fps == pytest.approx(237, rel=0.02)
    assert b.verdict.startswith("capped")


def test_no_gpu_data_means_no_bottleneck():
    rows = make_rows()
    for r in rows:
        r["ms_gpu_busy"] = None
    b = analyze.analyze(rows, "g", 1).bottleneck
    assert not b.available and b.notes


def test_display_dropped_and_vsync():
    rows = make_rows(sync=1)
    for r in rows[::10]:
        r["ms_between_display_change"] = None
    d = analyze.display_info(rows)
    assert d.vsync is True and d.dropped_pct == pytest.approx(10, abs=0.1)


# --- checks and report -----------------------------------------------------------------------


def test_checks_catch_expo_off_single_channel_low_refresh():
    r = result_for(
        make_rows(),
        ram_running_mts=4800,
        ram_modules=1,
        displays=[sysinfo.Display("Monitor", 2560, 1440, 60, 280, True)],
        power_plan="Power saver",
    )
    warns = " ".join(levels(r)["warn"])
    assert "rated 6000" in warns and "EXPO/XMP" in warns
    assert "single-channel" in warns
    assert "60 Hz but supports 280 Hz" in warns
    assert "Power saver" in warns


def test_checks_ok_system_and_composed_present_mode():
    r = result_for(make_rows(mode="Composed: Flip"), windowed_optimizations=False)
    lv = levels(r)
    assert any("RAM runs at 6000" in t for t in lv["ok"])
    assert any("desktop compositor" in t and "windowed games" in t for t in lv["warn"])


def test_render_has_all_sections_and_is_json_safe():
    r = json.loads(json.dumps(result_for(make_rows())))
    text = report.render(r)
    for heading in (
        "Frametrace report",
        "## Performance",
        "## Bottleneck",
        "## Display path",
        "## System",
        "## Checks",
    ):
        assert heading in text
    assert "RTX 4070 Ti SUPER, driver 581.80" in text
    assert "kit rated 6000" in text


def test_render_without_system_info():
    a = analyze.analyze(make_rows(), "g.exe", 1)
    text = report.render(report.build_result(a, sysinfo.SystemInfo(), {}))
    assert "(system info not available)" in text


def test_compare_changes_and_system_diff():
    before = result_for(make_rows(ft=2.2), ram_running_mts=4800)
    after = result_for(make_rows(ft=2.0))
    text = report.compare(before, after)
    assert "| Average FPS |" in text and "+10." in text  # 2.2 ms -> 2.0 ms is about +10% FPS
    assert "RAM speed: 4800 -> 6000" in text


# --- sysinfo helpers -------------------------------------------------------------------------


def test_sysinfo_helpers():
    assert sysinfo.nvidia_driver_version("32.0.15.8180") == "581.80"
    assert sysinfo.nvidia_driver_version(None) is None
    assert sysinfo.kit_speed_from_part("F5-6000J3038F16G", "DDR5") == 6000
    assert sysinfo.kit_speed_from_part("CMK32GX5M2B5600C36", "DDR5") == 5600
    assert sysinfo.kit_speed_from_part("KF560C36-16", "DDR5") is None
    assert sysinfo.normalize_mts(2400, "DDR5") == 4800
    assert sysinfo.normalize_mts(1600, "DDR4") == 3200
    assert sysinfo.normalize_mts(6000, "DDR5") == 6000
    assert (
        sysinfo.max_refresh([(2560, 1440, 60), (2560, 1440, 280), (1920, 1080, 360)], 2560, 1440)
        == 280
    )


@pytest.mark.parametrize(
    "out,expected",
    [
        ("Power Scheme GUID: 381b4222-f694-41f0-9685-ff5bb260df2e  (Balanced)", "Balanced"),
        (
            "Energischema-GUID: 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c  (Höga prestanda)",
            "Höga prestanda",
        ),
        ("GUID e9a42b02-d5df-448d-aa00-03f14749eb61", "Ultimate Performance"),
        ("nothing", None),
    ],
)
def test_parse_powercfg(out, expected):
    assert sysinfo.parse_powercfg(out) == expected


def test_placeholder_part_number_is_ignored():
    si = sysinfo.SystemInfo()
    sysinfo.apply_hardware(si, {"ram": [{"Capacity": 8589934592, "PartNumber": "None"}]})
    assert si.ram_part is None and si.ram_total_gb == 8.0


def test_main_gpu_prefers_discrete():
    si = sysinfo.SystemInfo(
        gpus=[
            sysinfo.Gpu("AMD Radeon(TM) Graphics"),
            sysinfo.Gpu("NVIDIA GeForce RTX 4070 Ti SUPER"),
        ]
    )
    assert "RTX" in si.main_gpu.name


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_collect_on_windows():
    info = sysinfo.collect()
    assert info.cpu and info.os_build
    assert isinstance(info.displays, list)


# --- hotkeys ---------------------------------------------------------------------------------


def test_parse_hotkey():
    assert hotkey.parse_hotkey("F10") == (0, 0x79)
    assert hotkey.parse_hotkey("ctrl + shift + f9") == (0x2 | 0x4, 0x78)
    assert hotkey.parse_hotkey("ScrollLock") == (0, 0x91)
    for bad in ("", "F99", "Hyper+F1", "F12"):
        with pytest.raises(ValueError):
            hotkey.parse_hotkey(bad)


# --- recorder with a fake PresentMon ---------------------------------------------------------

FAKE_PRESENTMON = """\
import sys, time
from pathlib import Path
args = sys.argv[1:]
stop = Path(__file__).with_name("stop")
if "--terminate_existing_session" in args:
    stop.write_text("x"); sys.exit(0)
out = Path(args[args.index("--output_file") + 1])
stop.unlink(missing_ok=True)
header = "Application,ProcessID,SwapChainAddress,PresentRuntime,SyncInterval,PresentFlags,AllowsTearing,PresentMode,TimeInMs,MsBetweenPresents,MsBetweenDisplayChange,MsBetweenAppStart,MsCPUBusy,MsCPUWait,MsGPUBusy"
t = {"game.exe": 0.0, "dwm.exe": 0.0}
with open(out, "w", encoding="utf-8-sig") as f:
    f.write(header + "\\n")
    while not stop.exists():
        for app, pid, ft, gpu in (("game.exe", 42, 4.0, 3.9), ("dwm.exe", 9, 7.0, 0.2)):
            for _ in range(10):
                t[app] += ft
                f.write(f"{app},{pid},0x1,DXGI,0,0,1,Hardware: Independent Flip,{t[app]:.3f},{ft},{ft},{ft},{ft*0.9},{ft*0.1},{gpu}\\n")
        f.flush()
        time.sleep(0.02)
"""


@pytest.mark.skipif(sys.platform == "win32", reason="the fake PresentMon is a POSIX script")
def test_recorder_end_to_end(tmp_path, monkeypatch):
    exe = tmp_path / "fake_presentmon"
    exe.write_text(f"#!{sys.executable}\n" + FAKE_PRESENTMON)
    exe.chmod(0o755)
    monkeypatch.setattr(
        process,
        "get_foreground_process",
        lambda: process.ForegroundProcess(42, "/games/game.exe", "Game"),
    )
    events: list[tuple[str, dict]] = []
    done = threading.Event()

    def on_event(kind, payload):
        events.append((kind, payload))
        if kind in ("done", "error"):
            done.set()

    rec = capture.Recorder(exe, on_event, root=tmp_path / "captures", system_provider=fake_system)
    rec.start(capture.CaptureSettings(length_s=1))
    assert rec.state == "recording"
    assert done.wait(20), events
    kinds = [k for k, _ in events]
    assert kinds == ["started", "stopping", "done"], events
    payload = events[-1][1]
    folder: Path = payload["folder"]
    assert folder.name.endswith("-game")
    assert (folder / "result.json").is_file() and (folder / "report.md").is_file()
    result = payload["result"]
    assert result["capture"]["app"] == "game.exe"
    assert result["capture"]["reason"] == "foreground window process"
    assert result["analysis"]["stats"]["avg_fps"] == pytest.approx(250, rel=0.02)
    assert "GPU-limited" in result["analysis"]["bottleneck"]["verdict"]
    assert capture.list_captures(tmp_path / "captures")[0][0] == folder
    assert rec.state == "idle"


def test_fake_presentmon_source_is_valid_python():
    compile(textwrap.dedent(FAKE_PRESENTMON), "fake", "exec")


def test_heavy_scene_is_not_a_hitch_but_a_lone_long_frame_is():
    rows = make_rows(n=1500, ft=2.0, jitter=0.0) + make_rows(n=1500, ft=6.0, jitter=0.0, seed=2)
    t = 0.0
    for r in rows:  # continuous time axis across the two scenes
        r["time_s"] = t
        t += r["ms_between_presents"] / 1000
    assert analyze.frame_stats(rows).spikes == 0  # 6 ms frames are a heavier scene, not stutter
    rows[2000]["ms_between_presents"] = 20.0
    s = analyze.frame_stats(rows)
    assert s.spikes == 1 and s.worst_spikes[0][0] == 20.0


def test_cpu_side_lows_use_frame_start_intervals():
    rows = make_rows(n=2000, ft=2.0, jitter=0.0)
    for r in rows[::50]:
        r["ms_between_presents"] = 5.0  # present pacing jitter only
    s = analyze.frame_stats(rows)
    assert s.p1_fps == pytest.approx(200, rel=0.01)
    assert s.cpu_p1_fps == pytest.approx(500, rel=0.01)


def _pattern_rows(seconds=30, pattern=(7.2, 3.0, 4.8), gpu=0.5, seed=3):
    """An in-game limiter like CS2's fps_max: exact rate per second, uneven frames."""
    rnd = random.Random(seed)
    rows, t, i = [], 0.0, 0
    while t < seconds:
        f = pattern[i % len(pattern)] * rnd.uniform(0.97, 1.03)
        rows.append(
            {
                "app": "game.exe",
                "pid": 7,
                "swapchain": "0x1",
                "runtime": "DXGI",
                "present_mode": "Hardware: Independent Flip",
                "allows_tearing": 1,
                "sync_interval": 0,
                "time_s": t,
                "ms_between_presents": f,
                "ms_frame_time": f,
                "ms_cpu_busy": f * 0.99,
                "ms_cpu_wait": f * 0.01,
                "ms_gpu_busy": 5.0 * gpu,
                "ms_between_display_change": f,
            }
        )
        t += f / 1000
        i += 1
    return rows


def test_in_game_cap_with_uneven_frames_is_detected():
    a = analyze.analyze(_pattern_rows(), "game.exe", 7)
    b = a.bottleneck
    assert b.cap_fps == pytest.approx(200, rel=0.02)
    assert b.verdict.startswith("capped at ~200")
    assert b.cpu_pct == 0 and b.wait_pct > 80  # limiter sleep isn't a CPU limit
    assert a.stats.p95_ms / a.stats.p5_ms > 2  # the old frame-uniformity rule alone missed this


def test_steady_free_running_cpu_limit_is_not_a_cap():
    rows = make_rows(n=15000, ft=2.0, jitter=0.2, gpu_frac=(0.4, 0.6))  # 30 s, ~500 FPS
    b = analyze.analyze(rows, "g", 1).bottleneck
    assert b.cap_fps is None and "CPU-limited" in b.verdict


def test_gpu_bound_steady_scene_is_not_a_cap():
    rows = make_rows(n=15000, ft=2.0, jitter=0.02, gpu_frac=(0.95, 0.99))
    b = analyze.analyze(rows, "g", 1).bottleneck
    assert b.cap_fps is None and "GPU-limited" in b.verdict


def test_pc_latency_from_reflex_markers():
    rows = make_rows(n=2000)
    for i, r in enumerate(rows):
        r["ms_pc_latency"] = 8.0 + (i % 10) * 0.2 if i % 2 else None  # markers on some frames
    a = analyze.analyze(rows, "g", 1)
    assert a.display.pc_latency_ms == pytest.approx(8.9, abs=0.2)
    text = report.render(report.build_result(a, sysinfo.SystemInfo(), {}))
    assert "PC latency (NVIDIA Reflex markers" in text
    before = report.build_result(a, sysinfo.SystemInfo(), {})
    assert "PC latency, median" in report.compare(before, before)
