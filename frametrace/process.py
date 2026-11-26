"""Finding the game process without any game-specific configuration.

Strategy (see docs/presentmon.md, "Game auto-detection"):

1. When the user presses the hotkey, note the foreground window's process ID.
2. Capture *all* presenting processes, not just that PID. This survives launchers
   that hand off to a child process, UWP/Store games whose window belongs to
   ApplicationFrameHost.exe, and games that render from a helper process.
3. After the capture, pick the target: the foreground PID if it presented frames,
   otherwise the process that presented the most frames, ignoring a short list
   of known non-game presenters (compositor, shell, browsers, overlays).

The user can always override with an explicit process name or PID.
"""

from __future__ import annotations

import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

# Processes that present frames but are never the game. Lowercase exe names.
# This is a list of desktop/system software, not games, so it does not break
# the "no game-specific code in the core" rule.
NON_GAME_PROCESSES = frozenset(
    {
        "dwm.exe",
        "explorer.exe",
        "applicationframehost.exe",
        "shellexperiencehost.exe",
        "startmenuexperiencehost.exe",
        "searchhost.exe",
        "textinputhost.exe",
        "gamebar.exe",
        "gamebarftserver.exe",
        "steamwebhelper.exe",
        "msedgewebview2.exe",
        "chrome.exe",
        "msedge.exe",
        "firefox.exe",
        "brave.exe",
        "opera.exe",
        "discord.exe",
        "obs64.exe",
        "nvidia overlay.exe",
        "nvidia app.exe",
        "radeonsoftware.exe",
        "presentmon.exe",
        "<unknown>",
    }
)

MIN_FRAMES = 30  # a process needs at least this many presents to count as a candidate


@dataclass
class Presenter:
    pid: int
    name: str
    frames: int = 0
    first_s: float | None = None
    last_s: float | None = None
    runtimes: Counter = field(default_factory=Counter)
    present_modes: Counter = field(default_factory=Counter)
    swapchains: Counter = field(default_factory=Counter)

    @property
    def avg_fps(self) -> float | None:
        if self.first_s is None or self.last_s is None or self.last_s <= self.first_s:
            return None
        return (self.frames - 1) / (self.last_s - self.first_s)

    @property
    def main_swapchain(self) -> str | None:
        return self.swapchains.most_common(1)[0][0] if self.swapchains else None

    @property
    def is_known_non_game(self) -> bool:
        return self.name.lower() in NON_GAME_PROCESSES


def summarize_presenters(frames: Iterable[dict]) -> list[Presenter]:
    """Group canonical frame rows by process. Sorted by frame count, highest first."""
    by_pid: dict[int, Presenter] = {}
    for row in frames:
        pid = row.get("pid")
        if pid is None:
            continue
        p = by_pid.get(pid)
        if p is None:
            p = by_pid[pid] = Presenter(pid=pid, name=row.get("app") or "<unknown>")
        p.frames += 1
        t = row.get("time_s")
        if t is not None:
            p.first_s = t if p.first_s is None else min(p.first_s, t)
            p.last_s = t if p.last_s is None else max(p.last_s, t)
        p.runtimes[row.get("runtime") or "?"] += 1
        p.present_modes[row.get("present_mode") or "?"] += 1
        p.swapchains[row.get("swapchain") or "?"] += 1
    return sorted(by_pid.values(), key=lambda p: p.frames, reverse=True)


def pick_target(
    presenters: list[Presenter],
    foreground_pid: int | None = None,
    *,
    process_name: str | None = None,
    min_frames: int = MIN_FRAMES,
    exclude_pids: frozenset[int] | set[int] = frozenset(),
) -> tuple[Presenter | None, str]:
    """Choose the game among the presenting processes. Returns (presenter, reason)."""
    presenters = [p for p in presenters if p.pid not in exclude_pids]
    if process_name:
        wanted = process_name.lower()
        named = [p for p in presenters if p.name.lower() == wanted]
        if named:
            return named[0], f"matched --process-name {process_name}"
        return None, f"no process named {process_name} presented any frames"

    if foreground_pid is not None:
        for p in presenters:
            if p.pid == foreground_pid and p.frames >= min_frames:
                return p, "foreground window process"

    candidates = [p for p in presenters if not p.is_known_non_game and p.frames >= min_frames]
    if candidates:
        why = "most frames presented"
        if foreground_pid is not None:
            why += f" (foreground PID {foreground_pid} presented fewer than {min_frames} frames)"
        return candidates[0], why
    return None, "no process presented enough frames"


# --- Windows foreground window -------------------------------------------------------------


@dataclass(frozen=True)
class ForegroundProcess:
    pid: int
    exe: str | None  # full image path, None if the process could not be opened
    window_title: str

    @property
    def name(self) -> str | None:
        return self.exe.replace("/", "\\").rsplit("\\", 1)[-1] if self.exe else None


def get_foreground_process() -> ForegroundProcess | None:
    """PID, image path and window title of the foreground window. Windows only."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, 256)

    exe = None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if handle:  # can fail for protected (e.g. anti-cheat) processes; the PID is still valid
        try:
            buf = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buf))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
                exe = buf.value
        finally:
            kernel32.CloseHandle(handle)
    return ForegroundProcess(pid=pid.value, exe=exe, window_title=title.value)
