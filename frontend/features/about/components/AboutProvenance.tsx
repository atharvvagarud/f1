// PROVENANCE — compact technical provenance. Relative source paths
// only; abbreviated hashes with full values on demand.
import type { AboutEvidence } from "@/features/models/lib/evidence";
import { abbrHash } from "@/features/models/components/format";

export function AboutProvenance({
  evidence,
}: {
  evidence: AboutEvidence;
}) {
  const provenance = evidence.provenance;
  return (
    <section
      aria-labelledby="about-provenance"
      className="border border-ink-700 bg-ink-900"
    >
      <div className="border-b border-ink-700 px-4 py-3">
        <h2
          id="about-provenance"
          className="font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg"
        >
          Provenance
        </h2>
        <p className="mt-1 break-all font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
          Contract {evidence.contract_version} · freeze tag{" "}
          {provenance.phase8_freeze_tag} · commit{" "}
          {abbrHash(provenance.phase8_freeze_commit)} · corpus{" "}
          {abbrHash(provenance.e2_corpus_aggregate_sha256)}
        </p>
      </div>
      <details className="px-4 py-3">
        <summary className="cursor-pointer font-data text-[12px] uppercase tracking-[0.1em] text-fg-muted">
          Full identities and relative source paths
        </summary>
        <dl className="mt-2 space-y-1.5">
          <div className="grid grid-cols-[180px_1fr] gap-3 max-sm:grid-cols-1 max-sm:gap-0.5">
            <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              Freeze commit
            </dt>
            <dd className="break-all font-data text-[12px] text-fg tabular-nums">
              {provenance.phase8_freeze_commit}
            </dd>
          </div>
          <div className="grid grid-cols-[180px_1fr] gap-3 max-sm:grid-cols-1 max-sm:gap-0.5">
            <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              Corpus aggregate
            </dt>
            <dd className="break-all font-data text-[12px] text-fg tabular-nums">
              {provenance.e2_corpus_aggregate_sha256}
            </dd>
          </div>
          {Object.entries(evidence.sources).map(([id, source]) => (
            <div
              key={id}
              className="grid grid-cols-[180px_1fr] gap-3 max-sm:grid-cols-1 max-sm:gap-0.5"
            >
              <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
                {id}
              </dt>
              <dd className="break-all font-data text-[12px] text-fg-muted">
                {source.path}
              </dd>
            </div>
          ))}
        </dl>
      </details>
    </section>
  );
}
