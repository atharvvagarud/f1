import { StrategyView } from "@/features/strategy/components/StrategyView";

export const metadata = {
  title: "Strategy Comparison | F1 Intelligence",
  description:
    "Compare simulated pit interventions from an exact historical state with paired Monte Carlo estimates and sampling uncertainty.",
};

export default function StrategyPage() {
  return <StrategyView />;
}
