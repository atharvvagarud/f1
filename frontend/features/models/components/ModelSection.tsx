// Numbered engineering section shell for /models. Structural only.
import type { ReactNode } from "react";

export function ModelSection({
  index,
  title,
  meta,
  note,
  children,
  labelledBy,
}: {
  index: string;
  title: string;
  meta?: string;
  note?: string;
  children: ReactNode;
  labelledBy: string;
}) {
  return (
    <section
      aria-labelledby={labelledBy}
      className="border border-ink-700 bg-ink-900"
    >
      <div className="border-b-2 border-ink-600 px-4 py-3">
        <p className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-dim">
          {index}
        </p>
        <h2
          id={labelledBy}
          className="mt-0.5 font-display text-[15px] font-bold uppercase tracking-[0.08em] text-fg"
        >
          {title}
        </h2>
        {meta ? (
          <p className="mt-1 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim">
            {meta}
          </p>
        ) : null}
        {note ? (
          <p className="mt-1 max-w-4xl font-data text-[11px] leading-5 text-fg-dim">
            {note}
          </p>
        ) : null}
      </div>
      <div className="px-4 py-4">{children}</div>
    </section>
  );
}
