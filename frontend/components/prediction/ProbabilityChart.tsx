"use client";

// Flat checkpoint-probability chart (UI2). Neutral hairline grid, no
// gradients. Series are distinguished by weight, dash pattern, marker shape
// and a labelled legend, never by colour alone. Paths break at missing
// checkpoints; no value is interpolated.

import { formatPercent, titleCaseModelName } from "@/lib/predictionHelpers";

type ProbabilityChartProps = {
  groupedData: Record<string, { lap: number; value: number }[]>;
};

const WIDTH = 920;
const HEIGHT = 320;
const PAD_LEFT = 46;
const PAD_RIGHT = 16;
const PAD_TOP = 16;
const PAD_BOTTOM = 34;

const SERIES_STYLES = [
  { color: "var(--color-fg)", dash: undefined, shape: "circle" as const },
  { color: "var(--color-info)", dash: "7 4", shape: "square" as const },
  { color: "var(--color-warn)", dash: "2 3", shape: "diamond" as const },
];

const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

function Marker({
  x,
  y,
  shape,
  color,
}: {
  x: number;
  y: number;
  shape: "circle" | "square" | "diamond";
  color: string;
}) {
  if (shape === "square") {
    return (
      <rect
        x={x - 2.8}
        y={y - 2.8}
        width={5.6}
        height={5.6}
        fill={color}
        stroke="var(--color-ink-950)"
        strokeWidth="1"
      />
    );
  }

  if (shape === "diamond") {
    return (
      <polygon
        points={`${x},${y - 3.4} ${x + 3.4},${y} ${x},${y + 3.4} ${x - 3.4},${y}`}
        fill={color}
        stroke="var(--color-ink-950)"
        strokeWidth="1"
      />
    );
  }

  return (
    <circle
      cx={x}
      cy={y}
      r="2.8"
      fill={color}
      stroke="var(--color-ink-950)"
      strokeWidth="1"
    />
  );
}

export default function ProbabilityChart({
  groupedData,
}: ProbabilityChartProps) {
  const entries = Object.entries(groupedData);
  const allPoints = entries.flatMap(([, points]) => points);
  if (!allPoints.length) return null;

  const laps = allPoints.map((point) => point.lap);
  const minLap = Math.min(...laps);
  const maxLap = Math.max(...laps);

  const chartWidth = WIDTH - PAD_LEFT - PAD_RIGHT;
  const chartHeight = HEIGHT - PAD_TOP - PAD_BOTTOM;

  const xScale = (lap: number) =>
    maxLap === minLap
      ? PAD_LEFT + chartWidth / 2
      : PAD_LEFT + ((lap - minLap) / (maxLap - minLap)) * chartWidth;

  const yScale = (value: number) =>
    PAD_TOP + (1 - Math.max(0, Math.min(1, value))) * chartHeight;

  const uniqueLaps = [...new Set(laps)].sort((a, b) => a - b);

  return (
    <div>
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          className="min-w-[640px]"
          role="img"
          aria-label={`Win probability by checkpoint for ${entries
            .map(([name]) => titleCaseModelName(name))
            .join(", ")}`}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
            <g key={tick}>
              <line
                x1={PAD_LEFT}
                x2={WIDTH - PAD_RIGHT}
                y1={yScale(tick)}
                y2={yScale(tick)}
                stroke="var(--color-ink-700)"
                strokeWidth="1"
              />
              <text
                x={PAD_LEFT - 8}
                y={yScale(tick) + 3.5}
                textAnchor="end"
                fill="var(--color-fg-dim)"
                fontFamily={MONO}
                fontSize="10"
              >
                {Math.round(tick * 100)}%
              </text>
            </g>
          ))}

          {uniqueLaps.map((lap) => (
            <g key={lap}>
              <line
                x1={xScale(lap)}
                x2={xScale(lap)}
                y1={PAD_TOP}
                y2={HEIGHT - PAD_BOTTOM}
                stroke="var(--color-ink-700)"
                strokeWidth="1"
              />
              <text
                x={xScale(lap)}
                y={HEIGHT - 12}
                textAnchor="middle"
                fill="var(--color-fg-dim)"
                fontFamily={MONO}
                fontSize="10"
              >
                L{lap}
              </text>
            </g>
          ))}

          {entries.map(([name, points], index) => {
            const style = SERIES_STYLES[index % SERIES_STYLES.length];
            const sorted = [...points].sort((a, b) => a.lap - b.lap);
            const path = sorted
              .map((point, pointIndex) => {
                const x = xScale(point.lap);
                const y = yScale(point.value);
                return `${pointIndex === 0 ? "M" : "L"} ${x} ${y}`;
              })
              .join(" ");

            return (
              <g key={name}>
                <path
                  d={path}
                  fill="none"
                  stroke={style.color}
                  strokeWidth="2"
                  strokeDasharray={style.dash}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {sorted.map((point) => (
                  <Marker
                    key={`${name}-${point.lap}`}
                    x={xScale(point.lap)}
                    y={yScale(point.value)}
                    shape={style.shape}
                    color={style.color}
                  />
                ))}
              </g>
            );
          })}
        </svg>
      </div>

      <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
        {entries.map(([name, points], index) => {
          const style = SERIES_STYLES[index % SERIES_STYLES.length];
          const latest = points.reduce((a, b) => (b.lap >= a.lap ? b : a));
          return (
            <li
              key={name}
              className="inline-flex items-center gap-2 font-data text-[11px] text-fg-muted"
            >
              <svg width="26" height="10" aria-hidden="true" className="shrink-0">
                <line
                  x1="1"
                  y1="5"
                  x2="25"
                  y2="5"
                  stroke={style.color}
                  strokeWidth="2"
                  strokeDasharray={style.dash}
                />
                <Marker x={13} y={5} shape={style.shape} color={style.color} />
              </svg>
              <span>{titleCaseModelName(name)}</span>
              <span className="text-fg tabular-nums">
                {formatPercent(latest.value)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
