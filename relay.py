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


def build_relay_block(*, target: dict, topic: str, speaker_sends: bool,
                      proxy_for, exclude_for=None) -> str:
    """The '■ 채널 중계' section embedded in a card body.

    Two audiences share one block because one card body is copied forward to the
    next: the speaker rule tells whoever holds this card to send its own speech
    (`speaker_sends` — true whenever *someone* in the meeting can send, not just
    the moderator), and the exclusion list tells the card's author which cards
    must NOT receive that rule (any profile with no messaging credentials,
    including the moderator itself when it lacks them — `exclude_for`; defaults
    to `proxy_for` for callers that don't distinguish the two).

    `proxy_for` (panelists the moderator proxies for) is only meaningful when the
    moderator itself can send — a moderator with no credentials cannot proxy
    anyone, so callers should pass an empty `proxy_for` in that case and rely on
    `exclude_for` to keep the doomed send command out of every incapable card.
    """
    proxy_for = list(proxy_for or [])
    exclude_for = list(exclude_for) if exclude_for is not None else list(proxy_for)
    if not speaker_sends and not exclude_for:
        return ""
    where = format_target(target)
    subject = f"[council: {topic}]"
    out = ["\n■ 채널 중계"]
    if speaker_sends:
        out.append(
            "- 회의록에 append한 직후, 같은 내용을 채널로도 보낸다:\n"
            f'  hermes send --to {where} --subject "{subject} ▸ <네 프로필> — TURN <n>" '
            '--quiet "<네 발언 전문>"')
    if proxy_for:
        names = ", ".join(proxy_for)
        out.append(
            f"- 다음 패널은 메신저 자격이 없다: {names}. 이들의 발언은 사회자가 대신 보낸다.\n"
            "  네가 사회자라면, 네 차례 직전 라운드에서 이들이 회의록에 남긴 발언을 각각 이렇게 보낸다:\n"
            f'  hermes send --to {where} --subject "{subject} ▸ <그 패널> — TURN <n> (대리)" '
            '--quiet "<그 패널의 발언 전문>"\n'
            "  직전 라운드 것만 보낸다(그 이전 것은 이미 보냈다).")
    if exclude_for:
        names = ", ".join(exclude_for)
        out.append(
            f"- 다음 카드를 만들 때 이 '■ 채널 중계' 절을 그대로 복사하되, {names}의 카드에는 "
            "복사하지 마라(보낼 수 없는 명령을 주지 않는다).")
    out.append("- 전송 실패해도 무시하고 다음 단계로 진행한다. 회의는 절대 멈추지 않는다.")
    return "\n".join(out) + "\n"
