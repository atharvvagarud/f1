import type { Metadata } from "next";
import { CounterfactualView } from "@/features/counterfactuals/components/CounterfactualView";

export const metadata: Metadata = {
  title: "Counterfactual Explorer · F1 Intelligence",
  description:
    "Simulated outcome changes under controlled pit interventions from exact historical race states. Simulator-conditional, never a recommendation.",
};

export default function CounterfactualsPage() {
  return <CounterfactualView />;
}
