"""Integration tests.

CI-safe: exercises the whole tools pipeline (start → transcript → status →
collect) with board shelled-out calls mocked, so it runs without a live Hermes.

Opt-in live: set COUNCIL_LIVE=1 to also drive the real `hermes council` CLI.
"""
import json, os, subprocess, pytest
from council import tools, registry, board, runner


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia", "noah"])
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {})
    yield


def _finished_transcript():
    return ("## [sophie] — TURN 0 (moderator·킥오프)\n안건.\n\n"
            "## [mia] — TURN 1 (speaker)\n의견 A.\n\n"
            "## [sophie] — TURN 1 (moderator)\n판단.\n\n"
            "## [SUMMARY]\n- 핵심 결론.\n\n"
            "## [FINAL] 결론 보고서\n### 결정\n본문.\n\n"
            "## [DECISIONS]\n- 결정: X 채택\n- 액션: mia — 초안\n")


def test_full_pipeline_start_to_all_formats(monkeypatch):
    started = json.loads(tools.handle_start(
        {"topic": "통합 테스트 회의", "panel": ["mia"], "moderator": "sophie", "max_turns": 2}))
    slug = started["slug"]
    assert started["kickoff_id"] == "t_kick"

    # simulate the self-propagating workers having produced a finished transcript
    (registry.meeting_dir(slug) / "transcript.md").write_text(_finished_transcript(), encoding="utf-8")

    monkeypatch.setattr(board, "list_cards", lambda b, **k: [{"id": "t1", "status": "done"}])
    st = json.loads(tools.handle_status({"slug": slug}))
    assert st["final_reached"] is True and st["runaway"] is False

    out = json.loads(tools.handle_collect({"slug": slug, "format": "all"}))
    d = registry.meeting_dir(slug)
    for f in ("summary.md", "report.md", "transcript.export.md", "decisions.md",
              f"{slug}.json", f"{slug}.html"):
        assert (d / f).exists(), f"missing {f}"
    assert registry.load_meta(slug)["status"] == "collected"


def test_runner_drives_simulated_meeting_to_collect(monkeypatch):
    started = json.loads(tools.handle_start(
        {"topic": "러너 통합", "panel": ["mia"], "moderator": "sophie"}))
    slug = started["slug"]
    # first poll: not final; then a worker "finishes" the transcript; second poll: final
    calls = {"n": 0}

    def status_fn(s):
        calls["n"] += 1
        if calls["n"] == 2:
            (registry.meeting_dir(s) / "transcript.md").write_text(_finished_transcript(), encoding="utf-8")
        return {"final_reached": calls["n"] >= 2, "blocked": [], "runaway": False}

    result = runner.drive(
        slug, status_fn=status_fn, resume_fn=lambda s: None, stop_fn=lambda s: None,
        collect_fn=lambda s: json.loads(tools.handle_collect({"slug": s})),
        sleep_fn=lambda n: None, interval=1, max_ticks=5)
    assert result["outcome"] == "final"
    assert (registry.meeting_dir(slug) / "summary.md").exists()


@pytest.mark.skipif(not os.environ.get("COUNCIL_LIVE"),
                    reason="set COUNCIL_LIVE=1 to run against a real hermes install")
def test_live_dry_run_plan():
    profile = os.environ.get("COUNCIL_PROFILE", "default")
    proc = subprocess.run(
        ["hermes", "-p", profile, "council", "start", "--topic", "라이브 스모크",
         "--panel", "mia,noah", "--moderator", "sophie", "--dry-run"],
        capture_output=True, text=True)
    raw = proc.stdout
    data = json.loads(raw[raw.find("{"):])
    assert data.get("dry_run") is True
    assert data["board"].startswith("council-")
