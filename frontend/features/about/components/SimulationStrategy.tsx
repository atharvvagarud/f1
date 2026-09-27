// 08 / SIMULATION PLUS STRATEGY — Monte Carlo kept separate from the
// prediction model, and strategy rendered as paired comparison only.
// Comparison vocabulary with no endorsement, optimality, or
// guaranteed-improvement language: the contract authorizes the outcome
// labels and a does-not of automatic optimization.
import type { AboutEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

const STRATEGY_OUTCOMES = [
  "IMPROVEMENT",
  "DEGRADATION",
  "INCONCLUSIVE",
  "UNAVAILABLE",
] as const;

export function SimulationStrategy({
  evidence,
}: {
  evidence: AboutEvidence;
}) {
  const monteCarlo = evidence.capabilities.find(
    (capability) => capability.id === "MONTE_CARLO",
  );
  const strategy = evidence.capabilities.find(
    (capability) => capability.id === "STRATEGY",
  );
  const seeds = evidence.reproducibility.deterministic_seeds;
  return (
    <ModelSection
      index="08 / Simulation plus strategy"
      title="Monte Carlo and paired strategy comparison"
      labelledBy="about-simulation-strategy"
      note="Simulation frequencies and prediction probabilities are different semantics. Strategy compares a candidate action against a baseline; it does not select or endorse one."
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="border border-ink-600 bg-ink-850 px-3 py-3">
          <p className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
            S3 / Simulation
          </p>
          <h3 className="mt-0.5 font-display text-[14px] font-bold uppercase tracking-[0.08em] text-fg">
            Stochastic simulation
          </h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] leading-5 text-fg-muted">
            <li>Initial condition taken from historical state at time T.</li>
            <li>Stochastic trajectories generate simulated race futures.</li>
            <li>
              Outcomes are mutually exclusive simulated finishing orders.
            </li>
            <li>
              Reported figures are Monte Carlo frequencies
              (MUTUALLY_EXCLUSIVE_FREQUENCY), not model probabilities.
            </li>
            <li>
              Runs use deterministic seeds (
              {seeds.map(String).join(", ")}) for repeatability.
            </li>
          </ul>
          {monteCarlo ? (
            <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
              {monteCarlo.does} Does not: {monteCarlo.does_not}
            </p>
          ) : null}
        </div>
        <div className="border border-ink-600 bg-ink-850 px-3 py-3">
          <p className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
            S4 / Strategy
          </p>
          <h3 className="mt-0.5 font-display text-[14px] font-bold uppercase tracking-[0.08em] text-fg">
            Paired intervention comparison
          </h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[12px] leading-5 text-fg-muted">
            <li>A single candidate decision at time T.</li>
            <li>Baseline versus intervention under common random numbers.</li>
            <li>Paired deltas with uncertainty intervals.</li>
            <li>Comparison only — never an endorsed or selected action.</li>
          </ul>
          <p className="mt-2 font-data text-[11px] uppercase tracking-[0.1em] text-fg-dim">
            Outcome vocabulary
          </p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {STRATEGY_OUTCOMES.map((outcome) => (
              <li
                key={outcome}
                className="border border-ink-600 px-1.5 py-0.5 font-data text-[11px] uppercase tracking-[0.1em] text-fg"
              >
                {outcome}
              </li>
            ))}
          </ul>
          {strategy ? (
            <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
              {strategy.does} Does not: {strategy.does_not} Strategy v1
              scope: one decision point, paired comparison, associational
              evidence only.
            </p>
          ) : null}
        </div>
      </div>
    </ModelSection>
  );
}
