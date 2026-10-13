"use client";

// Global command bar (UI1). Single navigation model for every implemented
// product surface. Route awareness lives here only; the root layout stays a
// server component. Facts only — no fabricated live/connection state.

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Predict" },
  { href: "/replay", label: "Replay" },
  { href: "/simulator", label: "Simulate" },
  { href: "/consensus", label: "Consensus" },
  { href: "/uncertainty", label: "Uncertainty" },
  { href: "/strategy", label: "Strategy" },
  { href: "/counterfactuals", label: "Counterfactuals" },
  { href: "/models", label: "Models" },
  { href: "/about", label: "About" },
] as const;

export function CommandBar() {
  const pathname = usePathname();

  return (
    <header className="border-b-2 border-ink-600 bg-ink-850">
      <div className="mx-auto grid max-w-7xl grid-cols-1 px-4 sm:grid-cols-[auto_1fr_auto] sm:px-6">
        <Link
          href="/"
          aria-label="F1 Intelligence — prediction home"
          className="flex min-h-12 items-center gap-2.5"
        >
          <span className="font-display text-[15px] font-extrabold uppercase tracking-[-0.02em] text-fg">
            F1 Intelligence
          </span>
          <span className="hidden font-data text-[10px] uppercase tracking-[0.14em] text-fg-dim lg:inline">
            Race Intelligence System · V2
          </span>
        </Link>

        <nav
          aria-label="Primary"
          className="flex min-h-11 items-stretch overflow-x-auto border-t border-ink-700 sm:min-h-12 sm:border-t-0 sm:border-l sm:pl-3"
        >
          {NAV_ITEMS.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`flex shrink-0 items-center border-b-2 px-3 font-ui text-[11px] uppercase tracking-[0.14em] transition-colors ${
                  active
                    ? "border-signal font-semibold text-fg"
                    : "border-transparent font-medium text-fg-muted hover:text-fg"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="hidden items-center justify-end sm:flex">
          <span className="font-data text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            Historical · V2
          </span>
        </div>
      </div>
    </header>
  );
}
