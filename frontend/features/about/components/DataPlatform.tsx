// 05 / DATA PLATFORM — verified dataset evidence with exact contract
// values. The 2025 boundary is a separate, visually explicit panel:
// data-platform coverage (2018-2025) vs served prediction coverage
// (2018-2024) vs 2025 frozen holdout, unserved.
import type { AboutEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";

function StatCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 px-3 py-2">
      <div className="font-data text-[10px] uppercase tracking-[0.16em] text-fg-dim">
        {label}
      </div>
      <div className="mt-0.5 font-data text-[13px] font-semibold text-fg tabular-nums">
        {value}
      </div>
    </div>
  );
}

export function DataPlatform({
  evidence,
  servedSeasons,
  holdoutSeason,
}: {
  evidence: AboutEvidence;
  servedSeasons: string;
  holdoutSeason: string;
}) {
  const stats = evidence.dataset_statistics;
  const tierA = stats.tier_a;
  const tierB = stats.tier_b;
  const phase2 = stats.phase2;
  const replay = stats.replay;
  const fmt = (value: number | string) =>
    typeof value === "number" ? value.toLocaleString("en-US") : value;
  return (
    <ModelSection
      index="05 / Data platform"
      title="Verified dataset evidence"
      labelledBy="about-data"
      note="All counts render the frozen dataset statistics verbatim."
    >
      <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
        Tier A · {String(tierA.seasons)}
      </h3>
      <dl className="mt-2 grid grid-cols-2 divide-ink-700 border border-ink-700 bg-ink-900 max-sm:divide-y sm:grid-cols-5 sm:divide-x sm:divide-y-0">
        <StatCell label="Terminal sessions" value={fmt(tierA.terminal_sessions)} />
        <StatCell label="Complete" value={fmt(tierA.complete)} />
        <StatCell label="Partial" value={fmt(tierA.partial)} />
        <StatCell label="Driver laps" value={fmt(tierA.driver_laps)} />
        <StatCell label="Results" value={fmt(tierA.results)} />
      </dl>
      <dl className="grid grid-cols-2 divide-ink-700 border border-t-0 border-ink-700 bg-ink-900 max-sm:divide-y sm:grid-cols-4 sm:divide-x sm:divide-y-0">
        <StatCell label="Pit stops" value={fmt(tierA.pit_stops)} />
        <StatCell label="Stints" value={fmt(tierA.stints)} />
        <StatCell label="Weather rows" value={fmt(tierA.weather_rows)} />
        <StatCell label="Race-control rows" value={fmt(tierA.race_control_rows)} />
      </dl>

      <h3 className="mt-4 font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
        Tier B · {String(tierB.seasons)}
      </h3>
      <dl className="mt-2 grid grid-cols-2 divide-ink-700 border border-ink-700 bg-ink-900 max-sm:divide-y sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <StatCell label="Seasons" value={fmt(tierB.seasons_count)} />
        <StatCell label="Races" value={fmt(tierB.races)} />
        <StatCell label="Results" value={fmt(tierB.results)} />
      </dl>

      <h3 className="mt-4 font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
        Phase 2 · Replay product
      </h3>
      <dl className="mt-2 grid grid-cols-2 divide-ink-700 border border-ink-700 bg-ink-900 max-sm:divide-y sm:grid-cols-5 sm:divide-x sm:divide-y-0">
        <StatCell label="States" value={fmt(phase2.states)} />
        <StatCell label="Predictive features" value={fmt(phase2.predictive_features)} />
        <StatCell label="Served races" value={fmt(replay.served_races)} />
        <StatCell label="Checkpoints" value={fmt(replay.checkpoints)} />
        <StatCell label="Observable predictions" value={fmt(replay.observable_predictions)} />
      </dl>

      <div
        aria-label="2025 serving boundary"
        className="mt-3 grid grid-cols-1 gap-px border-2 border-ink-600 bg-ink-600 sm:grid-cols-3"
      >
        <div className="bg-ink-900 px-3 py-2">
          <p className="font-data text-[10px] uppercase tracking-[0.16em] text-fg-dim">
            Data platform coverage
          </p>
          <p className="mt-0.5 font-data text-[13px] font-semibold text-fg">
            {String(tierA.seasons)}
          </p>
        </div>
        <div className="bg-ink-900 px-3 py-2">
          <p className="font-data text-[10px] uppercase tracking-[0.16em] text-fg-dim">
            Prediction / replay serving
          </p>
          <p className="mt-0.5 font-data text-[13px] font-semibold text-fg">
            {servedSeasons}
          </p>
        </div>
        <div className="bg-ink-850 px-3 py-2">
          <p className="font-data text-[10px] uppercase tracking-[0.16em] text-fg-dim">
            {holdoutSeason} · Frozen holdout / unserved
          </p>
          <p className="mt-0.5 font-data text-[13px] font-semibold text-fg">
            Not served by replay or prediction
          </p>
        </div>
      </div>
      <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
        {stats.serving_scope_note}
      </p>
    </ModelSection>
  );
}
