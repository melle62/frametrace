"""Share captures and comparisons with the Frametrace dataset (opt-in, asked once).

Every shared capture and comparison goes to a small inbox (server/supabase), and a daily
export publishes it in github.com/melle62/frametrace-data (CC0). Nothing is thrown away for
being noisy: tools/aggregate.py decides later which data is good enough for the game skills.
What is sent, what isn't, and how to delete it: PRIVACY.md and docs/data.md.

Kept out of every bundle (they identify the person, not the run): other processes that
presented frames, the window title, the computer's user folder, e-mail addresses, Steam
account IDs and system-probe error texts. The PresentMon CSV is cut to the game's own rows
before it's compressed and sent.

Stdlib only. Uploads go through urllib; when Python can't verify the certificate (debloated
Windows), through Windows' curl.exe, as the PresentMon download does.
"""

from __future__ import annotations

import copy
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from frametrace import __version__, report, summary

ENDPOINT = os.environ.get(
    "FRAMETRACE_SHARE_URL", "https://hompvqrkzyoeljcrastw.supabase.co/functions/v1"
).rstrip("/")
SCHEMA = 1
# Raise when what's shared changes in a way people should agree to again: the window then
# asks once more (people who said no aren't asked again).
CONSENT_VERSION = 1
STATE_PATH = Path(os.environ.get("APPDATA", Path.home())) / "Frametrace" / "shared.json"
PRIVACY_URL = "https://github.com/melle62/frametrace/blob/main/PRIVACY.md"
DATASET_URL = "https://github.com/melle62/frametrace-data"
MAX_CSV_BYTES = 50 * 1024 * 1024
CSV_RETRY_S = 6 * 3600  # after the inbox says "send the CSV later"
USER_AGENT = f"frametrace/{__version__}"
CREATE_NO_WINDOW = 0x08000000
# Who suggested the changes between A and B (asked in the Compare view).
ADVICE = ["Claude", "ChatGPT", "Gemini", "Another AI", "A guide or video", "My own idea"]


class ShareError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


# --- what's sent -----------------------------------------------------------------------------

_USER_DIR = re.compile(r"(?i)\b([A-Z]:[\\/]+(?:Users|Documents and Settings)[\\/]+)[^\\/\"']+")
_UNIX_HOME = re.compile(r"(/(?:home|Users)/)[^/\"']+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_STEAM64 = re.compile(r"\b7656119\d{10}\b")
_USERDATA = re.compile(r"(?i)(userdata[\\/]+)\d+")


def scrub_text(text: str) -> str:
    """Mask the parts of a string that point at a person."""
    text = _USER_DIR.sub(r"\1<user>", text)
    text = _UNIX_HOME.sub(r"\1<user>", text)
    text = _EMAIL.sub("<e-mail>", text)
    text = _STEAM64.sub("<account>", text)
    return _USERDATA.sub(r"\1<account>", text)


def scrub(value):
    """scrub_text() on every string in a JSON-like value (keys too)."""
    if isinstance(value, str):
        return scrub_text(value)
    if isinstance(value, dict):
        return {scrub_text(str(k)): scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(v) for v in value]
    return value


def capture_id(folder: Path) -> str:
    """The capture's folder name (date, time, game): unique per install, stable."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", folder.name).strip("_")[:80] or "capture"


def side_id(folder: Path, bundle: str | None = None) -> str:
    """One side of a comparison: the run's capture ID, or "bundle.<id>" for a bundle."""
    if bundle:
        return "bundle." + (re.sub(r"[^A-Za-z0-9._-]+", "_", bundle).strip("_")[:80] or "x")
    return capture_id(folder)


def comparison_id(
    fa: Path, fb: Path, a_bundle: str | None = None, b_bundle: str | None = None
) -> str:
    return f"{side_id(fa, a_bundle)}~{side_id(fb, b_bundle)}"


def utc(iso: str | None) -> str | None:
    """A local ISO time in UTC: the offset would tell roughly where someone lives."""
    try:
        t = dt.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    if t.tzinfo is None:
        return None
    return t.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def capture_bundle(result: dict) -> dict:
    """result.json as it's shared: everything about the run, nothing about the person."""
    r = copy.deepcopy(result)
    cap = r.setdefault("capture", {})
    cap["started"] = utc(cap.get("started"))
    fg = cap.pop("foreground", None)
    cap["foreground_is_game"] = (
        None if fg is None else fg.lower() == str(cap.get("app") or "").lower()
    )
    cap["other_presenters"] = len(cap.get("other_presenters") or [])  # how many, not which
    cap.pop("source", None)  # the CLI's path to the CSV
    game = r.get("game")
    if isinstance(game, dict):
        game.pop("window_title", None)
    system = r.get("system")
    if isinstance(system, dict):
        system["errors"] = len(system.get("errors") or [])
    return scrub(r)


def filtered_csv(path: Path, pid: int | None) -> bytes | None:
    """The PresentMon CSV with only the game's rows, gzipped. None when there's nothing to send.

    PresentMon records every process that presented a frame, so the full file names the other
    apps that were open (a browser, a chat app). Only the game's own process stays.
    """
    if pid is None or not path.is_file():
        return None
    out = io.BytesIO()
    kept = 0
    with (
        open(path, newline="", encoding="utf-8-sig", errors="replace") as f,
        gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as gz,
    ):
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        reader = csv.reader(f)
        writer = csv.writer(text, lineterminator="\n")
        try:
            header = next(reader)
        except StopIteration:
            return None
        try:
            col = header.index("ProcessID")
        except ValueError:
            return None
        writer.writerow(header)
        want = str(pid)
        for row in reader:
            if len(row) > col and row[col] == want:
                writer.writerow(row)
                kept += 1
        text.flush()
        text.detach()
    data = out.getvalue()
    return data if kept and len(data) <= MAX_CSV_BYTES else None


def comparison_bundle(
    a: dict,
    b: dict,
    a_id: str,
    b_id: str,
    goal: str | None = None,
    target: int | None = None,
    copied: bool = False,
    a_runs: list[str] | None = None,
    b_runs: list[str] | None = None,
) -> dict:
    """What the comparison showed: the goal's verdict, every delta and the settings changed.

    The two captures are shared on their own, so the server and the aggregate tool can
    always recompute this; it records which pairs people compared and what they concluded.
    A side that is a bundle is its runs combined, as the Compare view showed it: a and b are
    then its newest run that counts, and a_runs / b_runs every run that counts, oldest first.
    """
    g, tgt = report.resolve_goal(b, goal, target)
    status, _ = summary.goal_status(a, b, g, tgt)
    head, _items, notes = summary.compare_verdict(a, b, g, tgt)
    deltas = {
        name: {"a": d.a, "b": d.b, "change": d.change, "status": d.status}
        for name, d in summary.goal_deltas(a, b, tgt).items()
    }
    changes = summary.settings_changes(a, b)
    game = b.get("game") or {}
    return scrub(
        {
            "a": a_id,
            "b": b_id,
            "game": {k: game.get(k) for k in ("exe", "name", "store_id", "build", "engine")},
            "goal": g.key,
            "target_fps": tgt,
            "status": status,
            "verdict": summary.plain(head),
            "notes": [summary.plain(n) for n in notes],
            "settings_changed": [list(c) for c in changes] if changes is not None else None,
            "settings_unchanged_but_moved": summary.settings_unchanged_but_moved(a, b, tgt),
            "deltas": deltas,
            "advice": (b.get("user") or {}).get("advice"),
            "copied": copied,
            "a_runs": a_runs if a_runs and len(a_runs) > 1 else None,
            "b_runs": b_runs if b_runs and len(b_runs) > 1 else None,
            "benchmark": {"a": summary.benchmark(a), "b": summary.benchmark(b)},
        }
    )


def digest(data) -> str:
    raw = data if isinstance(data, bytes) else json.dumps(data, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


# --- transport -------------------------------------------------------------------------------


def _is_cert_error(err: BaseException) -> bool:
    reason = getattr(err, "reason", err)
    return "CERTIFICATE_VERIFY_FAILED" in str(reason) or "CERTIFICATE_VERIFY_FAILED" in str(err)


def _urllib(method: str, url: str, body: bytes, ctype: str) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url, data=body, method=method, headers={"Content-Type": ctype, "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _curl(method: str, url: str, body: bytes, ctype: str) -> tuple[int, bytes]:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise ShareError("no curl.exe to fall back on")
    with tempfile.TemporaryDirectory() as tmp:
        src, dst = Path(tmp) / "body", Path(tmp) / "reply"
        src.write_bytes(body)
        cmd = [curl, "-sS", "-X", method, "-A", USER_AGENT, "-H", f"Content-Type: {ctype}"]
        cmd += ["--data-binary", f"@{src}", "-o", str(dst), "-w", "%{http_code}", url]
        if sys.platform == "win32":
            cmd.insert(1, "--ssl-revoke-best-effort")
        run = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if run.returncode != 0:
            raise ShareError(f"curl failed: {run.stderr.strip() or run.returncode}")
        return int(run.stdout.strip() or 0), dst.read_bytes() if dst.exists() else b""


def request(method: str, url: str, body: bytes, ctype: str) -> tuple[int, bytes]:
    """(status, body). Network trouble raises ShareError."""
    try:
        return _urllib(method, url, body, ctype)
    except (urllib.error.URLError, OSError) as e:
        if _is_cert_error(e):
            return _curl(method, url, body, ctype)
        raise ShareError(f"no connection: {getattr(e, 'reason', e)}") from e


# --- the sharer --------------------------------------------------------------------------------


@dataclass
class Outcome:
    sent: int = 0
    unchanged: int = 0
    failed: int = 0
    total: int = 0  # everything this install has shared so far
    error: str | None = None


class Sharer:
    """Sends what changed since the last time. Safe to call from a worker thread.

    State (shared.json next to settings.json): the install ID, and for each capture and
    comparison the digest of what was last sent and whether its CSV arrived. A failed upload
    simply stays different and goes again on the next sync, so there is no separate queue.
    """

    def __init__(
        self,
        state_path: Path | None = None,
        endpoint: str | None = None,
        transport=None,
        clock=None,
    ):
        self.path = state_path or STATE_PATH
        self.endpoint = (ENDPOINT if endpoint is None else endpoint).rstrip("/")
        self.transport = transport or request
        self.clock = clock or time.time
        self.lock = threading.Lock()
        self.state = self._load()

    # state
    def _load(self) -> dict:
        try:
            state = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {}
        state.setdefault("install", None)
        state.setdefault("captures", {})
        state.setdefault("pairs", {})
        state.setdefault("csv_wait_until", 0)
        return state

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(self.state, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    @property
    def available(self) -> bool:
        return bool(self.endpoint)

    @property
    def has_shared(self) -> bool:
        return bool(self.state.get("install")) and bool(
            self.state["captures"] or self.state["pairs"]
        )

    @property
    def total(self) -> int:
        caps = sum(1 for c in self.state["captures"].values() if c.get("sha"))
        return caps + sum(1 for p in self.state["pairs"].values() if p.get("sha"))

    def install_id(self) -> str:
        with self.lock:
            if not self.state.get("install"):
                self.state["install"] = str(uuid.uuid4())
                self._save()
            return self.state["install"]

    def note_pair(
        self,
        fa: Path,
        fb: Path,
        goal: str,
        target: int | None,
        copied=False,
        a_runs: list[Path] | None = None,
        b_runs: list[Path] | None = None,
        a_bundle: str | None = None,
        b_bundle: str | None = None,
    ) -> None:
        """Remember a comparison the user looked at (or copied); the next sync sends it.

        fa / fb: the run standing for each side; a_runs / b_runs: a bundle's runs that count
        (oldest first) and its id, so the shared comparison is the one the Compare view
        showed."""
        key = comparison_id(
            fa,
            fb,
            a_bundle if a_runs and len(a_runs) > 1 else None,
            b_bundle if b_runs and len(b_runs) > 1 else None,
        )
        with self.lock:
            pair = self.state["pairs"].setdefault(key, {})
            new = {"a": str(fa), "b": str(fb), "goal": goal, "target": target}
            for side, runs in (("a_runs", a_runs), ("b_runs", b_runs)):
                if runs and len(runs) > 1:
                    new[side] = [str(f) for f in runs]
            new["copied"] = bool(copied or pair.get("copied"))
            if any(pair.get(k) != v for k, v in new.items()):
                pair.update(new)
                self._save()

    # sending
    def _post(self, fn: str, body: dict) -> dict:
        status, raw = self.transport(
            "POST", f"{self.endpoint}/{fn}", json.dumps(body).encode(), "application/json"
        )
        try:
            reply = json.loads(raw or b"{}")
        except ValueError:
            reply = {}
        if status != 200:
            raise ShareError(reply.get("error") or f"HTTP {status}", status)
        return reply

    def _send(self, kind: str, local_id: str, data: dict, blob: bytes | None) -> dict:
        body = {
            "install": self.install_id(),
            "kind": kind,
            "id": local_id,
            "schema": SCHEMA,
            "app": __version__,
            "data": data,
        }
        if blob is not None:
            body["csv"] = {"bytes": len(blob), "sha256": digest(blob)}
        reply = self._post("share", body)
        if blob is not None and reply.get("csv_upload"):
            status, _ = self.transport("PUT", reply["csv_upload"], blob, "application/gzip")
            if status not in (200, 201):
                raise ShareError(f"CSV upload failed: HTTP {status}", status)
        return reply

    def _csv_allowed(self) -> bool:
        return self.clock() >= float(self.state.get("csv_wait_until") or 0)

    def _sync_capture(self, folder: Path, result: dict, out: Outcome) -> None:
        """Send the bundle when it changed, and the CSV once (when the inbox has room for it).

        state "csv": the CSV's digest once it arrived, "none" when there's none to send, ""
        while it still has to go.
        """
        cid = capture_id(folder)
        data = capture_bundle(result)
        sha = digest(data)
        with self.lock:
            st = dict(self.state["captures"].get(cid, {}))
        csv_needed = not st.get("csv")
        csv_now = csv_needed and self._csv_allowed()
        if st.get("sha") == sha and not csv_now:
            out.unchanged += 1
            return
        blob = None
        if csv_now:
            blob = filtered_csv(folder / "presentmon.csv", (result.get("capture") or {}).get("pid"))
        reply = self._send("capture", cid, data, blob)
        if reply.get("csv_deferred"):  # the inbox is full of CSVs: try again in a few hours
            csv = ""
            with self.lock:
                self.state["csv_wait_until"] = self.clock() + CSV_RETRY_S
        elif blob is not None:
            csv = digest(blob)
        elif csv_now:
            csv = "none"
        else:
            csv = st.get("csv", "")
        with self.lock:
            self.state["captures"][cid] = {"sha": sha, "csv": csv}
            self._save()
        out.sent += 1

    def _sync_pair(self, key: str, pair: dict, results: dict[str, dict], out: Outcome) -> None:
        sides = []
        for side in ("a", "b"):
            folders = pair.get(f"{side}_runs") or [pair.get(side, "")]
            runs = [(Path(f), results.get(f)) for f in folders]
            if any(r is None for _, r in runs):  # a capture was deleted locally
                return
            if len(runs) > 1:
                from frametrace import feed  # feed imports quality; keep share light at import

                sides.append((feed.combine(runs), [capture_id(f) for f, _ in runs]))
            else:
                sides.append((runs[0][1], None))
        (a, a_ids), (b, b_ids) = sides
        data = comparison_bundle(
            a,
            b,
            capture_id(Path(pair["a"])),
            capture_id(Path(pair["b"])),
            pair.get("goal"),
            pair.get("target"),
            pair.get("copied", False),
            a_ids,
            b_ids,
        )
        sha = digest(data)
        if pair.get("sha") == sha:
            out.unchanged += 1
            return
        self._send("comparison", key, data, None)
        with self.lock:
            self.state["pairs"][key]["sha"] = sha
            self._save()
        out.sent += 1

    def sync(self, captures: list[tuple[Path, dict]]) -> Outcome:
        """Send every capture and noted comparison whose bundle changed. Stops at the first
        network or server problem (the rest goes next time)."""
        out = Outcome()
        if not self.available:
            out.error = "sharing isn't set up in this build"
            return out
        results = {str(f): r for f, r in captures}
        try:
            for folder, result in captures:
                try:
                    self._sync_capture(folder, result, out)
                except ShareError as e:
                    if e.status in (400, 413):  # this one bundle is refused: skip it
                        out.failed += 1
                        continue
                    raise
            with self.lock:
                pairs = [(k, dict(p)) for k, p in self.state["pairs"].items()]
            for key, pair in pairs:
                try:
                    self._sync_pair(key, pair, results, out)
                except ShareError as e:
                    if e.status in (400, 413):
                        out.failed += 1
                        continue
                    raise
        except ShareError as e:
            out.error = str(e)
            if e.status == 410:  # this install's data was deleted: start over with a new ID
                self.reset()
        except Exception as e:  # never let sharing break the window  # noqa: BLE001
            out.error = f"{type(e).__name__}: {e}"
        out.total = self.total
        return out

    def forget(self) -> int:
        """Delete everything this install shared, on the server and (next export) in the
        public dataset. Returns how many submissions were deleted."""
        with self.lock:
            install = self.state.get("install")
        if not install:
            self.reset()
            return 0
        reply = self._post("forget", {"install": install})
        self.reset()
        return int(reply.get("deleted") or 0)

    def reset(self) -> None:
        """Forget the install ID and what was sent: the next share starts as a new contributor."""
        with self.lock:
            self.state = {"install": None, "captures": {}, "pairs": {}, "csv_wait_until": 0}
            self._save()


def preview(folder: Path) -> str:
    """The exact JSON a capture would be shared as, for `python -m frametrace share-preview`."""
    result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
    data = capture_bundle(result)
    blob = filtered_csv(folder / "presentmon.csv", (result.get("capture") or {}).get("pid"))
    csv_note = (
        f"presentmon.csv: the game's rows only, gzipped, {len(blob):,} bytes"
        if blob
        else "presentmon.csv: not sent (missing or no rows for the game)"
    )
    return json.dumps(data, indent=1) + "\n\n" + csv_note
