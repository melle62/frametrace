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
    for key in ("screen", "graticule", "ch1", "ch2", "ch3", "trace"):
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
    assert app.verdict_head.cget("text") == "CPU-limited."  # newest first
    assert app.status_word.cget("text") == "SETUP"  # PresentMon missing
    assert not app.start_btn.enabled
    app.handle("trace", {"folder": app.selected[0], "trace": trace.load(app.selected[0])})
    tk_root.update()
    assert app.scope.find_all()  # something was drawn
    app.tabs.select("Report")
    assert app.shown_text == report.render(app.current_result())
    app.select(app.captures[1][0], add=True)
    assert app.tabs.current == "Compare" and "Frametrace compare" in app.shown_text
    app.toggle_theme()
    tk_root.update()
    assert (
        app.t.name == "light"
        and json.loads((tmp_path / "settings.json").read_text())["theme"] == "light"
    )
    app.on_close()
