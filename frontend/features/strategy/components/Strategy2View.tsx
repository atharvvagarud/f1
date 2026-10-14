// Strategy 2.0 workspace (V3.6G).
//
// Information architecture: context → precomputed catalogue → setup
// (exact anchor + target + alternatives, cache-first) → run →
// reference → leaders → trade-off matrix → distribution/detail →
// provenance → methodology. Composition only: the backend owns the
// science, useStrategy2 owns request state and identity guards,
// strategy2Machine owns pure display transforms. Copy stays bounded:
// point-estimate leaders, never a recommendation; counterfactual
// simulation, never an observed outcome; cached precomputation, never
// a live fallback.

"use client";

import Link from "next/link";
import type { ReplayFrameMeta } from "@/lib/v2";
import { RaceSelector } from "@/features/replay/components/RaceSelector";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { useStrategy2 } from "@/features/strategy/hooks/useStrategy2";
import { useExpertWorkspaceHydration } from "@/features/workspace/hooks/useExpertHydration";
import { Strategy2Results } from "@/features/strategy/components/Strategy2Results";
import {
  CANONICAL_CANDIDATES,
  strategyAnchorFromFrame,
} from "@/features/strategy/lib/strategyMachine";
import {
  CACHE_MISS_COPY,
  groupAvailabilityByRace,
} from "@/features/strategy/lib/strategy2Machine";
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
        <label htmlFor="strategy2-state" className={labelClass}>
          Race state · exact anchor
        </label>
        <span className="font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
          {totalFrames} discrete reconstructed states
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="font-data text-[10px] text-fg-dim tabular-nums">0</span>
        <input
          id="strategy2-state"
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

const ALTERNATIVE_GROUPS = ["STAY OUT", "PIT NOW", "PIT NEXT LAP"] as const;

export function Strategy2View() {
  const strategy = useStrategy2();
  const {
    races,
    racesLoading,
    racesError,
    catalogue,
    catalogueLoading,
    catalogueError,
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
    seed,
    selectSeed,
    alternativeKeys,
    toggleAlternative,
    selectAllAlternatives,
    detailKey,
    setDetailKey,
    applyCatalogueEntry,
    view,
    canRun,
    run,
    runLive,
    liveAllowed,
    retry,
  } = strategy;

  const running = view.kind === "running";
  // V3.10G: consume the canonical pit-wall deep link (?race=&frame=&driver=)
  // where supported — race + exact frame + target prefill only, no science
  // change. Unknown races and out-of-range frames are ignored fail-closed.
  useExpertWorkspaceHydration({
    racesLoading,
    raceIds: races.map((race) => race.race_id),
    raceId,
    totalFrames,
    frameIndex,
    driverKey: target ?? "",
    selectRace,
    selectFrame,
    applyDriver: selectTarget,
  });
  const anchor = selectedFrame ? strategyAnchorFromFrame(selectedFrame) : null;
  const selectedRace = races.find((race) => race.race_id === raceId) ?? null;
  const targetState = roster.find((d) => d.driver_id === target) ?? null;
  const catalogueGroups = groupAvailabilityByRace(catalogue);

  const status: { label: string; tone: StatusTone } =
    view.kind === "running"
      ? { label: view.live ? "Running live" : "Loading", tone: "warn" }
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
              Strategy 2.0 · simulated alternatives
            </h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
              Compare simulated strategy alternatives for one driver from one
              exact reconstructed historical state. Results are paired Monte
              Carlo estimates with sampling uncertainty — simulated
              differences, not observed outcomes.
            </p>
          </div>
          <div className="shrink-0 text-right">
            <div className="flex flex-wrap justify-end gap-1.5">
              <StatusChip label="Strategy 2.0" tone="neutral" />
              <StatusChip label="5,000 paired futures" tone="neutral" />
            </div>
            <p className="mt-1.5 font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
              Engine v3.6c · simulator MC2-E
            </p>
          </div>
        </div>
      </header>

      <Panel className="mt-4">
        <PanelHeader
          title="Race state"
          meta={timelineLoading ? "Loading states…" : "Exact anchor · no nearest state"}
        />
        <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3 sm:grid-cols-4 lg:grid-cols-8">
          <Fact label="Race">
            {selectedRace ? `${selectedRace.season} R${selectedRace.round_no}` : "—"}
            <span className="mt-0.5 block truncate text-[11px] text-fg-muted">
              {selectedRace?.event_name ?? "NO RACE"}
            </span>
          </Fact>
          <Fact label="Checkpoint">
            {anchor ? `LAP ${anchor.anchor_lap_number}` : "—"}
            <span className="mt-0.5 block truncate text-[11px] text-fg-muted">
              {anchor ? `${anchor.anchor_state_time_s.toFixed(3)} s` : "—"}
            </span>
          </Fact>
          <Fact label="Analysed driver">
            {target ? readableDriverId(target) : "—"}
            <span className="mt-0.5 block truncate text-[11px] text-fg-muted">
              {target ?? "—"}
            </span>
          </Fact>
          <Fact label="Position at T">
            {targetState?.position !== null && targetState?.position !== undefined
              ? `P${targetState.position}`
              : "—"}
          </Fact>
          <Fact label="Tyre">
            {targetState?.compound ?? "—"}
            <span className="mt-0.5 block truncate text-[11px] text-fg-muted">
              {targetState?.tyre_life !== null && targetState?.tyre_life !== undefined
                ? `age ${targetState.tyre_life}`
                : "—"}
            </span>
          </Fact>
          <Fact label="Anchor driver">
            {anchor ? readableDriverId(anchor.anchor_driver_id) : "—"}
          </Fact>
          <Fact label="Alternatives">{alternativeKeys.length} selected</Fact>
          <Fact label="Source">
            {view.kind === "result"
              ? view.response.execution_source === "cache"
                ? "Cached"
                : "Live engine"
              : "—"}
          </Fact>
        </div>
      </Panel>

      {racesError ? (
        <div role="alert" className="mt-4 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg">
          {racesError}
        </div>
      ) : null}

      <Panel className="mt-4">
        <PanelHeader
          title="Precomputed catalogue"
          meta={
            catalogueLoading
              ? "Loading catalogue…"
              : `${catalogue.length} precomputed ${catalogue.length === 1 ? "analysis" : "analyses"}`
          }
          note="Strategy 2.0 runs cache-first. Pick a precomputed state to load its exact anchor and target, then run."
        />
        <div className="px-4 py-3">
          {catalogueLoading ? (
            <p className="font-data text-[12px] text-fg-dim">Loading precomputed states…</p>
          ) : catalogueError ? (
            <p role="alert" className="font-data text-[12px] text-warn">{catalogueError}</p>
          ) : catalogueGroups.length === 0 ? (
            <p className="font-data text-[12px] text-fg-dim">
              No precomputed analyses are cached in this deployment. Manual
              selection below still works where the cache holds a result;
              anything else reports not-precomputed honestly.
            </p>
          ) : (
            <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
              {catalogueGroups.map((group) => (
                <li key={group.race_id} className="min-w-0 border border-ink-700">
                  <div className="border-b border-ink-700 px-3 py-1.5 font-data text-[11px] font-bold uppercase tracking-[0.1em] text-fg">
                    {group.race_id}
                    <span className="ml-2 font-normal normal-case tracking-normal text-fg-dim">
                      {group.entries.length} {group.entries.length === 1 ? "state" : "states"}
                    </span>
                  </div>
                  <ul>
                    {group.entries.map((entry) => (
                      <li key={entry.cache_key} className="border-b border-ink-700 last:border-b-0">
                        <button
                          type="button"
                          disabled={running}
                          onClick={() => applyCatalogueEntry(entry)}
                          className="flex w-full flex-wrap items-baseline justify-between gap-x-3 px-3 py-1.5 text-left font-data text-[12px] tabular-nums text-fg transition-colors hover:bg-ink-850 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-focus"
                        >
                          <span>
                            LAP {entry.anchor_lap_number} · {readableDriverId(entry.target_driver_id)}
                            <span className="ml-2 text-[11px] text-fg-dim">
                              {entry.supported ? `${entry.alternative_count} alternatives` : "unsupported state"}
                            </span>
                          </span>
                          <span className="text-[11px] uppercase tracking-[0.1em] text-fg-dim">
                            Load
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
            </ul>
          )}
        </div>
      </Panel>

      <Panel className="mt-4">
        <PanelHeader
          title="Strategy setup"
          meta="Cached by default · explicit run"
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

        <div className="grid grid-cols-1 gap-x-6 gap-y-4 border-b border-ink-700 px-4 py-3 lg:grid-cols-2">
          <div className="flex min-w-0 flex-col gap-1.5">
            <label htmlFor="strategy2-target" className={labelClass}>
              Target driver
            </label>
            <select
              id="strategy2-target"
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
              {rosterLoading ? "Loading roster…" : "One driver. Only the target is intervened on."}
            </span>
          </div>
          <div className="flex min-w-0 flex-col gap-1.5">
            <label htmlFor="strategy2-seed" className={labelClass}>
              Seed · advanced
            </label>
            <input
              id="strategy2-seed"
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
            <span className="font-data text-[11px] text-fg-dim">
              Part of the result identity; the catalogue uses 20240101.
            </span>
          </div>
        </div>

        <div className="border-b border-ink-700 px-4 py-3">
          <fieldset className="m-0 min-w-0 border-0 p-0">
            <legend className={labelClass}>
              Strategy alternatives · {alternativeKeys.length} of 9 selected
            </legend>
            <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-3 md:grid-cols-3">
              {ALTERNATIVE_GROUPS.map((group) => (
                <div key={group} className="min-w-0">
                  <div className="font-ui text-[10px] font-bold uppercase tracking-[0.14em] text-fg">
                    {group}
                  </div>
                  <ul className="mt-1.5 space-y-1.5">
                    {CANONICAL_CANDIDATES.filter((c) => c.group === group).map((candidate) => (
                      <li key={candidate.key}>
                        <label className="flex cursor-pointer items-start gap-2 text-[12px] leading-5 text-fg">
                          <input
                            type="checkbox"
                            checked={alternativeKeys.includes(candidate.key)}
                            disabled={running}
                            onChange={() => toggleAlternative(candidate.key)}
                            className="mt-1 h-3.5 w-3.5 shrink-0 cursor-pointer appearance-none border border-ink-600 bg-ink-950 checked:border-signal checked:bg-signal disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus"
                          />
                          <span>
                            {candidate.label}
                            <span className="block font-data text-[10px] uppercase tracking-[0.08em] text-fg-dim">
                              {candidate.key}
                              {candidate.requested_compound === null ? " · modelled compound" : ""}
                            </span>
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <button type="button" onClick={selectAllAlternatives} disabled={running} className={secondaryButtonClass}>
                Select all 9
              </button>
              <p className="font-data text-[11px] leading-5 text-fg-dim">
                Frozen 9-action contract only — no free-form compound or lap
                controls. Sampled means the compound follows the simulator draw.
              </p>
            </div>
          </fieldset>
        </div>

        <div className="grid grid-cols-1 gap-x-6 gap-y-4 px-4 py-3 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-end">
          <div className="flex min-w-0 flex-col gap-1.5">
            <span className={labelClass}>Run · cached</span>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" onClick={run} disabled={!canRun || running} className={primaryButtonClass}>
                {running ? (view.kind === "running" && view.live ? "Running live…" : "Loading…") : "Run comparison"}
              </button>
              {liveAllowed ? (
                <button
                  type="button"
                  onClick={runLive}
                  disabled={!canRun || running}
                  title="Developer only: executes a real 5,000-future simulation, potentially minutes"
                  className={secondaryButtonClass}
                >
                  Local live run
                </button>
              ) : null}
              <StatusChip label={status.label} tone={status.tone} />
            </div>
          </div>
          <div aria-live="polite" className="font-data text-[11px] leading-5 text-fg-dim">
            {running
              ? view.kind === "running" && view.live
                ? "Running 5,000 paired futures live. The backend does not stream progress; results appear when the run completes."
                : "Loading precomputed result…"
              : view.kind === "result"
                ? `Complete. ${view.response.execution_source === "cache" ? "Precomputed Strategy 2.0 result shown below." : "Live Strategy 2.0 result shown below."}`
                : view.kind === "cache-miss"
                  ? CACHE_MISS_COPY
                  : view.kind === "unsupported"
                    ? "The backend returned an unsupported state. Choose another race, state, or target."
                    : view.kind === "unavailable" || view.kind === "invalid" || view.kind === "error"
                      ? "The request did not produce a comparison. See below."
                      : !canRun
                        ? "Select an exact historical race state and target to enable Run."
                        : "Ready. Run is an explicit cached lookup; changing any control clears the previous result."}
          </div>
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

      {view.kind === "cache-miss" ? (
        <Panel className="mt-4">
          <PanelHeader title="Not precomputed" meta="Cache miss · no fallback" />
          <div className="px-4 py-4">
            <p className="max-w-2xl text-[13px] leading-5 text-fg">{CACHE_MISS_COPY}</p>
            <p className="mt-2 max-w-2xl text-[12px] leading-5 text-fg-muted">
              Nothing was simulated, and no estimate is shown. Pick a
              precomputed state from the catalogue above, or adjust the
              selection and run again.
            </p>
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
            meta="Backend eligibility gate"
            note="The strategy service refused this exact state. The interface does not override that decision."
          />
          <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 px-4 py-4">
            <div className="min-w-0 max-w-2xl">
              <p className="text-[13px] leading-5 text-fg">{view.message}</p>
              <p className="mt-2 text-[12px] leading-5 text-fg-muted">
                Choose another race, move the state selector, or pick a
                different target driver and run again — the state is never
                changed for you. Unsupported is not a negative result.
              </p>
            </div>
            <div className="shrink-0 text-right">
              <div className={labelClass}>Reason</div>
              <p className="mt-1 font-data text-[12px] text-warn">{view.reason ?? "strategy_unsupported"}</p>
              <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={retry}>
                Retry
              </button>
            </div>
          </div>
        </Panel>
      ) : null}

      {view.kind === "unavailable" || view.kind === "invalid" || view.kind === "error" ? (
        <div role="alert" className="mt-4 flex flex-wrap items-center justify-between gap-3 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg">
          <span>
            {view.kind === "unavailable" || view.kind === "invalid" || view.kind === "error"
              ? view.message
              : ""}
          </span>
          <button type="button" className={secondaryButtonClass} onClick={retry}>
            Retry
          </button>
        </div>
      ) : null}

      {view.kind === "result" ? (
        <Strategy2Results response={view.response} detailKey={detailKey} onSelectDetail={setDetailKey} />
      ) : null}

      {view.kind === "idle" && !running ? (
        <Panel className="mt-4">
          <PanelHeader title="Awaiting comparison" meta="Nothing has run yet" />
          <div className="grid grid-cols-1 gap-x-6 gap-y-3 px-4 py-4 lg:grid-cols-2">
            <div className="min-w-0">
              <p className="text-[13px] leading-5 text-fg-muted">
                Pick a precomputed state from the catalogue, or choose a
                served historical race, move to the exact state to branch
                from, pick a target driver and alternatives, then Run
                comparison.
              </p>
              <p className="mt-2 text-[12px] leading-5 text-fg-dim">
                A successful run returns paired simulated differences versus
                the no-intervention reference with Monte Carlo intervals.
              </p>
            </div>
            <div className="min-w-0 border-t border-ink-700 pt-3 lg:border-l lg:border-t-0 lg:pl-6 lg:pt-0">
              <div className={labelClass}>Scope (Strategy 2.0)</div>
              <ul className="mt-2 space-y-1 text-[12px] leading-5 text-fg-dim">
                <li>Single intervention at time T, then frozen simulation.</li>
                <li>No traffic model: free-air rejoin only.</li>
                <li>Compound choice carries no pace effect.</li>
                <li>Reliability, DNF and points are out of scope.</li>
                <li>Alternative futures are simulated, never observed.</li>
              </ul>
              <p className="mt-2 text-[12px] leading-5 text-fg-muted">
                Deeper modelling context lives in{" "}
                <Link href="/about" className="underline underline-offset-2 hover:text-fg">
                  About
                </Link>
                .
              </p>
            </div>
          </div>
          <div className="border-t border-ink-700 px-4 py-3">
            <SemanticsNote>
              Strategy 2.0 compares simulated alternatives with paired
              futures. Leaders are point-estimate labels, not recommendations.
            </SemanticsNote>
          </div>
        </Panel>
      ) : null}
    </div>
  );
}
