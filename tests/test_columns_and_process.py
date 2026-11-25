"""Tests for CSV schema detection, column mapping and game auto-detection.

Header rows in fixtures/headers/ are the exact headers PresentMon 2.6.0 writes with
default options, --v2_metrics and --v1_metrics (taken from PresentMon/CsvOutput.cpp at
the v2.6.0 tag). Row values here are synthetic.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from frametrace import columns, presentmon, process
from frametrace.__main__ import main as cli_main

HEADERS = Path(__file__).parent / "fixtures" / "headers"


def header(name: str) -> list[str]:
    return (HEADERS / f"presentmon-2.6.0-{name}.csv").read_text().strip().split(",")


def make_csv(headers: list[str], rows: list[dict]) -> str:
    """Build CSV text, placing canonical values in the right columns. Others get 0."""
    cmap = columns.map_columns(headers)
    lines = [",".join(headers)]
    for row in rows:
        cells = ["0"] * len(headers)
        for name, value in row.items():
            if name in cmap.index:
                cells[cmap.index[name]] = "NA" if value is None else str(value)
        lines.append(",".join(cells))
    return "\n".join(lines) + "\n"


def frames(
    app: str, pid: int, n: int, ms: float, gpu_busy: float, start: float = 0.0, swapchain="0x1"
):
    return [
        {
            "app": app,
            "pid": pid,
            "swapchain": swapchain,
            "runtime": "DXGI",
            "present_mode": "Hardware: Independent Flip",
            "time_s": start + i * ms / 1000,
            "ms_between_presents": ms,
            "ms_frame_time": ms,
            "ms_cpu_busy": ms * 0.9,
            "ms_cpu_wait": ms * 0.1,
            "ms_gpu_busy": gpu_busy,
        }
        for i in range(n)
    ]


@pytest.mark.parametrize(
    "name,schema",
    [
        ("default", columns.Schema.V3),
        ("v2_metrics", columns.Schema.V2),
        ("v1_metrics", columns.Schema.V1),
    ],
)
def test_detect_schema(name, schema):
    assert columns.detect_schema(header(name)) is schema


def test_unknown_schema():
    assert columns.detect_schema(["foo", "bar"]) is columns.Schema.UNKNOWN


def test_capabilities_per_schema():
    v3 = columns.map_columns(header("default")).capabilities()
    v2 = columns.map_columns(header("v2_metrics")).capabilities()
    v1 = columns.map_columns(header("v1_metrics")).capabilities()
    assert all(v3.values())
    assert v2["bottleneck"] and v2["cpu_split"] and v2["display_checks"]
    assert not v2["frame_stats"]  # 2.x output has no MsBetweenPresents
    assert v1["frame_stats"] and not v1["bottleneck"] and not v1["cpu_split"]


def test_same_canonical_names_across_schemas():
    v3 = columns.map_columns(header("default"))
    v2 = columns.map_columns(header("v2_metrics"))
    assert v3.headers[v3.index["ms_frame_time"]] == "MsBetweenAppStart"
    assert v2.headers[v2.index["ms_frame_time"]] == "FrameTime"
    assert v3.headers[v3.index["ms_gpu_busy"]] == "MsGPUBusy"
    assert v2.headers[v2.index["ms_gpu_busy"]] == "GPUBusy"
    v1 = columns.map_columns(header("v1_metrics"))
    assert v1.headers[v1.index["ms_gpu_busy"]] == "msGPUActive"
    assert v1.headers[v1.index["ms_between_presents"]] == "msBetweenPresents"


def test_values_na_and_bom():
    text = "﻿" + make_csv(
        header("default"),
        [{"app": "game.exe", "pid": 7, "ms_gpu_busy": None, "ms_between_presents": 2.5}],
    )
    cmap, rows = columns.iter_frames(io.StringIO(text))
    row = next(rows)
    assert cmap.headers[0] == "Application"
    assert row["app"] == "game.exe" and row["pid"] == 7
    assert row["ms_gpu_busy"] is None
    assert row["ms_between_presents"] == 2.5


def test_truncated_last_row_is_skipped():
    text = make_csv(header("default"), frames("game.exe", 7, 3, 2.0, 1.5))
    text += "game.exe,7,0x1\n"  # capture cut off mid-row
    _, rows = columns.iter_frames(io.StringIO(text))
    assert len(list(rows)) == 3


def test_pick_foreground_game():
    rows = (
        frames("dwm.exe", 1000, 280, 3.57, 0.2)
        + frames("cs2.exe", 1234, 500, 2.0, 1.5)
        + frames("chrome.exe", 2000, 60, 16.7, 1.0)
    )
    presenters = process.summarize_presenters(rows)
    target, reason = process.pick_target(presenters, foreground_pid=1234)
    assert target.name == "cs2.exe" and reason == "foreground window process"
    assert target.avg_fps == pytest.approx(500, rel=0.01)


def test_fallback_when_foreground_window_is_a_host_process():
    # UWP/Store games: the foreground window belongs to ApplicationFrameHost.exe
    rows = frames("dwm.exe", 1000, 900, 3.57, 0.2) + frames(
        "ForzaHorizon6.exe", 4321, 300, 6.9, 6.5
    )
    presenters = process.summarize_presenters(rows)
    target, reason = process.pick_target(presenters, foreground_pid=999)
    assert target.name == "ForzaHorizon6.exe"
    assert "most frames" in reason and "999" in reason


def test_process_name_override_and_nothing_found():
    rows = frames("dwm.exe", 1000, 900, 3.57, 0.2) + frames("game.exe", 5, 100, 10, 9)
    presenters = process.summarize_presenters(rows)
    assert process.pick_target(presenters, process_name="GAME.EXE")[0].pid == 5
    assert (
        process.pick_target(process.summarize_presenters(frames("dwm.exe", 1, 900, 3.57, 0.2)))[0]
        is None
    )


def test_main_swapchain():
    rows = frames("game.exe", 5, 400, 2.5, 2.0, swapchain="0xA") + frames(
        "game.exe", 5, 50, 20, 1, swapchain="0xB"
    )
    (p,) = process.summarize_presenters(rows)
    assert p.main_swapchain == "0xA" and len(p.swapchains) == 2


def test_presentmon_commands(tmp_path):
    exe = tmp_path / "PresentMon.exe"
    cmd = presentmon.capture_command(exe, tmp_path / "out.csv", timed_s=20)
    assert cmd[0] == str(exe)
    assert "--stop_existing_session" in cmd and "--terminate_after_timed" in cmd
    assert "--process_id" not in cmd  # all processes by default
    assert cmd[cmd.index("--session_name") + 1] == presentmon.SESSION_NAME
    assert presentmon.terminate_command(exe)[-1] == "--terminate_existing_session"


def test_find_presentmon_explicit(tmp_path):
    exe = tmp_path / "PresentMon-2.6.0-x64.exe"
    exe.write_bytes(b"MZ")
    assert presentmon.find_presentmon(exe) == exe


def test_cli_inspect(tmp_path, capsys):
    csv_path = tmp_path / "capture.csv"
    csv_path.write_text(
        make_csv(header("default"), frames("game.exe", 5, 100, 4.0, 3.9)), encoding="utf-8"
    )
    assert cli_main(["inspect", str(csv_path)]) == 0
    out = capsys.readouterr().out
    assert "Schema: v3" in out and "Target: game.exe" in out


def test_identify_presentmon(tmp_path, monkeypatch):
    other = tmp_path / "PresentMon-2.7.1-x64.exe"
    other.write_bytes(b"MZ not the pinned build")
    assert presentmon.identify(other) == "2.7.1 (from file name, not verified)"
    unnamed = tmp_path / "pm.exe"
    unnamed.write_bytes(b"MZ")
    assert presentmon.identify(unnamed).startswith("unknown")
    monkeypatch.setattr(presentmon, "EXE_SHA256", hashlib.sha256(b"MZ").hexdigest())
    assert presentmon.identify(unnamed) == f"{presentmon.PINNED_VERSION} (SHA-256 verified)"
