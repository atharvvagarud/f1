// 04 / CAPABILITY MAP — the 8 implemented capabilities as a technical
// matrix/timeline. Every row renders contract fields verbatim: phase,
// status, what it does, what it does not do, and semantics.
import type { AboutEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

export function CapabilityMap({ evidence }: { evidence: AboutEvidence }) {
  return (
    <ModelSection
      index="04 / Capability map"
      title="Eight frozen capabilities"
      labelledBy="about-capabilities"
      note="Not a roadmap. Everything below already exists in a frozen phase; the does-not column is part of the contract."
    >
      <div className="overflow-x-auto border border-ink-700">
        <table className="w-full min-w-[880px] border-collapse text-left">
          <thead>
            <tr className="border-b border-ink-600 bg-ink-850">
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Phase
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Capability
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Status
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                What it does
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                What it does not do
              </th>
              <th
                scope="col"
                className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
              >
                Semantics
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-700">
            {evidence.capabilities.map((capability) => (
              <tr key={capability.id}>
                <td className="px-3 py-2 font-data text-[12px] text-fg-dim tabular-nums">
                  P{capability.phase}
                </td>
                <th
                  scope="row"
                  className="px-3 py-2 font-data text-[12px] font-semibold text-fg"
                >
                  {capability.name}
                </th>
                <td className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.1em] text-fg">
                  {capability.status}
                </td>
                <td className="px-3 py-2 text-[12px] leading-5 text-fg-muted">
                  {capability.does}
                </td>
                <td className="px-3 py-2 text-[12px] leading-5 text-fg-muted">
                  {capability.does_not}
                </td>
                <td className="px-3 py-2 font-data text-[11px] uppercase tracking-[0.1em] text-fg-dim">
                  {capability.semantics}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ModelSection>
  );
}
