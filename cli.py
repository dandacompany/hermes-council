"""argparse wiring for `hermes council ...`."""
from __future__ import annotations
import json, time
try:  # package context (Hermes-loaded plugin)
    from . import tools, runner
except ImportError:  # flat/standalone context (e.g. pytest at repo root)
    import tools, runner  # type: ignore


def _add_start_args(p, required=True) -> None:
    p.add_argument("--topic", required=required)
    p.add_argument("--panel", required=required, help="쉼표구분 프로필")
    p.add_argument("--moderator", required=required)
    p.add_argument("--mode", default="sequential", choices=["sequential", "parallel"])
    p.add_argument("--max-turns", type=int, default=5)
    p.add_argument("--no-early-stop", action="store_true")
    p.add_argument("--slug")
    p.add_argument("--brief", help="안건 참고자료: 파일 경로 또는 인라인 텍스트")
    p.add_argument("--role", action="append", default=[], metavar="NAME=관점",
                   help="패널별 지정 관점 (반복 가능)")
    p.add_argument("--hitl", action="store_true", help="종료 전 사람 승인 게이트 (HITL)")


def _parse_roles(pairs) -> dict:
    roles = {}
    for item in pairs or []:
        if "=" in item:
            k, v = item.split("=", 1)
            roles[k.strip()] = v.strip()
    return roles


def setup(sp) -> None:
    sub = sp.add_subparsers(dest="council_action", required=True)
    s = sub.add_parser("start", help="회의 시작")
    _add_start_args(s)
    s.add_argument("--dry-run", action="store_true")

    r = sub.add_parser("run", help="회의 시작(또는 재부착)→완주 대기→자동 수집 (원샷)")
    _add_start_args(r, required=False)     # optional when --attach is used
    r.add_argument("--attach", metavar="SLUG", help="새로 시작하지 않고 기존 회의에 재부착")
    r.add_argument("--out", help="산출물 추가 복사 위치 (예: ~/Downloads)")
    r.add_argument("--format", default="md", choices=["md", "json", "html", "all"])
    r.add_argument("--timeout", type=int, default=1800, help="완주 대기 상한(초, 기본 1800)")
    r.add_argument("--interval", type=int, default=20, help="폴링 간격(초, 기본 20)")
    r.add_argument("--no-auto-resume", action="store_true", help="막힌 카드 자동 재개 비활성")
    r.add_argument("--no-collect", action="store_true", help="완주해도 수집하지 않음")

    for name in ("status", "collect", "stop", "resume", "archive"):
        p = sub.add_parser(name, help=f"회의 {name}")
        p.add_argument("slug")
        if name == "collect":
            p.add_argument("--out")
            p.add_argument("--format", default="md", choices=["md", "json", "html", "all"])
        if name == "stop":
            p.add_argument("--reason", default="")

    say = sub.add_parser("say", help="회의 중 사회자에게 지침 주입 (종료 안 함)")
    say.add_argument("slug")
    say.add_argument("note")

    dec = sub.add_parser("decide", help="HITL 결정 게이트에 사람이 응답")
    dec.add_argument("slug")
    dec.add_argument("choice")

    vote = sub.add_parser("vote", help="사람 투표 게이트 열기 (질문+선택지)")
    vote.add_argument("slug")
    vote.add_argument("question")
    vote.add_argument("options", nargs="*")

    rm = sub.add_parser("rm", help="회의 삭제 (레지스트리+보드, 파괴적)")
    rm.add_argument("slug")
    rm.add_argument("--yes", action="store_true", help="확인 없이 삭제")

    gc = sub.add_parser("gc", help="오래된 archived 회의 정리")
    gc.add_argument("--days", type=int, default=30)

    lst = sub.add_parser("list", help="회의 목록")
    lst.add_argument("--all", action="store_true", help="archived 포함")
    sub.add_parser("doctor", help="환경 진단 (플러그인·게이트웨이·kanban·레지스트리)")


def _start_args(args) -> dict:
    return {"topic": args.topic,
            "panel": [x.strip() for x in args.panel.split(",") if x.strip()],
            "moderator": args.moderator, "mode": args.mode, "max_turns": args.max_turns,
            "allow_early_stop": not args.no_early_stop, "slug": args.slug,
            "brief": getattr(args, "brief", None),
            "roles": _parse_roles(getattr(args, "role", [])),
            "hitl": bool(getattr(args, "hitl", False))}


def _run(args) -> str:
    if getattr(args, "attach", None):
        st = json.loads(tools.handle_status({"slug": args.attach}))
        if st.get("error"):
            return json.dumps(st, ensure_ascii=False)
        slug = args.attach
        print(f"⇱ 회의 재부착: {slug} — 완주까지 관찰합니다…")
    else:
        if not (args.topic and args.panel and args.moderator):
            return json.dumps({"error": "--topic/--panel/--moderator 필요 (또는 --attach <slug>)"},
                              ensure_ascii=False)
        started = json.loads(tools.handle_start({**_start_args(args), "dry_run": False}))
        if started.get("error"):
            return json.dumps(started, ensure_ascii=False)
        slug = started["slug"]
        for w in started.get("warnings", []):
            print(w)
        print(f"▶ 회의 시작: {slug} (board {started['board']}) — 완주까지 관찰합니다…")
    max_ticks = max(1, args.timeout // max(1, args.interval))

    def status_fn(s):
        return json.loads(tools.handle_status({"slug": s}))

    def collect_fn(s):
        if args.no_collect:
            return {}
        return json.loads(tools.handle_collect({"slug": s, "out_dir": getattr(args, "out", None),
                                                "format": getattr(args, "format", "md")}))

    result = runner.drive(
        slug, status_fn=status_fn,
        resume_fn=lambda s: json.loads(tools.handle_resume({"slug": s})),
        stop_fn=lambda s: json.loads(tools.handle_stop({"slug": s, "reason": "폭주 안전장치"})),
        collect_fn=collect_fn, sleep_fn=time.sleep,
        interval=args.interval, max_ticks=max_ticks,
        auto_resume=not args.no_auto_resume)

    if result.get("outcome") == "final":
        print("✅ 회의 완료 (FINAL 도달).")
        for kind, path in (result.get("written") or {}).items():
            print(f"  {kind}: {path}")
    elif result.get("outcome") == "awaiting_decision":
        pd = result.get("pending") or {}
        print("⏸ 사람 결정 대기 (HITL 게이트).")
        print(f"  질문: {pd.get('question','')}")
        if pd.get("options"):
            print(f"  선택지: {' / '.join(pd['options'])}")
        print(f"  → `hermes council decide {slug} \"<선택>\"` 후 `hermes council run --attach {slug}`로 재개")
    else:
        print(f"⏱ 시간 초과 — 아직 미완. `hermes council status {slug}`로 확인 후 "
              f"`hermes council collect {slug}`로 부분 수집하세요. (자동재개 {result.get('resumes', 0)}회)")
    return json.dumps(result, ensure_ascii=False)


def _list(show_all: bool) -> str:
    try:
        from . import registry
    except ImportError:
        import registry  # type: ignore
    rows = registry.load_index()
    if not show_all:
        rows = [r for r in rows if r.get("status") != "archived"]
    if not rows:
        return "council 회의가 없습니다."
    lines = ["council 회의 목록:" + (" (archived 포함)" if show_all else "")]
    for r in rows:
        when = (r.get("created_at") or "")[:10]
        lines.append(f"- {r['slug']} · {r.get('mode')} · {r.get('status')} · {when} · {r.get('topic','')[:40]}")
    return "\n".join(lines)


def handle(args) -> None:
    act = args.council_action
    if act == "start":
        out = tools.handle_start({**_start_args(args), "dry_run": args.dry_run})
    elif act == "run":
        out = _run(args)
    elif act == "status":
        out = tools.handle_status({"slug": args.slug})
    elif act == "collect":
        out = tools.handle_collect({"slug": args.slug, "out_dir": getattr(args, "out", None),
                                    "format": getattr(args, "format", "md")})
    elif act == "stop":
        out = tools.handle_stop({"slug": args.slug, "reason": args.reason})
    elif act == "resume":
        out = tools.handle_resume({"slug": args.slug})
    elif act == "say":
        out = tools.handle_say({"slug": args.slug, "note": args.note})
    elif act == "decide":
        out = tools.handle_decide({"slug": args.slug, "choice": args.choice})
    elif act == "vote":
        out = tools.handle_vote({"slug": args.slug, "question": args.question,
                                 "options": args.options})
    elif act == "archive":
        out = tools.handle_archive({"slug": args.slug})
    elif act == "rm":
        if not args.yes:
            out = json.dumps({"error": f"파괴적 작업 — 확인하려면 `council rm {args.slug} --yes`"},
                             ensure_ascii=False)
        else:
            out = tools.handle_rm({"slug": args.slug})
    elif act == "gc":
        out = tools.handle_gc({"days": args.days})
    elif act == "list":
        out = _list(bool(getattr(args, "all", False)))
    elif act == "doctor":
        res = json.loads(tools.handle_doctor({}))
        for c in res["checks"]:
            print(f"{'✅' if c['ok'] else '⚠️ '} {c['name']}: {c['detail']}")
        out = json.dumps({"all_ok": res["all_ok"]}, ensure_ascii=False)
    else:
        out = json.dumps({"error": f"unknown action {act}"})
    print(out)
