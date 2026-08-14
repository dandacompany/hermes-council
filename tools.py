"""Handlers that assemble registry + protocols + render + board."""
from __future__ import annotations
import json, datetime
try:  # package context (Hermes-loaded plugin)
    from . import registry, protocols, render, board, preflight, lint, relay, souls
except ImportError:  # flat/standalone context (e.g. pytest at repo root)
    import registry, protocols, render, board, preflight, lint, relay, souls  # type: ignore


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
        # Explicit roles win; the rest come from each profile's SOUL.md so that
        # "different profiles, different angles" is the default, not a setting.
        roles = souls.roles_for(panel, dict(args.get("roles") or {}))
        brief_raw = args.get("brief")
        hitl = bool(args.get("hitl", False))
        # Relay is on by default. Having to ask for it made it fail silently: a
        # caller who forgot got a finished meeting and an empty channel, with no
        # warning anywhere. The person opening a meeting knows where it will go,
        # so NOT relaying is what you state — `relay: false` / `--no-relay`, or
        # `council: {relay: false}` in the moderator's profile.
        # `relay` names a destination; `relay_off` is the only thing that disables.
        # They are separate because a model expressing "the request said nothing
        # about this" reached for `relay: false`, and a live meeting ran with no
        # relay as a result. Omitting both now cannot disable anything.
        relay_arg = args.get("relay")
        relay_off = bool(args.get("relay_off", False)) or relay_arg is False \
            or (isinstance(relay_arg, str) and relay_arg.strip().lower() in ("false", "off", "no"))
        relay_spec = "" if relay_off else str(relay_arg if isinstance(relay_arg, str) else "").strip()
        relay_off_reason = "off_requested" if relay_off else None
        relay_thread = bool(args.get("relay_thread", True))

        known = set(board.list_profiles())
        missing = [p for p in [moderator, *panel] if p not in known]
        if missing:
            return _dump({"error": f"unknown profile(s): {', '.join(missing)}"})

        warnings = preflight.warnings_for(
            moderator, panel,
            approval_mode_fn=board.profile_approval_mode,
            running_profiles=board.running_gateway_profiles())

        # --- relay: decide once, then let the workers carry it card to card ---
        relay_meta, relay_block = None, ""
        if not relay_off and relay.opted_out(moderator):
            relay_off_reason = "profile_opted_out"
        elif not relay_off and not relay_spec:
            # Prefer the conversation this request arrived on — someone asking for
            # a meeting in a thread means "show it to me here", and making them
            # name a channel pushes our plumbing into their prompt. Only use it if
            # the moderator can actually send on that platform.
            here = relay.current_conversation()
            if here and relay.parse_target(here)["platform"] in (
                    (board.send_targets(moderator) or {}).get("platforms") or {}):
                relay_spec = here
            else:
                # No conversation (CLI, cron) — fall back to wherever the moderator
                # can speak. Empty means no messenger at all, i.e. no relay.
                relay_spec = relay.auto_platform(moderator, list_fn=board.send_targets)
        if relay_spec:
            target = relay.parse_target(relay_spec)
            capable = relay.relay_capable([moderator, *panel], target["platform"],
                                          list_fn=board.send_targets)
            moderator_capable = moderator in capable
            capable_ordered = [p for p in [moderator, *panel] if p in capable]
            sender = capable_ordered[0] if capable_ordered else None
            if not capable:
                relay_off_reason = "no_capable_profile"
                warnings.append(
                    "경고: 중계를 켰으나 발신 가능한 프로필이 없습니다 — 회의는 정상 진행되고 "
                    "채널 전송만 생략됩니다. (`hermes -p <프로필> send --list`로 확인)")
            elif not moderator_capable:
                incapable_panel = [p for p in panel if p not in capable]
                if incapable_panel:
                    warnings.append(
                        f"안내: 사회자({moderator})에게 메신저 자격이 없어, 자격 없는 참가자"
                        f"({', '.join(incapable_panel)})의 발언은 council이 {sender} 자격으로 "
                        "대리 전송합니다. 이 대리 전송은 `council run`이 붙어 있는 동안에만 이뤄집니다.")
                else:
                    warnings.append(
                        f"안내: 사회자({moderator})에게 메신저 자격이 없어, 사회자의 판단은 council이 "
                        "대리 전송합니다. 이 대리 전송은 `council run`이 붙어 있는 동안에만 이뤄집니다.")
            # The header message anchors the thread, so it must go out as whoever
            # council itself sends as — the first capable profile, which is the
            # moderator whenever the moderator can send. Gating this on the
            # moderator alone left meetings with an incapable moderator threadless,
            # scattering every relayed speech as its own top-level message.
            # It also probes the target. A bot that is not in the channel fails
            # every later post too, so failing here means the whole relay is dead —
            # say it once now instead of silently losing every speech.
            if not dry_run and sender:
                try:
                    mid = board.send(profile=sender,
                                     target=relay.format_target(target),
                                     message=f"▶ 회의 시작: {topic}")
                    if relay_thread and relay.can_open_thread(target):
                        target["thread"] = mid
                except Exception:
                    warnings.append(
                        f"경고: 중계 대상({relay.format_target(target)})으로 보낼 수 없어 중계를 끕니다 — "
                        "봇이 그 채널에 초대되어 있는지 확인하세요. 회의는 정상 진행됩니다.")
                    relay_spec = ""         # fall through to "no relay" below
                    relay_off_reason = "target_unreachable"
            # Worker-side proxying needs a moderator who can send — its card is the
            # one that runs between every pair of turns. When it can't, the poller
            # takes the proxy work instead (council_relay_flush), which is why the
            # two lists are mutually exclusive by construction.
            proxy_for = [p for p in panel if p not in capable] if moderator_capable else []
            poller_proxy_for = ([] if moderator_capable
                                else [p for p in [moderator, *panel] if p not in capable])
            if relay_spec and sender:
                warnings.append(
                    f"안내: 발언을 {relay.format_target(target)}(으)로 중계합니다 — "
                    "회의 내용이 그 채널에 그대로 올라갑니다. 끄려면 `--no-relay`.")
                relay_meta = {"target": relay.format_target(target),
                              "thread": target["thread"], "proxy_for": proxy_for,
                              "poller_proxy_for": poller_proxy_for,
                              "sender": sender}
                relay_block = relay.build_relay_block(
                    target=target, topic=topic, capable=capable_ordered, proxy_for=proxy_for)

        taken = {r["slug"] for r in registry.load_index()}
        # Date-prefixed slug for readable, sortable meeting ids (unless explicit slug given).
        prefix = "" if args.get("slug") else _now_iso()[:10].replace("-", "")
        slug = registry.make_slug(args.get("slug") or topic, taken, prefix=prefix)
        board_slug = f"council-{slug}"
        # A brief may be inline text or a path to a file; resolve to text.
        brief_text = ""
        if brief_raw:
            import os, pathlib
            raw = str(brief_raw)
            bp = pathlib.Path(raw).expanduser()
            if bp.is_file():
                brief_text = bp.read_text(encoding="utf-8")
            elif _looks_like_a_path(raw):
                # A path that does not resolve used to be kept as inline text, so
                # the "brief" the panel read was the path string and has_brief said
                # true. Relative paths are the usual victim: over a messenger there
                # is no working directory to resolve them against.
                return _dump({"error": f"brief file not found: {raw} "
                                       f"(resolved against {os.getcwd()}) — "
                                       "절대경로를 주거나, 브리프 본문을 그대로 넣으세요."})
            else:
                brief_text = raw
        brief_note = ("참고자료: 작업 디렉토리의 brief.md를 발언/판단 전에 반드시 함께 읽어라."
                      if brief_text else "")

        meta = {"slug": slug, "topic": topic, "mode": mode, "moderator": moderator,
                "panel": panel, "max_turns": max_turns, "allow_early_stop": allow_early_stop,
                "board": board_slug, "status": "seeded", "created_at": _now_iso(),
                "final_at": None, "roles": roles, "has_brief": bool(brief_text),
                "card_cap": preflight.card_cap(len(panel), max_turns), "hitl": hitl,
                "relay": relay_meta,
                # Why there is no relay, so a later "why is the channel empty?"
                # is answered by the meeting itself instead of a session DB dig.
                "relay_off_reason": None if relay_meta else (relay_off_reason or "no_capable_profile")}
        transcript_path = str(registry.meeting_dir(slug) / "transcript.md")
        body_text = protocols.build_kickoff(mode=mode, topic=topic, slug=slug, moderator=moderator,
                                            panel=panel, max_turns=max_turns,
                                            allow_early_stop=allow_early_stop,
                                            transcript_path=transcript_path,
                                            roles=roles, brief_note=brief_note, hitl=hitl,
                                            relay_block=relay_block)

        if dry_run:
            # No side effects: don't create the registry entry or the board.
            # Echo the settings a person checks on screen. The turn cap and mode
            # live past the 600-char preview cut, so without these fields a dry
            # run cannot answer "did it understand three turns?" — which is most
            # of what a dry run is for.
            return _dump({"dry_run": True, "slug": slug, "board": board_slug,
                          "kickoff_assignee": moderator, "warnings": warnings,
                          "moderator": moderator, "panel": panel, "mode": mode,
                          "max_turns": max_turns, "allow_early_stop": allow_early_stop,
                          "hitl": hitl,
                          "roles": roles, "has_brief": bool(brief_text),
                          "kickoff_body_preview": body_text[:600],
                          "relay_block": relay_block})

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
                      "hint": hint, "relay": meta.get("relay")})
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
        meta = registry.load_meta(slug)                # existence check
        # Block live cards first. A worker that is already running keeps calling
        # kanban, and those calls recreate the board directory we are about to
        # delete — the deletion succeeds and the board reappears, empty. Blocking
        # stops the dispatcher from starting any more; a worker mid-flight can
        # still resurrect it, which is why `council gc` also sweeps.
        try:
            for c in board.list_cards(meta["board"]):
                if c.get("status") in ("done", "blocked"):
                    continue
                try:
                    board.block(meta["board"], c.get("id"), reason="회의 삭제")
                except Exception:
                    continue
        except Exception:
            pass                                       # best-effort; deletion still proceeds
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
        # Sweep council boards with no meeting behind them. A worker still in
        # flight when its meeting was deleted recreates the board directory it
        # was deleted from; without this those empty boards pile up in the list.
        swept = []
        try:
            live = {f"council-{r['slug']}" for r in registry.load_index()}
            for b in board.list_boards():
                if b.startswith("council-") and b not in live:
                    try:
                        board.remove_board(b[len("council-"):], hard=True)
                        swept.append(b)
                    except Exception:
                        continue
        except Exception:
            pass                                       # best-effort housekeeping
        return _dump({"removed": removed, "count": len(removed), "days": days,
                      "boards_swept": swept})
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
        relayed = False
        try:
            rl = meta.get("relay") or {}
            if isinstance(rl, dict) and rl.get("target"):
                board.send(profile=meta["moderator"], target=rl["target"],
                           subject=f"[council: {meta['topic']}]",
                           message=f"▸ 사람 결정: {choice}")
                relayed = True
        except Exception:
            pass                            # the decision is recorded regardless
        resumed = []
        for c in board.list_cards(meta["board"]):
            if c.get("status") == "blocked":
                board.unblock(meta["board"], c.get("id"))
                resumed.append(c.get("id"))
        if resumed:
            board.dispatch(meta["board"])
        registry.update_status(slug, "running")
        return _dump({"slug": slug, "decided": choice, "resumed": resumed,
                      "relayed": relayed})
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


def _looks_like_a_path(text: str) -> bool:
    """A brief argument meant as a file, not as prose.

    One line, no spaces, and either a directory separator or a document-ish
    suffix. Prose briefs are multi-word, so this only claims the shapes a person
    types when they mean "read this file".
    """
    t = text.strip()
    if not t or len(t.split()) != 1 or "\n" in t:
        return False
    return "/" in t or t.lower().endswith((".md", ".txt", ".markdown", ".rst"))


def _looks_like_slug(text: str) -> bool:
    """A slug is one bare token — meeting ids have no spaces or newlines."""
    return len(text.split()) == 1 and "\n" not in text


def handle_council_command(raw_args: str = "", **kwargs) -> str:
    """`/council` — open a meeting, show one, or list them.

    Three shapes, because this is the name people reach for after installing the
    plugin. Anything that is not a bare slug is a request to hold a meeting: the
    prose is handed back to the agent with instructions to call council_start,
    since only the agent can turn "패널은 에이다·올리버" into arguments. Reading
    that prose as a slug — what this used to do — answered "unknown meeting slug"
    to someone who was asking for a meeting.
    """
    try:
        arg = raw_args.strip()
        if arg and not _looks_like_slug(arg):
            # A slash handler's return value is the reply itself, so this command
            # cannot open a meeting no matter what it returns — it has no way to
            # hand the request to the agent. Say so, and show what does work.
            return ("`/council`은 회의를 열 수 없습니다 — 목록과 상태 조회 전용입니다.\n"
                    "회의는 슬래시 없이 그냥 말하면 열립니다:\n\n"
                    "  <안건 파일의 절대경로 또는 안건 내용>으로 회의를 열어줘.\n"
                    "  패널은 <프로필들>, 의장은 <프로필>. 최대 <n>턴.\n"
                    "  결론 내기 전에 나한테 물어봐.        ← 사람 결정 게이트\n"
                    "  먼저 예행으로 보여줘.                 ← 실제로 열기 전 확인\n\n"
                    "`/council` = 회의 목록 · `/council <slug>` = 그 회의 상태.")
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


def _relay_sent_path(slug: str):
    return registry.meeting_dir(slug) / "relay_sent.json"


def _load_relay_sent(slug: str) -> list:
    p = _relay_sent_path(slug)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []


def handle_relay_flush(args: dict, **kwargs) -> str:
    """Post the speeches nobody can send for themselves, exactly once each.

    Workers relay their own speech under their own identity; that is the whole point
    of worker-side sending. Proxy posts have already given identity up, so council
    does them here — from the transcript, against an on-disk record — which is the
    only way to cover a meeting whose moderator has no messaging credentials.
    Nothing here may raise: a relay hiccup must never disturb a running meeting.
    """
    try:
        slug = str(args.get("slug") or "").strip()
        if not slug:
            return _dump({"error": "slug is required"})
        meta = registry.load_meta(slug)
        rl = meta.get("relay") or {}
        if not isinstance(rl, dict):
            rl = {}
        proxy_for, sender = rl.get("poller_proxy_for") or [], rl.get("sender")
        if not (rl.get("target") and proxy_for and sender):
            return _dump({"slug": slug, "sent": 0, "failed": 0, "pending": 0})
        transcript = (registry.meeting_dir(slug) / "transcript.md").read_text(encoding="utf-8")
        sent_keys = _load_relay_sent(slug)
        pending = relay.pending_proxy_sections(transcript, proxy_for=proxy_for,
                                               sent_keys=sent_keys)
        sent = failed = 0
        for section in pending:
            try:
                board.send(profile=sender, target=rl["target"],
                           subject=relay.proxy_subject(meta["topic"], section),
                           message=section["body"])
            except Exception:
                failed += 1
                continue           # stays pending; the next tick retries it
            sent_keys.append(section["key"])
            sent += 1
            # Record after each send: a crash mid-flush must not replay what went out.
            _relay_sent_path(slug).write_text(json.dumps(sent_keys, ensure_ascii=False),
                                              encoding="utf-8")
        return _dump({"slug": slug, "sent": sent, "failed": failed,
                      "pending": len(pending) - sent})
    except FileNotFoundError:
        return _dump({"error": f"unknown meeting slug: {args.get('slug')}"})
    except Exception as exc:
        return _dump({"error": f"council_relay_flush failed: {type(exc).__name__}: {exc}"})
