"""The ways in: `python -m jinnverse_tui` (what the debugger runs) starts the one `JinnverseApp`."""

import runpy
import sys
from pathlib import Path

import pytest

from jinnverse_tui import config as configuration
from jinnverse_tui.app import JinnverseApp


def test_python_dash_m_starts_the_app_class_the_screens_import(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Started as `python -m jinnverse_tui.app`, the module ran as `__main__` beside its imported
    copy, and every screen's `isinstance(app, JinnverseApp)` failed (found in VS Code,
    2026-10-08). The package's `__main__` imports the app instead, so there is one class."""
    started: list[JinnverseApp] = []

    def run(self: JinnverseApp) -> None:  # the real one would take over the terminal
        started.append(self)

    monkeypatch.setattr(JinnverseApp, "run", run)
    monkeypatch.setattr(configuration, "config_dir", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["jinnverse_tui", "--server", "http://127.0.0.1:8000"])

    runpy.run_module("jinnverse_tui", run_name="__main__")

    assert len(started) == 1
    assert isinstance(started[0], JinnverseApp)
    assert started[0].config.server == "http://127.0.0.1:8000"
    assert (tmp_path / "config.toml").exists()  # the defaults were written, in the test's folder
