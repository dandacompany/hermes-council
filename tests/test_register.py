from council import register


class FakeCtx:
    def __init__(self):
        self.tools = []; self.commands = []; self.cli = []; self.skills = []

    def register_tool(self, **kw):
        self.tools.append(kw)

    def register_command(self, name, handler, description="", args_hint=""):
        self.commands.append(name)

    def register_cli_command(self, name, help, setup_fn, handler_fn=None, description=""):
        self.cli.append(name)

    def register_skill(self, name, path, description=""):
        self.skills.append((name, str(path)))


def test_register_wires_all_surfaces():
    ctx = FakeCtx(); register(ctx)
    assert {t["name"] for t in ctx.tools} == {"council_start", "council_status", "council_collect", "council_stop",
        "council_resume", "council_say", "council_archive",
        "council_decide", "council_vote", "council_relay_flush"}
    assert all(t["toolset"] == "council" for t in ctx.tools)
    assert "council" in ctx.commands
    assert "council" in ctx.cli
    assert ctx.skills and ctx.skills[0][0] == "council"


def test_council_registers_its_slash_command():
    """`/council` only exists if it is registered as a plugin command.

    Skill slash commands are resolved by scanning the skills directories
    (agent/skill_commands.scan_skill_commands → get_external_skills_dirs), and a
    plugin's bundled skill does not live there — register_skill() makes the skill
    loadable, not slash-addressable. Dropping the command registration in 0.10.0
    therefore did not move `/council` to the skill path; it removed `/council`
    entirely ("Unknown command /council" on Slack).
    """
    ctx = FakeCtx(); register(ctx)
    assert "council" in ctx.commands
    assert ctx.skills and ctx.skills[0][0] == "council"
