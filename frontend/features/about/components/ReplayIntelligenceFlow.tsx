// 07 / PREDICTION TO REPLAY — the product path from historical state to
// replay intelligence. Renders the frozen model identity (estimator,
// feature set, semantics) verbatim and keeps probability, local
// explanation, and change explanation as three distinct outputs.
import type {
  AboutEvidence,
  ModelsEvidence,
} from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

export function ReplayIntelligenceFlow({
  about,
  models,
}: {
  about: AboutEvidence;
  models: ModelsEvidence;
}) {
  const spec = models.model_spec;
  const intelligence = about.capabilities.find(
    (capability) => capability.id === "REPLAY_INTELLIGENCE",
  );
  const steps = [
    `Historical race state at time T`,
    `${spec.feature_set} feature materialization (${spec.canonical_feature_count} canonical features)`,
    `Frozen winner estimator (${spec.estimator})`,
    `Independent-binary probability per driver (${spec.probability_semantics})`,
    `Offline replay prediction cache`,
    `Probability timeline at prediction checkpoints`,
    `Local log-odds explanation of a single checkpoint`,
    `Checkpoint-to-checkpoint log-odds change explanation`,
  ];
  return (
    <ModelSection
      index="07 / Prediction to replay"
      title="From historical state to replay intelligence"
      labelledBy="about-replay-flow"
      note="Each step below restates frozen evidence; the page computes nothing. Local and change explanations are associational and model-internal, never causal."
    >
      <ol className="space-y-0 border border-ink-700">
        {steps.map((step, position) => (
          <li
            key={step}
            className="flex gap-3 border-ink-700 px-3 py-2 [&:not(:last-child)]:border-b"
          >
            <span className="font-data text-[12px] text-fg-dim tabular-nums">
              {String(position + 1).padStart(2, "0")}
            </span>
            <span className="font-data text-[12px] leading-6 text-fg">
              {step}
            </span>
          </li>
        ))}
      </ol>
      <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-3">
        <div className="border border-ink-600 bg-ink-850 px-3 py-2">
          <p className="font-data text-[11px] font-semibold uppercase tracking-[0.14em] text-fg">
            Probability
          </p>
          <p className="mt-1 text-[12px] leading-5 text-fg-muted">
            Independent estimates per driver (INDEPENDENT_BINARY), not
            expected to sum to 1.
          </p>
        </div>
        <div className="border border-ink-600 bg-ink-850 px-3 py-2">
          <p className="font-data text-[11px] font-semibold uppercase tracking-[0.14em] text-fg">
            Local explanation
          </p>
          <p className="mt-1 text-[12px] leading-5 text-fg-muted">
            Additive log-odds account of one checkpoint, not a causal
            account.
          </p>
        </div>
        <div className="border border-ink-600 bg-ink-850 px-3 py-2">
          <p className="font-data text-[11px] font-semibold uppercase tracking-[0.14em] text-fg">
            Change explanation
          </p>
          <p className="mt-1 text-[12px] leading-5 text-fg-muted">
            Log-odds movement between checkpoints at timeline granularity.
          </p>
        </div>
      </div>
      {intelligence ? (
        <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
          Replay Intelligence {intelligence.status}: {intelligence.does}{" "}
          Does not: {intelligence.does_not}
        </p>
      ) : null}
    </ModelSection>
  );
}
