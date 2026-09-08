"use client";

type ProbabilityChartProps = {
  groupedData: Record<string, { lap: number; value: number }[]>;
};

export default function ProbabilityChart({
  groupedData,
}: ProbabilityChartProps) {
  const width = 860;
  const height = 360;
  const padding = 48;

  const allPoints = Object.values(groupedData).flat();
  if (!allPoints.length) return null;

  const laps = allPoints.map((p) => p.lap);
  const values = allPoints.map((p) => p.value);

  const minLap = Math.min(...laps);
  const maxLap = Math.max(...laps);
  const minValue = 0;
  const maxValue = Math.max(1, ...values);

  const xScale = (lap: number) => {
    if (maxLap === minLap) return width / 2;
    return (
      padding + ((lap - minLap) / (maxLap - minLap)) * (width - padding * 2)
    );
  };

  const yScale = (value: number) => {
    if (maxValue === minValue) return height / 2;
    return (
      height -
      padding -
      ((value - minValue) / (maxValue - minValue)) * (height - padding * 2)
    );
  };

  const palette = [
    "#ffffff",
    "#94a3b8",
    "#475569",
    "#e2e8f0",
    "#64748b",
    "#334155",
  ];

  const entries = Object.entries(groupedData);

  return (
    <div className="rounded-[24px] border border-white/10 bg-white/[0.03] p-6">
      <div className="mb-4">
        <p className="text-sm uppercase tracking-[0.3em] text-slate-400">
          Probability evolution
        </p>
        <h3 className="mt-2 text-2xl font-semibold text-white">
          Win Probability Graph
        </h3>
      </div>

      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="min-w-[760px]"
          role="img"
          aria-label="Win probability graph"
        >
          {[0, 0.25, 0.5, 0.75, 1].map((tick) => (
            <g key={tick}>
              <line
                x1={padding}
                x2={width - padding}
                y1={yScale(tick)}
                y2={yScale(tick)}
                stroke="rgba(148,163,184,0.14)"
                strokeDasharray="4 6"
              />
              <text
                x={12}
                y={yScale(tick) + 4}
                fill="rgba(148,163,184,0.8)"
                fontSize="11"
              >
                {Math.round(tick * 100)}%
              </text>
            </g>
          ))}

          {Array.from(new Set(laps))
            .sort((a, b) => a - b)
            .map((lap) => (
              <g key={lap}>
                <line
                  x1={xScale(lap)}
                  x2={xScale(lap)}
                  y1={padding}
                  y2={height - padding}
                  stroke="rgba(148,163,184,0.08)"
                />
                <text
                  x={xScale(lap)}
                  y={height - 14}
                  textAnchor="middle"
                  fill="rgba(148,163,184,0.8)"
                  fontSize="11"
                >
                  Lap {lap}
                </text>
              </g>
            ))}

          {entries.map(([driver, points], index) => {
            const color = palette[index % palette.length];
            const path = points
              .map((point, i) => {
                const x = xScale(point.lap);
                const y = yScale(point.value);
                return `${i === 0 ? "M" : "L"} ${x} ${y}`;
              })
              .join(" ");

            return (
              <g key={driver}>
                <path
                  d={path}
                  fill="none"
                  stroke={color}
                  strokeWidth={index === 0 ? 3.5 : index === 1 ? 3 : 2.5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                {points.map((point) => (
                  <circle
                    key={`${driver}-${point.lap}`}
                    cx={xScale(point.lap)}
                    cy={yScale(point.value)}
                    r="5"
                    fill={color}
                    stroke="rgba(15,23,42,0.9)"
                    strokeWidth="1.5"
                  />
                ))}
              </g>
            );
          })}
        </svg>
      </div>

      <div className="mt-5 flex flex-wrap gap-3">
        {entries.map(([driver], index) => (
          <div
            key={driver}
            className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-xs text-slate-300"
          >
            <span
              className="h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: palette[index % palette.length] }}
            />
            <span>{driver}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
