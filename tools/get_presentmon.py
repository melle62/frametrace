"""Download the pinned PresentMon console exe into ./bin and verify its SHA-256.

    python tools/get_presentmon.py

The Frametrace window offers the same download; see frametrace/download.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from frametrace.download import ensure_presentmon

if __name__ == "__main__":
    sys.exit(0 if ensure_presentmon() else 1)
