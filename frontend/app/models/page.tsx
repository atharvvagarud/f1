// /models — Model validation terminal. Thin composition only: validated
// frozen evidence in, section components out. No fetching, no spinners,
// no scientific computation.
import { getModelsEvidence } from "@/features/models/lib/modelsEvidence";
import { ModelHeader } from "@/features/models/components/ModelHeader";
import { ProductionModel } from "@/features/models/components/ProductionModel";
import { HoldoutPerformance } from "@/features/models/components/HoldoutPerformance";
import { TemporalEvaluation } from "@/features/models/components/TemporalEvaluation";
import { DevelopmentComparison } from "@/features/models/components/DevelopmentComparison";
import { CalibrationEvidence } from "@/features/models/components/CalibrationEvidence";
import { FeatureSystem } from "@/features/models/components/FeatureSystem";
import { GlobalEvidence } from "@/features/models/components/GlobalEvidence";
import { ScientificSafeguards } from "@/features/models/components/ScientificSafeguards";
import { ModelLimitations } from "@/features/models/components/ModelLimitations";
import { EvidenceProvenance } from "@/features/models/components/EvidenceProvenance";

export const metadata = {
  title: "Winner Model / Validation Lab | F1 Intelligence",
  description:
    "Frozen winner model specification, temporal evaluation, 2025 holdout evidence, calibration, features, and global model evidence.",
};

export default function ModelsPage() {
  const evidence = getModelsEvidence();
  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6">
      <ModelHeader evidence={evidence} />
      <ProductionModel evidence={evidence} />
      <HoldoutPerformance evidence={evidence} />
      <TemporalEvaluation evidence={evidence} />
      <DevelopmentComparison evidence={evidence} />
      <CalibrationEvidence evidence={evidence} />
      <FeatureSystem evidence={evidence} />
      <GlobalEvidence evidence={evidence} />
      <ScientificSafeguards evidence={evidence} />
      <ModelLimitations evidence={evidence} />
      <EvidenceProvenance evidence={evidence} />
    </div>
  );
}
