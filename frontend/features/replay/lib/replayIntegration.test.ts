import { strict as assert } from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it } from "node:test";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { explanationSelectionKey, resolvedSelection } from "./explanationSelection.ts";

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (...parts: string[]): string =>
  readFileSync(join(HERE, ...parts), "utf8");

describe("explanation stale-selection guard", () => {
  it("keys selections by exact race, frame and driver identity", () => {
    const base = explanationSelectionKey("2024-r01-R", 10, "hamilton");
    assert.equal(base, "2024-r01-R|10|hamilton");
    assert.notEqual(base, explanationSelectionKey("2024-r01-R", 11, "hamilton"));
    assert.notEqual(base, explanationSelectionKey("2024-r02-R", 10, "hamilton"));
    assert.notEqual(base, explanationSelectionKey("2024-r01-R", 10, "vettel"));
  });

  it("renders the stored view only for the selection that produced it", () => {
    const state = {
      key: explanationSelectionKey("2024-r01-R", 10, "hamilton"),
      view: "HAMILTON_FRAME_10",
    };
    // Current selection matches: stored payload is authoritative.
    assert.equal(
      resolvedSelection(
        state,
        explanationSelectionKey("2024-r01-R", 10, "hamilton"),
        "LOADING",
      ),
      "HAMILTON_FRAME_10",
    );
    // Driver switched: the old payload must never render.
    assert.equal(
      resolvedSelection(
        state,
        explanationSelectionKey("2024-r01-R", 10, "vettel"),
        "LOADING",
      ),
      "LOADING",
    );
    // Frame switched: stale frame payload must never render.
    assert.equal(
      resolvedSelection(
        state,
        explanationSelectionKey("2024-r01-R", 11, "hamilton"),
        "LOADING",
      ),
      "LOADING",
    );
    // Race switched: stale race payload must never render.
    assert.equal(
      resolvedSelection(
        state,
        explanationSelectionKey("2024-r02-R", 10, "hamilton"),
        "LOADING",
      ),
      "LOADING",
    );
    // No payload yet (first selection) resolves to the caller fallback.
    assert.equal(
      resolvedSelection(
        null,
        explanationSelectionKey("2024-r01-R", 10, "hamilton"),
        "LOADING",
      ),
      "LOADING",
    );
  });
});

describe("replay integration invariants (source)", () => {
  const localHook = read("..", "hooks", "useLocalExplanation.ts");
  const changeHook = read("..", "hooks", "useTimelineChange.ts");
  const replayView = read("..", "components", "ReplayView.tsx");
  const predictionPanel = read("..", "components", "PredictionPanel.tsx");
  const localPanel = read("..", "components", "LocalExplanationPanel.tsx");
  const changePanel = read("..", "components", "ChangeExplanationPanel.tsx");
  const timelineChart = read("..", "components", "ProbabilityTimelineChart.tsx");
  const useReplay = read("..", "hooks", "useReplay.ts");

  it("both explanation hooks abort superseded requests and key the payload", () => {
    for (const hook of [localHook, changeHook]) {
      assert.match(hook, /AbortController/);
      assert.match(hook, /controller\.abort\(\)/);
      assert.match(hook, /explanationSelectionKey/);
      assert.match(hook, /resolvedSelection/);
    }
  });

  it("introduces no explanation cache (on-demand only)", () => {
    for (const hook of [localHook, changeHook]) {
      assert.equal(/new Map\(/.test(hook), false);
      assert.equal(/const\s+\w*[Cc]ache\w*\s*=/.test(hook), false);
    }
  });

  it("keeps one race-tagged selected-driver concept in ReplayView", () => {
    assert.match(replayView, /selection\.raceId === replay\.raceId/);
    assert.match(replayView, /onSelectDriver=\{onSelectDriver\}/);
    // No synchronous clear-on-race effect (selection derives to null instead).
    assert.equal(
      /useEffect\([\s\S]*?setSelection\(/.test(replayView),
      false,
    );
    // Shared with both the local explanation and the change/timeline surfaces.
    assert.match(replayView, /<PredictionPanel[\s\S]*?selectedDriverId=\{selectedDriverId\}/);
    assert.match(
      replayView,
      /<ProbabilityTimelineChart[\s\S]*?selectedDriverId=\{selectedDriverId\}/,
    );
  });

  it("PredictionPanel holds no private driver selection", () => {
    assert.equal(/useState/.test(predictionPanel), false);
    assert.match(predictionPanel, /selectedDriverId: string \| null/);
    assert.match(predictionPanel, /onSelectDriver:/);
    // Non-observable drivers are not offered an explanation control.
    assert.match(predictionPanel, /entry\.observable \?/);
    // Checkpoint honesty for non-checkpoint frames.
    assert.match(predictionPanel, /No model checkpoint/);
    assert.match(predictionPanel, /Factual frame only/);
  });

  it("change panel consumes the shared selection and labels first checkpoint", () => {
    assert.match(timelineChart, /selectedDriverId \?\?/);
    assert.match(timelineChart, /onSelectDriver=\{onSelectDriver\}/);
    assert.match(changePanel, /first checkpoint — no previous comparison/);
    assert.match(changePanel, /No previous prediction checkpoint exists/);
    assert.match(changePanel, /Exact checkpoints/);
  });

  it("communicates contribution direction without relying on the arrow", () => {
    assert.match(localPanel, /<span className="sr-only">\{directionWord/);
    assert.match(changePanel, /<span className="sr-only">\{deltaWord/);
    // Change group headings use words, not arrow glyphs alone.
    assert.match(changePanel, /Increased model log-odds/);
    assert.match(changePanel, /Decreased model log-odds/);
  });

  it("keeps disclosure and focus semantics for driver rows", () => {
    assert.match(predictionPanel, /aria-expanded=/);
    assert.match(predictionPanel, /focus-visible:outline-2/);
  });

  it("resets the deep-linked frame after the first race load", () => {
    assert.match(useReplay, /initialFrameAppliedRef/);
    assert.match(useReplay, /const applyDeepLink =/);
  });

  it("maps API error codes to specific states, not one generic error", () => {
    assert.match(useReplay, /unknown_frame/);
    assert.match(localHook, /error\.status === 422/);
    assert.match(localHook, /error\.isUnavailable\(\)/);
    assert.match(changeHook, /error\.isUnavailable\(\)/);
  });
});
