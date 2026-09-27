// 09 / REPRODUCIBILITY — freeze tags, artifact hashes, seeds,
// manifests, and make targets, all verbatim from the contract. Major
// phases are frozen as repository checkpoints; no single-command full
// reproduction is claimed.
import type { AboutEvidence } from "@/features/models/lib/evidence";
import { ModelSection } from "@/features/models/components/ModelSection";
import { abbrHash } from "@/features/models/components/format";

const PHASE_LABELS = [
  "P1 Data",
  "P2 Features",
  "P3 Model lab",
  "P4 Race state",
  "P5 Replay",
  "P6 Monte Carlo",
  "P7 Strategy",
  "P8 Replay intelligence",
] as const;

export function Reproducibility({ evidence }: { evidence: AboutEvidence }) {
  const repro = evidence.reproducibility;
  return (
    <ModelSection
      index="09 / Reproducibility"
      title="Frozen checkpoints and identities"
      labelledBy="about-reproducibility"
      note={repro.note}
    >
      <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
        Phase freeze timeline
      </h3>
      <ol className="mt-2 grid grid-cols-2 gap-px border border-ink-700 bg-ink-700 sm:grid-cols-4">
        {repro.freeze_tags.map((tag, position) => (
          <li key={tag} className="bg-ink-900 px-3 py-2">
            <p className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
              {PHASE_LABELS[position]}
            </p>
            <p
              className="mt-0.5 break-all font-data text-[11px] text-fg"
              title={tag}
            >
              {tag}
            </p>
          </li>
        ))}
      </ol>
      <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="border border-ink-700 px-3 py-2">
          <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
            Artifact identities (SHA-256, abbreviated)
          </h3>
          <dl className="mt-2 space-y-1.5">
            {Object.entries(repro.artifact_hashes).map(([label, hash]) => (
              <div
                key={label}
                className="grid grid-cols-[1fr_auto] items-baseline gap-3"
              >
                <dt className="break-all font-data text-[11px] uppercase tracking-[0.1em] text-fg-dim">
                  {label}
                </dt>
                <dd
                  className="font-data text-[12px] text-fg tabular-nums"
                  title={hash}
                >
                  {abbrHash(hash)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="border border-ink-700 px-3 py-2">
          <h3 className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
            Deterministic reproduction inputs
          </h3>
          <dl className="mt-2 space-y-1.5 font-data text-[12px]">
            <div className="grid grid-cols-[110px_1fr] gap-3">
              <dt className="text-[11px] uppercase tracking-[0.1em] text-fg-dim">
                Seeds
              </dt>
              <dd className="text-fg tabular-nums">
                {repro.deterministic_seeds.map(String).join(", ")}
              </dd>
            </div>
            <div className="grid grid-cols-[110px_1fr] gap-3">
              <dt className="text-[11px] uppercase tracking-[0.1em] text-fg-dim">
                Make targets
              </dt>
              <dd className="break-all text-fg">
                {repro.make_targets.join(" · ")}
              </dd>
            </div>
          </dl>
          <h3 className="mt-3 font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
            Validation manifests
          </h3>
          <ul className="mt-1.5 space-y-1">
            {repro.manifests.map((manifest) => (
              <li
                key={manifest}
                className="break-all font-data text-[11px] leading-5 text-fg-muted"
              >
                {manifest}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </ModelSection>
  );
}
