"""Pre-start risk checks. Pure — dependencies injected."""
from __future__ import annotations


def warnings_for(moderator, panel, *, approval_mode_fn, running_profiles) -> list[str]:
    """Return non-fatal warnings about conditions that stall a meeting.

    - No running gateway → ready cards never dispatch.
    - A profile in `manual` approval mode → background workers can time out on
      file/command approval and block, despite the file-tool protocol steer.
    """
    warnings: list[str] = []
    if not running_profiles:
        warnings.append(
            "경고: 실행 중 게이트웨이(디스패처)가 없어 카드가 ready 상태로 멈출 수 있습니다 — `hermes gateway start`.")
    for p in [moderator, *panel]:
        if approval_mode_fn(p) == "manual":
            warnings.append(
                f"경고: '{p}' 프로필의 승인 모드가 manual — 백그라운드 파일/명령 승인이 타임아웃되어 카드가 blocked될 수 있습니다"
                " (프로토콜은 파일 도구를 강제하지만 프로필 정책이 우선). 필요 시 `council resume`으로 재개.")
    return warnings


def card_cap(panel_size: int, max_turns: int) -> int:
    """Generous ceiling on total cards before a meeting is deemed runaway."""
    return (panel_size + 2) * max_turns + 4


def is_runaway(card_count: int, cap: int, final: bool) -> bool:
    """True when a still-open meeting has produced more cards than its cap."""
    return (not final) and cap > 0 and card_count > cap


def doctor_checks(*, enabled_fn, gateway_fn, assignees_fn, home_writable_fn) -> list[tuple]:
    """Read-only environment diagnosis. Each dep is a zero-arg callable.

    Returns [(name, ok: bool, detail: str), ...] — never raises; a failing
    check callable is reported as not-ok with the exception text.
    """
    def _run(name, fn, ok_detail, bad_detail):
        try:
            ok = bool(fn())
        except Exception as exc:  # diagnosis must not crash
            return (name, False, f"{bad_detail} ({type(exc).__name__}: {exc})")
        return (name, ok, ok_detail if ok else bad_detail)

    return [
        _run("plugin enabled", enabled_fn,
             "council 플러그인이 활성화됨", "council이 plugins.enabled에 없음 — `hermes plugins enable council`"),
        _run("gateway running", gateway_fn,
             "게이트웨이(디스패처) 실행 중", "실행 중 게이트웨이 없음 — 카드가 ready로 멈춤, `hermes gateway start`"),
        _run("kanban reachable", assignees_fn,
             "hermes kanban 도달 가능", "hermes kanban 호출 실패 — 설치/PATH 확인"),
        _run("registry writable", home_writable_fn,
             "~/.hermes/.council 쓰기 가능", "레지스트리 경로에 쓸 수 없음"),
    ]
