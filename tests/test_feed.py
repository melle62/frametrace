"""The captures list as a feed of setups (frametrace.feed), and the game profile."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_analysis_report import make_rows, result_for

from frametrace import feed, game, gamesettings, goals, report, summary

CS2 = game.GameInfo(exe="cs2.exe", name="Counter-Strike 2", name_source="steam", engine="Source 2")
VIDEO = [
    ("msaa_samples", "4"), ("videocfg_shadow_quality", "2"), ("videocfg_texture_detail", "1"),
    ("videocfg_ao_detail", "0"), ("fullscreen", "1"),
]  # fmt: skip
AVG = goals.get("avg_fps")
LOWS = goals.get("lows")

_minute = iter(range(10, 60))


def run(
    ft=2.0, settings=None, ram=6000, label=None, named=True, n=None, seed=1, spikes=0,
    split=None, group=None, settings_read=True,
) -> tuple[Path, dict]:  # fmt: skip
    """One saved CS2 capture; each call is a minute after the one before."""
    rows = make_rows(n=n or int(12000 / ft), ft=ft, seed=seed, spikes_every=spikes)  # ~12 s
    for r in rows:
        r["app"] = "cs2.exe"
    r = result_for(rows, ram_running_mts=ram)
    m = next(_minute)
    r["capture"].update(app="cs2.exe", started=f"2026-11-27T13:{m:02d}:00+01:00")
    r["game"] = (CS2 if named else game.GameInfo(exe="cs2.exe")).to_dict()
    if settings_read:
        values = dict(VIDEO, **(settings or {}))
        gs = gamesettings.GameSettings(
            "Source 2 video config", "cs2_video.txt", list(values.items())
        )
        r["game_settings"] = gs.to_dict()
    user = {k: v for k, v in (("label", label), ("split", split), ("group", group)) if v}
    if user:
        r["user"] = user
    return Path(f"/captures/20261127-13{m:02d}00-cs2"), r


def newest_first(*runs):
    return list(reversed(runs))


def test_repeat_runs_stack_and_rows_name_the_change():
    a1, a2, a3 = run(), run(seed=2), run(seed=3)
    b = run(settings={"msaa_samples": "2"})
    old = run(settings={"msaa_samples": "2"}, named=False, seed=5)  # before games had names
    [h] = feed.build(newest_first(a1, a2, a3, b, old), AVG)
    assert h.title == "Counter-Strike 2" and not h.custom  # the exe-only capture joins it
    assert [s.count for s in h.setups] == [2, 3]  # newest first; old joins b (nothing changed)
    first, msaa = h.oldest_first
    assert first.name == summary.when(a1[1]["capture"]["started"]) and first.kind == "first"
    assert first.count_text == "×3"
    assert msaa.name == "msaa_samples 4 → 2" and msaa.kind == "settings"
    assert msaa.folder == old[0]  # the newest run stands for the setup
    assert h.base is first and first.change == "BASE"
    assert msaa.status == "same" and msaa.change == "SAME"  # same frame times: inside noise


def test_labels_split_and_system_changes_start_new_setups():
    a = run(label="7800X3D EXPO on")
    a2 = run(seed=2)  # no label: another run of the same setup
    b = run(seed=3, label="Second try")  # a new label starts a new row
    c = run(seed=4, split="yes")  # split off by the user
    d = run(seed=5, ram=4800)  # RAM speed changed
    [h] = feed.build(newest_first(a, a2, b, c, d), AVG)
    names = [(s.name, s.kind, s.count) for s in h.oldest_first]
    assert names == [
        ("7800X3D EXPO on", "label", 2),
        ("Second try", "label", 1),
        (summary.when(c[1]["capture"]["started"]), "time", 1),
        ("RAM speed 6000 → 4800 MT/s", "system", 1),
    ]
    assert h.oldest_first[2].split


def test_unread_settings_and_other_lengths():
    a = run(settings_read=False)
    b = run(settings_read=False, seed=2)
    c = run(settings_read=False, seed=3, n=18000)  # three times longer: another scene
    [h] = feed.build(newest_first(a, b, c), AVG)
    assert [s.count for s in h.oldest_first] == [2, 1]
    longer = h.oldest_first[1]  # another kind of run: its own base, with nothing against it
    assert longer.base is longer and longer.status == "alone" and h.base is longer
    assert h.oldest_first[0].base is h.oldest_first[0]


def test_a_run_far_from_the_others_is_left_out():
    clean1, clean2 = run(seed=1), run(seed=2)
    hitchy = run(seed=3, spikes=40)  # 2.5% of frames six times as long: the 1% low drops
    [h] = feed.build(newest_first(clean1, clean2, hitchy), LOWS)
    [s] = h.setups
    assert h.metric == "1% low"
    assert s.used == [True, True, False] and s.count_text == "×2/3" and not s.spread
    assert s.trace_folder == clean2[0]  # the newest run that counts
    lows = [r["analysis"]["stats"]["p1_fps"] for _, r in (clean1, clean2)]
    assert s.value == pytest.approx(sum(lows) / 2)
    st = s.result["stack"]
    assert st["runs"] == 3 and st["used"] == 2 and st["left_out"] == [hitchy[0].name]
    secs = sum(len(r["analysis"]["stats"]["second_fps"]) for _, r in (clean1, clean2))
    assert len(s.result["analysis"]["stats"]["second_fps"]) == secs  # pooled
    [h2] = feed.build(newest_first(clean1, hitchy), LOWS)  # two that disagree: can't tell which
    assert h2.setups[0].spread and h2.setups[0].count_text == "×2"


def test_base_can_be_pinned_and_deltas_follow_the_goal():
    base = run(ft=2.0)
    faster = run(ft=1.8, settings={"videocfg_shadow_quality": "1"})
    slower = run(ft=2.4, settings={"videocfg_shadow_quality": "1", "msaa_samples": "8"})
    caps = newest_first(base, faster, slower)
    [h] = feed.build(caps, AVG)
    _, f, s = h.oldest_first
    assert (f.status, s.status) == ("better", "worse")
    assert f.change.startswith("+") and s.change.startswith("-")
    assert s.name == "msaa_samples 4 → 8"  # from the setup before, not the base
    [h] = feed.build(caps, AVG, bases={"game:Counter-Strike 2": faster[0].name})
    assert h.base.folder == faster[0] and h.oldest_first[0].status == "worse"


def test_profile_best_setup_tested_changes_and_text():
    base = run(ft=2.0)
    shadows = run(ft=1.8, settings={"videocfg_shadow_quality": "1"})
    shadows2 = run(ft=1.8, settings={"videocfg_shadow_quality": "1"}, seed=2)
    msaa = run(ft=2.2, settings={"videocfg_shadow_quality": "1", "msaa_samples": "8"})
    [h] = feed.build(newest_first(base, shadows, shadows2, msaa), AVG)
    p = feed.profile(h, AVG)
    assert p.best.name == "shadow_quality 2 → 1" and not p.chosen  # the namespace dropped
    assert p.best_status == "better" and p.differs == [("videocfg_shadow_quality", "2", "1")]
    assert [(t.name, t.status) for t in p.tested] == [
        ("msaa_samples 4 → 8", "worse"),
        ("shadow_quality 2 → 1", "better"),
    ]
    assert p.tested[1].runs == (1, 2)
    text = feed.profile_text(p)
    assert text.startswith("Frametrace profile · Counter-Strike 2")
    assert "- videocfg_shadow_quality: 2 -> 1" in text and "## Changes tested" in text
    assert "Measured on this PC: 3 setups, 4 runs." in text
    mine = feed.profile(h, AVG, chosen=base[0].name)  # the user keeps their own settings
    assert mine.chosen and mine.best is h.base and "Your settings" in feed.profile_text(mine)


def test_profile_with_nothing_better_keeps_the_base():
    a, b = run(ft=2.0), run(ft=2.3, settings={"msaa_samples": "8"})
    [h] = feed.build(newest_first(a, b), AVG)
    p = feed.profile(h, AVG)
    assert p.best is h.base and p.best_change == "BASE" and p.differs == []


def test_combined_report_and_compare_name_the_runs():
    a, b = run(seed=1), run(seed=2)
    c = run(ft=1.8, settings={"msaa_samples": "2"})
    [h] = feed.build(newest_first(a, b, c), AVG)
    stacked = h.oldest_first[0].result
    text = report.render(stacked)
    assert "Runs: 2 with the same settings, combined." in text
    assert text.count("\n- 2026-11-27 13:") == 2
    cmp = report.compare(stacked, h.oldest_first[1].result)
    assert "(2 runs combined)" in cmp.splitlines()[1]
    assert "2 runs combined" in summary.subtitle(stacked)


def test_groups_keep_their_own_heading():
    a = run()
    b = run(seed=2, group="Benchmark map")
    hs = feed.build(newest_first(a, b), AVG)
    assert [(h.key, h.custom, h.runs) for h in hs] == [
        ("group:Benchmark map", True, 1),
        ("game:Counter-Strike 2", False, 1),
    ]


# --- the window -------------------------------------------------------------------------------


def _window(tk_root, tmp_path, monkeypatch, runs):
    import json

    from test_analysis_report import fake_system

    from frametrace import gui, hotkey, presentmon, sysinfo

    class Listener:
        def __init__(self, key, cb):
            self.hotkey = key

        def start_and_wait(self):
            return None

        def is_alive(self):
            return True

        def stop(self):
            pass

    def not_found():
        raise presentmon.PresentMonNotFound("not here")

    monkeypatch.setattr(gui, "SETTINGS_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(hotkey, "HotkeyListener", Listener)
    monkeypatch.setattr(sysinfo, "collect", fake_system)
    monkeypatch.setattr(presentmon, "find_presentmon", not_found)
    root = tmp_path / "captures"
    folders = []
    for folder, result in runs:
        f = root / folder.name
        f.mkdir(parents=True)
        (f / "result.json").write_text(json.dumps(result))
        folders.append(f)
    app = gui.App(tk_root, captures_root=root)
    tk_root.update()
    return app, folders


def test_window_shows_setups_and_the_profile(tk_root, tmp_path, monkeypatch):
    import json

    from frametrace import gui

    runs = [run(ft=2.0), run(ft=2.0, seed=2), run(ft=1.8, settings={"msaa_samples": "2"})]
    app, (a1, a2, b) = _window(tk_root, tmp_path, monkeypatch, runs)
    assert app.rail_order == [b, a2]  # two rows: the stack is known by its newest run
    assert app.selected == [b]
    app.select(a2, add=False)
    assert app.current_result()["stack"]["runs"] == 2
    assert "2 runs combined" in app.header.winfo_children()[-1].winfo_children()[1].cget("text")
    assert app.runs_panel.winfo_manager()  # the runs panel shows for a stack
    app.tabs.select("Report")
    assert "Runs: 2 with the same settings, combined." in app.shown_text
    app.select(b, add=True)
    assert app.tabs.current == "Compare" and "(2 runs combined)" in app.shown_text

    app.open_profile("game:Counter-Strike 2")
    assert app.shown == "Profile" and app.shown_text.startswith("Frametrace profile")
    assert not app.tabs.winfo_manager() and app.page_profile.winfo_manager()
    assert "msaa_samples" in app.shown_text
    app.set_base(app.feed[0], app.setups[b])
    assert json.loads((tmp_path / "settings.json").read_text())["bases"] == {
        "game:Counter-Strike 2": [b.name]
    }
    assert app.setups[b].status == "base" and app.setups[a2].status == "worse"
    app.choose_settings(app.feed[0], app.setups[a2])
    assert "Your settings" in app.shown_text
    app.select(b, add=False)  # a row leaves the profile
    assert app.profile_key is None and app.tabs.winfo_manager()

    answers = iter(["EXPO on"])
    monkeypatch.setattr(gui.TextDialog, "ask", staticmethod(lambda *a, **k: next(answers)))
    app.rename_capture(a2)  # names the whole stack
    assert {summary.label(app.result_for(f)) for f in (a1, a2)} == {"EXPO on"}
    app.split_setup(app.setups[a2])
    assert app.rail_order == [b, a2, a1]
    app.join_setup(app.setups[a2])
    assert app.rail_order == [b, a2]
    app.handle("done", {"folder": a2, "report": "one run"})  # a repeat run: copied combined
    assert "Runs: 2 with the same settings, combined." in app.shown_text
    app.ask_delete(app._runs_of(a2))
    assert app.confirm[0].startswith("Delete EXPO on (2 runs)?")
    app.cancel_confirm()
    app.on_close()


def test_keys_only_one_run_has_are_not_changes():
    """An older Frametrace read cpu_level, a newer one filters it: that's no settings change."""
    old = run(settings={"cpu_level": "3"})
    new = run(seed=2)
    new[1]["game_settings"]["settings"] = [
        kv for kv in new[1]["game_settings"]["settings"] if kv[0] != "cpu_level"
    ]
    many = run(seed=3, settings={"msaa_samples": "2", "videocfg_ao_detail": "1", "fullscreen": "0"})
    [h] = feed.build(newest_first(old, new, many), AVG)
    first, three = h.oldest_first
    assert first.count == 2  # stacked: only cpu_level differs, and only one run has it
    assert three.name == "msaa_samples 4 → 2 +2 more"


def test_a_key_only_the_newer_run_has_is_a_change_when_still_read():
    """Some games write a setting only once it's set: a new key the reader still reads counts."""
    old = run()
    new = run(seed=2, settings={"fps_max": "200"})
    [h] = feed.build(newest_first(old, new), AVG)
    first, second = h.oldest_first
    assert first.count == second.count == 1  # not stacked
    assert second.name == "fps_max - → 200"
