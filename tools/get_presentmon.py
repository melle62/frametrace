"""Download the pinned PresentMon console exe into ./bin and verify its SHA-256.

    python tools/get_presentmon.py

Also downloads Intel's LICENSE.txt and THIRD_PARTY.txt, which must ship next to
the exe whenever Frametrace redistributes it. The exe is never committed to git.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frametrace.presentmon import (
    BIN_DIR,
    DOWNLOAD_URL,
    EXE_NAME,
    EXE_SHA256,
    NOTICE_URLS,
    PINNED_VERSION,
)


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "frametrace-setup"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> int:
    BIN_DIR.mkdir(exist_ok=True)
    target = BIN_DIR / EXE_NAME

    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == EXE_SHA256:
        print(f"{target} already present and verified.")
    else:
        print(f"Downloading PresentMon {PINNED_VERSION} ...")
        data = download(DOWNLOAD_URL)
        digest = hashlib.sha256(data).hexdigest()
        if digest != EXE_SHA256:
            print(f"SHA-256 mismatch!\n  expected {EXE_SHA256}\n  got      {digest}")
            print("Not saving the file. Check the release page before trusting this download.")
            return 1
        target.write_bytes(data)
        print(f"Saved and verified: {target}")

    for name, url in NOTICE_URLS.items():
        path = BIN_DIR / name
        if not path.is_file():
            path.write_bytes(download(url))
            print(f"Saved {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
