// 06 / FEATURE SYSTEM — 84 canonical / 106 transformed, 8 families with
// exact counts. Names expand per family; no default dump.
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

export function FeatureSystem({ evidence }: { evidence: ModelsEvidence }) {
  const features = evidence.feature_system;
  return (
    <ModelSection
      index="06 / Feature system"
      title="84 canonical → 106 transformed"
      labelledBy="models-features"
      meta={`${features.canonical_total} canonical · ${features.transformed_dim} transformed · 8 families`}
      note={features.preprocessing}
    >
      <div className="overflow-x-auto border border-ink-700">
        <table className="w-full min-w-[560px] text-left">
          <thead>
            <tr className="border-b border-ink-600 bg-ink-850">
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
                Count
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Composition
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Meaning
              </th>
            </tr>
          </thead>
          <tbody>
            {features.families.map((family) => (
              <tr
                key={family.family}
                className="border-b border-ink-700 text-[12px] last:border-b-0"
              >
                <th
                  scope="row"
                  className="px-3 py-2 font-ui text-[12px] font-semibold text-fg"
                >
                  {family.family}
                </th>
                <td className="px-3 py-2 text-right font-data tabular-nums text-fg">
                  {family.count}
                </td>
                <td className="px-3 py-2">
                  <span aria-hidden="true" className="block h-1.5 bg-ink-850">
                    <span
                      className="block h-full bg-fg"
                      style={{
                        width: `${(family.count / features.canonical_total) * 100}%`,
                      }}
                    />
                  </span>
                </td>
                <td className="px-3 py-2 text-[12px] text-fg-muted">
                  {family.meaning}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 space-y-2">
        {features.families.map((family) => (
          <details
            key={family.family}
            className="border border-ink-700 bg-ink-850"
          >
            <summary className="cursor-pointer px-3 py-2 font-data text-[12px] uppercase tracking-[0.1em] text-fg">
              {family.family} — {family.count} feature
              {family.count === 1 ? "" : "s"}
            </summary>
            <p className="border-t border-ink-700 px-3 py-2 font-data text-[12px] leading-6 text-fg-muted">
              {(features.feature_names_by_family[family.family] ?? []).join(
                ", ",
              )}
            </p>
          </details>
        ))}
      </div>
    </ModelSection>
  );
}
