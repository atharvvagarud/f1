// Causal timeline marker strip (V3.10D).
//
// A compact dot row under the scrubber showing past/current event markers
// ONLY (frameIndex <= T — the caller passes the visible set, so future
// positions can never leak). Same-frame events share one dot (count kept,
// details preserved in the feed). Dots are keyboard-operable seeks with
// text-equivalent accessible labels; kind is never color-only.

"use client";

import type { EventMarker } from "@/features/pit-wall/lib/events";

function markerLabel(marker: EventMarker): string {
  const head = marker.events
    .slice(0, 3)
    .map((event) => event.label)
    .join("; ");
  const tail =
    marker.events.length > 3
      ? `; +${marker.events.length - 3} more`
      : "";
  return `${marker.count} event${marker.count === 1 ? "" : "s"} at frame ${marker.frameIndex}: ${head}${tail}`;
}

export function EventMarkers({
  markers,
  totalFrames,
  onSeek,
}: {
  markers: EventMarker[];
  totalFrames: number;
  onSeek: (frameIndex: number) => void;
}) {
  if (totalFrames <= 1 || markers.length === 0) return null;
  const max = totalFrames - 1;
  return (
    <div
      className="relative mt-1 h-6"
      role="group"
      aria-label="Past event markers"
    >
      <span
        aria-hidden="true"
        className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-ink-700"
      />
      {markers.map((marker) => (
        <button
          key={`${marker.frameIndex}`}
          type="button"
          onClick={() => onSeek(marker.frameIndex)}
          title={markerLabel(marker)}
          aria-label={markerLabel(marker)}
          className="absolute top-1/2 flex h-6 w-4 -translate-x-1/2 -translate-y-1/2 items-center justify-center focus-visible:outline-2 focus-visible:outline-focus"
          style={{ left: `${(marker.frameIndex / max) * 100}%` }}
        >
          <span
            aria-hidden="true"
            className="block h-2 w-2 rounded-full border border-signal bg-ink-950"
          />
        </button>
      ))}
    </div>
  );
}
