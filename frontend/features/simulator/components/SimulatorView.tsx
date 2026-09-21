// Monte Carlo simulator view (Phase-6 R8).
//
// Minimal, race-first telementry surface: pick a served historical race,
// pick an exact replay state, choose a bounded simulation count, press Run.
// No auto-run, no strategy/what-if controls — those belong to Phase 7.

"use client";

import Link from "next/link";
import { RaceSelector } from "@/features/replay/components/RaceSelector";
import { useSimulator } from "@/features/simulator/hooks/useSimulator";
import { SimulationResults } from "@/features/simulator/components/SimulationResults";
import { anchorFromFrame } from "@/features/simulator/lib/simulatorMachine";

export function SimulatorView() {
  const simulator = useSimulator();
  const {
    races,
    racesLoading,
    racesError,
    raceId,
    selectRace,
    totalFrames,
    timelineLoading,
    timelineError,
    frameIndex,
    selectedFrame,
    selectFrame,
    count,
    selectCount,
    counts,
    view,
    canRun,
    run,
    retry,
  } = simulator;

  const running = view.kind === "running";
  const anchor = selectedFrame ? anchorFromFrame(selectedFrame) : null;

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto flex max-w-6xl flex-col gap-5 px-4 py-6 sm:px-6">
        <header className="flex flex-wrap items-end justify-between gap-3 border-b border-white/10 pb-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-red-500">
              Phase 6 · Monte Carlo
            </p>
            <h1 className="font-heading mt-1 text-2xl font-bold tracking-tight">
              Race simulator
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-400">
              Simulate a historically plausible remainder of a served 2018–2024
              race from one exact state. Results are simulated outcome
              frequencies, not Phase-3 winner probabilities.
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              href="/replay"
              className="rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-white/25 focus-visible:outline-2 focus-visible:outline-red-500"
            >
              ← Replay
            </Link>
            <Link
              href="/"
              className="rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-white/25 focus-visible:outline-2 focus-visible:outline-red-500"
            >
              Prediction home
            </Link>
          </div>
        </header>

        {racesError && (
          <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {racesError}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 rounded-lg border border-white/10 bg-slate-900/40 p-4 md:grid-cols-3">
          <RaceSelector
            races={races}
            raceId={raceId}
            disabled={racesLoading}
            onSelect={selectRace}
          />

          <label className="flex min-w-0 flex-col gap-1 md:col-span-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
              Race state
            </span>
            <input
              aria-label="Select race state frame"
              type="range"
              min={0}
              max={Math.max(0, totalFrames - 1)}
              value={frameIndex}
              disabled={totalFrames === 0 || running}
              onChange={(event) => selectFrame(Number(event.target.value))}
              className="w-full accent-red-500 disabled:opacity-50"
            />
            <span className="text-xs text-slate-400">
              {selectedFrame === null
                ? timelineLoading
                  ? "Loading states…"
                  : "No state selected."
                : `Frame ${frameIndex + 1} of ${totalFrames} · anchor ${
                    selectedFrame.anchor_driver_id
                  } lap ${selectedFrame.anchor_lap_number}`}
            </span>
          </label>
        </div>

        {timelineError && (
          <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {timelineError}{" "}
            <button
              type="button"
              className="underline"
              onClick={() => raceId && selectRace(raceId)}
            >
              Retry
            </button>
          </div>
        )}

        <div className="flex flex-wrap items-end gap-4 rounded-lg border border-white/10 bg-slate-900/40 p-4">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
              Simulations
            </span>
            <select
              aria-label="Simulation count"
              className="rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus-visible:outline-2 focus-visible:outline-red-500 disabled:opacity-50"
              value={count}
              disabled={running}
              onChange={(event) =>
                selectCount(Number(event.target.value) as (typeof counts)[number])
              }
            >
              {counts.map((option) => (
                <option key={option} value={option}>
                  {option.toLocaleString("en-US")}
                </option>
              ))}
            </select>
          </label>

          <button
            type="button"
            onClick={run}
            disabled={!canRun}
            className="rounded-md bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-500 focus-visible:outline-2 focus-visible:outline-red-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {running ? "Running…" : "Run simulation"}
          </button>

          {anchor && (
            <p className="text-xs text-slate-500">
              Exact state: {anchor.race_id} · {anchor.anchor_driver_id} lap{" "}
              {anchor.anchor_lap_number} · T {anchor.anchor_state_time_s.toFixed(3)}s
            </p>
          )}
        </div>

        <div aria-live="polite">
          {running && (
            <p className="text-sm text-slate-400">
              Running Monte Carlo simulation… this can take several seconds at
              higher counts.
            </p>
          )}
        </div>

        {view.kind === "unsupported" && (
          <div role="alert" className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
            <p>{view.message}</p>
            {view.reason && (
              <p className="mt-1 text-xs text-amber-200/80">
                reason: {view.reason}
              </p>
            )}
          </div>
        )}

        {view.kind === "error" && (
          <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {view.message}{" "}
            <button type="button" className="underline" onClick={retry}>
              Retry
            </button>
          </div>
        )}

        {view.kind === "result" && <SimulationResults response={view.response} />}
      </div>
    </main>
  );
}
