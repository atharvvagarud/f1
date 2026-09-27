// EVIDENCE / PROVENANCE — compact identifiers, full hashes on demand.
import type { ModelsEvidence } from "@/features/models/lib/evidence";
import { abbrHash } from "@/features/models/components/format";

export function EvidenceProvenance({
  evidence,
}: {
  evidence: ModelsEvidence;
}) {
  const provenance = evidence.provenance;
  const hashes: [string, string][] = [
    ["Serving artifact SHA", provenance.winner_serving_sha256],
    ["Phase-2 content hash", provenance.phase2_content_hash],
    ["Holdout report SHA", provenance.holdout_report_sha256],
    ["E3 evidence SHA", provenance.e3_artifact_sha256],
    ["Spec fingerprint", provenance.model_spec_fingerprint],
    ["Protocol hash", provenance.protocol_semantic_hash],
  ];
  return (
    <section
      aria-labelledby="models-provenance"
      className="border border-ink-700 bg-ink-900"
    >
      <div className="border-b border-ink-700 px-4 py-3">
        <h2
          id="models-provenance"
          className="font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg"
        >
          Evidence / provenance
        </h2>
        <p className="mt-1 break-all font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
          Contract {evidence.contract_version} · freeze tag{" "}
          {provenance.phase8_freeze_tag} · commit{" "}
          {abbrHash(provenance.phase8_freeze_commit)} · holdout source{" "}
          {evidence.sources.FINAL_HOLDOUT_2025.path} · E3{" "}
          {evidence.sources.E3_GLOBAL_EXPLANATION.path}
        </p>
      </div>
      <details className="px-4 py-3">
        <summary className="cursor-pointer font-data text-[12px] uppercase tracking-[0.1em] text-fg-muted">
          Full hashes (copy-friendly monospace)
        </summary>
        <dl className="mt-2 space-y-1.5">
          {hashes.map(([label, hash]) => (
            <div
              key={label}
              className="grid grid-cols-[180px_1fr] gap-3 max-sm:grid-cols-1 max-sm:gap-0.5"
            >
              <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
                {label}
              </dt>
              <dd className="break-all font-data text-[12px] text-fg tabular-nums">
                {hash}
              </dd>
            </div>
          ))}
          <div className="grid grid-cols-[180px_1fr] gap-3 max-sm:grid-cols-1 max-sm:gap-0.5">
            <dt className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              Freeze commit
            </dt>
            <dd className="break-all font-data text-[12px] text-fg tabular-nums">
              {provenance.phase8_freeze_commit}
            </dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
