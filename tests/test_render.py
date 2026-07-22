from council import render

SAMPLE = """## [sophie] — TURN 0 (moderator·킥오프)
안건 정리.

## [mia] — TURN 1 (speaker)
의견 A.

## [sophie] — TURN 1 (moderator)
판단.

## [SUMMARY]
- 핵심 결론 1
- 핵심 결론 2

## [FINAL] 결론 보고서
### 1. 결정
본문 결론.
"""

META = dict(topic="T", slug="demo", mode="sequential",
            moderator="sophie", panel=["mia"])


def test_split_extracts_three_parts():
    out = render.split(SAMPLE, **META)
    assert out["final_reached"] is True
    assert "핵심 결론 1" in out["summary"]
    assert "## [SUMMARY]" not in out["summary"]        # marker stripped, content kept
    assert "본문 결론." in out["report"]
    assert "결론 보고서" in out["report"]
    assert "## [mia] — TURN 1" in out["transcript_export"]   # full transcript preserved
    assert out["transcript_export"].startswith("# ")          # export has a title header


def test_split_without_final_flags_partial():
    partial = "## [sophie] — TURN 0 (moderator·킥오프)\n안건.\n"
    out = render.split(partial, **META)
    assert out["final_reached"] is False
    assert "미도달" in out["summary"] or "부분" in out["summary"]
