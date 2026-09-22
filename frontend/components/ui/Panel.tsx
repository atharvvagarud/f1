"use client";

// Shared structural primitives (UI0/UI2 language; promoted to components/ui in
// UI3 so replay and prediction share one square, 1px-ruled panel vocabulary).
// No cards-for-every-number, no shadows, no gradients, no radii beyond the 2px
// chip. Colour is never the only signal: every bar is paired with its value.

import type { ReactNode } from "react";

export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`border border-ink-700 bg-ink-900 ${className}`}>
      {children}
    </section>
  );
}

export function PanelHeader({
  title,
  meta,
  note,
}: {
  title: string;
  meta?: ReactNode;
  note?: string;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-ink-700 px-4 py-3">
      <h2 className="font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg">
        {title}
      </h2>
      {meta ? (
        <div className="font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
          {meta}
        </div>
      ) : null}
      {note ? (
        <p className="w-full font-data text-[11px] leading-5 text-fg-dim">
          {note}
        </p>
      ) : null}
    </div>
  );
}

export function Stat({
  label,
  value,
  hint,
  className = "",
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={`min-w-0 px-4 py-3 ${className}`}>
      <div className="text-[10px] uppercase tracking-[0.14em] text-fg-dim">
        {label}
      </div>
      <div className="mt-1 truncate font-data text-sm text-fg tabular-nums">
        {value}
      </div>
      {hint ? (
        <div className="mt-0.5 truncate text-[11px] text-fg-dim">{hint}</div>
      ) : null}
    </div>
  );
}

// Flat structural fill. The numeric value is always rendered alongside, so the
// bar length is never the sole carrier of the probability.
export function ProbabilityBar({
  value,
  className = "",
}: {
  value: number;
  className?: string;
}) {
  const safe = Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 0;
  const width = safe > 0 ? Math.max(safe * 100, 0.5) : 0;

  return (
    <span
      aria-hidden="true"
      className={`inline-block h-1.5 overflow-hidden bg-ink-850 ${className}`}
    >
      <span className="block h-full bg-fg" style={{ width: `${width}%` }} />
    </span>
  );
}

export function SemanticsNote({ children }: { children: ReactNode }) {
  return (
    <p className="font-data text-[11px] leading-5 text-fg-dim">{children}</p>
  );
}
