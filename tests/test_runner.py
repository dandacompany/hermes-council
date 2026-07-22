from council import runner


def test_drive_collects_on_final():
    seq = [{"final_reached": False, "blocked": []},
           {"final_reached": True, "blocked": []}]
    calls = {"collect": 0, "resume": 0, "sleep": 0}
    out = runner.drive(
        "s",
        status_fn=lambda s: seq.pop(0),
        resume_fn=lambda s: calls.__setitem__("resume", calls["resume"] + 1),
        collect_fn=lambda s: (calls.__setitem__("collect", 1) or {"written": {"summary": "x"}}),
        sleep_fn=lambda n: calls.__setitem__("sleep", calls["sleep"] + 1),
        interval=1, max_ticks=5)
    assert out["outcome"] == "final" and out["written"] == {"summary": "x"}
    assert calls["collect"] == 1 and calls["resume"] == 0


def test_drive_auto_resumes_blocked():
    seq = [{"final_reached": False, "blocked": ["t_1"]},
           {"final_reached": True, "blocked": []}]
    resumed = []
    out = runner.drive(
        "s",
        status_fn=lambda s: seq.pop(0),
        resume_fn=lambda s: resumed.append(s),
        collect_fn=lambda s: {"written": {}},
        sleep_fn=lambda n: None,
        interval=1, max_ticks=5)
    assert out["outcome"] == "final"
    assert resumed == ["s"]


def test_drive_times_out():
    out = runner.drive(
        "s",
        status_fn=lambda s: {"final_reached": False, "blocked": []},
        resume_fn=lambda s: None,
        collect_fn=lambda s: {},
        sleep_fn=lambda n: None,
        interval=1, max_ticks=3)
    assert out["outcome"] == "timeout"


def test_drive_force_stops_on_runaway():
    seq = [{"final_reached": False, "runaway": True, "blocked": []},
           {"final_reached": True, "runaway": False, "blocked": []}]
    stopped = []
    out = runner.drive(
        "s", status_fn=lambda s: seq.pop(0),
        resume_fn=lambda s: None,
        stop_fn=lambda s: stopped.append(s),
        collect_fn=lambda s: {"written": {}},
        sleep_fn=lambda n: None, interval=1, max_ticks=5)
    assert out["outcome"] == "final" and stopped == ["s"]


def test_drive_pauses_on_pending_decision():
    out = runner.drive(
        "s", status_fn=lambda s: {"final_reached": False, "blocked": [],
                                  "pending_decision": {"question": "A?", "options": ["A", "B"]}},
        resume_fn=lambda s: None, stop_fn=lambda s: None,
        collect_fn=lambda s: {}, sleep_fn=lambda n: None, interval=1, max_ticks=5)
    assert out["outcome"] == "awaiting_decision" and out["pending"]["question"] == "A?"
