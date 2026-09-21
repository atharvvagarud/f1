// Monte Carlo simulator results (Phase-6 R8).
//
// Renders the backend aggregate verbatim. Win/podium probabilities are
// MONTE_CARLO_FREQUENCY outcome frequencies — never normalized, never summed
// into a share. DNF/points stay "—" because those models are deferred.

"use client";

import { useMemo, useState } from "react";
import type { SimulationResponse } from "@/lib/v2";
import {
  formatCount,
  formatExpectedFinish,
  formatPercent,
  formatRuntime,
  sortDriversByWin,
  winMass,
} from "@/features/simulator/lib/simulatorMachine";

function FinishDistribution({
  driver,
}: {
  driver: SimulationResponse["drivers"][number];
}) {
  const field = driver.finish_position_distribution;
  return (
    <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
      {field.map((bucket) => (
        <div
          key={String(bucket.position)}
          className="flex items-center justify-between gap-2 text-xs text-slate-400"
        >
          <span>{bucket.position === null ? "DNF" : `P${bucket.position}`}</span>
          <span className="font-mono text-slate-200">
            {formatPercent(bucket.frequency)}
          </span>
        </div>
      ))}
    </div>
  );
}

export function SimulationResults({ response }: { response: SimulationResponse }) {
  const ordered = useMemo(
    () => sortDriversByWin(response.drivers),
    [response.drivers],
  );
  const [expanded, setExpanded] = useState<string | null>(null);
  const mass = winMass(response.drivers);

  return (
    <section
      aria-label="Simulation results"
      className="rounded-lg border border-white/10 bg-slate-900/40 p-4"
    >
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-heading text-sm font-bold uppercase tracking-[0.16em] text-slate-300">
          Simulated outcome frequencies
        </h2>
        <p className="text-xs text-slate-400">
          {formatCount(response.valid_simulations)} valid /{" "}
          {formatCount(response.requested_simulation_count)} requested · seed{" "}
          {response.master_seed} · {formatRuntime(response.engine_runtime_s)}{" "}
          engine
        </p>
      </div>

      <p className="mb-3 text-xs text-slate-500">
        {response.probability_semantics} — empirical outcome frequencies over
        valid trials, not Phase-3 independent binary winner probabilities.
        Winner mass over the field: {formatPercent(mass)}. DNF and points are
        not modelled.
      </p>

      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-slate-500">
            <th className="py-2 pr-3 font-semibold">Driver</th>
            <th className="py-2 pr-3 text-right font-semibold">Win</th>
            <th className="py-2 pr-3 text-right font-semibold">Podium</th>
            <th className="py-2 pr-3 text-right font-semibold">Exp. finish</th>
            <th className="py-2 text-right font-semibold">DNF / Pts</th>
          </tr>
        </thead>
        <tbody>
          {ordered.map((driver) => (
            <tr key={driver.driver_id} className="border-b border-white/5 align-top">
              <td className="py-2 pr-3">
                <button
                  type="button"
                  className="text-left font-medium text-slate-100 hover:text-red-400"
                  onClick={() =>
                    setExpanded((current) =>
                      current === driver.driver_id ? null : driver.driver_id,
                    )
                  }
                  aria-expanded={expanded === driver.driver_id}
                >
                  {driver.driver_id}
                </button>
                {expanded === driver.driver_id && (
                  <FinishDistribution driver={driver} />
                )}
              </td>
              <td className="py-2 pr-3 text-right font-mono text-slate-100">
                {formatPercent(driver.win_probability)}
              </td>
              <td className="py-2 pr-3 text-right font-mono text-slate-200">
                {formatPercent(driver.podium_probability)}
              </td>
              <td className="py-2 pr-3 text-right font-mono text-slate-200">
                {formatExpectedFinish(driver.expected_finish)}
              </td>
              <td className="py-2 text-right font-mono text-slate-500">
                {driver.dnf_probability === null ? "—" : formatPercent(driver.dnf_probability)}{" "}
                / {driver.expected_points === null ? "—" : driver.expected_points}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-3 text-[11px] text-slate-600">
        Parameter {response.parameter_version} · {response.monte_carlo_version} ·{" "}
        {response.pit_dynamics_version} · result{" "}
        {response.scientific_result_identity.slice(0, 16)}…
      </p>
    </section>
  );
}
