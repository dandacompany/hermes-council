import json
from council import board


def make_runner(mapping):
    calls = []

    def runner(args):
        calls.append(args)
        for key, out in mapping.items():
            if key in args:
                return out
        return ""
    return runner, calls


def test_create_card_returns_id_and_targets_board():
    runner, calls = make_runner({"create": json.dumps({"id": "t_abc", "status": "ready"})})
    tid = board.create_card(board="council-demo", title="X", assignee="mia",
                            body="B", workspace="dir:/tmp/demo", runner=runner)
    assert tid == "t_abc"
    flat = " ".join(calls[0])
    assert "--board council-demo" in flat and "--assignee mia" in flat


def test_list_profiles_parses_names():
    runner, _ = make_runner({"assignees": json.dumps(
        [{"name": "default"}, {"name": "mia"}, {"name": "sophie"}])})
    assert board.list_profiles(runner=runner) == ["default", "mia", "sophie"]
