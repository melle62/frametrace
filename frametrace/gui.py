"""Frametrace window: tkinter with the Sun Valley (Windows 11) theme.

All slow work (PresentMon, analysis, system info, downloads) runs on worker threads.
Workers never touch widgets: they put (kind, payload) on self.events, and poll()
handles them on the Tk thread every 100 ms.
"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import ttk

from frametrace import __version__, capture, download, hotkey, presentmon, report, sysinfo

SETTINGS_PATH = Path(os.environ.get("APPDATA", Path.home())) / "Frametrace" / "settings.json"
DEFAULTS = {"hotkey": "F10", "length_s": 30, "manual": False, "process_name": "", "sound": True}
LENGTHS = ["10", "20", "30", "60", "90", "120", "180", "300"]
INTRO = """Start a game, press {hotkey} and play normally.

{length}

The report appears here and is copied to your clipboard. Paste it into any AI.
Tip: play the same scene each time (a benchmark map, replay or fixed route), so
captures can be compared."""


def load_settings() -> dict:
    try:
        return {**DEFAULTS, **json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(json.dumps(settings, indent=1), encoding="utf-8")
    except OSError:
        pass


def _pick_font(root: tk.Tk, *names: str) -> str:
    available = set(tkfont.families(root))
    return next((n for n in names if n in available), "Courier")


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.events: queue.Queue = queue.Queue()
        self.settings = load_settings()
        self.system: sysinfo.SystemInfo | None = None
        self.recorder: capture.Recorder | None = None
        self.listener: hotkey.HotkeyListener | None = None
        self.shown_text = ""
        self.captures: dict[str, tuple[Path, dict]] = {}

        root.title(f"Frametrace {__version__}")
        root.geometry("900x720")
        root.minsize(760, 560)
        self.dark = self._apply_theme()
        self.mono = (
            _pick_font(root, "Cascadia Mono", "Consolas", "Courier New", "DejaVu Sans Mono"),
            10,
        )
        self._build()
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        threading.Thread(target=self._load_system, daemon=True).start()
        self.check_setup()
        self.refresh_history()
        root.after(100, self.poll)

    # --- theme and layout -----------------------------------------------------------------

    def _apply_theme(self) -> bool:
        try:
            import sv_ttk

            sv_ttk.set_theme("dark")
        except ImportError:
            return False
        self.root.after(50, self._dark_title_bar)
        return True

    def _dark_title_bar(self) -> None:
        if sys.platform != "win32":
            return
        try:  # DWMWA_USE_IMMERSIVE_DARK_MODE (Windows 11)
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
        except (AttributeError, OSError):
            pass

    def _build(self) -> None:
        root = self.root
        outer = ttk.Frame(root, padding=14)
        outer.pack(fill="both", expand=True)

        head = ttk.Frame(outer)
        head.pack(fill="x")
        ttk.Label(head, text="Frametrace", font=("Segoe UI Semibold", 18)).pack(side="left")
        self.sys_label = ttk.Label(head, text="Reading system info…", foreground="#9a9a9a")
        self.sys_label.pack(side="left", padx=14, pady=(6, 0))

        self.banner = ttk.Frame(outer, padding=(0, 10, 0, 0))
        self.banner_text = ttk.Label(self.banner, text="", foreground="#f0b429", wraplength=820)
        self.banner_text.pack(side="left", fill="x", expand=True)
        self.banner_buttons = ttk.Frame(self.banner)
        self.banner_buttons.pack(side="right")

        box = ttk.LabelFrame(outer, text="Capture", padding=12)
        box.pack(fill="x", pady=(12, 10))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="Hotkey").grid(row=0, column=0, sticky="w", pady=4)
        hk = ttk.Frame(box)
        hk.grid(row=0, column=1, sticky="w")
        self.hotkey_var = tk.StringVar(value=self.settings["hotkey"])
        combo = ttk.Combobox(hk, textvariable=self.hotkey_var, values=hotkey.SUGGESTED, width=14)
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda _e: self.apply_hotkey())
        combo.bind("<Return>", lambda _e: self.apply_hotkey())
        combo.bind("<FocusOut>", lambda _e: self.apply_hotkey())
        self.hotkey_status = ttk.Label(hk, text="", foreground="#9a9a9a")
        self.hotkey_status.pack(side="left", padx=10)

        ttk.Label(box, text="Length").grid(row=1, column=0, sticky="w", pady=4)
        ln = ttk.Frame(box)
        ln.grid(row=1, column=1, sticky="w")
        self.manual_var = tk.BooleanVar(value=self.settings["manual"])
        self.length_var = tk.StringVar(value=str(self.settings["length_s"]))
        ttk.Radiobutton(
            ln, text="Fixed", variable=self.manual_var, value=False, command=self.save
        ).pack(side="left")
        self.length_box = ttk.Combobox(ln, textvariable=self.length_var, values=LENGTHS, width=6)
        self.length_box.pack(side="left", padx=(6, 4))
        self.length_box.bind("<<ComboboxSelected>>", lambda _e: self.save())
        self.length_box.bind("<FocusOut>", lambda _e: self.save())
        ttk.Label(ln, text="seconds").pack(side="left", padx=(0, 18))
        ttk.Radiobutton(
            ln,
            text="Manual (the hotkey stops it)",
            variable=self.manual_var,
            value=True,
            command=self.save,
        ).pack(side="left")

        ttk.Label(box, text="Game").grid(row=2, column=0, sticky="w", pady=4)
        gm = ttk.Frame(box)
        gm.grid(row=2, column=1, sticky="w")
        self.process_var = tk.StringVar(value=self.settings["process_name"])
        entry = ttk.Entry(gm, textvariable=self.process_var, width=24)
        entry.pack(side="left")
        entry.bind("<FocusOut>", lambda _e: self.save())
        ttk.Label(
            gm,
            text="optional, empty = auto-detect",
            foreground="#9a9a9a",
        ).pack(side="left", padx=10)

        self.sound_var = tk.BooleanVar(value=self.settings["sound"])
        ttk.Checkbutton(
            box, text="Beep on start and stop", variable=self.sound_var, command=self.save
        ).grid(row=3, column=1, sticky="w", pady=(4, 0))

        side = ttk.Frame(box)
        side.grid(row=0, column=2, rowspan=4, sticky="ne", padx=(12, 0))
        self.start_btn = ttk.Button(
            side,
            text="Start capture",
            width=18,
            command=self.toggle_capture,
            style="Accent.TButton" if self.dark else "TButton",
        )
        self.start_btn.pack(fill="x")
        self.status = ttk.Label(side, text="", foreground="#9a9a9a", width=26, anchor="center")
        self.status.pack(fill="x", pady=(8, 0))

        tabs = ttk.Notebook(outer)
        tabs.pack(fill="both", expand=True)
        self.tabs = tabs

        rep = ttk.Frame(tabs, padding=(0, 8, 0, 0))
        tabs.add(rep, text="Report")
        text_wrap = ttk.Frame(rep)
        text_wrap.pack(fill="both", expand=True)
        colors = (
            {"bg": "#1c1c1c", "fg": "#e4e4e4", "insertbackground": "#e4e4e4"} if self.dark else {}
        )
        self.text = tk.Text(
            text_wrap, wrap="word", font=self.mono, relief="flat", padx=10, pady=8, **colors
        )
        scroll = ttk.Scrollbar(text_wrap, command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        bar = ttk.Frame(rep, padding=(0, 8, 0, 0))
        bar.pack(fill="x")
        ttk.Button(bar, text="Copy", command=self.copy_shown).pack(side="left")
        ttk.Button(bar, text="Open captures folder", command=self.open_root).pack(
            side="left", padx=8
        )
        self.copy_note = ttk.Label(bar, text="", foreground="#9a9a9a")
        self.copy_note.pack(side="left", padx=8)

        hist = ttk.Frame(tabs, padding=(0, 8, 0, 0))
        tabs.add(hist, text="Captures")
        cols = ("when", "game", "length", "avg", "p1", "verdict")
        self.tree = ttk.Treeview(hist, columns=cols, show="headings", selectmode="extended")
        for col, title, width in zip(
            cols,
            ("Date", "Game", "Length", "Avg FPS", "1% low", "Bottleneck"),
            (130, 150, 70, 80, 80, 260),
            strict=True,
        ):
            self.tree.heading(col, text=title)
            self.tree.column(col, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self.show_selected())
        hb = ttk.Frame(hist, padding=(0, 8, 0, 0))
        hb.pack(fill="x")
        ttk.Button(hb, text="Show report", command=self.show_selected).pack(side="left")
        ttk.Button(hb, text="Compare 2 selected", command=self.compare_selected).pack(
            side="left", padx=8
        )
        ttk.Button(hb, text="Open folder", command=self.open_selected).pack(side="left")
        ttk.Button(hb, text="Refresh", command=self.refresh_history).pack(side="left", padx=8)

        self.show_intro()
        self.set_status("idle")

    # --- setup checks ------------------------------------------------------------------------

    def show_banner(self, text: str, buttons: list[tuple[str, object]]) -> None:
        for child in self.banner_buttons.winfo_children():
            child.destroy()
        self.banner_text.configure(text=text)
        for label, cmd in buttons:
            ttk.Button(self.banner_buttons, text=label, command=cmd).pack(side="left", padx=(8, 0))
        self.banner.pack(fill="x", after=self.banner.master.winfo_children()[0])

    def hide_banner(self) -> None:
        self.banner.pack_forget()

    def check_setup(self) -> None:
        try:
            exe = presentmon.find_presentmon()
        except presentmon.PresentMonNotFound:
            self.show_banner(
                "PresentMon (Intel's free frame-capture tool) isn't downloaded yet.",
                [("Download PresentMon", self.download_presentmon)],
            )
            self.start_btn.state(["disabled"])
            return
        ok, _why = presentmon.can_trace()
        if not ok:
            self.show_banner(
                "Recording needs administrator rights, or your account in the 'Performance Log "
                "Users' group (one-time setup, then sign out and back in).",
                [
                    ("Restart as administrator", self.restart_as_admin),
                    ("One-time setup", self.add_to_perf_log_users),
                ],
            )
            self.start_btn.state(["disabled"])
        else:
            self.hide_banner()
            self.start_btn.state(["!disabled"])
        self.recorder = capture.Recorder(
            exe,
            lambda kind, payload: self.events.put((kind, payload)),
            system_provider=self.system_for_capture,
        )
        self.apply_hotkey()

    def download_presentmon(self) -> None:
        self.show_banner("Downloading PresentMon…", [])

        def work() -> None:
            lines: list[str] = []
            ok = download.ensure_presentmon(say=lines.append)
            self.events.put(("download", {"ok": ok, "log": "\n".join(lines)}))

        threading.Thread(target=work, daemon=True).start()

    def restart_as_admin(self) -> None:
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        cwd = str(Path(__file__).resolve().parent.parent)
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", str(pyw if pyw.exists() else exe), "-m frametrace", cwd, 1
        )
        if rc > 32:
            self.on_close()

    def add_to_perf_log_users(self) -> None:
        member = f"{os.environ.get('USERDOMAIN', '')}\\{os.environ.get('USERNAME', '')}".strip("\\")
        cmd = f"Add-LocalGroupMember -SID 'S-1-5-32-559' -Member '{member}'"
        rc = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe", f'-NoProfile -Command "{cmd}"', None, 0
        )
        if rc > 32:
            self.show_banner(
                "Added your account to Performance Log Users (if you approved the prompt). "
                "Sign out of Windows and back in, then start Frametrace again.",
                [],
            )

    # --- system info -------------------------------------------------------------------------

    def _load_system(self) -> None:
        info = sysinfo.collect()
        self.events.put(("system", {"info": info}))

    def system_for_capture(self) -> sysinfo.SystemInfo:
        """Called on the analysis thread: hardware from startup, settings read fresh."""
        return sysinfo.refresh_settings(self.system) if self.system else sysinfo.collect()

    def show_system(self, info: sysinfo.SystemInfo) -> None:
        parts = [info.cpu and info.cpu.replace(" Processor", "").replace("-Core", "C")]
        gpu = info.main_gpu
        if gpu:
            parts.append(gpu.name.replace("NVIDIA GeForce ", "").replace("AMD Radeon ", "Radeon "))
        if info.ram_total_gb:
            parts.append(
                f"{info.ram_total_gb:.0f} GB {info.ram_type or ''} @ {info.ram_running_mts or '?'}"
            )
        disp = info.main_display
        if disp:
            parts.append(f"{disp.width}x{disp.height} @ {disp.refresh_hz} Hz")
        self.sys_label.configure(
            text="  ·  ".join(p for p in parts if p) or "System info unavailable"
        )

    # --- hotkey and capture ------------------------------------------------------------------

    def apply_hotkey(self) -> None:
        key = self.hotkey_var.get().strip()
        if self.listener and self.listener.hotkey == key and self.listener.is_alive():
            return
        try:
            new = hotkey.HotkeyListener(key, lambda: self.events.put(("hotkey", {})))
        except ValueError as e:
            self.hotkey_status.configure(text=str(e), foreground="#f0b429")
            return
        if self.listener:
            self.listener.stop()
        error = new.start_and_wait()
        if error:
            self.listener = None
            self.hotkey_status.configure(text=error, foreground="#f0b429")
        else:
            self.listener = new
            self.hotkey_status.configure(text="works in any game", foreground="#9a9a9a")
            self.save()
        if self.recorder and self.recorder.state == "idle":
            self.set_status("idle")
            self.show_intro_if_empty()

    def current_settings(self) -> capture.CaptureSettings:
        length = None if self.manual_var.get() else self.length_seconds()
        return capture.CaptureSettings(
            length_s=length, process_name=self.process_var.get().strip() or None
        )

    def length_seconds(self) -> int:
        try:
            return max(5, min(3600, int(float(self.length_var.get()))))
        except ValueError:
            return DEFAULTS["length_s"]

    def toggle_capture(self) -> None:
        if not self.recorder or "disabled" in self.start_btn.state():
            return
        self.recorder.toggle(self.current_settings())

    def set_status(self, state: str, extra: str = "") -> None:
        key = self.hotkey_var.get() or "the hotkey"
        if state == "idle":
            self.start_btn.configure(text="Start capture")
            self.status.configure(text=f"Ready. Press {key} in a game.")
        elif state == "recording":
            self.start_btn.configure(text="Stop capture")
            self.status.configure(text=extra)
        elif state == "analyzing":
            self.start_btn.configure(text="Analyzing…")
            self.status.configure(text="Stopping and analyzing…")
        elif state == "error":
            self.start_btn.configure(text="Start capture")
            self.status.configure(text="Capture failed, see the report tab.")

    def save(self) -> None:
        self.settings.update(
            hotkey=self.listener.hotkey if self.listener else self.settings["hotkey"],
            length_s=self.length_seconds(),
            manual=self.manual_var.get(),
            process_name=self.process_var.get().strip(),
            sound=self.sound_var.get(),
        )
        save_settings(self.settings)
        self.show_intro_if_empty()

    # --- events ------------------------------------------------------------------------------

    def poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                self.handle(kind, payload)
        except queue.Empty:
            pass
        if self.recorder and self.recorder.state == "recording":
            secs = self.recorder.elapsed()
            length = self.recorder.length_s
            self.set_status(
                "recording", f"Recording {secs:.0f} s" + (f" / {length} s" if length else "")
            )
        self.root.after(100, self.poll)

    def handle(self, kind: str, p: dict) -> None:
        if kind == "hotkey":
            self.toggle_capture()
        elif kind == "started":
            if self.sound_var.get():
                capture.beep("start")
            who = p.get("foreground") or "?"
            self.show_text(
                f"Recording… (window in front: {who})\n\nPress {self.hotkey_var.get()} to stop"
                + (f", or wait {p['length_s']} s." if p.get("length_s") else "."),
                keep=False,
            )
        elif kind == "stopping":
            if self.sound_var.get():
                capture.beep("stop")
            self.set_status("analyzing")
        elif kind == "done":
            self.set_status("idle")
            self.show_text(p["report"])
            self.copy_shown(note="Report copied to the clipboard.")
            self.tabs.select(0)
            self.refresh_history()
        elif kind == "error":
            if self.sound_var.get():
                capture.beep("error")
            self.set_status("error")
            self.show_text("Capture failed.\n\n" + p["message"], keep=False)
        elif kind == "system":
            self.system = p["info"]
            self.show_system(self.system)
        elif kind == "download":
            if p["ok"]:
                self.check_setup()
            else:
                self.show_banner(
                    "Download failed:\n" + p["log"][-600:], [("Retry", self.download_presentmon)]
                )

    # --- report and history ------------------------------------------------------------------

    def show_text(self, text: str, keep: bool = True) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")
        if keep:
            self.shown_text = text
        self.copy_note.configure(text="")

    def show_intro(self) -> None:
        length = (
            "Recording stops when you press it again."
            if self.manual_var.get()
            else f"Recording stops after {self.length_seconds()} seconds (or when you press it again)."
        )
        self.show_text(INTRO.format(hotkey=self.hotkey_var.get(), length=length), keep=False)
        self.shown_text = ""

    def show_intro_if_empty(self) -> None:
        if not self.shown_text and (not self.recorder or self.recorder.state == "idle"):
            self.show_intro()

    def copy_shown(self, note: str = "Copied.") -> None:
        if not self.shown_text:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.shown_text)
        self.root.update()
        self.copy_note.configure(text=note)

    def refresh_history(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.captures.clear()
        for folder, result in capture.list_captures():
            try:
                cap, an = result["capture"], result["analysis"]
                values = (
                    report._when(cap.get("started")),
                    cap["app"],
                    f"{an['stats']['duration_s']:.0f} s",
                    f"{an['stats']['avg_fps']:.1f}",
                    f"{an['stats']['p1_fps']:.1f}",
                    an["bottleneck"]["verdict"],
                )
            except (KeyError, TypeError):
                continue
            iid = self.tree.insert("", "end", values=values)
            self.captures[iid] = (folder, result)

    def _selected(self) -> list[tuple[Path, dict]]:
        return [self.captures[i] for i in self.tree.selection() if i in self.captures]

    def show_selected(self) -> None:
        sel = self._selected()
        if sel:
            self.show_text(report.render(sel[0][1]))
            self.tabs.select(0)

    def compare_selected(self) -> None:
        sel = self._selected()
        if len(sel) != 2:
            self.copy_note.configure(text="Select exactly two captures (Ctrl+click).")
            self.tabs.select(0)
            return
        older, newer = sorted(sel, key=lambda fr: fr[1]["capture"].get("started", ""))
        self.show_text(report.compare(older[1], newer[1]))
        self.tabs.select(0)

    def open_selected(self) -> None:
        sel = self._selected()
        if sel:
            _open(sel[0][0])

    def open_root(self) -> None:
        capture.DEFAULT_ROOT.mkdir(parents=True, exist_ok=True)
        _open(capture.DEFAULT_ROOT)

    # --- shutdown ----------------------------------------------------------------------------

    def on_close(self) -> None:
        if self.listener:
            self.listener.stop()
        if self.recorder and self.recorder.state == "recording":
            try:  # don't leave an ETW session running
                subprocess.run(
                    presentmon.terminate_command(self.recorder.exe),
                    timeout=10,
                    capture_output=True,
                    check=False,
                    creationflags=capture.CREATE_NO_WINDOW if os.name == "nt" else 0,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        self.root.destroy()


def _open(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


def main() -> int:
    if sys.platform == "win32":
        try:  # crisp text on high-DPI screens
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    App(root)
    root.mainloop()
    return 0
