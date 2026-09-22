"use client";

import { useRef } from "react";
import type { MainTab } from "@/lib/predictionTypes";

// Result view tabs (UI2). Real tab semantics: role=tablist/tab, aria-selected,
// roving tabindex and arrow-key navigation. Square, 2px structural rule — no
// pills, no backdrop blur, selected state is a rule + weight, not colour alone.

type PredictionTabsProps = {
  activeTab: MainTab;
  setActiveTab: (tab: MainTab) => void;
};

const TABS: Array<{ id: MainTab; label: string }> = [
  { id: "field", label: "Field" },
  { id: "checkpoints", label: "Checkpoints" },
  { id: "probability", label: "Probability" },
];

export default function PredictionTabs({
  activeTab,
  setActiveTab,
}: PredictionTabsProps) {
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  function handleKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    const index = TABS.findIndex((tab) => tab.id === activeTab);
    let next = index;

    if (event.key === "ArrowRight") next = (index + 1) % TABS.length;
    else if (event.key === "ArrowLeft")
      next = (index - 1 + TABS.length) % TABS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = TABS.length - 1;
    else return;

    event.preventDefault();
    const nextId = TABS[next].id;
    setActiveTab(nextId);
    tabRefs.current[nextId]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label="Prediction result views"
      className="flex flex-wrap border-b-2 border-ink-600"
    >
      {TABS.map((tab) => {
        const active = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            ref={(element) => {
              tabRefs.current[tab.id] = element;
            }}
            type="button"
            role="tab"
            id={`pred-tab-${tab.id}`}
            aria-selected={active}
            aria-controls={`pred-panel-${tab.id}`}
            tabIndex={active ? 0 : -1}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={handleKeyDown}
            className={`border-b-2 px-3 py-2 font-ui text-[11px] uppercase tracking-[0.14em] transition-colors ${
              active
                ? "border-signal font-semibold text-fg"
                : "border-transparent font-medium text-fg-muted hover:text-fg"
            }`}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
