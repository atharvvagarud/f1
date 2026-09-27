// 04 / DEVELOPMENT EVIDENCE — dev-only candidate table (D1/D2/D3 visible,
// never merged with holdout) plus the frozen selection protocol.
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";
import { fmt4 } from "@/features/models/components/format";

const FROZEN_SERVING_VARIANT = "frozen-global C=0.01 outer (M7)";

export function DevelopmentComparison({
  evidence,
}: {
  evidence: ModelsEvidence;
}) {
  const dev = evidence.development_evidence;
  const selection = evidence.model_selection;
  return (
    <ModelSection
      index="04 / Development evidence"
      title="Development-only candidate comparison"
      labelledBy="models-development"
      meta={`Protocol ${dev.protocol} · ${dev.metric} dev means · ${dev.warning}`}
      note="Inter-fold variance is real: read the D1/D2/D3 columns, not the mean alone. This table never includes holdout values and carries no ranking."
    >
      <div className="overflow-x-auto border border-ink-700">
        <table className="w-full min-w-[860px] text-left">
          <thead>
            <tr className="border-b border-ink-600 bg-ink-850">
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Model
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Variant
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-right font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                D1
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-right font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                D2
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-right font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                D3
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-right font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Dev mean
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Protocol
              </th>
            </tr>
          </thead>
          <tbody>
            {dev.candidates.map((candidate) => (
              <tr
                key={`${candidate.family}__${candidate.variant}`}
                className="border-b border-ink-700 text-[12px] last:border-b-0"
              >
                <th
                  scope="row"
                  className="px-3 py-2 font-ui text-[12px] font-semibold text-fg"
                >
                  {candidate.family}
                  {candidate.variant === FROZEN_SERVING_VARIANT ? (
                    <span className="ml-2 border border-signal/60 px-1 py-px font-data text-[10px] uppercase tracking-[0.1em] text-fg">
                      Frozen serving choice
                    </span>
                  ) : null}
                </th>
                <td className="px-3 py-2 text-[12px] text-fg-muted">
                  {candidate.variant}
                </td>
                <td
                  className="px-3 py-2 text-right font-data tabular-nums text-fg"
                  title={String(candidate.development_log_loss.per_fold.D1)}
                >
                  {fmt4(candidate.development_log_loss.per_fold.D1)}
                </td>
                <td
                  className="px-3 py-2 text-right font-data tabular-nums text-fg"
                  title={String(candidate.development_log_loss.per_fold.D2)}
                >
                  {fmt4(candidate.development_log_loss.per_fold.D2)}
                </td>
                <td
                  className="px-3 py-2 text-right font-data tabular-nums text-fg"
                  title={String(candidate.development_log_loss.per_fold.D3)}
                >
                  {fmt4(candidate.development_log_loss.per_fold.D3)}
                </td>
                <td
                  className="px-3 py-2 text-right font-data font-semibold tabular-nums text-fg"
                  title={String(candidate.development_log_loss.mean)}
                >
                  {fmt4(candidate.development_log_loss.mean)}
                </td>
                <td className="px-3 py-2 font-data text-[11px] text-fg-muted">
                  {dev.protocol}
                  <span className="block text-fg-dim">
                    {candidate.limitation}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 border border-ink-600 bg-ink-850 px-3 py-2">
        <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.18em] text-fg">
          Selection protocol
        </h3>
        <dl className="mt-2 space-y-2 text-[12px] leading-5">
          <div>
            <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              Serving choice
            </dt>
            <dd className="font-data text-fg">{selection.serving_choice}</dd>
          </div>
          <div>
            <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              Selection rule
            </dt>
            <dd className="text-fg-muted">{selection.selection_rule}</dd>
          </div>
          <div>
            <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              Measured evidence
            </dt>
            <dd>
              <ul className="list-disc space-y-1 pl-5 text-fg-muted">
                {selection.measured_evidence.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </dd>
          </div>
          <div>
            <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              Engineering context
            </dt>
            <dd className="text-fg-muted">{selection.engineering_context}</dd>
          </div>
          <div>
            <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              Limitations
            </dt>
            <dd className="text-fg-muted">{selection.limitations}</dd>
          </div>
        </dl>
      </div>
    </ModelSection>
  );
}
