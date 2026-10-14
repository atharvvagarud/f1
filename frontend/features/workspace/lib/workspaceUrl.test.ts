import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { hydrateFromUrl, parseWorkspaceSearch, serializeWorkspace } from "./workspaceUrl.ts";
import type { WorkspaceState } from "./workspaceState.ts";

// URL serialization contract (V3.10B §10–13). Run with
// `node --test workspaceUrl.test.ts` (Node >= 22, no new dependencies).

describe("workspace URL serialization", () => {
  it("serializes race+frame deterministically", () => {
    const state: WorkspaceState = {
      raceId: "2024-r21-qatar",
      frameIndex: 123,
      selectedDriverId: null,
    };
    assert.equal(serializeWorkspace(state), "race=2024-r21-qatar&frame=123");
  });

  it("appends the driver when selected", () => {
    const state: WorkspaceState = {
      raceId: "2024-r21-qatar",
      frameIndex: 123,
      selectedDriverId: "NOR",
    };
    assert.equal(
      serializeWorkspace(state),
      "race=2024-r21-qatar&frame=123&driver=NOR",
    );
  });

  it("round-trips race+frame+driver through parse", () => {
    const state: WorkspaceState = {
      raceId: "2024-r21-qatar",
      frameIndex: 123,
      selectedDriverId: "NOR",
    };
    const parsed = parseWorkspaceSearch(`?${serializeWorkspace(state)}`);
    assert.equal(parsed.ok, true);
    if (!parsed.ok) throw new Error("unreachable");
    assert.deepEqual(parsed.state, state);
  });

  it("round-trips without a driver (optional driver allowed)", () => {
    const parsed = parseWorkspaceSearch("?race=2024-r21-qatar&frame=0");
    assert.equal(parsed.ok, true);
    if (!parsed.ok) throw new Error("unreachable");
    assert.equal(parsed.state.selectedDriverId, null);
  });

  it("treats an empty driver parameter as no selection", () => {
    const parsed = parseWorkspaceSearch("?race=2024-r21-qatar&frame=0&driver=");
    assert.equal(parsed.ok, true);
    if (!parsed.ok) throw new Error("unreachable");
    assert.equal(parsed.state.selectedDriverId, null);
  });

  it("rejects missing race", () => {
    const parsed = parseWorkspaceSearch("?frame=5");
    assert.equal(parsed.ok, false);
    if (parsed.ok) throw new Error("unreachable");
    assert.equal(parsed.error.code, "MALFORMED_URL");
  });

  it("rejects non-numeric and negative frames without snapping", () => {
    for (const bad of ["?race=X&frame=abc", "?race=X&frame=12.5", "?race=X&frame=-3", "?race=X"]) {
      const parsed = parseWorkspaceSearch(bad);
      assert.equal(parsed.ok, false, `${bad} must be rejected`);
      if (parsed.ok) throw new Error("unreachable");
      assert.equal(parsed.error.code, "MALFORMED_URL");
    }
  });

  it("never throws on garbage input", () => {
    assert.doesNotThrow(() => parseWorkspaceSearch("?%%"));
    assert.doesNotThrow(() => parseWorkspaceSearch(""));
  });

  it("hydrateFromUrl matches strict parse (no silent repair)", () => {
    const good = hydrateFromUrl("?race=2024-r21-qatar&frame=7&driver=VER");
    assert.equal(good.ok, true);
    const bad = hydrateFromUrl("?race=2024-r21-qatar&frame=near-7");
    assert.equal(bad.ok, false);
  });

  it("reload identity: same query resolves to the same state twice", () => {
    const q = "?race=2024-r21-qatar&frame=123&driver=NOR";
    const first = hydrateFromUrl(q);
    const second = hydrateFromUrl(q);
    assert.equal(first.ok, true);
    assert.equal(second.ok, true);
    if (!first.ok || !second.ok) throw new Error("unreachable");
    assert.deepEqual(first.state, second.state);
  });
});
