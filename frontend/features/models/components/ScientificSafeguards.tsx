// 08 / SCIENTIFIC SAFEGUARDS — bounded statement plus the seven concrete
// temporal safeguards, verbatim from the contract.
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

export function ScientificSafeguards({
  evidence,
}: {
  evidence: ModelsEvidence;
}) {
  const safeguards = evidence.temporal_safeguards;
  return (
    <ModelSection
      index="08 / Scientific safeguards"
      title="Temporal safety record"
      labelledBy="models-safeguards"
    >
      <p className="border border-ink-600 bg-ink-850 px-3 py-2 font-data text-[12px] leading-6 text-fg">
        &ldquo;{safeguards.statement}&rdquo;
      </p>
      <ol className="mt-3 divide-y divide-ink-700 border border-ink-700">
        {safeguards.items.map((item, position) => (
          <li key={item.id} className="px-3 py-2">
            <p className="font-data text-[12px] text-fg">
              <span className="text-fg-dim tabular-nums">
                {String(position + 1).padStart(2, "0")}
              </span>{" "}
              <strong className="font-semibold">{item.title}</strong>{" "}
              <span className="border border-ink-600 px-1 py-px text-[10px] uppercase tracking-[0.1em] text-fg-dim">
                {item.id}
              </span>
            </p>
            <p className="mt-0.5 pl-7 text-[12px] leading-5 text-fg-muted">
              {item.description}
            </p>
          </li>
        ))}
      </ol>
    </ModelSection>
  );
}
