import json, pathlib, pytest
from council import registry


@pytest.fixture(autouse=True)
def _home(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    yield


def test_make_slug_ascii_only_and_collision():
    # ASCII kept, Hangul dropped (board slugs must be ASCII).
    assert registry.make_slug("ChatGPT Work 강의기획!", set()) == "chatgpt-work"
    assert registry.make_slug("Topic", {"topic"}) == "topic-2"


def test_make_slug_hangul_only_falls_back_to_hash():
    slug = registry.make_slug("단테랩스 유튜브 콘텐츠", set())
    assert slug.startswith("meeting-")
    assert __import__("re").fullmatch(r"[a-z0-9_-]{1,64}", slug)   # valid board slug
    # deterministic
    assert slug == registry.make_slug("단테랩스 유튜브 콘텐츠", set())


def test_create_meeting_writes_files_and_index():
    meta = {"slug": "demo", "topic": "T", "mode": "sequential",
            "moderator": "sophie", "panel": ["mia"], "max_turns": 3,
            "allow_early_stop": True, "board": "council-demo",
            "status": "seeded", "created_at": "2026-07-22T00:00:00+09:00"}
    d = registry.create_meeting(meta)
    assert (d / "meta.json").exists()
    assert (d / "transcript.md").read_text() == ""
    idx = registry.load_index()
    assert idx[0]["slug"] == "demo" and idx[0]["status"] == "seeded"


def test_update_status_patches_both():
    registry.create_meeting({"slug": "demo", "topic": "T", "mode": "sequential",
        "moderator": "s", "panel": ["a"], "max_turns": 3, "allow_early_stop": True,
        "board": "council-demo", "status": "seeded", "created_at": "x"})
    registry.update_status("demo", "final", final_at="2026")
    assert registry.load_meta("demo")["status"] == "final"
    assert registry.load_index()[0]["final_at"] == "2026"


def test_make_slug_with_date_prefix():
    assert registry.make_slug("Q3 Roadmap", set(), prefix="20260723") == "20260723-q3-roadmap"
    s = registry.make_slug("한글 주제", set(), prefix="20260723")
    assert s.startswith("20260723-meeting-")


def test_delete_meeting_removes_dir_and_index():
    registry.create_meeting({"slug": "gone", "topic": "T", "mode": "sequential",
        "moderator": "s", "panel": ["a"], "max_turns": 2, "allow_early_stop": True,
        "board": "council-gone", "status": "seeded", "created_at": "x"})
    assert registry.meeting_dir("gone").exists()
    registry.delete_meeting("gone")
    assert not registry.meeting_dir("gone").exists()
    assert all(r["slug"] != "gone" for r in registry.load_index())
