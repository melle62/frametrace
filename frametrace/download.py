"""Download the pinned PresentMon console exe into ./bin and verify its SHA-256.

Also downloads Intel's LICENSE.txt and THIRD_PARTY.txt, which must ship next to
the exe whenever Frametrace redistributes it. The exe is never committed to git.

If Python can't verify GitHub's certificate (common on debloated Windows, where
automatic root-certificate updates are often turned off), the download falls back to
Windows' own curl.exe, which still verifies the certificate but uses Windows'
certificate handling. The SHA-256 check applies whichever way the file arrives.
"""

from __future__ import annotations

import hashlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from frametrace.presentmon import (
    BIN_DIR,
    DOWNLOAD_URL,
    EXE_NAME,
    EXE_SHA256,
    NOTICE_URLS,
    PINNED_VERSION,
)

CREATE_NO_WINDOW = 0x08000000

USER_AGENT = "frametrace-setup"


class DownloadError(RuntimeError):
    pass


def _is_cert_error(err: BaseException) -> bool:
    reason = getattr(err, "reason", err)
    return isinstance(reason, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(
        err
    )


def _download_urllib(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _download_curl(url: str) -> bytes:
    curl = shutil.which("curl.exe") or shutil.which("curl")
    if not curl:
        raise DownloadError("curl.exe not found")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "download"
        cmd = [curl, "-fsSL", "--retry", "2", "-A", USER_AGENT, "-o", str(out), url]
        if sys.platform == "win32":
            # Don't fail when the revocation server is unreachable; the certificate is still verified.
            cmd.insert(1, "--ssl-revoke-best-effort")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        if result.returncode != 0 or not out.is_file():
            raise DownloadError(f"curl failed: {result.stderr.strip() or result.returncode}")
        return out.read_bytes()


def download(url: str, say=print) -> bytes:
    try:
        return _download_urllib(url)
    except urllib.error.URLError as err:
        if not _is_cert_error(err):
            raise DownloadError(str(err)) from err
        say("Python couldn't verify the HTTPS certificate (a root certificate is missing from")
        say("Windows' store). Retrying with Windows' curl.exe ...")
    try:
        return _download_curl(url)
    except (DownloadError, OSError, subprocess.SubprocessError) as err:
        raise DownloadError(str(err)) from err


def manual_instructions() -> str:
    return (
        "Download it manually instead:\n"
        f"  1. Open {DOWNLOAD_URL} in your browser.\n"
        f"  2. Save it as {BIN_DIR / EXE_NAME}\n"
        "  3. Run this script again to verify it."
    )


def ensure_presentmon(say=print) -> bool:
    """Download and verify PresentMon if needed. Returns True when bin/ has a verified exe."""
    BIN_DIR.mkdir(exist_ok=True)
    target = BIN_DIR / EXE_NAME

    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == EXE_SHA256:
        say(f"{target} already present and verified.")
    else:
        if target.is_file():
            say(f"{target.name} exists but its SHA-256 doesn't match; downloading again.")
        say(f"Downloading PresentMon {PINNED_VERSION} ...")
        try:
            data = download(DOWNLOAD_URL, say)
        except DownloadError as err:
            say(f"Download failed: {err}\n{manual_instructions()}")
            return False
        digest = hashlib.sha256(data).hexdigest()
        if digest != EXE_SHA256:
            say(f"SHA-256 mismatch!\n  expected {EXE_SHA256}\n  got      {digest}")
            say("Not saving the file. Check the release page before trusting this download.")
            return False
        target.write_bytes(data)
        say(f"Saved and verified: {target}")

    # Intel's notices are only needed when redistributing PresentMon, so a failure here
    # is a warning, not an error.
    for name, url in NOTICE_URLS.items():
        path = BIN_DIR / name
        if path.is_file():
            continue
        try:
            path.write_bytes(download(url, say))
            say(f"Saved {path.name}")
        except DownloadError as err:
            say(f"Warning: couldn't download {name} ({err}). Not needed for capturing.")
    return True
