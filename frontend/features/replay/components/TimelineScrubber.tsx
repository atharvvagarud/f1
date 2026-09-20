// Timeline scrubber (Phase-5 R5).
//
// Navigates by frame_index. Pointer drags preview locally and fetch on
// release; keyboard steps commit immediately (single requests). Scrubbing
// never fires hundreds of frame requests and never invents frame state.

"use client";

import { useState } from "react";
import { displayFrame } from "@/features/replay/lib/replayMachine";

export function TimelineScrubber({
  index,
  totalFrames,
  disabled,
  onCommit,
}: {
  index: number;
  totalFrames: number;
  disabled: boolean;
  onCommit: (index: number) => void;
}) {
  // drag holds the preview value while the pointer is down; null means the
  // slider tracks the committed frame. No effect needed: releasing the
  // pointer commits and clears, keyboard steps commit immediately.
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? index;

  if (totalFrames <= 0) return null;
  const max = totalFrames - 1;

  const commit = (value: number) => {
    setDrag(null);
    if (value !== index) onCommit(value);
  };

  return (
    <div className="w-full">
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="font-mono tabular-nums text-slate-300">
          FRAME {displayFrame(shown)} / {totalFrames}
        </span>
        <span className="text-slate-500">drag to preview, release to load</span>
      </div>
      <input
        type="range"
        aria-label="Replay timeline scrubber"
        min={0}
        max={max}
        step={1}
        value={shown}
        disabled={disabled}
        className="w-full accent-red-600 disabled:opacity-50"
        onPointerDown={() => {
          setDrag(shown);
        }}
        onChange={(event) => {
          const value = Number(event.target.value);
          if (drag !== null) {
            setDrag(value);
          } else {
            commit(value);
          }
        }}
        onPointerUp={(event) =>
          commit(Number((event.target as HTMLInputElement).value))
        }
        onPointerCancel={() => {
          setDrag(null);
        }}
      />
    </div>
  );
}
