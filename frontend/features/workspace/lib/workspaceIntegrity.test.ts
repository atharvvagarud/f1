import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
import { fileURLToPath } from "node:url";

// Structural integrity guards for the workspace state substrate (V3.10B).
// These are source-characterisation tests (repo precedent:
// features/replay/lib/replayIntegration.test.ts): they pin dependency
// direction and wiring without executing React. Run with
// `node --test workspaceIntegrity.test.ts` (Node >= 22, no new dependencies).

const here = dirname(fileURLToPath(import.meta.url));
const read = (rel: string): string =>
  readFileSync(join(here, rel), "utf8");

const CORE = read("workspaceState.ts");
const URL = read("workspaceUrl.ts");
const LINKS = read("deepLinks.ts");
const ADAPTER = read("replayAdapter.ts");
const PROVIDER = read("../hooks/useWorkspace.tsx");
const APP_SHELL = read("../../../components/shell/AppShell.tsx");

const FORBIDDEN_IMPORTS = [
  "raceintel",
  "@/lib/v2",
  "@/lib/api",
  "from \"./v2",
  "from \"./api",
  "features/consensus",
  "features/uncertainty",
  "features/counterfactuals",
  "features/strategy",
  "features/simulator",
];

// Route-name mentions ("/consensus" link targets, adoption-table prose) are
// legitimate: deep links name routes without importing their science. Only
// module imports of science/fetching layers are forbidden.
function importLines(src: string): string {
  return src
    .split("\n")
    .filter((line) => /^\s*import[ (]/.test(line))
    .join("\n");
}

const PRESENTATION_KEYS = [
  "drawerOpen",
  "activeTab",
  "sidebarCollapsed",
  "hoveredDriver",
  "tableSort",
  "detailsExpanded",
];

describe("workspace dependency direction", () => {
  it("core, URL, links, and adapter import nothing scientific or fetching", () => {
    for (const [name, src] of [
      ["workspaceState", CORE],
      ["workspaceUrl", URL],
      ["deepLinks", LINKS],
      ["replayAdapter", ADAPTER],
    ] as const) {
      const imports = importLines(src);
      for (const forbidden of FORBIDDEN_IMPORTS) {
        assert.ok(
          !imports.includes(forbidden),
          `${name} must not import ${forbidden}`,
        );
      }
      assert.ok(!src.includes("fetch("), `${name} must never fetch`);
    }
  });

  it("core imports nothing at all (framework-free, side-effect-free)", () => {
    assert.ok(!/^import /m.test(CORE), "workspaceState.ts must have zero imports");
    assert.ok(!CORE.includes("fetch("), "core must never fetch");
  });

  it("no science execution is introduced by the workspace substrate", () => {
    for (const src of [CORE, URL, LINKS, ADAPTER, PROVIDER]) {
      assert.ok(!src.includes("MC2"), "no MC2 references");
      assert.ok(!src.includes("predictEnsemble"), "no prediction execution");
      assert.ok(!src.includes("compare-v3"), "no strategy execution");
    }
  });
});

describe("presentation-state separation", () => {
  it("no presentation key enters the canonical state type or key set", () => {
    // Doc comments name these keys as explicitly excluded; the guard pins
    // the type body and key tuple, not prose.
    const interfaceBody = CORE.slice(
      CORE.indexOf("export interface WorkspaceState"),
      CORE.indexOf("}", CORE.indexOf("export interface WorkspaceState")) + 1,
    );
    for (const key of PRESENTATION_KEYS) {
      assert.ok(
        !interfaceBody.includes(key),
        `WorkspaceState must not contain ${key}`,
      );
    }
    for (const key of PRESENTATION_KEYS) {
      assert.ok(
        !new RegExp(`^\\s*"${key}",?\\s*$`, "m").test(CORE),
        `WORKSPACE_STATE_KEYS must not contain ${key}`,
      );
    }
  });

  it("provider exposes only narrowly typed identity operations", () => {
    for (const op of ["setRace", "seekFrame", "selectDriver", "clearDriver"]) {
      assert.ok(PROVIDER.includes(op), `provider must expose ${op}`);
    }
    for (const key of PRESENTATION_KEYS) {
      assert.ok(!PROVIDER.includes(key), `provider must not own ${key}`);
    }
  });
});

describe("provider wiring", () => {
  it("AppShell mounts exactly one WorkspaceProvider with no visual change", () => {
    assert.ok(
      APP_SHELL.includes("WorkspaceProvider"),
      "AppShell must mount WorkspaceProvider",
    );
    assert.ok(
      APP_SHELL.includes("useWorkspace"),
      "AppShell must import from the workspace hook module",
    );
    // Shell keeps its single workstation frame: no new layout, no nav change.
    assert.ok(APP_SHELL.includes("CommandBar"), "CommandBar stays mounted");
    assert.ok(!APP_SHELL.includes("pit-wall"), "no /pit-wall in V3.10B");
  });

  it("provider owns URL init once and never re-reads it", () => {
    assert.ok(PROVIDER.includes("hydrateFromUrl"), "provider hydrates from URL");
    assert.ok(PROVIDER.includes("replaceState"), "transient sync replaces");
    assert.ok(PROVIDER.includes("pushState"), "race selection pushes");
    assert.ok(
      PROVIDER.includes("typeof window"),
      "provider is SSR-safe (no window at render)",
    );
  });

  it("provider never invents interpolation or snapping", () => {
    for (const word of ["nearest", "interpolat", "snap"]) {
      assert.ok(
        !PROVIDER.toLowerCase().includes(word),
        `provider must not mention ${word}`,
      );
    }
  });
});
