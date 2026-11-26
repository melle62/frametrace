"""Trace buckets, summary wording, theme helpers and a smoke test of the window."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from test_analysis_report import fake_system, make_rows, result_for

from frametrace import report, summary, theme, trace


def test_trace_buckets_and_hitches():
    rows = make_rows(n=6000, ft=2.0, spikes_every=1500)
    tr = trace.build(rows, buckets=100)
    assert tr is not None and tr.buckets == 100
    for lo, mid, hi in zip(tr.p5, tr.p50, tr.p95, strict=True):
        assert lo <= mid <= hi
    assert all(g is not None for g in tr.gpu) and all(c is not None for c in tr.cpu)
    assert len(tr.hitches) == 3  # every 1500th frame is 6x long; the first one is skipped
    assert all(ms == pytest.approx(12.0) for _, ms in tr.hitches)
    assert tr.duration_s == pytest.approx(10.95, abs=0.2)  # 12 s of frames minus the first second
    assert tr.peak_ms() >= 2.0


def test_trace_save_load_roundtrip(tmp_path):
    tr = trace.build(make_rows(n=2000), buckets=50)
    trace.save(tr, tmp_path)
    back = trace.load(tmp_path)
    assert back == tr
    (tmp_path / trace.TRACE_FILE).write_text("{not json")
    assert trace.load(tmp_path) is None


def test_trace_rebuilt_from_csv_for_old_captures(tmp_path):
    rows = make_rows(n=3000)
    header_file = Path(__file__).parent / "fixtures/headers/presentmon-2.6.0-default.csv"
    header = header_file.read_text().splitlines()[0].strip().split(",")
    with open(tmp_path / "presentmon.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            rec = dict.fromkeys(header, "NA")
            rec.update(
                Application="game.exe", ProcessID="7", SwapChainAddress="0x1", PresentRuntime="DXGI",
                SyncInterval="0", AllowsTearing="1", PresentMode=r["present_mode"],
                TimeInMs=f"{r['time_s'] * 1000:.4f}", MsBetweenPresents=f"{r['ms_between_presents']:.4f}",
                MsBetweenAppStart=f"{r['ms_frame_time']:.4f}", MsCPUBusy=f"{r['ms_cpu_busy']:.4f}",
                MsCPUWait=f"{r['ms_cpu_wait']:.4f}", MsGPUBusy=f"{r['ms_gpu_busy']:.4f}",
            )  # fmt: skip
            w.writerow([rec[h] for h in header])
    result = result_for(rows)
    result["capture"]["pid"] = 7
    tr = trace.get(tmp_path, result)
    assert tr is not None and tr.buckets == trace.BUCKETS
    assert (tmp_path / trace.TRACE_FILE).is_file()  # cached for next time
    assert trace.get(tmp_path / "missing", result) is None


@pytest.mark.parametrize(
    ("gpu_frac", "cpu_wait", "head"),
    [((0.95, 0.99), 0.05, "GPU-limited."), ((0.3, 0.5), 0.05, "CPU-limited.")],
)
def test_verdict_headlines(gpu_frac, cpu_wait, head):
    r = result_for(make_rows(gpu_frac=gpu_frac, cpu_wait_frac=cpu_wait))
    h, sentence = summary.verdict(r)
    assert h == head
    assert sentence.endswith(".") and "%" in sentence


def test_verdict_for_cap_and_missing_gpu_data():
    capped = result_for(make_rows(n=4000, ft=5.0, jitter=0.0, gpu_frac=(0.3, 0.4)))
    assert summary.verdict(capped)[0] == "Capped at 200 FPS."
    rows = make_rows()
    for r in rows:
        r["ms_gpu_busy"] = None
    assert summary.verdict(result_for(rows))[0] == "No bottleneck data."


def test_readouts_details_and_rail_row():
    r = result_for(make_rows(n=8000, gpu_frac=(0.95, 0.99)))
    ro = summary.readouts(r)
    assert [x.title for x in ro] == [
        "Average",
        "1% low",
        "CPU-side 1% low",
        "PC latency",
        "0.1% low",
    ]
    assert ro[0].unit == "FPS" and float(ro[0].value.replace(",", "")) == pytest.approx(
        500, rel=0.05
    )
    assert ro[3].value is None and ro[3].sub == "needs NVIDIA Reflex"
    r["analysis"]["display"]["pc_latency_ms"], r["analysis"]["display"]["pc_latency_p95_ms"] = (
        6.83,
        10.49,
    )
    ro = summary.readouts(r)
    assert ro[3].value == "6.8" and ro[4].title == "P95 latency" and ro[4].value == "10.5"
    assert "REFLEX" in summary.tags(r)
    labels = [k for k, _ in summary.details(r)]
    assert labels[0] == "GPU busy, median" and "Hitches" in labels
    level, name, meta, fps, sub = summary.rail_row(r)
    assert name == "game.exe" and level == "ok" and "s" in meta and float(fps) > 0
    assert sub.startswith(("GPU", "CPU"))
    short = result_for(make_rows(n=3000))  # 6 s, minus the skipped first second
    assert summary.rail_row(short)[0] == "warn" and summary.rail_row(short)[4] == "short"


def test_compare_deltas_noise_and_direction():
    a = result_for(make_rows(n=8000, gpu_frac=(0.95, 0.99)))
    slower = result_for(make_rows(n=8000, ft=2.2, gpu_frac=(0.95, 0.99), seed=3))
    groups = dict(summary.compare_deltas(a, slower))
    assert list(groups) == ["Frame rate", "Frame times", "Load per frame"]  # no latency data
    avg = groups["Frame rate"][0]
    assert (
        avg.label == "Average"
        and avg.status == "worse"
        and avg.change == pytest.approx(-9.1, abs=1)
    )
    assert avg.change_text().startswith("-") and avg.change_text().endswith("%")
    assert groups["Frame times"][0].status == "worse"  # longer median frame time
    assert groups["Load per frame"][0].status == "changed"  # GPU busy has no better direction
    same = result_for(make_rows(n=8000, gpu_frac=(0.95, 0.99), seed=2))
    assert dict(summary.compare_deltas(a, same))["Frame rate"][0].status == "same"


def test_compare_verdict_and_system_changes():
    a = result_for(make_rows(n=8000, gpu_frac=(0.95, 0.99)))
    b = result_for(make_rows(n=8000, ft=2.2, gpu_frac=(0.95, 0.99), seed=3), ram_running_mts=5600)
    head, items, notes = summary.compare_verdict(a, b)
    assert summary.plain(head) == "B is 9.0% slower on average."
    assert summary.runs(head)[1] == ("9.0%", True)  # numbers are set in mono
    assert items and all(status == "worse" for status, _ in items)
    assert notes == []
    head, items, _ = summary.compare_verdict(b, a)
    assert summary.plain(head).startswith("B is") and "faster" in head
    same = result_for(make_rows(n=8000, gpu_frac=(0.95, 0.99), seed=2))
    head, items, _ = summary.compare_verdict(a, same)
    assert head == "Same average FPS." and items[0][0] == "same"
    short_cpu = result_for(make_rows(n=3000, gpu_frac=(0.3, 0.5)))
    _, _, notes = summary.compare_verdict(a, short_cpu)
    assert any("limit moved from the GPU to the CPU" in n for n in notes)
    assert any("Different lengths" in n for n in notes)
    assert summary.system_changes(a, b) == [("RAM speed", "6000 MT/s", "5600 MT/s")]
    assert summary.system_changes(a, a) == []


def test_small_helpers():
    assert summary.initials("cs2.exe") == "CS"
    assert summary.initials("DayZ_x64.exe") == "DA"
    assert summary.when("2026-11-25T22:34:02+01:00") == "25 Nov 22:34"
    assert summary.system_rows(["CPU: X (8C/16T)", "loose line"]) == [
        ("CPU", "X (8C/16T)"),
        ("", "loose line"),
    ]
    assert theme.mix("#FFFFFF", "#000000", 0.5) == "#808080"
    assert theme.mix("#F5C518", "#141413", 1.0) == "#F5C518"
    for name in ("dark", "light"):
        assert set(theme.PALETTES[name]) == set(theme.DARK)
    # the scope screen never changes with the mode
    for key in ("screen", "graticule", "ch1", "ch2", "ch3", "trace", "ref"):
        assert theme.LIGHT[key] == theme.DARK[key]


def test_scope_scales():
    instruments = pytest.importorskip("frametrace.instruments")
    assert instruments.nice_div(2.4) == 1
    assert instruments.nice_div(4.7) == 1.5
    assert instruments.nice_div(17.0) == 10
    assert instruments.nice_time_step(100) == 20
    assert instruments.nice_time_step(30) == 5


@pytest.fixture
def tk_root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_window_smoke(tk_root, tmp_path, monkeypatch):
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

    root_dir = tmp_path / "captures"
    for i, gpu in enumerate(((0.95, 0.99), (0.3, 0.5))):
        folder = root_dir / f"20261125-22{i}000-game"
        folder.mkdir(parents=True)
        rows = make_rows(n=4000, gpu_frac=gpu, seed=i)
        result = result_for(rows)
        result["capture"]["started"] = f"2026-11-25T22:{i}0:00+01:00"
        (folder / "result.json").write_text(json.dumps(result))
        trace.save(trace.build(rows), folder)

    app = gui.App(tk_root, captures_root=root_dir)
    tk_root.update()
    assert len(app.captures) == 2 and app.selected == [app.captures[0][0]]
    assert app.headline == "CPU-limited."  # newest first
    assert theme.untrack(app.status_word.cget("text")) == "SETUP"  # PresentMon missing
    assert not app.start_btn.enabled
    app.handle("trace", {"folder": app.selected[0], "trace": trace.load(app.selected[0])})
    tk_root.update()
    assert app.scope.find_all()  # something was drawn
    app.tabs.select("Report")
    assert app.shown_text == report.render(app.current_result())
    app.select(app.captures[1][0], add=True)
    assert app.tabs.current == "Compare" and "Frametrace compare" in app.shown_text
    tk_root.update()
    assert app.compare_scope is not None and app.page_compare.inner.winfo_children()
    for f in app.selected:
        app.handle("trace", {"folder": f, "trace": trace.load(f)})
    assert app.compare_scope.ref is not None and app.compare_scope.trace is not None
    app._compare_with(app.captures[0][0])  # the rows' context menu
    assert len(app.selected) == 2 and app.tabs.current == "Compare"
    app.select(app.captures[0][0], add=False)
    assert app.selected == [app.captures[0][0]]

    class Key:
        widget = tk_root

    app._key_move(Key, 1)  # Down arrow: next capture
    assert app.selected == [app.captures[1][0]]
    app.handle("system", {"info": fake_system()})
    assert "\n" in app.system_line() and "7800X3D" in app.system_line()
    app.toggle_theme()
    tk_root.update()
    assert (
        app.t.name == "light"
        and json.loads((tmp_path / "settings.json").read_text())["theme"] == "light"
    )
    app.theme_var.set("dark")  # the top bar's switch
    app.toggle_theme()
    assert app.t.name == "dark"
    app.on_close()


def test_numbers_in_prose_are_found_with_their_units():
    nums = [
        p for p, is_num in summary.number_runs("RAM runs at 6000 MT/s (kit rated 6000).") if is_num
    ]
    assert nums == ["6000 MT/s", "6000"]
    text = "93% of frames. Median GPU busy 2.16 ms: about 1,462 FPS, ~200 or -3.8% and +0.12 pp."
    assert [p for p, n in summary.number_runs(text) if n] == [
        "93%",
        "2.16 ms",
        "1,462 FPS",
        "~200",
        "-3.8%",
        "+0.12 pp",
    ]
    # digits inside names stay in the sans, and a trailing comma is not part of a number
    names = "7800X3D DDR5 P95 SHA-256 2x build 26300, done"
    assert [p for p, n in summary.number_runs(names) if n] == ["26300"]
    assert "".join(p for p, _ in summary.number_runs(text)) == text
    assert summary.number_runs("B is `4.2%` faster") == summary.runs("B is `4.2%` faster")


def test_display_scale_and_silk_tracking():
    assert theme.scale_for(96) == 1.0
    assert theme.scale_for(100) == 1.0  # Xvfb and some monitors report ~100 DPI
    assert theme.scale_for(120) == 1.25
    assert theme.scale_for(144) == 1.5
    assert theme.scale_for(400) == 3.0
    assert theme.track("CPU") == "C P U"
    assert theme.untrack(theme.track("1% LOW")) == "1% LOW"


def test_system_sections_split_settings():
    lines = [
        "CPU: AMD Ryzen 7 7800X3D 8-Core Processor (8C/16T)",
        (
            "Settings: power plan High performance | Game Mode on | HAGS ? | memory integrity off"
            " | windowed optimizations on"
        ),
    ]
    (hw_title, hw), (st_title, st) = summary.system_sections(lines)
    assert hw_title == "Hardware" and hw[0][0] == "CPU"
    assert st_title == "Windows settings"
    assert st == [
        ("Power plan", "High performance"),
        ("Game Mode", "on"),
        ("HAGS", "unknown"),
        ("Memory integrity", "off"),
        ("Windowed optimizations", "on"),
    ]
    assert summary.system_sections(["(system info not available)"]) == [
        ("Hardware", [("", "(system info not available)")])
    ]


def test_instruments_on_tk(tk_root):
    from frametrace.instruments import RichText, Scope, ThinScrollbar

    t = theme.apply(tk_root, "dark")
    box = tk_root.nametowidget(".")
    rt = RichText(box, t, "word " * 60)
    rt.place(x=0, y=0, width=200)
    tk_root.update()
    rt._fit()
    assert int(rt.cget("height")) > 1  # wraps and grows
    assert "num" in rt.tag_names() and not rt.tag_ranges("num")
    rt.set("Median GPU busy 2.16 ms")
    assert rt.get(*rt.tag_ranges("num")) == "2.16 ms"  # number and unit stay together

    moved = []
    sb = ThinScrollbar(box, t, lambda *a: moved.append(a))
    sb.place(x=0, y=0, width=6, height=200)
    tk_root.update()
    sb.set(0.0, 1.0)
    assert not sb.needed and not sb.find_all()
    sb.set(0.25, 0.5)
    assert sb.needed and sb.find_all()

    rows = make_rows(n=6000, ft=2.0, spikes_every=1500)
    scope = Scope(box, t)
    scope.show(trace.build(rows, buckets=100))
    assert scope.scale_text().endswith(" s") and "ms/div" in scope.scale_text()
    assert scope.has("ch1") and scope.has("ch2")
    for r in rows:
        r["ms_gpu_busy"] = None
    scope.show(trace.build(rows, buckets=100))
    assert not scope.has("ch2")
