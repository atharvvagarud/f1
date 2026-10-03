// Race-status view-model for the spatial track panel (Phase-12 P12-8).
//
// WHAT IS HAPPENING TO THE RACE RIGHT NOW, from the already-authoritative
// RaceState at the current replay frame. Every value is carried verbatim
// from `RaceControlState` (D9 contemporaneous track_state token + causal
// as-of last message); nothing is inferred here and no second lookup
// exists: status shares the replay clock by construction.
//
// Vocabulary (FastF1 3.7.0 mapping, frozen in D9):
//   all_clear -> GREEN, yellow -> YELLOW, safety_car -> SAFETY CAR,
//   vsc / vsc_ending -> VIRTUAL SC, red_flag -> RED FLAG, null -> UNKNOWN.
// Message line: latest timestamped race-control message, shown ONLY when
// it names status-relevant state (Flag YELLOW / DOUBLE YELLOW / RED).
// BLUE / CLEAR / GREEN / CHEQUERED / BLACK AND WHITE notices, null flags,
// and Drs / CarEvent / Other / SafetyCar-null chatter are deterministic
// clutter and never render. Raw flag text is verbatim, never reinterpreted.

import type { RaceControlState } from "@/lib/v2";

export type RaceStatusKey =
  | "green"
  | "yellow"
  | "safety_car"
  | "vsc"
  | "red_flag"
  | "unknown";

export type RaceStatusView = {
  key: RaceStatusKey;
  /** Text label; status is never conveyed by colour alone. */
  label: string;
  /** Brutalist chip classes (same tokens as the ContextBar banner). */
  chipClassName: string;
};

export function raceStatusOf(
  raceControl: Pick<RaceControlState, "track_state"> | null,
): RaceStatusView {
  const token = raceControl?.track_state ?? null;
  switch (token) {
    case "all_clear":
      return { key: "green", label: "GREEN", chipClassName: "bg-ok text-ink-950" };
    case "yellow":
      return { key: "yellow", label: "YELLOW", chipClassName: "bg-warn text-ink-950" };
    case "safety_car":
      return {
        key: "safety_car",
        label: "SAFETY CAR",
        chipClassName: "bg-warn text-ink-950",
      };
    case "vsc":
    case "vsc_ending":
      return {
        key: "vsc",
        label: "VIRTUAL SC",
        chipClassName: "bg-warn text-ink-950",
      };
    case "red_flag":
      return {
        key: "red_flag",
        label: "RED FLAG",
        chipClassName: "bg-danger text-ink-950",
      };
    default:
      return {
        key: "unknown",
        label: "STATUS UNKNOWN",
        chipClassName: "border border-ink-600 bg-ink-850 text-fg-muted",
      };
  }
}

export type RaceControlMessageView = {
  category: string;
  flag: string;
};

const MESSAGE_CATEGORIES = new Set(["Flag", "SafetyCar"]);

/** Status-relevant message flags (verbatim display, deterministic filter). */
const MESSAGE_FLAGS = new Set(["YELLOW", "DOUBLE YELLOW", "RED"]);

/**
 * Compact latest-message view, or null when the message is noise.
 * Causal by construction (D7 attaches the latest timestamped message with
 * observed_at_s <= state_time_s); this only filters relevance, never time.
 */
export function raceControlMessageOf(
  raceControl: Pick<
    RaceControlState,
    "last_message_category" | "last_message_flag"
  > | null,
): RaceControlMessageView | null {
  if (raceControl === null) return null;
  const { last_message_category: category, last_message_flag: flag } =
    raceControl;
  if (category === null || flag === null) return null;
  if (!MESSAGE_CATEGORIES.has(category)) return null;
  if (!MESSAGE_FLAGS.has(flag)) return null;
  return { category, flag };
}
