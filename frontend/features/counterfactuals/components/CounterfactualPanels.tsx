// Counterfactual Explorer composable panels (V3.7G).
//
// Factual-state header, methodology drawer, provenance panel, and
// limitations panel. Each is a standalone section so the explorer can
// later compose into a unified workspace (V3.10) without redesign.
// Presentation only: every value is a backend value, shortened hashes
// are display-only with full values exposed via title attributes.

"use client";

import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { Panel, PanelHeader, SemanticsNote } from "@/components/ui/Panel";
import type { CounterfactualAvailability } from "@/lib/v2";
import {
  LIMITATIONS_COPY,
  METHODOLOGY_COPY,
} from "@/features/counterfactuals/lib/counterfactualMachine";

const labelClass = "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

function shortHash(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 16 ? `${value.slice(0, 12)}…` : value;
}

export function FactualHeader({
  availability,
  targetDriverId,
}: {
  availability: CounterfactualAvailability;
  targetDriverId: string | null;
}) {
  const target =
    targetDriverId && availability.drivers.some((d) => d.driver_id === targetDriverId)
      ? targetDriverId
      : (availability.eligible_targets[0] ?? null);
  const targetRow = availability.drivers.find((d) => d.driver_id === target) ?? null;
  return (
    <Panel>
      <PanelHeader
        title="Factual race state"
        meta="Historical replay state · facts at T only"
      />
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-3 sm:grid-cols-4 lg:grid-cols-8">
        <div className="min-w-0">
          <div className={labelClass}>Race</div>
          <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
            {availability.race_id}
          </div>
        </div>
        <div className="min-w-0">
          <div className={labelClass}>Decision lap</div>
          <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
            LAP {availability.anchor_lap_number}
          </div>
        </div>
        <div className="min-w-0">
          <div className={labelClass}>Target</div>
          <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
            {target ? readableDriverId(target) : "—"}
          </div>
        </div>
        <div className="min-w-0">
          <div className={labelClass}>Position at T</div>
          <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
            {targetRow?.position !== null && targetRow?.position !== undefined ? `P${targetRow.position}` : "—"}
          </div>
        </div>
        <div className="min-w-0">
          <div className={labelClass}>Remaining laps</div>
          <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
            {targetRow?.remaining_laps ?? "—"}
          </div>
        </div>
        <div className="min-w-0">
          <div className={labelClass}>Tyre at T</div>
          <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
            {targetRow?.compound ?? "—"}
          </div>
        </div>
        <div className="min-w-0">
          <div className={labelClass}>Eligible N</div>
          <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums">
            {targetRow !== null &&
            targetRow.eligible_n_min !== null &&
            targetRow.eligible_n_max !== null
              ? `${targetRow.eligible_n_min}–${targetRow.eligible_n_max}`
              : "—"}
          </div>
        </div>
        <div className="min-w-0">
          <div className={labelClass}>State identity</div>
          <div className="mt-1 truncate font-data text-[13px] text-fg tabular-nums" title={availability.state_identity ?? ""}>
            {shortHash(availability.state_identity)}
          </div>
        </div>
      </div>
    </Panel>
  );
}

export function MethodologyDrawer({
  open,
  onToggle,
}: {
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <Panel>
      <PanelHeader title="Methodology" meta="Simulator-conditional reading guide" />
      <div className="px-4 py-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="border border-ink-700 px-3 py-1.5 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
        >
          {open ? "Hide methodology" : "How to read these results"}
        </button>
        {open ? (
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-3 md:grid-cols-2">
            {METHODOLOGY_COPY.map((item) => (
              <div key={item.term} className="min-w-0 border-t border-ink-700 pt-2">
                <dt className="font-ui text-[11px] font-bold uppercase tracking-[0.14em] text-fg">
                  {item.term}
                </dt>
                <dd className="mt-1 text-[12px] leading-5 text-fg-muted">{item.definition}</dd>
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    </Panel>
  );
}

const PROVENANCE_FIELDS: { key: string; label: string }[] = [
  { key: "v37a_contract_identity", label: "V3.7A contract" },
  { key: "v37b_contract_identity", label: "V3.7B contract" },
  { key: "v37c_engine_identity", label: "V3.7C engine" },
  { key: "runtime_identity", label: "V3.7F runtime" },
  { key: "api_schema", label: "V3.7F API schema" },
  { key: "outcome_schema_version", label: "Outcome schema" },
  { key: "mc2_identity", label: "Simulator" },
];

export function ProvenancePanel({
  open,
  onToggle,
  provenance,
  comparisonIdentity,
  stateIdentity,
  count,
  seed,
  source,
}: {
  open: boolean;
  onToggle: () => void;
  provenance: Record<string, unknown>;
  comparisonIdentity: string | null;
  stateIdentity: string | null;
  count: number | null;
  seed: number | null;
  source: string | null;
}) {
  return (
    <Panel>
      <PanelHeader title="Provenance" meta="Technical identities" />
      <div className="px-4 py-3">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="border border-ink-700 px-3 py-1.5 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
        >
          {open ? "Hide provenance" : "Show provenance"}
        </button>
        {open ? (
          <dl className="mt-3 grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-2">
            {PROVENANCE_FIELDS.map((field) => {
              const raw = provenance[field.key];
              const value = typeof raw === "string" ? raw : raw !== undefined && raw !== null ? String(raw) : null;
              return (
                <div key={field.key} className="flex min-w-0 items-baseline justify-between gap-3 border-t border-ink-700 pt-1.5">
                  <dt className="shrink-0 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
                    {field.label}
                  </dt>
                  <dd className="truncate font-data text-[11px] text-fg tabular-nums" title={value ?? ""}>
                    {shortHash(value)}
                  </dd>
                </div>
              );
            })}
            <div className="flex min-w-0 items-baseline justify-between gap-3 border-t border-ink-700 pt-1.5">
              <dt className="shrink-0 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">Comparison</dt>
              <dd className="truncate font-data text-[11px] text-fg tabular-nums" title={comparisonIdentity ?? ""}>
                {shortHash(comparisonIdentity)}
              </dd>
            </div>
            <div className="flex min-w-0 items-baseline justify-between gap-3 border-t border-ink-700 pt-1.5">
              <dt className="shrink-0 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">State</dt>
              <dd className="truncate font-data text-[11px] text-fg tabular-nums" title={stateIdentity ?? ""}>
                {shortHash(stateIdentity)}
              </dd>
            </div>
            <div className="flex min-w-0 items-baseline justify-between gap-3 border-t border-ink-700 pt-1.5">
              <dt className="shrink-0 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">Futures / seed</dt>
              <dd className="truncate font-data text-[11px] text-fg tabular-nums">
                {count?.toLocaleString("en-US") ?? "—"} / {seed ?? "—"}
              </dd>
            </div>
            <div className="flex min-w-0 items-baseline justify-between gap-3 border-t border-ink-700 pt-1.5">
              <dt className="shrink-0 font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">Source</dt>
              <dd className="truncate font-data text-[11px] text-fg tabular-nums">{source ?? "—"}</dd>
            </div>
          </dl>
        ) : null}
      </div>
    </Panel>
  );
}

export function LimitationsPanel() {
  return (
    <Panel>
      <PanelHeader title="Limitations" meta="What this is not" />
      <div className="px-4 py-3">
        <ul className="grid grid-cols-1 gap-x-6 gap-y-1.5 md:grid-cols-2">
          {LIMITATIONS_COPY.map((item) => (
            <li key={item} className="border-t border-ink-700 pt-1.5 text-[12px] leading-5 text-fg-muted">
              {item}
            </li>
          ))}
        </ul>
        <div className="mt-3 border-t border-ink-700 pt-3">
          <SemanticsNote>
            Simulated differences under controlled interventions — not historical
            truth, not a recommendation, not an optimal strategy.
          </SemanticsNote>
        </div>
      </div>
    </Panel>
  );
}
