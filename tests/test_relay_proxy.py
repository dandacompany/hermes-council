"""Poller-side proxy relay: council posts the speeches nobody can send for themselves.

Self-sends stay with the workers (a profile speaks under its own identity). Proxy
sends have already given that up — they carry a '▸ name' header under someone
else's credentials — so they can be done deterministically from the transcript
instead, which is the only way to cover a meeting whose moderator cannot send.
"""
import json

import pytest

from council import board, registry, relay, runner, tools

TRANSCRIPT = (
    "## [sophie] — TURN 0 (moderator·킥오프)\n안건 정리.\n\n"
    "## [mia] — TURN 1 (speaker)\n시장은 이렇게 봅니다.\n\n"
    "## [sophie] — TURN 1 (moderator)\n다음은 noah.\n\n"
    "## [noah] — TURN 2 (speaker)\n운영 리스크는 이렇습니다.\n"
)


def test_pending_proxy_sections_skips_profiles_that_send_for_themselves():
    pending = relay.pending_proxy_sections(TRANSCRIPT, proxy_for=["sophie", "mia"], sent_keys=[])
    assert [(s["speaker"], s["turn"]) for s in pending] == [("sophie", 0), ("mia", 1), ("sophie", 1)]
    assert all(s["speaker"] != "noah" for s in pending)      # noah relays its own speech


def test_pending_proxy_sections_are_keyed_so_a_resend_cannot_happen():
    first = relay.pending_proxy_sections(TRANSCRIPT, proxy_for=["mia"], sent_keys=[])
    assert len(first) == 1
    again = relay.pending_proxy_sections(TRANSCRIPT, proxy_for=["mia"],
                                         sent_keys=[s["key"] for s in first])
    assert again == []


def test_section_key_distinguishes_same_speaker_across_turns():
    keys = {s["key"] for s in relay.pending_proxy_sections(TRANSCRIPT, proxy_for=["sophie"],
                                                           sent_keys=[])}
    assert len(keys) == 2                                    # sophie TURN 0 and TURN 1


@pytest.fixture
def meeting(tmp_path, monkeypatch):
    """A started meeting whose moderator cannot send but whose panelist noah can."""
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia", "noah"])
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {})
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    monkeypatch.setattr(board, "send_targets", lambda p, **k: {
        "platforms": {"slack": [{"name": "Dante"}] if p == "noah" else []}})
    monkeypatch.setattr(board, "send", lambda **kw: "1755.0")   # header probe
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia", "noah"],
                                         "moderator": "sophie", "relay": "slack:#council"}))
    slug = out["slug"]
    (registry.meeting_dir(slug) / "transcript.md").write_text(TRANSCRIPT, encoding="utf-8")
    return slug


def test_start_routes_proxying_to_the_poller_when_the_moderator_cannot_send(meeting):
    meta = registry.load_meta(meeting)
    assert meta["relay"]["proxy_for"] == []                  # no worker-side proxy: sophie can't send
    assert meta["relay"]["poller_proxy_for"] == ["sophie", "mia"]
    assert meta["relay"]["sender"] == "noah"                 # first capable in meeting order


def test_relay_flush_sends_each_unsent_section_once(meeting, monkeypatch):
    sent = []
    monkeypatch.setattr(board, "send", lambda **kw: sent.append(kw) or f"ts{len(sent)}")
    first = json.loads(tools.handle_relay_flush({"slug": meeting}))
    assert first["sent"] == 3
    assert [k["profile"] for k in sent] == ["noah", "noah", "noah"]
    assert "▸ sophie — TURN 0" in sent[0]["subject"] and "(대리)" in sent[0]["subject"]
    assert "시장은 이렇게 봅니다" in sent[1]["message"]
    # a second pass is a no-op — the record is on disk, so a re-attached run cannot double-post
    again = json.loads(tools.handle_relay_flush({"slug": meeting}))
    assert again["sent"] == 0 and len(sent) == 3


def test_relay_flush_records_only_what_actually_went_out(meeting, monkeypatch):
    """A failed send must stay pending so the next tick retries it."""
    calls = {"n": 0}

    def flaky(**kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise board.BoardError("network")
        return "ts"

    monkeypatch.setattr(board, "send", flaky)
    first = json.loads(tools.handle_relay_flush({"slug": meeting}))
    assert first["sent"] == 2 and first["failed"] == 1
    monkeypatch.setattr(board, "send", lambda **kw: "ts")
    retry = json.loads(tools.handle_relay_flush({"slug": meeting}))
    assert retry["sent"] == 1                                 # only the one that failed


def test_relay_flush_is_a_noop_without_relay(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia"])
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {})
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    (registry.meeting_dir(out["slug"]) / "transcript.md").write_text(TRANSCRIPT, encoding="utf-8")

    def boom(**kw):
        raise AssertionError("relay off must never send")

    monkeypatch.setattr(board, "send", boom)
    assert json.loads(tools.handle_relay_flush({"slug": out["slug"]}))["sent"] == 0


def test_drive_flushes_the_proxy_queue_on_every_tick():
    """The poller is what makes proxying deterministic — it must run each poll."""
    ticks = []
    result = runner.drive(
        "s",
        status_fn=lambda s: {"final_reached": len(ticks) >= 2, "blocked": []},
        resume_fn=lambda s: {}, collect_fn=lambda s: {"written": {}},
        relay_fn=lambda s: ticks.append(s) or {"sent": 1},
        sleep_fn=lambda n: None, interval=1, max_ticks=5)
    assert result["outcome"] == "final"
    assert ticks == ["s", "s", "s"]          # including the tick that saw FINAL


def test_drive_survives_a_relay_flush_error():
    def boom(slug):
        raise RuntimeError("relay down")

    result = runner.drive(
        "s", status_fn=lambda s: {"final_reached": True, "blocked": []},
        resume_fn=lambda s: {}, collect_fn=lambda s: {"written": {}},
        relay_fn=boom, sleep_fn=lambda n: None, interval=1, max_ticks=3)
    assert result["outcome"] == "final"


def test_thread_is_opened_by_the_sending_profile_not_the_moderator(tmp_path, monkeypatch):
    """An incapable moderator must not cost the meeting its thread.

    council's own sends go out as `sender` (the first capable profile), so the
    header message that anchors the thread must be sent by that profile too —
    otherwise every relayed speech lands as a separate top-level message.
    """
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia", "noah"])
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {})
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    monkeypatch.setattr(board, "send_targets", lambda p, **k: {
        "platforms": {"slack": [{"name": "Dante"}] if p == "noah" else []}})
    opened = []
    monkeypatch.setattr(board, "send", lambda **kw: opened.append(kw) or "1755.9")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia", "noah"],
                                         "moderator": "sophie", "relay": "slack:D0B3"}))
    assert opened and opened[0]["profile"] == "noah"          # not sophie, which cannot send
    rl = registry.load_meta(out["slug"])["relay"]
    assert rl["thread"] == "1755.9"
    assert rl["target"] == "slack:D0B3:1755.9"                # every later post lands in it
