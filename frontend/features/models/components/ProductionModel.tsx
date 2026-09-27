// 01 / PRODUCTION MODEL — exact frozen specification, verbatim.
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

function Row({ term, value }: { term: string; value: string }) {
  return (
    <div className="grid grid-cols-[160px_1fr] gap-3 border-b border-ink-700 py-1.5 last:border-b-0 max-sm:grid-cols-1 max-sm:gap-0.5">
      <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
        {term}
      </dt>
      <dd className="font-data text-[12px] text-fg tabular-nums">{value}</dd>
    </div>
  );
}

export function ProductionModel({ evidence }: { evidence: ModelsEvidence }) {
  const spec = evidence.model_spec;
  return (
    <ModelSection
      index="01 / Production model"
      title="Frozen serving specification"
      labelledBy="models-production"
      meta="One frozen specification · not a best-of-all-possible-models claim"
    >
      <div className="border border-ink-600 bg-ink-850 px-3 py-2">
        <p className="font-data text-[11px] uppercase tracking-[0.14em] text-fg-dim">
          Probability semantics
        </p>
        <p className="mt-1 font-display text-lg font-extrabold uppercase tracking-[0.06em] text-fg">
          {spec.probability_semantics}
        </p>
        <p className="mt-1 max-w-3xl text-[13px] leading-6 text-fg-muted">
          Each driver&apos;s winner probability is estimated independently.
          Values are not race shares and field probabilities are not expected
          to sum to 1.
        </p>
      </div>
      <dl className="mt-3">
        <Row term="Estimator" value={spec.estimator} />
        <Row term="Task" value={spec.task} />
        <Row term="Target" value={spec.target} />
        <Row term="Eligibility" value={spec.eligibility} />
        <Row term="C" value={String(spec.C)} />
        <Row term="Penalty" value={spec.penalty} />
        <Row term="Solver" value={spec.solver} />
        <Row term="Max iter" value={String(spec.max_iter)} />
        <Row term="Class weight" value={String(spec.class_weight)} />
        <Row term="Random state" value={String(spec.random_state)} />
        <Row
          term="Feature set"
          value={`${spec.feature_set} / ${spec.feature_version}`}
        />
        <Row
          term="Preprocessing"
          value={`${spec.canonical_feature_count} → ${spec.transformed_feature_count} (train-fitted only)`}
        />
        <Row term="Calibration" value={spec.calibration} />
        <Row term="Final-fit seasons" value={spec.final_fit_seasons} />
        <Row term="Holdout season" value={String(spec.holdout_season)} />
      </dl>
    </ModelSection>
  );
}
