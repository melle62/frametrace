"""Fixtures shared by the test files."""

from __future__ import annotations

import pytest


@pytest.fixture
def tk_root():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    root.withdraw()
    yield root
    try:
        root.destroy()
    except tk.TclError:
        pass


@pytest.fixture(autouse=True)
def no_live_sharing(tmp_path, monkeypatch):
    """No test may reach the live inbox or the real shared.json.

    A window test that turns sharing on would otherwise send its fake captures to the
    Frametrace dataset (it did on 2026-11-27, from CI). Tests that need a sharer pass their
    own endpoint and fake transport.
    """
    from frametrace import share

    monkeypatch.setattr(share, "ENDPOINT", "")
    monkeypatch.setattr(share, "STATE_PATH", tmp_path / "shared-test.json")

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to reach the network through share.request")

    monkeypatch.setattr(share, "request", refuse)
