// Counterfactual Explorer workspace (V3.7G).
//
// Information architecture: factual state → controlled plan →
// comparison mode → simulated differences → lifecycle evidence →
// interpretation → limitations. Composition only: the backend owns
// the science, useCounterfactuals owns request state, the machine
// owns pure display transforms. Copy stays bounded: simulated
// differences, never observed outcomes; cached precomputation, never
// a live fallback; no recommendation language anywhere.

"use client";

import { RaceSelector } from "@/features/replay/components/RaceSelector";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { useCounterfactuals } from "@/features/counterfactuals/hooks/useCounterfactuals";
import { CounterfactualPlanBuilder } from "@/features/counterfactuals/components/CounterfactualPlanBuilder";
import { CounterfactualResults } from "@/features/counterfactuals/components/CounterfactualResults";
import {
  FactualHeader,
  LimitationsPanel,
  MethodologyDrawer,
  ProvenancePanel,
} from "@/features/counterfactuals/components/CounterfactualPanels";
import { Panel, PanelHeader, SemanticsNote } from "@/components/ui/Panel";
import {
  CACHE_MISS_COPY,
  counterfactualReasonCopy,
} from "@/features/counterfactuals/lib/counterfactualMachine";

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

export function CounterfactualView() {
  const explorer = useCounterfactuals();
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
    availability,
    availabilityLoading,
    availabilityError,
    form,
    setForm,
    altTargets,
    setAltTargets,
    altItems,
    setAltItems,
    baseTargets,
    setBaseTargets,
    baseItems,
    setBaseItems,
    rival,
    setRival,
    methodologyOpen,
    setMethodologyOpen,
    provenanceOpen,
    setProvenanceOpen,
    view,
    canRun,
    run,
    retry,
    applyPreset,
  } = explorer;

  const running = view.kind === "running";
  const max = Math.max(0, totalFrames - 1);

  const status: { label: string; tone: StatusTone } =
    view.kind === "running"
      ? { label: "Loading", tone: "warn" }
      : view.kind === "result"
        ? { label: "Complete", tone: "ok" }
        : view.kind === "cache-miss" || view.kind === "unsupported"
          ? { label: "Unavailable", tone: "warn" }
          : view.kind === "error" || view.kind === "invalid" || view.kind === "unavailable"
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
              Counterfactual Explorer
            </h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
              From this factual race state, how do simulated outcomes change
              under this controlled intervention? Paired 5,000-future
              simulations — simulated differences, never what the team should
              have done.
            </p>
          </div>
          <div className="shrink-0 text-right">
            <div className="flex flex-wrap justify-end gap-1.5">
              <StatusChip label="Counterfactuals" tone="neutral" />
              <StatusChip label="5,000 paired futures" tone="neutral" />
            </div>
            <p className="mt-1.5 font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
              Engine v3.7c · runtime v3.7f · simulator MC2-E
            </p>
          </div>
        </div>
      </header>

      {availability && availability.supported ? <div className="mt-4"><FactualHeader availability={availability} targetDriverId={altTargets[0] ?? null} /></div> : null}

      {racesError ? (
        <div role="alert" className="mt-4 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg">
          {racesError}
        </div>
      ) : null}

      <Panel className="mt-4">
        <PanelHeader
          title="Replay state"
          meta={timelineLoading ? "Loading states…" : "Exact anchor · historical replay"}
          note="A historical replay state. Availability below is factual and instant — no simulation runs until Run."
        />
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 px-4 py-3 lg:grid-cols-[minmax(15rem,1fr)_minmax(0,2fr)]">
          <RaceSelector
            races={races}
            raceId={raceId}
            disabled={racesLoading || running}
            onSelect={selectRace}
          />
          {selectedFrame ? (
            <div className="flex min-w-0 flex-col gap-1.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <label htmlFor="cf-state" className={labelClass}>
                  Decision point · exact anchor
                </label>
                <span className="font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
                  {totalFrames} discrete reconstructed states
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-data text-[10px] text-fg-dim tabular-nums">0</span>
                <input
                  id="cf-state"
                  type="range"
                  aria-label="Select exact historical decision point"
                  aria-valuetext={`state ${frameIndex + 1} of ${totalFrames}, anchor ${readableDriverId(selectedFrame.anchor_driver_id)} lap ${selectedFrame.anchor_lap_number}`}
                  min={0}
                  max={max}
                  step={1}
                  value={frameIndex}
                  disabled={running || totalFrames === 0}
                  onChange={(event) => selectFrame(Number(event.target.value))}
                  className="h-6 w-full min-w-0 cursor-pointer appearance-none bg-transparent disabled:cursor-not-allowed disabled:opacity-50 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-2 [&::-moz-range-thumb]:rounded-none [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-signal [&::-moz-range-track]:h-1.5 [&::-moz-range-track]:bg-ink-850 [&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:bg-ink-850 [&::-webkit-slider-thumb]:mt-[-5px] [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-2 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-none [&::-webkit-slider-thumb]:bg-signal"
                />
                <span className="font-data text-[10px] text-fg-dim tabular-nums">{max}</span>
              </div>
              <p className="font-data text-[10px] text-fg-muted tabular-nums">
                LAP {selectedFrame.anchor_lap_number} · anchor {readableDriverId(selectedFrame.anchor_driver_id)} · exact, no interpolation
              </p>
            </div>
          ) : (
            <p className="self-end font-data text-[11px] leading-5 text-fg-dim">
              {racesLoading || timelineLoading ? "Loading race state…" : "Select a served race to load its replay states."}
            </p>
          )}
        </div>
        <div className="border-t border-ink-700 px-4 py-3">
          {availabilityLoading ? (
            <p className="font-data text-[12px] text-fg-dim" role="status">Checking factual availability…</p>
          ) : availabilityError ? (
            <p role="alert" className="font-data text-[12px] text-warn">{availabilityError}</p>
          ) : availability ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-data text-[11px] tabular-nums" aria-live="polite">
              <span className={availability.supported ? "text-ok" : "text-warn"}>
                {availability.supported ? "SUPPORTED STATE" : `UNSUPPORTED · ${availability.reason_code ?? "unknown"}`}
              </span>
              <span className="text-fg-dim">
                {availability.eligible_targets.length} eligible target{availability.eligible_targets.length === 1 ? "" : "s"}
                {" · "}N from availability
                {" · "}{availability.cached_comparison_identities.length} precomputed comparison{availability.cached_comparison_identities.length === 1 ? "" : "s"}
              </span>
            </div>
          ) : null}
        </div>
      </Panel>

      {timelineError ? (
        <div role="alert" className="mt-4 flex flex-wrap items-center justify-between gap-3 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg">
          <span>{timelineError}</span>
          <button type="button" className={secondaryButtonClass} onClick={() => raceId && selectRace(raceId)}>
            Retry
          </button>
        </div>
      ) : null}

      {availability && availability.supported ? (
        <div className="mt-4">
          <CounterfactualPlanBuilder
            form={form}
            onForm={setForm}
            availability={availability}
            running={running}
            altTargets={altTargets}
            altItems={altItems}
            onAltTargets={setAltTargets}
            onAltItems={setAltItems}
            baseTargets={baseTargets}
            baseItems={baseItems}
            onBaseTargets={setBaseTargets}
            onBaseItems={setBaseItems}
            rival={rival}
            onRival={setRival}
            onPreset={applyPreset}
          />
        </div>
      ) : null}

      <Panel className="mt-4">
        <PanelHeader title="Run comparison" meta="Cached by default · explicit run" />
        <div className="flex flex-wrap items-center gap-3 px-4 py-3">
          <button type="button" onClick={run} disabled={!canRun || running} className={primaryButtonClass}>
            {running ? "Loading…" : "Run comparison"}
          </button>
          <StatusChip label={status.label} tone={status.tone} />
          <span aria-live="polite" className="font-data text-[11px] leading-5 text-fg-dim">
            {running
              ? "Loading result. The backend does not stream progress; cached results return instantly."
              : view.kind === "result"
                ? `Complete. ${view.response.execution_source === "cache" ? "Precomputed 5,000-future result shown below." : "Live 5,000-future result shown below."}`
                : view.kind === "cache-miss"
                  ? CACHE_MISS_COPY
                  : view.kind === "unsupported"
                    ? counterfactualReasonCopy(view.reason)
                    : !canRun
                      ? "Select a supported replay state and intervention plan to enable Run."
                      : "Ready. Run is an explicit lookup; changing any control clears the previous result."}
          </span>
        </div>
      </Panel>

      {view.kind === "cache-miss" ? (
        <Panel className="mt-4">
          <PanelHeader title="Not precomputed" meta="Valid counterfactual · no estimate shown" />
          <div className="px-4 py-4">
            <p className="max-w-2xl text-[13px] leading-5 text-fg">Valid counterfactual — not precomputed in this demo.</p>
            <p className="mt-2 max-w-2xl text-[12px] leading-5 text-fg-muted">{CACHE_MISS_COPY}</p>
            <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={retry}>
              Retry
            </button>
          </div>
        </Panel>
      ) : null}

      {view.kind === "unsupported" ? (
        <Panel className="mt-4">
          <PanelHeader
            title="Comparison unavailable"
            meta="Scientifically unsupported · no metrics"
            note="The backend refused this exact comparison. The interface never overrides that decision."
          />
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 px-4 py-4">
            <p className="min-w-0 max-w-2xl text-[13px] leading-5 text-fg">{view.message}</p>
            <div className="shrink-0 text-right">
              <div className={labelClass}>Reason</div>
              <p className="mt-1 font-data text-[12px] text-warn">{view.reason ?? "unsupported"}</p>
              <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={retry}>
                Retry
              </button>
            </div>
          </div>
        </Panel>
      ) : null}

      {view.kind === "unavailable" || view.kind === "invalid" || view.kind === "error" ? (
        <div role="alert" className="mt-4 flex flex-wrap items-center justify-between gap-3 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg">
          <span>{view.message}</span>
          <button type="button" className={secondaryButtonClass} onClick={retry}>
            Retry
          </button>
        </div>
      ) : null}

      {view.kind === "result" ? (
        <div className="mt-4">
          <CounterfactualResults response={view.response} />
        </div>
      ) : null}

      {view.kind === "idle" && !running ? (
        <Panel className="mt-4">
          <PanelHeader title="Awaiting comparison" meta="Nothing has run yet" />
          <div className="px-4 py-4">
            <p className="max-w-2xl text-[13px] leading-5 text-fg-muted">
              Move to the exact decision point, shape a controlled pit schedule,
              then run. A successful comparison returns paired simulated
              differences versus the no-intervention reference with MC sampling
              intervals — plus the lifecycle evidence showing whether the
              schedule actually executed.
            </p>
            <div className="mt-3 border-t border-ink-700 pt-3">
              <SemanticsNote>
                Counterfactuals compare simulated futures under controlled
                interventions. Deltas are simulator-conditional, never
                recommendations.
              </SemanticsNote>
            </div>
          </div>
        </Panel>
      ) : null}

      <div className="mt-4 space-y-4">
        {view.kind === "result" ? (
          <ProvenancePanel
            open={provenanceOpen}
            onToggle={() => setProvenanceOpen(!provenanceOpen)}
            provenance={view.response.provenance}
            comparisonIdentity={view.response.comparison_identity}
            stateIdentity={view.response.state_identity}
            count={view.response.simulation_count}
            seed={view.response.master_seed}
            source={view.response.execution_source}
          />
        ) : null}
        <MethodologyDrawer open={methodologyOpen} onToggle={() => setMethodologyOpen(!methodologyOpen)} />
        <LimitationsPanel />
      </div>
    </div>
  );
}
