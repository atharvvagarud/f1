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
