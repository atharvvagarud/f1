// 07 / GLOBAL MODEL EVIDENCE — coefficients (LOG_ODDS, conditional
// association, never causal) and permutation evidence (visibly in-sample).
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

// Fixed display scales; bars are presentational against stated constants.
const COEF_SCALE = 1.1;
const PERM_SCALE = 0.03;

export function GlobalEvidence({ evidence }: { evidence: ModelsEvidence }) {
  const coef = evidence.coefficient_evidence;
  const perm = evidence.permutation_evidence;
  return (
    <ModelSection
      index="07 / Global model evidence"
      title="Coefficients + permutation evidence"
      labelledBy="models-global"
      note="Two evidence classes. Coefficient signs read on the standardized log-odds scale: negative is associated with lower model log-odds — not a verdict on strategy or driver quality, and never a causal claim."
    >
      <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.18em] text-fg-muted">
        Coefficient evidence — LOG_ODDS space
      </h3>
      <p className="mt-1 font-data text-[11px] leading-5 text-fg-dim">
        {coef.reading} Intercept {coef.intercept.toFixed(5)}. Conditional
        model association only.
      </p>
      <div className="mt-2 overflow-x-auto border border-ink-700">
        <table className="w-full min-w-[640px] text-left">
          <thead>
            <tr className="border-b border-ink-600 bg-ink-850">
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Canonical feature
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Family
              </th>
              <th
                scope="col"
                className="px-3 py-2 text-right font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Coefficient
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Direction
              </th>
            </tr>
          </thead>
          <tbody>
            {coef.top_by_abs.map((entry) => {
              const positive = entry.coefficient >= 0;
              return (
                <tr
                  key={entry.transformed}
                  className="border-b border-ink-700 text-[12px] last:border-b-0"
                >
                  <th
                    scope="row"
                    className="px-3 py-2 font-data text-[12px] text-fg"
                  >
                    {entry.canonical}
                    <span className="block text-[11px] text-fg-dim">
                      {entry.transformed}
                    </span>
                  </th>
                  <td className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.1em] text-fg-muted">
                    {entry.family}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-data tabular-nums text-fg"
                    title={String(entry.coefficient)}
                  >
                    {entry.coefficient >= 0 ? "+" : ""}
                    {entry.coefficient.toFixed(3)}
                  </td>
                  <td className="px-3 py-2">
                    <span
                      aria-hidden="true"
                      className="block h-1.5 w-24 bg-ink-850"
                    >
                      <span
                        className={`block h-full ${positive ? "bg-ok" : "bg-danger"}`}
                        style={{
                          width: `${(Math.abs(entry.coefficient) / COEF_SCALE) * 100}%`,
                        }}
                      />
                    </span>
                    <span className="mt-0.5 block font-data text-[10px] uppercase tracking-[0.1em] text-fg-muted">
                      {positive ? "Positive log-odds" : "Negative log-odds"}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="mt-5 border border-warn/60">
        <div className="border-b border-warn/60 bg-ink-850 px-3 py-2">
          <h3 className="font-data text-[11px] font-bold uppercase tracking-[0.18em] text-warn">
            Permutation evidence — PRE_2025_FINAL_FIT_IN_SAMPLE
          </h3>
          <p className="mt-1 font-data text-[11px] leading-5 text-fg-muted">
            {perm.evidence_class}: {perm.evidence_class_note} Unit{" "}{perm.permutation_unit} · metric {perm.metric}{" "}
            · {perm.repeats} repeats · seed {perm.base_seed} · baseline{" "}
            {perm.baseline_metric.toFixed(4)}.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left">
            <thead>
              <tr className="border-b border-ink-600 bg-ink-850">
                <th
                  scope="col"
                  className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                >
                  Canonical feature
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                >
                  Family
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-right font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                >
                  Mean Δ
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                >
                  Sensitivity
                </th>
                <th
                  scope="col"
                  className="px-3 py-2 text-right font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                >
                  Min–max Δ
                </th>
              </tr>
            </thead>
            <tbody>
              {perm.entries.map((entry) => (
                <tr
                  key={entry.canonical}
                  className="border-b border-ink-700 text-[12px] last:border-b-0"
                >
                  <th
                    scope="row"
                    className="px-3 py-2 font-data text-[12px] text-fg"
                  >
                    {entry.canonical}
                  </th>
                  <td className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.1em] text-fg-muted">
                    {entry.family}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-data tabular-nums text-fg"
                    title={String(entry.mean_delta)}
                  >
                    {entry.mean_delta.toFixed(4)}
                  </td>
                  <td className="px-3 py-2">
                    <span aria-hidden="true" className="block h-1.5 w-24 bg-ink-850">
                      <span
                        className="block h-full bg-info"
                        style={{
                          width: `${(entry.mean_delta / PERM_SCALE) * 100}%`,
                        }}
                      />
                    </span>
                  </td>
                  <td className="px-3 py-2 text-right font-data text-[11px] tabular-nums text-fg-muted">
                    {entry.min_delta.toFixed(4)}–{entry.max_delta.toFixed(4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="border-t border-ink-700 px-3 py-2 font-data text-[11px] leading-5 text-fg-dim">
          {perm.limitations} Correlated or redundant inputs can mask one
          another — a low permutation delta does not imply a feature is
          useless.
        </p>
      </div>
    </ModelSection>
  );
}
