"""Per-profile perspective hints read from each profile's SOUL.md.

Hermes already loads a profile's SOUL.md, so a worker knows who it is. But a
meeting agenda pulls hard: in practice a designer and a copywriter both argued
like generic strategy consultants, because nothing in the card asked them to
speak from their own job. council fills the per-panelist role hints from SOUL.md
when the caller did not supply them, so "different profiles, different angles" is
the default rather than something you must remember to configure.

Reading is best-effort by design — a missing or unreadable SOUL is simply no
hint, never a failed meeting.
"""
from __future__ import annotations
import os
import pathlib
import re

_HINT_MAX = 120


def _profiles_dir() -> pathlib.Path:
    home = os.environ.get("HERMES_HOME")
    base = pathlib.Path(home).expanduser() if home else pathlib.Path.home() / ".hermes"
    return base / "profiles"


def _clean(line: str) -> str:
    line = re.sub(r"[*_`]+", "", line)                 # markdown emphasis reads as noise here
    return " ".join(line.split()).strip()


def hint(profile: str) -> str:
    """One line describing what this profile is, or '' when there is nothing to read.

    Takes the first prose line — headings name the file, the line under them says
    who the profile actually is ("저는 Mia입니다. … 디자이너로, …").
    """
    try:
        text = (_profiles_dir() / profile / "SOUL.md").read_text(encoding="utf-8")
    except Exception:
        return ""
    for raw in text.splitlines():
        line = _clean(raw)
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        return line[:_HINT_MAX].rstrip()
    return ""


def roles_for(panel, roles=None) -> dict:
    """Explicit roles win; the rest are filled from SOUL.md where one exists."""
    out = dict(roles or {})
    for profile in panel or []:
        if out.get(profile):
            continue
        got = hint(profile)
        if got:
            out[profile] = got
    return out
