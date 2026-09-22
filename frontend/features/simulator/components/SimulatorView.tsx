// Monte Carlo simulator workspace (Phase-6 R8; UI4 race-simulation workstation).
//
// Information architecture: page context → simulation setup (exact historical
// initial state + configuration) → run/eligibility → empirical outcome summary
// → finishing-position distribution → provenance/limitations. Composition only:
// the backend owns the science, useSimulator owns request state and identity
// guards, simulatorMachine owns pure display transforms. An unsupported state
// is a first-class technical state — never rewritten into a generic failure and
// never auto-corrected to a different anchor.

"use client";

import type { ReplayFrameMeta } from "@/lib/v2";
import { RaceSelector } from "@/features/replay/components/RaceSelector";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { useSimulator } from "@/features/simulator/hooks/useSimulator";
import { SimulationResults } from "@/features/simulator/components/SimulationResults";
import {
  anchorFromFrame,
  formatCount,
} from "@/features/simulator/lib/simulatorMachine";
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
        <label htmlFor="sim-state" className={labelClass}>
          Race state · exact anchor
        </label>
        <span className="font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
          {totalFrames} discrete reconstructed states
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="font-data text-[10px] text-fg-dim tabular-nums">0</span>
        <input
          id="sim-state"
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
  const selectedRace = races.find((race) => race.race_id === raceId) ?? null;

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
              Race simulator
            </h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
              Branch stochastic futures from one exact reconstructed historical
              state. Results are empirical finishing-order frequencies over
              valid simulated trials — not Phase-3 independent binary winner
              probabilities.
            </p>
          </div>
          <div className="shrink-0">
            <StatusChip label="MONTE_CARLO_FREQUENCY" tone="neutral" />
            <p className="mt-1.5 text-right font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
              Simulation contract v1
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
          title="Simulation setup"
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
              {anchor &&
              anchor.anchor_driver_id !==
                readableDriverId(anchor.anchor_driver_id).toLowerCase() ? (
                <span className="mt-0.5 block truncate text-[10px] uppercase tracking-[0.08em] text-fg-dim">
                  {anchor.anchor_driver_id}
                </span>
              ) : null}
            </Fact>
            <Fact label="Anchor lap">
              {anchor ? anchor.anchor_lap_number : "—"}
            </Fact>
            <Fact label="State time T">
              {anchor ? `${anchor.anchor_state_time_s.toFixed(3)} s` : "—"}
            </Fact>
            <Fact label="Frame">
              {selectedFrame ? `${frameIndex + 1} / ${totalFrames}` : "—"}
            </Fact>
            <Fact label="Simulations requested">{formatCount(count)}</Fact>
          </div>
          <SemanticsNote>
            Replay observes the exact reconstructed race truth at T; the
            simulator branches stochastic futures from that same state. The
            anchor is authoritative — there is no nearest-state behaviour.
          </SemanticsNote>
        </div>

        <div className="grid grid-cols-1 gap-x-6 gap-y-4 px-4 py-3 lg:grid-cols-[auto_auto_minmax(0,1fr)] lg:items-end">
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
                    name="sim-count"
                    value={option}
                    checked={count === option}
                    disabled={running}
                    onChange={() => selectCount(option)}
                    className="peer sr-only"
                  />
                  <span className="flex items-center px-3 font-data text-[12px] tabular-nums text-fg-muted peer-checked:bg-ink-600 peer-checked:text-fg peer-focus-visible:outline-2 peer-focus-visible:-outline-offset-2 peer-focus-visible:outline-focus">
                    {formatCount(option)}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div className="flex min-w-0 flex-col gap-1.5">
            <span className={labelClass}>Run</span>
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={run}
                disabled={!canRun || running}
                className={primaryButtonClass}
              >
                {running ? "Running…" : "Run simulation"}
              </button>
              <StatusChip label={status.label} tone={status.tone} />
            </div>
          </div>

          <div aria-live="polite" className="font-data text-[11px] leading-5 text-fg-dim">
            {running
              ? `Running ${formatCount(count)} simulations… the backend does not stream progress; results appear when the run completes.`
              : view.kind === "result"
                ? "Complete. Simulated outcome frequencies are shown below."
                : view.kind === "unsupported"
                  ? "The backend rejected this exact state. Choose another race or move the state selector, then run again."
                  : view.kind === "error"
                    ? "The request failed. Retry when the API is reachable."
                    : !canRun
                      ? "Select an exact historical race state to enable Run."
                      : "Ready. Run is an explicit action; changing race, state, or count clears the previous result."}
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
            title="Simulation unavailable"
            meta="Backend eligibility gate"
            note="The Phase-6 service rejects this exact historical state. The interface does not override that decision."
          />
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 px-4 py-4">
            <div className="min-w-0 max-w-2xl">
              <p className="text-[13px] leading-5 text-fg">{view.message}</p>
              <p className="mt-2 text-[12px] leading-5 text-fg-muted">
                R4/V1 evolves only supported all-clear, dry, contemporaneous
                anchors. Choose another race or move the state selector and run
                again — the state is never changed for you.
              </p>
            </div>
            <div className="shrink-0 text-right">
              <div className={labelClass}>Reason</div>
              <p className="mt-1 font-data text-[12px] text-warn">
                {view.reason ?? "simulation_unsupported"}
              </p>
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
        <SimulationResults response={view.response} />
      ) : null}

      {view.kind === "idle" && !running ? (
        <Panel className="mt-4">
          <PanelHeader title="Awaiting simulation" meta="Nothing has run yet" />
          <div className="grid grid-cols-1 gap-x-6 gap-y-3 px-4 py-4 lg:grid-cols-2">
            <div className="min-w-0">
              <p className="text-[13px] leading-5 text-fg-muted">
                Choose a served historical race, move to the exact state you
                want to branch from, pick a simulation count, then Run.
              </p>
              <p className="mt-2 text-[12px] leading-5 text-fg-dim">
                A successful run returns empirical finishing-position
                frequencies over valid simulated trials from this exact state.
              </p>
            </div>
            <div className="min-w-0 border-t border-ink-700 pt-3 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
              <div className={labelClass}>Model scope (Phase 6, v1)</div>
              <ul className="mt-2 space-y-1 text-[12px] leading-5 text-fg-dim">
                <li>Supported: all-clear, dry, contemporaneous anchors.</li>
                <li>Rejected: neutralized, wet, non-contemporaneous states.</li>
                <li>Reliability / DNF and points are deferred — not modelled.</li>
                <li>Traffic and overtaking are deferred.</li>
                <li>Pit dynamics are empirical (r6-pit-dynamics-v1).</li>
              </ul>
            </div>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
