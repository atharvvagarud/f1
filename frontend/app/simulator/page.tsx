import { SimulatorView } from "@/features/simulator/components/SimulatorView";

export const metadata = {
  title: "Monte Carlo Race Simulator | F1 Intelligence",
  description:
    "Simulate the remaining 2018–2024 race from an exact historical state and view simulated outcome frequencies.",
};

export default function SimulatorPage() {
  return <SimulatorView />;
}
