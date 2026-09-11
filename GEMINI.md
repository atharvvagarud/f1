<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->

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
