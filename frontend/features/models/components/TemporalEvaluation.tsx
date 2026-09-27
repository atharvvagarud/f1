// 03 / TEMPORAL EVALUATION — expanding-window fold matrix. 2025 is
// structurally isolated from development.
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

export function TemporalEvaluation({
  evidence,
}: {
  evidence: ModelsEvidence;
}) {
  const temporal = evidence.temporal_evaluation;
  return (
    <ModelSection
      index="03 / Temporal evaluation"
      title="Expanding-window development protocol"
      labelledBy="models-temporal"
      meta={`Protocol ${temporal.protocol} · train strictly before validation`}
      note="Development folds grow the training window one season at a time and touch each outer validation season once. The final fit uses all 2018–2024 data. The 2025 holdout was evaluated one-shot and is isolated from development."
    >
      <ol className="space-y-2">
        {temporal.development_folds.map((fold) => (
          <li
            key={fold.fold}
            className="grid grid-cols-[48px_1fr] items-stretch gap-0 border border-ink-700 max-sm:grid-cols-1"
          >
            <div className="flex items-center justify-center border-ink-700 bg-ink-850 px-2 py-2 font-data text-[12px] font-bold text-fg max-sm:justify-start sm:border-r">
              {fold.fold}
            </div>
            <div className="grid grid-cols-[1fr_auto] items-center gap-3 px-3 py-2 max-sm:grid-cols-1 max-sm:gap-1">
              <div>
                <p className="font-data text-[12px] text-fg">
                  <span className="border border-ink-600 bg-ink-950 px-1.5 py-0.5 uppercase tracking-[0.1em] text-fg-muted">
                    Train
                  </span>{" "}
                  <span className="tabular-nums">
                    {fold.train} · {fold.train_states.toLocaleString("en-US")}{" "}
                    states
                  </span>
                </p>
                <p className="mt-1.5 font-data text-[12px] text-fg">
                  <span className="border border-signal/60 bg-ink-950 px-1.5 py-0.5 uppercase tracking-[0.1em] text-fg">
                    Validate
                  </span>{" "}
                  <span className="tabular-nums">
                    {fold.validate} · {fold.val_states.toLocaleString("en-US")}{" "}
                    states
                  </span>
                </p>
              </div>
              <p className="font-data text-[11px] text-fg-dim tabular-nums">
                {fold.train} → {fold.validate}
              </p>
            </div>
          </li>
        ))}
        <li className="grid grid-cols-[48px_1fr] items-stretch gap-0 border border-ink-600 max-sm:grid-cols-1">
          <div className="flex items-center justify-center bg-ink-850 px-2 py-2 font-data text-[11px] font-bold uppercase text-fg max-sm:justify-start sm:border-r sm:border-ink-700">
            Fit
          </div>
          <p className="px-3 py-2 font-data text-[12px] text-fg">
            <span className="border border-ok/50 px-1.5 py-0.5 uppercase tracking-[0.1em]">
              Final fit
            </span>{" "}
            <span className="tabular-nums">
              {temporal.final_fit} · single all-data fit, no validation split
            </span>
          </p>
        </li>
        <li className="grid grid-cols-[48px_1fr] items-stretch gap-0 border-2 border-warn/60 max-sm:grid-cols-1">
          <div className="flex items-center justify-center bg-ink-850 px-2 py-2 font-data text-[11px] font-bold uppercase text-warn max-sm:justify-start sm:border-r sm:border-ink-700">
            Lock
          </div>
          <p className="px-3 py-2 font-data text-[12px] text-fg">
            <span className="border border-warn/60 px-1.5 py-0.5 uppercase tracking-[0.1em] text-warn">
              Holdout {temporal.holdout}
            </span>{" "}
            <span className="text-fg-muted">
              one-shot · unreachable from development paths
            </span>
          </p>
        </li>
      </ol>
      <div className="mt-3 border border-ink-700 px-3 py-2">
        <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.18em] text-fg-muted">
          Protocol guards
        </h3>
        <ul className="mt-1 list-disc space-y-1 pl-5 font-data text-[12px] leading-5 text-fg-muted">
          {temporal.guards.map((guard) => (
            <li key={guard}>{guard}</li>
          ))}
        </ul>
      </div>
    </ModelSection>
  );
}
