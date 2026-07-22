"""Pure splitter: transcript.md -> summary / report / transcript.export."""
from __future__ import annotations
import re

_SUMMARY_RE = re.compile(r"^##\s*\[SUMMARY\]\s*$", re.M)
_FINAL_RE = re.compile(r"^##\s*\[FINAL\][^\n]*$", re.M)
_DECISIONS_RE = re.compile(r"^##\s*\[DECISIONS\]\s*$", re.M)
_TURN_RE = re.compile(r"^##\s*\[", re.M)


def _title(topic, mode, moderator, panel):
    return (f"# {topic} — 회의록\n\n"
            f"> 방식: {mode} · 사회자: {moderator} · 패널: {', '.join(panel)}\n\n---\n\n")


def split(transcript: str, *, topic, slug, mode, moderator, panel) -> dict:
    sm = _SUMMARY_RE.search(transcript)
    fm = _FINAL_RE.search(transcript)
    final_reached = bool(fm)

    export = _title(topic, mode, moderator, panel) + transcript.rstrip() + "\n"

    if not final_reached:
        warn = "> ⚠️ FINAL 미도달 — 부분 수집본입니다.\n\n"
        summary = f"# {topic} — 요약 (부분)\n\n{warn}"
        report = f"# {topic} — 결론 보고서 (부분)\n\n{warn}" + transcript.rstrip() + "\n"
        return {"summary": summary, "report": report,
                "transcript_export": export, "final_reached": False}

    dm = _DECISIONS_RE.search(transcript)
    # Tolerate a missing SUMMARY block: still produce report/export, note the gap.
    summary_body = (transcript[sm.end():fm.start()].strip() if sm
                    else "(요약 블록 없음 — 사회자가 SUMMARY를 기록하지 않았습니다. 보고서에서 발췌하세요.)")
    # Report runs from FINAL up to DECISIONS (if any), else to end.
    report_end = dm.start() if dm else len(transcript)
    report_body = transcript[fm.start():report_end].strip()
    report_body = re.sub(r"^##\s*\[FINAL\][^\n]*\n?", "", report_body, count=1).strip()

    summary = f"# {topic} — 요약\n\n{summary_body}\n"
    report = f"# {topic} — 결론 보고서\n\n> 사회자 {moderator} 종합\n\n{report_body}\n"
    out = {"summary": summary, "report": report,
           "transcript_export": export, "final_reached": True}
    if dm:
        decisions_body = re.sub(r"^##\s*\[DECISIONS\][^\n]*\n?", "",
                                transcript[dm.start():].strip(), count=1).strip()
        out["decisions"] = f"# {topic} — 결정·액션\n\n{decisions_body}\n"
    return out


# ---- HITL decision gate -----------------------------------------------------

_REQUEST_RE = re.compile(r"^##\s*\[결정 요청\][^\n]*$", re.M)
_DECIDED_RE = re.compile(r"^##\s*\[사용자 결정\][^\n]*$", re.M)


def parse_pending_decision(transcript: str) -> dict | None:
    """Return the open decision gate, or None.

    A gate is a '## [결정 요청]' block not yet followed by a '## [사용자 결정]'.
    Parses the '질문:' and optional '선택지:' lines that follow the header.
    """
    reqs = list(_REQUEST_RE.finditer(transcript))
    if not reqs:
        return None
    last = reqs[-1]
    if _DECIDED_RE.search(transcript, last.end()):
        return None                       # already resolved
    # body runs from the header to the next '## [' section or end
    nxt = re.compile(r"^##\s*\[", re.M).search(transcript, last.end())
    body = transcript[last.end():nxt.start() if nxt else len(transcript)]
    question, options = "", []
    for line in body.splitlines():
        s = line.strip()
        qm = re.match(r"^질문:\s*(.+)$", s)
        om = re.match(r"^선택지:\s*(.+)$", s)
        if qm:
            question = qm.group(1).strip()
        elif om:
            options = [o.strip() for o in re.split(r"[/,]", om.group(1)) if o.strip()]
    if not question:
        question = body.strip()[:200]
    return {"question": question, "options": options}


# ---- structured / alternate formats -----------------------------------------

_SECTION_HDR_RE = re.compile(
    r"^##\s*\[(?P<name>[^\]]+)\]\s*—\s*TURN\s+(?P<turn>\d+)\s*\((?P<role>[^)]*)\)\s*$", re.M)


def parse_sections(transcript: str) -> list[dict]:
    """Parse '## [name] — TURN n (role)' speaker/moderator blocks into records."""
    heads = list(_SECTION_HDR_RE.finditer(transcript))
    out = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(transcript)
        body = transcript[m.end():end].strip()
        role = m.group("role")
        out.append({"speaker": m.group("name").strip(), "turn": int(m.group("turn")),
                    "role": "moderator" if role.startswith("moderator") else "speaker",
                    "body": body})
    return out


def to_json(transcript: str, *, topic, slug, mode, moderator, panel) -> dict:
    parts = split(transcript, topic=topic, slug=slug, mode=mode, moderator=moderator, panel=panel)

    def _strip_title(md):
        return re.sub(r"^#[^\n]*\n+", "", md, count=1).strip()

    return {
        "slug": slug, "topic": topic, "mode": mode, "moderator": moderator, "panel": panel,
        "final_reached": parts["final_reached"],
        "summary": _strip_title(parts["summary"]) if parts["final_reached"] else "",
        "report": _strip_title(parts["report"]),
        "decisions": _strip_title(parts["decisions"]) if parts.get("decisions") else "",
        "sections": parse_sections(transcript),
    }


def _md_lines_to_html(md: str) -> str:
    import html as _html
    lines, html_out, in_ul = md.splitlines(), [], False
    for ln in lines:
        s = ln.rstrip()
        if not s.strip():
            if in_ul:
                html_out.append("</ul>"); in_ul = False
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            if in_ul:
                html_out.append("</ul>"); in_ul = False
            lvl = len(m.group(1))
            html_out.append(f"<h{lvl}>{_html.escape(m.group(2))}</h{lvl}>")
            continue
        lm = re.match(r"^\s*[-*]\s+(.*)$", s)
        if lm:
            if not in_ul:
                html_out.append("<ul>"); in_ul = True
            html_out.append(f"<li>{_html.escape(lm.group(1))}</li>")
            continue
        if in_ul:
            html_out.append("</ul>"); in_ul = False
        html_out.append(f"<p>{_html.escape(s)}</p>")
    if in_ul:
        html_out.append("</ul>")
    return "\n".join(html_out)


def to_html(parts: dict, *, topic) -> str:
    blocks = [("요약", parts.get("summary", "")), ("결론 보고서", parts.get("report", ""))]
    if parts.get("decisions"):
        blocks.append(("결정·액션", parts["decisions"]))
    blocks.append(("회의록 전문", parts.get("transcript_export", "")))
    import html as _html
    body = "\n".join(f"<section>{_md_lines_to_html(md)}</section>" for _, md in blocks)
    return (
        "<!doctype html>\n<html lang=\"ko\"><head><meta charset=\"utf-8\">\n"
        f"<title>{_html.escape(topic)} — council</title>\n"
        "<style>body{font-family:system-ui,'Noto Sans KR',sans-serif;max-width:800px;"
        "margin:2rem auto;padding:0 1rem;line-height:1.6;color:#1a1a1a}"
        "h1{border-bottom:2px solid #A0522D;padding-bottom:.3rem}"
        "section{margin-bottom:2.5rem}ul{padding-left:1.2rem}</style></head>\n<body>\n"
        + body + "\n</body></html>\n")
