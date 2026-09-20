// Race context header (Phase-5 R5).
//
// Factual header: historical time, leader lap + progress, frame anchor,
// track-state/flag banner (text + color, never color-only), weather as-of.
// All values are backend facts; nothing is inferred client-side.

"use client";

import type { ReplayFrameResponse } from "@/lib/v2";
import { formatRaceTime } from "@/features/replay/lib/replayMachine";

function flagBanner(trackState: string | null): {
  label: string;
  className: string;
} {
  switch (trackState) {
    case "red_flag":
      return { label: "RED FLAG", className: "bg-red-600 text-white" };
    case "safety_car":
      return { label: "SAFETY CAR", className: "bg-amber-400 text-black" };
    case "vsc":
    case "vsc_ending":
      return { label: "VIRTUAL SC", className: "bg-amber-200 text-black" };
    case "yellow":
      return { label: "YELLOW", className: "bg-yellow-500 text-black" };
    case "all_clear":
      return { label: "GREEN", className: "bg-emerald-600 text-white" };
    default:
      return {
        label: (trackState ?? "UNKNOWN").toUpperCase(),
        className: "bg-slate-700 text-slate-200",
      };
  }
}

export function ContextBar({ frame }: { frame: ReplayFrameResponse }) {
  const { state, leader_lap } = frame;
  const rc = state.race_control;
  const banner = flagBanner(rc.track_state);
  const progress =
    state.race_context.race_progress_frac !== null
      ? `${(state.race_context.race_progress_frac * 100).toFixed(1)}%`
      : "—";
  const weather =
    state.weather.air_temp_c !== null || state.weather.track_temp_c !== null
      ? `Air ${state.weather.air_temp_c ?? "—"}°C • Track ${state.weather.track_temp_c ?? "—"}°C` +
        (state.weather.rainfall ? " • RAIN" : "")
      : "Weather unavailable";

  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
      <span
        role="status"
        aria-label={`Track state: ${banner.label}`}
        className={`rounded px-2 py-1 text-xs font-bold tracking-[0.12em] ${banner.className}`}
      >
        {banner.label}
      </span>
      <span className="font-mono text-sm tabular-nums text-slate-100">
        T {formatRaceTime(state.state_time_s)}
      </span>
      <span className="text-sm text-slate-300">
        Leader lap{" "}
        <strong className="font-mono tabular-nums">
          {leader_lap ?? "—"}
        </strong>{" "}
        <span className="text-slate-500">({progress})</span>
      </span>
      <span className="text-xs text-slate-500">
        anchor {state.anchor_driver_id} L{state.anchor_lap_number}
      </span>
      <span className="text-xs text-slate-400">{weather}</span>
      {(rc.flag_yellow || rc.flag_safety_car || rc.flag_vsc || rc.flag_red) && (
        <span className="text-[11px] uppercase tracking-[0.12em] text-slate-400">
          {[
            rc.flag_yellow && "yellow",
            rc.flag_safety_car && "SC",
            rc.flag_vsc && "VSC",
            rc.flag_red && "red",
          ]
            .filter(Boolean)
            .join(" • ")}
        </span>
      )}
    </div>
  );
}
