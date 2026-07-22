from council import render

META = dict(topic="T", slug="demo", mode="sequential", moderator="sophie", panel=["mia"])


def test_final_without_summary_still_produces_report():
    t = ("## [sophie] — TURN 0 (moderator·킥오프)\n안건.\n\n"
         "## [FINAL] 결론 보고서\n본문 결론.\n")
    out = render.split(t, **META)
    assert out["final_reached"] is True
    assert "본문 결론." in out["report"]
    assert "요약 블록 없음" in out["summary"]


def test_decisions_block_extracted_and_report_bounded():
    t = ("## [sophie] — TURN 0 (moderator·킥오프)\n안건.\n\n"
         "## [SUMMARY]\n- 요약.\n\n"
         "## [FINAL] 결론 보고서\n본문 결론.\n\n"
         "## [DECISIONS]\n- 결정: X 채택\n- 액션: mia — 초안\n- 미결: 예산\n")
    out = render.split(t, **META)
    assert "decisions" in out
    assert "X 채택" in out["decisions"] and "mia — 초안" in out["decisions"]
    assert "결정: X 채택" not in out["report"]     # report must stop before DECISIONS
    assert "본문 결론." in out["report"]


def test_no_decisions_block_omits_key():
    t = ("## [sophie] — TURN 0 (moderator·킥오프)\n안.\n\n"
         "## [SUMMARY]\n- s\n\n## [FINAL] 결론 보고서\n본문.\n")
    assert "decisions" not in render.split(t, **META)


FULL = ("## [sophie] — TURN 0 (moderator·킥오프)\n안건 정리.\n\n"
        "## [mia] — TURN 1 (speaker)\n의견 A.\n\n"
        "## [sophie] — TURN 1 (moderator)\n판단.\n\n"
        "## [SUMMARY]\n- 결론 요약.\n\n"
        "## [FINAL] 결론 보고서\n### 1. 결정\n본문.\n\n"
        "## [DECISIONS]\n- 결정: X 채택\n")


def test_to_json_structures_sections_and_parts():
    j = render.to_json(FULL, **META)
    assert j["final_reached"] is True
    assert j["topic"] == "T" and j["mode"] == "sequential"
    assert "결론 요약." in j["summary"] and "X 채택" in j["decisions"]
    turns = [(s["speaker"], s["turn"], s["role"]) for s in j["sections"]]
    assert ("sophie", 0, "moderator") in turns
    assert ("mia", 1, "speaker") in turns


def test_to_html_is_self_contained():
    parts = render.split(FULL, **META)
    h = render.to_html(parts, topic="T")
    assert h.startswith("<!doctype html>")
    assert "<h1>" in h and "결론 보고서" in h
    assert "http://" not in h and "https://" not in h    # no external assets


def test_pending_decision_open():
    t = ("## [sophie] — TURN 1 (moderator)\n판단.\n\n"
         "## [결정 요청] 2026-07-23T10:00\n질문: 후보 A와 B 중 무엇으로 확정할까요?\n선택지: A / B\n")
    pd = render.parse_pending_decision(t)
    assert pd is not None
    assert "A와 B" in pd["question"] and pd["options"] == ["A", "B"]


def test_pending_decision_resolved_returns_none():
    t = ("## [결정 요청] t1\n질문: X?\n선택지: A / B\n\n"
         "## [사용자 결정] t2\nA로 확정\n")
    assert render.parse_pending_decision(t) is None


def test_no_gate_returns_none():
    assert render.parse_pending_decision("## [mia] — TURN 1 (speaker)\n의견.\n") is None
