// /about header: dossier title plus a compact identity strip.
//
// Every strip value renders a contract field verbatim. Historical data
// coverage (2018-2025) and served prediction coverage (final-fit seasons
// from the frozen model spec) are labeled as separate cells so no reviewer
// can infer 2025 predictions are served.
import type { AboutEvidence } from "@/features/models/lib/evidence";

function StripCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 px-3 py-2">
      <div className="font-data text-[10px] uppercase tracking-[0.16em] text-fg-dim">
        {label}
      </div>
      <div
        className="mt-0.5 truncate font-data text-[12px] font-semibold text-fg tabular-nums"
        title={value}
      >
        {value}
      </div>
    </div>
  );
}

export function AboutHeader({
  evidence,
  servedSeasons,
}: {
  evidence: AboutEvidence;
  servedSeasons: string;
}) {
  const tierA = evidence.dataset_statistics.tier_a;
  const phase2 = evidence.dataset_statistics.phase2;
  const replay = evidence.dataset_statistics.replay;
  return (
    <header className="border-b-2 border-ink-600 pb-4">
      <p className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-muted">
        About
      </p>
      <h1 className="mt-1 font-display text-2xl font-bold tracking-tight text-fg">
        F1 Race Intelligence / System Dossier
      </h1>
      <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
        Frozen technical record of the implemented race-intelligence system:
        historical data engineering, temporally safe state reconstruction,
        frozen winner estimation, historical replay, Monte Carlo simulation,
        and paired strategy comparison. Presentation only — this page
        describes checked-in evidence and replays nothing by itself.
      </p>
      <dl className="mt-4 grid grid-cols-2 divide-ink-700 border border-ink-700 bg-ink-900 max-sm:divide-y sm:grid-cols-6 sm:divide-x sm:divide-y-0">
        <StripCell label="Data" value={String(tierA.seasons)} />
        <StripCell label="Served replay" value={servedSeasons} />
        <StripCell label="Features" value={String(phase2.predictive_features)} />
        <StripCell
          label="Replay races"
          value={Number(replay.served_races).toLocaleString("en-US")}
        />
        <StripCell
          label="Checkpoints"
          value={Number(replay.checkpoints).toLocaleString("en-US")}
        />
        <StripCell label="Phases" value="8 frozen" />
      </dl>
      <p className="mt-2 font-data text-[11px] leading-5 text-fg-dim">
        {evidence.dataset_statistics.serving_scope_note}
      </p>
    </header>
  );
}
