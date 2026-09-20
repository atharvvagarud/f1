// Served-race selector (Phase-5 R5).
//
// Renders the backend-served registry as-is, chronological. Never fabricates
// entries (2025 comes only from the backend, which excludes it).

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
    <label className="flex min-w-0 flex-col gap-1">
      <span className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-400">
        Historical race
      </span>
      <select
        aria-label="Select historical race"
        className="w-full rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-100 focus-visible:outline-2 focus-visible:outline-red-500 disabled:opacity-50"
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
    </label>
  );
}
