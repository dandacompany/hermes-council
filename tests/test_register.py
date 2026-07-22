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
        "council_decide", "council_vote"}
    assert all(t["toolset"] == "council" for t in ctx.tools)
    assert "council" in ctx.commands
    assert "council" in ctx.cli
    assert ctx.skills and ctx.skills[0][0] == "council"
