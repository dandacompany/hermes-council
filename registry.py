"""Filesystem registry under ~/.hermes/.council/. No kanban/subprocess deps."""
from __future__ import annotations
import json, re, hashlib, pathlib
try:  # package context (Hermes-loaded plugin)
    from ._paths import council_home
except ImportError:  # flat/standalone context (e.g. pytest at repo root)
    from _paths import council_home  # type: ignore

# Kanban board slugs must be lowercase ASCII [a-z0-9_-], 1-64 chars. The slug is
# reused as the board suffix (council-<slug>), so it must be ASCII-safe even when
# the topic is Korean — non-ASCII topics fall back to a deterministic short hash.
_ASCII_STRIP = re.compile(r"[^a-z0-9]+")


def _index_path() -> pathlib.Path:
    return council_home() / "index.json"


def make_slug(topic: str, taken: set[str], *, prefix: str = "") -> str:
    ascii_part = _ASCII_STRIP.sub("-", topic.strip().lower()).strip("-")
    if len(ascii_part) < 3:
        h = hashlib.sha1(topic.encode("utf-8")).hexdigest()[:6]
        ascii_part = f"{ascii_part}-{h}".strip("-") if ascii_part else f"meeting-{h}"
    if prefix:
        ascii_part = f"{prefix}-{ascii_part}"
    base = ascii_part[:48]                    # leave room for `council-` prefix + collision suffix (<=64)
    slug, n = base, 1
    while slug in taken:
        n += 1
        slug = f"{base}-{n}"
    return slug


def load_index() -> list[dict]:
    p = _index_path()
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _write_index(rows: list[dict]) -> None:
    p = _index_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def meeting_dir(slug: str) -> pathlib.Path:
    return council_home() / slug


def create_meeting(meta: dict) -> pathlib.Path:
    slug = meta["slug"]
    d = meeting_dir(slug)
    d.mkdir(parents=True, exist_ok=True)
    (d / "transcript.md").write_text("", encoding="utf-8")
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [r for r in load_index() if r.get("slug") != slug]
    row = {**meta, "dir": str(d)}
    rows.append(row)
    _write_index(rows)
    return d


def load_meta(slug: str) -> dict:
    return json.loads((meeting_dir(slug) / "meta.json").read_text(encoding="utf-8"))


def delete_meeting(slug: str) -> None:
    """Remove a meeting's registry dir and its index row (destructive)."""
    import shutil
    d = meeting_dir(slug)
    if d.exists():
        shutil.rmtree(d)
    _write_index([r for r in load_index() if r.get("slug") != slug])


def update_status(slug: str, status: str, **fields) -> dict:
    meta = load_meta(slug)
    meta.update(status=status, **fields)
    (meeting_dir(slug) / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = load_index()
    for r in rows:
        if r.get("slug") == slug:
            r.update(status=status, **fields)
    _write_index(rows)
    return meta
