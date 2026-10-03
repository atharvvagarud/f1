// Interactive harness body (client): fixture tabs + live P12-5 mode.

"use client";

import { useState } from "react";

import { Panel, PanelHeader } from "@/components/ui/Panel";
import { SpatialTrackRenderer } from "@/features/replay/components/SpatialTrackRenderer";
import {
  SpatialApiError,
  getSpatialFrame,
  getSpatialGeometry,
  getSpatialWindow,
  type SpatialFrame,
  type SpatialGeometry,
  type SpatialWindowSample,
} from "@/lib/spatial";
import { FIXTURES } from "./fixtures";

const LIVE_RACES = [
  "2023-r01-R",
  "2021-r05-R",
  "2024-r04-R",
  "2023-r03-R",
  "2023-r15-R",
  "2024-r09-R",
];

type LiveState =
  | { kind: "idle" }
  | { kind: "loading" }
  | {
      kind: "ready";
      geometry: SpatialGeometry;
      frame: SpatialFrame;
      trail: SpatialWindowSample[] | null;
    }
  | { kind: "unavailable" }
  | { kind: "error"; detail: string };

function errorDetail(err: unknown): string {
  if (err instanceof SpatialApiError) {
    return `${err.code ?? "error"} — ${err.message}`;
  }
  return err instanceof Error ? err.message : "Unknown load failure";
}

export function SpatialHarness() {
  const [tab, setTab] = useState<string>("fixtures");
  const [fixtureId, setFixtureId] = useState<string>(FIXTURES[0].id);
  const [liveRace, setLiveRace] = useState<string>(LIVE_RACES[0]);
  const [liveFrame, setLiveFrame] = useState<string>("528");
  const [live, setLive] = useState<LiveState>({ kind: "idle" });

  const fixture = FIXTURES.find((f) => f.id === fixtureId) ?? FIXTURES[0];

  async function loadLive(withTrail: boolean) {
    const frameIndex = Number.parseInt(liveFrame, 10);
    if (!Number.isInteger(frameIndex) || frameIndex < 0) {
      setLive({ kind: "error", detail: "Frame index must be a non-negative integer." });
      return;
    }
    setLive({ kind: "loading" });
    try {
      const [geometry, frame] = await Promise.all([
        getSpatialGeometry(liveRace),
        getSpatialFrame(liveRace, frameIndex),
      ]);
      let trail: SpatialWindowSample[] | null = null;
      if (withTrail) {
        const first = frame.drivers.find(
          (d) => d.driver_number !== null && d.availability !== "UNAVAILABLE",
        );
        if (first?.driver_number !== null && first?.driver_number !== undefined) {
          const window = await getSpatialWindow(
            liveRace,
            frameIndex,
            first.driver_number,
            5,
          );
          trail = window.samples;
        }
      }
      setLive({ kind: "ready", geometry, frame, trail });
    } catch (err) {
      if (err instanceof SpatialApiError && err.isUnavailable()) {
        setLive({ kind: "unavailable" });
      } else {
        setLive({ kind: "error", detail: errorDetail(err) });
      }
    }
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <header className="border-b border-ink-700 pb-4">
        <h1 className="font-display text-2xl font-bold tracking-tight text-fg">
          Spatial renderer harness
        </h1>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
          Isolated P12-6 validation. Fixtures are synthetic loops; live mode
          loads real P12-5 geometry and frames from the backend.
        </p>
      </header>

      <div className="mt-4 flex gap-2" role="tablist" aria-label="Harness mode">
        {(["fixtures", "live"] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            role="tab"
            aria-selected={tab === mode}
            onClick={() => setTab(mode)}
            className={`h-8 border px-3 font-ui text-[11px] uppercase tracking-[0.14em] transition-colors ${
              tab === mode
                ? "border-ink-600 bg-ink-850 text-fg"
                : "border-ink-700 text-fg-muted hover:text-fg"
            }`}
          >
            {mode}
          </button>
        ))}
      </div>

      {tab === "fixtures" ? (
        <div className="mt-4">
          <div className="flex flex-wrap gap-2" role="tablist" aria-label="Fixture">
            {FIXTURES.map((f) => (
              <button
                key={f.id}
                type="button"
                role="tab"
                aria-selected={fixtureId === f.id}
                onClick={() => setFixtureId(f.id)}
                className={`h-8 border px-3 font-ui text-[11px] uppercase tracking-[0.14em] transition-colors ${
                  fixtureId === f.id
                    ? "border-ink-600 bg-ink-850 text-fg"
                    : "border-ink-700 text-fg-muted hover:text-fg"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <SpatialTrackRenderer
              geometry={fixture.geometry}
              frame={fixture.frame}
              status="ready"
              selectedDriverId={fixture.selectedDriverId}
              headline="Track map / fixture"
            />
            <Panel>
              <PanelHeader title="Fixture notes" meta="SYNTHETIC" />
              <div className="px-4 py-3 font-data text-[12px] leading-6 text-fg-muted">
                <p>Loop: 48-pt synthetic closed circuit (not circuit data).</p>
                <p>Pack: 2 adjacent FRESH dots + STALE + off-map + NO FIX rows.</p>
                <p>Selection paints on top; coordinates never move.</p>
              </div>
            </Panel>
          </div>
        </div>
      ) : (
        <div className="mt-4">
          <Panel>
            <PanelHeader title="Live P12-5 load" meta="BACKEND" />
            <div className="flex flex-wrap items-end gap-3 px-4 py-3">
              <label className="flex flex-col gap-1 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted">
                Race
                <select
                  value={liveRace}
                  onChange={(e) => setLiveRace(e.target.value)}
                  className="h-9 border border-ink-700 bg-ink-950 px-2 font-data text-[12px] normal-case tracking-normal text-fg"
                >
                  {LIVE_RACES.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted">
                Frame
                <input
                  value={liveFrame}
                  onChange={(e) => setLiveFrame(e.target.value)}
                  inputMode="numeric"
                  className="h-9 w-28 border border-ink-700 bg-ink-950 px-2 font-data text-[12px] text-fg"
                />
              </label>
              <button
                type="button"
                onClick={() => void loadLive(false)}
                className="h-9 border border-ink-600 bg-ink-850 px-4 font-ui text-[11px] uppercase tracking-[0.14em] text-fg transition-colors hover:text-fg"
              >
                Load
              </button>
              <button
                type="button"
                onClick={() => void loadLive(true)}
                className="h-9 border border-ink-700 px-4 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:text-fg"
              >
                Load + 5 s trail
              </button>
            </div>
          </Panel>
          <div className="mt-4">
            {live.kind === "idle" ? (
              <p className="border border-ink-700 bg-ink-900 px-4 py-3 font-data text-[12px] text-fg-muted">
                No live frame loaded. 2024-r09-R demonstrates the unavailable
                state; 2023-r15-R is PARTIAL.
              </p>
            ) : live.kind === "loading" ? (
              <SpatialTrackRenderer geometry={null} frame={null} status="loading" />
            ) : live.kind === "unavailable" ? (
              <SpatialTrackRenderer geometry={null} frame={null} status="unavailable" />
            ) : live.kind === "error" ? (
              <SpatialTrackRenderer
                geometry={null}
                frame={null}
                status="error"
                errorDetail={live.detail}
              />
            ) : (
              <SpatialTrackRenderer
                geometry={live.geometry}
                frame={live.frame}
                status="ready"
                trail={live.trail}
                headline="Track map / live"
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
