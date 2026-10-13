import { UncertaintyView } from "@/features/uncertainty/components/UncertaintyView";

export const metadata = {
  title: "Uncertainty Intelligence | F1 Intelligence",
  description:
    "Model × simulation disagreement, Monte Carlo finite-sampling precision, and the explicit simulator-sensitivity limitation at an exact historical race state.",
};

export default function UncertaintyPage() {
  return <UncertaintyView />;
}
