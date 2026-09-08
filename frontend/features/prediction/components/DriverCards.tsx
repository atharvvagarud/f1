"use client";

import { motion } from "motion/react";
import type { DriverRow } from "@/lib/predictionTypes";
import { formatDriverName, formatGap, formatPercent, formatWhole } from "@/lib/predictionHelpers";

export function DriverCard({
  driver,
  rank,
  accent = "from-white to-slate-300",
}: {
  driver: DriverRow;
  rank: number;
  accent?: string;
}) {
  const safeProb = Math.max(0, Math.min(1, driver.win_probability));
  const probWidth = Math.max(safeProb * 100, 2);
  const isLeader = rank === 1;

  return (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      className={`rounded-2xl border px-4 py-4 transition-all hover:border-white/15 ${
        isLeader
          ? "border-white/15 bg-slate-900/80 shadow-lg shadow-black/10"
          : "border-white/8 bg-slate-900/70"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <div
              className={`inline-flex h-7 min-w-7 items-center justify-center rounded-lg px-2 text-[11px] font-semibold ${
                isLeader
                  ? "bg-white/10 text-white ring-1 ring-white/15"
                  : "bg-white/5 text-slate-300 ring-1 ring-white/10"
              }`}
            >
              P{rank}
            </div>

            <h4 className="font-heading truncate text-[17px] font-semibold tracking-tight text-white">
              {formatDriverName(driver.driver)}
            </h4>
          </div>

          <div className="mt-1 text-sm text-slate-400">
            Driver #{driver.driver_number}
          </div>
        </div>

        <div className="shrink-0 text-right">
          <div className="font-heading text-2xl font-bold tracking-tight text-white">
            {formatPercent(safeProb)}
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Win chance
          </div>
        </div>
      </div>

      <div className="mt-5">
        <div className="mb-2 flex items-center justify-between text-xs">
          <span className="text-slate-400">Win probability</span>
          <span className="font-medium text-slate-300">
            {formatPercent(safeProb)}
          </span>
        </div>

        <div className="h-2.5 overflow-hidden rounded-full bg-slate-800/90 ring-1 ring-white/5">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${probWidth}%` }}
            transition={{ duration: 0.65, ease: "easeOut" }}
            className={`h-full rounded-full bg-gradient-to-r ${accent}`}
          />
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Position
          </div>
          <div className="mt-1 font-medium text-slate-200">
            P{formatWhole(driver.position_x)}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Gap
          </div>
          <div className="mt-1 font-medium text-slate-200">
            {formatGap(driver.gap_to_leader_seconds)}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Compound
          </div>
          <div className="mt-1 font-medium text-slate-200">
            {driver.compound_x}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Tyre Life
          </div>
          <div className="mt-1 font-medium text-slate-200">
            {formatWhole(driver.tyre_life_x)} laps
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Stint
          </div>
          <div className="mt-1 font-medium text-slate-200">
            {formatWhole(driver.stint_x)}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-[0.12em] text-slate-500">
            Number
          </div>
          <div className="mt-1 font-medium text-slate-200">
            #{formatWhole(driver.driver_number)}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export function CompactDriverRow({
  driver,
  rank,
  accent = "from-white to-slate-300",
}: {
  driver: DriverRow;
  rank: number;
  accent?: string;
}) {
  const safeProb = Math.max(0, Math.min(1, driver.win_probability));
  const barWidth = Math.max(safeProb * 100, 2);

  return (
    <motion.div
      whileHover={{ y: -1, scale: 1.005 }}
      className="rounded-[18px] border border-white/8 bg-slate-900/70 px-4 py-3 transition-all hover:border-white/15"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="inline-flex h-8 min-w-8 items-center justify-center rounded-lg bg-white/5 text-xs font-semibold text-slate-200 ring-1 ring-white/10">
            P{rank}
          </div>

          <div className="min-w-0">
            <div className="font-heading truncate text-sm font-semibold text-white">
              {formatDriverName(driver.driver)}
            </div>
            <div className="mt-0.5 text-xs text-slate-400">
              Gap {formatGap(driver.gap_to_leader_seconds)}
            </div>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <div className="font-heading text-sm font-semibold text-white">
            {formatPercent(safeProb)}
          </div>
          <div className="mt-0.5 text-[11px] text-slate-500">
            Win probability
          </div>
        </div>
      </div>

      <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-800/90">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${barWidth}%` }}
          transition={{ duration: 0.55, ease: "easeOut" }}
          className={`h-full rounded-full bg-gradient-to-r ${accent}`}
        />
      </div>
    </motion.div>
  );
}

