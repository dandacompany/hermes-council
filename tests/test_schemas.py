from council import schemas


def test_all_four_present_and_shaped():
    assert set(schemas.ALL) == {"council_start", "council_status", "council_collect", "council_stop",
                                "council_resume", "council_say", "council_archive",
                                "council_decide", "council_vote"}
    for name, s in schemas.ALL.items():
        assert s["name"] == name
        assert isinstance(s["description"], str) and s["description"]
        assert s["parameters"]["type"] == "object"


def test_start_requires_core_fields():
    props = schemas.START_SCHEMA["parameters"]["properties"]
    assert {"topic", "panel", "moderator", "mode"} <= set(props)
    assert set(schemas.START_SCHEMA["parameters"]["required"]) >= {"topic", "panel", "moderator"}
    assert props["mode"]["enum"] == ["sequential", "parallel"]
