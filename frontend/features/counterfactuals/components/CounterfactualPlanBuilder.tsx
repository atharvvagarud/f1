// Counterfactual plan builder (V3.7G).
//
// Controls derive entirely from availability/API constraints: eligible
// N options per target, admitted compounds, roster-bounded targets,
// rival candidates minus targets, structural cap of 8 interventions.
// The backend remains authoritative: frontend guards only improve UX.

"use client";

import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { Panel, PanelHeader } from "@/components/ui/Panel";
import type {
  CounterfactualAvailability,
  CounterfactualCompound,
  CounterfactualForm,
} from "@/lib/v2";
import {
  MAX_INTERVENTIONS,
  MULTI_DRIVER_LIMIT_COPY,
  NO_INTERVENTION_REFERENCE_COPY,
  SUPPORTED_COMPOUNDS,
  eligibleNValues,
  isRivalAllowed,
  pitTimingLabel,
  presetsFor,
  type Preset,
} from "@/features/counterfactuals/lib/counterfactualMachine";
import type { InterventionDraft } from "@/features/counterfactuals/hooks/useCounterfactuals";

const labelClass = "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

const selectClass =
  "h-9 w-full border border-ink-700 bg-ink-950 px-2 font-data text-[12px] text-fg disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-focus";

const secondaryButtonClass =
  "h-8 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus";

function InterventionRow({
  item,
  index,
  planLabel,
  availability,
  running,
  onChange,
  onRemove,
  removable,
}: {
  item: InterventionDraft;
  index: number;
  planLabel: string;
  availability: CounterfactualAvailability;
  running: boolean;
  onChange: (next: InterventionDraft) => void;
  onRemove: () => void;
  removable: boolean;
}) {
  const byId = new Map(availability.drivers.map((d) => [d.driver_id, d]));
  const driver = byId.get(item.target_driver_id);
  const options = driver ? eligibleNValues(driver) : [];
  const decisionLap = driver?.decision_lap ?? null;
  return (
    <li className="border border-ink-700 px-3 py-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-data text-[11px] font-bold uppercase tracking-[0.1em] text-fg">
          Stop {index + 1}
        </span>
        {removable ? (
          <button
            type="button"
            onClick={onRemove}
            disabled={running}
            aria-label={`Remove stop ${index + 1} from ${planLabel}`}
            className="font-data text-[11px] uppercase tracking-[0.1em] text-fg-dim transition-colors hover:text-danger disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-focus"
          >
            Remove
          </button>
        ) : null}
      </div>
      <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-3">
        <div className="flex min-w-0 flex-col gap-1">
          <label htmlFor={`${planLabel}-target-${item.id}`} className={labelClass}>
            Target
          </label>
          <select
            id={`${planLabel}-target-${item.id}`}
            value={item.target_driver_id}
            disabled={running}
            onChange={(event) => onChange({ ...item, target_driver_id: event.target.value })}
            className={selectClass}
          >
            {availability.eligible_targets.map((id) => (
              <option key={id} value={id}>
                {readableDriverId(id)}
              </option>
            ))}
          </select>
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <label htmlFor={`${planLabel}-n-${item.id}`} className={labelClass}>
            Pit in N laps
          </label>
          {options.length > 0 ? (
            <select
              id={`${planLabel}-n-${item.id}`}
              value={options.includes(item.lap_offset_n) ? item.lap_offset_n : options[0]}
              disabled={running}
              onChange={(event) => onChange({ ...item, lap_offset_n: Number(event.target.value) })}
              className={selectClass}
            >
              {options.map((n) => (
                <option key={n} value={n}>
                  PIT IN {n} {n === 1 ? "LAP" : "LAPS"}
                </option>
              ))}
            </select>
          ) : (
            <input
              id={`${planLabel}-n-${item.id}`}
              type="number"
              min={1}
              value={item.lap_offset_n}
              disabled={running}
              onChange={(event) => {
                const parsed = Number(event.target.value);
                onChange({ ...item, lap_offset_n: Number.isInteger(parsed) && parsed >= 1 ? parsed : 1 });
              }}
              className={selectClass}
            />
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <label htmlFor={`${planLabel}-compound-${item.id}`} className={labelClass}>
            Compound
          </label>
          <select
            id={`${planLabel}-compound-${item.id}`}
            value={item.requested_compound}
            disabled={running}
            onChange={(event) =>
              onChange({ ...item, requested_compound: event.target.value as CounterfactualCompound })
            }
            className={selectClass}
          >
            {SUPPORTED_COMPOUNDS.map((compound) => (
              <option key={compound} value={compound}>
                {compound}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="mt-1.5 font-data text-[11px] text-fg-muted tabular-nums">
        {pitTimingLabel(item.lap_offset_n, decisionLap)}
      </p>
    </li>
  );
}

function PlanSection({
  planLabel,
  targets,
  items,
  availability,
  running,
  onTargets,
  onItems,
}: {
  planLabel: string;
  targets: string[];
  items: InterventionDraft[];
  availability: CounterfactualAvailability;
  running: boolean;
  onTargets: (next: string[]) => void;
  onItems: (next: InterventionDraft[]) => void;
}) {
  const usedTargets = [...new Set(items.map((i) => i.target_driver_id))];
  const effectiveTargets = targets.length > 0 ? targets : usedTargets;
  return (
    <div className="min-w-0">
      <div className="font-ui text-[11px] font-bold uppercase tracking-[0.14em] text-fg">
        {planLabel}
      </div>
      <fieldset className="m-0 mt-2 min-w-0 border-0 p-0">
        <legend className={labelClass}>Plan targets</legend>
        <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1.5">
          {availability.eligible_targets.map((id) => (
            <label key={id} className="flex cursor-pointer items-center gap-1.5 text-[12px] text-fg">
              <input
                type="checkbox"
                checked={effectiveTargets.includes(id)}
                disabled={running}
                onChange={() => {
                  const next = effectiveTargets.includes(id)
                    ? effectiveTargets.filter((t) => t !== id)
                    : [...effectiveTargets, id];
                  onTargets(next);
                }}
                className="h-3.5 w-3.5 shrink-0 cursor-pointer appearance-none border border-ink-600 bg-ink-950 checked:border-signal checked:bg-signal disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-focus"
              />
              {readableDriverId(id)}
            </label>
          ))}
        </div>
      </fieldset>
      <ul className="mt-2 space-y-2">
        {items.map((item, index) => (
          <InterventionRow
            key={item.id}
            item={item}
            index={index}
            planLabel={planLabel}
            availability={availability}
            running={running}
            onChange={(next) => onItems(items.map((i) => (i.id === item.id ? next : i)))}
            onRemove={() => onItems(items.filter((i) => i.id !== item.id))}
            removable={items.length > 1}
          />
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={running || items.length >= MAX_INTERVENTIONS}
          onClick={() => {
            const fallback = effectiveTargets[0] ?? availability.eligible_targets[0];
            if (!fallback) return;
            const driver = availability.drivers.find((d) => d.driver_id === fallback);
            const firstN = driver ? eligibleNValues(driver)[0] ?? 2 : 2;
            onItems([
              ...items,
              {
                id: `iv-${Date.now()}-${items.length}`,
                target_driver_id: fallback,
                lap_offset_n: firstN,
                requested_compound: "MEDIUM",
              },
            ]);
          }}
          className={secondaryButtonClass}
        >
          Add stop
        </button>
        <span className="font-data text-[11px] text-fg-dim">
          {items.length} of {MAX_INTERVENTIONS} · one simulated trajectory
        </span>
      </div>
    </div>
  );
}

export function CounterfactualPlanBuilder({
  form,
  onForm,
  availability,
  running,
  altTargets,
  altItems,
  onAltTargets,
  onAltItems,
  baseTargets,
  baseItems,
  onBaseTargets,
  onBaseItems,
  rival,
  onRival,
  onPreset,
}: {
  form: CounterfactualForm;
  onForm: (next: CounterfactualForm) => void;
  availability: CounterfactualAvailability;
  running: boolean;
  altTargets: string[];
  altItems: InterventionDraft[];
  onAltTargets: (next: string[]) => void;
  onAltItems: (next: InterventionDraft[]) => void;
  baseTargets: string[];
  baseItems: InterventionDraft[];
  onBaseTargets: (next: string[]) => void;
  onBaseItems: (next: InterventionDraft[]) => void;
  rival: string | null;
  onRival: (next: string | null) => void;
  onPreset: (preset: Preset) => void;
}) {
  const coTarget =
    availability.eligible_targets.find((id) => id !== altTargets[0]) ?? null;
  const presets = presetsFor(altTargets[0] ?? "", coTarget);
  const rivalOptions = availability.rival_candidates.filter((id) => !altTargets.includes(id));
  const rivalBlocked = rival !== null && !isRivalAllowed(rival, altTargets, availability.rival_candidates);
  return (
    <Panel>
      <PanelHeader
        title="Intervention plan"
        meta="Controlled pit schedule · backend-validated"
        note="Plans are validated by the backend. Availability bounds what can be chosen; eligibility gates what can be compared."
      />
      <div className="grid grid-cols-1 gap-x-6 gap-y-4 border-b border-ink-700 px-4 py-3 lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-1.5">
          <span id="cf-mode-label" className={labelClass}>
            Comparison mode
          </span>
          <div role="radiogroup" aria-labelledby="cf-mode-label" className="flex flex-wrap gap-2">
            {(
              [
                { value: "REFERENCE_VS_PLAN", label: "Reference vs plan" },
                { value: "PLAN_VS_PLAN", label: "Plan vs plan" },
              ] as const
            ).map((option) => (
              <button
                key={option.value}
                type="button"
                role="radio"
                aria-checked={form === option.value}
                disabled={running}
                onClick={() => onForm(option.value)}
                className={`h-9 border px-3 font-ui text-[11px] uppercase tracking-[0.14em] transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-focus ${
                  form === option.value
                    ? "border-signal bg-signal/10 font-semibold text-fg"
                    : "border-ink-700 text-fg-muted hover:border-ink-600 hover:text-fg"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
          <span className="font-data text-[11px] leading-5 text-fg-dim">
            {form === "REFERENCE_VS_PLAN"
              ? `BASE: no-intervention reference. ${NO_INTERVENTION_REFERENCE_COPY}`
              : "BASE: plan A. ALT: plan B. Positive deltas favor B per each metric's frozen orientation."}
          </span>
        </div>
        <div className="flex min-w-0 flex-col gap-1.5">
          <label htmlFor="cf-rival" className={labelClass}>
            Rival · P(ahead of rival)
          </label>
          <select
            id="cf-rival"
            value={rival ?? ""}
            disabled={running}
            onChange={(event) => onRival(event.target.value === "" ? null : event.target.value)}
            className={`${selectClass} max-w-xs`}
          >
            <option value="">No rival</option>
            {rivalOptions.map((id) => (
              <option key={id} value={id}>
                {readableDriverId(id)}
              </option>
            ))}
            {rival !== null && !rivalOptions.includes(rival) ? (
              <option value={rival}>{readableDriverId(rival)} (in plan — backend will refuse)</option>
            ) : null}
          </select>
          <span className="font-data text-[11px] leading-5 text-fg-dim">
            {rivalBlocked
              ? "Rival must differ from every plan target; the backend refuses this combination."
              : "Factual rival only. A rival that is also a target is refused by the backend."}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-x-6 gap-y-5 border-b border-ink-700 px-4 py-3 lg:grid-cols-2">
        {form === "PLAN_VS_PLAN" ? (
          <PlanSection
            planLabel="Plan A · base"
            targets={baseTargets}
            items={baseItems}
            availability={availability}
            running={running}
            onTargets={onBaseTargets}
            onItems={onBaseItems}
          />
        ) : null}
        <PlanSection
          planLabel={form === "PLAN_VS_PLAN" ? "Plan B · alternative" : "Plan · alternative"}
          targets={altTargets}
          items={altItems}
          availability={availability}
          running={running}
          onTargets={onAltTargets}
          onItems={onAltItems}
        />
      </div>

      {altTargets.length > 1 ? (
        <p className="border-b border-ink-700 px-4 py-2 font-data text-[11px] leading-5 text-fg-dim">
          {MULTI_DRIVER_LIMIT_COPY}
        </p>
      ) : null}

      <div className="px-4 py-3">
        <div className={labelClass}>Fixture presets · structure only, never ranked</div>
        <div className="mt-2 flex flex-wrap gap-2">
          {presets.map((preset) => (
            <button
              key={preset.key}
              type="button"
              disabled={running}
              onClick={() => onPreset(preset)}
              className="h-8 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-focus"
            >
              {preset.label}
            </button>
          ))}
        </div>
        <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
          Each preset maps to a precomputed demo-cache comparison. Compound pace
          differentiation is limited by the frozen simulator — presets do not
          optimize tyres.
        </p>
      </div>
    </Panel>
  );
}
