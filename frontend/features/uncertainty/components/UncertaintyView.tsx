// Uncertainty intelligence workspace (V3.9D).
//
// Information architecture: state context → field comparison (U1) →
// selected-driver inspector (U1 exact + U2 finite-sampling precision) →
// field agreement telemetry → simulator-sensitivity limitation (U3) →
// scientific context/provenance. Composition only: the V3.9C product API
// owns all values; this module renders them verbatim and never recomputes
// gaps, ranks, standard errors, or intervals. The three uncertainty kinds
// are visually distinct sections — never collapsed into one score, never
// fused, never ranked into a source winner.

"use client";

import { useState } from "react";
import { Panel, PanelHeader, SemanticsNote, Stat } from "@/components/ui/Panel";
import {
  DEMO_ANCHORS,
  useUncertainty,
  type DemoAnchorId,
} from "@/features/uncertainty/hooks/useUncertainty";
import type {
  UncertaintyCompare,
  UncertaintyDriver,
} from "@/features/uncertainty/lib/uncertaintyClient";
import {
  formatAbsGap,
  formatBound,
  formatCount,
  formatJaccard,
  formatProb,
  formatRank,
  formatSE,
  formatSignedGap,
  formatSpearman,
  gapDirection,
  leaderWording,
  readableUncertaintyDriver,
  refusalCopy,
  statusLabel,
} from "@/features/uncertainty/lib/uncertaintyFormat";

const labelClass = "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

const anchorButtonClass = (active: boolean): string =>
  `h-9 border px-3 font-ui text-[11px] uppercase tracking-[0.14em] transition-colors focus-visible:outline-2 focus-visible:outline-focus ${
    active
      ? "border-signal bg-signal font-semibold text-focus"
      : "border-ink-700 text-fg-muted hover:border-ink-600 hover:text-fg"
  }`;

function StatusChip({
  label,
  tone,
}: {
  label: string;
  tone: "neutral" | "ok" | "warn" | "danger";
}) {
  const tones = {
    neutral: "border-ink-600 text-fg-muted",
    ok: "border-ok/60 text-ok",
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

function statusTone(status: string): "neutral" | "ok" | "warn" | "danger" {
  switch (status) {
    case "AVAILABLE":
    case "COMPARABLE":
      return "ok";
    case "MISSING_SOURCE":
    case "INSUFFICIENT_SIMULATIONS":
    case "NOT_COMPARABLE":
      return "warn";
    case "UNSUPPORTED_STATE":
      return "danger";
    default:
      return "neutral";
  }
}

const clamp01 = (v: number): number =>
  Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0;

/** Finite-sampling interval visualization (U2 only).
 *
 * A horizontal MC2 simulation-frequency scale carrying the Wilson 95%
 * interval bar and the p_hat marker. Boundary values render explicitly:
 * the marker is clamped inside the track with a minimum width, so a valid
 * zero is always visible at the edge and never hidden. Text values sit
 * beside the graphic, so position is never the sole carrier.
 */
export function WilsonViz({
  driverId,
  pHat,
  lower,
  upper,
  n,
  k,
}: {
  driverId: string;
  pHat: number;
  lower: number;
  upper: number;
  n: number;
  k: number;
}) {
  const lo = clamp01(lower);
  const hi = clamp01(upper);
  const p = clamp01(pHat);
  const pct = (v: number): string => `${(v * 100).toFixed(2)}%`;
  const name = readableUncertaintyDriver(driverId);
  return (
    <div>
      <div
        role="img"
        aria-label={`${name}: MC2 simulation frequency ${formatProb(pHat)}, Wilson 95% finite-sampling interval ${formatBound(lower)} to ${formatBound(upper)} from ${k} successes across ${n} simulated futures. Interval describes sampling precision only, not the true race probability.`}
        className="relative block h-10"
      >
        <span
          aria-hidden="true"
          className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-ink-600"
        />
        <span
          aria-hidden="true"
          className="absolute top-1/2 h-1.5 -translate-y-1/2 bg-fg-dim"
          style={{ left: pct(lo), width: `calc(${pct(hi)} - ${pct(lo)})`, minWidth: 2 }}
        />
        <span
          aria-hidden="true"
          title={`p_hat ${formatProb(pHat)}`}
          className="absolute top-1/2 h-3 w-[3px] -translate-y-1/2 bg-fg"
          style={{ left: `clamp(0px, ${pct(p)}, calc(100% - 3px))` }}
        />
      </div>
      <div
        aria-hidden="true"
        className="flex justify-between font-data text-[10px] tabular-nums text-fg-dim"
      >
        <span>0.000 native</span>
        <span>MC2 simulation-frequency scale</span>
        <span>1.000 native</span>
      </div>
    </div>
  );
}

function FieldTable({
  drivers,
  selectedId,
  onSelect,
}: {
  drivers: UncertaintyDriver[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px]">
        <caption className="px-4 py-2 text-left font-data text-[11px] leading-5 text-fg-dim">
          Δ = simulation − model (+ = simulation higher). Ranks are
          backend average-tie values, shown exactly. 0.000 is valid measured
          evidence, never missing.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="border-b border-ink-600 px-2 py-2 text-left font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              Driver
            </th>
            <th scope="col" className="border-b border-ink-600 px-2 py-2 text-right font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              <abbr title="V3.1B logistic independent-binary probability" className="no-underline">Model p</abbr>
            </th>
            <th scope="col" className="border-b border-ink-600 px-2 py-2 text-right font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              <abbr title="MC2-E mutually exclusive simulation frequency" className="no-underline">Sim p</abbr>
            </th>
            <th scope="col" className="border-b border-ink-600 px-2 py-2 text-right font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              <abbr title="Signed gap: simulation minus model" className="no-underline">Δ</abbr>
            </th>
            <th scope="col" className="hidden border-b border-ink-600 px-2 py-2 text-right font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim md:table-cell">
              <abbr title="Absolute gap magnitude" className="no-underline">|Δ|</abbr>
            </th>
            <th scope="col" className="hidden border-b border-ink-600 px-2 py-2 text-right font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim md:table-cell">
              Model rk
            </th>
            <th scope="col" className="hidden border-b border-ink-600 px-2 py-2 text-right font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim md:table-cell">
              Sim rk
            </th>
            <th scope="col" className="border-b border-ink-600 px-2 py-2 text-left font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              Status
            </th>
          </tr>
        </thead>
        <tbody>
          {drivers.map((d) => {
            const active = d.driver_id === selectedId;
            const gap = d.disagreement?.signed_gap ?? null;
            return (
              <tr key={d.driver_id} className={active ? "bg-ink-850" : undefined}>
                <th scope="row" className="border-b border-ink-700 px-2 py-1.5 text-left font-data text-[12px] font-normal">
                  <button
                    type="button"
                    onClick={() => onSelect(d.driver_id)}
                    aria-pressed={active}
                    aria-label={`Inspect ${readableUncertaintyDriver(d.driver_id)}`}
                    className="uppercase tracking-[0.06em] hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
                  >
                    <span className={active ? "font-bold text-fg" : "text-fg-muted"}>
                      {active ? "▸ " : ""}
                      {readableUncertaintyDriver(d.driver_id)}
                    </span>
                  </button>
                </th>
                <td
                  title={d.disagreement ? String(d.disagreement.p_model) : undefined}
                  className="border-b border-ink-700 px-2 py-1.5 text-right font-data text-[12px] tabular-nums"
                >
                  {d.disagreement ? formatProb(d.disagreement.p_model) : "—"}
                </td>
                <td
                  title={d.disagreement ? String(d.disagreement.p_simulation) : undefined}
                  className="border-b border-ink-700 px-2 py-1.5 text-right font-data text-[12px] tabular-nums"
                >
                  {d.disagreement ? formatProb(d.disagreement.p_simulation) : "—"}
                </td>
                <td className="border-b border-ink-700 px-2 py-1.5 text-right font-data text-[12px] tabular-nums">
                  {d.disagreement ? (
                    <span title={gapDirection(gap)}>
                      {formatSignedGap(gap)}{" "}
                      <span className="text-fg-dim">· {gapDirection(gap)}</span>
                    </span>
                  ) : (
                    "—"
                  )}
                </td>
                <td className="hidden border-b border-ink-700 px-2 py-1.5 text-right font-data text-[12px] tabular-nums md:table-cell">
                  {d.disagreement ? formatAbsGap(d.disagreement.absolute_gap) : "—"}
                </td>
                <td className="hidden border-b border-ink-700 px-2 py-1.5 text-right font-data text-[12px] tabular-nums md:table-cell">
                  {d.disagreement ? formatRank(d.disagreement.model_rank) : "—"}
                </td>
                <td className="hidden border-b border-ink-700 px-2 py-1.5 text-right font-data text-[12px] tabular-nums md:table-cell">
                  {d.disagreement ? formatRank(d.disagreement.simulation_rank) : "—"}
                </td>
                <td className="border-b border-ink-700 px-2 py-1.5 font-data text-[11px]">
                  <StatusChip label={statusLabel(d.status)} tone={statusTone(d.status)} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DriverInspector({ driver }: { driver: UncertaintyDriver }) {
  const name = readableUncertaintyDriver(driver.driver_id);
  const dis = driver.disagreement;
  const mc = driver.monte_carlo_sampling;
  if (!dis || !mc) {
    return (
      <div className="space-y-2 px-4 py-4">
        <StatusChip label={statusLabel(driver.status)} tone={statusTone(driver.status)} />
        <p className="font-data text-[12px] leading-6 text-fg-dim">
          {driver.status === "MISSING_SOURCE"
            ? `No ${driver.missing_arm ?? "source"} evidence for ${name} at this state. Missing is not zero; no interval is rendered.`
            : driver.status === "INSUFFICIENT_SIMULATIONS"
              ? `Too few valid simulated futures for ${name} to report sampling precision. No interval is fabricated.`
              : `Evidence unavailable for ${name} at this state.`}
        </p>
      </div>
    );
  }
  const gap = dis.signed_gap;
  return (
    <div className="space-y-4 px-4 py-3">
      <div>
        <h3 className="font-display text-[12px] font-bold uppercase tracking-[0.14em] text-fg">
          Model × Simulation disagreement · {name}
        </h3>
        <p className={labelClass}>
          Δ = simulation − model · {gapDirection(gap)}
        </p>
        <dl className="mt-2 grid grid-cols-2 gap-px bg-ink-700 sm:grid-cols-3">
          {[
            ["Model probability", formatProb(dis.p_model), String(dis.p_model)],
            ["Simulation probability", formatProb(dis.p_simulation), String(dis.p_simulation)],
            ["Signed gap", formatSignedGap(gap), `${gapDirection(gap)}; ${String(gap)}`],
            ["Absolute gap", formatAbsGap(dis.absolute_gap), String(dis.absolute_gap)],
            ["Model rank", formatRank(dis.model_rank), undefined],
            ["Simulation rank", formatRank(dis.simulation_rank), undefined],
          ].map(([term, value, title]) => (
            <div key={term} className="bg-ink-900 px-3 py-2">
              <dt className={labelClass}>{term}</dt>
              <dd title={title ?? undefined} className="mt-0.5 font-data text-[13px] tabular-nums text-fg">
                {value}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
          Model value inside simulation Wilson interval:{" "}
          {dis.model_inside_simulation_wilson ? "yes" : "no"} (descriptive
          overlap note, not a verdict on either source).
        </p>
      </div>
      <div className="border-t border-ink-700 pt-3">
        <h3 className="font-display text-[12px] font-bold uppercase tracking-[0.14em] text-fg">
          Monte Carlo precision · finite-sampling evidence
        </h3>
        <p className="mt-1 font-data text-[11px] leading-5 text-fg-dim">
          MC2 observed {formatCount(mc.success_count_k)} successes across{" "}
          {formatCount(mc.valid_futures_n)} simulated futures. The interval
          below describes precision of the simulated frequency from finite
          sampling only — not total uncertainty about the real race.
        </p>
        <dl className="mt-2 grid grid-cols-2 gap-px bg-ink-700 sm:grid-cols-3">
          {[
            ["Successes k", formatCount(mc.success_count_k), undefined],
            ["Futures n", formatCount(mc.valid_futures_n), undefined],
            ["Simulation frequency", formatProb(mc.p_hat), String(mc.p_hat)],
            ["Finite-sampling SE", formatSE(mc.standard_error), String(mc.standard_error)],
            ["Wilson 95% lower", formatBound(mc.wilson_95_lower), String(mc.wilson_95_lower)],
            ["Wilson 95% upper", formatBound(mc.wilson_95_upper), String(mc.wilson_95_upper)],
          ].map(([term, value, title]) => (
            <div key={term} className="bg-ink-900 px-3 py-2">
              <dt className={labelClass}>{term}</dt>
              <dd title={title ?? undefined} className="mt-0.5 font-data text-[13px] tabular-nums text-fg">
                {value}
              </dd>
            </div>
          ))}
        </dl>
        <div className="mt-3">
          <WilsonViz
            driverId={driver.driver_id}
            pHat={mc.p_hat}
            lower={mc.wilson_95_lower}
            upper={mc.wilson_95_upper}
            n={mc.valid_futures_n}
            k={mc.success_count_k}
          />
        </div>
      </div>
    </div>
  );
}

function ResultView({ compare }: { compare: UncertaintyCompare }) {
  const available = compare.drivers.filter((d) => d.status === "AVAILABLE");
  const [selectedId, setSelectedId] = useState<string>(
    available[0]?.driver_id ?? compare.drivers[0]?.driver_id ?? "",
  );
  const selected =
    compare.drivers.find((d) => d.driver_id === selectedId) ??
    compare.drivers[0];
  const f = compare.field;
  const u3 = compare.simulator_sensitivity;

  return (
    <div className="space-y-4">
      <p className="font-data text-[11px] uppercase tracking-[0.14em] text-fg-dim">
        {compare.state.race_id} · Season {compare.state.season} · Lap{" "}
        {compare.state.lap_number}
        {compare.state.stage ? ` · ${compare.state.stage}` : ""} ·{" "}
        {compare.state.state_id}
      </p>

      <Panel>
        <PanelHeader
          title="Field comparison · model × simulation"
          meta={`${compare.drivers.length} drivers · ${available.length} available`}
          note="MODEL is V3.1B logistic independent-binary probability. SIMULATION is MC2-E mutually exclusive simulation frequency. Different families — shown side by side, never blended."
        />
        {selected ? (
          <FieldTable
            drivers={compare.drivers}
            selectedId={selected.driver_id}
            onSelect={setSelectedId}
          />
        ) : null}
      </Panel>

      {selected ? (
        <Panel>
          <PanelHeader
            title="Driver inspector"
            meta={readableUncertaintyDriver(selected.driver_id)}
            note="Exact U1 comparison plus U2 sampling evidence for the selected driver. Selection is local — no further request is issued."
          />
          <DriverInspector driver={selected} />
        </Panel>
      ) : null}

      <Panel>
        <PanelHeader
          title="Field agreement telemetry"
          meta="rank relationship only"
          note="Spearman rank correlation, leader identity, and top-3 set overlap between the two rankings. Values only — no thresholds, no verdicts."
        />
        <div className="grid grid-cols-2 divide-x divide-ink-700 lg:grid-cols-4">
          <Stat
            label="Rank correlation"
            value={formatSpearman(f.rank_correlation_spearman)}
            hint="Spearman, model vs simulation ranks"
          />
          <Stat
            label={leaderWording(f.leader_agree)}
            value={f.leader_agree === null || f.leader_agree === undefined ? "—" : f.leader_agree ? "MATCH" : "DIFFERENT"}
            hint={`${f.leader_model ? readableUncertaintyDriver(f.leader_model) : "—"} vs ${f.leader_simulation ? readableUncertaintyDriver(f.leader_simulation) : "—"}`}
          />
          <Stat
            label="Top-3 overlap"
            value={formatJaccard(f.top3_jaccard)}
            hint="set overlap fraction, not P(finish ≤ 3)"
          />
          <Stat
            label="Common drivers"
            value={String(f.n_common_drivers)}
            hint="drivers compared"
          />
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Simulator sensitivity · not established"
          meta={statusLabel(u3.status)}
        />
        <div className="space-y-2 px-4 py-4">
          <StatusChip label="Not established" tone="neutral" />
          <p className="font-ui text-[13px] leading-6 text-fg">
            No scientifically defensible parameter perturbation range is
            currently registered.
          </p>
          <p className="font-data text-[11px] leading-5 text-fg-dim">
            {u3.reason} This is a limitation of the evidence, not a failure
            of this page.
          </p>
          <details className="border border-ink-700 px-3 py-2">
            <summary className="cursor-pointer font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted focus-visible:outline-2 focus-visible:outline-focus">
              Parameter detail
            </summary>
            <dl className="mt-2 space-y-1 font-data text-[11px] leading-5">
              <div className="flex gap-2">
                <dt className="shrink-0 uppercase tracking-[0.12em] text-fg-dim">regime_std_s</dt>
                <dd className="text-fg">provenance insufficient for perturbation bounds</dd>
              </div>
              <div className="flex gap-2">
                <dt className="shrink-0 uppercase tracking-[0.12em] text-fg-dim">rho</dt>
                <dd className="text-fg">provenance insufficient for perturbation bounds</dd>
              </div>
              <div className="flex gap-2">
                <dt className="shrink-0 uppercase tracking-[0.12em] text-fg-dim">gate</dt>
                <dd className="text-fg">{u3.gate} · {u3.gate_version}</dd>
              </div>
            </dl>
          </details>
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Scientific context & provenance" />
        <div className="space-y-3 px-4 py-3">
          <SemanticsNote>
            MODEL ({compare.sources.model.source}) produces independent
            binary probabilities — one per driver, never summing to a field
            total. SIMULATION ({compare.sources.simulation.source}) produces
            winner frequencies over mutually exclusive simulated outcomes.
            DISAGREEMENT is the difference between those two mechanisms at
            the same factual race state — it does not determine which source
            is correct, and no blended probability is shown because
            controlled fusion research did not improve on the logistic model.
          </SemanticsNote>
          <SemanticsNote>
            MONTE CARLO PRECISION describes how precisely the simulation
            frequency was estimated from finite futures (k successes across
            n simulated futures). SIMULATOR SENSITIVITY is not established:
            no perturbation range is registered, so nothing is claimed about
            robustness.
          </SemanticsNote>
          <details className="border border-ink-700 px-3 py-2">
            <summary className="cursor-pointer font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted focus-visible:outline-2 focus-visible:outline-focus">
              Provenance
            </summary>
            <dl className="mt-2 grid grid-cols-1 gap-1 font-data text-[11px] sm:grid-cols-2">
              <div className="flex gap-2">
                <dt className="shrink-0 uppercase tracking-[0.12em] text-fg-dim">schema</dt>
                <dd className="break-all text-fg">{compare.schema_version}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="shrink-0 uppercase tracking-[0.12em] text-fg-dim">metrics</dt>
                <dd className="break-all text-fg">{compare.metric_implementation}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="shrink-0 uppercase tracking-[0.12em] text-fg-dim">model family</dt>
                <dd className="break-all text-fg">{compare.sources.model.probability_family}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="shrink-0 uppercase tracking-[0.12em] text-fg-dim">simulation family</dt>
                <dd className="break-all text-fg">{compare.sources.simulation.probability_family}</dd>
              </div>
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

export function UncertaintyView() {
  const { anchorId, selectAnchor, view, retry } = useUncertainty();
  const ids: DemoAnchorId[] = ["supported", "sim-ineligible", "excluded-2025"];

  return (
    <main className="mx-auto max-w-7xl space-y-4 px-4 py-4 sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b-2 border-ink-600 pb-3">
        <div>
          <h1 className="font-display text-lg font-extrabold uppercase tracking-[-0.02em] text-fg">
            Uncertainty · Model × Simulation × Sampling
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
            Loading uncertainty bundle…
          </p>
        </Panel>
      )}

      {view.kind === "result" && (
        <>
          <p className="font-data text-[11px] uppercase tracking-[0.14em] text-fg-dim">
            {DEMO_ANCHORS[anchorId].note}
          </p>
          <ResultView compare={view.compare} />
        </>
      )}

      {view.kind === "not-comparable" && (
        <Panel>
          <PanelHeader title="Comparison not comparable" meta={statusLabel(view.availability.comparison)} />
          <div className="space-y-2 px-4 py-4">
            <p className="font-ui text-[13px] text-fg">
              Model: {statusLabel(view.availability.model)} · Simulation:{" "}
              {statusLabel(view.availability.simulation)} · Sensitivity:{" "}
              {statusLabel(view.availability.simulator_sensitivity)}
            </p>
            <p className="font-data text-[12px] leading-6 text-fg-dim">
              {refusalCopy(view.reason)} No disagreement is rendered because
              both sources are required. Simulation is not shown as 0%.
              Simulator sensitivity remains not established, not hidden.
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
              2025 is unsupported for this product evidence — not zero
              uncertainty, not missing data. No fallback state is substituted
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
