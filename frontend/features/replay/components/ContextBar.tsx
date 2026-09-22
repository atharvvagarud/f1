// Race state header (Phase-5 R5; UI3 factual header).
//
// The ContextBar is the factual "where are we in the race" strip: leader lap +
// progress, track state/flag (text + colour, never colour-only), historical T,
// roster size, current anchor and as-of weather. Every value is a backend fact;
// nothing is inferred client-side and null renders `—`/`NO DATA`.

"use client";

import type { ReplayFrameResponse } from "@/lib/v2";
import { formatRaceTime } from "@/features/replay/lib/replayMachine";
import { readableDriverId } from "@/features/replay/components/StandingsTable";

function flagBanner(trackState: string | null): {
  label: string;
  className: string;
} {
  switch (trackState) {
    case "red_flag":
      return { label: "RED FLAG", className: "bg-danger text-ink-950" };
    case "safety_car":
      return { label: "SAFETY CAR", className: "bg-warn text-ink-950" };
    case "vsc":
    case "vsc_ending":
      return { label: "VIRTUAL SC", className: "bg-warn text-ink-950" };
    case "yellow":
      return { label: "YELLOW", className: "bg-warn text-ink-950" };
    case "all_clear":
      return { label: "GREEN", className: "bg-ok text-ink-950" };
    default:
      return {
        label: (trackState ?? "NO DATA").toUpperCase(),
        className: "border border-ink-600 bg-ink-850 text-fg-muted",
      };
  }
}

function Fact({
  label,
  children,
  className = "",
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`min-w-0 ${className}`}>
      <div className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
        {label}
      </div>
      <div className="mt-1 font-data text-[13px] text-fg tabular-nums">
        {children}
      </div>
    </div>
  );
}

export function ContextBar({ frame }: { frame: ReplayFrameResponse }) {
  const { state, leader_lap } = frame;
  const rc = state.race_control;
  const banner = flagBanner(rc.track_state);
  const progress =
    state.race_context.race_progress_frac !== null
      ? `${(state.race_context.race_progress_frac * 100).toFixed(1)}%`
      : "—";
  const weatherUnavailable =
    state.weather.air_temp_c === null && state.weather.track_temp_c === null;
  const bannerKey = rc.track_state === "vsc_ending" ? "vsc" : rc.track_state;
  const flags = (
    [
      { label: "YELLOW", on: rc.flag_yellow, key: "yellow" },
      { label: "SC", on: rc.flag_safety_car, key: "safety_car" },
      { label: "VSC", on: rc.flag_vsc, key: "vsc" },
      { label: "RED", on: rc.flag_red, key: "red_flag" },
    ] as const
  )
    .filter((flag) => flag.on && flag.key !== bannerKey)
    .map((flag) => flag.label);

  return (
    <div className="min-w-0">
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-6">
        <Fact label="Track state">
          <span
            role="status"
            aria-label={`Track state: ${banner.label}`}
            className={`inline-block rounded-chip px-2 py-0.5 font-ui text-[11px] font-bold uppercase tracking-[0.12em] ${banner.className}`}
          >
            {banner.label}
          </span>
          {flags.length > 0 ? (
            <span className="mt-1 block font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim">
              {flags.join(" · ")}
            </span>
          ) : null}
        </Fact>

        <Fact label="Leader lap">
          <span className="text-lg text-fg">{leader_lap ?? "—"}</span>
          <span className="ml-2 text-[11px] text-fg-dim">({progress})</span>
        </Fact>

        <Fact label="Race time">
          <span className="text-lg text-fg">
            {formatRaceTime(state.state_time_s)}
          </span>
        </Fact>

        <Fact label="Drivers">
          <span className="text-lg text-fg">{state.roster_size}</span>
        </Fact>

        <Fact label={`Anchor · L${state.anchor_lap_number}`}>
          <span
            className="block truncate text-[12px] text-fg"
            title={readableDriverId(state.anchor_driver_id)}
          >
            {readableDriverId(state.anchor_driver_id)}
          </span>
        </Fact>

        <Fact label="Air / track °C">
          {weatherUnavailable ? (
            <span className="text-fg-dim">NO DATA</span>
          ) : (
            <>
              <span>{state.weather.air_temp_c ?? "—"}</span>
              <span className="mx-1 text-fg-dim">/</span>
              <span>{state.weather.track_temp_c ?? "—"}</span>
              {state.weather.rainfall ? (
                <span className="ml-1.5 text-info">RAIN</span>
              ) : null}
            </>
          )}
        </Fact>
      </div>
    </div>
  );
}
