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
