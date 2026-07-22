"""Thin wrapper over the `hermes` CLI. Injectable runner for tests."""
from __future__ import annotations
import json, re, subprocess, pathlib


class BoardError(RuntimeError):
    pass


def _default_runner(args: list[str]) -> str:
    proc = subprocess.run(["hermes", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise BoardError(f"hermes {' '.join(args)} failed: {proc.stderr.strip()[:300]}")
    # Hermes may prepend a secrets-manager banner line on stdout; callers slice JSON themselves.
    return proc.stdout


def _json_obj(out: str) -> dict:
    start = out.find("{")
    if start < 0:
        raise BoardError(f"no JSON object in output: {out[:200]}")
    return json.loads(out[start:])


def _json_arr(out: str) -> list:
    start = out.find("[")
    if start < 0:
        return []
    return json.loads(out[start:])


def list_profiles(*, runner=_default_runner) -> list[str]:
    # `hermes profile list` has no machine-readable flag; kanban assignees does.
    out = runner(["kanban", "assignees", "--json"])
    return [row["name"] for row in _json_arr(out)
            if isinstance(row, dict) and row.get("name")]


def create_board(slug: str, *, runner=_default_runner) -> None:
    runner(["kanban", "boards", "create", f"council-{slug}"])
    runner(["kanban", "--board", f"council-{slug}", "init"])


def create_card(*, board, title, assignee, body, workspace,
                max_runtime="8m", parents=None, runner=_default_runner) -> str:
    args = ["kanban", "--board", board, "create", title,
            "--assignee", assignee, "--workspace", workspace,
            "--max-runtime", max_runtime, "--created-by", "council", "--body", body]
    for p in (parents or []):
        args += ["--parent", p]
    args.append("--json")
    return _json_obj(runner(args))["id"]


def dispatch(board: str, max_n: int = 1, *, runner=_default_runner) -> dict:
    return _json_obj(runner(["kanban", "--board", board, "dispatch",
                             "--max", str(max_n), "--json"]))


def list_cards(board: str, *, runner=_default_runner) -> list[dict]:
    return _json_arr(runner(["kanban", "--board", board, "list", "--json"]))


def unblock(board: str, task_id: str, *, runner=_default_runner) -> None:
    runner(["kanban", "--board", board, "unblock", task_id])


def remove_board(slug: str, *, hard: bool = False, runner=_default_runner) -> None:
    args = ["kanban", "boards", "rm", f"council-{slug}"]
    if hard:
        args += ["--hard", "--yes"]
    try:
        runner(args)
    except BoardError:
        pass                       # board may already be gone; housekeeping is best-effort


def comment(board: str, task_id: str, text: str, *, runner=_default_runner) -> None:
    runner(["kanban", "--board", board, "comment", task_id, text])


_GW_RE = re.compile(r"^\s*[✓✔]\s*([A-Za-z0-9_-]+)\s*[—-]\s*PID", re.M)


def running_gateway_profiles(*, runner=_default_runner) -> list[str]:
    """Parse `hermes gateway status` for profiles with a live gateway.

    Returns the per-profile names that show a running PID. An empty list means
    no dispatcher is running, so ready cards would sit forever.
    """
    try:
        out = runner(["gateway", "status"])
    except BoardError:
        return []
    names = _GW_RE.findall(out)
    if "supervised by launchd" in out and not names:
        # Single-gateway machine: the supervised line proves a dispatcher runs.
        return ["*"]
    return names


def _profiles_root(config_root=None) -> pathlib.Path:
    if config_root is not None:
        return pathlib.Path(config_root)
    return pathlib.Path.home() / ".hermes" / "profiles"


def profile_approval_mode(profile: str, *, config_root=None) -> str:
    """Read `approvals.mode` from a profile's config.yaml (best-effort).

    Returns "unknown" when the file or key is absent. Uses a tiny line scan to
    avoid a hard YAML dependency at import time.
    """
    cfg = _profiles_root(config_root) / profile / "config.yaml"
    if not cfg.exists():
        return "unknown"
    in_approvals = False
    for raw in cfg.read_text(encoding="utf-8").splitlines():
        if re.match(r"^approvals:\s*$", raw):
            in_approvals = True
            continue
        if in_approvals:
            if raw and not raw[0].isspace():
                break                      # left the approvals block
            m = re.match(r"\s+mode:\s*(\S+)", raw)
            if m:
                return m.group(1).strip().strip("'\"")
    return "unknown"
