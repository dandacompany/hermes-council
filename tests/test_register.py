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
    assert "council" in ctx.cli
    assert ctx.skills and ctx.skills[0][0] == "council"


def test_council_does_not_register_a_slash_command_that_shadows_its_skill():
    """`/council <request>` has to reach the agent, and only the skill path does.

    A plugin slash command's return value IS the reply (`fn(raw_args) -> str|None`,
    hermes_cli/plugins.py), so a handler cannot hand work to the agent — on Slack
    the instruction text was printed to the user and the meeting never opened.
    The skill path instead rewrites the inbound message and lets the agent act,
    but a registered command of the same name is matched first and wins. So the
    command must not exist for the skill to be reachable.
    """
    ctx = FakeCtx(); register(ctx)
    assert "council" not in ctx.commands
    assert ctx.skills and ctx.skills[0][0] == "council"
