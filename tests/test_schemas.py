import argparse

from council import cli, schemas


def test_all_four_present_and_shaped():
    assert set(schemas.ALL) == {"council_start", "council_status", "council_collect", "council_stop",
                                "council_resume", "council_say", "council_archive",
                                "council_decide", "council_vote",
                                "council_relay_flush"}
    for name, s in schemas.ALL.items():
        assert s["name"] == name
        assert isinstance(s["description"], str) and s["description"]
        assert s["parameters"]["type"] == "object"


def test_start_requires_core_fields():
    props = schemas.START_SCHEMA["parameters"]["properties"]
    assert {"topic", "panel", "moderator", "mode"} <= set(props)
    assert set(schemas.START_SCHEMA["parameters"]["required"]) >= {"topic", "panel", "moderator"}
    assert props["mode"]["enum"] == ["sequential", "parallel"]


def test_start_exposes_hitl_like_the_cli():
    """The CLI's --hitl must be reachable from natural language too (agent tool call)."""
    props = schemas.START_SCHEMA["parameters"]["properties"]
    assert props["hitl"]["type"] == "boolean"
    assert "hitl" not in schemas.START_SCHEMA["parameters"]["required"]


def test_cli_start_options_are_all_reachable_from_the_tool_schema():
    """Whatever `hermes council start` can pass to handle_start, an agent must be able to pass too."""
    p = argparse.ArgumentParser()
    cli._add_start_args(p)
    args = p.parse_args(["--topic", "T", "--panel", "mia", "--moderator", "sophie"])
    payload = cli._start_args(args)
    assert set(payload) <= set(schemas.START_SCHEMA["parameters"]["properties"])


def test_start_exposes_relay_options():
    props = schemas.START_SCHEMA["parameters"]["properties"]
    assert props["relay"]["type"] == "string"
    assert props["relay_thread"]["type"] == "boolean"
