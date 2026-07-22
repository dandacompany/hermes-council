"""Pure builders for self-propagating meeting card bodies. No side effects."""
from __future__ import annotations

PROTOCOL_RULES = """\
[회의 자동진행 프로토콜 — council]
- 회의록 파일: {transcript_path} (이 회의의 유일한 공식 기록).
- 레지스트리 규약: 이 회의는 ~/.hermes/.council/{slug}/ 아래에 저장된다(meta.json·transcript.md·산출물). 보드는 council-{slug}.

■ 절대 규칙 (모든 카드 공통)
1) 먼저 {transcript_path} 전문을 읽어 사회자 지시와 이전 발언을 모두 파악한다.
2) 아래 "== 이번 차례 =="의 역할을 수행한다.
3) 네 발언/판단을 회의록 끝에 append 한다(덮어쓰기 금지):
   ## [<프로필>] — TURN <n> (<speaker|moderator>)
   <내용>
   ★반드시 파일 편집 도구(write/edit/append_file 등 네게 있는 파일 도구)로 기록하라.
   python3·bash·shell 명령으로 파일을 쓰지 마라 — 백그라운드에서는 실행 승인이 지연되어 카드가 차단된다.
4) 다음 카드를 만들어 공을 넘긴다:
   kanban_create(board="council-{slug}", assignee="<다음 프로필>", max_runtime_seconds=480,
     body="<이 프로토콜 전체 복사>\\n\\n== 진행 상태 ==\\nTURN: <값> / CAP: {cap}\\n\\n== 이번 차례 ==\\n<다음 지시>")
   그리고 kanban_complete(summary="한 줄", created_cards=["<새 카드 id>"]).
5) 카드 body에 transcript 내용을 넣지 마라(회의록은 파일이다).
6) assignee는 실존 프로필이어야 한다: 사회자 {moderator} / 패널 {panel}.

■ 카운팅 & 종료
- 패널 발언마다 TURN +1. 사회자 판단 카드는 TURN을 올리지 않는다.
- allow_early_stop={early}. TURN이 CAP({cap})에 도달했거나(사회자가 수렴 판단하면, early_stop이 참일 때) 사회자는 다음 발언 카드를 만들지 말고, 회의록에 아래 두 블록을 함께 기록한 뒤 kanban_complete만 하고 체인을 끝낸다(created_cards 없음):
   ## [SUMMARY]
   <5~10줄 임원 요약>

   ## [FINAL] 결론 보고서
   <구조화된 결론 본문>

   ## [DECISIONS]
   - 결정: <확정된 사항>
   - 액션: <담당 프로필/사람> — <할 일>
   - 미결: <남은 질문/후속 필요>
"""


def _ctx(mode, topic, slug, moderator, panel, max_turns, allow_early_stop, transcript_path):
    return dict(mode=mode, topic=topic, slug=slug, moderator=moderator,
                panel=", ".join(panel), cap=max_turns,
                early="참" if allow_early_stop else "거짓",
                transcript_path=transcript_path)


def _roles_line(roles) -> str:
    if not roles:
        return ""
    parts = ", ".join(f"{k}={v}" for k, v in roles.items())
    return f"패널 역할: {parts}\n"


def _header(topic, mode, panel, moderator, max_turns, allow_early_stop, transcript_path, slug,
            roles=None, brief_note=""):
    rules = PROTOCOL_RULES.format(**_ctx(mode, topic, slug, moderator, panel,
                                         max_turns, allow_early_stop, transcript_path))
    extra = _roles_line(roles)
    if brief_note:
        extra += brief_note + "\n"
    return (f"안건: {topic}\n사회자: {moderator} / 패널: {', '.join(panel)} / 방식: {mode}\n"
            + extra + "\n" + rules)


_HITL_RULE = (
    "\n■ HITL(사람 개입) 모드\n"
    "- 이 회의는 HITL 모드다. FINAL을 쓰기 '직전'에 반드시 회의록에 다음 게이트를 남기고 대기하라:\n"
    "  ## [결정 요청] <시각>\n  질문: <사람에게 물을 핵심 결정>\n  선택지: <A / B / ...>(있으면)\n"
    "  그런 다음 SUMMARY/FINAL을 쓰지 말고 kanban_block(reason='awaiting-human: <질문>')로 멈춘다.\n"
    "- 사람이 회의록에 '## [사용자 결정]'을 남기고 카드를 unblock하면, 그 결정을 반영해 "
    "SUMMARY+FINAL(+DECISIONS)을 작성하고 종료한다.\n")


def build_kickoff(*, mode, topic, slug, moderator, panel, max_turns,
                  allow_early_stop, transcript_path, roles=None, brief_note="", hitl=False) -> str:
    head = _header(topic, mode, panel, moderator, max_turns, allow_early_stop,
                   transcript_path, slug, roles=roles, brief_note=brief_note)
    if hitl:
        head += _HITL_RULE
    if mode == "parallel":
        turn_block = (
            "== 진행 상태 ==\nROUND: 1 / CAP: {cap}\n\n"
            "== 이번 차례 ==\n(사회자 {mod} · 킥오프 · parallel)\n"
            "1) 회의록에 안건·쟁점을 '## [{mod}] — TURN 0 (moderator·킥오프)'로 기록.\n"
            "2) 패널 {panel} 전원에게 '동시에' SPEAKER 카드를 각각 만든다"
            "(모두 assignee=각 패널, 이번 라운드 = TURN 1, 서로의 발언은 이번 턴엔 못 봄).\n"
            "3) 이어 종합 카드 1장을 만든다: kanban_create(board=\"council-{slug}\", "
            "assignee=\"{mod}\", parents=[방금 만든 SPEAKER 카드 id 전부], body=<MODERATOR(ROUND 1) 지시>).\n"
            "   MODERATOR 지시에는 아래 '라운드 반복 규칙'을 반드시 포함한다.\n"
            "4) kanban_complete(summary=\"parallel 킥오프\", created_cards=[전체 새 카드 id]).\n\n"
            "■ 라운드 반복 규칙 (parallel 종합 카드가 따른다)\n"
            "- 종합 카드는 parents(그 라운드 패널 전원)가 끝난 뒤 실행된다. 회의록의 그 라운드 발언을 종합해 "
            "'## [{mod}] — TURN <R> (moderator)'로 기록한다.\n"
            "- ROUND R < CAP({cap})이고 논의가 더 필요하면: 다음 라운드 패널 SPEAKER 카드 전원(각 TURN R+1)을 동시 생성 + "
            "새 종합 카드(parents=그 패널들, body에 이 규칙 유지, ROUND R+1)를 만든다.\n"
            "- ROUND R == CAP 또는 수렴 시: 발언 카드를 만들지 말고 SUMMARY+FINAL+DECISIONS로 종료한다."
        ).format(cap=max_turns, mod=moderator, panel=", ".join(panel), slug=slug)
    else:
        turn_block = (
            "== 진행 상태 ==\nTURN: 0 / CAP: {cap}\n\n"
            "== 이번 차례 ==\n(사회자 {mod} · 킥오프 · sequential)\n"
            "1) 회의록에 안건·쟁점을 '## [{mod}] — TURN 0 (moderator·킥오프)'로 기록.\n"
            "2) 첫 발언자 1명을 정하고 발언 범위를 가이드한다.\n"
            "3) SPEAKER 카드를 만든다: kanban_create(board=\"council-{slug}\", "
            "assignee=\"<첫 발언자>\", body=<프로토콜+진행상태(TURN 0)+SPEAKER 지시(이번 발언=TURN 1)>).\n"
            "4) kanban_complete(summary=\"킥오프\", created_cards=[새 카드 id])."
        ).format(cap=max_turns, mod=moderator, slug=slug)
    return head + "\n\n" + turn_block


def build_speaker(*, mode, topic, slug, moderator, panel, max_turns,
                  allow_early_stop, transcript_path, turn, speaker,
                  roles=None, brief_note="", role="") -> str:
    head = _header(topic, mode, panel, moderator, max_turns, allow_early_stop,
                   transcript_path, slug, roles=roles, brief_note=brief_note)
    role_line = f"네 지정 관점: {role}\n" if role else ""
    block = (
        "== 진행 상태 ==\nTURN: {t} / CAP: {cap}\n\n"
        "== 이번 차례 ==\n(발언자 {sp} · TURN {t} · speaker)\n" + role_line +
        "회의록을 읽고 네 전문 관점에서 안건에 대한 '구체적' 의견을 1~2가지 제시하라"
        "(중복 회피, 추상론 금지). 회의록에 '## [{sp}] — TURN {t} (speaker)'로 append 후, "
        "공을 사회자에게 넘겨라: kanban_create(board=\"council-{slug}\", assignee='{mod}', "
        "body=<프로토콜+진행상태(TURN {t})+MODERATOR 지시(직전 발언=TURN {t})>). "
        "kanban_complete(summary=\"{sp} 발언\", created_cards=[새 카드 id])."
    ).format(t=turn, cap=max_turns, sp=speaker, mod=moderator, slug=slug)
    return head + "\n\n" + block


def build_moderator(*, mode, topic, slug, moderator, panel, max_turns,
                    allow_early_stop, transcript_path, turn, roles=None, brief_note="") -> str:
    head = _header(topic, mode, panel, moderator, max_turns, allow_early_stop,
                   transcript_path, slug, roles=roles, brief_note=brief_note)
    block = (
        "== 진행 상태 ==\nTURN: {t} / CAP: {cap}\n\n"
        "== 이번 차례 ==\n(사회자 {mod} · 판단 · 직전 발언 TURN {t})\n"
        "회의록을 읽고 (1) 방금 발언 핵심 1~2줄 정리, (2) 중복·발산·추상화 점검, "
        "(3) 다음 관점 판단. 모든 패널이 최소 1회 발언하도록 배분하라. "
        "CAP({cap}) 미만이고 논의가 더 필요하면 다음 발언자 1명에게 SPEAKER 카드(그 발언=TURN {tn})를 만든다. "
        "CAP 도달 또는 수렴 시에는 프로토콜 종료 규칙대로 SUMMARY+FINAL을 기록하고 체인을 끝낸다."
    ).format(t=turn, cap=max_turns, mod=moderator, tn=turn + 1)
    return head + "\n\n" + block


def build_parallel_moderator(*, round, topic, slug, moderator, panel, max_turns,
                             allow_early_stop, transcript_path, roles=None, brief_note="") -> str:
    """Synthesis-card body for a parallel round R (used/embedded by the moderator)."""
    head = _header(topic, "parallel", panel, moderator, max_turns, allow_early_stop,
                   transcript_path, slug, roles=roles, brief_note=brief_note)
    if round < max_turns:
        tail = (
            "ROUND {r} < CAP({cap})이고 논의가 더 필요하면: 다음 라운드 패널 {panel} 전원에게 "
            "SPEAKER 카드(각 TURN {rn})를 '동시에' 만들고, 새 종합 카드(parents=그 패널 전원, ROUND {rn}, "
            "body에 이 라운드 규칙 유지)를 만든다. 수렴했다고 판단하면 대신 SUMMARY+FINAL+DECISIONS로 종료한다."
        ).format(r=round, cap=max_turns, panel=", ".join(panel), rn=round + 1)
    else:
        tail = ("ROUND {r}이 CAP({cap})에 도달했다. 발언 카드를 만들지 말고 "
                "SUMMARY+FINAL+DECISIONS를 기록하고 체인을 끝낸다.").format(r=round, cap=max_turns)
    block = (
        "== 진행 상태 ==\nROUND: {r} / CAP: {cap}\n\n"
        "== 이번 차례 ==\n(사회자 {mod} · ROUND {r} 종합 · parallel)\n"
        "회의록에서 이번 라운드 패널 발언을 읽고 '## [{mod}] — TURN {r} (moderator)'로 종합을 기록하라. "
    ).format(r=round, cap=max_turns, mod=moderator) + tail
    return head + "\n\n" + block


def build_finalize(*, topic, slug, moderator, transcript_path, reason="") -> str:
    why = f"(사유: {reason})" if reason else ""
    return (
        f"안건: {topic}\n사회자: {moderator} / 방식: 강제 종합{why}\n\n"
        f"== 이번 차례 ==\n(사회자 {moderator} · 즉시 종합 · 종료)\n"
        f"지금 {transcript_path} 전문을 읽고, 더 이상 다음 카드(발언 카드)를 '만들지' 말고 회의록 끝에 "
        f"'## [SUMMARY]'(5~10줄)·'## [FINAL] 결론 보고서'(구조화 본문)·'## [DECISIONS]'(결정·액션·미결)를 함께 기록하라"
        f"(반드시 파일 편집 도구로 기록, shell/python 금지). "
        f"그런 다음 kanban_complete(summary=\"회의 강제 종료·종합\")로 끝낸다(created_cards 없음)."
    )
