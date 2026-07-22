import pathlib, yaml
import council
from council import _paths

# Plugin root = wherever the `council` package resolves — the `council/`
# subdir in the dev repo, or the flat repo root when published.
ROOT = pathlib.Path(list(council.__path__)[0])


def test_manifest_matches_registered_tools():
    from council import schemas
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text())
    assert manifest["name"] == "council"
    assert isinstance(manifest["version"], str) and manifest["version"]
    # manifest must declare exactly the tools register(ctx) wires up
    assert set(manifest["provides_tools"]) == set(schemas.ALL)


def test_council_home_honors_env(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCIL_HOME", str(tmp_path / ".council"))
    assert _paths.council_home() == tmp_path / ".council"
