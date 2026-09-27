// /models page header: dense telemetry strip, not KPI cards.
import type { ModelsEvidence } from "@/features/models/lib/evidence";

function StripCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 px-3 py-2">
      <div className="font-data text-[10px] uppercase tracking-[0.16em] text-fg-dim">
        {label}
      </div>
      <div
        className="mt-0.5 truncate font-data text-[12px] font-semibold text-fg tabular-nums"
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

export function ModelHeader({ evidence }: { evidence: ModelsEvidence }) {
  const spec = evidence.model_spec;
  return (
    <header className="border-b-2 border-ink-600 pb-4">
      <p className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-muted">
        Models
      </p>
      <h1 className="mt-1 font-display text-2xl font-bold tracking-tight text-fg">
        Winner model / validation lab
      </h1>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
        Frozen record of the serving winner model, its temporal evaluation,
        2025 holdout evidence, calibration, feature system, and global model
        evidence. Presentation only — nothing here retrains or re-evaluates.
      </p>
      <dl className="mt-4 grid grid-cols-2 divide-ink-700 border border-ink-700 bg-ink-900 max-sm:divide-y sm:grid-cols-7 sm:divide-x sm:divide-y-0">
        <StripCell label="Task" value={spec.task} />
        <StripCell label="Winner" value={`${spec.estimator} C=${spec.C}`} />
        <StripCell
          label="Features"
          value={`${spec.canonical_feature_count}`}
        />
        <StripCell
          label="Transformed"
          value={`${spec.transformed_feature_count}`}
        />
        <StripCell label="Calibration" value={spec.calibration} />
        <StripCell label="Semantics" value={spec.probability_semantics} />
        <StripCell label="Holdout" value={`${spec.holdout_season}`} />
      </dl>
    </header>
  );
}
