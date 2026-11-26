"""Which game was captured: its name, store entry, version and engine.

Everything comes from generic sources: the process image path, Steam's app manifests,
the exe's version resource and files every build of an engine ships with. No list of games.
The AI needs the real game name (not just "cs2.exe") to recommend in-game settings.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

log = logging.getLogger(__name__)


@dataclass
class GameInfo:
    exe: str  # image name, "cs2.exe"
    path: str | None = None  # full image path
    name: str | None = None  # "Counter-Strike 2"
    name_source: str | None = None  # steam, version info, window title, exe name
    version: str | None = None  # product version from the exe
    store: str | None = None  # "Steam"
    store_id: str | None = None  # Steam app ID
    build: str | None = None  # Steam build ID
    install_dir: str | None = None  # the game's top folder
    engine: str | None = None  # Unreal Engine, Unity, Source 2, ...
    window_title: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def display_name(self) -> str:
        return self.name or self.exe.removesuffix(".exe")


# --- Valve KeyValues (appmanifest_*.acf, Source 2 video configs) ------------------------------

_KV_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])|(//[^\n]*)')


def parse_keyvalues(text: str) -> dict:
    """Parse Valve's KeyValues text format into nested dicts. Later duplicate keys win."""
    root: dict = {}
    stack = [root]
    key = None
    for m in _KV_TOKEN.finditer(text):
        s, brace, comment = m.groups()
        if comment:
            continue
        if brace == "{":
            child: dict = {}
            stack[-1][key if key is not None else ""] = child
            stack.append(child)
            key = None
        elif brace == "}":
            if len(stack) > 1:
                stack.pop()
            key = None
        elif key is None:
            key = s
        else:
            stack[-1][key] = s
            key = None
    return root


# --- Steam -----------------------------------------------------------------------------------


def _parts(path: str) -> tuple[str, ...]:
    return Path(path).parts


def steam_library(exe_path: str) -> tuple[Path, str] | None:
    """(library root, install folder name) when the exe lives under steamapps/common."""
    parts = _parts(exe_path)
    low = [p.lower() for p in parts]
    for i in range(len(low) - 2):
        if low[i] == "steamapps" and low[i + 1] == "common":
            return Path(*parts[: i + 1]), parts[i + 2]
    return None


def steam_manifest(steamapps: Path, install_folder: str) -> dict | None:
    """The appmanifest whose installdir is this folder: {appid, name, buildid, ...}."""
    try:
        manifests = list(steamapps.glob("appmanifest_*.acf"))
    except OSError:
        return None
    for m in manifests:
        try:
            state = parse_keyvalues(m.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        app = state.get("AppState") or {}
        if str(app.get("installdir", "")).lower() == install_folder.lower():
            return app
    return None


def steam_root() -> Path | None:
    """Steam's own folder (where userdata lives), from the registry."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            value, _ = winreg.QueryValueEx(k, "SteamPath")
        p = Path(value)
        return p if p.is_dir() else None
    except OSError:
        return None


# --- exe version resource --------------------------------------------------------------------


def version_info(exe_path: str) -> dict[str, str]:
    """ProductName, FileDescription, ProductVersion from the exe's version resource."""
    if sys.platform != "win32":
        return {}
    import ctypes
    from ctypes import wintypes

    try:
        ver = ctypes.WinDLL("version")
    except OSError:
        return {}
    ver.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    ver.GetFileVersionInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    ver.VerQueryValueW.argtypes = [
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.UINT),
    ]
    size = ver.GetFileVersionInfoSizeW(exe_path, None)
    if not size:
        return {}
    buf = ctypes.create_string_buffer(size)
    if not ver.GetFileVersionInfoW(exe_path, 0, size, buf):
        return {}
    ptr, length = ctypes.c_void_p(), wintypes.UINT()
    langs = []
    if ver.VerQueryValueW(
        buf, r"\VarFileInfo\Translation", ctypes.byref(ptr), ctypes.byref(length)
    ):
        arr = ctypes.cast(ptr, ctypes.POINTER(wintypes.WORD))
        langs = [f"{arr[i]:04x}{arr[i + 1]:04x}" for i in range(0, length.value // 2, 2)]
    out: dict[str, str] = {}
    for lang in [*langs, "040904b0", "040904e4"]:
        for field in ("ProductName", "FileDescription", "ProductVersion", "FileVersion"):
            if field in out:
                continue
            if (
                ver.VerQueryValueW(
                    buf, rf"\StringFileInfo\{lang}\{field}", ctypes.byref(ptr), ctypes.byref(length)
                )
                and length.value
            ):
                value = ctypes.wstring_at(ptr, length.value).rstrip("\0").strip()
                if value:
                    out[field] = value
    # Many games ship no version strings, only the numeric VS_FIXEDFILEINFO block
    if "ProductVersion" not in out and "FileVersion" not in out:
        fixed = _fixed_version(ver, buf)
        if fixed:
            out["FixedVersion"] = fixed
    return out


def _fixed_version(ver, buf) -> str | None:
    """'1.41.1.6' from VS_FIXEDFILEINFO (product version), or None when it's empty or 0.0.0.0."""
    import ctypes
    from ctypes import wintypes

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", ctypes.c_uint32),
            ("dwStrucVersion", ctypes.c_uint32),
            ("dwFileVersionMS", ctypes.c_uint32),
            ("dwFileVersionLS", ctypes.c_uint32),
            ("dwProductVersionMS", ctypes.c_uint32),
            ("dwProductVersionLS", ctypes.c_uint32),
        ]

    ptr, length = ctypes.c_void_p(), wintypes.UINT()
    if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)):
        return None
    if length.value < ctypes.sizeof(VS_FIXEDFILEINFO) or not ptr.value:
        return None
    info = ctypes.cast(ptr, ctypes.POINTER(VS_FIXEDFILEINFO)).contents
    if info.dwSignature != 0xFEEF04BD:
        return None
    ms, ls = (
        info.dwProductVersionMS or info.dwFileVersionMS,
        info.dwProductVersionLS or info.dwFileVersionLS,
    )
    parts = (ms >> 16, ms & 0xFFFF, ls >> 16, ls & 0xFFFF)
    return ".".join(map(str, parts)) if any(parts) else None


# Names an engine or launcher stub puts in the version resource instead of the game's own.
_GENERIC_NAMES = re.compile(
    r"^(BootstrapPackagedGame|UnrealGame|UE4Game|UE5Game|Unity Player|UnityPlayer|"
    r"Epic Games|Launcher|Game|Client|Win64)$",
    re.IGNORECASE,
)


# --- engine ----------------------------------------------------------------------------------


def detect_engine(exe_path: str) -> str | None:
    """Engine from files every build ships with. None when unsure."""
    p = Path(exe_path)
    folder = p.parent
    try:
        if p.stem.lower().endswith("-win64-shipping") or (
            folder.name.lower() == "win64" and folder.parent.name.lower() == "binaries"
        ):
            return "Unreal Engine"
        if (folder / "UnityPlayer.dll").exists() or (folder / f"{p.stem}_Data").is_dir():
            return "Unity"
        if (folder / "engine2.dll").exists():
            return "Source 2"
        if (folder / "engine.dll").exists() and (folder / "bin").is_dir():
            return "Source"
        if any(folder.glob("REFramework*")) or (folder / "re_chunk_000.pak").exists():
            return "RE Engine"
    except OSError:
        return None
    return None


def unreal_project(exe_path: str) -> str | None:
    """The Unreal project name: 'Foo' for Foo-Win64-Shipping.exe or Foo/Binaries/Win64/x.exe."""
    p = Path(exe_path)
    m = re.match(r"(.+?)-Win64-Shipping$", p.stem, re.IGNORECASE)
    if m:
        return m.group(1)
    parts = p.parts
    if len(parts) >= 4 and parts[-2].lower() == "win64" and parts[-3].lower() == "binaries":
        return parts[-4]
    return None


def install_dir(exe_path: str) -> Path:
    """The game's top folder: steamapps/common/<game>, or two levels up from Unreal binaries."""
    lib = steam_library(exe_path)
    if lib:
        return lib[0] / "common" / lib[1]
    p = Path(exe_path).parent
    if p.name.lower() == "win64" and p.parent.name.lower() == "binaries":
        return p.parent.parent.parent
    return p


# --- putting it together ---------------------------------------------------------------------


def identify(exe: str, path: str | None, window_title: str | None = None) -> GameInfo:
    """Everything Frametrace can find out about the captured game. Never raises."""
    info = GameInfo(exe=exe, path=path, window_title=window_title or None)
    if path:
        try:
            info.install_dir = str(install_dir(path))
            info.engine = detect_engine(path)
            lib = steam_library(path)
            if lib:
                app = steam_manifest(lib[0], lib[1])
                if app:
                    info.store, info.store_id = "Steam", app.get("appid")
                    info.build = app.get("buildid")
                    if app.get("name"):
                        info.name, info.name_source = app["name"], "steam"
            vi = version_info(path)
            info.version = (
                vi.get("ProductVersion") or vi.get("FileVersion") or vi.get("FixedVersion")
            )
            if not info.name:
                for field in ("ProductName", "FileDescription"):
                    v = vi.get(field)
                    if v and not _GENERIC_NAMES.match(v):
                        info.name, info.name_source = v, "version info"
                        break
        except Exception:  # identification is a bonus: never fail a capture over it
            log.exception("could not identify %s", exe)
    if not info.name and window_title and len(window_title) <= 80:
        info.name, info.name_source = window_title.strip(), "window title"
    return info
