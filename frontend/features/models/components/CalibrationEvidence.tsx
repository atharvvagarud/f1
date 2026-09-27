// 05 / CALIBRATION — development-only RAW/Platt/Isotonic comparison.
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";
import { fmt4 } from "@/features/models/components/format";

const METHOD_ORDER = ["RAW", "PLATT", "ISOTONIC"] as const;

export function CalibrationEvidence({
  evidence,
}: {
  evidence: ModelsEvidence;
}) {
  const cal = evidence.calibration_evidence;
  return (
    <ModelSection
      index="05 / Calibration"
      title="Development evidence — RAW retained"
      labelledBy="models-calibration"
      meta={`Development-only · ${cal.metric} · ${cal.population}`}
      note="Holdout ECE stays in the holdout section as evaluation evidence and is not mixed into this selection table. RAW was retained under the predeclared development rule; it was not chosen on 2025 results."
    >
      <div className="overflow-x-auto border border-ink-700">
        <table className="w-full min-w-[560px] text-left">
          <thead>
            <tr className="border-b border-ink-600 bg-ink-850">
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Method
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
                Mean
              </th>
            </tr>
          </thead>
          <tbody>
            {METHOD_ORDER.map((method) => {
              const entry = cal.methods[method];
              const frozen = method === cal.selected_method;
              return (
                <tr
                  key={method}
                  className="border-b border-ink-700 text-[12px] last:border-b-0"
                >
                  <th
                    scope="row"
                    className="px-3 py-2 font-ui text-[12px] font-semibold text-fg"
                  >
                    {method}
                    {frozen ? (
                      <span className="ml-2 border border-signal/60 px-1 py-px font-data text-[10px] uppercase tracking-[0.1em] text-fg">
                        RAW — frozen
                      </span>
                    ) : null}
                  </th>
                  <td
                    className="px-3 py-2 text-right font-data tabular-nums text-fg"
                    title={String(entry.per_fold.D1)}
                  >
                    {fmt4(entry.per_fold.D1)}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-data tabular-nums text-fg"
                    title={String(entry.per_fold.D2)}
                  >
                    {fmt4(entry.per_fold.D2)}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-data tabular-nums text-fg"
                    title={String(entry.per_fold.D3)}
                  >
                    {fmt4(entry.per_fold.D3)}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-data font-semibold tabular-nums text-fg"
                    title={String(entry.mean)}
                  >
                    {fmt4(entry.mean)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-2 break-all font-data text-[11px] leading-5 text-fg-dim">
        Selection rule: {cal.selection_rule}. Verdict from frozen evidence:
        RAW retained; neither calibrator improved development probability
        quality under the predeclared rule.
      </p>
    </ModelSection>
  );
}
