// 02 / SYSTEM SEMANTICS — the most important section of /about.
//
// Four contract-defined concepts rendered as text-distinct panels. Each
// panel carries its id, display name, definition, probability semantics
// where the contract defines one, and an explicit not-to-confuse-with
// line. Distinction never relies on color alone.
import type { AboutEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

const SEMANTIC_INDEX: Record<string, string> = {
  FACT: "S1",
  PREDICTION: "S2",
  SIMULATION: "S3",
  STRATEGY: "S4",
};

export function SystemSemantics({ evidence }: { evidence: AboutEvidence }) {
  return (
    <ModelSection
      index="02 / System semantics"
      title="Fact, prediction, simulation, strategy"
      labelledBy="about-semantics"
      note="Four different meanings of system output. They share no chart axis, and the word probability is never used here without its qualifier."
    >
      <ol className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {evidence.system_semantics.map((semantic) => (
          <li
            key={semantic.id}
            className="border border-ink-600 bg-ink-850 px-3 py-3"
          >
            <p className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
              {SEMANTIC_INDEX[semantic.id]} / {semantic.id}
            </p>
            <h3 className="mt-0.5 font-display text-[15px] font-bold uppercase tracking-[0.08em] text-fg">
              {semantic.display_name}
            </h3>
            <p className="mt-1 text-[13px] leading-6 text-fg-muted">
              {semantic.definition}
            </p>
            {semantic.probability_semantics ? (
              <p className="mt-2 inline-block border border-ink-600 px-1.5 py-0.5 font-data text-[11px] uppercase tracking-[0.1em] text-fg">
                {semantic.probability_semantics}
              </p>
            ) : null}
            <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
              Not to confuse with: {semantic.not_to_confuse_with.join(", ")}
            </p>
          </li>
        ))}
      </ol>
      <div className="mt-3 border border-ink-700 px-3 py-3">
        <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
          How the four relate
        </h3>
        <ol className="mt-2 space-y-1.5 font-data text-[12px] leading-6 text-fg">
          <li>
            <span className="font-semibold">FACT</span>
            <span aria-hidden="true"> → </span>
            <span className="font-semibold">PREDICTION</span>
            <span className="text-fg-dim">
              {" "}
              — historical state at time T is scored by the frozen winner
              estimator.
            </span>
          </li>
          <li>
            <span className="font-semibold">FACT</span>
            <span aria-hidden="true"> → </span>
            <span className="font-semibold">SIMULATION</span>
            <span aria-hidden="true"> → </span>
            <span className="font-semibold">STRATEGY COMPARISON</span>
            <span className="text-fg-dim">
              {" "}
              — historical truth supplies the simulation initial condition;
              stochastic future trajectories produce mutually exclusive
              simulated finishing outcomes for paired comparison.
            </span>
          </li>
        </ol>
        <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
          The frozen winner probabilities are not fed into the Monte Carlo
          engine. Prediction probability (independent-binary per driver) and
          simulation frequency (share of mutually exclusive simulated
          outcomes) are different probability semantics and are never mixed.
        </p>
      </div>
    </ModelSection>
  );
}
