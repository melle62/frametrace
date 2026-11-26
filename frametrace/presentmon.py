"""Locating and driving the PresentMon console application.

Frametrace pins one PresentMon version so the CSV format is predictable.
columns.py still detects the schema from the header, so a user-supplied
PresentMon of another version keeps working.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PINNED_VERSION = "2.6.0"
EXE_NAME = f"PresentMon-{PINNED_VERSION}-x64.exe"
DOWNLOAD_URL = (
    f"https://github.com/GameTechDev/PresentMon/releases/download/v{PINNED_VERSION}/{EXE_NAME}"
)
EXE_SHA256 = "b2a706bc6ad475749e3b7e3409263aa1e6906d45bdcf993f6dbc0f660188f1af"
# Intel's notices must ship next to the exe whenever we redistribute it (MIT).
NOTICE_URLS = {
    "PresentMon-LICENSE.txt": f"https://raw.githubusercontent.com/GameTechDev/PresentMon/v{PINNED_VERSION}/LICENSE.txt",
    "PresentMon-THIRD_PARTY.txt": f"https://raw.githubusercontent.com/GameTechDev/PresentMon/v{PINNED_VERSION}/THIRD_PARTY.txt",
}

SESSION_NAME = "Frametrace"
REPO_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = REPO_ROOT / "bin"
PERF_LOG_USERS_SID = "S-1-5-32-559"  # BUILTIN\Performance Log Users


class PresentMonNotFound(FileNotFoundError):
    pass


def find_presentmon(explicit: str | os.PathLike | None = None) -> Path:
    """Find the PresentMon console exe: explicit path, $FRAMETRACE_PRESENTMON, ./bin, PATH."""
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    if env := os.environ.get("FRAMETRACE_PRESENTMON"):
        candidates.append(Path(env))
    candidates.append(BIN_DIR / EXE_NAME)
    candidates.extend(sorted(BIN_DIR.glob("PresentMon*.exe"), reverse=True))
    for name in (EXE_NAME, "PresentMon.exe", "PresentMon-x64.exe"):
        if found := shutil.which(name):
            candidates.append(Path(found))
    for c in candidates:
        if c.is_file():
            return c
    raise PresentMonNotFound(
        "PresentMon console exe not found. Run `python tools/get_presentmon.py`, "
        "or pass its path, or set FRAMETRACE_PRESENTMON."
    )


def is_admin() -> bool:
    if sys.platform != "win32":
        return False
    import ctypes

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def in_perf_log_users() -> bool | None:
    """True if the current user's token has the Performance Log Users group. None if unknown."""
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(
            ["whoami", "/groups"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=0x08000000,  # CREATE_NO_WINDOW: no console flash from the GUI
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return PERF_LOG_USERS_SID in out


def can_trace() -> tuple[bool, str]:
    """PresentMon needs admin rights or Performance Log Users membership (ETW access)."""
    if is_admin():
        return True, "running as administrator"
    member = in_perf_log_users()
    if member:
        return True, "user is in Performance Log Users"
    if member is None:
        return False, "could not determine privileges"
    return False, (
        "not elevated and not in Performance Log Users. Run as administrator, or add your "
        "account to the group once (see docs/presentmon.md) and sign out and back in."
    )


def identify(exe: Path) -> str:
    """Which PresentMon this is. The console exe has no --version flag and no version
    resource, so the pinned build is recognised by its SHA-256, anything else by file name."""
    try:
        if hashlib.sha256(exe.read_bytes()).hexdigest() == EXE_SHA256:
            return f"{PINNED_VERSION} (SHA-256 verified)"
    except OSError:
        pass
    if m := re.search(r"PresentMon-(\d+\.\d+\.\d+)", exe.name, re.IGNORECASE):
        return f"{m.group(1)} (from file name, not verified)"
    return "unknown (not the pinned build)"


def capture_command(
    exe: Path,
    output_csv: Path,
    *,
    session_name: str = SESSION_NAME,
    process_id: int | None = None,
    process_names: tuple[str, ...] = (),
    timed_s: float | None = None,
    extra: tuple[str, ...] = (),
) -> list[str]:
    """Command line for one recording. With no process filter, all processes are captured."""
    cmd = [
        str(exe),
        "--output_file",
        str(output_csv),
        "--session_name",
        session_name,
        "--stop_existing_session",
        "--no_console_stats",
        # Read NVIDIA's PC Latency Stats markers (sent by games with Reflex / Streamline).
        # Adds MsPCLatency; values stay NA for games that don't send the markers.
        "--track_pc_latency",
    ]
    if process_id is not None:
        cmd += ["--process_id", str(process_id)]
    for name in process_names:
        cmd += ["--process_name", name]
    if timed_s is not None:
        cmd += ["--timed", str(int(timed_s)), "--terminate_after_timed"]
    cmd += list(extra)
    return cmd


def terminate_command(exe: Path, session_name: str = SESSION_NAME) -> list[str]:
    """Stops a running recording cleanly: the recording PresentMon flushes its CSV and exits."""
    return [str(exe), "--session_name", session_name, "--terminate_existing_session"]


def read_console_log(path: Path) -> str:
    """PresentMon writes UTF-16 to a redirected console, other tools write UTF-8."""
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    elif b"\x00" in raw[:200]:
        text = raw.decode("utf-16-le", errors="replace")
    else:
        text = raw.decode("utf-8", errors="replace")
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())
