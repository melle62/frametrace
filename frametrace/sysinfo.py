"""System information that matters for game performance. Windows only; stdlib only.

Hardware comes from one PowerShell/CIM call (slow, ~1-3 s, so it runs once in the
background). Settings that can change between captures (display mode, power plan,
Game Mode, HAGS) are read directly from the registry and Win32 APIs, which is fast.

Every probe is best-effort: a failure leaves the field as None and adds a note
to SystemInfo.errors instead of raising.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field

CREATE_NO_WINDOW = 0x08000000

PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
function D($d) { if ($d) { $d.ToString('yyyy-MM-dd') } else { $null } }
$o = [ordered]@{}
$o.os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber
$o.cpu = Get-CimInstance Win32_Processor | Select-Object -First 1 Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed
$o.gpu = @(Get-CimInstance Win32_VideoController | Select-Object Name, DriverVersion, @{n='DriverDate';e={D $_.DriverDate}}, AdapterCompatibility, CurrentHorizontalResolution, CurrentVerticalResolution, CurrentRefreshRate)
$o.ram = @(Get-CimInstance Win32_PhysicalMemory | Select-Object Capacity, Speed, ConfiguredClockSpeed, SMBIOSMemoryType, Manufacturer, PartNumber, DeviceLocator)
$o.board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product
$o.bios = Get-CimInstance Win32_BIOS | Select-Object SMBIOSBIOSVersion, @{n='ReleaseDate';e={D $_.ReleaseDate}}
$dg = Get-CimInstance -Namespace root\Microsoft\Windows\DeviceGuard -ClassName Win32_DeviceGuard
$o.vbs_services = @($dg.SecurityServicesRunning)
$o | ConvertTo-Json -Depth 4 -Compress
"""

MEMORY_TYPES = {24: "DDR3", 26: "DDR4", 34: "DDR5", 35: "LPDDR5"}
POWER_PLANS = {
    "381b4222-f694-41f0-9685-ff5bb260df2e": "Balanced",
    "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c": "High performance",
    "a1841308-3541-4fab-bc81-f71556f20b4a": "Power saver",
    "e9a42b02-d5df-448d-aa00-03f14749eb61": "Ultimate Performance",
}
PLACEHOLDERS = {"", "none", "unknown", "undefined", "not specified", "to be filled by o.e.m."}
DISCRETE_GPU = re.compile(r"\b(RTX|GTX|Radeon RX|RX \d|Arc [AB]\d)", re.IGNORECASE)


@dataclass
class Gpu:
    name: str
    driver: str | None = None
    driver_date: str | None = None
    vendor: str | None = None

    @property
    def nvidia_driver(self) -> str | None:
        return (
            nvidia_driver_version(self.driver)
            if self.vendor and "NVIDIA" in self.vendor.upper()
            else None
        )


@dataclass
class Display:
    name: str
    width: int
    height: int
    refresh_hz: int
    max_refresh_hz: int | None
    primary: bool


@dataclass
class SystemInfo:
    os_name: str | None = None
    os_build: str | None = None  # e.g. 26100.4652
    os_release: str | None = None  # e.g. 24H2
    cpu: str | None = None
    cpu_cores: int | None = None
    cpu_threads: int | None = None
    gpus: list[Gpu] = field(default_factory=list)
    ram_total_gb: float | None = None
    ram_type: str | None = None
    ram_modules: int | None = None
    ram_running_mts: int | None = None
    ram_module_max_mts: int | None = None  # JEDEC speed in the module's SPD, not its EXPO/XMP
    ram_kit_mts: int | None = None  # speed parsed from the part number, if recognisable
    ram_part: str | None = None
    board: str | None = None
    bios: str | None = None
    bios_date: str | None = None
    displays: list[Display] = field(default_factory=list)
    power_plan: str | None = None
    game_mode: bool | None = None
    hags: bool | None = None
    memory_integrity: bool | None = None
    windowed_optimizations: bool | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def main_gpu(self) -> Gpu | None:
        if not self.gpus:
            return None
        discrete = [g for g in self.gpus if DISCRETE_GPU.search(g.name)]
        return (discrete or self.gpus)[0]

    @property
    def main_display(self) -> Display | None:
        primary = [d for d in self.displays if d.primary]
        return (primary or self.displays or [None])[0]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gpus"] = [dict(asdict(g), nvidia_driver=g.nvidia_driver) for g in self.gpus]
        return d


# --- pure helpers (tested on any OS) -------------------------------------------------------


def nvidia_driver_version(windows_version: str | None) -> str | None:
    """'32.0.15.8180' -> '581.80': NVIDIA's version is the last 5 digits of the last two parts."""
    if not windows_version:
        return None
    parts = windows_version.split(".")
    if len(parts) < 4:
        return None
    digits = (parts[-2] + parts[-1])[-5:]
    return f"{digits[:3]}.{digits[3:]}" if len(digits) == 5 and digits.isdigit() else None


def normalize_mts(value: int | None, ram_type: str | None) -> int | None:
    """WMI reports MT/s on most systems but MHz (half) on some; DDR4/5 never run that low."""
    if not value:
        return None
    if ram_type == "DDR5" and value < 3000 or ram_type == "DDR4" and value < 1700:
        return value * 2
    return value


def kit_speed_from_part(part: str | None, ram_type: str | None) -> int | None:
    """Rated speed from part numbers like F5-6000J3038F16G or CMK32GX5M2B6000C36."""
    if not part:
        return None
    lo, hi = (4000, 9600) if ram_type == "DDR5" else (2133, 5333)
    for m in re.finditer(r"(?<!\d)(\d{4})(?!\d)", part):
        speed = int(m.group(1))
        if lo <= speed <= hi:
            return speed
    return None


def parse_powercfg(output: str) -> str | None:
    m = re.search(
        r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\s*\((.+)\)",
        output,
        re.IGNORECASE,
    )
    if m:
        return m.group(2).strip()
    m = re.search(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", output, re.IGNORECASE
    )
    return POWER_PLANS.get(m.group(0).lower()) if m else None


def max_refresh(modes: list[tuple[int, int, int]], width: int, height: int) -> int | None:
    """Highest refresh rate among (width, height, hz) modes at the given resolution."""
    rates = [hz for w, h, hz in modes if w == width and h == height and hz > 1]
    return max(rates) if rates else None


def apply_hardware(info: SystemInfo, data: dict) -> None:
    """Fill SystemInfo from the PowerShell JSON (also used by tests)."""
    os_ = data.get("os") or {}
    info.os_name = os_.get("Caption") or info.os_name
    cpu = data.get("cpu") or {}
    info.cpu = (cpu.get("Name") or "").strip() or None
    info.cpu_cores = cpu.get("NumberOfCores")
    info.cpu_threads = cpu.get("NumberOfLogicalProcessors")

    gpus = data.get("gpu") or []
    info.gpus = [
        Gpu(
            name=(g.get("Name") or "?").strip(),
            driver=g.get("DriverVersion"),
            driver_date=g.get("DriverDate"),
            vendor=g.get("AdapterCompatibility"),
        )
        for g in (gpus if isinstance(gpus, list) else [gpus])
    ]

    ram = data.get("ram") or []
    ram = ram if isinstance(ram, list) else [ram]
    if ram:
        info.ram_modules = len(ram)
        info.ram_total_gb = round(sum(int(m.get("Capacity") or 0) for m in ram) / 2**30, 1)
        info.ram_type = MEMORY_TYPES.get(ram[0].get("SMBIOSMemoryType"))
        running = [m.get("ConfiguredClockSpeed") for m in ram if m.get("ConfiguredClockSpeed")]
        rated = [m.get("Speed") for m in ram if m.get("Speed")]
        info.ram_running_mts = normalize_mts(min(running), info.ram_type) if running else None
        info.ram_module_max_mts = normalize_mts(min(rated), info.ram_type) if rated else None
        part = (ram[0].get("PartNumber") or "").strip()
        info.ram_part = None if part.lower() in PLACEHOLDERS else part
        info.ram_kit_mts = kit_speed_from_part(info.ram_part, info.ram_type)

    board = data.get("board") or {}
    if board:
        info.board = (
            " ".join(x.strip() for x in (board.get("Manufacturer"), board.get("Product")) if x)
            or None
        )
    bios = data.get("bios") or {}
    info.bios = bios.get("SMBIOSBIOSVersion")
    info.bios_date = bios.get("ReleaseDate")
    vbs = data.get("vbs_services")
    if isinstance(vbs, list):
        info.memory_integrity = 2 in vbs  # 2 = hypervisor-enforced code integrity running


# --- Windows probes --------------------------------------------------------------------------


def _run(cmd: list[str], timeout: float) -> str:
    out = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return out.stdout


def collect_hardware(info: SystemInfo) -> None:
    try:
        raw = _run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                PS_SCRIPT,
            ],
            timeout=45,
        )
        apply_hardware(info, json.loads(raw))
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        info.errors.append(f"hardware query failed: {e}")


def _reg(root, path: str, name: str):
    import winreg

    try:
        with winreg.OpenKey(root, path) as key:
            return winreg.QueryValueEx(key, name)[0]
    except OSError:
        return None


def collect_settings(info: SystemInfo) -> None:
    """Fast, changeable settings: OS build, power plan, Game Mode, HAGS, windowed optimizations."""
    import winreg

    nt = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    build, ubr = (
        _reg(winreg.HKEY_LOCAL_MACHINE, nt, "CurrentBuild"),
        _reg(winreg.HKEY_LOCAL_MACHINE, nt, "UBR"),
    )
    info.os_build = f"{build}.{ubr}" if build and ubr is not None else build
    info.os_release = _reg(winreg.HKEY_LOCAL_MACHINE, nt, "DisplayVersion")

    hw = _reg(
        winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode"
    )
    info.hags = {2: True, 1: False}.get(hw)
    gm = _reg(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", "AutoGameModeEnabled")
    info.game_mode = True if gm is None else bool(gm)  # on by default in Windows 11
    dx = _reg(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\DirectX\UserGpuPreferences",
        "DirectXUserGlobalSettings",
    )
    if isinstance(dx, str):
        m = re.search(r"SwapEffectUpgradeEnable=(\d)", dx)
        info.windowed_optimizations = bool(int(m.group(1))) if m else None

    try:
        info.power_plan = parse_powercfg(_run(["powercfg", "/getactivescheme"], timeout=10))
    except (OSError, subprocess.SubprocessError) as e:
        info.errors.append(f"power plan: {e}")

    try:
        info.displays = list_displays()
    except OSError as e:
        info.errors.append(f"displays: {e}")


def list_displays() -> list[Display]:
    import ctypes
    from ctypes import wintypes

    class DISPLAY_DEVICEW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("DeviceName", wintypes.WCHAR * 32),
            ("DeviceString", wintypes.WCHAR * 128),
            ("StateFlags", wintypes.DWORD),
            ("DeviceID", wintypes.WCHAR * 128),
            ("DeviceKey", wintypes.WCHAR * 128),
        ]

    class DEVMODEW(ctypes.Structure):  # display variant of the union; sizeof == 220
        _fields_ = [
            ("dmDeviceName", wintypes.WCHAR * 32),
            ("dmSpecVersion", wintypes.WORD),
            ("dmDriverVersion", wintypes.WORD),
            ("dmSize", wintypes.WORD),
            ("dmDriverExtra", wintypes.WORD),
            ("dmFields", wintypes.DWORD),
            ("dmPositionX", wintypes.LONG),
            ("dmPositionY", wintypes.LONG),
            ("dmDisplayOrientation", wintypes.DWORD),
            ("dmDisplayFixedOutput", wintypes.DWORD),
            ("dmColor", ctypes.c_short),
            ("dmDuplex", ctypes.c_short),
            ("dmYResolution", ctypes.c_short),
            ("dmTTOption", ctypes.c_short),
            ("dmCollate", ctypes.c_short),
            ("dmFormName", wintypes.WCHAR * 32),
            ("dmLogPixels", wintypes.WORD),
            ("dmBitsPerPel", wintypes.DWORD),
            ("dmPelsWidth", wintypes.DWORD),
            ("dmPelsHeight", wintypes.DWORD),
            ("dmDisplayFlags", wintypes.DWORD),
            ("dmDisplayFrequency", wintypes.DWORD),
            ("dmICMMethod", wintypes.DWORD),
            ("dmICMIntent", wintypes.DWORD),
            ("dmMediaType", wintypes.DWORD),
            ("dmDitherType", wintypes.DWORD),
            ("dmReserved1", wintypes.DWORD),
            ("dmReserved2", wintypes.DWORD),
            ("dmPanningWidth", wintypes.DWORD),
            ("dmPanningHeight", wintypes.DWORD),
        ]

    user32 = ctypes.WinDLL("user32")
    user32.EnumDisplayDevicesW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(DISPLAY_DEVICEW),
        wintypes.DWORD,
    ]
    user32.EnumDisplaySettingsW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(DEVMODEW),
    ]
    ATTACHED, PRIMARY, ENUM_CURRENT = 0x1, 0x4, 0xFFFFFFFF

    displays = []
    i = 0
    while True:
        dev = DISPLAY_DEVICEW(cb=ctypes.sizeof(DISPLAY_DEVICEW))
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(dev), 0):
            break
        i += 1
        if not dev.StateFlags & ATTACHED:
            continue
        cur = DEVMODEW(dmSize=ctypes.sizeof(DEVMODEW))
        if not user32.EnumDisplaySettingsW(dev.DeviceName, ENUM_CURRENT, ctypes.byref(cur)):
            continue
        modes = []
        j = 0
        while j < 5000:
            dm = DEVMODEW(dmSize=ctypes.sizeof(DEVMODEW))
            if not user32.EnumDisplaySettingsW(dev.DeviceName, j, ctypes.byref(dm)):
                break
            modes.append((dm.dmPelsWidth, dm.dmPelsHeight, dm.dmDisplayFrequency))
            j += 1
        monitor = DISPLAY_DEVICEW(cb=ctypes.sizeof(DISPLAY_DEVICEW))
        name = dev.DeviceString
        if user32.EnumDisplayDevicesW(dev.DeviceName, 0, ctypes.byref(monitor), 0):
            name = monitor.DeviceString or name
        displays.append(
            Display(
                name=name,
                width=cur.dmPelsWidth,
                height=cur.dmPelsHeight,
                refresh_hz=cur.dmDisplayFrequency,
                max_refresh_hz=max_refresh(modes, cur.dmPelsWidth, cur.dmPelsHeight),
                primary=bool(dev.StateFlags & PRIMARY),
            )
        )
    return displays


def collect(hardware: bool = True) -> SystemInfo:
    """Collect everything. With hardware=False, only the fast settings part runs."""
    info = SystemInfo()
    if sys.platform != "win32":
        info.errors.append("system info is only collected on Windows")
        return info
    if hardware:
        collect_hardware(info)
    collect_settings(info)
    return info


def refresh_settings(info: SystemInfo) -> SystemInfo:
    """Copy of info with the fast, changeable settings read again (after a capture)."""
    fresh = SystemInfo(**{k: v for k, v in info.__dict__.items() if k != "errors"})
    fresh.errors = []
    if sys.platform == "win32":
        collect_settings(fresh)
    return fresh
