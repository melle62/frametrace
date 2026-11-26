"""Screenshots of the Frametrace window with synthetic demo captures (README, design review).

Builds a throwaway captures folder with deterministic captures shaped like real runs (a CS2
benchmark map with Reflex off and on, a 200 FPS cap, a CPU-limited game, a short capture
without GPU columns), opens the real window on it with PresentMon and the hotkey stubbed
out, and saves one PNG per view. Nothing on your PC is read or changed.

    # Linux (ImageMagick's `import` grabs the screen; -dpi 144 renders at 150 %)
    xvfb-run -s "-screen 0 1600x1000x24" python tools/window_shots.py docs/images --readme
    xvfb-run -s "-screen 0 1600x1000x24" python tools/window_shots.py shots           # every view

    # Windows (needs `pip install pillow` for the screen grab)
    python tools/window_shots.py shots
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk

from frametrace import (
    analyze,
    game,
    gamesettings,
    goals,
    gui,
    hotkey,
    presentmon,
    report,
    share,
    sysinfo,
    theme,
    trace,
)

W, H = 1200, 820


# --- demo data --------------------------------------------------------------------------------


def demo_system(ram_mts: int = 5600) -> sysinfo.SystemInfo:
    """The developer's PC from the handover: 7800X3D, RTX 4070 Ti SUPER, DDR5, 280 Hz OLED."""
    si = sysinfo.SystemInfo(os_build="26300.7171", os_release="26H2")
    sysinfo.apply_hardware(
        si,
        {
            "os": {"Caption": "Microsoft Windows 11 Home"},
            "cpu": {
                "Name": "AMD Ryzen 7 7800X3D 8-Core Processor",
                "NumberOfCores": 8,
                "NumberOfLogicalProcessors": 16,
            },
            "gpu": {
                "Name": "NVIDIA GeForce RTX 4070 Ti SUPER",
                "DriverVersion": "32.0.16.2140",
                "AdapterCompatibility": "NVIDIA",
            },
            "ram": [
                {
                    "Capacity": 17179869184,
                    "Speed": 4800,
                    "ConfiguredClockSpeed": ram_mts,
                    "SMBIOSMemoryType": 34,
                    "PartNumber": "CMH32GX5M2B5600Z36",
                }
            ]
            * 2,
            "board": {
                "Manufacturer": "ASUSTeK COMPUTER INC.",
                "Product": "TUF GAMING B650-PLUS WIFI",
            },
            "bios": {"SMBIOSBIOSVersion": "3287", "ReleaseDate": "2025-08-12"},
            "vbs_services": [0, 2],
        },
    )
    si.power_plan, si.game_mode, si.hags, si.windowed_optimizations = "Balanced", True, None, True
    si.displays = [
        sysinfo.Display("XG27AQWMG", 2560, 1440, 280, 280, True),
        sysinfo.Display("Portrait", 1080, 1920, 260, 260, False),
    ]
    return si


def frames(
    seed: int,
    seconds: float,
    base_ms: float,
    gpu_share: float,
    cpu_ms: float,
    cap_fps: float | None = None,
    latency_ms: float | None = None,
    hitches: tuple[tuple[float, float], ...] = (),
    gpu_columns: bool = True,
    app: str = "cs2.exe",
) -> list[dict]:
    """A capture with scene changes (slow waves), noise, rare spikes and a few hitches."""
    rnd = random.Random(seed)
    rows, t = [], 0.0
    pending = sorted(hitches)
    while t < seconds:
        scene = (
            1 + 0.18 * math.sin(t / 7.3) + 0.1 * math.sin(t / 2.1 + 1.3)
            + 0.14 * math.exp(-(((t - 38) / 6) ** 2)) - 0.2 * math.exp(-(((t - 91) / 3) ** 2))
        )  # fmt: skip
        gpu = max(0.3, base_ms * gpu_share * scene + rnd.gauss(0, 0.05 * base_ms))
        cpu = max(0.3, cpu_ms * (1 + 0.12 * math.sin(t / 5.1)) + rnd.gauss(0, 0.04 * cpu_ms))
        ft = max(gpu / 0.97, cpu) + abs(rnd.gauss(0, 0.015 * base_ms))
        if cap_fps:
            ft = max(ft, 1000 / cap_fps * (1 + rnd.gauss(0, 0.004)))
        if rnd.random() < 0.006:
            ft += rnd.uniform(0.3, 0.8) * base_ms  # visible in the band, not a hitch
        if pending and t >= pending[0][0]:
            ft = pending.pop(0)[1]
        rows.append(
            {
                "app": app, "pid": 7, "swapchain": "0x1", "runtime": "DXGI",
                "present_mode": "Hardware: Independent Flip", "allows_tearing": 1,
                "sync_interval": 0, "time_s": t, "ms_between_presents": ft, "ms_frame_time": ft,
                "ms_cpu_busy": min(cpu, ft), "ms_cpu_wait": max(0.0, ft - cpu) * 0.1,
                "ms_gpu_busy": gpu if gpu_columns else None, "ms_between_display_change": ft,
                "ms_pc_latency": (
                    max(2.0, latency_ms * scene * rnd.lognormvariate(0, 0.18)) if latency_ms else None
                ),
            }
        )  # fmt: skip
        t += ft / 1000
    return rows


CS2 = game.GameInfo(
    exe="cs2.exe", name="Counter-Strike 2", name_source="steam", store="Steam", store_id="730",
    build="20864571", engine="Source 2", version="1.41.1.6",
)  # fmt: skip
CS2_VIDEO = [
    ("defaultres", "2560"), ("defaultresheight", "1440"), ("fullscreen", "1"),
    ("mat_vsync", "0"), ("msaa_samples", "4"), ("r_csgo_cmaa_enable", "0"),
    ("videocfg_shadow_quality", "2"), ("videocfg_dynamic_shadows", "1"),
    ("videocfg_texture_detail", "1"), ("r_texturefilteringquality", "5"),
    ("shaderquality", "0"), ("videocfg_particle_detail", "1"), ("videocfg_ao_detail", "0"),
    ("videocfg_hdr_detail", "3"), ("videocfg_fsr_detail", "0"), ("r_low_latency", "1"),
]  # fmt: skip


def cs2_settings(**changes) -> gamesettings.GameSettings:
    return gamesettings.GameSettings(
        "Source 2 video config",
        r"C:\Program Files (x86)\Steam\userdata\<account>\730\local\cfg\cs2_video.txt",
        [(k, changes.get(k, v)) for k, v in CS2_VIDEO],
    )


def write_capture(
    root: Path,
    name: str,
    started: str,
    rows: list[dict],
    ram_mts=5600,
    settings=None,
    goal=None,
    user=None,
) -> None:
    app = rows[0]["app"]
    info = CS2 if app == "cs2.exe" else game.GameInfo(exe=app)
    if app == "DayZ_x64.exe":
        info = game.GameInfo(exe=app, name="DayZ", name_source="version info", engine=None)
    result = report.build_result(
        analyze.analyze(rows, app, 7),
        demo_system(ram_mts),
        {"reason": "hotkey", "started": started, "requested_s": None},
        game=info,
        settings=settings,
        goal=goal,
    )
    if user:
        result["user"] = user
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "result.json").write_text(json.dumps(result), encoding="utf-8")
    tr = trace.build(rows)
    if tr:
        trace.save(tr, folder)


def demo_captures(root: Path) -> None:
    hitches = ((23.0, 9.6), (61.4, 14.8), (84.2, 11.2))
    write_capture(
        root, "20261126-2241-cs2", "2026-11-26T22:41:00+01:00",
        frames(1, 100, 2.31, 0.94, 1.0, latency_ms=6.6, hitches=hitches),
        settings=cs2_settings(videocfg_shadow_quality="1"), goal={"key": "lows"},
        user={"label": "Shadows medium", "group": "Benchmark map"},
    )  # fmt: skip
    write_capture(
        root, "20261126-2234-cs2", "2026-11-26T22:34:00+01:00",
        frames(2, 100, 2.28, 0.94, 1.0, latency_ms=7.1, hitches=hitches[1:]),
        settings=cs2_settings(), goal={"key": "lows"},
        user={"label": "Baseline", "group": "Benchmark map"},
    )  # fmt: skip
    write_capture(
        root, "20261126-2211-cs2", "2026-11-26T22:11:00+01:00",
        frames(3, 60, 2.3, 0.5, 1.0, cap_fps=200),
        settings=cs2_settings(), goal={"key": "target", "target_fps": 200},
    )  # fmt: skip
    write_capture(
        root, "20261126-2140-dayz", "2026-11-26T21:40:00+01:00",
        frames(4, 60, 7.4, 0.45, 7.1, hitches=((14.0, 31.0), (47.5, 26.0)), app="DayZ_x64.exe"),
    )  # fmt: skip
    write_capture(
        root, "20261126-2120-fh6", "2026-11-26T21:20:00+01:00",
        frames(5, 9, 3.0, 0.9, 1.4, gpu_columns=False, app="ForzaHorizon6.exe"),
    )  # fmt: skip


# --- window -----------------------------------------------------------------------------------


class _Listener:
    def __init__(self, key, cb):
        self.hotkey = key

    def start_and_wait(self):
        return None

    def is_alive(self):
        return True

    def stop(self):
        pass


class _Recording:
    state, length_s, exe = "recording", 30, None

    def elapsed(self) -> float:
        return 12.4


def grab(root: tk.Tk, path: Path) -> None:
    for _ in range(8):
        root.update()
    w, h = root.winfo_width(), root.winfo_height()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    if shutil.which("import") and sys.platform != "win32":
        crop = f"{w}x{h}+{x}+{y}"
        subprocess.run(["import", "-window", "root", "-crop", crop, str(path)], check=True)
    else:
        from PIL import ImageGrab

        ImageGrab.grab(bbox=(x, y, x + w, y + h)).save(path)
    print("wrote", path)


def _offline(method, url, body, ctype):
    """Sharing in screenshots never reaches the server."""
    return 200, b'{"ok": true, "changed": true, "csv_upload": null}'


def open_window(theme_name: str, captures: Path, setup_missing=False, sharing="off"):
    """sharing: "off" (said no), "ask" (not asked yet: the consent banner) or "on"."""
    tmp = Path(tempfile.mkdtemp())
    gui.SETTINGS_PATH = tmp / "settings.json"
    settings = {"theme": theme_name, "share": {"off": False, "ask": None, "on": True}[sharing]}
    if sharing == "on":
        settings["share_version"] = share.CONSENT_VERSION
    gui.SETTINGS_PATH.write_text(json.dumps(settings), encoding="utf-8")
    share.STATE_PATH = tmp / "shared.json"
    share.request = _offline
    hotkey.HotkeyListener = _Listener
    sysinfo.collect = demo_system
    sysinfo.refresh_settings = lambda s: s
    if setup_missing:

        def missing():
            raise presentmon.PresentMonNotFound("demo")

        presentmon.find_presentmon = missing
    else:
        presentmon.find_presentmon = lambda: Path("PresentMon-2.6.0-x64.exe")
        presentmon.identify = lambda exe: "2.6.0"
        presentmon.can_trace = lambda: (True, "")
    root = tk.Tk()
    app = gui.App(root, captures_root=captures)
    root.geometry(f"{theme.px(W)}x{theme.px(H)}+0+0")
    app.handle("system", {"info": demo_system()})
    for folder, _ in app.captures:  # traces load on threads in the app; here, at once
        app.handle("trace", {"folder": folder, "trace": trace.load(folder)})
    return root, app


def _shoot_and_close(root: tk.Tk, path: Path) -> None:
    """Screenshot an open dialog, then close it with Escape."""
    grab(root, path)
    focus = root.focus_get()
    if focus:
        focus.event_generate("<Escape>")


def shots(out: Path, themes: list[str], readme: bool) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = Path(tempfile.mkdtemp()) / "captures"
    demo_captures(data)
    empty = Path(tempfile.mkdtemp()) / "captures"
    empty.mkdir()
    for name in themes:
        root, app = open_window(name, data)
        if readme:
            grab(root, out / f"window-{name}.png")
            app.on_close()
            continue
        grab(root, out / f"{name}-summary.png")
        app.page_summary.canvas.yview_moveto(1.0)
        grab(root, out / f"{name}-summary-bottom.png")
        app.page_summary.canvas.yview_moveto(0.0)
        for tab in ("Report", "Game", "System"):
            app.tabs.select(tab)
            grab(root, out / f"{name}-{tab.lower()}.png")
        folders = [f for f, _ in app.captures]
        app.select(folders[1], add=False)
        app.select(folders[0], add=True)
        grab(root, out / f"{name}-compare.png")
        app.page_compare.canvas.yview_moveto(1.0)
        grab(root, out / f"{name}-compare-bottom.png")
        for i, tag in ((2, "capped"), (3, "cpu"), (4, "no-gpu")):
            app.select(folders[i], add=False)
            grab(root, out / f"{name}-{tag}.png")
        app.ask_delete([folders[3]])
        grab(root, out / f"{name}-confirm-delete.png")
        app.cancel_confirm()
        app.toggle_group("Benchmark map")
        grab(root, out / f"{name}-group-folded.png")
        app.toggle_group("Benchmark map")
        root.after(400, _shoot_and_close, root, out / f"{name}-rename-dialog.png")
        app.rename_capture(folders[0])
        app.select(folders[3], add=False)
        app.tabs.select("Game")
        grab(root, out / f"{name}-game-unread.png")
        app.tabs.select("Summary")
        app.goal_var.set(goals.GOALS["target"].label)
        app.target_var.set("144")
        app.apply_goal()
        grab(root, out / f"{name}-goal-target.png")
        app.goal_var.set(goals.GOALS["avg_fps"].label)
        app.target_var.set("")
        app.apply_goal()
        app.select(folders[0], add=False)
        app.recorder = _Recording()
        app.handle("started", {"foreground": "cs2.exe"})
        grab(root, out / f"{name}-recording.png")
        app.recorder = None
        app.on_close()
        root, app = open_window(name, data, sharing="ask")
        grab(root, out / f"{name}-share-ask.png")
        app.consent_yes()
        for _ in range(100):  # let the (offline) sync finish, then handle its event
            root.after(50)
            root.update()
            while not app.events.empty():
                app.handle(*app.events.get())
            if not app.share_busy:
                break
        grab(root, out / f"{name}-share-on.png")
        app.ask_forget()
        grab(root, out / f"{name}-share-delete.png")
        app.cancel_confirm()
        app.on_close()
        root, app = open_window(name, empty, setup_missing=True)
        grab(root, out / f"{name}-setup.png")
        app.on_close()


def main() -> None:
    if sys.platform == "win32":  # screen coordinates in real pixels for the grab
        import ctypes

        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("out", type=Path, help="folder for the PNGs")
    p.add_argument(
        "--readme", action="store_true", help="only window-dark.png and window-light.png"
    )
    p.add_argument("--theme", choices=["dark", "light"], help="one theme only")
    a = p.parse_args()
    shots(a.out, [a.theme] if a.theme else ["dark", "light"], a.readme)


if __name__ == "__main__":
    main()
