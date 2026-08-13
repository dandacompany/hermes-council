from council import relay


def test_parse_target_platform_only():
    t = relay.parse_target("slack")
    assert t == {"platform": "slack", "chat": "", "thread": "", "explicit_thread": False}


def test_parse_target_with_channel():
    t = relay.parse_target("slack:#council")
    assert t["platform"] == "slack" and t["chat"] == "#council"
    assert t["thread"] == "" and t["explicit_thread"] is False


def test_parse_target_with_explicit_thread():
    t = relay.parse_target("telegram:-1001234567890:17585")
    assert t["chat"] == "-1001234567890"
    assert t["thread"] == "17585" and t["explicit_thread"] is True


def test_format_target_round_trips():
    for spec in ("slack", "slack:#council", "telegram:-100123:17585"):
        assert relay.format_target(relay.parse_target(spec)) == spec


def test_can_open_thread_only_for_slack_without_explicit_thread():
    # Slack's third segment is the parent message ts, which `hermes send` returns.
    assert relay.can_open_thread(relay.parse_target("slack:#council")) is True
    # Telegram's is a forum topic id — not derivable from a sent message.
    assert relay.can_open_thread(relay.parse_target("telegram:-100123")) is False
    # Discord's is an existing thread channel id — `hermes send` cannot create one.
    assert relay.can_open_thread(relay.parse_target("discord:#ops")) is False
    # A user-supplied thread is honored as-is; council must not overwrite it.
    assert relay.can_open_thread(relay.parse_target("slack:#council:1755.1")) is False


def test_relay_capable_keeps_only_profiles_with_that_platform():
    directory = {
        "sophie": {"platforms": {"slack": [{"name": "Dante"}], "telegram": []}},
        "mia": {"platforms": {"slack": [], "telegram": []}},
    }
    got = relay.relay_capable(["sophie", "mia"], "slack", list_fn=directory.get)
    assert got == {"sophie"}


def test_relay_capable_treats_lookup_failure_as_incapable():
    """A gateway hiccup must never fail a meeting — it just means no relay."""

    def boom(profile):
        raise RuntimeError("gateway down")

    assert relay.relay_capable(["sophie", "mia"], "slack", list_fn=boom) == set()
