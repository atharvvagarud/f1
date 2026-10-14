import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { clearDriver, historyActionFor, isValidFrameIndex, isValidRaceId, isWorkspaceState, resolveDriverEvidence, seekFrame, selectDriver, setRace, WORKSPACE_START_FRAME, WORKSPACE_STATE_KEYS } from "./workspaceState.ts";

// Canonical state transitions (V3.10B §20). Run with
// `node --test workspaceState.test.ts` (Node >= 22, no new dependencies).

const RACE = "2024-r21-qatar";

function entered() {
  const r = setRace(null, RACE);
  assert.equal(r.ok, true);
  if (!r.ok) throw new Error("unreachable");
  return r.state;
}

describe("workspace identity", () => {
  it("canonical state carries exactly raceId + frameIndex + selectedDriverId", () => {
    assert.deepEqual([...WORKSPACE_STATE_KEYS], [
      "raceId",
      "frameIndex",
      "selectedDriverId",
    ]);
  });

  it("isWorkspaceState accepts a well-formed state", () => {
    assert.equal(
      isWorkspaceState({ raceId: RACE, frameIndex: 3, selectedDriverId: null }),
      true,
    );
  });

  it("isWorkspaceState rejects extra presentation keys", () => {
    assert.equal(
      isWorkspaceState({
        raceId: RACE,
        frameIndex: 3,
        selectedDriverId: null,
        drawerOpen: true,
      }),
      false,
    );
  });

  it("isWorkspaceState rejects missing driver key and bad shapes", () => {
    assert.equal(isWorkspaceState({ raceId: RACE, frameIndex: 3 }), false);
    assert.equal(
      isWorkspaceState({ raceId: "", frameIndex: 3, selectedDriverId: null }),
      false,
    );
    assert.equal(
      isWorkspaceState({ raceId: RACE, frameIndex: -1, selectedDriverId: null }),
      false,
    );
    assert.equal(
      isWorkspaceState({ raceId: RACE, frameIndex: 1.5, selectedDriverId: null }),
      false,
    );
  });

  it("race and frame validators reject empties and non-integers", () => {
    assert.equal(isValidRaceId(""), false);
    assert.equal(isValidRaceId("   "), false);
    assert.equal(isValidRaceId(null), false);
    assert.equal(isValidFrameIndex(-1), false);
    assert.equal(isValidFrameIndex(2.5), false);
    assert.equal(isValidFrameIndex("3"), false);
  });
});

describe("SET_RACE", () => {
  it("enters a race at the explicit start frame with no driver", () => {
    const r = setRace(null, RACE);
    assert.equal(r.ok, true);
    if (!r.ok) throw new Error("unreachable");
    assert.deepEqual(r.state, {
      raceId: RACE,
      frameIndex: WORKSPACE_START_FRAME,
      selectedDriverId: null,
    });
    assert.equal(WORKSPACE_START_FRAME, 0);
  });

  it("clears a race-A driver when entering race B without a roster", () => {
    const s = entered();
    const sel = selectDriver(s, "NOR");
    assert.equal(sel.ok, true);
    if (!sel.ok) throw new Error("unreachable");
    const moved = setRace(sel.state, "2024-r22-abu-dhabi");
    assert.equal(moved.ok, true);
    if (!moved.ok) throw new Error("unreachable");
    assert.equal(moved.state.selectedDriverId, null);
    assert.equal(moved.state.frameIndex, WORKSPACE_START_FRAME);
  });

  it("carries the driver only when the new-race roster contains it", () => {
    const s = entered();
    const sel = selectDriver(s, "NOR");
    if (!sel.ok) throw new Error("unreachable");
    const kept = setRace(sel.state, "2024-r22-abu-dhabi", ["NOR", "VER"]);
    if (!kept.ok) throw new Error("unreachable");
    assert.equal(kept.state.selectedDriverId, "NOR");
    const dropped = setRace(sel.state, "2024-r22-abu-dhabi", ["VER", "LEC"]);
    if (!dropped.ok) throw new Error("unreachable");
    assert.equal(dropped.state.selectedDriverId, null);
  });

  it("rejects empty race identity", () => {
    const r = setRace(entered(), "");
    assert.equal(r.ok, false);
    if (r.ok) throw new Error("unreachable");
    assert.equal(r.error.code, "INVALID_RACE");
  });
});

describe("SEEK_FRAME", () => {
  it("seeks an exact valid frame and preserves the driver", () => {
    let s = entered();
    const sel = selectDriver(s, "NOR");
    if (!sel.ok) throw new Error("unreachable");
    s = sel.state;
    const r = seekFrame(s, 123, 1400);
    assert.equal(r.ok, true);
    if (!r.ok) throw new Error("unreachable");
    assert.equal(r.state.frameIndex, 123);
    assert.equal(r.state.selectedDriverId, "NOR");
    assert.equal(r.state.raceId, RACE);
  });

  it("rejects out-of-range frames without snapping", () => {
    const s = entered();
    for (const bad of [-1, 1400, 9999]) {
      const r = seekFrame(s, bad, 1400);
      assert.equal(r.ok, false, `frame ${bad} must be rejected`);
      if (r.ok) throw new Error("unreachable");
      assert.equal(r.error.code, "INVALID_FRAME");
    }
  });

  it("rejects non-integer frames", () => {
    const r = seekFrame(entered(), 1.5, 1400);
    assert.equal(r.ok, false);
    if (r.ok) throw new Error("unreachable");
    assert.equal(r.error.code, "INVALID_FRAME");
  });

  it("accepts shape-valid frames when the domain is unknown (adapter validates later)", () => {
    const r = seekFrame(entered(), 42, null);
    assert.equal(r.ok, true);
  });
});

describe("SELECT_DRIVER / CLEAR_DRIVER", () => {
  it("selects a valid driver and changes selection explicitly", () => {
    const s = entered();
    let r = selectDriver(s, "NOR");
    assert.equal(r.ok, true);
    if (!r.ok) throw new Error("unreachable");
    assert.equal(r.state.selectedDriverId, "NOR");
    r = selectDriver(r.state, "VER");
    if (!r.ok) throw new Error("unreachable");
    assert.equal(r.state.selectedDriverId, "VER");
  });

  it("rejects empty driver identity", () => {
    const r = selectDriver(entered(), "  ");
    assert.equal(r.ok, false);
    if (r.ok) throw new Error("unreachable");
    assert.equal(r.error.code, "INVALID_DRIVER");
  });

  it("rejects a driver known to be invalid for the race without substituting", () => {
    const s = entered();
    const r = selectDriver(s, "ALO", ["NOR", "VER"]);
    assert.equal(r.ok, false);
    if (r.ok) throw new Error("unreachable");
    assert.equal(r.error.code, "INVALID_DRIVER");
    // Caller's state is untouched: no silent substitution happened.
    assert.equal(s.selectedDriverId, null);
  });

  it("preserves selection across frame changes (no auto-switch)", () => {
    const s = entered();
    const sel = selectDriver(s, "NOR");
    if (!sel.ok) throw new Error("unreachable");
    const moved = seekFrame(sel.state, 500, 1400);
    if (!moved.ok) throw new Error("unreachable");
    assert.equal(moved.state.selectedDriverId, "NOR");
  });

  it("clears selection to null", () => {
    const s = entered();
    const sel = selectDriver(s, "NOR");
    if (!sel.ok) throw new Error("unreachable");
    const cleared = clearDriver(sel.state);
    assert.equal(cleared.selectedDriverId, null);
    assert.equal(cleared.raceId, RACE);
  });
});

describe("driver evidence vs identity", () => {
  it("distinguishes no-evidence-at-frame from invalid identity", () => {
    assert.equal(resolveDriverEvidence("NOR", ["VER", "LEC"]), "selected-no-evidence");
    assert.equal(resolveDriverEvidence("NOR", ["NOR", "VER"]), "selected-with-evidence");
    assert.equal(resolveDriverEvidence("NOR", null), "unknown-domain");
  });
});

describe("history semantics", () => {
  it("race selection pushes; replay progression replaces; hydration writes nothing", () => {
    assert.equal(historyActionFor("SET_RACE"), "push");
    assert.equal(historyActionFor("SEEK_FRAME"), "replace");
    assert.equal(historyActionFor("SELECT_DRIVER"), "replace");
    assert.equal(historyActionFor("CLEAR_DRIVER"), "replace");
    assert.equal(historyActionFor("HYDRATE"), "none");
  });
});
