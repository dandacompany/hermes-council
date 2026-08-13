"""Panelists should speak from their own job, not as interchangeable analysts.

A profile's SOUL.md already gives it an identity and Hermes loads it — but a
meeting's agenda pulls hard, and in practice a designer and a copywriter both
came out sounding like generic strategy consultants. council therefore states the
expectation in the protocol, and fills the per-panelist perspective hints from
each SOUL.md when the caller did not supply them.
"""
import json

from council import board, protocols, registry, souls, tools

SOPHIE_SOUL = """# Identity
당신은 **Sophie**입니다. 직책은 **총무(비서)** — 사용자의 일정·이메일·할 일을 챙깁니다.

# Style
- 정중하지만 간결하게.
"""

MIA_SOUL = """# Mia — MAGMA 디자이너
저는 Mia입니다. MAGMA 전략기획실의 디자이너로, 로고와 VI 컨셉을 만듭니다.

## 회사 — MAGMA
- 3040 남성 패션 브랜드입니다.
"""


def _write_souls(home, mapping):
    for name, text in mapping.items():
        d = home / "profiles" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SOUL.md").write_text(text, encoding="utf-8")


def test_hint_takes_the_identity_sentence_not_the_heading(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_souls(tmp_path, {"mia": MIA_SOUL})
    hint = souls.hint("mia")
    assert "디자이너" in hint
    assert not hint.startswith("#")               # a markdown heading is not a perspective
    assert "MAGMA" in hint


def test_hint_strips_markdown_emphasis_so_the_header_line_stays_readable(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_souls(tmp_path, {"sophie": SOPHIE_SOUL})
    hint = souls.hint("sophie")
    assert "**" not in hint and "총무" in hint


def test_hint_is_empty_when_there_is_no_soul(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assert souls.hint("ghost") == ""


def test_hint_is_capped_so_one_profile_cannot_swamp_the_card(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_souls(tmp_path, {"long": "# T\n" + "가" * 500 + "\n"})
    assert 0 < len(souls.hint("long")) <= 120


def test_roles_for_fills_only_the_gaps(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_souls(tmp_path, {"mia": MIA_SOUL, "sophie": SOPHIE_SOUL})
    got = souls.roles_for(["mia", "sophie"], {"sophie": "진행 관점"})
    assert got["sophie"] == "진행 관점"           # an explicit role is never overwritten
    assert "디자이너" in got["mia"]


def test_protocol_tells_each_worker_to_speak_from_its_own_job():
    body = protocols.build_kickoff(
        mode="sequential", topic="T", slug="s", moderator="sophie", panel=["mia"],
        max_turns=2, allow_early_stop=True, transcript_path="/tmp/t.md")
    assert "네 프로필" in body and "일반론" in body


def test_start_fills_roles_from_souls(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_souls(tmp_path, {"mia": MIA_SOUL, "sophie": SOPHIE_SOUL})
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia"])
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {})
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert "디자이너" in registry.load_meta(out["slug"])["roles"]["mia"]


def test_start_keeps_explicit_roles_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    _write_souls(tmp_path, {"mia": MIA_SOUL})
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia"])
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {})
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "roles": {"mia": "시장 관점"}}))
    assert registry.load_meta(out["slug"])["roles"] == {"mia": "시장 관점"}


def test_start_survives_an_unreadable_soul_dir(tmp_path, monkeypatch):
    """Role auto-fill is a nicety; it must never be able to fail a meeting."""
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "nope"))
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia"])
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {})
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert "error" not in out and registry.load_meta(out["slug"])["roles"] == {}
