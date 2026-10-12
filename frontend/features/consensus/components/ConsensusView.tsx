// Model × Simulation disagreement workspace (V3.8G).
//
// Information architecture: state context → model panel → simulation
// panel → disagreement summary → paired visualization → field table →
// interpretation/provenance. Composition only: the F product API owns all
// values; this module renders them verbatim (native*100 for display) and
// never recomputes ranks, ties, or intervals. Disagreement is information,
// never an error state and never a source verdict.

"use client";

import { Panel, PanelHeader, SemanticsNote, Stat } from "@/components/ui/Panel";
import { useConsensus, DEMO_ANCHORS, type DemoAnchorId } from "@/features/consensus/hooks/useConsensus";
import type { ConsensusCompare } from "@/features/consensus/lib/consensusClient";
import {
  formatGapPp,
  formatLeaders,
  formatPct,
  readableConsensusDriver,
  refusalCopy,
} from "@/features/consensus/lib/consensusFormat";
import { FieldTable } from "@/features/consensus/components/FieldTable";
import { GapViz } from "@/features/consensus/components/GapViz";

const labelClass = "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

const anchorButtonClass = (active: boolean): string =>
  `h-9 border px-3 font-ui text-[11px] uppercase tracking-[0.14em] transition-colors focus-visible:outline-2 focus-visible:outline-focus ${
    active
      ? "border-signal bg-signal font-semibold text-focus"
      : "border-ink-700 text-fg-muted hover:border-ink-600 hover:text-fg"
  }`;

function StatusChip({ label, tone }: { label: string; tone: "neutral" | "warn" | "danger" }) {
  const tones = {
    neutral: "border-ink-600 text-fg-muted",
    warn: "border-warn/60 text-warn",
    danger: "border-danger/60 text-danger",
  } as const;
  return (
    <span
      role="status"
      className={`inline-block rounded-chip border px-2 py-0.5 font-ui text-[10px] font-bold uppercase tracking-[0.14em] ${tones[tone]}`}
    >
      {label}
    </span>
  );
}

function topDrivers<T extends { driver_id: string }>(
  drivers: T[],
  key: Extract<keyof T, string>,
  n = 3,
): string[] {
  return [...drivers]
    .sort((a, b) => Number(b[key]) - Number(a[key]))
    .slice(0, n)
    .map((d) => d.driver_id);
}

function SummaryStats({ compare }: { compare: ConsensusCompare }) {
  const rows = compare.disagreement.drivers;
  const leader = compare.disagreement.leader as {
    model_leader?: string[];
    simulation_leader?: string[];
    exact_leader_match?: boolean;
  };
  const topK = compare.disagreement.top_k as Record<string, {
    model?: string[];
    simulation?: string[];
    jaccard?: number | null;
  }>;
  const topEntry = Object.entries(topK).find(([k]) => k.startsWith("top_"));
  const jaccard = topEntry?.[1]?.jaccard;
  const widest = [...rows].sort(
    (a, b) => (b.absolute_gap ?? -1) - (a.absolute_gap ?? -1),
  )[0];
  return (
    <div className="grid grid-cols-2 divide-x divide-ink-700 lg:grid-cols-4">
      <Stat
        label={leader.exact_leader_match ? "Leader match" : "Leader split"}
        value={leader.exact_leader_match ? "LEADER MATCH" : "LEADER SPLIT"}
        hint={`${formatLeaders(leader.model_leader)} vs ${formatLeaders(leader.simulation_leader)}`}
      />
      <Stat
        label="Top-3 overlap"
        value={jaccard === null || jaccard === undefined ? "—" : `${Math.round(jaccard * 100)}%`}
        hint="WIN-ranking overlap, not P(finish ≤ 3)"
      />
      <Stat
        label="Largest gap"
        value={formatGapPp(widest?.signed_gap ?? null) ?? "—"}
        hint={widest ? readableConsensusDriver(widest.driver_id) : undefined}
      />
      <Stat
        label="Field size"
        value={String(rows.length)}
        hint="drivers compared"
      />
    </div>
  );
}

function ResultView({ compare }: { compare: ConsensusCompare }) {
  const modelTop = topDrivers(compare.model.drivers, "p_model");
  const simTop = topDrivers(compare.simulation.drivers, "p_simulation");
  const rank = compare.disagreement.rank as {
    model_rank?: Record<string, number>;
    simulation_rank?: Record<string, number>;
    rank_displacement?: Record<string, number>;
  };
  const leader = compare.disagreement.leader as {
    model_leader?: string[];
    simulation_leader?: string[];
  };
  const trials = compare.disagreement.drivers[0]?.valid_trials;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel>
          <PanelHeader
            title="Model · Logistic"
            meta={compare.availability.model}
            note="Independent binary WIN probabilities — one per driver, never summing to a field total."
          />
          <div className="grid grid-cols-2 divide-x divide-ink-700">
            <Stat label="Model leader" value={formatLeaders(leader.model_leader)} />
            <Stat
              label="Leader probability"
              value={formatPct(compare.model.drivers.find((d) => d.driver_id === leader.model_leader?.[0])?.p_model ?? null) ?? "—"}
            />
          </div>
          <div className="border-t border-ink-700 px-4 py-3">
            <div className={labelClass}>Top ranked</div>
            <ol className="mt-1 space-y-0.5 font-data text-[12px] tabular-nums">
              {modelTop.map((id) => (
                <li key={id} className="flex justify-between gap-2">
                  <span>{readableConsensusDriver(id)}</span>
                  <span className="text-fg-dim">
                    {formatPct(compare.model.drivers.find((d) => d.driver_id === id)?.p_model ?? null)}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </Panel>
        <Panel>
          <PanelHeader
            title="Simulation · MC2-E"
            meta={compare.availability.simulation}
            note="Winner frequencies over mutually exclusive simulated outcomes."
          />
          <div className="grid grid-cols-2 divide-x divide-ink-700">
            <Stat label="Simulation leader" value={formatLeaders(leader.simulation_leader)} />
            <Stat
              label="Leader frequency"
              value={formatPct(compare.simulation.drivers.find((d) => d.driver_id === leader.simulation_leader?.[0])?.p_simulation ?? null) ?? "—"}
            />
          </div>
          <div className="border-t border-ink-700 px-4 py-3">
            <div className={labelClass}>Top ranked · {trials ?? "—"} valid trials</div>
            <ol className="mt-1 space-y-0.5 font-data text-[12px] tabular-nums">
              {simTop.map((id) => (
                <li key={id} className="flex justify-between gap-2">
                  <span>{readableConsensusDriver(id)}</span>
                  <span className="text-fg-dim">
                    {formatPct(compare.simulation.drivers.find((d) => d.driver_id === id)?.p_simulation ?? null)}
                  </span>
                </li>
              ))}
            </ol>
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHeader
          title="Disagreement"
          meta="Δ = simulation − model"
          note="Descriptive difference between two mechanisms at the same factual race state. Disagreement does not determine which source is correct."
        />
        <SummaryStats compare={compare} />
      </Panel>

      <Panel>
        <PanelHeader title="Paired comparison" note="Model and simulation markers share one native-probability scale for visual comparison only; the families differ." />
        <GapViz rows={compare.disagreement.drivers} />
      </Panel>

      <Panel>
        <PanelHeader title="Field comparison table" note="Dense per-driver comparison. Rank columns collapse on small screens." />
        <FieldTable
          rows={compare.disagreement.drivers}
          modelRank={rank.model_rank ?? {}}
          simulationRank={rank.simulation_rank ?? {}}
          rankDisplacement={rank.rank_displacement ?? {}}
        />
      </Panel>

      <Panel>
        <PanelHeader title="Interpretation & provenance" />
        <div className="space-y-3 px-4 py-3">
          <SemanticsNote>
            MODEL is a trained predictive model producing independent binary
            winner probabilities. SIMULATION is a Monte Carlo race simulation
            producing winner frequencies from simulated futures. DISAGREEMENT
            is the difference between those two mechanisms at the same factual
            race state — it does not determine which source is correct.
          </SemanticsNote>
          <SemanticsNote>
            Historical out-of-fold evaluation found meaningful disagreement
            between the mechanisms. Controlled fusion research did not improve
            on the Logistic model, so this workspace shows both sources
            instead of a blended probability.
          </SemanticsNote>
          <details className="border border-ink-700 px-3 py-2">
            <summary className="cursor-pointer font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted focus-visible:outline-2 focus-visible:outline-focus">
              Provenance
            </summary>
            <dl className="mt-2 grid grid-cols-1 gap-1 font-data text-[11px] sm:grid-cols-2">
              {Object.entries(compare.provenance).map(([k, v]) => (
                <div key={k} className="flex gap-2">
                  <dt className="shrink-0 uppercase tracking-[0.12em] text-fg-dim">{k}</dt>
                  <dd className="break-all text-fg">{v}</dd>
                </div>
              ))}
            </dl>
          </details>
        </div>
      </Panel>
    </div>
  );
}

export function ConsensusView() {
  const { anchorId, selectAnchor, view, retry } = useConsensus();
  const ids: DemoAnchorId[] = ["supported", "sim-ineligible", "excluded-2025"];

  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-4 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-ink-600 pb-3">
        <div>
          <h1 className="font-display text-lg font-extrabold uppercase tracking-[-0.02em] text-fg">
            Consensus · Model × Simulation
          </h1>
          <p className="mt-0.5 font-data text-[11px] uppercase tracking-[0.14em] text-fg-dim">
            <StatusChip label="Historical replay" tone="neutral" />{" "}
            Illustrative supported state — disagreement magnitude is not typical of all races
          </p>
        </div>
        <div role="group" aria-label="Comparison state" className="flex flex-wrap gap-2">
          {ids.map((id) => (
            <button
              key={id}
              type="button"
              aria-pressed={anchorId === id}
              onClick={() => selectAnchor(id)}
              className={anchorButtonClass(anchorId === id)}
            >
              {DEMO_ANCHORS[id].label}
            </button>
          ))}
        </div>
      </div>

      {view.kind === "loading" && (
        <Panel>
          <p role="status" className="px-4 py-8 font-data text-[12px] text-fg-dim">
            Loading comparison…
          </p>
        </Panel>
      )}

      {view.kind === "result" && (
        <>
          <p className="font-data text-[11px] uppercase tracking-[0.14em] text-fg-dim">
            {view.compare.state.race_id} · Season {view.compare.state.season} · Lap {view.compare.state.lap_number}
            {view.compare.state.stage ? ` · ${view.compare.state.stage}` : ""} ·{" "}
            {DEMO_ANCHORS[anchorId].note}
          </p>
          <ResultView compare={view.compare} />
        </>
      )}

      {view.kind === "not-comparable" && (
        <Panel>
          <PanelHeader title="Comparison not comparable" meta={view.availability.comparison} />
          <div className="space-y-2 px-4 py-4">
            <p className="font-ui text-[13px] text-fg">
              Model: {view.availability.model} · Simulation: {view.availability.simulation}
            </p>
            <p className="font-data text-[12px] leading-6 text-fg-dim">
              {refusalCopy(view.reason)} No disagreement is rendered because
              both sources are required. Simulation is not shown as 0%.
            </p>
          </div>
        </Panel>
      )}

      {view.kind === "unsupported" && (
        <Panel>
          <PanelHeader title="Unsupported state" meta="NOT_COMPARABLE" />
          <div className="space-y-2 px-4 py-4">
            <p className="font-ui text-[13px] text-fg">{refusalCopy(view.reason)}</p>
            <p className="font-data text-[12px] text-fg-dim">
              2025 remains product-excluded; no fallback state is substituted
              and no research-only predictions are loaded.
            </p>
          </div>
        </Panel>
      )}

      {view.kind === "error" && (
        <Panel>
          <PanelHeader title="Request failed" meta="ERROR" />
          <div className="flex flex-wrap items-center gap-3 px-4 py-4">
            <p role="alert" className="font-data text-[12px] text-fg-dim">
              {view.message}
            </p>
            <button type="button" onClick={retry} className={anchorButtonClass(false)}>
              Retry
            </button>
          </div>
        </Panel>
      )}
    </main>
  );
}
