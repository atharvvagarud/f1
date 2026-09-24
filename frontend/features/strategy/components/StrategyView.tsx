// Strategy workspace (Phase-7 S7).
//
// Information architecture: page context → strategy setup (exact historical
// state + target + explicit objective + run config) → candidate matrix →
// run/eligibility → baseline reference → point-estimate leader → comparison
// table → candidate detail. Composition only: the backend owns the science,
// useStrategy owns request state and identity guards, strategyMachine owns
// pure display transforms. Copy stays bounded: point-estimate leader, never
// a recommendation; counterfactual simulation, never an observed outcome.

"use client";

import type { ReplayFrameMeta } from "@/lib/v2";
import type { StrategyObjective } from "@/lib/v2";
import { RaceSelector } from "@/features/replay/components/RaceSelector";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { useStrategy } from "@/features/strategy/hooks/useStrategy";
import { StrategyResults } from "@/features/strategy/components/StrategyResults";
import {
  CANONICAL_CANDIDATES,
  DEFAULT_STRATEGY_OBJECTIVE,
  OBJECTIVE_LABELS,
  STRATEGY_OBJECTIVES,
  canAddCandidate,
  formatStrategyCount,
  strategyAnchorFromFrame,
  workloadBand,
  workloadNote,
} from "@/features/strategy/lib/strategyMachine";
import { Panel, PanelHeader, SemanticsNote } from "@/components/ui/Panel";

const labelClass = "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

const secondaryButtonClass =
  "h-8 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus";

const primaryButtonClass =
  "h-9 border border-signal bg-signal px-4 font-ui text-[11px] font-semibold uppercase tracking-[0.14em] text-focus transition-colors hover:bg-signal/90 disabled:cursor-not-allowed disabled:border-dashed disabled:border-ink-700 disabled:bg-ink-950 disabled:text-fg-dim";

type StatusTone = "ok" | "warn" | "danger" | "neutral";

const STATUS_TONE: Record<StatusTone, string> = {
  ok: "border-ok/60 text-ok",
  warn: "border-warn/60 text-warn",
  danger: "border-danger/60 text-danger",
  neutral: "border-ink-600 text-fg-muted",
};

function StatusChip({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <span
      role="status"
      className={`inline-block rounded-chip border px-2 py-0.5 font-ui text-[10px] font-bold uppercase tracking-[0.14em] ${STATUS_TONE[tone]}`}
    >
      {label}
    </span>
  );
}

function Fact({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`min-w-0 ${className}`}>
      <div className={labelClass}>{label}</div>
      <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
        {children}
      </div>
    </div>
  );
}

// Discrete exact-state navigation. The value is a frame ordinal over frozen
// reconstructed states — no interpolation, no nearest-state snapping.
function StateScrubber({
  index,
  totalFrames,
  frame,
  disabled,
  onCommit,
}: {
  index: number;
  totalFrames: number;
  frame: ReplayFrameMeta;
  disabled: boolean;
  onCommit: (index: number) => void;
}) {
  const max = Math.max(0, totalFrames - 1);
  const valueText = `state ${index + 1} of ${totalFrames}, anchor ${readableDriverId(
    frame.anchor_driver_id,
  )} lap ${frame.anchor_lap_number}`;

  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <label htmlFor="strategy-state" className={labelClass}>
          Race state · exact anchor
        </label>
        <span className="font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
          {totalFrames} discrete reconstructed states
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="font-data text-[10px] text-fg-dim tabular-nums">0</span>
        <input
          id="strategy-state"
          type="range"
          aria-label="Select exact historical race state"
          aria-valuetext={valueText}
          min={0}
          max={max}
          step={1}
          value={index}
          disabled={disabled || totalFrames === 0}
          onChange={(event) => onCommit(Number(event.target.value))}
          className="h-6 w-full min-w-0 cursor-pointer appearance-none bg-transparent disabled:cursor-not-allowed disabled:opacity-50 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-2 [&::-moz-range-thumb]:rounded-none [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-signal [&::-moz-range-track]:h-1.5 [&::-moz-range-track]:bg-ink-850 [&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:bg-ink-850 [&::-webkit-slider-thumb]:mt-[-5px] [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-2 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-none [&::-webkit-slider-thumb]:bg-signal"
        />
        <span className="font-data text-[10px] text-fg-dim tabular-nums">
          {max}
        </span>
      </div>
      <p className="font-data text-[10px] text-fg-muted tabular-nums">
        FRAME {index + 1} / {totalFrames} · anchor index {index} · exact, no
        interpolation
      </p>
    </div>
  );
}

const CANDIDATE_GROUPS = ["STAY OUT", "PIT NOW", "PIT NEXT LAP"] as const;

export function StrategyView() {
  const strategy = useStrategy();
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
    roster,
    rosterLoading,
    target,
    selectTarget,
    objective,
    selectObjective,
    count,
    selectCount,
    counts,
    seed,
    selectSeed,
    candidateKeys,
    toggleCandidate,
    view,
    canRun,
    run,
    retry,
  } = strategy;

  const running = view.kind === "running";
  const anchor = selectedFrame ? strategyAnchorFromFrame(selectedFrame) : null;
  const selectedRace = races.find((race) => race.race_id === raceId) ?? null;
  const band = workloadBand(count, candidateKeys.length);

  const status: { label: string; tone: StatusTone } =
    view.kind === "running"
      ? { label: "Running", tone: "warn" }
      : view.kind === "result"
        ? { label: "Complete", tone: "ok" }
        : view.kind === "unsupported"
          ? { label: "Unsupported", tone: "warn" }
          : view.kind === "error"
            ? { label: "Error", tone: "danger" }
            : canRun
              ? { label: "Ready", tone: "ok" }
              : { label: "Awaiting state", tone: "neutral" };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <header className="border-b border-ink-700 pb-4">
        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
          <div className="min-w-0">
            <h1 className="font-display text-2xl font-bold tracking-tight text-fg">
              Strategy · counterfactual pit analysis
            </h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
              Compare simulated pit interventions for one driver from one
              exact reconstructed historical state. Results are paired Monte
              Carlo estimates with sampling uncertainty — not Phase-3
              independent binary winner probabilities.
            </p>
          </div>
          <div className="shrink-0 text-right">
            <StatusChip label="MONTE_CARLO_FREQUENCY" tone="neutral" />
            <p className="mt-1.5 font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
              Strategy contract s1 · comparison v1
            </p>
          </div>
        </div>
      </header>

      {racesError ? (
        <div
          role="alert"
          className="mt-4 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          {racesError}
        </div>
      ) : null}

      <Panel className="mt-4">
        <PanelHeader
          title="Strategy setup"
          meta={timelineLoading ? "Loading states…" : "Exact anchor · no nearest state"}
        />

        <div className="grid grid-cols-1 gap-x-6 gap-y-4 border-b border-ink-700 px-4 py-3 lg:grid-cols-[minmax(15rem,1fr)_minmax(0,2.4fr)]">
          <RaceSelector
            races={races}
            raceId={raceId}
            disabled={racesLoading || running}
            onSelect={selectRace}
          />
          {selectedFrame ? (
            <StateScrubber
              index={frameIndex}
              totalFrames={totalFrames}
              frame={selectedFrame}
              disabled={running}
              onCommit={selectFrame}
            />
          ) : (
            <p className="self-end font-data text-[11px] leading-5 text-fg-dim">
              {racesLoading || timelineLoading
                ? "Loading race state…"
                : "Select a served race to load its reconstructed states."}
            </p>
          )}
        </div>

        <div className="border-b border-ink-700 px-4 py-3">
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
            <Fact label="Race">
              {selectedRace
                ? `${selectedRace.season} R${selectedRace.round_no}`
                : "—"}
              <span className="mt-0.5 block truncate text-[11px] text-fg-muted">
                {selectedRace?.event_name ?? "NO RACE"}
              </span>
            </Fact>
            <Fact label="Anchor driver">
              {anchor ? readableDriverId(anchor.anchor_driver_id) : "—"}
            </Fact>
            <Fact label="Anchor lap">
              {anchor ? anchor.anchor_lap_number : "—"}
            </Fact>
            <Fact label="State time T">
              {anchor ? `${anchor.anchor_state_time_s.toFixed(3)} s` : "—"}
            </Fact>
            <Fact label="Target driver">{target ?? "—"}</Fact>
            <Fact label="Simulations requested">{formatStrategyCount(count)}</Fact>
          </div>
          <SemanticsNote>
            Strategy runs from the exact factual state at time T. The anchor
            is authoritative — there is no nearest-state behaviour.
          </SemanticsNote>
        </div>

        <div className="grid grid-cols-1 gap-x-6 gap-y-4 border-b border-ink-700 px-4 py-3 lg:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-1.5">
            <label htmlFor="strategy-target" className={labelClass}>
              Target driver
            </label>
            <select
              id="strategy-target"
              value={target ?? ""}
              disabled={running || rosterLoading || roster.length === 0}
              onChange={(event) => selectTarget(event.target.value)}
              className="h-9 w-full max-w-xs border border-ink-700 bg-ink-950 px-2 font-data text-[12px] text-fg disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-focus"
            >
              {roster.map((driver) => (
                <option key={driver.driver_id} value={driver.driver_id}>
                  {readableDriverId(driver.driver_id)} · {driver.driver_id}
                </option>
              ))}
            </select>
            <span className="font-data text-[11px] text-fg-dim">
              {rosterLoading
                ? "Loading roster…"
                : "One driver. Only the target is intervened on."}
            </span>
          </div>

          <fieldset className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
            <legend className={labelClass}>
              Objective · explicit, submitted with the run
            </legend>
            <div
              role="radiogroup"
              aria-label="Strategy objective"
              className="flex flex-wrap gap-0 self-start border border-ink-700"
            >
              {STRATEGY_OBJECTIVES.map((option, index) => (
                <label
                  key={option}
                  className={`relative inline-flex cursor-pointer ${
                    index > 0 ? "border-l border-ink-700" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="strategy-objective"
                    value={option}
                    checked={objective === option}
                    disabled={running}
                    onChange={() =>
                      selectObjective(option as StrategyObjective)
                    }
                    className="peer sr-only"
                  />
                  <span className="flex items-center px-3 py-2 font-ui text-[11px] uppercase tracking-[0.1em] text-fg-muted peer-checked:bg-ink-600 peer-checked:text-fg peer-focus-visible:outline-2 peer-focus-visible:-outline-offset-2 peer-focus-visible:outline-focus">
                    {OBJECTIVE_LABELS[option]}
                  </span>
                </label>
              ))}
            </div>
            <span className="font-data text-[11px] text-fg-dim">
              Initial selection {OBJECTIVE_LABELS[DEFAULT_STRATEGY_OBJECTIVE]} —
              visible, editable, and sent explicitly. No objective is
              inherently correct.
            </span>
          </fieldset>
        </div>

        <div className="grid grid-cols-1 gap-x-6 gap-y-4 border-b border-ink-700 px-4 py-3 lg:grid-cols-[auto_auto_minmax(0,1fr)] lg:items-end">
          <fieldset className="m-0 flex min-w-0 flex-col gap-1.5 border-0 p-0">
            <legend className={labelClass}>Simulation count</legend>
            <div className="inline-flex h-9 self-start border border-ink-700">
              {counts.map((option, index) => (
                <label
                  key={option}
                  className={`relative inline-flex cursor-pointer ${
                    index > 0 ? "border-l border-ink-700" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="strategy-count"
                    value={option}
                    checked={count === option}
                    disabled={running}
                    onChange={() => selectCount(option)}
                    className="peer sr-only"
                  />
                  <span className="flex items-center px-3 font-data text-[12px] tabular-nums text-fg-muted peer-checked:bg-ink-600 peer-checked:text-fg peer-focus-visible:outline-2 peer-focus-visible:-outline-offset-2 peer-focus-visible:outline-focus">
                    {formatStrategyCount(option)}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="flex min-w-0 flex-col gap-1.5">
            <label htmlFor="strategy-seed" className={labelClass}>
              Seed · advanced
            </label>
            <input
              id="strategy-seed"
              type="number"
              min={0}
              inputMode="numeric"
              placeholder="Default 20240101"
              value={seed ?? ""}
              disabled={running}
              onChange={(event) => {
                const raw = event.target.value;
                if (raw === "") {
                  selectSeed(undefined);
                  return;
                }
                const parsed = Number(raw);
                selectSeed(Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined);
              }}
              className="h-9 w-44 border border-ink-700 bg-ink-950 px-2 font-data text-[12px] text-fg tabular-nums disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-focus"
            />
          </div>

          <div className="min-w-0">
            <div className={labelClass}>Workload</div>
            <p className="mt-1 font-data text-[11px] leading-5 text-fg-dim">
              <span className="font-bold text-fg">{band}</span>
              {band !== "STANDARD" ? " · " : " · "}
              {workloadNote(band)}
            </p>
          </div>
        </div>

        <div className="border-b border-ink-700 px-4 py-3">
          <fieldset className="m-0 min-w-0 border-0 p-0">
            <legend className={labelClass}>
              Candidate interventions · {candidateKeys.length} selected
            </legend>
            <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-3 md:grid-cols-3">
              {CANDIDATE_GROUPS.map((group) => (
                <div key={group} className="min-w-0">
                  <div className="font-ui text-[10px] font-bold uppercase tracking-[0.14em] text-fg">
                    {group}
                  </div>
                  <ul className="mt-1.5 space-y-1.5">
                    {CANONICAL_CANDIDATES.filter((c) => c.group === group).map(
                      (candidate) => {
                        const checked = candidateKeys.includes(candidate.key);
                        const blocked =
                          !checked && !canAddCandidate(count, candidateKeys);
                        return (
                          <li key={candidate.key}>
                            <label
                              className={`flex cursor-pointer items-start gap-2 text-[12px] leading-5 ${
                                blocked
                                  ? "cursor-not-allowed text-fg-dim"
                                  : "text-fg"
                              }`}
                            >
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={running || blocked}
                                onChange={() => toggleCandidate(candidate.key)}
                                className="mt-1 h-3.5 w-3.5 shrink-0 cursor-pointer appearance-none border border-ink-600 bg-ink-950 checked:border-signal checked:bg-signal disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus"
                              />
                              <span>
                                {candidate.label}
                                <span className="block font-data text-[10px] uppercase tracking-[0.08em] text-fg-dim">
                                  {candidate.key}
                                  {candidate.requested_compound === null
                                    ? " · modelled compound"
                                    : ""}
                                </span>
                              </span>
                            </label>
                          </li>
                        );
                      },
                    )}
                  </ul>
                </div>
              ))}
            </div>
            <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
              Sampled means the compound follows the simulator draw; an
              explicit compound changes only stint sampling and future
              transitions, with no pace effect. The full 9-candidate set is
              an explicit heavier comparison, never automatic.
            </p>
          </fieldset>
        </div>

        <div className="grid grid-cols-1 gap-x-6 gap-y-4 px-4 py-3 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-end">
          <div className="flex min-w-0 flex-col gap-1.5">
            <span className={labelClass}>Run</span>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={run}
                disabled={!canRun || running}
                className={primaryButtonClass}
              >
                {running ? "Running…" : "Run comparison"}
              </button>
              <StatusChip label={status.label} tone={status.tone} />
            </div>
          </div>

          <div aria-live="polite" className="font-data text-[11px] leading-5 text-fg-dim">
            {running
              ? `Running Monte Carlo (${formatStrategyCount(count)} trials × ${candidateKeys.length} candidate${candidateKeys.length === 1 ? "" : "s"})… the backend does not stream progress; results appear when the run completes.`
              : view.kind === "result"
                ? "Complete. Simulated strategy comparison shown below."
                : view.kind === "unsupported"
                  ? "The backend returned an unsupported state. Choose another race, state, or target, then run again."
                  : view.kind === "error"
                    ? "The request failed. Retry when the API is reachable."
                    : !canRun
                      ? "Select an exact historical race state and target to enable Run."
                      : "Ready. Run is an explicit action; changing any control clears the previous result."}
          </div>
        </div>
      </Panel>

      {timelineError ? (
        <div
          role="alert"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          <span>{timelineError}</span>
          <button
            type="button"
            className={secondaryButtonClass}
            onClick={() => raceId && selectRace(raceId)}
          >
            Retry
          </button>
        </div>
      ) : null}

      {view.kind === "unsupported" ? (
        <Panel className="mt-4">
          <PanelHeader
            title="Comparison unavailable"
            meta="Backend eligibility gate"
            note="The strategy service refused this exact state. The interface does not override that decision."
          />
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 px-4 py-4">
            <div className="min-w-0 max-w-2xl">
              <p className="text-[13px] leading-5 text-fg">{view.message}</p>
              <p className="mt-2 text-[12px] leading-5 text-fg-muted">
                Choose another race, move the state selector, or pick a
                different target driver and run again — the state is never
                changed for you.
              </p>
            </div>
            <div className="shrink-0 text-right">
              <div className={labelClass}>Reason</div>
              <p className="mt-1 font-data text-[12px] text-warn">
                {view.reason ?? "strategy_unsupported"}
              </p>
              <button
                type="button"
                className={`${secondaryButtonClass} mt-3`}
                onClick={retry}
              >
                Retry
              </button>
            </div>
          </div>
        </Panel>
      ) : null}

      {view.kind === "error" ? (
        <div
          role="alert"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          <span>{view.message}</span>
          <button type="button" className={secondaryButtonClass} onClick={retry}>
            Retry
          </button>
        </div>
      ) : null}

      {view.kind === "result" ? (
        <StrategyResults response={view.response} />
      ) : null}

      {view.kind === "idle" && !running ? (
        <Panel className="mt-4">
          <PanelHeader title="Awaiting comparison" meta="Nothing has run yet" />
          <div className="grid grid-cols-1 gap-x-6 gap-y-3 px-4 py-4 lg:grid-cols-2">
            <div className="min-w-0">
              <p className="text-[13px] leading-5 text-fg-muted">
                Choose a served historical race, move to the exact state you
                want to branch from, pick a target driver and an explicit
                objective, select interventions, then Run comparison.
              </p>
              <p className="mt-2 text-[12px] leading-5 text-fg-dim">
                A successful run returns paired estimates of the change versus
                the simulated baseline, with Monte Carlo sampling intervals.
              </p>
            </div>
            <div className="min-w-0 border-t border-ink-700 pt-3 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
              <div className={labelClass}>Model scope (Phase 7, s1/v1)</div>
              <ul className="mt-2 space-y-1 text-[12px] leading-5 text-fg-dim">
                <li>Single intervention at time T, then frozen simulation.</li>
                <li>No traffic or overtaking model: free-air rejoin only.</li>
                <li>Compound choice carries no pace effect.</li>
                <li>Reliability / DNF and points are deferred.</li>
                <li>Alternative futures are simulated, never observed.</li>
              </ul>
            </div>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
