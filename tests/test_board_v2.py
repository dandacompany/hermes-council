import json
from council import board


def make_runner(mapping, default=""):
    calls = []

    def runner(args):
        calls.append(args)
        for key, out in mapping.items():
            if key in args:
                return out
        return default
    return runner, calls


def test_running_gateway_profiles_parses_names():
    text = ("✓ Gateway is supervised by launchd (PID 45339)\n"
            "  ✓ ethan            — PID 32652\n"
            "  ✓ mia              — PID 1562\n")
    runner, _ = make_runner({"status": text})
    assert board.running_gateway_profiles(runner=runner) == ["ethan", "mia"]


def test_running_gateway_empty_when_no_pids_and_no_supervisor():
    runner, _ = make_runner({"status": "no gateways running\n"})
    assert board.running_gateway_profiles(runner=runner) == []


def test_unblock_and_comment_target_board():
    runner, calls = make_runner({})
    board.unblock("council-x", "t_1", runner=runner)
    board.comment("council-x", "t_1", "hi", runner=runner)
    assert calls[0] == ["kanban", "--board", "council-x", "unblock", "t_1"]
    assert calls[1] == ["kanban", "--board", "council-x", "comment", "t_1", "hi"]


def test_profile_approval_mode_reads_yaml(tmp_path):
    p = tmp_path / "sophie"
    p.mkdir()
    (p / "config.yaml").write_text(
        "gateway:\n  x: 1\napprovals:\n  mode: manual\n  timeout: 60\nother: 2\n",
        encoding="utf-8")
    assert board.profile_approval_mode("sophie", config_root=tmp_path) == "manual"


def test_profile_approval_mode_unknown_when_missing(tmp_path):
    assert board.profile_approval_mode("ghost", config_root=tmp_path) == "unknown"


def test_json_obj_empty_raises():
    import pytest
    runner, _ = make_runner({"create": ""})
    with pytest.raises(board.BoardError):
        board.create_card(board="b", title="t", assignee="a", body="x",
                          workspace="dir:/tmp", runner=runner)


def test_nonzero_runner_raises_boarderror():
    import pytest
    def bad_runner(args):
        raise board.BoardError("boom")
    with pytest.raises(board.BoardError):
        board.dispatch("b", runner=bad_runner)


def test_remove_board_hard_flag():
    runner, calls = make_runner({})
    board.remove_board("demo", hard=True, runner=runner)
    assert calls[0] == ["kanban", "boards", "rm", "council-demo", "--hard", "--yes"]
    board.remove_board("demo", hard=False, runner=runner)
    assert calls[1] == ["kanban", "boards", "rm", "council-demo"]
