"""Goals, game identification and in-game settings readers (no Windows needed)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_analysis_report import make_rows, result_for

from frametrace import analyze, game, gamesettings, goals, report, summary, sysinfo

CS2_VIDEO = """"video.cfg"
{
	"Version"		"14"
	"VendorID"		"4318"
	"setting.cpu_level"		"3"
	"setting.gpu_level"		"3"
	"setting.gpu_mem_level"		"3"
	"setting.defaultres"		"2560"
	"setting.defaultresheight"		"1440"
	"setting.msaa_samples"		"4"
	"setting.videocfg_shadow_quality"		"2"
	"setting.r_low_latency"		"1"
	"AutoConfig"		"2"
}
"""


def steam_library(tmp: Path) -> Path:
    """A Steam library with CS2 installed and its manifest; returns the exe path."""
    apps = tmp / "lib" / "steamapps"
    exe = apps / "common" / "Counter-Strike Global Offensive" / "game" / "bin" / "win64" / "cs2.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")
    (exe.parent / "engine2.dll").write_bytes(b"")
    (apps / "appmanifest_730.acf").write_text(
        '"AppState"\n{\n\t"appid"\t\t"730"\n\t"name"\t\t"Counter-Strike 2"\n'
        '\t"buildid"\t\t"20864571"\n\t"installdir"\t\t"Counter-Strike Global Offensive"\n}\n',
        encoding="utf-8",
    )
    (apps / "appmanifest_1.acf").write_text('"AppState" { "installdir" "Other" }', encoding="utf-8")
    return exe


# --- goals -----------------------------------------------------------------------------------


def test_goal_lookup_and_defaults():
    assert goals.get(None).key == goals.DEFAULT_GOAL
    assert goals.get("nope").key == goals.DEFAULT_GOAL
    r = result_for(make_rows())
    assert goals.from_result(r)[0].key == goals.DEFAULT_GOAL
    assert goals.default_target(r) == 280  # the primary display's refresh rate


def test_target_status_and_seconds():
    stats = {"p1_fps": 150.0, "avg_fps": 200.0, "second_fps": [200.0] * 9 + [140.0]}
    assert goals.seconds_at_target_pct(stats, 144) == 90
    assert goals.target_status(stats, 144) == "met"
    assert goals.target_status(stats, 120) == "above"
    assert goals.target_status(stats, 180) == "close"
    assert goals.target_status(stats, 240) == "short"


def test_second_fps_is_saved():
    r = result_for(make_rows(n=8000))
    secs = r["analysis"]["stats"]["second_fps"]
    assert len(secs) >= 10 and all(450 < x < 550 for x in secs)


@pytest.mark.parametrize("key", list(goals.GOALS))
def test_every_goal_renders_a_prompt(key):
    r = json.loads(json.dumps(result_for(make_rows(n=8000))))
    text = report.render(r, key)
    goal = goals.GOALS[key]
    assert f"Goal: {goal.label}" in text
    assert "## Task for the AI" in text and "Recommend which in-game settings" in text
    assert "ask me" in text  # settings weren't read: the AI must ask for them
    assert "one short text block" in text and "    NEXT  1  <menu name>" in text
    assert text.index("    NEXT  1") < text.index("Skill:")  # the skill line stays last
    if key == "target":
        assert "Target 280 FPS" in text  # defaults to the refresh rate


def test_goal_saved_with_capture_is_used():
    a = report.build_result(
        analyze.analyze(make_rows(n=8000), "g.exe", 1),
        sysinfo.SystemInfo(),
        {},
        goal={"key": "target", "target_fps": 144},
    )
    text = report.render(a)
    assert "Goal: Hit a target FPS (144 FPS)" in text
    assert "met with room to spare" in text  # ~500 FPS against 144
    assert "Goal: Higher 1% lows" in report.render(a, "lows")  # the window's goal wins


def test_compare_lists_settings_changes_and_asks_for_next_step():
    a = result_for(make_rows(n=8000, ft=2.2))
    b = result_for(make_rows(n=8000, ft=2.0, seed=3))
    a["game_settings"] = {"reader": "x", "source": "y", "settings": [["shadows", "2"], ["aa", "4"]]}
    b["game_settings"] = {"reader": "x", "source": "y", "settings": [["shadows", "0"], ["aa", "4"]]}
    assert summary.settings_changes(a, b) == [("shadows", "2", "0")]
    text = report.compare(a, b, "avg_fps")
    assert "B is better for a higher average FPS." in text
    assert "- shadows: 2 -> 0" in text
    assert "Recommend the next 1-3 settings" in text
    assert "(the base)" in text and "      vs BASE  <metric>" in text
    b["game_settings"] = None
    assert summary.settings_changes(a, b) is None
    assert "ask me what I changed" in report.compare(a, b)


def test_goal_verdict_lows_and_target():
    a = result_for(make_rows(n=8000, ft=2.2))
    b = result_for(make_rows(n=8000, ft=2.0, seed=3))
    status, decide = summary.goal_status(a, b, goals.get("lows"), None)
    assert status == "better" and decide[0].label == "1% low"
    status, decide = summary.goal_status(a, b, goals.get("target"), 480)
    assert status == "better" and decide[0].label == "Seconds at 480 FPS"
    head, _ = summary.goal_verdict(b, goals.get("target"), 480)
    assert head.startswith("Target 480 FPS")


# --- game identification ---------------------------------------------------------------------


def test_parse_keyvalues_nested_and_comments():
    kv = game.parse_keyvalues('"A" { // note\n "b" "1" "C" { "d" "two words" } }')
    assert kv == {"A": {"b": "1", "C": {"d": "two words"}}}


def test_identify_steam_game(tmp_path):
    exe = steam_library(tmp_path)
    info = game.identify("cs2.exe", str(exe))
    assert info.name == "Counter-Strike 2" and info.name_source == "steam"
    assert (info.store, info.store_id, info.build) == ("Steam", "730", "20864571")
    assert info.engine == "Source 2"
    assert info.install_dir.endswith("Counter-Strike Global Offensive")


def test_identify_falls_back_to_window_title_and_exe():
    assert game.identify("x.exe", None, "Cool Game").name == "Cool Game"
    info = game.identify("x.exe", None)
    assert info.name is None and info.display_name == "x"


def test_unreal_and_unity_detection(tmp_path):
    ue = tmp_path / "Hogwarts" / "Phoenix" / "Binaries" / "Win64" / "HogwartsLegacy.exe"
    ue.parent.mkdir(parents=True)
    ue.write_bytes(b"")
    assert game.detect_engine(str(ue)) == "Unreal Engine"
    assert game.unreal_project(str(ue)) == "Phoenix"
    assert game.unreal_project("C:/x/Foo-Win64-Shipping.exe") == "Foo"
    un = tmp_path / "U" / "Game.exe"
    (tmp_path / "U" / "Game_Data").mkdir(parents=True)
    un.write_bytes(b"")
    assert game.detect_engine(str(un)) == "Unity"


# --- in-game settings ------------------------------------------------------------------------


def test_source2_video_config_from_userdata(tmp_path):
    exe = steam_library(tmp_path)
    steam = tmp_path / "Steam"
    cfg = steam / "userdata" / "123456789" / "730" / "local" / "cfg"
    cfg.mkdir(parents=True)
    (cfg / "cs2_video.txt").write_text(CS2_VIDEO, encoding="utf-8")
    info = game.identify("cs2.exe", str(exe))
    found = gamesettings.read_source2(info, steam)
    assert found and found.reader == "Source 2 video config"
    assert ("videocfg_shadow_quality", "2") in found.settings
    keys = [k for k, _ in found.settings]
    assert "VendorID" not in keys and "AutoConfig" not in keys and "Version" not in keys
    assert not {"cpu_level", "gpu_level", "gpu_mem_level"} & set(keys)  # auto-detected levels
    assert "123456789" not in found.source and "<account>" in found.source  # no Steam ID


def test_unreal_game_user_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    ini = tmp_path / "local" / "Phoenix" / "Saved" / "Config" / "Windows" / "GameUserSettings.ini"
    ini.parent.mkdir(parents=True)
    ini.write_text(
        "[/Script/Engine.GameUserSettings]\n"
        "sg.ShadowQuality=3\nsg.ViewDistanceQuality=2\nbUseVSync=False\nFrameRateLimit=0.000000\n"
        "LastConfirmedFullscreenMode=1\nVersion=5\nWindowPosX=-1\n"
        "[/Script/Phoenix.PhoenixGameUserSettings]\nUpscaleType=2\nUserName=melvin\n"
        "AuthToken=abc\nSomeStruct=(X=1,Y=2)\n",
        encoding="utf-8",
    )
    exe = tmp_path / "Hogwarts" / "Phoenix" / "Binaries" / "Win64" / "HogwartsLegacy.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    info = game.identify("HogwartsLegacy.exe", str(exe))
    found = gamesettings.read(info)
    assert found and found.reader.startswith("Unreal")
    assert found.settings == [
        ("sg.ShadowQuality", "3"),
        ("sg.ViewDistanceQuality", "2"),
        ("bUseVSync", "False"),
        ("FrameRateLimit", "0.000000"),
        ("PhoenixGameUserSettings.UpscaleType", "2"),
    ]


def test_privacy_filter():
    for key, value in (
        ("PlayerName", "x"),
        ("steam_id", "1"),
        ("LastUser", "x"),
        ("email", "a"),
        ("Path", r"C:\Users\melvin"),
        ("blob", "x" * 100),
    ):
        assert not gamesettings.keep(key, value), key
    assert gamesettings.keep("videocfg_shadow_quality", "2")
    assert gamesettings.keep("GuideLines", "1")


def test_no_reader_means_none():
    assert gamesettings.read(game.GameInfo(exe="x.exe")) is None


def test_game_sections_for_the_game_tab():
    r = result_for(make_rows())
    r["game"] = game.GameInfo(exe="g.exe", name="G", engine="Unity").to_dict()
    secs = dict(summary.game_sections(r))
    assert ("Game", "G") in secs["Captured game"]
    assert secs["In-game settings"][0][0] == ""  # the "not read" note


def test_fixed_version_from_numeric_block():
    """Games without version strings still have VS_FIXEDFILEINFO; parse it like Windows does."""
    import ctypes
    import struct

    block = ctypes.create_string_buffer(
        struct.pack(
            "<6I", 0xFEEF04BD, 0x10000, (1 << 16) | 41, (1 << 16) | 6, (1 << 16) | 41, (1 << 16) | 6
        )
    )

    class FakeVersionDll:
        def VerQueryValueW(self, buf, sub, ptr, length):
            assert sub == "\\"
            ptr._obj.value = ctypes.addressof(block)
            length._obj.value = len(block.raw)
            return 1

    assert game._fixed_version(FakeVersionDll(), None) == "1.41.1.6"
    zero = ctypes.create_string_buffer(struct.pack("<6I", 0xFEEF04BD, 0, 0, 0, 0, 0))
    block = zero
    assert game._fixed_version(FakeVersionDll(), None) is None


def test_stutter_is_a_capture_note_not_a_fix():
    r = result_for(make_rows(n=8000))
    r["checks"].append({"level": "warn", "text": "Stutter: 3.7% of the time was spent in hitches."})
    text = report.render(r)
    fix = text.split("## Fix first (outside the game)")[1].split("##")[0]
    notes = text.split("## Capture notes")[1].split("##")[0]
    assert "Stutter" in notes and "Stutter" not in fix  # old captures without a kind, too
    assert "Frame generation" in notes and "RAM runs at" in fix
    kinds = {c["text"].split(" ")[0]: c["kind"] for c in r["checks"] if "kind" in c}
    assert kinds["RAM"] == "system" and kinds["Frame"] == "capture"
    a, b = r, result_for(make_rows(n=8000))
    assert "Stutter" not in report.compare(b, a).split("Fix first, flagged")[-1]


CS2_CONVARS = """"config"
{
	"convars"
	{
		"cl_crosshairsize"		"2.000000"
		"fps_max"		"400.000000"
		"fps_max_ui$2"		"120.000000"
		"r_player_visibility_mode"		"1"
		"r_low_latency"		"2"
		"sensitivity"		"1.250000"
		"name"		"melvin"
	}
}
"""


def test_source2_reads_rendering_convars_next_to_the_video_config(tmp_path):
    exe = steam_library(tmp_path)
    cfg = tmp_path / "Steam" / "userdata" / "42" / "730" / "local" / "cfg"
    cfg.mkdir(parents=True)
    (cfg / "cs2_video.txt").write_text(CS2_VIDEO, encoding="utf-8")
    (cfg / "cs2_user_convars_0_slot0.vcfg").write_text(CS2_CONVARS, encoding="utf-8")
    found = gamesettings.read_source2(game.identify("cs2.exe", str(exe)), tmp_path / "Steam")
    d = dict(found.settings)
    assert d["fps_max"] == "400" and d["fps_max_ui"] == "120"  # $2 slot suffix dropped
    assert d["r_player_visibility_mode"] == "1"
    assert d["r_low_latency"] == "1"  # the video config's value; convars don't duplicate it
    assert not {"cl_crosshairsize", "sensitivity", "name"} & set(d)  # not rendering, or private
    assert found.reader == "Source 2 video config and convars"
    assert "cs2_user_convars_0_slot0.vcfg" in found.source


def test_source2_shipped_defaults_never_override_the_user(tmp_path):
    import os
    import time

    exe = steam_library(tmp_path)
    cfg = tmp_path / "Steam" / "userdata" / "42" / "730" / "local" / "cfg"
    cfg.mkdir(parents=True)
    (cfg / "cs2_video.txt").write_text(CS2_VIDEO, encoding="utf-8")
    user = cfg / "cs2_user_convars_0_slot0.vcfg"
    user.write_text(CS2_CONVARS.replace('"400.000000"', '"0"'), encoding="utf-8")  # no cap
    shipped = exe.parents[2] / "csgo" / "cfg" / "machine_convars_default.vcfg"
    shipped.parent.mkdir(parents=True)
    shipped.write_text('"config" { "convars" { "fps_max" "400" } }', encoding="utf-8")
    later = time.time() + 60  # a game update just rewrote the defaults
    os.utime(shipped, (later, later))
    found = gamesettings.read_source2(game.identify("cs2.exe", str(exe)), tmp_path / "Steam")
    assert dict(found.settings)["fps_max"] == "0"  # the user's value, not the newer default
    assert "machine_convars_default" not in found.source


def _with_settings(r, pairs, reader="x"):
    r["game_settings"] = {"reader": reader, "source": "y", "settings": [list(p) for p in pairs]}
    return r


def test_same_settings_but_results_moved_is_flagged():
    a = _with_settings(result_for(make_rows(n=8000, ft=2.2)), [("aa", "2")])
    b = _with_settings(result_for(make_rows(n=8000, ft=2.0, seed=3)), [("aa", "2")])
    assert summary.settings_changes(a, b) == []
    assert summary.settings_unchanged_but_moved(a, b)
    _, _, notes = summary.compare_verdict(a, b)
    assert any(n.startswith("Same in-game settings in A and B") for n in notes)
    text = report.compare(a, b)
    assert "same settings, yet the results moved" in text
    assert "4. The settings didn't change between A and B." in text
    same = _with_settings(result_for(make_rows(n=8000, ft=2.2, seed=2)), [("aa", "2")])
    assert not summary.settings_unchanged_but_moved(a, same)  # inside noise: nothing to flag


def test_newly_read_keys_are_not_changes():
    a = _with_settings(result_for(make_rows()), [("aa", "2")], reader="Source 2 video config")
    b = _with_settings(
        result_for(make_rows()),
        [("aa", "2"), ("fps_max", "400")],
        reader="Source 2 video config and convars",
    )
    assert summary.settings_changes(a, b) == []
