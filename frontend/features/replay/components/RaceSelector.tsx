// Served-race selector (Phase-5 R5; UI3 workstation control).
//
// Renders the backend-served registry as-is, chronological. Never fabricates
// entries (2025 comes only from the backend, which excludes it). Compact,
// square, monospace control with a programmatically associated label.

"use client";

import type { V2RaceSummary } from "@/lib/v2";

export function raceLabel(race: V2RaceSummary): string {
  return `${race.season} R${race.round_no} — ${race.event_name}`;
}

export function RaceSelector({
  races,
  raceId,
  disabled,
  onSelect,
}: {
  races: V2RaceSummary[];
  raceId: string | null;
  disabled: boolean;
  onSelect: (raceId: string) => void;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label
        htmlFor="replay-race"
        className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim"
      >
        Historical race
      </label>
      <select
        id="replay-race"
        className="h-9 w-full border border-ink-700 bg-ink-950 px-2.5 font-data text-[13px] text-fg transition-colors focus-visible:border-ink-600 disabled:cursor-not-allowed disabled:text-fg-dim"
        value={raceId ?? ""}
        disabled={disabled || races.length === 0}
        onChange={(event) => onSelect(event.target.value)}
      >
        {races.length === 0 && <option value="">No races served</option>}
        {races.map((race) => (
          <option key={race.race_id} value={race.race_id}>
            {raceLabel(race)}
          </option>
        ))}
      </select>
      {raceId ? (
        <span className="font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
          {races.length} served races · 2018–2024
        </span>
      ) : null}
    </div>
  );
}
