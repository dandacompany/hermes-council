"""Relay to the conversation the meeting was asked for in.

Naming a channel is the plugin's problem leaking into the prompt: someone who
says "hold a meeting" in Slack means "and show it to me here". The gateway
already knows where "here" is — it sets session context vars for the platform,
chat and thread that a request arrived on — so council reads that instead of
asking. Falls back to the moderator's home channel when there is no conversation
(CLI, cron), which is where it used to go anyway.
"""
import json

import pytest

from council import board, registry, relay, tools


def _dir(**platforms):
    return {"platforms": {k: [{"name": "x"}] if v else [] for k, v in platforms.items()}}


def _session(monkeypatch, **vars):
    """Stand in for the gateway's session context vars."""
    monkeypatch.setattr(relay, "_session_env", lambda name, default="": vars.get(name, default))


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
    monkeypatch.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))
    monkeypatch.setattr(board, "send", lambda **kw: "1755.new")
    _session(monkeypatch)                      # no conversation unless a test sets one
    return monkeypatch


def test_current_conversation_uses_platform_chat_and_thread(env):
    _session(env, HERMES_SESSION_PLATFORM="slack",
             HERMES_SESSION_CHAT_ID="C0B8", HERMES_SESSION_THREAD_ID="1786681649.684969")
    assert relay.current_conversation() == "slack:C0B8:1786681649.684969"


def test_current_conversation_without_a_thread_is_just_the_channel(env):
    _session(env, HERMES_SESSION_PLATFORM="slack", HERMES_SESSION_CHAT_ID="C0B8")
    assert relay.current_conversation() == "slack:C0B8"


def test_current_conversation_needs_a_chat_id_not_just_a_thread(env):
    """A thread id alone cannot be delivered to — that is what made a live run
    fail, with the agent passing `slack:<ts>` because the ts was all it knew."""
    _session(env, HERMES_SESSION_PLATFORM="slack", HERMES_SESSION_THREAD_ID="1786681649.68")
    assert relay.current_conversation() == ""


def test_current_conversation_is_empty_outside_a_conversation(env):
    assert relay.current_conversation() == ""


def test_start_relays_into_the_asking_thread(env):
    _session(env, HERMES_SESSION_PLATFORM="slack",
             HERMES_SESSION_CHAT_ID="C0B8", HERMES_SESSION_THREAD_ID="1786681649.684969")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    rl = registry.load_meta(out["slug"])["relay"]
    assert rl["target"] == "slack:C0B8:1786681649.684969"
    assert rl["thread"] == "1786681649.684969"       # the asking thread, not a new one


def test_the_asking_thread_is_not_replaced_by_a_new_one(env):
    """council opens a thread of its own only when it has no thread to join."""
    opened = []
    env.setattr(board, "send", lambda **kw: opened.append(kw["target"]) or "1755.new")
    _session(env, HERMES_SESSION_PLATFORM="slack",
             HERMES_SESSION_CHAT_ID="C0B8", HERMES_SESSION_THREAD_ID="1786681649.684969")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert opened == ["slack:C0B8:1786681649.684969"]        # header posted into that thread
    assert registry.load_meta(out["slug"])["relay"]["thread"] == "1786681649.684969"


def test_a_channel_conversation_still_opens_its_own_thread(env):
    _session(env, HERMES_SESSION_PLATFORM="slack", HERMES_SESSION_CHAT_ID="C0B8")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    rl = registry.load_meta(out["slug"])["relay"]
    assert rl["thread"] == "1755.new"                        # header message anchors a thread
    assert rl["target"] == "slack:C0B8:1755.new"


def test_an_explicit_target_still_wins_over_the_conversation(env):
    _session(env, HERMES_SESSION_PLATFORM="slack", HERMES_SESSION_CHAT_ID="C0B8")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "relay": "slack:#elsewhere"}))
    assert registry.load_meta(out["slug"])["relay"]["target"].startswith("slack:#elsewhere")


def test_falls_back_to_the_home_channel_outside_a_conversation(env):
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert registry.load_meta(out["slug"])["relay"]["target"].startswith("slack")


def test_a_conversation_the_moderator_cannot_send_on_is_not_used(env):
    """Session says telegram, but the moderator only has slack configured."""
    _session(env, HERMES_SESSION_PLATFORM="telegram", HERMES_SESSION_CHAT_ID="-100123")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    rl = registry.load_meta(out["slug"])["relay"]
    assert rl is None or not rl["target"].startswith("telegram")


def test_a_thread_id_equal_to_the_message_id_is_not_a_thread(env):
    """Slack gives every top-level message a thread id equal to its own ts.

    The inbound handler sets it as a session-keying fallback (slack adapter:
    "when thread_id == reply_to the 'thread' is synthetic"). Treating it as a
    real thread pins the whole meeting inside an ephemeral thread spawned around
    the one message that asked for it — not where the conversation is.
    """
    _session(env, HERMES_SESSION_PLATFORM="slack", HERMES_SESSION_CHAT_ID="C0B8",
             HERMES_SESSION_THREAD_ID="1786681649.684969",
             HERMES_SESSION_MESSAGE_ID="1786681649.684969")
    assert relay.current_conversation() == "slack:C0B8"      # channel, no thread


def test_a_real_thread_survives_the_synthetic_check(env):
    _session(env, HERMES_SESSION_PLATFORM="slack", HERMES_SESSION_CHAT_ID="C0B8",
             HERMES_SESSION_THREAD_ID="1786600000.111111",
             HERMES_SESSION_MESSAGE_ID="1786681649.684969")
    assert relay.current_conversation() == "slack:C0B8:1786600000.111111"


def test_start_opens_its_own_thread_when_the_asking_thread_was_synthetic(env):
    """Dropping the synthetic thread must not cost the meeting a thread — council
    still anchors one with its own header message, in the right channel."""
    _session(env, HERMES_SESSION_PLATFORM="slack", HERMES_SESSION_CHAT_ID="C0B8",
             HERMES_SESSION_THREAD_ID="1786681649.684969",
             HERMES_SESSION_MESSAGE_ID="1786681649.684969")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    rl = registry.load_meta(out["slug"])["relay"]
    assert rl["target"] == "slack:C0B8:1755.new"
