import { Strategy2View } from "@/features/strategy/components/Strategy2View";

export const metadata = {
  title: "Strategy 2.0 | F1 Intelligence",
  description:
    "Compare simulated strategy alternatives from an exact historical state: no-intervention reference, paired trade-off deltas with 95% MC intervals, downside risk and objective leaders.",
};

export default function StrategyPage() {
  return <Strategy2View />;
}
