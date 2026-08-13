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


TARGET = {"platform": "slack", "chat": "#council", "thread": "1755.1",
          "explicit_thread": True}


def test_relay_block_tells_a_capable_speaker_to_send_its_own_speech():
    block = relay.build_relay_block(target=TARGET, topic="커피머신 교체",
                                    speaker_sends=True, proxy_for=[])
    assert "hermes send --to slack:#council:1755.1" in block
    assert "[council: 커피머신 교체]" in block
    assert "실패해도 무시" in block
    assert "대리" not in block


def test_relay_block_asks_the_moderator_to_proxy_for_incapable_panelists():
    block = relay.build_relay_block(target=TARGET, topic="T",
                                    speaker_sends=True, proxy_for=["mia", "iris"])
    assert "mia, iris" in block
    assert "대리" in block
    # The moderator creates the panel cards; it must not hand a send command to a
    # profile that cannot send.
    assert "복사하지 마라" in block


def test_relay_block_is_empty_when_nobody_can_send():
    assert relay.build_relay_block(target=TARGET, topic="T",
                                   speaker_sends=False, proxy_for=[]) == ""


def test_relay_block_when_moderator_incapable_but_a_panelist_is_not():
    """An incapable moderator cannot proxy anyone — no proxy paragraph — but the
    self-send rule still applies for whoever holds a capable card, and every
    incapable profile (moderator included) must be named in the copy-exclusion
    list so it never receives a doomed send command."""
    block = relay.build_relay_block(target=TARGET, topic="T",
                                    speaker_sends=True, proxy_for=[],
                                    exclude_for=["sophie", "mia"])
    assert "hermes send" in block
    assert "대리" not in block                 # no proxying without a capable moderator
    assert "복사하지 마라" in block and "sophie, mia" in block
