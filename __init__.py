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
             "council_vote": tools.handle_vote}


def register(ctx) -> None:
    for name, schema in schemas.ALL.items():
        ctx.register_tool(name=name, toolset="council", schema=schema,
                          handler=_HANDLERS[name], emoji=_EMOJI.get(name, ""))
    ctx.register_command("council", tools.handle_council_command,
                         description="council 회의 목록 / <slug>로 상태", args_hint="[slug]")
    ctx.register_cli_command("council", "칸반 기반 다중 프로필 회의",
                             cli.setup, cli.handle, description="council meetings")
    skill_path = pathlib.Path(__file__).parent / "skills" / "council"
    if skill_path.exists():
        ctx.register_skill("council", skill_path,
                           description="칸반 회의(council) 운영 플레이북")
