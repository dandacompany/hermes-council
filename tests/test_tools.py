import json, pytest
from council import tools, registry, board


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    monkeypatch.setattr(board, "list_profiles", lambda **k: ["sophie", "mia", "noah"])
    monkeypatch.setattr(board, "create_board", lambda slug, **k: None)
    monkeypatch.setattr(board, "create_card", lambda **k: "t_kick")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: {"spawned": [{"task_id": "t_kick"}]})
    monkeypatch.setattr(board, "running_gateway_profiles", lambda **k: ["*"])
    monkeypatch.setattr(board, "profile_approval_mode", lambda p, **k: "yolo")
    monkeypatch.setattr(tools, "_now_iso", lambda: "2026-07-22T00:00:00+09:00")
    yield


def test_start_rejects_unknown_profile():
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["ghost"], "moderator": "sophie"}))
    assert "error" in out and "ghost" in out["error"]


def test_start_seeds_meeting_and_returns_ids():
    out = json.loads(tools.handle_start(
        {"topic": "강의 기획", "panel": ["mia", "noah"], "moderator": "sophie", "mode": "sequential"}))
    assert out["kickoff_id"] == "t_kick"
    assert out["board"] == f"council-{out['slug']}"
    assert registry.load_meta(out["slug"])["status"] == "running"


def test_start_dry_run_makes_no_dispatch(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(board, "dispatch", lambda b, **k: called.__setitem__("n", called["n"] + 1) or {})
    out = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie", "dry_run": True}))
    assert out["dry_run"] is True and called["n"] == 0
    # dry_run has no side effects: no registry entry, no meeting dir
    assert registry.load_index() == []
    assert not registry.meeting_dir(out["slug"]).exists()


def test_collect_writes_three_files():
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    (registry.meeting_dir(slug) / "transcript.md").write_text(
        "## [sophie] — TURN 0 (moderator·킥오프)\n안건.\n\n"
        "## [SUMMARY]\n- 결론.\n\n## [FINAL] 결론 보고서\n본문.\n", encoding="utf-8")
    out = json.loads(tools.handle_collect({"slug": slug}))
    d = registry.meeting_dir(slug)
    assert (d / "summary.md").exists() and (d / "report.md").exists() and (d / "transcript.export.md").exists()
    assert out["final_reached"] is True


def test_status_includes_lint_warnings(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    (registry.meeting_dir(slug) / "transcript.md").write_text(
        "## [mia] TURN 1 speaker\n형식오류.\n", encoding="utf-8")
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [])
    out = json.loads(tools.handle_status({"slug": slug}))
    assert any("형식 오류" in w for w in out["warnings"])


def test_resume_unblocks_and_dispatches(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [
        {"id": "t_a", "status": "blocked"}, {"id": "t_b", "status": "done"}])
    unblocked, commented, dispatched = [], [], []
    monkeypatch.setattr(board, "unblock", lambda b, tid, **k: unblocked.append(tid))
    monkeypatch.setattr(board, "comment", lambda b, tid, txt, **k: commented.append(tid))
    monkeypatch.setattr(board, "dispatch", lambda b, **k: dispatched.append(b) or {})
    out = json.loads(tools.handle_resume({"slug": slug}))
    assert out["count"] == 1 and out["resumed"] == ["t_a"]
    assert unblocked == ["t_a"] and commented == ["t_a"] and dispatched


def test_status_detects_final_and_updates(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    (registry.meeting_dir(slug) / "transcript.md").write_text(
        "## [sophie] — TURN 0 (moderator·킥오프)\n안.\n\n## [SUMMARY]\n- s\n\n## [FINAL] 결론 보고서\n본.\n",
        encoding="utf-8")
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [{"id": "t1", "status": "done"}])
    out = json.loads(tools.handle_status({"slug": slug}))
    assert out["final_reached"] is True and out["status"] == "final"
    assert registry.load_meta(slug)["status"] == "final"


def test_status_surfaces_blocked_hint(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [{"id": "tb", "status": "blocked"}])
    out = json.loads(tools.handle_status({"slug": slug}))
    assert out["blocked"] == ["tb"] and "resume" in out["hint"]


def test_stop_creates_finalize_card(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    made, dispatched = [], []
    monkeypatch.setattr(board, "create_card", lambda **k: made.append(k) or "t_fin")
    monkeypatch.setattr(board, "dispatch", lambda b, **k: dispatched.append(b) or {})
    out = json.loads(tools.handle_stop({"slug": slug, "reason": "시간 종료"}))
    assert out["finalize_card"] == "t_fin" and out["status"] == "stopped"
    assert made and made[0]["assignee"] == "sophie"
    assert registry.load_meta(slug)["status"] == "stopped"


def test_unknown_slug_errors():
    assert "error" in json.loads(tools.handle_status({"slug": "nope"}))
    assert "error" in json.loads(tools.handle_collect({"slug": "nope"}))
    assert "error" in json.loads(tools.handle_stop({"slug": "nope"}))
    assert "error" in json.loads(tools.handle_resume({"slug": "nope"}))


def test_start_saves_brief_and_roles(tmp_path):
    brief_file = tmp_path / "agenda.md"
    brief_file.write_text("## 배경\n중요한 맥락.\n", encoding="utf-8")
    out = json.loads(tools.handle_start({
        "topic": "T", "panel": ["mia"], "moderator": "sophie",
        "brief": str(brief_file), "roles": {"mia": "시장 관점"}}))
    d = registry.meeting_dir(out["slug"])
    assert (d / "brief.md").read_text(encoding="utf-8") == "## 배경\n중요한 맥락.\n"
    assert registry.load_meta(out["slug"])["roles"] == {"mia": "시장 관점"}
    assert registry.load_meta(out["slug"])["has_brief"] is True


def test_start_brief_inline_text():
    out = json.loads(tools.handle_start({
        "topic": "T", "panel": ["mia"], "moderator": "sophie", "brief": "인라인 안건 텍스트"}))
    d = registry.meeting_dir(out["slug"])
    assert "인라인 안건 텍스트" in (d / "brief.md").read_text(encoding="utf-8")


def test_start_stores_card_cap():
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia", "noah"], "moderator": "sophie", "max_turns": 5}))
    assert registry.load_meta(out["slug"])["card_cap"] == (2 + 2) * 5 + 4


def test_status_flags_runaway(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie", "max_turns": 2}))
    slug = start["slug"]
    cap = registry.load_meta(slug)["card_cap"]
    monkeypatch.setattr(board, "list_cards",
                        lambda b, **k: [{"id": f"t{i}", "status": "done"} for i in range(cap + 1)])
    out = json.loads(tools.handle_status({"slug": slug}))
    assert out["runaway"] is True and out["card_count"] == cap + 1
    assert any("폭주" in w for w in out["warnings"])


def test_say_appends_directive():
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    out = json.loads(tools.handle_say({"slug": slug, "note": "비용 관점도 다뤄줘"}))
    assert out["appended"] is True
    txt = (registry.meeting_dir(slug) / "transcript.md").read_text(encoding="utf-8")
    assert "## [사용자 지침]" in txt and "비용 관점도 다뤄줘" in txt


def test_archive_sets_status(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    removed = []
    monkeypatch.setattr(board, "remove_board", lambda s, **k: removed.append((s, k.get("hard"))))
    out = json.loads(tools.handle_archive({"slug": slug}))
    assert out["archived"] is True
    assert registry.load_meta(slug)["status"] == "archived"
    assert removed == [(slug, False)]


def test_rm_deletes(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    monkeypatch.setattr(board, "remove_board", lambda s, **k: None)
    out = json.loads(tools.handle_rm({"slug": slug}))
    assert out["removed"] is True
    assert not registry.meeting_dir(slug).exists()


def test_gc_removes_old_archived(monkeypatch):
    monkeypatch.setattr(board, "remove_board", lambda s, **k: None)
    old = json.loads(tools.handle_start({"topic": "old", "panel": ["mia"], "moderator": "sophie"}))["slug"]
    registry.update_status(old, "archived")
    # backdate created_at
    m = registry.load_meta(old); m["created_at"] = "2000-01-01T00:00:00+09:00"
    import json as _j, pathlib
    (registry.meeting_dir(old) / "meta.json").write_text(_j.dumps(m, ensure_ascii=False), encoding="utf-8")
    rows = registry.load_index()
    for r in rows:
        if r["slug"] == old:
            r["created_at"] = "2000-01-01T00:00:00+09:00"; r["status"] = "archived"
    (pathlib.Path(registry.council_home()) / "index.json").write_text(_j.dumps(rows, ensure_ascii=False), encoding="utf-8")
    out = json.loads(tools.handle_gc({"days": 30}))
    assert old in out["removed"]


def test_collect_json_and_html_formats():
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    (registry.meeting_dir(slug) / "transcript.md").write_text(
        "## [sophie] — TURN 0 (moderator·킥오프)\n안.\n\n## [mia] — TURN 1 (speaker)\n의견.\n\n"
        "## [SUMMARY]\n- s\n\n## [FINAL] 결론 보고서\n본문.\n\n## [DECISIONS]\n- 결정: X\n", encoding="utf-8")
    out = json.loads(tools.handle_collect({"slug": slug, "format": "all"}))
    d = registry.meeting_dir(slug)
    assert (d / f"{slug}.json").exists() and (d / f"{slug}.html").exists()
    import json as _j
    data = _j.loads((d / f"{slug}.json").read_text(encoding="utf-8"))
    assert data["final_reached"] is True and any(s["speaker"] == "mia" for s in data["sections"])
    assert out["written"]["html"].endswith(".html")


def test_start_hitl_flag_in_meta_and_body():
    out = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie", "hitl": True}))
    assert registry.load_meta(out["slug"])["hitl"] is True


def test_vote_then_status_pending_then_decide(monkeypatch):
    start = json.loads(tools.handle_start({"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    # open a vote gate
    v = json.loads(tools.handle_vote({"slug": slug, "question": "A냐 B냐?", "options": ["A", "B"]}))
    assert v["vote_opened"] is True
    # status shows pending decision
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [{"id": "tb", "status": "blocked"}])
    st = json.loads(tools.handle_status({"slug": slug}))
    assert st["pending_decision"]["question"].startswith("A냐 B냐") and st["pending_decision"]["options"] == ["A", "B"]
    assert "decide" in st["hint"]
    # human decides → appends + unblocks
    unblocked, dispatched = [], []
    monkeypatch.setattr(board, "unblock", lambda b, tid, **k: unblocked.append(tid))
    monkeypatch.setattr(board, "dispatch", lambda b, **k: dispatched.append(b) or {})
    d = json.loads(tools.handle_decide({"slug": slug, "choice": "A로 확정"}))
    assert d["decided"] == "A로 확정" and unblocked == ["tb"]
    txt = (registry.meeting_dir(slug) / "transcript.md").read_text(encoding="utf-8")
    assert "## [사용자 결정]" in txt and "A로 확정" in txt
    # gate now resolved
    st2 = json.loads(tools.handle_status({"slug": slug}))
    assert st2["pending_decision"] is None


def _capable(*names):
    """A send-directory stub: listed profiles have Slack, others have nothing."""
    def list_fn(profile, **kw):
        has = profile in names
        return {"platforms": {"slack": [{"name": "Dante"}] if has else []}}
    return list_fn


def test_start_without_relay_stores_no_relay_metadata():
    out = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    assert registry.load_meta(out["slug"])["relay"] is None


def test_start_with_relay_opens_a_thread_and_embeds_the_block(monkeypatch):
    bodies = {}
    monkeypatch.setattr(board, "send_targets", _capable("sophie", "noah"))
    monkeypatch.setattr(board, "send", lambda **kw: "1755.1")
    monkeypatch.setattr(board, "create_card",
                        lambda **kw: bodies.update(kw) or "t_kick")
    out = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia", "noah"], "moderator": "sophie",
         "relay": "slack:#council"}))
    meta = registry.load_meta(out["slug"])
    assert meta["relay"]["thread"] == "1755.1"
    assert meta["relay"]["target"] == "slack:#council:1755.1"
    assert meta["relay"]["proxy_for"] == ["mia"]          # noah can send for itself
    assert "■ 채널 중계" in bodies["body"]
    assert "slack:#council:1755.1" in bodies["body"]


def test_start_degrades_to_flat_when_opening_the_thread_fails(monkeypatch):
    bodies = {}
    monkeypatch.setattr(board, "send_targets", _capable("sophie"))

    def boom(**kw):
        raise board.BoardError("channel_not_found")

    monkeypatch.setattr(board, "send", boom)
    monkeypatch.setattr(board, "create_card",
                        lambda **kw: bodies.update(kw) or "t_kick")
    out = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie",
         "relay": "slack:#council"}))
    assert "error" not in out                               # the meeting still starts
    meta = registry.load_meta(out["slug"])
    assert meta["relay"]["thread"] == ""                    # flat, no thread
    assert "slack:#council" in bodies["body"]


def test_start_warns_when_relay_is_on_but_nobody_can_send(monkeypatch):
    monkeypatch.setattr(board, "send_targets", _capable())   # nobody
    out = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie",
         "relay": "slack:#council"}))
    assert any("발신 가능한 프로필" in w for w in out["warnings"])


def test_start_skips_thread_for_platforms_that_cannot_open_one(monkeypatch):
    sent = {"n": 0}
    monkeypatch.setattr(board, "send_targets", _capable("sophie"))
    monkeypatch.setattr(board, "send",
                        lambda **kw: sent.__setitem__("n", sent["n"] + 1) or "x")
    out = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie",
         "relay": "telegram:-100123"}))
    assert sent["n"] == 0                                   # no header message
    assert registry.load_meta(out["slug"])["relay"]["thread"] == ""


def test_start_dry_run_never_sends_even_with_relay_on(monkeypatch):
    sent = {"n": 0}
    monkeypatch.setattr(board, "send_targets", _capable("sophie"))
    monkeypatch.setattr(board, "send",
                        lambda **kw: sent.__setitem__("n", sent["n"] + 1) or "1755.1")
    out = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie",
         "relay": "slack:#council", "dry_run": True}))
    assert sent["n"] == 0                                   # preview never sends a live message
    assert out["dry_run"] is True
    # dry_run has no side effects at all: no registry entry to carry relay metadata
    assert registry.load_index() == []


def test_decide_posts_the_human_choice_to_the_relay_thread(monkeypatch):
    monkeypatch.setattr(board, "send_targets", _capable("sophie"))
    monkeypatch.setattr(board, "send", lambda **kw: "1755.1")
    start = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie",
         "relay": "slack:#council"}))
    slug = start["slug"]
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [])
    posted = {}
    monkeypatch.setattr(board, "send", lambda **kw: posted.update(kw) or "1755.2")
    out = json.loads(tools.handle_decide({"slug": slug, "choice": "A안으로 간다"}))
    assert out["relayed"] is True
    assert posted["target"] == "slack:#council:1755.1"
    assert "A안으로 간다" in posted["message"]
    assert posted["profile"] == "sophie"


def test_decide_without_relay_reports_not_relayed(monkeypatch):
    start = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [])
    out = json.loads(tools.handle_decide({"slug": start["slug"], "choice": "A"}))
    assert out["relayed"] is False


def test_decide_survives_a_relay_failure(monkeypatch):
    monkeypatch.setattr(board, "send_targets", _capable("sophie"))
    monkeypatch.setattr(board, "send", lambda **kw: "1755.1")
    start = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie",
         "relay": "slack:#council"}))
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [])

    def boom(**kw):
        raise board.BoardError("network")

    monkeypatch.setattr(board, "send", boom)
    out = json.loads(tools.handle_decide({"slug": start["slug"], "choice": "A"}))
    assert out["decided"] == "A" and out["relayed"] is False


def test_decide_survives_a_malformed_relay_meta(monkeypatch):
    """meta['relay'] should only ever be None or a dict, but if something external
    corrupts it (e.g. a manual edit leaves a bare string), handle_decide must not
    let that turn a recorded decision into an error response."""
    start = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie"}))
    slug = start["slug"]
    meta_path = registry.meeting_dir(slug) / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["relay"] = "slack:#council"          # malformed: string, not dict/None
    meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(board, "list_cards", lambda b, **k: [])
    out = json.loads(tools.handle_decide({"slug": slug, "choice": "A"}))
    assert "error" not in out
    assert out["decided"] == "A" and out["relayed"] is False


def test_status_reports_relay_state(monkeypatch):
    monkeypatch.setattr(board, "send_targets", _capable("sophie"))
    monkeypatch.setattr(board, "send", lambda **kw: "1755.1")
    start = json.loads(tools.handle_start(
        {"topic": "T", "panel": ["mia"], "moderator": "sophie",
         "relay": "slack:#council"}))
    monkeypatch.setattr(board, "list_cards", lambda b, **k: [])
    st = json.loads(tools.handle_status({"slug": start["slug"]}))
    assert st["relay"]["target"] == "slack:#council:1755.1"
    assert st["relay"]["proxy_for"] == ["mia"]
