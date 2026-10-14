import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { eventSeek, scopeDriverForRace, timelineSeek, toReplaySelection, validateRaceEntryForReplay, validateSeekForReplay } from "./replayAdapter.ts";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { setRace } from "./workspaceState.ts";

// Replay adapter boundary (V3.10B §14, §22–23). Run with
// `node --test replayAdapter.test.ts` (Node >= 22, no new dependencies).

const RACE = "2024-r21-qatar";

function entered() {
  const r = setRace(null, RACE);
  if (!r.ok) throw new Error("unreachable");
  return r.state;
}

describe("replay adapter parity", () => {
  it("translates canonical state to replay selection identically", () => {
    const sel = toReplaySelection({ raceId: RACE, frameIndex: 9, selectedDriverId: "NOR" });
    assert.deepEqual(sel, { raceId: RACE, frameIndex: 9 });
  });

  it("validates seeks before replay navigation (rejects, never clamps)", () => {
    const s = entered();
    const good = validateSeekForReplay(s, 10, 1400);
    assert.equal(good.ok, true);
    const bad = validateSeekForReplay(s, 1400, 1400);
    assert.equal(bad.ok, false);
    if (bad.ok) throw new Error("unreachable");
    assert.equal(bad.error.code, "INVALID_FRAME");
  });

  it("race entry resolves the start frame and fail-closes the driver", () => {
    const fresh = validateRaceEntryForReplay(null, RACE);
    assert.equal(fresh.ok, true);
    if (!fresh.ok) throw new Error("unreachable");
    assert.equal(fresh.state.frameIndex, 0);
    const cleared = validateRaceEntryForReplay(entered(), "2024-r22-abu-dhabi");
    if (!cleared.ok) throw new Error("unreachable");
    assert.equal(cleared.state.selectedDriverId, null);
  });

  it("scopes drivers to their race (cross-race selection derives to null)", () => {
    assert.equal(scopeDriverForRace("NOR", RACE, RACE), "NOR");
    assert.equal(scopeDriverForRace("NOR", RACE, "2024-r22-abu-dhabi"), null);
    assert.equal(scopeDriverForRace(null, RACE, RACE), null);
  });

  it("timeline and event primitives resolve to the exact seek", () => {
    const s = entered();
    const t = timelineSeek(s, 55, 1400);
    assert.equal(t.ok, true);
    if (!t.ok) throw new Error("unreachable");
    assert.equal(t.state.frameIndex, 55);
    const e = eventSeek(s, 1400, 1400);
    assert.equal(e.ok, false);
    if (e.ok) throw new Error("unreachable");
    assert.equal(e.error.code, "INVALID_FRAME");
  });
});
