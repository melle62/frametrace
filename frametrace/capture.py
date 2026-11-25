"""Hotkey-driven recording (next step 3).

Plan: register a global hotkey (default F10) with RegisterHotKey. On the first press,
note the foreground process (process.get_foreground_process) and start PresentMon for
all processes (presentmon.capture_command). On the second press, stop it with
presentmon.terminate_command, then pick the game with process.pick_target.
"""
