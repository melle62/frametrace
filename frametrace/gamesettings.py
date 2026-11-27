"""Read the game's current in-game settings, so the AI knows what to change.

Readers work per engine, not per game: each one knows where an engine keeps its settings
(Unreal's GameUserSettings.ini, Unity's PlayerPrefs in the registry, Source 2's video
config). When none applies, the report asks the AI to get the settings from the user
(pasted or as a screenshot of the graphics menu).

Settings go into a report the user pastes into an AI, so anything that looks like an
account name, ID, token or path is left out.
"""

from __future__ import annotations

import logging
import os
import re
import struct
import sys
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

from frametrace.game import GameInfo, parse_keyvalues, steam_root, unreal_project

log = logging.getLogger(__name__)

MAX_SETTINGS = 80
MAX_VALUE_LEN = 60

# Keys that may hold personal or secret data, or that only add noise.
_PRIVATE = re.compile(
    r"token|password|passwd|secret|auth|session|cookie|e-?mail|account|user|login|"
    r"steam|player_?name|nickname|profile|guid(?!e)|uuid|serial|license|"
    r"(^|[._])id$|(^|[._])ids?([._]|$)|deviceid|vendorid|hardware",
    re.IGNORECASE,
)
_NOISE = re.compile(
    r"^(version|last.*|.*timestamp.*|.*analytics.*|unity\..*|.*crash.*|.*telemetry.*|"
    r"autoconfig|knowndevice|.*position.*|.*windowpos.*|bUseDesired.*)$",
    re.IGNORECASE,
)


@dataclass
class GameSettings:
    reader: str  # "Unreal Engine GameUserSettings.ini"
    source: str  # where they were read from, with the user folder shortened
    settings: list[tuple[str, str]] = field(default_factory=list)  # (key, value) in file order
    modified: float | None = None  # mtime of the source

    def to_dict(self) -> dict:
        d = asdict(self)
        d["settings"] = [list(kv) for kv in self.settings]
        return d


def keep(key: str, value: str) -> bool:
    """Leave out personal data, long blobs, paths and bookkeeping."""
    value = value.strip()
    if not key or _PRIVATE.search(key) or _NOISE.match(key):
        return False
    return not (len(value) > MAX_VALUE_LEN or "\\" in value or "/" in value or "@" in value)


def still_read(reader: str, key: str, value: str) -> bool:
    """Whether today's reader would still report this setting from a saved capture.

    A capture keeps what the reader of its day read. A key a newer reader leaves out (Source 2's
    cpu_level, a stricter privacy filter) isn't something the user changed, while a key a game
    writes only once it's set (Unity PlayerPrefs) is.
    """
    value = str(value)
    if not keep(key, value):
        return False
    if reader.startswith("Source 2") and key in SOURCE2_AUTODETECT:
        return False
    return not (reader.startswith("Unreal") and "(" in value)


def _short(path: Path | str) -> str:
    """Path with the user's home shortened to %USERPROFILE%, so no user name leaks."""
    s = str(path)
    home = str(Path.home())
    if home and s.lower().startswith(home.lower()):
        s = "%USERPROFILE%" + s[len(home) :]
    # Steam keeps per-account files under userdata/<account ID>: leave the ID out
    return re.sub(r"(userdata[\\/])\d+", r"\1<account>", s, flags=re.IGNORECASE)


def _newest(paths: list[Path]) -> Path | None:
    found = []
    for p in paths:
        try:
            if p.is_file():
                found.append((p.stat().st_mtime, p))
        except OSError:
            pass
    return max(found)[1] if found else None


def _mtime(p: Path) -> float | None:
    try:
        return p.stat().st_mtime
    except OSError:
        return None


# --- Source 2 (CS2, Dota 2, Deadlock): video config in KeyValues -----------------------------


# Hardware levels Source 2 detects on its own: not options in the game's menu
SOURCE2_AUTODETECT = frozenset({"cpu_level", "gpu_level", "gpu_mem_level"})


def source2_candidates(game: GameInfo, steam: Path | None) -> list[Path]:
    out: list[Path] = []
    if steam and game.store_id:
        try:
            out += list((steam / "userdata").glob(f"*/{game.store_id}/local/cfg/*video*.txt"))
        except OSError:
            pass
    if game.install_dir:
        try:
            out += list(Path(game.install_dir).glob("game/*/cfg/*video*.txt"))
        except OSError:
            pass
    return out


# Console variables that change rendering or the frame rate. Source engines name them by
# subsystem, so a prefix is enough: no per-game list. Everything else in the convar files
# (crosshair, binds, audio, HUD) stays out of the report.
SOURCE2_CONVAR_PREFIXES = ("fps_max", "r_", "mat_", "engine_low_latency")
MAX_CONVARS = 30


def _number(value: str) -> str:
    """'400.000000' -> '400', '0.500000' -> '0.5'; anything else unchanged."""
    if re.fullmatch(r"-?\d+\.\d+", value):
        return value.rstrip("0").rstrip(".")
    return value


def source2_convar_files(video: Path, game: GameInfo) -> list[Path]:
    """Convar files next to the video config (per account), then the install's machine ones.

    Oldest first, so a newer file's value wins when both hold a key.
    """
    found: list[Path] = []
    try:
        found += list(video.parent.glob("*convars*.vcfg"))
        if game.install_dir:
            found += list(Path(game.install_dir).glob("game/*/cfg/*machine_convars*.vcfg"))
    except OSError:
        return []
    # Shipped defaults (machine_convars_default.vcfg) aren't the user's settings, and a game
    # update gives them a new date, which would let them win over what the user set
    found = [p for p in found if "default" not in p.name.lower()]
    files = [(m, p) for p in found if (m := _mtime(p)) is not None]
    return [p for _, p in sorted(files)]


def read_source2_convars(files: list[Path], skip: set[str]) -> list[tuple[str, str]]:
    """Rendering convars from vcfg files ("config" { "convars" { ... } })."""
    merged: dict[str, str] = {}
    for f in files:
        try:
            kv = parse_keyvalues(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        for block in kv.values():
            convars = block.get("convars") if isinstance(block, dict) else None
            for k, v in (convars or {}).items():
                key = re.sub(r"\$\d+$", "", k)  # fps_max_ui$2: a per-slot copy
                if isinstance(v, str) and key.startswith(SOURCE2_CONVAR_PREFIXES):
                    merged[key] = _number(v.strip())
    return [(k, v) for k, v in sorted(merged.items()) if k not in skip and keep(k, v)][:MAX_CONVARS]


def read_source2(game: GameInfo, steam: Path | None = None) -> GameSettings | None:
    if game.engine != "Source 2":
        return None
    path = _newest(source2_candidates(game, steam if steam is not None else steam_root()))
    if path is None:
        return None
    try:
        kv = parse_keyvalues(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    block = next((v for v in kv.values() if isinstance(v, dict)), {})
    pairs = [(k, v) for k, v in block.items() if isinstance(v, str)]
    prefixed = [(k.removeprefix("setting."), v) for k, v in pairs if k.startswith("setting.")]
    settings = [
        (k, v) for k, v in (prefixed or pairs) if keep(k, v) and k not in SOURCE2_AUTODETECT
    ]
    if not settings:
        return None
    files = source2_convar_files(path, game)
    convars = read_source2_convars(files, {k for k, _ in settings})
    source = _short(path)
    if convars:
        source += " + " + ", ".join(sorted({f.name for f in files}))
        reader = "Source 2 video config and convars"
    else:
        reader = "Source 2 video config"
    modified = max(filter(None, [_mtime(path), *(_mtime(f) for f in files)]), default=None)
    return GameSettings(reader, source, settings + convars, modified)


# --- Unreal Engine: GameUserSettings.ini ------------------------------------------------------

UNREAL_PLATFORMS = ("Windows", "WindowsNoEditor", "WindowsClient", "WinGDK", "WinGDKClient")


def unreal_candidates(game: GameInfo) -> list[Path]:
    project = unreal_project(game.path or "")
    if not project:
        return []
    roots = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / project)
    roots.append(Path.home() / "Documents" / "My Games" / project)
    roots.append(Path.home() / "Saved Games" / project)
    if game.install_dir:
        roots.append(Path(game.install_dir) / project)
    return [
        root / "Saved" / "Config" / plat / "GameUserSettings.ini"
        for root in roots
        for plat in UNREAL_PLATFORMS
    ]


def parse_ini(text: str) -> list[tuple[str, str, str]]:
    """(section, key, value) in file order. Tolerates Unreal's +Key= arrays and duplicates."""
    out = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line[0] in ";#":
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            out.append((section, k.strip().lstrip("+-.!"), v.strip().strip('"')))
    return out


def read_unreal(game: GameInfo) -> GameSettings | None:
    if game.engine != "Unreal Engine":
        return None
    path = _newest(unreal_candidates(game))
    if path is None:
        return None
    try:
        rows = parse_ini(path.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return None
    settings = []
    for section, k, v in rows:
        if not keep(k, v) or "(" in v:  # (X=..,Y=..) structs are positions and the like
            continue
        short = section.rsplit(".", 1)[-1]
        key = k if short in ("GameUserSettings", "") else f"{short}.{k}"
        settings.append((key, v))
    if not settings:
        return None
    return GameSettings("Unreal Engine GameUserSettings.ini", _short(path), settings, _mtime(path))


# --- Unity: PlayerPrefs in HKCU\Software\<company>\<product> ---------------------------------


def unity_app_info(game: GameInfo) -> tuple[str, str] | None:
    if not game.path:
        return None
    p = Path(game.path)
    info = p.parent / f"{p.stem}_Data" / "app.info"
    try:
        lines = info.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    if len(lines) >= 2 and lines[0].strip() and lines[1].strip():
        return lines[0].strip(), lines[1].strip()
    return None


def unity_value(kind: int, data) -> str | None:
    """A PlayerPrefs registry value as text. Unity keeps floats as 64-bit doubles."""
    import winreg

    if kind == winreg.REG_DWORD:
        return str(data)
    if kind == winreg.REG_QWORD:
        f = struct.unpack("<d", struct.pack("<Q", data))[0]
        return f"{f:g}"
    if kind == winreg.REG_BINARY and isinstance(data, bytes):
        text = data.rstrip(b"\0").decode("utf-8", errors="replace")
        return text if text.isprintable() else None
    if kind == winreg.REG_SZ:
        return str(data)
    return None


def read_unity(game: GameInfo) -> GameSettings | None:
    if game.engine != "Unity" or sys.platform != "win32":
        return None
    app = unity_app_info(game)
    if not app:
        return None
    import winreg

    sub = rf"Software\{app[0]}\{app[1]}"
    settings = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, sub) as k:
            i = 0
            while True:
                try:
                    name, data, kind = winreg.EnumValue(k, i)
                except OSError:
                    break
                i += 1
                key = re.sub(r"_h\d+$", "", name)
                value = unity_value(kind, data)
                if value is not None and keep(key, value):
                    settings.append((key, value))
    except OSError:
        return None
    if not settings:
        return None
    settings.sort(key=lambda kv: kv[0].lower())
    return GameSettings("Unity PlayerPrefs (registry)", rf"HKCU\{sub}", settings)


# --- entry point -----------------------------------------------------------------------------

READERS: list[Callable[[GameInfo], GameSettings | None]] = [read_source2, read_unreal, read_unity]


def read(game: GameInfo) -> GameSettings | None:
    """The first reader that finds settings for this game, or None. Never raises."""
    for reader in READERS:
        try:
            found = reader(game)
        except Exception:  # a broken config must never fail a capture
            log.exception("settings reader %s failed", reader.__name__)
            found = None
        if found:
            found.settings = found.settings[:MAX_SETTINGS]
            return found
    return None
