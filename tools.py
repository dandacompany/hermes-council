"""Handlers that assemble registry + protocols + render + board."""
from __future__ import annotations
import json, datetime
try:  # package context (Hermes-loaded plugin)
    from . import registry, protocols, render, board, preflight, lint
except ImportError:  # flat/standalone context (e.g. pytest at repo root)
    import registry, protocols, render, board, preflight, lint  # type: ignore


def _dump(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _now_iso() -> str:
    return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()


def handle_start(args: dict, **kwargs) -> str:
    try:
        topic = str(args.get("topic") or "").strip()
        panel = list(args.get("panel") or [])
        moderator = str(args.get("moderator") or "").strip()
        if not topic or not panel or not moderator:
            return _dump({"error": "topic, panel, moderator are required"})
        mode = args.get("mode") or "sequential"
        if mode not in ("sequential", "parallel"):
            return _dump({"error": f"invalid mode: {mode}"})
        max_turns = int(args.get("max_turns") or 5)
        allow_early_stop = bool(args.get("allow_early_stop", True))
        dry_run = bool(args.get("dry_run", False))
        roles = dict(args.get("roles") or {})
        brief_raw = args.get("brief")
        hitl = bool(args.get("hitl", False))

        known = set(board.list_profiles())
        missing = [p for p in [moderator, *panel] if p not in known]
        if missing:
            return _dump({"error": f"unknown profile(s): {', '.join(missing)}"})

        warnings = preflight.warnings_for(
            moderator, panel,
            approval_mode_fn=board.profile_approval_mode,
            running_profiles=board.running_gateway_profiles())

        taken = {r["slug"] for r in registry.load_index()}
        # Date-prefixed slug for readable, sortable meeting ids (unless explicit slug given).
        prefix = "" if args.get("slug") else _now_iso()[:10].replace("-", "")
        slug = registry.make_slug(args.get("slug") or topic, taken, prefix=prefix)
        board_slug = f"council-{slug}"
        # A brief may be inline text or a path to a file; resolve to text.
        brief_text = ""
        if brief_raw:
            import pathlib
            bp = pathlib.Path(str(brief_raw)).expanduser()
            brief_text = bp.read_text(encoding="utf-8") if bp.is_file() else str(brief_raw)
        brief_note = ("참고자료: 작업 디렉토리의 brief.md를 발언/판단 전에 반드시 함께 읽어라."
                      if brief_text else "")

        meta = {"slug": slug, "topic": topic, "mode": mode, "moderator": moderator,
                "panel": panel, "max_turns": max_turns, "allow_early_stop": allow_early_stop,
                "board": board_slug, "status": "seeded", "created_at": _now_iso(),
                "final_at": None, "roles": roles, "has_brief": bool(brief_text),
                "card_cap": preflight.card_cap(len(panel), max_turns), "hitl": hitl}
        transcript_path = str(registry.meeting_dir(slug) / "transcript.md")
        body_text = protocols.build_kickoff(mode=mode, topic=topic, slug=slug, moderator=moderator,
                                            panel=panel, max_turns=max_turns,
                                            allow_early_stop=allow_early_stop,
                                            transcript_path=transcript_path,
                                            roles=roles, brief_note=brief_note, hitl=hitl)

        if dry_run:
            # No side effects: don't create the registry entry or the board.
            return _dump({"dry_run": True, "slug": slug, "board": board_slug,
                          "kickoff_assignee": moderator, "warnings": warnings,
                          "roles": roles, "has_brief": bool(brief_text),
                          "kickoff_body_preview": body_text[:600]})

        d = registry.create_meeting(meta)
        if brief_text:
            (d / "brief.md").write_text(brief_text, encoding="utf-8")
        board.create_board(slug)
        kickoff_id = board.create_card(board=board_slug, title=f"[council] {topic} — 킥오프",
                                       assignee=moderator, body=body_text,
                                       workspace=f"dir:{d}")
        board.dispatch(board_slug)
        registry.update_status(slug, "running", kickoff_id=kickoff_id)
        return _dump({"slug": slug, "board": board_slug, "dir": str(d),
                      "kickoff_id": kickoff_id, "mode": mode, "warnings": warnings,
                      "next": "council_status로 진행을 관찰하고, FINAL 후 council_collect로 산출물 수집."})
    except Exception as exc:
        return _dump({"error": f"council_start failed: {type(exc).__name__}: {exc}"})


def _section_count(text: str) -> int:
    return sum(1 for ln in text.splitlines() if ln.startswith("## ["))


def handle_status(args: dict, **kwargs) -> str:
    try:
        slug = str(args.get("slug") or "").strip()
        if not slug:
            return _dump({"error": "slug is required"})
        meta = registry.load_meta(slug)
        transcript = (registry.meeting_dir(slug) / "transcript.md").read_text(encoding="utf-8")
        final = "## [FINAL]" in transcript
        cards = board.list_cards(meta["board"])
        blocked = [c.get("id") for c in cards if c.get("status") == "blocked"]
        if final and meta.get("status") not in ("final", "collected", "stopped"):
            registry.update_status(slug, "final", final_at=_now_iso())
        cap = int(meta.get("card_cap") or 0)
        runaway = preflight.is_runaway(len(cards), cap, final)
        warnings = lint.lint_transcript(transcript)
        if runaway:
            warnings.append(f"경고: 카드 수 {len(cards)} > 상한 {cap} — 폭주 의심. `council stop {slug}`로 강제 종합 권장.")
        pending = render.parse_pending_decision(transcript)
        hint = ""
        if pending:
            hint = f"사람 결정 대기 — `council decide {slug} \"<선택>\"`로 응답"
        elif blocked:
            hint = f"blocked 카드는 `council resume {slug}`로 재개"
        return _dump({"slug": slug, "status": "final" if final else meta.get("status"),
                      "sections": _section_count(transcript), "final_reached": final,
                      "cards": [{"id": c.get("id"), "assignee": c.get("assignee"),
                                 "status": c.get("status"), "title": c.get("title")} for c in cards],
                      "blocked": blocked, "card_count": len(cards), "card_cap": cap,
                      "runaway": runaway, "pending_decision": pending, "warnings": warnings,
                      "hint": hint})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_status failed: {type(exc).__name__}: {exc}"})


def handle_collect(args: dict, **kwargs) -> str:
    try:
        slug = str(args.get("slug") or "").strip()
        if not slug:
            return _dump({"error": "slug is required"})
        meta = registry.load_meta(slug)
        d = registry.meeting_dir(slug)
        transcript = (d / "transcript.md").read_text(encoding="utf-8")
        parts = render.split(transcript, topic=meta["topic"], slug=slug, mode=meta["mode"],
                             moderator=meta["moderator"], panel=meta["panel"])
        (d / "summary.md").write_text(parts["summary"], encoding="utf-8")
        (d / "report.md").write_text(parts["report"], encoding="utf-8")
        (d / "transcript.export.md").write_text(parts["transcript_export"], encoding="utf-8")
        written = {"summary": str(d / "summary.md"), "report": str(d / "report.md"),
                   "transcript": str(d / "transcript.export.md")}
        if parts.get("decisions"):
            (d / "decisions.md").write_text(parts["decisions"], encoding="utf-8")
            written["decisions"] = str(d / "decisions.md")

        fmt = str(args.get("format") or "md").lower()
        if fmt in ("json", "all"):
            data = render.to_json(transcript, topic=meta["topic"], slug=slug, mode=meta["mode"],
                                  moderator=meta["moderator"], panel=meta["panel"])
            (d / f"{slug}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            written["json"] = str(d / f"{slug}.json")
        if fmt in ("html", "all"):
            (d / f"{slug}.html").write_text(render.to_html(parts, topic=meta["topic"]), encoding="utf-8")
            written["html"] = str(d / f"{slug}.html")

        out_dir = args.get("out_dir")
        if out_dir:
            import pathlib, shutil
            od = pathlib.Path(out_dir).expanduser()
            od.mkdir(parents=True, exist_ok=True)
            for kind, path in list(written.items()):
                ext = pathlib.Path(path).suffix or ".md"
                dest = od / f"{slug}-{kind}{ext}"
                shutil.copyfile(path, dest)
                written[f"{kind}_copy"] = str(dest)
        registry.update_status(slug, "collected")
        return _dump({"slug": slug, "final_reached": parts["final_reached"], "written": written})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_collect failed: {type(exc).__name__}: {exc}"})


def handle_stop(args: dict, **kwargs) -> str:
    try:
        slug = str(args.get("slug") or "").strip()
        if not slug:
            return _dump({"error": "slug is required"})
        meta = registry.load_meta(slug)
        d = registry.meeting_dir(slug)
        body_text = protocols.build_finalize(topic=meta["topic"], slug=slug, moderator=meta["moderator"],
                                             transcript_path=str(d / "transcript.md"),
                                             reason=str(args.get("reason") or ""))
        cid = board.create_card(board=meta["board"], title=f"[council] {meta['topic']} — 강제 종합",
                                assignee=meta["moderator"], body=body_text, workspace=f"dir:{d}")
        board.dispatch(meta["board"])
        registry.update_status(slug, "stopped")
        return _dump({"slug": slug, "finalize_card": cid, "status": "stopped"})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_stop failed: {type(exc).__name__}: {exc}"})


_RESUME_GUIDE = ("재개 안내: 회의록(transcript.md) append는 반드시 파일 편집 도구로 하라. "
                 "python3·bash·shell로 파일을 쓰면 백그라운드 승인 타임아웃으로 다시 차단된다.")


def handle_resume(args: dict, **kwargs) -> str:
    try:
        slug = str(args.get("slug") or "").strip()
        if not slug:
            return _dump({"error": "slug is required"})
        meta = registry.load_meta(slug)
        cards = board.list_cards(meta["board"])
        blocked = [c.get("id") for c in cards if c.get("status") == "blocked"]
        for cid in blocked:
            board.comment(meta["board"], cid, _RESUME_GUIDE)
            board.unblock(meta["board"], cid)
        if blocked:
            board.dispatch(meta["board"])
            registry.update_status(slug, "running")
        return _dump({"slug": slug, "resumed": blocked, "count": len(blocked)})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_resume failed: {type(exc).__name__}: {exc}"})


def handle_archive(args: dict, **kwargs) -> str:
    """Archive a meeting: mark status + archive its board. Reversible-ish."""
    try:
        slug = str(args.get("slug") or "").strip()
        if not slug:
            return _dump({"error": "slug is required"})
        meta = registry.load_meta(slug)
        board.remove_board(slug, hard=False)
        registry.update_status(slug, "archived")
        return _dump({"slug": slug, "archived": True, "board": meta["board"]})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_archive failed: {type(exc).__name__}: {exc}"})


def handle_rm(args: dict, **kwargs) -> str:
    """Delete a meeting's registry dir + board (destructive). CLI-guarded by --yes."""
    try:
        slug = str(args.get("slug") or "").strip()
        if not slug:
            return _dump({"error": "slug is required"})
        registry.load_meta(slug)                       # existence check
        board.remove_board(slug, hard=True)
        registry.delete_meeting(slug)
        return _dump({"slug": slug, "removed": True})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_rm failed: {type(exc).__name__}: {exc}"})


def handle_gc(args: dict, **kwargs) -> str:
    """Remove archived meetings older than `days` (default 30)."""
    try:
        days = int(args.get("days") or 30)
        cutoff = (datetime.datetime.now().astimezone() - datetime.timedelta(days=days))
        removed = []
        for r in list(registry.load_index()):
            if r.get("status") != "archived":
                continue
            created = r.get("created_at") or ""
            try:
                when = datetime.datetime.fromisoformat(created)
            except ValueError:
                continue
            if when < cutoff:
                json.loads(handle_rm({"slug": r["slug"]}))
                removed.append(r["slug"])
        return _dump({"removed": removed, "count": len(removed), "days": days})
    except Exception as exc:
        return _dump({"error": f"council_gc failed: {type(exc).__name__}: {exc}"})


def handle_say(args: dict, **kwargs) -> str:
    """Inject a moderator directive mid-meeting by appending to the transcript.

    No card/dispatch — the next moderator card reads it. Non-destructive.
    """
    try:
        slug = str(args.get("slug") or "").strip()
        note = str(args.get("note") or "").strip()
        if not slug or not note:
            return _dump({"error": "slug and note are required"})
        registry.load_meta(slug)                       # existence check
        tp = registry.meeting_dir(slug) / "transcript.md"
        with tp.open("a", encoding="utf-8") as f:
            f.write(f"\n\n## [사용자 지침] {_now_iso()}\n{note}\n")
        return _dump({"slug": slug, "appended": True,
                      "note_hint": "다음 사회자 판단 카드가 이 지침을 읽고 반영합니다(회의는 계속)."})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_say failed: {type(exc).__name__}: {exc}"})


def handle_decide(args: dict, **kwargs) -> str:
    """Resolve an open HITL decision gate: record the human's choice + resume."""
    try:
        slug = str(args.get("slug") or "").strip()
        choice = str(args.get("choice") or "").strip()
        if not slug or not choice:
            return _dump({"error": "slug and choice are required"})
        meta = registry.load_meta(slug)
        tp = registry.meeting_dir(slug) / "transcript.md"
        with tp.open("a", encoding="utf-8") as f:
            f.write(f"\n\n## [사용자 결정] {_now_iso()}\n{choice}\n")
        resumed = []
        for c in board.list_cards(meta["board"]):
            if c.get("status") == "blocked":
                board.unblock(meta["board"], c.get("id"))
                resumed.append(c.get("id"))
        if resumed:
            board.dispatch(meta["board"])
        registry.update_status(slug, "running")
        return _dump({"slug": slug, "decided": choice, "resumed": resumed})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_decide failed: {type(exc).__name__}: {exc}"})


def handle_vote(args: dict, **kwargs) -> str:
    """Open a human vote gate: append a '결정 요청' with options to the transcript."""
    try:
        slug = str(args.get("slug") or "").strip()
        question = str(args.get("question") or "").strip()
        options = list(args.get("options") or [])
        if not slug or not question:
            return _dump({"error": "slug and question are required"})
        registry.load_meta(slug)
        tp = registry.meeting_dir(slug) / "transcript.md"
        opt_line = f"선택지: {' / '.join(options)}\n" if options else ""
        with tp.open("a", encoding="utf-8") as f:
            f.write(f"\n\n## [결정 요청] {_now_iso()}\n질문: {question}\n{opt_line}")
        return _dump({"slug": slug, "vote_opened": True, "question": question, "options": options,
                      "hint": f"`council decide {slug} \"<선택>\"`로 응답"})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_vote failed: {type(exc).__name__}: {exc}"})


def handle_doctor(args: dict, **kwargs) -> str:
    import pathlib
    from ._paths import council_home

    def _home_writable():
        h = council_home()
        h.mkdir(parents=True, exist_ok=True)
        probe = h / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True

    def _enabled():
        try:
            from hermes_cli.config import load_config
            enabled = (load_config().get("plugins", {}) or {}).get("enabled", []) or []
            return "council" in enabled
        except Exception:
            return False

    checks = preflight.doctor_checks(
        enabled_fn=_enabled,
        gateway_fn=lambda: bool(board.running_gateway_profiles()),
        assignees_fn=lambda: bool(board.list_profiles()),
        home_writable_fn=_home_writable)
    return _dump({"checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
                  "all_ok": all(ok for _, ok, _ in checks)})


def handle_council_command(raw_args: str = "", **kwargs) -> str:
    """`/council` — list meetings from the registry, or show one when a slug is given."""
    try:
        arg = raw_args.strip()
        if arg:
            return handle_status({"slug": arg})
        rows = registry.load_index()
        if not rows:
            return "등록된 council 회의가 없습니다. council_start로 시작하세요."
        lines = ["council 회의 목록:"]
        for r in rows:
            when = (r.get("created_at") or "")[:10]
            lines.append(f"- {r['slug']} · {r.get('mode')} · {r.get('status')} · {when} · {r.get('topic','')[:40]}")
        return "\n".join(lines)
    except Exception as exc:
        return f"council 목록 실패: {type(exc).__name__}: {exc}"
