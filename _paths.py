"""Registry root resolution — no side effects."""
from __future__ import annotations
import os
import pathlib


def council_home() -> pathlib.Path:
    override = os.environ.get("COUNCIL_HOME")
    if override:
        return pathlib.Path(override).expanduser()
    hermes = os.environ.get("HERMES_HOME")
    base = pathlib.Path(hermes).expanduser() if hermes else pathlib.Path.home() / ".hermes"
    return base / ".council"
