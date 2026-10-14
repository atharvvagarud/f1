// Event + lap navigation row (V3.10D).
//
// PREVIOUS EVENT seeks the previous observable event frame; NEXT EVENT is a
// deliberately generic seek-forward control — its label never names the
// future event (type, driver, lap all stay hidden until arrival). PREV/NEXT
// LAP seek exact first-frames of laps from the causal index. All moves are
// workspace seeks: same race, same driver, same state as manual arrival.

"use client";

const navButtonClass =
  "h-11 border border-ink-700 bg-ink-950 px-3 font-ui text-[11px] font-semibold uppercase tracking-[0.14em] text-fg-muted " +
  "transition-colors hover:border-ink-600 hover:text-fg " +
  "disabled:cursor-not-allowed disabled:border-dashed disabled:text-fg-dim " +
  "focus-visible:outline-2 focus-visible:outline-focus";

export function EventNav({
  hasPreviousEvent,
  hasNextEvent,
  hasPreviousLap,
  hasNextLap,
  onPreviousEvent,
  onNextEvent,
  onPreviousLap,
  onNextLap,
}: {
  hasPreviousEvent: boolean;
  hasNextEvent: boolean;
  hasPreviousLap: boolean;
  hasNextLap: boolean;
  onPreviousEvent: () => void;
  onNextEvent: () => void;
  onPreviousLap: () => void;
  onNextLap: () => void;
}) {
  return (
    <div
      className="flex flex-wrap items-center gap-1.5"
      role="group"
      aria-label="Event and lap navigation"
    >
      <button
        type="button"
        disabled={!hasPreviousEvent}
        onClick={onPreviousEvent}
        aria-label="Go to previous event"
        className={navButtonClass}
      >
        ‹ Event
      </button>
      <button
        type="button"
        disabled={!hasNextEvent}
        onClick={onNextEvent}
        aria-label="Go to next event"
        className={navButtonClass}
      >
        Event ›
      </button>
      <button
        type="button"
        disabled={!hasPreviousLap}
        onClick={onPreviousLap}
        aria-label="Go to previous lap"
        className={navButtonClass}
      >
        ‹ Lap
      </button>
      <button
        type="button"
        disabled={!hasNextLap}
        onClick={onNextLap}
        aria-label="Go to next lap"
        className={navButtonClass}
      >
        Lap ›
      </button>
    </div>
  );
}
