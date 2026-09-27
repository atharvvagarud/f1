// LIMITATIONS — prominent, structured, verbatim from the contract.
// Never footnotes: each limitation is card content.
import type { AboutEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

export function AboutLimitations({
  evidence,
}: {
  evidence: AboutEvidence;
}) {
  return (
    <ModelSection
      index="10 / Limitations"
      title="What the system does not claim"
      labelledBy="about-limitations"
      note="The system is historical and frozen: it studies recorded races with a fixed model and fixed simulation, and its explanations are associational."
    >
      <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
        {evidence.limitations.map((limitation) => (
          <li
            key={limitation.id}
            className="border border-ink-600 bg-ink-850 px-3 py-2"
          >
            <p className="font-data text-[11px] font-semibold uppercase tracking-[0.14em] text-fg">
              {limitation.id.replaceAll("_", " ")}
            </p>
            <p className="mt-1 text-[12px] leading-5 text-fg-muted">
              {limitation.text}
            </p>
          </li>
        ))}
      </ul>
    </ModelSection>
  );
}
