"""Pure builders for channel relay. No side effects — council never sends from here.

council has no process running between cards, so the workers do the relaying
themselves. This module only computes *what instruction text* to embed in a card
body, plus the small amount of target arithmetic that decision needs.
"""
from __future__ import annotations

# Platforms where council can OPEN a thread from a message it just sent.
# Slack's third target segment is `thread_ts` — the parent message's id, which
# `hermes send --json` returns. Telegram's is a forum *topic* id and Discord's is
# an existing thread *channel* id; neither is derivable from a sent message, so
# council never fabricates one for them (it would misroute).
THREAD_OPENERS = frozenset({"slack"})


def parse_target(spec: str) -> dict:
    """'slack' | 'slack:#council' | 'telegram:-100…:17585' -> parts."""
    parts = [p.strip() for p in str(spec or "").split(":")]
    platform = parts[0] if parts else ""
    chat = parts[1] if len(parts) > 1 else ""
    thread = parts[2] if len(parts) > 2 else ""
    return {"platform": platform, "chat": chat, "thread": thread,
            "explicit_thread": bool(thread)}


def format_target(target: dict) -> str:
    out = target.get("platform", "")
    if target.get("chat"):
        out += ":" + target["chat"]
    if target.get("thread"):
        out += ":" + target["thread"]
    return out


def can_open_thread(target: dict) -> bool:
    """True only when council may derive a thread id from its own header message."""
    if target.get("explicit_thread"):
        return False                       # the user picked the thread; don't touch it
    return target.get("platform") in THREAD_OPENERS


def relay_capable(profiles, platform: str, *, list_fn) -> set:
    """Profiles that actually have a configured target on `platform`.

    `list_fn(profile)` returns that profile's messaging directory (see
    board.send_targets). A profile whose lookup raises, returns nothing, or has an
    empty list for the platform is incapable — the caller then routes its speech
    through the moderator instead of handing a worker a command that must fail.
    """
    capable = set()
    for profile in profiles:
        try:
            directory = list_fn(profile) or {}
            if (directory.get("platforms") or {}).get(platform):
                capable.add(profile)
        except Exception:
            continue                       # incapable, not fatal
    return capable
