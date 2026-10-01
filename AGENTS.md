## F1 Agent Execution Policy (long-running commands)

Project-owned. Applies to any long command: full `pytest tests/`, D11, matrix
builds, frontend build, data generation.

- **No long fixed sleeps.** Never `sleep 120/300/600` to wait for tests,
  builds, D11, data generation or any known background process. Short sleeps
  inside bounded polling are fine.
- **Capture the PID; poll cheaply; wait for the real status.** Launch heavy
  work in the background, record `$!`, then wait on that PID:
  ```bash
  <cmd> > /tmp/task.log 2>&1 &
  PID=$!
  while kill -0 "$PID" 2>/dev/null; do sleep 20; done
  wait "$PID"; STATUS=$?
  ```
  Poll every ~15–30 s (never a tight loop). Trust the exit status, not log
  text. If a tool wrapper blocks on foreground commands, still background the
  process; never simulate completion with a fixed sleep.
- **Keep logs out of context.** While running, check liveness with `kill -0`
  / `ps` and at most a small `tail`. After completion, read only the relevant
  tail; open full logs only when a failure needs investigation.
- **Optimize waiting, never correctness.** Do not skip/shorten tests, weaken
  assertions, change expected results, add xfails, bypass D11 findings, drop
  required fresh-env checks, or touch temporal/leakage/frozen Phase-2
  semantics to go faster.
- **Serialize heavy work.** Do not run two CPU/memory-heavy F1
  validation/data commands concurrently without explicit evidence it is safe
  and beneficial; run expensive gates sequentially. Lightweight independent
  checks (lint, static scans, small tests) may run in parallel.
- **Fast gates first.** Where ordering is not contractually fixed, run
  cheapest failure-detection checks (targeted/static/quick) before committing
  to a 20+ minute full-suite or D11 run. This never replaces the required full
  validation.
- **Don't rerun unchanged gates.** If an expensive gate already passed in the
  current task and later changes provably cannot affect it, reuse that result
  explicitly and say so; rerun whenever validated behaviour could change.
  Never claim a gate passed unless it ran, or the reused evidence is clearly
  identified from the current unchanged state.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## headroom

Headroom 0.37.0 (uv tool `headroom-ai`) is validated for opt-in context optimisation. No persistent config: global `opencode.jsonc` carries no headroom entries by design.

- Launch wrapped sessions only: `HEADROOM_BEACON=off HEADROOM_MODE=cache headroom wrap opencode --no-serena -- <opencode args>`. Never `headroom deploy`/`init` here; never `--memory`/`--learn`.
- Graphify stays the repo-structure tool; headroom only trims redundant tool output. Source/tests override summaries; task requirements override savings.
- Preserve exact failure evidence (traces, metric values, hashes, diffs, gate results). Compressed content is recoverable via the headroom MCP retrieve tool that wrap registers per session.
- Rollback: `headroom unwrap opencode` restores `opencode.jsonc` from its automatic backup and stops the proxy.
