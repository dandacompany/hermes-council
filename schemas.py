"""LLM-facing tool schemas for the council toolset."""
from __future__ import annotations

START_SCHEMA = {
    "name": "council_start",
    "description": (
        "Start an automated kanban meeting: named moderator + panel profiles debate a "
        "topic on an isolated board and self-propagate cards. mode 'sequential' = moderator↔panel "
        "ping-pong; 'parallel' = all panelists speak at once then the moderator synthesizes. "
        "Returns the slug/board/kickoff card id. Observe with council_status, gather outputs with council_collect."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "description": "Meeting agenda / question."},
            "panel": {"type": "array", "items": {"type": "string"},
                      "description": "Panelist profile names (must exist)."},
            "moderator": {"type": "string", "description": "Moderator profile name."},
            "mode": {"type": "string", "enum": ["sequential", "parallel"],
                     "description": "Turn topology (default sequential)."},
            "max_turns": {"type": "integer", "description": "Cap on panel turns/rounds (default 5)."},
            "allow_early_stop": {"type": "boolean",
                                 "description": "Let the moderator converge before the cap (default true)."},
            "slug": {"type": "string", "description": "Optional explicit slug (else derived from topic)."},
            "brief": {"type": "string", "description": "Agenda/context: inline text or a path to a file. Saved to <slug>/brief.md; workers read it before speaking."},
            "roles": {"type": "object", "description": "Per-panelist perspective hints, e.g. {\"mia\": \"market view\", \"noah\": \"ops view\"}."},
            "hitl": {"type": "boolean",
                     "description": "Pause for the human before the moderator writes its conclusion (HITL gate). Set true whenever the request asks to be consulted, approved, or asked before the meeting decides or finishes — e.g. '결론 내기 전에 물어봐', '끝내기 전에 확인받아', '내 승인 받고 진행해', 'ask me before you decide', 'check with me first'. The moderator then opens a '결정 요청' and blocks until council_decide answers (default false)."},
            "relay": {"type": "string",
                      "description": "Which channel to relay speeches to, using `hermes send --to` syntax: 'slack', 'slack:#council', 'telegram:-1001234567890:17585'. OMIT THIS unless the request names a destination — relaying is on by default and goes to the channel the moderator can send on. This field never disables relaying; use relay_off for that."},
            "relay_off": {"type": "boolean",
                          "description": "Set true ONLY when the request says not to relay the meeting (e.g. '중계하지 마', 'keep this off the channel'). Omit it otherwise — omitting is not the same as turning relaying off (default false)."},
            "relay_thread": {"type": "boolean",
                             "description": "Group the relayed speeches under one thread where the platform allows it (Slack today); flat channel posts otherwise (default true)."},
            "dry_run": {"type": "boolean", "description": "Plan cards without dispatching (default false)."},
        },
        "required": ["topic", "panel", "moderator"],
    },
}

STATUS_SCHEMA = {
    "name": "council_status",
    "description": "Report a council meeting's progress: card statuses, transcript section count, current TURN, whether FINAL was reached, and any blocked cards.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."}},
                   "required": ["slug"]},
}

COLLECT_SCHEMA = {
    "name": "council_collect",
    "description": "Produce the three deliverables (summary, conclusion report, full transcript) from a meeting's transcript into its registry folder, optionally copying to out_dir.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."},
                                  "out_dir": {"type": "string", "description": "Extra copy destination (e.g. ~/Downloads)."},
                                  "format": {"type": "string", "enum": ["md", "json", "html", "all"],
                                             "description": "Also emit structured JSON and/or a self-contained HTML page (default md)."}},
                   "required": ["slug"]},
}

STOP_SCHEMA = {
    "name": "council_stop",
    "description": "Force-terminate a running meeting: inject a card telling the moderator to synthesize SUMMARY+FINAL now and create no further cards.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."},
                                  "reason": {"type": "string", "description": "Why stop now (optional)."}},
                   "required": ["slug"]},
}

RESUME_SCHEMA = {
    "name": "council_resume",
    "description": "Recover a stalled meeting: unblock every blocked card, inject a file-tool reminder comment, and re-dispatch so the chain continues.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."}},
                   "required": ["slug"]},
}

SAY_SCHEMA = {
    "name": "council_say",
    "description": "Inject a moderator directive mid-meeting (without ending it): appends a '사용자 지침' note to the transcript that the next moderator card reads and applies.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."},
                                  "note": {"type": "string", "description": "The steer/instruction for the moderator."}},
                   "required": ["slug", "note"]},
}

ARCHIVE_SCHEMA = {
    "name": "council_archive",
    "description": "Archive a finished meeting: mark it archived and archive its kanban board (reversible). Use to tidy the meeting list.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."}},
                   "required": ["slug"]},
}

DECIDE_SCHEMA = {
    "name": "council_decide",
    "description": "Resolve an open HITL decision gate: record the human's choice in the transcript and resume the meeting so the moderator applies it.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."},
                                  "choice": {"type": "string", "description": "The human's decision/answer to the open gate."}},
                   "required": ["slug", "choice"]},
}

VOTE_SCHEMA = {
    "name": "council_vote",
    "description": "Open a human vote/decision gate mid-meeting: appends a '결정 요청' with a question and options for the human to resolve via council_decide.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."},
                                  "question": {"type": "string", "description": "The question to put to the human."},
                                  "options": {"type": "array", "items": {"type": "string"},
                                              "description": "Optional choices."}},
                   "required": ["slug", "question"]},
}

RELAY_FLUSH_SCHEMA = {
    "name": "council_relay_flush",
    "description": "Post any speeches that no participant can relay for itself (the moderator has no messenger credentials) to the meeting's channel, exactly once each. No-op when relay is off or everyone sends for themselves.",
    "parameters": {"type": "object",
                   "properties": {"slug": {"type": "string", "description": "Meeting slug."}},
                   "required": ["slug"]},
}

ALL = {s["name"]: s for s in (START_SCHEMA, STATUS_SCHEMA, COLLECT_SCHEMA, STOP_SCHEMA,
                              RESUME_SCHEMA, SAY_SCHEMA, ARCHIVE_SCHEMA, DECIDE_SCHEMA, VOTE_SCHEMA, RELAY_FLUSH_SCHEMA)}
