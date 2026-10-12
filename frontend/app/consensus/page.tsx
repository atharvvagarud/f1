import { ConsensusView } from "@/features/consensus/components/ConsensusView";

export const metadata = {
  title: "Model × Simulation Consensus | F1 Intelligence",
  description:
    "Compare the frozen Logistic model against MC2-E simulation at an exact historical race state and inspect their descriptive disagreement.",
};

export default function ConsensusPage() {
  return <ConsensusView />;
}
