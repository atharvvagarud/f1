"use client";

import type { ComponentType } from "react";
import { LayoutGrid, Table2, LineChart, Users } from "lucide-react";
import type { MainTab } from "@/lib/predictionTypes";

type PredictionTabsProps = {
  activeTab: MainTab;
  setActiveTab: (tab: MainTab) => void;
};

const tabs: Array<{
  id: MainTab;
  label: string;
  icon: ComponentType<{ className?: string }>;
}> = [
  { id: "overview", label: "Overview", icon: LayoutGrid },
  { id: "table", label: "Checkpoint Table", icon: Table2 },
  { id: "chart", label: "Win Probability Graph", icon: LineChart },
  { id: "drivers", label: "Top Drivers", icon: Users },
];

export default function PredictionTabs({
  activeTab,
  setActiveTab,
}: PredictionTabsProps) {
  return (
    <div className="inline-flex flex-wrap gap-2 rounded-full border border-white/10 bg-white/5 p-2 backdrop-blur-xl">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const active = activeTab === tab.id;

        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={[
              "inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium transition-all",
              active
                ? "bg-white text-slate-950 shadow-lg"
                : "text-slate-300 hover:bg-white/10 hover:text-white",
            ].join(" ")}
          >
            <Icon className="h-4 w-4" />
            <span>{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
