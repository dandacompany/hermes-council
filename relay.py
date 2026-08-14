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


def build_relay_block(*, target: dict, topic: str, capable, proxy_for=None) -> str:
    """The '■ 채널 중계' section embedded in a card body.

    One card body is copied forward to the next, so the block must survive that
    copy unchanged — it is the only carrier a relay chain has, and every second
    card belongs to the moderator, who is the chain's relay. The block therefore
    states its own roster (`capable` — every profile that may send, in meeting
    order) instead of leaning on the card's provenance: a worker checks whether
    its OWN profile is in that roster before running the send command, so the
    same instruction is safe to hand to a capable panelist and an incapable
    moderator alike. Propagation is unconditional — "copy this into the next
    card" — never "copy it to everyone except X"; nobody is ever excluded from
    carrying the block forward, only from the send command inside it.

    `proxy_for` (panelists the moderator proxies for) is only meaningful when the
    moderator itself can send — a moderator with no credentials cannot proxy
    anyone, so callers should pass an empty `proxy_for` in that case (the
    moderator not being in `capable` already keeps it out of the self-send rule).

    Returns "" when `capable` is empty — nobody can send, so nothing belongs in
    the card.
    """
    capable = list(capable or [])
    proxy_for = list(proxy_for or [])
    if not capable:
        return ""
    where = format_target(target)
    subject = f"[council: {topic}]"
    names = ", ".join(capable)
    out = ["\n■ 채널 중계"]
    out.append(
        f"- 발신 가능한 프로필: {names}. 네 프로필이 이 목록에 있으면, 회의록에 append한 직후 "
        "같은 내용을 채널로도 보낸다:\n"
        f'  hermes send --to {where} --subject "{subject} ▸ <네 프로필> — TURN <n>" '
        '--quiet "<네 발언 전문>"\n'
        "  목록에 없으면 이 명령을 실행하지 않는다.")
    if proxy_for:
        names2 = ", ".join(proxy_for)
        out.append(
            f"- 다음 패널은 메신저 자격이 없다: {names2}. 이들의 발언은 사회자가 대신 보낸다.\n"
            "  네가 사회자라면, 네 차례 직전 라운드에서 이들이 회의록에 남긴 발언을 각각 이렇게 보낸다:\n"
            f'  hermes send --to {where} --subject "{subject} ▸ <그 패널> — TURN <n> (대리)" '
            '--quiet "<그 패널의 발언 전문>"\n'
            "  직전 라운드 것만 보낸다(그 이전 것은 이미 보냈다).")
    out.append("- 다음 카드를 만들 때 이 '■ 채널 중계' 절을 그대로 복사한다(누구의 카드든 예외 없이 — "
                "이 절이 회의 끝까지 이어지게 한다).")
    out.append("- 전송 실패해도 무시하고 다음 단계로 진행한다. 회의는 절대 멈추지 않는다.")
    return "\n".join(out) + "\n"


def section_key(section: dict) -> str:
    """Identity of one transcript section, stable across re-reads."""
    return f"{section['speaker']}#{section['turn']}#{section['role']}"


def pending_proxy_sections(transcript: str, *, proxy_for, sent_keys) -> list:
    """Transcript sections that council must relay on someone else's behalf.

    Only for profiles in `proxy_for` — a profile that can send posts its own speech
    from its own card, under its own identity. `sent_keys` is what already went out;
    it lives on disk, so re-attaching a run cannot double-post.
    """
    try:
        from . import render
    except ImportError:
        import render  # type: ignore
    proxy_for, sent = set(proxy_for or []), set(sent_keys or [])
    out = []
    for s in render.parse_sections(transcript):
        if s["speaker"] not in proxy_for:
            continue
        s = {**s, "key": section_key(s)}
        if s["key"] not in sent:
            out.append(s)
    return out


def proxy_subject(topic: str, section: dict) -> str:
    return f"[council: {topic}] ▸ {section['speaker']} — TURN {section['turn']} (대리)"


# Conversation platforms first: a meeting reads as a conversation, and email or a
# push-only channel is a poor home for one. Anything not listed still works when
# the caller names it explicitly; this order only decides the automatic pick.
_PLATFORM_PREFERENCE = ("slack", "discord", "telegram", "matrix", "teams",
                        "google_chat", "signal", "whatsapp")


def auto_platform(moderator: str, *, list_fn) -> str:
    """The platform a meeting relays to when the caller named no target.

    Relay is on by default, so this has to answer "where?" without being told.
    It answers from the moderator's own messaging directory — the meeting speaks
    where its moderator can speak — and returns "" when it cannot send anywhere,
    which is the common case and means "no relay", not "problem".
    """
    try:
        platforms = (list_fn(moderator) or {}).get("platforms") or {}
    except Exception:
        return ""
    have = {name for name, rows in platforms.items() if rows}
    for name in _PLATFORM_PREFERENCE:
        if name in have:
            return name
    return sorted(have)[0] if have else ""


def opted_out(moderator: str) -> bool:
    """True when the moderator's profile config says council must not relay.

    A profile that should never broadcast its meetings says so once, in
    `council: {relay: false}`, instead of every caller having to remember.
    """
    try:
        from . import souls
    except ImportError:
        import souls  # type: ignore
    try:
        import yaml
        text = (souls._profiles_dir() / moderator / "config.yaml").read_text(encoding="utf-8")
        cfg = yaml.safe_load(text) or {}
        return (cfg.get("council") or {}).get("relay") is False
    except Exception:
        return False                       # unreadable config is not an opt-out


def _session_env(name: str, default: str = "") -> str:
    """Read a gateway session context var, or "" when there is no gateway.

    The gateway sets these per request (task-local, so concurrent messages do not
    clobber each other) and falls back to os.environ for CLI/cron. Wrapped here so
    tests can stand in for a conversation, and so a Hermes without this module
    simply means "no conversation".
    """
    try:
        from gateway.session_context import get_session_env
        return get_session_env(name, default) or default
    except Exception:
        import os
        return os.environ.get(name, default) or default


def current_conversation() -> str:
    """Where the request came from, as a `hermes send --to` target, or "".

    Someone who asks for a meeting in a Slack thread means "show it to me here",
    and making them name the channel pushes our plumbing into their prompt. The
    gateway already knows, so read it rather than ask.

    A chat id is required: a thread id alone cannot be delivered to. An agent that
    knew only the thread ts passed `slack:<ts>` and every send failed, which is the
    failure this exists to prevent.
    """
    platform = _session_env("HERMES_SESSION_PLATFORM").strip()
    chat = _session_env("HERMES_SESSION_CHAT_ID").strip()
    if not platform or not chat:
        return ""
    thread = _session_env("HERMES_SESSION_THREAD_ID").strip()
    # Slack stamps every top-level message with a thread id equal to its own ts,
    # as a session key rather than a place ("when thread_id == reply_to the
    # 'thread' is synthetic" — plugins/platforms/slack/adapter.py). Joining it
    # would bury the meeting in an ephemeral thread around the single message
    # that asked for it, instead of the conversation the asker is watching.
    if thread and thread == _session_env("HERMES_SESSION_MESSAGE_ID").strip():
        thread = ""
    return f"{platform}:{chat}:{thread}" if thread else f"{platform}:{chat}"
