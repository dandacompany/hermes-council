# council

[![ci](https://github.com/dandacompany/hermes-council/actions/workflows/ci.yml/badge.svg)](https://github.com/dandacompany/hermes-council/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Hermes plugin that runs **kanban-based multi-profile meetings**. A named moderator and panel of profiles debate a topic on an isolated board, propagate the discussion themselves via self-scheduling cards, and hand you three deliverables: a summary, a conclusion report, and the full transcript.

Most "multi-agent" helpers fan out one prompt and staple the answers together. `council` runs an actual meeting: every speaker reads the whole record first, the moderator decides who talks next and when the room has converged, and the minutes accumulate in one file you can read live.

## How it works

`council` is thin on purpose. `council_start` seeds a single **kickoff card** whose body carries a mode-specific protocol; from there the kanban workers create the next card themselves and the gateway dispatcher runs them. The shared `transcript.md` under `~/.hermes/.council/<slug>/` is the single source of truth — cards carry the protocol, never the transcript.

- **sequential** — moderator ↔ panelist ping-pong. Each speaker receives the full prior conversation, just like a real meeting.
- **parallel** — the moderator dispatches every panelist at once (they cannot see each other _that_ round), then synthesizes via a card that depends on all of them.
- **max_turns** — cap on panel turns (sequential) or rounds (parallel).
- **allow_early_stop** — let the moderator converge before the cap; `council_stop` forces an immediate synthesis.

## Install

**Option A — clone + copy (development)**

```bash
git clone https://github.com/dandacompany/hermes-council
cp -R hermes-council ~/.hermes/plugins/council   # the repo root is the plugin
hermes -p <profile> plugins enable council               # opt-in is per profile
```

> Plugin discovery does **not** follow symlinks — copy the `council/` directory into `~/.hermes/plugins/`. Enabling is per-profile: a bare `hermes` uses your active profile, so enable `council` on whichever profile you'll drive meetings from. Meeting worker profiles (the panel) don't need the plugin.

**Option B — plugin install**

```bash
hermes plugins install dandacompany/hermes-council --enable
```

**Verify**

```bash
hermes -p <profile> council doctor       # plugin/gateway/kanban/registry checks
hermes -p <profile> council --help       # CLI subcommands
```

## Tools

Handlers follow the Hermes contract `handle(args: dict, **kwargs) -> str` (JSON string).

| Tool              | Purpose                                                                                                                                          |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `council_start`   | Seed a meeting (topic, panel, moderator, mode, max_turns, allow_early_stop). Returns slug/board/kickoff id. `dry_run` plans without dispatching. |
| `council_status`  | Card statuses, transcript section count, whether FINAL was reached, blocked-card recovery hint.                                                  |
| `council_collect` | Split the transcript into `summary.md` / `report.md` / `transcript.export.md`. Optional `out_dir` copy.                                          |
| `council_stop`    | Inject a card telling the moderator to synthesize now and stop.                                                                                  |
| `council_resume`  | Recover a stalled meeting: unblock blocked cards with a file-tool reminder and re-dispatch.                                                      |
| `council_say`     | Steer a live meeting without ending it — appends a directive the next moderator card reads.                                                      |
| `council_archive` | Archive a finished meeting (reversible) and archive its board, to tidy the list.                                                                 |
| `council_decide`  | Resolve an open HITL decision gate — record the human's choice and resume the meeting.                                                           |
| `council_vote`    | Open a human vote/decision gate mid-meeting (question + options) for a person to resolve.                                                        |

`council_start` and `council_status` also return `warnings` — preflight risk checks (no running gateway; a profile in `manual` approval mode, which can time out background workers) and transcript-lint findings (malformed headers, missing/duplicate SUMMARY/FINAL).

Also registered: the `/council` slash command (list meetings / show one by slug), the `hermes council {start|run|status|list|collect|stop|resume|doctor}` CLI, and a bundled `council` skill (operating playbook).

### Richer meetings

- **Brief & roles** — `--brief <file-or-text>` attaches an agenda/context doc (saved to `<slug>/brief.md`, read by every worker); `--role name="perspective"` (repeatable) gives each panelist an assigned lens.
- **Decisions log** — the moderator's final card also writes a `## [DECISIONS]` block (decisions / action items / open questions); `council_collect` splits it into `decisions.md`.
- **Multi-round parallel** — `--mode parallel --max-turns N` runs N rounds; each round dispatches the panel simultaneously and the moderator synthesizes before the next round.
- **Doctor** — `hermes council doctor` checks plugin-enabled, a running gateway, kanban reachability, and registry writability.
- **Runaway safeguard** — each meeting carries a card ceiling; `council_status` reports `runaway` and `council run` force-synthesizes if the moderator overruns `max_turns`.
- **Mid-meeting steer** — `hermes council say <slug> "<note>"` injects a directive the moderator reads next, without ending the meeting.
- **Housekeeping** — `council archive <slug>` (reversible), `council rm <slug> --yes` (destructive), `council gc --days N` (drop old archived), `council list --all`.
- **Re-attach** — `council run --attach <slug>` re-attaches to a running (or orchestrator-crashed) meeting, polls to completion, and collects — the meeting survives the `run` process dying because the gateway drives the cards.
- **Output formats** — `council collect --format md|json|html|all` also emits a structured `<slug>.json` (parsed turns + parts) and a self-contained `<slug>.html` page.
- **Human-in-the-loop** — `--hitl` makes the moderator open a `결정 요청` gate and block before finalizing; `council status` surfaces it as `pending_decision`, and `council decide <slug> "<choice>"` records the answer and resumes. `council vote <slug> "<question>" A B` opens a gate with options. `council run` pauses (never auto-resumes) on a human gate. (Panel-vs-panel voting: just run `--mode parallel` with a "vote A/B/C" brief.)

### One-shot run

`hermes council run` starts a meeting, polls to completion (auto-resuming any blocked cards), collects the deliverables, and prints a completion banner — so you can fire it and walk away:

```bash
hermes council run --topic "Q3 roadmap" --panel "mia,noah" --moderator sophie \
  --mode sequential --max-turns 3 --out ~/Downloads --timeout 1800
```

## Outputs

Everything lives under `~/.hermes/.council/`:

```
~/.hermes/.council/
  index.json                 # every meeting (slug, mode, status, …)
  <slug>/
    meta.json                # config + status
    transcript.md            # the running record
    summary.md               # collect: executive digest
    report.md                # collect: conclusion report
    transcript.export.md     # collect: full transcript with header + TOC
```

## Security

- Meetings run **real profile workers** on an **isolated board** (`council-<slug>`), so they inherit each profile's own tools and approval mode — scope your panel profiles accordingly.
- The plugin handles no secrets and shells out only to the local `hermes` CLI.
- `council_start` refuses unknown profiles; `dry_run` lets you inspect the planned cards before anything dispatches.

## Attribution

Built on the Hermes Agent kanban system (`kanban_create` fan-out + gateway dispatcher). MIT licensed — see `LICENSE`.

---

**Dante Labs** · [YouTube @dante-labs](https://youtube.com/@dante-labs) · datapod.k@gmail.com · [Discord](https://discord.com/invite/rXyy5e9ujs) · [Buy Me a Coffee](https://buymeacoffee.com/dante.labs)
