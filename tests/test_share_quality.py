"""Sharing (frametrace/share.py), quality scoring (frametrace/quality.py), tools/aggregate.py."""

from __future__ import annotations

import copy
import gzip
import json
import math
import sys
from pathlib import Path

import pytest
from test_analysis_report import result_for

from frametrace import quality, share

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import aggregate

# --- helpers -----------------------------------------------------------------------------------


def scene_rows(seconds=40, scale=1.0, seed=1, spike_every=0):
    """Frames whose rate follows a fixed scene (a slow wave), like a repeatable benchmark run."""
    import random

    rnd = random.Random(seed)
    rows, t, i = [], 0.0, 0
    while t < seconds:
        base = 2.0 * (1 + 0.35 * math.sin(t / 3.0)) * scale
        f = max(0.2, rnd.gauss(base, base * 0.03))
        if spike_every and i and i % spike_every == 0:
            f = base * 8
        g = f * 0.95
        rows.append(
            {
                "app": "cs2.exe",
                "pid": 7,
                "swapchain": "0x1",
                "runtime": "DXGI",
                "present_mode": "Hardware: Independent Flip",
                "allows_tearing": 1,
                "sync_interval": 0,
                "time_s": t,
                "ms_between_presents": f,
                "ms_frame_time": f,
                "ms_cpu_busy": f * 0.5,
                "ms_cpu_wait": f * 0.05,
                "ms_gpu_busy": g,
                "ms_between_display_change": f,
            }
        )
        t += f / 1000
        i += 1
    return rows


def capture(settings=None, label="Baseline", **kw) -> dict:
    r = result_for(scene_rows(**kw))
    r["game"].update(exe="cs2.exe", name="Counter-Strike 2", name_source="steam", store_id="730")
    r["game"]["build"] = "26879581"
    r["capture"]["app"] = "cs2.exe"
    r["game_settings"] = {
        "reader": "Source 2 video config and convars",
        "source": "x",
        "settings": [list(p) for p in (settings or [("msaa_samples", "4"), ("shadows", "2")])],
    }
    r["user"] = {"label": label}
    return r


# --- what's sent ---------------------------------------------------------------------------------


def test_scrub_masks_people_not_runs():
    text = (
        r"C:\Users\Melvin\AppData\x.cfg, D:\Steam\userdata\123456789\730, mail me@example.com,"
        " id 76561198000000000, /home/melvin/.steam"
    )
    out = share.scrub_text(text)
    assert "Melvin" not in out and "melvin" not in out and "me@example.com" not in out
    assert "123456789" not in out and "76561198000000000" not in out
    assert r"C:\Users\<user>\AppData" in out and "/home/<user>/" in out
    assert share.scrub_text("RTX 4070 Ti SUPER @ 2560x1440, 280 Hz") == (
        "RTX 4070 Ti SUPER @ 2560x1440, 280 Hz"
    )


def test_capture_bundle_drops_other_apps_window_title_and_probe_errors():
    r = capture()
    r["capture"].update(foreground="cs2.exe", other_presenters=["Discord.exe", "chrome.exe"])
    r["game"]["window_title"] = "Counter-Strike 2 - Melvin's server"
    r["game"]["path"] = r"C:\Users\Melvin\Games\cs2.exe"
    r["system"]["errors"] = [r"probe failed in C:\Users\Melvin"]
    before = copy.deepcopy(r)
    b = share.capture_bundle(r)
    text = json.dumps(b)
    assert "Discord" not in text and "chrome" not in text and "Melvin" not in text
    assert b["capture"]["other_presenters"] == 2 and b["capture"]["foreground_is_game"] is True
    assert "window_title" not in b["game"] and b["system"]["errors"] == 1
    assert b["user"]["label"] == "Baseline"
    assert b["analysis"] == json.loads(json.dumps(before["analysis"]))  # numbers untouched
    assert r == before  # the saved result is untouched


def test_start_time_is_shared_in_utc():
    r = capture()
    r["capture"]["started"] = "2026-11-26T20:00:00+01:00"
    assert share.capture_bundle(r)["capture"]["started"] == "2026-11-26T19:00:00+00:00"
    assert share.utc("not a time") is None and share.utc("2026-11-26T20:00:00") is None


def test_filtered_csv_keeps_only_the_games_rows(tmp_path):
    path = tmp_path / "presentmon.csv"
    path.write_text(
        "Application,ProcessID,MsBetweenPresents\n"
        "cs2.exe,7,2.1\nDiscord.exe,99,16.6\ncs2.exe,7,2.2\nchrome.exe,12,8.3\n",
        encoding="utf-8",
    )
    blob = share.filtered_csv(path, 7)
    text = gzip.decompress(blob).decode()
    assert text.splitlines() == [
        "Application,ProcessID,MsBetweenPresents",
        "cs2.exe,7,2.1",
        "cs2.exe,7,2.2",
    ]
    assert share.filtered_csv(path, 1234) is None
    assert share.filtered_csv(tmp_path / "missing.csv", 7) is None
    assert share.filtered_csv(path, None) is None


def test_comparison_bundle_records_goal_changes_and_advice():
    a = capture()
    b = capture(settings=[("msaa_samples", "2"), ("shadows", "2")], label="MSAA 2x", scale=0.9)
    b["user"]["advice"] = "Claude"
    out = share.comparison_bundle(a, b, "A", "B", goal="avg_fps", copied=True)
    assert out["a"] == "A" and out["b"] == "B" and out["goal"] == "avg_fps"
    assert out["settings_changed"] == [["msaa_samples", "4", "2"]]
    assert out["advice"] == "Claude" and out["copied"] is True
    assert out["status"] == "better" and out["deltas"]["Average"]["change"] > 5
    assert out["game"]["exe"] == "cs2.exe"


# --- the sharer -----------------------------------------------------------------------------------


class FakeServer:
    """Records requests; replies like the share and forget functions."""

    def __init__(self):
        self.calls, self.have_csv, self.fail = [], set(), None

    def __call__(self, method, url, body, ctype):
        if self.fail:
            raise self.fail
        if method == "PUT":
            self.calls.append(("PUT", url, len(body)))
            self.have_csv.add(url)
            return 200, b""
        req = json.loads(body)
        fn = url.rsplit("/", 1)[1]
        self.calls.append((fn, req.get("kind"), req.get("id"), "csv" in req))
        if fn == "forget":
            return 200, json.dumps({"ok": True, "deleted": 3}).encode()
        upload = f"https://upload/{req['id']}" if "csv" in req else None
        return 200, json.dumps({"ok": True, "changed": True, "csv_upload": upload}).encode()


def saved_capture(root: Path, name: str, result: dict) -> Path:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (folder / "presentmon.csv").write_text(
        "Application,ProcessID,MsBetweenPresents\ncs2.exe,7,2.0\nDiscord.exe,9,16\n",
        encoding="utf-8",
    )
    return folder


def test_sync_sends_new_and_changed_things_once(tmp_path):
    server = FakeServer()
    sharer = share.Sharer(tmp_path / "shared.json", "https://inbox/fn", server)
    fa = saved_capture(tmp_path / "caps", "20261126-140400-cs2", capture())
    fb = saved_capture(tmp_path / "caps", "20261126-141000-cs2", capture(label="After"))
    caps = [(fa, json.loads((fa / "result.json").read_text())),
            (fb, json.loads((fb / "result.json").read_text()))]  # fmt: skip

    out = sharer.sync(caps)
    assert (out.sent, out.failed, out.error) == (2, 0, None)
    assert [c[0] for c in server.calls] == ["share", "PUT", "share", "PUT"]
    install = sharer.state["install"]
    assert install and json.loads((tmp_path / "shared.json").read_text())["install"] == install

    server.calls.clear()
    assert sharer.sync(caps).unchanged == 2 and server.calls == []

    caps[1][1]["user"]["label"] = "After, renamed"  # a label edit goes out again, without the CSV
    sharer.note_pair(fa, fb, "lows", None)
    out = sharer.sync(caps)
    assert out.sent == 2 and out.total == 3
    assert server.calls == [
        ("share", "capture", "20261126-141000-cs2", False),
        ("share", "comparison", "20261126-140400-cs2~20261126-141000-cs2", False),
    ]


def test_sync_stops_offline_and_resets_after_a_deleted_install(tmp_path):
    server = FakeServer()
    sharer = share.Sharer(tmp_path / "shared.json", "https://inbox/fn", server)
    fa = saved_capture(tmp_path / "caps", "20261126-140400-cs2", capture())
    caps = [(fa, json.loads((fa / "result.json").read_text()))]

    server.fail = share.ShareError("no connection")
    out = sharer.sync(caps)
    assert out.error and out.sent == 0 and sharer.state["captures"] == {}

    server.fail = share.ShareError("deleted", 410)
    sharer.install_id()
    out = sharer.sync(caps)
    assert out.error and sharer.state["install"] is None  # a new ID next time


def test_a_refused_bundle_is_skipped_not_fatal(tmp_path):
    calls = []

    def transport(method, url, body, ctype):
        req = json.loads(body) if method == "POST" else {}
        calls.append(req.get("id"))
        if req.get("id") == "bad":
            return 400, b'{"error": "bad id"}'
        return 200, b'{"ok": true, "changed": true, "csv_upload": null}'

    sharer = share.Sharer(tmp_path / "s.json", "https://inbox/fn", transport)
    good = saved_capture(tmp_path / "caps", "good", capture())
    bad = saved_capture(tmp_path / "caps", "bad", capture())
    out = sharer.sync([(bad, capture()), (good, capture())])
    assert (out.sent, out.failed, out.error) == (1, 1, None) and calls == ["bad", "good"]


def test_a_full_inbox_defers_csvs_but_not_the_data(tmp_path):
    now = [1000.0]
    puts, deferring = [], [True]

    def transport(method, url, body, ctype):
        if method == "PUT":
            puts.append(url)
            return 200, b""
        req = json.loads(body)
        if "csv" in req and deferring[0]:
            return 200, b'{"ok": true, "changed": true, "csv_upload": null, "csv_deferred": true}'
        upload = f"https://upload/{req['id']}" if "csv" in req else None
        return 200, json.dumps({"ok": True, "changed": True, "csv_upload": upload}).encode()

    sharer = share.Sharer(tmp_path / "s.json", "https://inbox/fn", transport, clock=lambda: now[0])
    caps = []
    for i in range(3):
        folder = saved_capture(tmp_path / "caps", f"20261126-14000{i}-cs2", capture())
        caps.append((folder, json.loads((folder / "result.json").read_text())))
    out = sharer.sync(caps)
    assert out.sent == 3 and puts == []  # all three bundles in, no CSV yet
    assert all(c["csv"] == "" for c in sharer.state["captures"].values())
    assert sharer.sync(caps).unchanged == 3  # inside the wait: nothing is sent again
    now[0] += share.CSV_RETRY_S + 1
    deferring[0] = False
    out = sharer.sync(caps)
    assert out.sent == 3 and len(puts) == 3
    assert all(c["csv"] not in ("", "none") for c in sharer.state["captures"].values())


def test_forget_deletes_on_the_server_and_starts_over(tmp_path):
    server = FakeServer()
    sharer = share.Sharer(tmp_path / "shared.json", "https://inbox/fn", server)
    first = sharer.install_id()
    assert sharer.forget() == 3
    assert server.calls[-1][0] == "forget"
    assert sharer.state == {"install": None, "captures": {}, "pairs": {}, "csv_wait_until": 0}
    assert sharer.install_id() != first


def test_no_endpoint_means_no_sharing(tmp_path):
    sharer = share.Sharer(tmp_path / "s.json", "", lambda *a: pytest.fail("no request"))
    assert not sharer.available
    assert sharer.sync([]).error


def test_preview_shows_what_would_be_sent(tmp_path):
    r = capture()
    r["capture"]["other_presenters"] = ["Discord.exe"]
    folder = saved_capture(tmp_path, "20261126-140400-cs2", r)
    text = share.preview(folder)
    assert "Discord" not in text and "the game's rows only" in text


# --- quality ------------------------------------------------------------------------------------


def test_capture_score_rewards_complete_clean_identified_runs():
    good = capture()
    assert quality.capture_score(good) == 100
    poor = capture(seconds=12, spike_every=40)
    poor["game_settings"] = None
    poor["user"] = {}
    failed = {c.name for c in quality.capture_checks(poor) if not c.passed}
    assert {"settings read", "long enough", "clean run", "labelled"} <= failed
    assert quality.capture_score(poor) < 50


def test_one_change_in_the_same_scene_is_usable_for_costs():
    a = capture()
    b = capture(settings=[("msaa_samples", "2"), ("shadows", "2")], scale=0.9, seed=2)
    pair = quality.judge_pair(a, b)
    assert pair.scene_r > 0.9 and pair.usable_for_costs and not pair.baseline


def test_two_identical_runs_are_an_agreeing_baseline():
    pair = quality.judge_pair(capture(), capture(seed=5))
    assert pair.baseline and pair.agreeing_baseline and not pair.usable_for_costs


def test_different_scene_system_or_several_changes_are_not_usable():
    a = capture()
    b = capture(settings=[("msaa_samples", "2"), ("shadows", "2")], seed=3)
    b["analysis"]["stats"]["second_fps"] = list(reversed(b["analysis"]["stats"]["second_fps"]))
    assert not quality.judge_pair(a, b).usable_for_costs
    c = capture(settings=[("msaa_samples", "2"), ("shadows", "2")], seed=3)
    c["system"]["cpu"] = "Another CPU"
    assert not quality.judge_pair(a, c).usable_for_costs
    d = capture(settings=[("msaa_samples", "2"), ("shadows", "0")], seed=3)
    assert not quality.judge_pair(a, d).usable_for_costs


def test_contributor_levels():
    caps = [capture(), capture(seed=5)]
    baseline = quality.judge_pair(*caps)
    assert quality.judge_contributor("x", caps, [baseline]).level == "trusted"
    assert quality.judge_contributor("x", caps, []).level == "contributing"
    assert quality.judge_contributor("x", [], []).level == "new"


# --- aggregate ------------------------------------------------------------------------------------


def write_dataset(root: Path, who: str, captures: list[tuple[str, dict]], compared=()):
    for local_id, data in captures:
        path = root / "captures" / "cs2" / who / f"{local_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"kind": "capture", "contributor": who, "local_id": local_id}
        rec.update(updated_at="2026-11-26T12:00:00+00:00", data=share.capture_bundle(data))
        path.write_text(json.dumps(rec), encoding="utf-8")
    for a, b in compared:
        path = root / "comparisons" / "cs2" / who / f"{a}~{b}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"kind": "comparison", "contributor": who, "updated_at": "2026-11-27T08:00:00+00:00"}
        path.write_text(json.dumps({**rec, "data": {"a": a, "b": b}}), encoding="utf-8")


def runs(start: str, *settings_list, seed=0):
    out = []
    for i, settings in enumerate(settings_list):
        r = capture(settings=settings, seed=seed + i, scale=1.0 if settings[0][1] == "4" else 0.9)
        r["capture"]["started"] = f"2026-11-26T{start}:{i:02d}+01:00"
        out.append((f"20261126-{start.replace(':', '')}{i:02d}-cs2", r))
    return out


HIGH = [("msaa_samples", "4"), ("shadows", "2")]
LOW = [("msaa_samples", "2"), ("shadows", "2")]


def test_aggregate_counts_only_trusted_one_change_runs(tmp_path):
    # trusted: an agreeing baseline pair, then one change (found as consecutive captures)
    write_dataset(tmp_path, "aaaaaaaaaaaaaaaa", runs("14:00", HIGH, HIGH, LOW))
    # not trusted: a single one-change pair with no baseline, opened in Compare
    lone = runs("15:00", HIGH, LOW, seed=10)
    write_dataset(tmp_path, "bbbbbbbbbbbbbbbb", lone, compared=[(lone[0][0], lone[1][0])])
    ds = aggregate.load(tmp_path)
    judged, people = aggregate.judge(ds)
    assert people["aaaaaaaaaaaaaaaa"].level == "trusted"
    assert people["bbbbbbbbbbbbbbbb"].level == "contributing"
    rows = aggregate.rows_for({"cs2.exe"}, judged, people)
    assert len(rows) == 1
    row = rows[0]
    assert (row["key"], row["a"], row["b"], row["runs"], row["people"]) == (
        "msaa_samples", "4", "2", 1, 1
    )  # fmt: skip
    assert row["Average"] > 5 and row["GPU busy"] < -5
    text = aggregate.table(rows, ds.newest)
    assert "| `msaa_samples` | 4 → 2 | 1 | 1 |" in text and "As of 2026-11-27" in text
    assert "RTX 4070 Ti SUPER (2560×1440)" in text


def test_aggregate_writes_between_the_markers_and_checks(tmp_path, monkeypatch):
    skill = tmp_path / "skills" / "frametrace-cs2" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    original = (ROOT / "skills" / "frametrace-cs2" / "SKILL.md").read_text(encoding="utf-8")
    skill.write_text(original, encoding="utf-8")
    monkeypatch.setattr(aggregate, "SKILLS", tmp_path / "skills")
    monkeypatch.setattr(aggregate, "ROOT", tmp_path)
    data = tmp_path / "data"
    write_dataset(data, "aaaaaaaaaaaaaaaa", runs("14:00", HIGH, HIGH, LOW))
    assert aggregate.main(["--data", str(data), "--check"]) == 1
    assert aggregate.main(["--data", str(data)]) == 0
    text = skill.read_text(encoding="utf-8")
    assert "**Community data**" in text and text.count("frametrace:community-data") == 2
    assert text.replace(aggregate.BLOCK.search(text).group(0), "") == original.replace(
        aggregate.BLOCK.search(original).group(0), ""
    )  # nothing outside the markers changed
    assert aggregate.main(["--data", str(data), "--check"]) == 0


def test_an_empty_dataset_keeps_the_placeholder():
    rows = aggregate.rows_for({"cs2.exe"}, [], {})
    assert "No community data yet" in aggregate.table(rows, "")


def test_every_game_skill_and_the_template_have_the_community_markers():
    for path in [
        *ROOT.glob("skills/frametrace-*/SKILL.md"),
        ROOT / "skills/game-skill-template.md",
    ]:
        assert aggregate.BLOCK.search(path.read_text(encoding="utf-8")), path
