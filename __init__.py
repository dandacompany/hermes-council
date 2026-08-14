"""council — Hermes kanban meeting plugin."""
from __future__ import annotations
import pathlib

try:
    from . import schemas, tools, cli
except ImportError:  # pytest direct-run context
    import schemas, tools, cli  # type: ignore

_EMOJI = {"council_start": "🏛️", "council_status": "📊", "council_collect": "🧾",
          "council_stop": "🛑", "council_resume": "▶️", "council_say": "🗣️",
          "council_archive": "🗄️", "council_decide": "✅", "council_vote": "🗳️"}
_HANDLERS = {"council_start": tools.handle_start, "council_status": tools.handle_status,
             "council_collect": tools.handle_collect, "council_stop": tools.handle_stop,
             "council_resume": tools.handle_resume, "council_say": tools.handle_say,
             "council_archive": tools.handle_archive, "council_decide": tools.handle_decide,
             "council_vote": tools.handle_vote,
             "council_relay_flush": tools.handle_relay_flush}


def register(ctx) -> None:
    for name, schema in schemas.ALL.items():
        ctx.register_tool(name=name, toolset="council", schema=schema,
                          handler=_HANDLERS[name], emoji=_EMOJI.get(name, ""))
    # /council exists only because of this registration. Skill slash commands are
    # resolved by scanning the skills directories, and a plugin's bundled skill is
    # not in them — register_skill() makes the skill loadable, not slash-addressable.
    # A command handler cannot open a meeting either (its return value IS the
    # reply), so the handler answers with what to type instead.
    ctx.register_command("council", tools.handle_council_command,
                         description="회의 목록 / <slug> 상태 (회의 개설은 자연어로)",
                         args_hint="[slug]")
    ctx.register_cli_command("council", "칸반 기반 다중 프로필 회의",
                             cli.setup, cli.handle, description="council meetings")
    skill_path = pathlib.Path(__file__).parent / "skills" / "council"
    if skill_path.exists():
        ctx.register_skill("council", skill_path,
                           description="칸반 회의(council) 운영 플레이북")
