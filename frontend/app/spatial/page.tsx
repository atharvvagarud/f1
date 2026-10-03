// Isolated spatial renderer harness (Phase-12 P12-6 validation only).
//
// Not production navigation: no nav link points here. Synthetic
// fixtures exercise layout states without the backend; live mode loads
// real P12-5 geometry/frames for visual validation. P12-7 owns replay
// integration.

import { SpatialHarness } from "./harness";

export const metadata = {
  title: "Spatial Renderer Harness | F1 Intelligence",
  description:
    "Isolated validation harness for the SVG track renderer: fixtures and live P12-5 spatial frames.",
};

export default function SpatialHarnessPage() {
  return <SpatialHarness />;
}
