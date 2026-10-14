import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { ROUTE_WORKSPACE_ADOPTION, workspaceDeepLink } from "./deepLinks.ts";
import type { WorkspaceState } from "./workspaceState.ts";

// Expert-page deep-link helpers (V3.10B §19). Run with
// `node --test deepLinks.test.ts` (Node >= 22, no new dependencies).

const STATE: WorkspaceState = {
  raceId: "2024-r21-qatar",
  frameIndex: 123,
  selectedDriverId: "NOR",
};

describe("workspace deep links", () => {
  it("carries race+frame+driver to every linked route", () => {
    for (const route of [
      "/replay",
      "/strategy",
      "/counterfactuals",
      "/consensus",
      "/uncertainty",
      "/simulator",
    ] as const) {
      const link = workspaceDeepLink(route, STATE);
      assert.ok(link.startsWith(`${route}?`), link);
      assert.ok(link.includes("race=2024-r21-qatar"), link);
      assert.ok(link.includes("frame=123"), link);
      assert.ok(link.includes("driver=NOR"), link);
    }
  });

  it("omits the driver parameter when nothing is selected", () => {
    const link = workspaceDeepLink("/strategy", { ...STATE, selectedDriverId: null });
    assert.ok(!link.includes("driver="), link);
    assert.ok(link.includes("race=2024-r21-qatar"), link);
  });

  it("replay deep link parses back with the existing replay convention", () => {
    // ?race=&frame= is the validated useReplay convention; the link must
    // remain compatible with it (driver is additive and ignored until adopted).
    const link = workspaceDeepLink("/replay", STATE);
    const query = link.slice("/replay".length);
    assert.ok(query.includes("race=2024-r21-qatar"));
    assert.ok(query.includes("frame=123"));
  });

  it("adoption table covers all linked routes honestly", () => {
    const routes = ROUTE_WORKSPACE_ADOPTION.map((r) => r.route).sort();
    assert.deepEqual(routes, [
      "/consensus",
      "/counterfactuals",
      "/replay",
      "/simulator",
      "/strategy",
      "/uncertainty",
    ]);
    // V3.10G: /strategy and /counterfactuals consume the canonical
    // race+frame+driver deep link (prefill only); every other route records
    // explicit deferred adoption (no silent claims of integration).
    for (const entry of ROUTE_WORKSPACE_ADOPTION) {
      if (entry.route === "/replay") {
        assert.deepEqual([...entry.consumes], ["race", "frame"]);
      } else if (entry.route === "/strategy" || entry.route === "/counterfactuals") {
        assert.deepEqual([...entry.consumes], ["race", "frame", "driver"]);
      } else {
        assert.deepEqual([...entry.consumes], []);
      }
      assert.ok(entry.deferred.length > 0, entry.route);
    }
  });
});
