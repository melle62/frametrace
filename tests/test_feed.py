"""The captures list as a feed of setups (frametrace.feed), and the game profile."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_analysis_report import make_rows, result_for

from frametrace import feed, game, gamesettings, goals, report, summary, theme

CS2 = game.GameInfo(exe="cs2.exe", name="Counter-Strike 2", name_source="steam", engine="Source 2")
VIDEO = [
    ("msaa_samples", "4"), ("videocfg_shadow_quality", "2"), ("videocfg_texture_detail", "1"),
    ("videocfg_ao_detail", "0"), ("fullscreen", "1"),
]  # fmt: skip
AVG = goals.get("avg_fps")
LOWS = goals.get("lows")

_minute = iter(range(60))


def run(
    ft=2.0, settings=None, ram=6000, label=None, named=True, n=None, seed=1, spikes=0,
    bundle=None, group=None, settings_read=True, bench=None,
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
    fields = (("label", label), ("bundle", bundle), ("group", group), ("benchmark", bench))
    user = {k: v for k, v in fields if v}
    if user:
        r["user"] = user
    return Path(f"/captures/20261127-13{m:02d}00-cs2"), r


def newest_first(*runs):
    return list(reversed(runs))


def test_runs_stay_single_rows_named_after_the_change():
    a1, a2, a3 = run(), run(seed=2), run(seed=3)  # same settings: still three rows
    b = run(settings={"msaa_samples": "2"})
    old = run(settings={"msaa_samples": "2"}, named=False, seed=5)  # before games had names
    [h] = feed.build(newest_first(a1, a2, a3, b, old), AVG)
    assert h.title == "Counter-Strike 2" and not h.custom  # the exe-only capture joins it
    assert [s.count for s in h.setups] == [1, 1, 1, 1, 1]  # nothing bundles on its own
    first, second, _, msaa, last = h.oldest_first
    assert first.name == summary.when(a1[1]["capture"]["started"]) and first.kind == "first"
    assert second.kind == "time" and second.name == summary.when(a2[1]["capture"]["started"])
    assert msaa.name == "msaa_samples 4 → 2" and msaa.kind == "settings"
    assert last.kind == "time" and last.key == old[0] and not last.is_bundle
    assert h.base is first and first.change == "BASE"
    assert msaa.status == "same" and msaa.change == "SAME"  # same frame times: inside noise


def test_the_user_bundles_runs_and_a_bundle_opens_to_its_runs():
    a = run(label="7800X3D EXPO on", bundle="b1")
    other = run(seed=2, settings={"msaa_samples": "2"})  # between the bundled runs
    a2 = run(seed=3, bundle="b1")
    lone = run(seed=4, bundle="b2")  # a bundle of one run is just a run
    [h] = feed.build(newest_first(a, other, a2, lone), AVG)
    rows = h.oldest_first
    assert [(s.name, s.count) for s in rows] == [
        ("7800X3D EXPO on", 2),  # at its oldest run
        ("msaa_samples 4 → 2", 1),
        ("msaa_samples 2 → 4", 1),
    ]
    bundle = rows[0]
    assert bundle.is_bundle and feed.is_bundle_key(bundle.key) and bundle.folder == a2[0]
    assert bundle.key == feed.bundle_key(a[0], "b1") and bundle.count_text == "×2"
    assert [c.key for c in bundle.children] == [a[0], a2[0]]
    assert all(c.parent is bundle and c.status == "run" for c in bundle.children)
    assert all(c.change.endswith("%") for c in bundle.children)  # each run against the bundle
    assert bundle.mixed == [] and not rows[2].is_bundle and rows[2].bundle == "b2"
    assert h.setup_of(a2[0]) is bundle


def test_a_bundle_with_different_settings_says_so():
    a = run(bundle="b")
    b = run(seed=2, bundle="b", settings={"msaa_samples": "2"})
    c = run(seed=3, bundle="b", n=40000)  # much longer: another scene
    [h] = feed.build(newest_first(a, b, c), AVG)
    [bundle] = h.setups
    assert [m[0] for m in bundle.mixed] == ["msaa_samples", "Length"]
    text = report.render(bundle.result)
    assert "Runs: 3 bundled, but not all the same, combined." in text
    assert "Not the same in every run: msaa_samples 4 -> 2; Length" in text


def test_system_changes_name_rows_and_other_lengths_get_their_own_base():
    a = run(label="7800X3D EXPO on")
    d = run(seed=5, ram=4800)  # RAM speed changed
    [h] = feed.build(newest_first(a, d), AVG)
    assert [(s.name, s.kind) for s in h.oldest_first] == [
        ("7800X3D EXPO on", "label"),
        ("RAM speed 6000 → 4800 MT/s", "system"),
    ]
    x, y = run(settings_read=False), run(settings_read=False, seed=3, n=18000)  # another scene
    [h] = feed.build(newest_first(x, y), AVG)
    longer = h.oldest_first[1]  # another kind of run: its own base, with nothing against it
    assert longer.base is longer and longer.status == "alone" and h.base is longer
    assert h.oldest_first[0].base is h.oldest_first[0]


def test_a_run_far_from_the_others_is_left_out():
    clean1, clean2 = run(seed=1, bundle="b"), run(seed=2, bundle="b")
    hitchy = run(seed=3, spikes=40, bundle="b")  # 2.5% of frames six times as long
    [h] = feed.build(newest_first(clean1, clean2, hitchy), LOWS)
    [s] = h.setups
    assert h.metric == "1% low"
    assert s.used == [True, True, False] and s.count_text == "×2/3" and not s.spread
    assert [c.status for c in s.children] == ["run", "run", "out"]
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
    shadows = run(ft=1.8, settings={"videocfg_shadow_quality": "1"}, bundle="s")
    shadows2 = run(ft=1.8, settings={"videocfg_shadow_quality": "1"}, seed=2, bundle="s")
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
    a, b = run(seed=1, bundle="b"), run(seed=2, bundle="b")
    c = run(ft=1.8, settings={"msaa_samples": "2"})
    [h] = feed.build(newest_first(a, b, c), AVG)
    stacked = h.oldest_first[0].result
    text = report.render(stacked)
    assert "Runs: 2 repeats of one setup, combined." in text
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


def test_window_bundles_by_drag_and_shows_the_profile(tk_root, tmp_path, monkeypatch):
    import json

    from frametrace import gui

    runs = [run(ft=2.0), run(ft=2.0, seed=2), run(ft=1.8, settings={"msaa_samples": "2"})]
    app, (a1, a2, b) = _window(tk_root, tmp_path, monkeypatch, runs)
    assert app.rail_order == [b, a2, a1]  # nothing bundles on its own
    assert app.selected == [b]

    class Click:  # a press and release without moving: a click selects
        x_root = y_root = 10

    app._drag_start(Click, a2)
    app._drag_end(Click)
    assert app.selected == [a2] and app.drag is None

    heading = app.feed[0]
    text, do = app.drop_action(a2, ("row", app.setups[a1], []))  # drag a2 onto a1
    assert text == f"Bundle with {app.setups[a1].name}"
    do()
    key = feed.bundle_key(a1, a1.name)
    assert app.rail_order == [b, key, a2, a1]  # the bundle opens: its runs as a tree
    assert app.selected == [key] and app.current_result()["stack"]["runs"] == 2
    assert app.runs_panel.winfo_manager()  # the runs panel shows for a bundle
    assert json.loads((tmp_path / "settings.json").read_text())["open_bundles"] == [a1.name]
    app.tabs.select("Report")
    assert "Runs: 2 repeats of one setup, combined." in app.shown_text
    app.select(a1, add=False)  # one run of the bundle on its own
    assert app.current_result().get("stack") is None
    sub = app.header.winfo_children()[-1].winfo_children()[1].cget("text")
    assert sub.startswith("Run 1 of 2 · ")
    app.select(key, add=False)
    app.select(b, add=True)
    assert app.tabs.current == "Compare" and "(2 runs combined)" in app.shown_text
    assert app.drop_action(a1, ("row", app.setups[key], [])) is None  # already in it
    assert app.drop_action(key, ("heading", heading, [])) is None  # already under it

    answers = iter(["EXPO on"])
    monkeypatch.setattr(gui.TextDialog, "ask", staticmethod(lambda *a, **k: next(answers)))
    app.rename_capture(a1)  # a run inside a bundle: names the bundle
    assert {summary.label(app.result_for(f)) for f in (a1, a2)} == {"EXPO on"}
    app.ask_delete(app._runs_of(key))
    assert app.confirm[0].startswith("Delete EXPO on (2 runs)?")
    app.cancel_confirm()

    app.toggle_bundle(a1.name)  # close it
    assert app.rail_order == [b, key]
    app.toggle_bundle(a1.name)
    text, do = app.drop_action(a1, ("heading", app.feed[0], []))  # drag a run out
    assert text == "Take out of the bundle"
    do()
    assert app.rail_order == [b, a2, a1]
    app.move_to_group([b], "Map")
    group = app.heading_for("group:Map")
    text, do = app.drop_action(a1, ("heading", group, []))
    assert text == "Move to Map"
    do()
    assert summary.group(app.result_for(a1)) == "Map"
    game = app.heading_for("game:Counter-Strike 2")
    text, do = app.drop_action(a1, ("heading", game, []))
    assert text == "Out of the group, under Counter-Strike 2"
    do()
    assert summary.group(app.result_for(a1)) is None

    app.open_profile("game:Counter-Strike 2")
    assert app.shown == "Profile" and app.shown_text.startswith("Frametrace profile")
    assert not app.tabs.winfo_manager() and app.page_profile.winfo_manager()
    h = app.heading_for("game:Counter-Strike 2")
    app.set_base(h, app.setups[a2])
    assert json.loads((tmp_path / "settings.json").read_text())["bases"] == {
        "game:Counter-Strike 2": [a2.name]
    }
    assert app.setups[a2].status == "base"
    app.choose_settings(app.heading_for("game:Counter-Strike 2"), app.setups[a1])
    assert "Your settings" in app.shown_text
    app.select(a2, add=False)  # a row leaves the profile
    assert app.profile_key is None and app.tabs.winfo_manager()

    # the rail: the recording settings fold away with a one-line summary
    assert not app.capture_more.winfo_manager()
    assert app.fold_sum.cget("text") == "F10 · 30 s · auto"
    app.toggle_capture_settings()
    assert app.capture_more.winfo_manager() and app.fold_sum.cget("text") == ""
    app.toggle_capture_settings()
    assert theme.untrack(app.col_value.cget("text")) == "AVERAGE FPS"
    app.move_to_group([b], None)  # back after a2 under the game: named after its change
    msaa = app.setups[b]  # a long change keeps its new value when cut
    font = app.t.fonts["mono_sm"]
    assert app._row_name(msaa, "mono_sm", 1000) == "msaa_samples 4 → 2"
    tight = font.measure("msaa_samples → 2")
    assert app._row_name(msaa, "mono_sm", tight) == "msaa_samples → 2"
    assert app._row_name(msaa, "mono_sm", tight - font.measure("xxxx")).endswith("… → 2")
    # a long name wraps instead of being cut: a change breaks between its key and its values
    assert app._row_lines(msaa, "mono_sm", 1000) == ["msaa_samples 4 → 2"]
    two = max(font.measure("msaa_samples"), font.measure("4 → 2"))
    assert app._row_lines(msaa, "mono_sm", two) == ["msaa_samples", "4 → 2"]
    msaa.name, msaa.kind = "Discord HW acceleration off, overlay off, FG on", "label"
    sans = app.t.fonts["body_sm"]
    lines = app._row_lines(msaa, "body_sm", sans.measure("Discord HW acceleration"))
    assert lines[0] == "Discord HW acceleration" and " ".join(lines).endswith("FG on")
    # the rail is as wide as the user drags it, and remembers it
    app.set_rail_width(500)
    assert app.rail_w == theme.px(500)
    assert json.loads((tmp_path / "settings.json").read_text())["rail_width"] == 500
    app.set_rail_width(None)  # double-click: the default again
    assert "rail_width" not in json.loads((tmp_path / "settings.json").read_text())
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
    _, second, three = h.oldest_first
    assert second.kind == "time"  # only cpu_level differs, and only one run has it: no change
    assert three.name == "msaa_samples 4 → 2 +2 more"


def test_a_key_only_the_newer_run_has_is_a_change_when_still_read():
    """Some games write a setting only once it's set: a new key the reader still reads counts."""
    old = run()
    new = run(seed=2, settings={"fps_max": "200"})
    [h] = feed.build(newest_first(old, new), AVG)
    _, second = h.oldest_first
    assert second.name == "fps_max - → 200"


def test_each_benchmark_has_its_own_base_and_names_its_first_run():
    old = run()  # from before benchmark tags: its own kind of run
    m1 = run(bench="Mirage Benchmark")
    a1 = run(bench="Anubis DM", ft=2.5)
    m2 = run(bench="mirage  benchmark", settings={"msaa_samples": "2"})  # same tag, other case
    a2 = run(bench="Anubis DM", ft=2.5, seed=2)
    [h] = feed.build(newest_first(old, m1, a1, m2, a2), AVG)
    rows = h.oldest_first
    assert [(s.name, s.kind) for s in rows][1:3] == [
        ("Mirage Benchmark", "benchmark"),
        ("Anubis DM", "benchmark"),
    ]
    _, mirage, anubis, msaa, anubis2 = rows
    assert msaa.name == "msaa_samples 4 → 2" and msaa.base is mirage  # named after Mirage's run
    assert anubis2.base is anubis and anubis2.kind == "time"  # nothing changed since Anubis
    assert rows[0].base is rows[0] and not feed.comparable(rows[0].result, mirage.result)
    assert feed.benchmarks(newest_first(old, m1, a1, m2, a2)) == ["Anubis DM", "mirage  benchmark"]
    p = feed.profile(h, AVG)
    assert [t.name for t in p.tested] == ["msaa_samples 4 → 2"]  # no pair across benchmarks


def test_a_bundle_of_two_benchmarks_is_mixed():
    a = run(bench="Mirage Benchmark", bundle="b1")
    b = run(bench="Anubis DM", seed=2, bundle="b1")
    [h] = feed.build(newest_first(a, b), AVG)
    [s] = h.setups
    assert ("Benchmark", "Mirage Benchmark", "Anubis DM") in s.mixed


def test_report_and_compare_name_the_benchmark():
    a, b = run(bench="Mirage Benchmark")[1], run(bench="Anubis DM")[1]
    assert "Benchmark: Mirage Benchmark" in report.render(a).splitlines()[:4]
    text = report.compare(a, b)
    assert "Benchmark: A Mirage Benchmark · B Anubis DM" in text
    _, _, notes = summary.compare_verdict(a, b)
    assert any(n.startswith("Different benchmarks") for n in notes)


def test_comparing_two_games_says_so():
    a = run()[1]
    b = run()[1]
    b["capture"]["app"] = "DayZ_x64.exe"
    b["game"] = {"exe": "DayZ_x64.exe", "name": "DayZ"}
    _, _, notes = summary.compare_verdict(a, b)
    assert "Different games: A is Counter-Strike 2, B is DayZ." in notes
