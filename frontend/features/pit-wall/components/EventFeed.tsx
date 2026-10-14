// Compact causal race-control feed (V3.10D).
//
// Subordinate to the track. L0 shows the latest 5 events at or before T
// (chronological); older past events sit behind the native disclosure
// pattern. Every row carries only source-derived evidence (time/lap, kind,
// label, driver where relevant). Rows seek their exact frame; the driver
// chip selects the driver — two distinct buttons, never nested, and seeking
// never switches the driver.

"use client";

import { readableDriverId } from "@/features/replay/components/StandingsTable";
import { formatRaceTime } from "@/features/replay/lib/replayMachine";
import type { ReplayEvent } from "@/features/pit-wall/lib/events";

function kindChip(kind: ReplayEvent["kind"]): string {
  switch (kind) {
    case "FLAG_YELLOW":
      return "FLAG · YELLOW";
    case "FLAG_SAFETY_CAR":
      return "SAFETY CAR";
    case "FLAG_VSC":
      return "VIRTUAL SC";
    case "FLAG_RED":
      return "RED FLAG";
    case "FLAG_GREEN":
      return "GREEN";
    case "FLAG_UNKNOWN":
      return "STATUS";
    case "RC_MESSAGE":
      return "RACE CONTROL";
    case "PIT":
      return "PIT";
    case "LAP":
      return "LAP";
  }
}

function EventRow({
  event,
  onSeek,
  onSelectDriver,
}: {
  event: ReplayEvent;
  onSeek: (frameIndex: number) => void;
  onSelectDriver: (driverId: string) => void;
}) {
  const meta = [
    `F${event.frameIndex}`,
    formatRaceTime(event.eventTimeS),
    event.leaderLap !== null ? `L${event.leaderLap}` : null,
  ]
    .filter((part): part is string => part !== null)
    .join(" · ");
  return (
    <li className="flex min-w-0 items-start gap-2 border-b border-ink-700 py-2">
      <button
        type="button"
        onClick={() => onSeek(event.frameIndex)}
        aria-label={`Go to frame ${event.frameIndex}: ${event.label}`}
        className="min-w-0 flex-1 text-left focus-visible:outline-2 focus-visible:outline-focus"
      >
        <span className="block font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim tabular-nums">
          {meta}
        </span>
        <span className="mt-0.5 block">
          <span className="mr-2 inline-block rounded-chip border border-ink-700 bg-ink-850 px-1.5 py-0.5 font-ui text-[10px] font-semibold uppercase tracking-[0.08em] text-fg-muted">
            {kindChip(event.kind)}
          </span>
          <span className="font-data text-[12px] text-fg">{event.label}</span>
        </span>
      </button>
      {event.driverId !== null ? (
        <button
          type="button"
          onClick={() => onSelectDriver(event.driverId as string)}
          aria-label={`Select driver ${readableDriverId(event.driverId)}`}
          title={`Select ${readableDriverId(event.driverId)}`}
          className="mt-4 shrink-0 border border-ink-700 px-2 py-1 font-ui text-[10px] uppercase tracking-[0.08em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
        >
          {readableDriverId(event.driverId)}
        </button>
      ) : null}
    </li>
  );
}

export function EventFeed({
  visibleCount,
  recent,
  older,
  onSeek,
  onSelectDriver,
}: {
  /** Causal visible count (frameIndex <= T). Never a future total. */
  visibleCount: number;
  recent: ReplayEvent[];
  older: ReplayEvent[];
  onSeek: (frameIndex: number) => void;
  onSelectDriver: (driverId: string) => void;
}) {
  return (
    <div className="min-w-0">
      <p className="font-data text-[11px] text-fg-dim tabular-nums">
        {visibleCount === 0
          ? "No events observed yet at this point in the race."
          : `${visibleCount} event${visibleCount === 1 ? "" : "s"} to this point`}
      </p>
      {recent.length > 0 ? (
        <ul className="mt-1">
          {recent.map((event) => (
            <EventRow
              key={event.id}
              event={event}
              onSeek={onSeek}
              onSelectDriver={onSelectDriver}
            />
          ))}
        </ul>
      ) : null}
      {older.length > 0 ? (
        <details className="mt-2 border-t border-ink-700 pt-2">
          <summary className="cursor-pointer font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted focus-visible:outline-2 focus-visible:outline-focus">
            Older events ({older.length})
          </summary>
          <ul className="max-h-64 overflow-y-auto">
            {older.map((event) => (
              <EventRow
                key={event.id}
                event={event}
                onSeek={onSeek}
                onSelectDriver={onSelectDriver}
              />
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  );
}
