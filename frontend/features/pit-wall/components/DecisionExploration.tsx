// Contextual strategy + alternative exploration (V3.10G).
//
// Compact entry points scoped to the exact workspace state (race + frame +
// selected driver). Context first, exploration second, no advice:
//
//   STRATEGY    availability-gated "Explore strategy" (explicit cached compare)
//   ALTERNATIVE availability-gated intervention form (explicit compare)
//
// Both surfaces reuse the frozen typed clients and frozen display
// orientation; values pass through verbatim. Alternatives stay in canonical
// (never performance) order. Deltas are descriptive simulated differences —
// never scores, never ranks, never thresholds, never color-coded.

"use client";

import { useState } from "react";
import Link from "next/link";
import {
  readableDriverId,
} from "@/features/replay/components/StandingsTable";
import { workspaceDeepLink } from "@/features/workspace/lib/deepLinks";
import type { WorkspaceState } from "@/features/workspace/lib/workspaceState";
import type {
  CounterfactualCompound,
  ReplayFrameMeta,
  Strategy2AlternativeResult,
} from "@/lib/v2";
import {
  useCounterfactualEntry,
  useStrategyEntry,
  type CounterfactualEntryStatus,
  type StrategyEntryStatus,
} from "@/features/pit-wall/hooks/useDecisionExploration";
import {
  canonicalAlternativeOrder,
  counterfactualCompactLines,
  strategyCompactLines,
} from "@/features/pit-wall/lib/decisionDisplay";
import {
  INTERVAL_COPY as CF_INTERVAL_COPY,
  NO_INTERVENTION_REFERENCE_COPY,
  SUPERSESSION_COPY,
  lifecycleCounts,
  pitTimingLabel,
} from "@/features/counterfactuals/lib/counterfactualMachine";
import {
  CACHE_MISS_COPY,
  INTERVAL_COPY as ST_INTERVAL_COPY,
  REFERENCE_COPY,
} from "@/features/strategy/lib/strategy2Machine";

const regionTitleClass =
  "font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg";
const statusClass = "font-data text-[12px] leading-5 text-fg-dim";
const buttonClass =
  "h-11 border border-ink-700 px-4 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:text-fg-dim";
const summaryClass =
  "cursor-pointer font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted focus-visible:outline-2 focus-visible:outline-focus";
const linkClass =
  "font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted underline decoration-ink-600 underline-offset-4 transition-colors hover:text-fg focus-visible:outline-2 focus-visible:outline-focus";
const labelClass =
  "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

function candidateLabel(alternative: Strategy2AlternativeResult): string {
  const action = alternative.action.replace(/_/g, " ");
  const compound = alternative.requested_compound;
  return compound ? `${action} — ${compound}` : `${action} — SAMPLED`;
}

function ExpertLinks({ strategyHref, alternativeHref }: { strategyHref: string; alternativeHref: string }) {
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 pt-1">
      <Link href={strategyHref} className={linkClass}>
        Expert: strategy
      </Link>
      <Link href={alternativeHref} className={linkClass}>
        Expert: counterfactuals
      </Link>
    </p>
  );
}

function StrategyResult({ status }: { status: Extract<StrategyEntryStatus, { kind: "result" }> }) {
  const order = canonicalAlternativeOrder();
  const byKey = new Map(status.response.alternatives.map((a) => [a.candidate_key, a]));
  return (
    <div className="mt-3" role="status">
      <p className={statusClass}>
        Deltas are compared with the simulated no-intervention reference.
      </p>
      <ul className="mt-2 space-y-3">
        {order.map((key) => {
          const alternative = byKey.get(key);
          if (!alternative || !alternative.evaluated) return null;
          return (
            <li key={key} className="border-t border-ink-700 pt-2">
              <p className="font-data text-[13px] font-semibold text-fg tabular-nums">
                {candidateLabel(alternative)}
              </p>
              <dl className="mt-1 space-y-1">
                {strategyCompactLines(alternative).map((line) => (
                  <div key={line.metric} className="flex flex-wrap gap-x-2 font-data text-[12px] text-fg tabular-nums">
                    <dt className={labelClass}>{line.short}</dt>
                    <dd>{line.point}</dd>
                    <dd className="text-fg-dim">· 95% MC {line.interval}</dd>
                  </div>
                ))}
              </dl>
            </li>
          );
        })}
      </ul>
      <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
        Intervals show simulation sampling uncertainty.
      </p>
      <details className="mt-2 border-t border-ink-700 pt-2">
        <summary className={summaryClass}>How to read</summary>
        <div className="mt-2 space-y-2">
          <p className="font-data text-[11px] leading-5 text-fg-dim">{REFERENCE_COPY}</p>
          <p className="font-data text-[11px] leading-5 text-fg-dim">{ST_INTERVAL_COPY}</p>
        </div>
      </details>
    </div>
  );
}

function CounterfactualResult({ status }: { status: Extract<CounterfactualEntryStatus, { kind: "result" }> }) {
  const response = status.response;
  const lifecycle = lifecycleCounts(response);
  const superseded = lifecycle.some((row) => row.status === "SUPERSEDED" && row.count > 0);
  return (
    <div className="mt-3" role="status">
      <p className="font-data text-[13px] font-semibold text-fg">
        Simulated alternative
      </p>
      <p className="mt-1 font-data text-[12px] leading-5 text-fg-dim">
        Simulator-conditional comparison under a controlled intervention.
      </p>
      <dl className="mt-2 space-y-1">
        {counterfactualCompactLines(response).map((line) => (
          <div key={line.metric} className="flex flex-wrap gap-x-2 font-data text-[12px] text-fg tabular-nums">
            <dt className={labelClass}>{line.short}</dt>
            <dd>{line.point}</dd>
            <dd className="text-fg-dim">· MC sampling {line.interval}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
        {NO_INTERVENTION_REFERENCE_COPY}
      </p>
      {lifecycle.length > 0 ? (
        <ul className="mt-2 space-y-1 border-t border-ink-700 pt-2">
          {lifecycle.map((row) => (
            <li key={`${row.arm}-${row.status}`} className="font-data text-[11px] text-fg-dim tabular-nums">
              {row.arm} · {row.status} · {row.count.toLocaleString("en-US")} of{" "}
              {row.total.toLocaleString("en-US")}
            </li>
          ))}
        </ul>
      ) : null}
      <details className="mt-2 border-t border-ink-700 pt-2">
        <summary className={summaryClass}>How to read</summary>
        <div className="mt-2 space-y-2">
          <p className="font-data text-[11px] leading-5 text-fg-dim">{CF_INTERVAL_COPY}</p>
          {superseded ? (
            <p className="font-data text-[11px] leading-5 text-fg-dim">{SUPERSESSION_COPY}</p>
          ) : null}
        </div>
      </details>
    </div>
  );
}

function InterventionForm({
  formKey,
  nMin,
  nMax,
  decisionLap,
  compounds,
  running,
  onRun,
}: {
  formKey: string;
  nMin: number;
  nMax: number;
  decisionLap: number;
  compounds: string[];
  running: boolean;
  onRun: (n: number, compound: CounterfactualCompound) => void;
}) {
  const options: number[] = [];
  for (let n = nMin; n <= nMax; n += 1) options.push(n);
  const [n, setN] = useState<number>(nMin);
  const [compound, setCompound] = useState<string>(
    compounds.includes("MEDIUM") ? "MEDIUM" : (compounds[0] ?? "SAMPLED"),
  );
  return (
    <form
      key={formKey}
      className="mt-2 space-y-3"
      onSubmit={(event) => {
        event.preventDefault();
        onRun(n, compound as CounterfactualCompound);
      }}
    >
      <div className="grid grid-cols-2 gap-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor="pitwall-cf-n" className={labelClass}>
            Pit in N laps
          </label>
          <select
            id="pitwall-cf-n"
            className="h-11 min-w-0 border border-ink-700 bg-ink-950 px-2.5 font-data text-[13px] text-fg focus-visible:border-ink-600"
            value={n}
            disabled={running}
            onChange={(event) => setN(Number(event.target.value))}
          >
            {options.map((value) => (
              <option key={value} value={value}>
                N={value}
              </option>
            ))}
          </select>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor="pitwall-cf-compound" className={labelClass}>
            Compound
          </label>
          <select
            id="pitwall-cf-compound"
            className="h-11 min-w-0 border border-ink-700 bg-ink-950 px-2.5 font-data text-[13px] text-fg focus-visible:border-ink-600"
            value={compound}
            disabled={running}
            onChange={(event) => setCompound(event.target.value)}
          >
            {compounds.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="font-data text-[11px] leading-5 text-fg-dim">
        {pitTimingLabel(n, decisionLap)} · only supported interventions are listed.
      </p>
      <button type="submit" disabled={running} className={buttonClass}>
        {running ? "Running comparison…" : "Run comparison"}
      </button>
    </form>
  );
}

export function DecisionExploration({
  state,
  frame,
}: {
  state: WorkspaceState;
  frame: ReplayFrameMeta;
}) {
  const meta = {
    raceId: frame.race_id,
    frameIndex: frame.frame_index,
    anchorDriverId: frame.anchor_driver_id,
    anchorLapNumber: frame.anchor_lap_number,
    anchorStateTimeS: frame.anchor_state_time_s,
  };
  const strategy = useStrategyEntry({
    raceId: state.raceId,
    frame: meta,
    selectedDriverId: state.selectedDriverId,
  });
  const alternative = useCounterfactualEntry({
    raceId: state.raceId,
    frame: meta,
    selectedDriverId: state.selectedDriverId,
  });
  const strategyHref = workspaceDeepLink("/strategy", state);
  const alternativeHref = workspaceDeepLink("/counterfactuals", state);
  const driverName =
    state.selectedDriverId !== null ? readableDriverId(state.selectedDriverId) : null;

  return (
    <div className="min-w-0">
      <section aria-label="Strategy" className="min-w-0">
        <h2 className={regionTitleClass}>Strategy</h2>
        <div className="mt-2">
          <StrategyBlock
            status={strategy.status}
            driverName={driverName}
            onRun={strategy.run}
            onRetry={strategy.retry}
          />
        </div>
      </section>

      <section aria-label="Alternative" className="mt-6 min-w-0">
        <h2 className={regionTitleClass}>Alternative</h2>
        <div className="mt-2">
          <AlternativeBlock
            status={alternative.status}
            driverName={driverName}
            anchorKey={`${meta.raceId}|${meta.anchorDriverId}|${meta.anchorLapNumber}|${meta.anchorStateTimeS}|${state.selectedDriverId ?? "-"}`}
            onRun={alternative.run}
            onRetry={alternative.retry}
          />
        </div>
      </section>

      <div className="mt-3 border-t border-ink-700 pt-2">
        <ExpertLinks strategyHref={strategyHref} alternativeHref={alternativeHref} />
      </div>
    </div>
  );
}

function StrategyBlock({
  status,
  driverName,
  onRun,
  onRetry,
}: {
  status: StrategyEntryStatus;
  driverName: string | null;
  onRun: () => void;
  onRetry: () => void;
}) {
  if (status.kind === "idle") {
    return (
      <p className={statusClass}>
        Select a driver to inspect frozen strategy alternatives at this frame.
      </p>
    );
  }
  if (status.kind === "checking") {
    return (
      <p aria-live="polite" className={statusClass}>
        Checking strategy availability…
      </p>
    );
  }
  if (status.kind === "available" || status.kind === "running" || status.kind === "result") {
    // V3.10H §33: the entry control persists across available → running
    // → result (repeat runs supersede via abort + session guards), so there
    // is no dead end after a run and results announce via role=status.
    const running = status.kind === "running";
    return (
      <div>
        <p role="status" className={statusClass}>
          Strategy alternatives available for {driverName} at this state — cached comparison, nine actions.
        </p>
        <button
          type="button"
          onClick={onRun}
          aria-label={`Explore strategy alternatives for ${driverName} at this state`}
          className={`${buttonClass} mt-2`}
        >
          {status.kind === "result" ? "Run again" : running ? "Running…" : "Explore strategy"}
        </button>
        {status.kind === "result" ? <StrategyResult status={status} /> : null}
        {running ? (
          <p aria-live="polite" className={`${statusClass} mt-2`}>
            Running cached comparison…
          </p>
        ) : null}
      </div>
    );
  }
  if (status.kind === "unsupported") {
    return (
      <div>
        <p role="status" className={statusClass}>
          Strategy unavailable at this state — {status.message}
        </p>
      </div>
    );
  }
  if (status.kind === "cache-miss") {
    return (
      <div>
        <p role="status" className={statusClass}>{CACHE_MISS_COPY}</p>
      </div>
    );
  }
  return (
    <div>
      <p role="alert" className={statusClass}>{status.message}</p>
      <button type="button" onClick={onRetry} className={`${buttonClass} mt-2`}>
        Retry availability
      </button>
    </div>
  );
}

function AlternativeBlock({
  status,
  driverName,
  anchorKey,
  onRun,
  onRetry,
}: {
  status: CounterfactualEntryStatus;
  driverName: string | null;
  anchorKey: string;
  onRun: (n: number, compound: CounterfactualCompound) => void;
  onRetry: () => void;
}) {
  if (status.kind === "idle") {
    return (
      <p className={statusClass}>
        Select a driver to inspect a simulated alternative at this frame.
      </p>
    );
  }
  if (status.kind === "checking") {
    return (
      <p aria-live="polite" className={statusClass}>
        Checking alternative availability…
      </p>
    );
  }
  if (status.kind === "available" || status.kind === "running" || status.kind === "result") {
    // V3.10H §33: the intervention form persists across available →
    // running → result (selections kept, no dead end after a run). Controls
    // disable briefly while running so N/compound cannot drift from the
    // pending request; results announce via role=status.
    const running = status.kind === "running";
    return (
      <div>
        <p role="status" className={statusClass}>
          Simulated alternative available for {driverName} at this state.
        </p>
        <details className="mt-2">
          <summary className={summaryClass}>Explore alternative</summary>
          <InterventionForm
            formKey={anchorKey}
            nMin={status.nMin}
            nMax={status.nMax}
            decisionLap={status.decisionLap}
            compounds={status.compounds}
            running={running}
            onRun={onRun}
          />
        </details>
        {status.kind === "result" ? <CounterfactualResult status={status} /> : null}
        {running ? (
          <p aria-live="polite" className={`${statusClass} mt-2`}>
            Running comparison…
          </p>
        ) : null}
      </div>
    );
  }
  if (status.kind === "unsupported") {
    return (
      <div>
        <p role="status" className={statusClass}>
          Alternative unavailable at this state — {status.message}
        </p>
      </div>
    );
  }
  if (status.kind === "cache-miss") {
    return (
      <div>
        <p role="status" className={statusClass}>
          This comparison is scientifically valid but is not in the precomputed
          cache. Nothing was simulated and no estimate is shown.
        </p>
      </div>
    );
  }
  if (status.kind === "invalid") {
    return (
      <div>
        <p role="alert" className={statusClass}>{status.message}</p>
      </div>
    );
  }
  return (
    <div>
      <p role="alert" className={statusClass}>{status.message}</p>
      <button type="button" onClick={onRetry} className={`${buttonClass} mt-2`}>
        Retry availability
      </button>
    </div>
  );
}
