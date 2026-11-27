"""Recording controller: start/stop PresentMon, pick the game, analyze, save the result.

One recording at a time. start()/stop()/toggle() can be called from any thread (the
hotkey thread, a timer, the GUI); work happens on worker threads and progress is
reported through on_event(kind, payload):

    "started"   {"foreground": name or None, "length_s": int or None, "folder": Path}
    "stopping"  {}
    "done"      {"result": dict, "folder": Path, "report": str}
    "error"     {"message": str}
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from frametrace import (
    analyze,
    columns,
    game,
    gamesettings,
    goals,
    presentmon,
    process,
    report,
    sysinfo,
    trace,
)

log = logging.getLogger(__name__)
CREATE_NO_WINDOW = 0x08000000
DEFAULT_ROOT = Path.home() / "Documents" / "Frametrace" / "captures"
STOP_TIMEOUT_S = 15


class CaptureError(RuntimeError):
    pass


@dataclass
class CaptureSettings:
    length_s: int | None = 30  # None = manual: runs until stopped
    process_name: str | None = None  # None = auto-detect
    goal: str = goals.DEFAULT_GOAL  # see goals.GOALS
    target_fps: int | None = None  # for the "target" goal; None = display refresh rate
    benchmark: str | None = None  # the user's tag for the scene, e.g. "Mirage Benchmark"


def _popen_flags() -> int:
    return CREATE_NO_WINDOW if os.name == "nt" else 0


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")[:40] or "capture"


class Recorder:
    def __init__(
        self,
        exe: Path,
        on_event: Callable[[str, dict], None],
        root: Path | None = None,
        system_provider: Callable[[], sysinfo.SystemInfo] | None = None,
    ):
        self.exe = exe
        self.on_event = on_event
        self.root = root or DEFAULT_ROOT
        self.system_provider = system_provider or (lambda: sysinfo.collect())
        self.state = "idle"  # idle | recording | analyzing
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._log_file = None
        self._timer: threading.Timer | None = None
        self._started_at = 0.0
        self._ctx: dict = {}

    # --- control ---------------------------------------------------------------------------

    def toggle(self, settings: CaptureSettings) -> None:
        if self.state == "idle":
            self.start(settings)
        elif self.state == "recording":
            self.stop()

    @property
    def length_s(self) -> int | None:
        """Fixed length of the current recording, None when it's manual or not recording."""
        settings = self._ctx.get("settings") if self.state == "recording" else None
        return settings.length_s if settings else None

    def elapsed(self) -> float:
        return time.monotonic() - self._started_at if self.state == "recording" else 0.0

    def start(self, settings: CaptureSettings) -> None:
        with self._lock:
            if self.state != "idle":
                return
            fg = process.get_foreground_process()
            stamp = dt.datetime.now().astimezone()
            folder = self.root / stamp.strftime("%Y%m%d-%H%M%S")
            try:
                folder.mkdir(parents=True, exist_ok=True)
                csv_path = folder / "presentmon.csv"
                self._log_file = open(folder / "presentmon.log", "wb")  # noqa: SIM115
                cmd = presentmon.capture_command(self.exe, csv_path)
                self._proc = subprocess.Popen(
                    cmd,
                    stdout=self._log_file,
                    stderr=subprocess.STDOUT,
                    creationflags=_popen_flags(),
                )
            except OSError as e:
                self._close_log()
                self.on_event("error", {"message": f"Couldn't start PresentMon: {e}"})
                return
            self.state = "recording"
            self._started_at = time.monotonic()
            self._ctx = {
                "folder": folder,
                "csv": csv_path,
                "fg": fg,
                "settings": settings,
                "started": stamp.isoformat(timespec="seconds"),
            }
            if settings.length_s:
                self._timer = threading.Timer(settings.length_s, self.stop)
                self._timer.daemon = True
                self._timer.start()
        threading.Thread(target=self._watch_startup, daemon=True).start()
        self.on_event(
            "started",
            {
                "foreground": fg.name if fg else None,
                "length_s": settings.length_s,
                "folder": folder,
            },
        )

    def stop(self) -> None:
        with self._lock:
            if self.state != "recording":
                return
            self.state = "analyzing"
            if self._timer:
                self._timer.cancel()
                self._timer = None
            duration = time.monotonic() - self._started_at
        self.on_event("stopping", {})
        threading.Thread(target=self._finish, args=(duration,), daemon=True).start()

    # --- workers ---------------------------------------------------------------------------

    def _watch_startup(self) -> None:
        """PresentMon exits right away when it lacks privileges; report that clearly."""
        time.sleep(2.0)
        proc = self._proc
        if self.state == "recording" and proc is not None and proc.poll() is not None:
            with self._lock:
                if self.state != "recording":
                    return
                self.state = "idle"
                if self._timer:
                    self._timer.cancel()
            self._close_log()
            text = presentmon.read_console_log(self._ctx["folder"] / "presentmon.log")
            self.on_event("error", {"message": "PresentMon stopped right away:\n" + text[-800:]})

    def _stop_presentmon(self) -> str:
        proc = self._proc
        try:
            subprocess.run(
                presentmon.terminate_command(self.exe),
                capture_output=True,
                timeout=30,
                check=False,
                creationflags=_popen_flags(),
            )
        except (OSError, subprocess.SubprocessError) as e:
            log.warning("terminate_existing_session failed: %s", e)
        if proc is None:
            return "not running"
        try:
            proc.wait(timeout=STOP_TIMEOUT_S)
            return "terminate_existing_session"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
            return "killed (CSV may be incomplete)"

    def _finish(self, duration: float) -> None:
        stop_method = self._stop_presentmon()
        self._close_log()
        ctx = self._ctx
        try:
            result, folder = self._analyze(ctx, duration, stop_method)
            text = report.render(result)
            (folder / "report.md").write_text(text, encoding="utf-8")
            self.on_event("done", {"result": result, "folder": folder, "report": text})
        except Exception as e:  # report every failure to the user, never crash the thread
            log.exception("analysis failed")
            self.on_event("error", {"message": str(e)})
        finally:
            with self._lock:
                self.state = "idle"
                self._proc = None

    def _analyze(self, ctx: dict, duration: float, stop_method: str) -> tuple[dict, Path]:
        csv_path: Path = ctx["csv"]
        if not csv_path.is_file() or csv_path.stat().st_size == 0:
            raise CaptureError("PresentMon didn't write any data.")
        # Two passes over the file: every process is only counted, and only the game's
        # frames are kept in memory (a long capture of all processes can be large).
        with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
            cmap, rows = columns.iter_frames(f)
            if not cmap.has(*columns.REQUIRED_FOR["frame_stats"]):
                missing = ", ".join(cmap.missing(columns.REQUIRED_FOR["frame_stats"]))
                raise CaptureError(
                    f"This PresentMon CSV is missing columns Frametrace needs: {missing}"
                )
            presenters = process.summarize_presenters(rows)
        fg = ctx["fg"]
        settings: CaptureSettings = ctx["settings"]
        target, reason = process.pick_target(
            presenters,
            fg.pid if fg else None,
            process_name=settings.process_name,
            exclude_pids={os.getpid()},
        )
        if target is None:
            seen = ", ".join(f"{p.name} ({p.frames})" for p in presenters[:5]) or "nothing"
            raise CaptureError(
                f"No game found: {reason}. Presenting processes: {seen}. "
                "Was the game in the foreground and rendering? Some anti-cheats block tracing."
            )
        with open(csv_path, newline="", encoding="utf-8-sig", errors="replace") as f:
            _, rows = columns.iter_frames(f)
            main = [
                r
                for r in rows
                if r.get("pid") == target.pid and r.get("swapchain") == target.main_swapchain
            ]
        analysis = analyze.analyze(main, target.name, target.pid)
        meta = {
            "started": ctx["started"],
            "requested_s": settings.length_s,
            "recorded_s": round(duration, 1),
            "reason": reason,
            "foreground": fg.name if fg else None,
            "presentmon": presentmon.identify(self.exe),
            "csv_schema": cmap.schema.value,
            "stop_method": stop_method,
            "other_presenters": [p.name for p in presenters if p.pid != target.pid][:5],
        }
        info, found = identify_game(target, fg)
        result = report.build_result(
            analysis,
            self.system_provider(),
            meta,
            game=info,
            settings=found,
            goal={"key": settings.goal, "target_fps": settings.target_fps},
        )
        tag = (settings.benchmark or "").strip()[:80]
        if tag:  # the scene the user named before the run; the list keeps one base per tag
            result["user"] = {**(result.get("user") or {}), "benchmark": tag}

        folder: Path = ctx["folder"]
        named = folder.with_name(f"{folder.name}-{_safe(target.name.removesuffix('.exe'))}")
        try:
            folder.rename(named)
            folder = named
        except OSError:
            pass
        (folder / "result.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
        try:  # the scope view is a bonus: never fail a capture over it
            tr = trace.build(main, skip_start_s=analysis.skipped_start_s)
            if tr is not None:
                trace.save(tr, folder)
        except Exception:
            log.exception("could not save trace.json")
        return result, folder

    def _close_log(self) -> None:
        if self._log_file:
            try:
                self._log_file.close()
            except OSError:
                pass
            self._log_file = None


def identify_game(
    target: process.Presenter, fg
) -> tuple[game.GameInfo, gamesettings.GameSettings | None]:
    """Name, store entry and engine of the captured game, and its in-game settings."""
    same = fg is not None and fg.pid == target.pid
    path = process.image_path(target.pid) or (fg.exe if same else None)
    info = game.identify(target.name, path, fg.window_title if same else None)
    return info, gamesettings.read(info)


def list_captures(root: Path | None = None) -> list[tuple[Path, dict]]:
    """Saved captures, newest first."""
    root = root or DEFAULT_ROOT
    out = []
    if not root.is_dir():
        return out
    for folder in sorted(root.iterdir(), reverse=True):
        f = folder / "result.json"
        if f.is_file():
            try:
                out.append((folder, json.loads(f.read_text(encoding="utf-8"))))
            except (OSError, ValueError):
                continue
    return out


# --- organizing saved captures ----------------------------------------------------------------


def save_user(folder: Path, **fields: str | None) -> dict:
    """Set the user's label or group on a saved capture; None or "" clears a field.

    Kept in result.json under "user", so it travels with the folder and the report and
    comparison can show it. Written to a temporary file first, so a crash can't truncate
    the result.
    """
    path = folder / "result.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    user = dict(result.get("user") or {})
    for key, value in fields.items():
        value = (value or "").strip()
        if value:
            user[key] = value[:80]
        else:
            user.pop(key, None)
    result["user"] = user
    tmp = path.with_name("result.json.tmp")
    tmp.write_text(json.dumps(result, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return result


def _recycle(path: Path) -> bool:
    """Move a folder to the Windows Recycle Bin. False when that isn't possible."""
    if os.name != "nt":
        return False
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_ushort),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 0x4, 0x10, 0x40, 0x400
    op = SHFILEOPSTRUCTW(
        wFunc=FO_DELETE,
        pFrom=str(path) + "\0",  # a double-null-terminated list
        fFlags=FOF_SILENT | FOF_NOCONFIRMATION | FOF_ALLOWUNDO | FOF_NOERRORUI,
    )
    ok = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0
    return ok and not op.fAnyOperationsAborted and not path.exists()


def delete_capture(folder: Path, root: Path | None = None) -> str:
    """Delete one saved capture folder. Returns "recycled" or "deleted".

    Only a folder directly inside the captures root that holds a result.json: nothing
    else on the disk can be removed this way. On Windows it goes to the Recycle Bin.
    """
    root = (root or DEFAULT_ROOT).resolve()
    folder = folder.resolve()
    if folder.parent != root or not (folder / "result.json").is_file():
        raise CaptureError(f"Not a Frametrace capture folder: {folder}")
    if _recycle(folder):
        return "recycled"
    shutil.rmtree(folder)
    return "deleted"


def beep(kind: str) -> None:
    """Audible start/stop cue, since the window isn't visible during a game."""
    if os.name != "nt":
        return
    import winsound

    tones = {
        "start": [(880, 90), (1320, 120)],
        "stop": [(1320, 90), (880, 120)],
        "error": [(300, 300)],
    }

    def play() -> None:
        for freq, ms in tones.get(kind, []):
            winsound.Beep(freq, ms)

    threading.Thread(target=play, daemon=True).start()
