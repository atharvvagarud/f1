// 03 / ARCHITECTURE — implemented stack only, rendered as an ordered
// text flow (accessible without color or sight of the connectors).
// The contract `not_used` block is rendered separately under an explicit
// heading so absent infrastructure is never mistaken for implemented.
import type { AboutEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

export function ArchitectureMap({ evidence }: { evidence: AboutEvidence }) {
  const implemented = evidence.architecture.implemented;
  return (
    <ModelSection
      index="03 / Architecture"
      title="Implemented system map"
      labelledBy="about-architecture"
      note="Data moves left to right: canonical history is reconstructed into race states, scored by the frozen estimator, and served through replay, simulation, and strategy surfaces."
    >
      <ol className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
        {implemented.map((item, position) => (
          <li
            key={item}
            className="border border-ink-600 bg-ink-850 px-3 py-2"
          >
            <p className="font-data text-[10px] uppercase tracking-[0.16em] text-fg-dim tabular-nums">
              Stage {String(position + 1).padStart(2, "0")}
              <span aria-hidden="true">
                {position < implemented.length - 1 ? " →" : ""}
              </span>
            </p>
            <p className="mt-0.5 font-data text-[12px] font-semibold text-fg">
              {item}
            </p>
          </li>
        ))}
      </ol>
      <div className="mt-3 border border-ink-700 px-3 py-3">
        <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
          Intentionally not part of current architecture
        </h3>
        <p className="mt-1 font-data text-[11px] leading-5 text-fg-dim">
          The project avoids infrastructure that is not currently justified
          by a frozen, locally served replay system.
        </p>
        <ul className="mt-2 flex flex-wrap gap-1.5">
          {evidence.architecture.not_used.map((item) => (
            <li
              key={item}
              className="border border-ink-700 px-1.5 py-0.5 font-data text-[11px] uppercase tracking-[0.1em] text-fg-muted"
            >
              {item}
            </li>
          ))}
        </ul>
      </div>
    </ModelSection>
  );
}
