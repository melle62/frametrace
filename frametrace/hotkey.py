"""Global hotkey via RegisterHotKey (not a keyboard hook, so it stays out of anti-cheat's way).

The hotkey is registered on a dedicated thread with its own message loop, because
Windows delivers WM_HOTKEY to the thread that registered it.
"""

from __future__ import annotations

import logging
import sys
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

MODIFIERS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

KEYS: dict[str, int] = {f"f{i}": 0x6F + i for i in range(1, 25)}
KEYS.update({chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)})
KEYS.update({str(d): ord(str(d)) for d in range(10)})
KEYS.update({f"numpad{d}": 0x60 + d for d in range(10)})
KEYS.update(
    {
        "scrolllock": 0x91,
        "pause": 0x13,
        "insert": 0x2D,
        "delete": 0x2E,
        "home": 0x24,
        "end": 0x23,
        "pageup": 0x21,
        "pagedown": 0x22,
        "printscreen": 0x2C,
    }
)
SUGGESTED = ["F10", "F9", "F11", "Ctrl+F10", "Alt+F10", "ScrollLock", "Pause", "Insert"]


def parse_hotkey(text: str) -> tuple[int, int]:
    """'Ctrl+Shift+F9' -> (modifiers, virtual-key code). Raises ValueError if invalid."""
    parts = [p.strip().lower().replace(" ", "") for p in text.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty hotkey")
    *mods, key = parts
    if key not in KEYS:
        raise ValueError(f"unknown key '{key}'")
    modifiers = 0
    for m in mods:
        if m not in MODIFIERS:
            raise ValueError(f"unknown modifier '{m}' (use Ctrl, Alt, Shift, Win)")
        modifiers |= MODIFIERS[m]
    if key == "f12" and modifiers == 0:
        raise ValueError("F12 alone is reserved by Windows for debuggers")
    return modifiers, KEYS[key]


class HotkeyListener(threading.Thread):
    """Calls callback() (on this thread) each time the hotkey is pressed."""

    def __init__(self, hotkey: str, callback: Callable[[], None]):
        super().__init__(name="frametrace-hotkey", daemon=True)
        self.hotkey = hotkey
        self.modifiers, self.vk = parse_hotkey(hotkey)
        self.callback = callback
        self.error: str | None = None
        self._ready = threading.Event()
        self._thread_id = 0

    def run(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32")
        self._thread_id = kernel32.GetCurrentThreadId()
        if not user32.RegisterHotKey(None, 1, self.modifiers | MOD_NOREPEAT, self.vk):
            self.error = f"{self.hotkey} is already in use by another program"
            self._ready.set()
            return
        self._ready.set()
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY:
                    try:
                        self.callback()
                    except Exception:  # never let the listener thread die
                        log.exception("hotkey callback failed")
        finally:
            user32.UnregisterHotKey(None, 1)

    def start_and_wait(self, timeout: float = 2.0) -> str | None:
        """Start listening. Returns an error message, or None on success."""
        if sys.platform != "win32":
            return "global hotkeys only work on Windows"
        self.start()
        self._ready.wait(timeout)
        return self.error

    def stop(self) -> None:
        if self._thread_id and self.is_alive():
            import ctypes

            ctypes.WinDLL("user32").PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            self.join(timeout=2)
