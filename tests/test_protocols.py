from council import protocols

BASE = dict(topic="T", slug="demo", moderator="sophie",
            panel=["mia", "noah"], max_turns=5, allow_early_stop=True,
            transcript_path="/x/transcript.md")


def test_kickoff_sequential_has_core_markers():
    b = protocols.build_kickoff(mode="sequential", **BASE)
    assert "transcript.md" in b
    assert "먼저" in b and "읽" in b            # read-first rule
    assert "kanban_create" in b and "assignee" in b
    assert "CAP: 5" in b
    assert "council-demo" in b                  # board name embedded
    assert "SUMMARY" in b and "FINAL" in b       # dual-write convention known upfront
    assert "파일 편집 도구" in b and "shell" in b   # steer to file tool, not shell (avoids approval block)


def test_kickoff_parallel_mentions_parents_and_simultaneous():
    b = protocols.build_kickoff(mode="parallel", **BASE)
    assert "parents=" in b
    assert "동시" in b                          # simultaneous dispatch of panel cards


def test_speaker_carries_turn_and_hands_to_moderator():
    b = protocols.build_speaker(mode="sequential", turn=2, speaker="noah", **BASE)
    assert "TURN 2" in b
    assert "assignee='sophie'" in b or 'assignee="sophie"' in b


def test_finalize_forbids_next_card():
    b = protocols.build_finalize(topic="T", slug="demo", moderator="sophie",
                                 transcript_path="/x/transcript.md", reason="사용자 종료")
    assert "다음 카드" in b and ("만들지" in b or "생성하지" in b)
    assert "SUMMARY" in b and "FINAL" in b


def test_kickoff_embeds_roles_and_brief_note():
    b = protocols.build_kickoff(mode="sequential", roles={"mia": "시장 관점", "noah": "운영 관점"},
                                brief_note="참고자료: brief.md를 읽어라.", **BASE)
    assert "패널 역할:" in b and "mia=시장 관점" in b
    assert "brief.md" in b


def test_speaker_embeds_its_role():
    b = protocols.build_speaker(mode="sequential", turn=1, speaker="mia", role="시장 관점", **BASE)
    assert "지정 관점: 시장 관점" in b


PBASE = dict(topic="T", slug="demo", moderator="sophie", panel=["mia", "noah"],
             max_turns=3, allow_early_stop=True, transcript_path="/x/transcript.md")


def test_parallel_kickoff_has_round_rule():
    b = protocols.build_kickoff(mode="parallel", **BASE)
    assert "라운드 반복 규칙" in b and "ROUND" in b


def test_parallel_moderator_continues_when_round_below_cap():
    b = protocols.build_parallel_moderator(round=1, **PBASE)
    assert "ROUND: 1 / CAP: 3" in b
    assert "다음 라운드" in b and "TURN 2" in b


def test_parallel_moderator_finalizes_at_cap():
    b = protocols.build_parallel_moderator(round=3, **PBASE)
    assert "SUMMARY+FINAL+DECISIONS" in b
    assert "발언 카드를 만들지 말고" in b


def test_kickoff_hitl_adds_gate_rule():
    b = protocols.build_kickoff(mode="sequential", hitl=True, **BASE)
    assert "HITL" in b and "결정 요청" in b and "awaiting-human" in b
    b2 = protocols.build_kickoff(mode="sequential", hitl=False, **BASE)
    assert "결정 요청" not in b2


def test_every_card_carries_a_rerun_guard():
    """A resumed card re-runs from the top; it must not append or send twice."""
    b = protocols.build_kickoff(mode="sequential", **BASE)
    assert "재실행된 카드" in b
    assert "같은 프로필·같은 TURN" in b


def test_rerun_guard_continues_the_turn_instead_of_jumping_to_next_card():
    """C1: on a resumed HITL/CAP card the rerun guard must not force the worker
    into step 4 (next-card creation) — it must let the remaining steps of this
    turn run, since those may be SUMMARY+FINAL+DECISIONS + chain termination."""
    b = protocols.build_kickoff(mode="sequential", **BASE)
    assert "재실행된 카드" in b
    assert "다음 카드 생성 단계로 넘어가라" not in b       # no longer routes to step 4
    assert "다음 카드 생성으로 곧장 건너뛰지 마라" in b
    assert "나머지 단계" in b and "계속" in b


def test_kickoff_embeds_the_relay_block_when_given():
    block = "\n■ 채널 중계\n- 테스트 지시문\n"
    b = protocols.build_kickoff(mode="sequential", relay_block=block, **BASE)
    assert "■ 채널 중계" in b and "테스트 지시문" in b


def test_kickoff_without_relay_block_is_unchanged():
    assert protocols.build_kickoff(mode="sequential", relay_block="", **BASE) == \
           protocols.build_kickoff(mode="sequential", **BASE)


def test_hitl_rule_tells_the_moderator_to_announce_the_gate_on_the_channel():
    b = protocols.build_kickoff(mode="sequential", hitl=True,
                                relay_block="\n■ 채널 중계\n- x\n", **BASE)
    assert "결정 요청" in b and "채널에도" in b


def test_speech_asks_for_spoken_register_but_the_closing_documents_stay_formal():
    """The transcript is what the channel shows, so speeches must read as speech.

    SUMMARY/FINAL/DECISIONS are deliverables, not speech — they keep the document
    register, so the split has to be stated in the protocol, not left to taste.
    """
    b = protocols.build_kickoff(mode="sequential", **BASE)
    assert "말하듯" in b                       # speeches
    assert "문서" in b                         # the closing blocks are documents
    speech_at = b.index("말하듯")
    closing_at = b.index("## [SUMMARY]")
    assert speech_at < closing_at             # the register rule comes with the append rule


def _split_turn(body: str):
    """Split a card body into "what every card carries" and "this turn only".

    `== 이번 차례 ==` also appears inside rule 4's card-creation example, so the
    real turn block is the last occurrence, not the first.
    """
    i = body.rindex("== 이번 차례 ==")
    return body[:i], body[i:]


def test_hitl_gate_is_the_moderators_alone():
    """Only the moderator may stop the meeting to ask a person.

    The HITL rule used to sit in the header, and rule 4 tells every worker to copy
    the protocol forward — so panel cards carried "leave a 결정 요청 and
    kanban_block" too. A panelist acting on it blocks a card nobody is waiting
    for: `council decide` resolves the moderator's gate, not a speaker's, so the
    meeting stops silently. Panels have opinions; the moderator holds the gate.
    """
    b = protocols.build_kickoff(mode="sequential", hitl=True, **BASE)
    head, turn = _split_turn(b)
    # The gate instruction — write a 결정 요청, then block — must not reach a
    # panel card. The header may still name kanban_block, but only to forbid it.
    assert "kanban_block(reason=" not in head
    assert "kanban_block을 부르거나" in head     # panels are told not to
    assert "kanban_block(reason=" in turn       # the moderator's own turn holds the gate
    assert "결정 요청" in turn
    assert "사회자만" in b


def test_panels_are_told_to_raise_it_in_their_speech_instead():
    b = protocols.build_kickoff(mode="sequential", hitl=True, **BASE)
    assert "자기 발언에 적기만" in _split_turn(b)[0]


def test_parallel_mode_keeps_the_gate_with_the_moderator_too():
    b = protocols.build_kickoff(mode="parallel", hitl=True, **BASE)
    head, turn = _split_turn(b)
    assert "kanban_block(reason=" not in head
    assert "결정 요청" in turn


def test_no_hitl_means_no_gate_anywhere():
    b = protocols.build_kickoff(mode="sequential", hitl=False, **BASE)
    assert "결정 요청" not in b and "사회자만" not in b
