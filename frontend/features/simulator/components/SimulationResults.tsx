// Monte Carlo simulator results (Phase-6 R8; UI4 outcome workstation).
//
// Renders the backend aggregate verbatim, in the frozen information order:
// empirical outcome summary → field outcome frequencies → finishing-position
// distribution → model provenance/limitations. Win/podium values are
// MONTE_CARLO_FREQUENCY outcome frequencies; they are never normalized, summed
// into a share, or blended with Phase-3 independent binary probabilities.
// DNF/points stay "—" because those models are deferred.

"use client";

import { useMemo } from "react";
import type { SimulationResponse } from "@/lib/v2";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { PositionDistribution } from "@/features/simulator/components/PositionDistribution";
import {
  formatCount,
  formatExpectedFinish,
  formatPercent,
  formatRuntime,
  mostFrequentWinner,
  sortDriversByWin,
  winMass,
} from "@/features/simulator/lib/simulatorMachine";
import {
  Panel,
  PanelHeader,
  ProbabilityBar,
  SemanticsNote,
  Stat,
} from "@/components/ui/Panel";

function ProvenanceFact({
  label,
  value,
  title,
}: {
  label: string;
  value: string;
  title?: string;
}) {
  return (
    <div className="min-w-0 border-t border-ink-700 px-4 py-2.5">
      <div className="text-[10px] uppercase tracking-[0.14em] text-fg-dim">
        {label}
      </div>
      <div
        className="mt-1 truncate font-data text-[12px] text-fg tabular-nums"
        title={title}
      >
        {value}
      </div>
    </div>
  );
}

export function SimulationResults({ response }: { response: SimulationResponse }) {
  const ordered = useMemo(
    () => sortDriversByWin(response.drivers),
    [response.drivers],
  );
  const winner = useMemo(
    () => mostFrequentWinner(response.drivers),
    [response.drivers],
  );
  const mass = winMass(response.drivers);

  return (
    <div className="mt-4 flex flex-col gap-4">
      <Panel>
        <PanelHeader
          title="Simulated outcome summary"
          meta={`${formatCount(response.valid_simulations)} valid trials · seed ${response.master_seed}`}
          note="Empirical frequencies over valid simulated trials from the exact anchor above."
        />

        <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-4 px-4 py-4">
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.16em] text-fg-dim">
              Most frequent simulated winner
            </p>
            <p className="mt-1 font-display text-3xl font-extrabold tracking-[-0.03em] text-fg sm:text-4xl">
              {winner ? readableDriverId(winner.driver_id) : "—"}
            </p>
            <p className="mt-1.5 font-data text-[11px] tracking-[0.08em] text-fg-muted">
              {winner?.driver_id ?? "—"} · {response.race_id} · anchor lap{" "}
              {response.anchor_lap_number}
            </p>
            {winner ? (
              <p className="mt-2 font-data text-[12px] text-fg-muted tabular-nums">
                Podium{" "}
                <span className="text-fg">
                  {formatPercent(winner.podium_probability)}
                </span>
                {" · "}Expected finish{" "}
                <span className="text-fg">
                  {formatExpectedFinish(winner.expected_finish)}
                </span>
              </p>
            ) : null}
          </div>

          <div className="w-full min-w-0 max-w-xs shrink-0 sm:w-auto sm:text-right">
            <p className="font-data text-4xl font-bold tracking-[-0.02em] text-fg tabular-nums sm:text-5xl">
              {formatPercent(winner?.win_probability ?? null)}
            </p>
            <p className="mt-1 text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              Win frequency over valid trials
            </p>
            <ProbabilityBar
              value={winner?.win_probability ?? 0}
              className="mt-2 w-full sm:w-52"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
          <Stat
            label="Valid simulations"
            value={formatCount(response.valid_simulations)}
            hint="Counted"
            className="border-t border-ink-700"
          />
          <Stat
            label="Invalid simulations"
            value={formatCount(response.invalid_simulations)}
            hint="Rejected"
            className="border-t border-ink-700"
          />
          <Stat
            label="Requested"
            value={formatCount(response.requested_simulation_count)}
            hint="Per run"
            className="border-t border-ink-700"
          />
          <Stat
            label="Winner mass"
            value={formatPercent(mass)}
            hint="Sums to 1"
            className="border-t border-ink-700"
          />
          <Stat
            label="Engine runtime"
            value={formatRuntime(response.engine_runtime_s)}
            hint="Full run"
            className="border-t border-ink-700"
          />
        </div>

        <div className="border-t border-ink-700 bg-ink-950/50 px-4 py-3">
          <SemanticsNote>
            {response.probability_semantics} — {response.probability_semantics_note}
          </SemanticsNote>
        </div>
      </Panel>

      <Panel>
        <PanelHeader
          title="Field outcome frequencies"
          meta={`${response.drivers.length} drivers`}
          note="Win and podium are separate empirical outcomes over the same valid trials — not a combined score. Expected finish is a mean finishing position, not an integer place. DNF and points are not modelled in v1."
        />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[13px]">
            <caption className="sr-only">
              Field outcome frequencies. Each row is one driver with empirical
              win and podium frequencies, mean expected finish and the deferred
              DNF / points placeholders over the same valid trials.
            </caption>
            <thead>
              <tr className="border-b border-ink-700 text-[10px] uppercase tracking-[0.14em] text-fg-dim">
                <th scope="col" className="px-3 py-2 font-medium">#</th>
                <th scope="col" className="px-3 py-2 font-medium">Driver</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Win frequency
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Podium frequency
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Expected finish
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  DNF / points
                </th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((driver, index) => (
                <tr
                  key={driver.driver_id}
                  className="border-t border-ink-700 hover:bg-ink-850/60"
                >
                  <td className="px-3 py-2 font-data text-fg-dim tabular-nums">
                    {index + 1}
                  </td>
                  <th scope="row" className="px-3 py-2 text-left font-normal">
                    <span className="text-fg">
                      {readableDriverId(driver.driver_id)}
                    </span>
                    <span className="ml-2 font-data text-[11px] text-fg-dim">
                      {driver.driver_id}
                    </span>
                  </th>
                  <td className="px-3 py-2">
                    <span className="flex items-center justify-end gap-2">
                      <ProbabilityBar value={driver.win_probability} className="w-16" />
                      <span className="w-14 text-right font-data text-fg tabular-nums">
                        {formatPercent(driver.win_probability)}
                      </span>
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-data text-fg-muted tabular-nums">
                    {formatPercent(driver.podium_probability)}
                  </td>
                  <td className="px-3 py-2 text-right font-data text-fg-muted tabular-nums">
                    {formatExpectedFinish(driver.expected_finish)}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-data text-fg-dim tabular-nums"
                    title="Reliability and points are deferred in v1"
                  >
                    {driver.dnf_probability === null
                      ? "—"
                      : formatPercent(driver.dnf_probability)}{" "}
                    /{" "}
                    {driver.expected_points === null
                      ? "—"
                      : driver.expected_points}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border-t border-ink-700 bg-ink-950/50 px-4 py-3">
          <SemanticsNote>
            Order is by win frequency (deterministic), not user-sortable. The
            field is the exact contemporaneous roster reconstructed at the
            anchor; no driver is added or removed.
          </SemanticsNote>
        </div>
      </Panel>

      <PositionDistribution response={response} />

      <Panel>
        <PanelHeader
          title="Simulation model & provenance"
          meta={response.parameter_set_id}
          note="Returned by the Phase-6 service for this exact run; not inferred by the frontend."
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
          <ProvenanceFact
            label="Simulation contract"
            value={response.simulation_contract_version}
          />
          <ProvenanceFact label="Engine" value={response.engine_version} />
          <ProvenanceFact
            label="Monte Carlo"
            value={response.monte_carlo_version}
          />
          <ProvenanceFact
            label="Pit dynamics"
            value={response.pit_dynamics_version}
          />
          <ProvenanceFact
            label="Parameter version"
            value={response.parameter_version}
          />
          <ProvenanceFact
            label="Parameter hash"
            value={`${response.parameter_hash.slice(0, 16)}…`}
            title={response.parameter_hash}
          />
          <ProvenanceFact
            label="Simulation request id"
            value={`${response.simulation_request_identity.slice(0, 16)}…`}
            title={response.simulation_request_identity}
          />
          <ProvenanceFact
            label="Scientific result id"
            value={`${response.scientific_result_identity.slice(0, 16)}…`}
            title={response.scientific_result_identity}
          />
        </div>

        <div className="grid grid-cols-1 gap-x-6 gap-y-3 border-b border-ink-700 px-4 py-3 lg:grid-cols-2">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              Mechanics
            </div>
            <p className="mt-1 font-data text-[12px] text-fg">
              {response.mechanics.length > 0
                ? response.mechanics.join(" · ")
                : "—"}
            </p>
          </div>
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.14em] text-fg-dim">
              Runtime breakdown
            </div>
            <p className="mt-1 font-data text-[12px] text-fg-muted tabular-nums">
              reconstruct {formatRuntime(response.runtime.reconstruction_s)} ·
              adapt {formatRuntime(response.runtime.adaptation_s)} · simulate{" "}
              {formatRuntime(response.runtime.simulation_s)} · total{" "}
              {formatRuntime(response.runtime.total_s)}
            </p>
          </div>
        </div>

        <div className="border-b border-ink-700 px-4 py-3">
          <div className="text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            Provenance vocabulary
          </div>
          <p className="mt-1 font-data text-[11px] leading-5 text-fg-dim">
            The response does not expose a per-field provenance tag. These are
            the frozen engine&apos;s categories:
          </p>
          <div className="mt-2 grid grid-cols-1 gap-x-6 gap-y-1 text-[12px] leading-5 text-fg-dim sm:grid-cols-2">
            <span>
              <span className="font-data">FACTUAL_AT_T</span> — exact
              reconstructed state at T
            </span>
            <span>
              <span className="font-data">HISTORICALLY_ESTIMATED</span> —
              parameters estimated from history
            </span>
            <span>
              <span className="font-data">STOCHASTIC_DRAW</span> — quantities
              drawn per simulated trial
            </span>
            <span>
              <span className="font-data">USER_ASSUMPTION</span> — run
              configuration supplied by the user
            </span>
          </div>
          <SemanticsNote>
            ORACLE_EVALUATION_ONLY is a validation-only category and is never
            used in this production simulation.
          </SemanticsNote>
        </div>

        <div className="px-4 py-3">
          <div className="text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            Known limitations (v1)
          </div>
          <ul className="mt-2 space-y-1 text-[12px] leading-5 text-fg-dim">
            <li>Reliability / DNF and points are deferred — not modelled.</li>
            <li>Traffic and overtaking are deferred.</li>
            <li>
              Supported anchors are all-clear, dry and contemporaneous;
              neutralized, wet and non-contemporaneous states are rejected by
              the backend.
            </li>
            <li>Pit dynamics are empirical (r6-pit-dynamics-v1).</li>
          </ul>
        </div>
      </Panel>
    </div>
  );
}
