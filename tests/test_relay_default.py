"""Relay is on by default: opening a meeting should not require remembering to ask.

Having to say "and relay this to the channel" made relay fail silently — a caller
who forgot got a full meeting with an empty channel and no warning. The person
opening a meeting knows where it will go; wanting it NOT to go to the channel is
the exception, so that is what you now state.
"""
import json

import pytest

from council import board, registry, relay, tools


def _dir(**platforms):
    return {"platforms": {k: [{"name": "x"}] if v else [] for k, v in platforms.items()}}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia"])
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {})
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    return monkeypatch


def test_auto_platform_picks_the_one_the_moderator_can_send_on(env):
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True, telegram=False))
    assert relay.auto_platform("sophie", list_fn=board.send_targets) == "slack"


def test_auto_platform_prefers_the_richer_conversation_platform(env):
    """Several platforms configured: pick deterministically, not by dict order."""
    env.setattr(board, "send_targets", lambda p, **k: _dir(email=True, telegram=True, slack=True))
    assert relay.auto_platform("sophie", list_fn=board.send_targets) == "slack"
    env.setattr(board, "send_targets", lambda p, **k: _dir(email=True, telegram=True))
    assert relay.auto_platform("sophie", list_fn=board.send_targets) == "telegram"


def test_auto_platform_is_empty_when_nothing_is_configured(env):
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=False))
    assert relay.auto_platform("sophie", list_fn=board.send_targets) == ""


def test_start_relays_without_being_asked(env):
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))
    env.setattr(board, "send", lambda **kw: "1755.1")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    rl = registry.load_meta(out["slug"])["relay"]
    assert rl["target"] == "slack:1755.1"            # bare platform -> Hermes routes to home
    assert any("중계" in w and "slack" in w for w in out["warnings"])


def test_start_says_where_it_is_relaying_to(env):
    """The operator must learn the destination at start, not by checking the channel."""
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))
    env.setattr(board, "send", lambda **kw: "1755.1")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert any(w.startswith("안내: 발언을") for w in out["warnings"])


def test_relay_false_turns_it_off_entirely(env):
    def boom(**kw):
        raise AssertionError("relay:false must not send")

    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))
    env.setattr(board, "send", boom)
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "relay": False}))
    assert registry.load_meta(out["slug"])["relay"] is None
    assert not any("중계" in w for w in out["warnings"])


def test_explicit_target_still_wins(env):
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True, telegram=True))
    env.setattr(board, "send", lambda **kw: "1755.1")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "relay": "telegram:-100123"}))
    assert registry.load_meta(out["slug"])["relay"]["target"].startswith("telegram:-100123")


def test_no_credentials_means_no_relay_and_no_noise(env):
    """Most profiles have no messenger at all; that must stay silent, not warn."""
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=False))
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert registry.load_meta(out["slug"])["relay"] is None
    assert not any("중계" in w for w in out["warnings"])


def test_a_dead_target_disables_relay_instead_of_failing_every_speech(env):
    """The header send doubles as a probe: a bot that is not in the channel fails
    every later post too, so say so once at start rather than silently each turn."""
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))

    def dead(**kw):
        raise board.BoardError("not_in_channel")

    env.setattr(board, "send", dead)
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert "error" not in out                              # the meeting still runs
    assert registry.load_meta(out["slug"])["relay"] is None
    assert any("초대" in w for w in out["warnings"])


def test_an_explicit_target_that_fails_is_reported_the_same_way(env):
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))

    def dead(**kw):
        raise board.BoardError("channel_not_found")

    env.setattr(board, "send", dead)
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "relay": "slack:#nope"}))
    assert registry.load_meta(out["slug"])["relay"] is None
    assert any("초대" in w for w in out["warnings"])


def test_dry_run_still_sends_nothing(env):
    def boom(**kw):
        raise AssertionError("dry_run must not send")

    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))
    env.setattr(board, "send", boom)
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "dry_run": True}))
    assert out["dry_run"] is True


def test_profile_config_can_turn_the_default_off(env, tmp_path):
    """A profile that should never relay says so once, instead of at every call."""
    d = tmp_path / "hermes" / "profiles" / "sophie"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.yaml").write_text("council:\n  relay: false\n", encoding="utf-8")

    def boom(**kw):
        raise AssertionError("profile opted out of relay")

    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))
    env.setattr(board, "send", boom)
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert registry.load_meta(out["slug"])["relay"] is None
