// 02 / FROZEN 2025 HOLDOUT — one-shot evidence with metric roles, plus
// holdout stage evidence (descriptive; never a selection signal).
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";
import { fmt4 } from "@/features/models/components/format";

const ROLE_LABEL: Record<string, string> = {
  PRIMARY: "Primary",
  SECONDARY: "Secondary",
  TECHNICAL: "Technical · detail",
};

// Fixed display scale so stage bars never derive a scale from the data.
const STAGE_BAR_SCALE = 0.1;

export function HoldoutPerformance({
  evidence,
}: {
  evidence: ModelsEvidence;
}) {
  const holdout = evidence.holdout_evidence;
  const primary = holdout.metrics.filter((m) => m.role === "PRIMARY");
  const secondary = holdout.metrics.filter((m) => m.role === "SECONDARY");
  const technical = holdout.metrics.filter((m) => m.role === "TECHNICAL");

  return (
    <ModelSection
      index="02 / Frozen 2025 holdout"
      title="One-shot frozen evaluation — not development CV"
      labelledBy="models-holdout"
      meta={`${holdout.population.races} races · ${holdout.population.eligible_states.toLocaleString("en-US")} states · ${holdout.aggregation}`}
      note="Each metric below carries its own aggregation and population. A log-loss value and a top-3 hit-rate are different kinds of score and are not comparable with each other. Values show 4dp; full stored precision is in the title text."
    >
      {(
        [
          ["Primary metric", primary],
          ["Secondary metrics", secondary],
          ["Technical / detail metrics", technical],
        ] as const
      ).map(([groupLabel, group]) => (
        <div key={groupLabel} className="mt-4 first:mt-0">
          <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.18em] text-fg-muted">
            {groupLabel}
          </h3>
          <div className="mt-2 overflow-x-auto border border-ink-700">
            <table className="w-full min-w-[720px] text-left">
              <thead>
                <tr className="border-b border-ink-600 bg-ink-850">
                  <th
                    scope="col"
                    className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                  >
                    Metric
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                  >
                    Value
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                  >
                    Direction
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                  >
                    Aggregation · population
                  </th>
                  <th
                    scope="col"
                    className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
                  >
                    Meaning · limitation
                  </th>
                </tr>
              </thead>
              <tbody>
                {group.map((metric) => (
                  <tr
                    key={metric.id}
                    className="border-b border-ink-700 text-[12px] last:border-b-0"
                  >
                    <th
                      scope="row"
                      className="px-3 py-2 font-ui text-[12px] font-semibold text-fg"
                    >
                      {metric.display_name}
                      <span className="ml-2 border border-ink-600 px-1 py-px font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
                        {ROLE_LABEL[metric.role]}
                      </span>
                    </th>
                    <td
                      className="px-3 py-2 font-data text-[13px] font-semibold text-fg tabular-nums"
                      title={String(metric.value)}
                    >
                      {fmt4(metric.value)}
                    </td>
                    <td className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.1em] text-fg-muted">
                      <span
                        aria-label={
                          metric.direction === "lower_is_better"
                            ? "Lower is better"
                            : "Higher is better"
                        }
                      >
                        {metric.direction === "lower_is_better"
                          ? "▼ lower better"
                          : "▲ higher better"}
                      </span>
                    </td>
                    <td className="px-3 py-2 font-data text-[11px] leading-5 text-fg-muted">
                      {metric.aggregation} · {metric.population}
                    </td>
                    <td className="px-3 py-2 text-[12px] leading-5 text-fg-muted">
                      {metric.description} {metric.limitation}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      <div className="mt-4">
        <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.18em] text-fg-muted">
          Holdout stage performance — descriptive only
        </h3>
        <p className="mt-1 max-w-4xl font-data text-[11px] leading-5 text-fg-dim">
          Race-macro log loss by race-progress stage on the frozen holdout.
          Stage values describe the holdout; the model was not selected on
          2025 stage results. Prediction gets easier as the race unfolds —
          this is information, not learning. Bar scale fixed 0–0.10.
        </p>
        <ul className="mt-2 divide-y divide-ink-700 border border-ink-700">
          {holdout.stages.map((stage) => (
            <li
              key={stage.stage}
              className="grid grid-cols-[72px_1fr_88px] items-center gap-3 px-3 py-2 max-sm:grid-cols-[64px_1fr]"
            >
              <span className="font-data text-[11px] font-semibold uppercase tracking-[0.14em] text-fg">
                {stage.stage}
              </span>
              <span className="block">
                <span
                  aria-hidden="true"
                  className="block h-2 bg-ink-850"
                >
                  <span
                    className="block h-full bg-info"
                    style={{
                      width: `${Math.min(100, (stage.race_macro_log_loss / STAGE_BAR_SCALE) * 100)}%`,
                    }}
                  />
                </span>
                <span className="mt-1 block font-data text-[11px] text-fg-dim">
                  {stage.definition}
                </span>
              </span>
              <span
                className="text-right font-data text-[13px] font-semibold text-fg tabular-nums"
                title={String(stage.race_macro_log_loss)}
              >
                {fmt4(stage.race_macro_log_loss)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </ModelSection>
  );
}
