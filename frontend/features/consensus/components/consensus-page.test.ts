// Consensus page contract tests (V3.8G). Static source assertions over the
// G surface plus deterministic client/hook checks. No network, no server.
// Run with: node --test features/consensus/components/consensus-page.test.ts
import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { describe, it } from "node:test";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, "..", "..", "..", "..");
const G_FILES = [
  "frontend/app/consensus/page.tsx",
  "frontend/features/consensus/lib/consensusClient.ts",
  "frontend/features/consensus/lib/consensusFormat.ts",
  "frontend/features/consensus/hooks/useConsensus.ts",
  "frontend/features/consensus/components/ConsensusView.tsx",
  "frontend/features/consensus/components/FieldTable.tsx",
  "frontend/features/consensus/components/GapViz.tsx",
  "frontend/components/shell/CommandBar.tsx",
];
const src = (p: string): string => readFileSync(join(REPO, p), "utf8");
const ALL = G_FILES.map(src).join("\n");

describe("route and navigation", () => {
  it("consensus route renders the workspace", () => {
    assert.match(src("frontend/app/consensus/page.tsx"), /ConsensusView/);
  });
  it("navigation integrates without restructuring", () => {
    assert.match(src("frontend/components/shell/CommandBar.tsx"), /\/consensus/);
  });
});

describe("source labels and family wording", () => {
  it("names MODEL/Logistic/independent-binary and SIMULATION/MC2-E/frequency", () => {
    assert.match(ALL, /MODEL.*Logistic|Logistic/);
    assert.match(ALL, /MC2-E/);
    assert.match(ALL, /[Ii]ndependent binary/);
    assert.match(ALL, /[Mm]utually exclusive|[Ss]imulation frequency|[Ww]inner frequenc/);
  });
  it("states the gap sign convention visibly", () => {
    assert.match(ALL, /simulation [−-] model|simulation_minus_model/);
  });
  it("top-k wording is WIN-ranking overlap, never finish<=k", () => {
    assert.match(ALL, /not P\(finish/i);
    assert.ok(!/probability of finishing/i.test(ALL));
  });
  it("MC sampling wording is finite-simulation only", () => {
    assert.match(ALL, /finite-simulation sampling|MC sampling range|sampling range/i);
    assert.ok(!/real-world uncertainty/i.test(ALL));
  });
});

describe("prohibited concepts", () => {
  const banned = [
    "fused_probability",
    "consensus_probability",
    "combined_probability",
    "average probability",
    "confidence score",
    "consensus score",
    "preferred source",
    "trusted source",
    "source winner",
    "recommended probability",
    "optimal source",
    "Trust simulation",
    "Trust model",
    "Best source",
    "Model is wrong",
    "Simulation is right",
  ];
  for (const token of banned) {
    it(`absent: ${token}`, () => {
      assert.ok(!ALL.includes(token), token);
    });
  }
  it("no midpoint/average markers in the visualization", () => {
    const viz = src("frontend/features/consensus/components/GapViz.tsx");
    assert.ok(!/midpoint|blend\(|confidence band/i.test(viz));
  });
});

describe("research-boundary integrity", () => {
  it("no direct research-artifact frontend import", () => {
    assert.ok(!/per_row_records|mc2_checkpoint|oof_baseline|fusion_evaluation|historical_evaluation/i.test(ALL));
    assert.ok(!/results\/v3\/v3_8[de]/i.test(ALL));
  });
  it("no direct model/simulator frontend import", () => {
    assert.ok(!/raceintel\/(model_lab|simulation)|ml\/inference|joblib|\.parquet|\.pkl/i.test(ALL));
  });
  it("consumes the F API seam only", () => {
    const client = src("frontend/features/consensus/lib/consensusClient.ts");
    assert.match(client, /\/v2\/consensus\/availability/);
    assert.match(client, /\/v2\/consensus\/compare/);
  });
  it("no recomputation of authoritative C metrics", () => {
    assert.ok(!/wilson_interval|average_ranks|leader_set|topk_set|mc_sampling_se/i.test(ALL));
  });
});

describe("fixture and demo disclosure", () => {
  it("identifies historical replay, never live", () => {
    assert.match(ALL, /Historical replay/i);
    const consensusOnly = G_FILES.filter((f) => f.includes("/consensus/")).map(src).join("\n");
    assert.ok(!/\blive\b/i.test(consensusOnly));
  });
  it("discloses illustrative/non-representative magnitude", () => {
    assert.match(ALL, /not typical|illustrative/i);
  });
  it("demo anchors are explicit, no free-form year input", () => {
    const hook = src("frontend/features/consensus/hooks/useConsensus.ts");
    assert.match(hook, /2022-r03-R/);
    assert.match(hook, /2022-r19-R/);
    assert.match(hook, /2025-r01-R/);
  });
});

describe("availability and refusal rendering", () => {
  it("covers comparable, not-comparable, unsupported, error, loading", () => {
    const view = src("frontend/features/consensus/components/ConsensusView.tsx");
    assert.match(view, /not-comparable/);
    assert.match(view, /unsupported/);
    assert.match(view, /role="status"/);
    assert.match(view, /role="alert"/);
    assert.match(view, /Loading comparison/);
  });
  it("missing simulation is unavailable text, never 0%", () => {
    const view = src("frontend/features/consensus/components/ConsensusView.tsx");
    assert.match(view, /not shown as 0%|UNAVAILABLE/i);
  });
});

describe("accessibility and responsive markers", () => {
  it("semantic landmarks, headings, table scope, labels", () => {
    const view = src("frontend/features/consensus/components/ConsensusView.tsx");
    const table = src("frontend/features/consensus/components/FieldTable.tsx");
    assert.match(view, /<main/);
    assert.match(view, /<h1/);
    assert.match(table, /scope="col"/);
    assert.match(table, /scope="row"/);
    assert.match(table, /aria-label/);
    assert.match(ALL, /focus-visible/);
  });
  it("status and direction not color-only", () => {
    assert.match(ALL, /role="status"/);
    assert.match(ALL, /simulation higher|model higher/);
  });
  it("responsive breakpoints without fixed viewport widths", () => {
    assert.match(ALL, /md:table-cell|lg:grid-cols-4|sm:grid-cols/);
    assert.ok(!/min-w-\[390|w-\[1600|width:\s*1600/i.test(ALL));
  });
  it("native details disclosure for provenance", () => {
    assert.match(src("frontend/features/consensus/components/ConsensusView.tsx"), /<details/);
  });
});

describe("request discipline", () => {
  it("single compare per selection, no polling or streaming", () => {
    const hook = src("frontend/features/consensus/hooks/useConsensus.ts");
    assert.match(hook, /AbortController/);
    assert.ok(!/setInterval|EventSource|WebSocket/i.test(hook));
    assert.ok(!/simulation_count|master_seed/i.test(
      src("frontend/features/consensus/lib/consensusClient.ts"),
    ));
  });
});
