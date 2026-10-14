// Selected-driver region (V3.10C shell + V3.10E intelligence).
//
// Responds only to workspace.selectedDriverId: frame facts (position, gaps,
// tyre, stint, pit stops) plus compact model × simulation intelligence for
// the selected driver from the frozen uncertainty bundle at this state's
// anchor. The bundle serves every driver; switching drivers slices locally.
// DETAILS carries ranks, precision, limitation, and provenance — never a
// verdict, never a blend, never a recommendation.

"use client";

import Link from "next/link";
import { readableDriverId } from "@/features/replay/components/StandingsTable";
import type { DriverRaceState } from "@/lib/v2";
import { selectedDriverFacts } from "@/features/pit-wall/lib/driverFacts";
import { DriverTelemetry } from "@/features/pit-wall/components/DriverTelemetry";
import { selectDriverIntelligence } from "@/features/pit-wall/lib/driverIntelligence";
import type { DriverIntelligenceView } from "@/features/pit-wall/hooks/useDriverIntelligence";
import { WilsonViz } from "@/features/uncertainty/components/UncertaintyView";
import {
  formatBound,
  formatCount,
  formatProb,
  formatRank,
  formatSE,
  formatSignedGap,
  gapDirection,
  leaderWording,
  readableUncertaintyDriver,
  refusalCopy,
  statusLabel,
} from "@/features/uncertainty/lib/uncertaintyFormat";

const labelClass =
  "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className={labelClass}>{label}</div>
      <div className="mt-1 font-data text-[15px] text-fg tabular-nums">
        {value}
      </div>
    </div>
  );
}

export function DriverPanel({
  drivers,
  selectedDriverId,
  onSelect,
  onClear,
  intelligence,
  expertHrefs,
  telemetry,
}: {
  drivers: DriverRaceState[];
  selectedDriverId: string | null;
  onSelect: (driverId: string) => void;
  onClear: () => void;
  intelligence: DriverIntelligenceView;
  expertHrefs: { consensus: string; uncertainty: string } | null;
  /**
   * V3.10F telemetry context. Null while the frame is unavailable; the
   * telemetry disclosures render only for a selected driver with a clock.
   */
  telemetry: {
    raceId: string;
    tS: number;
    leaderLap: number | null;
    raceComplete: boolean;
  } | null;
}) {
  const facts = selectedDriverFacts(drivers, selectedDriverId);
  const sorted = [...drivers].sort((a, b) =>
    a.driver_id < b.driver_id ? -1 : 1,
  );

  return (
    <section aria-label="Selected driver" className="min-w-0">
      <h2 className="font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg">
        Driver
      </h2>

      <div className="mt-3 flex min-w-0 flex-col gap-1.5">
        <label
          htmlFor="pitwall-driver"
          className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim"
        >
          Selected driver
        </label>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <select
            id="pitwall-driver"
            className="h-11 min-w-0 flex-1 border border-ink-700 bg-ink-950 px-2.5 font-data text-[13px] text-fg transition-colors focus-visible:border-ink-600 disabled:cursor-not-allowed disabled:text-fg-dim"
            value={selectedDriverId ?? ""}
            disabled={drivers.length === 0}
            onChange={(event) => {
              const next = event.target.value;
              if (next) onSelect(next);
              else onClear();
            }}
          >
            <option value="">Select a driver</option>
            {sorted.map((driver) => (
              <option key={driver.driver_id} value={driver.driver_id}>
                {readableDriverId(driver.driver_id)}
              </option>
            ))}
          </select>
          {selectedDriverId !== null ? (
            <button
              type="button"
              onClick={onClear}
              className="h-11 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
            >
              Clear
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-4">
        {facts.status === "unselected" ? (
          <p className="font-data text-[12px] leading-5 text-fg-dim">
            Select a driver to read position, gap, tyre, and model ×
            simulation intelligence at this frame.
          </p>
        ) : facts.status === "no-evidence" ? (
          <p className="font-data text-[12px] leading-5 text-fg-dim">
            {readableDriverId(facts.driverId ?? "")} has no observed data at
            this frame. The selection is kept — nothing is substituted.
          </p>
        ) : (
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3">
            <Fact label="Position" value={facts.position} />
            <Fact label="Gap leader" value={facts.gapToLeader} />
            <Fact label="Gap ahead" value={facts.gapToAhead} />
            <Fact label="Tyre" value={facts.tyre} />
            <Fact label="Stint" value={facts.stint} />
            <Fact label="Pit stops" value={facts.pitStops} />
          </dl>
        )}
      </div>

      {selectedDriverId !== null ? (
        <DriverIntelligence
          driverId={selectedDriverId}
          intelligence={intelligence}
          expertHrefs={expertHrefs}
        />
      ) : null}

      {selectedDriverId !== null && telemetry !== null ? (
        <DriverTelemetry
          raceId={telemetry.raceId}
          driverId={selectedDriverId}
          drivers={drivers}
          tS={telemetry.tS}
          leaderLap={telemetry.leaderLap}
          raceComplete={telemetry.raceComplete}
        />
      ) : null}
    </section>
  );
}

/**
 * Compact model × simulation intelligence for the selected driver (V3.10E).
 *
 * L0: MODEL / SIM / Δ plus a finite-sampling precision line — values only,
 * rendered verbatim from the frozen bundle. DETAILS: ranks, leader
 * disagreement, Wilson interval, U3 limitation, probability families, and
 * expert deep links. Refusals render as status, never as zeros; disagreement
 * is information, never a source verdict.
 */
function DriverIntelligence({
  driverId,
  intelligence,
  expertHrefs,
}: {
  driverId: string;
  intelligence: DriverIntelligenceView;
  expertHrefs: { consensus: string; uncertainty: string } | null;
}) {
  const { view, retry } = intelligence;
  const name = readableUncertaintyDriver(driverId);

  if (view.kind === "loading") {
    return (
      <p
        aria-live="polite"
        className="mt-4 font-data text-[12px] leading-5 text-fg-dim"
      >
        Loading intelligence…
      </p>
    );
  }

  if (view.kind === "error") {
    return (
      <div className="mt-4">
        <p className="font-data text-[12px] leading-5 text-fg-dim">
          Intelligence request failed.
        </p>
        <button
          type="button"
          onClick={retry}
          className="mt-2 h-9 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
        >
          Retry intelligence
        </button>
      </div>
    );
  }

  if (view.kind === "unsupported") {
    return (
      <p className="mt-4 font-data text-[12px] leading-5 text-fg-dim">
        {refusalCopy(view.reason)}
      </p>
    );
  }

  if (view.kind === "not-comparable") {
    const availability = view.availability;
    const reason =
      availability.simulation !== "AVAILABLE"
        ? (availability.simulation_reason ?? availability.simulation)
        : (availability.model_reason ?? availability.model);
    return (
      <div className="mt-4">
        <p className="font-data text-[12px] leading-5 text-fg-dim">
          Model × simulation unavailable at this state — {reason} Missing is
          not zero.
        </p>
        <ExpertLinks expertHrefs={expertHrefs} />
      </div>
    );
  }

  const slice = selectDriverIntelligence(view.compare, driverId);
  const evidence = slice.driver;
  if (!evidence) {
    return (
      <div className="mt-4">
        <p className="font-data text-[12px] leading-5 text-fg-dim">
          No model × simulation evidence for {name} at this state. The
          selection is kept — nothing is substituted.
        </p>
        <ExpertLinks expertHrefs={expertHrefs} />
      </div>
    );
  }

  const sampling = evidence.sampling;
  return (
    <div className="mt-4 border-t border-ink-700 pt-3">
      {evidence.pModel !== null &&
      evidence.pSimulation !== null &&
      evidence.signedGap !== null ? (
        <dl className="grid grid-cols-3 gap-x-4">
          <Fact label="Model" value={formatProb(evidence.pModel) ?? "—"} />
          <Fact
            label="Simulation"
            value={formatProb(evidence.pSimulation) ?? "—"}
          />
          <Fact
            label="Difference"
            value={formatSignedGap(evidence.signedGap) ?? "—"}
          />
        </dl>
      ) : (
        <p className="font-data text-[12px] leading-5 text-fg-dim">
          {statusLabel(evidence.status)}
          {evidence.missingArm
            ? ` — missing ${evidence.missingArm}`
            : ""}
          . Missing is not zero.
        </p>
      )}
      {sampling ? (
        <p className="mt-2 font-data text-[11px] tabular-nums text-fg-dim">
          n={formatCount(sampling.validFuturesN)} · 95% [
          {formatBound(sampling.wilsonLower)},{" "}
          {formatBound(sampling.wilsonUpper)}]
        </p>
      ) : null}

      <details className="mt-3 border-t border-ink-700 pt-3">
        <summary className="cursor-pointer font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted focus-visible:outline-2 focus-visible:outline-focus">
          Details
        </summary>
        <div className="mt-3 space-y-3">
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            <Fact
              label="Model rank"
              value={formatRank(evidence.modelRank)}
            />
            <Fact
              label="Simulation rank"
              value={formatRank(evidence.simulationRank)}
            />
          </dl>
          <p className="font-data text-[12px] leading-5 text-fg-dim">
            {leaderWording(slice.bundle.leaderAgree)}:{" "}
            {slice.bundle.leaderModel
              ? readableUncertaintyDriver(slice.bundle.leaderModel)
              : "—"}{" "}
            vs{" "}
            {slice.bundle.leaderSimulation
              ? readableUncertaintyDriver(slice.bundle.leaderSimulation)
              : "—"}
            {evidence.signedGap !== null
              ? ` · ${gapDirection(evidence.signedGap)}`
              : ""}
            . Disagreement is information, not a verdict on either source.
          </p>
          {sampling ? (
            <div>
              <WilsonViz
                driverId={driverId}
                pHat={sampling.pHat}
                lower={sampling.wilsonLower}
                upper={sampling.wilsonUpper}
                n={sampling.validFuturesN}
                k={sampling.successCountK}
              />
              <p className="mt-1 font-data text-[11px] tabular-nums text-fg-dim">
                SE {formatSE(sampling.standardError)} · {sampling.precisionLabel === "FINITE_MC_SAMPLING_CONTEXT_ONLY" ? "finite-sampling precision only" : sampling.precisionLabel}
              </p>
            </div>
          ) : null}
          <p className="font-data text-[12px] leading-5 text-fg-dim">
            Simulator sensitivity:{" "}
            {statusLabel(slice.bundle.sensitivityStatus)} —{" "}
            {slice.bundle.sensitivityReason}
          </p>
          <p className="font-data text-[11px] leading-5 text-fg-dim">
            MODEL {slice.bundle.modelFamily} · SIMULATION{" "}
            {slice.bundle.simulationFamily} — shown side by side, never
            blended.
          </p>
          <ExpertLinks expertHrefs={expertHrefs} />
        </div>
      </details>
    </div>
  );
}

function ExpertLinks({
  expertHrefs,
}: {
  expertHrefs: { consensus: string; uncertainty: string } | null;
}) {
  if (!expertHrefs) return null;
  const linkClass =
    "font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted underline decoration-ink-600 underline-offset-4 transition-colors hover:text-fg focus-visible:outline-2 focus-visible:outline-focus";
  return (
    <p className="flex flex-wrap gap-x-4 gap-y-1 pt-1">
      <Link href={expertHrefs.consensus} className={linkClass}>
        Expert: consensus
      </Link>
      <Link href={expertHrefs.uncertainty} className={linkClass}>
        Expert: uncertainty
      </Link>
    </p>
  );
}
