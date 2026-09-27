// LIMITATIONS — part of the technical model card, not footnotes.
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

export function ModelLimitations({
  evidence,
}: {
  evidence: ModelsEvidence;
}) {
  return (
    <ModelSection
      index="09 / Limitations"
      title="What this evidence does not support"
      labelledBy="models-limitations"
      note="Read before quoting any number from this page."
    >
      <ul className="divide-y divide-ink-700 border border-ink-700">
        {evidence.limitations.map((limitation) => (
          <li key={limitation.id} className="px-3 py-2">
            <p className="font-data text-[11px] uppercase tracking-[0.14em] text-warn">
              {limitation.id.replace(/_/g, " ")}
            </p>
            <p className="mt-0.5 text-[13px] leading-6 text-fg">
              {limitation.text}
            </p>
          </li>
        ))}
      </ul>
    </ModelSection>
  );
}
