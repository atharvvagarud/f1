"use client";

// Re-export of the shared UI primitives. The implementation moved to
// components/ui/Panel.tsx in UI3 so the replay workspace can reuse the same
// square, 1px-ruled panel vocabulary without importing across features. Kept
// as a stable import path for the existing prediction components.

export {
  Panel,
  PanelHeader,
  Stat,
  ProbabilityBar,
  SemanticsNote,
} from "@/components/ui/Panel";
