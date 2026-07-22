from council import lint

CLEAN = """## [sophie] — TURN 0 (moderator·킥오프)
안건.

## [mia] — TURN 1 (speaker)
의견.

## [SUMMARY]
- 결론.

## [FINAL] 결론 보고서
본문.
"""


def test_clean_transcript_no_warnings():
    assert lint.lint_transcript(CLEAN) == []


def test_bad_header_flagged():
    bad = "## [mia] TURN 1 speaker\n내용.\n"       # missing —/parens
    w = lint.lint_transcript(bad)
    assert any("형식 오류 헤더" in x for x in w)


def test_double_final_flagged():
    t = CLEAN + "\n## [FINAL] 또 다른 결론\n중복.\n"
    assert any("여러 개" in x for x in lint.lint_transcript(t))


def test_final_without_summary_flagged():
    t = "## [sophie] — TURN 0 (moderator·킥오프)\n안건.\n\n## [FINAL] 결론\n본문.\n"
    assert any("SUMMARY" in x for x in lint.lint_transcript(t))
