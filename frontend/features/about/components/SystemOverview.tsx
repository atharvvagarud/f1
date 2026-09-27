// 01 / SYSTEM — concise technical description of what is implemented.
// Lists only capabilities present in the contract; nothing aspirational.
import { ModelSection } from "@/features/models/components/ModelSection";

const SYSTEM_THREADS = [
  "Historical F1 data engineering",
  "Temporally safe race-state reconstruction",
  "Probabilistic winner prediction",
  "Historical replay",
  "Monte Carlo race simulation",
  "Strategy intervention comparison",
  "Model explanation",
] as const;

export function SystemOverview() {
  return (
    <ModelSection
      index="01 / System"
      title="What this system is"
      labelledBy="about-system"
      note="A frozen research system served locally from checked-in artifacts. Every thread below names an implemented, frozen phase — see the capability map for per-phase scope."
    >
      <p className="max-w-4xl text-sm leading-6 text-fg-muted">
        F1 Race Intelligence v2 reconstructs historical Formula 1 races as
        synchronized machine-readable states, estimates win probabilities
        with a frozen statistical model, replays those estimates against
        recorded history, and compares pit-wall interventions with paired
        simulation. It studies races that already happened; it does not
        follow a season in progress.
      </p>
      <ul className="mt-3 grid grid-cols-1 gap-px border border-ink-700 bg-ink-700 sm:grid-cols-2 lg:grid-cols-3">
        {SYSTEM_THREADS.map((thread, position) => (
          <li
            key={thread}
            className="bg-ink-900 px-3 py-2 font-data text-[12px] text-fg"
          >
            <span className="text-fg-dim tabular-nums">
              {String(position + 1).padStart(2, "0")}
            </span>{" "}
            {thread}
          </li>
        ))}
      </ul>
    </ModelSection>
  );
}
