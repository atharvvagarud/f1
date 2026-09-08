"use client";

import { motion } from "motion/react";
import { formatPercent } from "@/lib/predictionHelpers";

export function ConfidenceBar({
  value,
  barClassName,
}: {
  value: number;
  barClassName: string;
}) {
  const safe = Math.max(0, Math.min(1, value));

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="text-slate-400">Confidence strength</span>
        <span className="font-medium text-slate-200">
          {formatPercent(safe)}
        </span>
      </div>

      <div className="relative h-3 overflow-hidden rounded-full bg-slate-800 ring-1 ring-white/10">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(safe * 100, 4)}%` }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="relative h-full rounded-full bg-white"
        >
          <div className="absolute inset-0 bg-[linear-gradient(110deg,transparent,rgba(255,255,255,0.25),transparent)] opacity-80" />
        </motion.div>
      </div>
    </div>
  );
}

export function OverviewCard({
  icon,
  label,
  value,
  subvalue,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  subvalue?: string;
}) {
  return (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      className="group rounded-[26px] border border-white/10 bg-gradient-to-br from-slate-950/75 via-slate-950/55 to-slate-900/35 p-5 shadow-xl transition-all hover:border-white/15"
    >
      <div className="flex items-center gap-3">
        <div className="rounded-xl bg-white/5 p-2 ring-1 ring-white/10 transition group-hover:bg-white/10">
          {icon}
        </div>
        <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
          {label}
        </div>
      </div>

      <div className="font-heading mt-4 text-2xl font-semibold tracking-tight text-white xl:text-[1.7rem]">
        {value}
      </div>

      {subvalue && (
        <div className="mt-2 text-sm leading-6 text-slate-400">{subvalue}</div>
      )}
    </motion.div>
  );
}

export function ChartInsightCard({
  label,
  value,
  subvalue,
}: {
  label: string;
  value: string;
  subvalue: string;
}) {
  return (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      className="rounded-[22px] border border-white/10 bg-gradient-to-br from-slate-950/70 via-slate-950/50 to-slate-900/30 px-5 py-4 shadow-xl transition-all hover:border-white/15"
    >
      <div className="text-[11px] uppercase tracking-[0.14em] text-slate-500">
        {label}
      </div>
      <div className="font-heading mt-3 text-2xl font-bold tracking-tight text-white">
        {value}
      </div>
      <div className="mt-2 text-sm leading-6 text-slate-400">{subvalue}</div>
    </motion.div>
  );
}

