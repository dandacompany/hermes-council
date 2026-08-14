"""Turning relay off has to be something you say, not something you can fall into.

Relay is on by default, and the way a model expressed "nothing was asked about
this" was `relay: false` — which reads as "turn it off". A live meeting ran with
no relay because of exactly that. So the argument that names a target and the
argument that disables relaying are now separate: `relay` takes a target string,
and only `relay_off` disables. Omitting both cannot disable anything.
"""
import json

import pytest

from council import board, registry, relay, schemas, tools


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
    monkeypatch.setattr(board, "send_targets", lambda p, **k: _dir(slack=True))
    monkeypatch.setattr(board, "send", lambda **kw: "1755.1")
    return monkeypatch


def test_schema_gives_relay_a_string_type_so_false_is_not_expressible():
    """A model reaching for "not applicable" must not land on something that
    disables the feature. `relay` is a target; typing it as a string removes
    `false` from the shapes the model can produce."""
    props = schemas.START_SCHEMA["parameters"]["properties"]
    assert props["relay"]["type"] == "string"
    assert props["relay_off"]["type"] == "boolean"
    assert "relay_off" in props["relay"]["description"]      # points at the real off switch


def test_omitting_everything_relays(env):
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert registry.load_meta(out["slug"])["relay"] is not None


def test_relay_off_true_disables(env):
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "relay_off": True}))
    meta = registry.load_meta(out["slug"])
    assert meta["relay"] is None
    assert meta["relay_off_reason"] == "off_requested"


def test_relay_false_still_disables_for_callers_that_already_use_it(env):
    """The CLI's --no-relay sends relay=false; keep honouring it."""
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "relay": False}))
    assert registry.load_meta(out["slug"])["relay"] is None


def test_a_target_string_still_selects_the_target(env):
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie",
                                         "relay": "slack:#council"}))
    assert registry.load_meta(out["slug"])["relay"]["target"].startswith("slack:#council")


def test_meta_says_why_relay_is_off_when_nobody_can_send(env):
    env.setattr(board, "send_targets", lambda p, **k: _dir(slack=False))
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    meta = registry.load_meta(out["slug"])
    assert meta["relay"] is None
    assert meta["relay_off_reason"] == "no_capable_profile"


def test_meta_says_why_relay_is_off_when_the_target_is_unreachable(env):
    def dead(**kw):
        raise board.BoardError("not_in_channel")

    env.setattr(board, "send", dead)
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    meta = registry.load_meta(out["slug"])
    assert meta["relay"] is None
    assert meta["relay_off_reason"] == "target_unreachable"


def test_meta_says_why_relay_is_off_when_the_profile_opted_out(env, tmp_path):
    d = tmp_path / "hermes" / "profiles" / "sophie"
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.yaml").write_text("council:\n  relay: false\n", encoding="utf-8")
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    meta = registry.load_meta(out["slug"])
    assert meta["relay"] is None
    assert meta["relay_off_reason"] == "profile_opted_out"


def test_relay_on_leaves_no_reason(env):
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert registry.load_meta(out["slug"])["relay_off_reason"] is None


def test_cli_no_relay_maps_to_relay_off():
    """--no-relay must reach the handler as the explicit off switch, and the CLI
    must not send `relay: True` — the tool schema types relay as a string."""
    import argparse

    from council import cli
    p = argparse.ArgumentParser()
    cli._add_start_args(p)
    plain = cli._start_args(p.parse_args(["--topic", "T", "--panel", "mia", "--moderator", "s"]))
    assert plain["relay_off"] is False
    assert plain["relay"] in (None, "")               # never the boolean True
    off = cli._start_args(p.parse_args(["--topic", "T", "--panel", "mia", "--moderator", "s",
                                        "--no-relay"]))
    assert off["relay_off"] is True


def test_council_start_instruction_tells_the_agent_to_omit_relay():
    """The /council handoff text is closer to the model than the schema is, and
    grouping relay with "fill only what was mentioned" is what produced
    `relay: false` on a request that never mentioned relaying."""
    out = tools.handle_council_command("회의를 열어줘. 패널은 mia, 의장은 sophie.")
    # the command no longer instructs the agent at all, so the guidance lives in
    # the skill — assert there instead
    import pathlib
    skill = (pathlib.Path(__file__).parent.parent / "skills" / "council" / "SKILL.md").read_text()
    assert "relay" in skill and "넘기지" in skill
