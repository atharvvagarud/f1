// /about — System technical dossier. Thin composition only: validated
// frozen evidence in, section components out. No fetching, no spinners,
// no scientific computation.
import { getAboutEvidence } from "@/features/about/lib/aboutEvidence";
import { getModelsEvidence } from "@/features/models/lib/modelsEvidence";
import { AboutHeader } from "@/features/about/components/AboutHeader";
import { SystemOverview } from "@/features/about/components/SystemOverview";
import { SystemSemantics } from "@/features/about/components/SystemSemantics";
import { ArchitectureMap } from "@/features/about/components/ArchitectureMap";
import { CapabilityMap } from "@/features/about/components/CapabilityMap";
import { DataPlatform } from "@/features/about/components/DataPlatform";
import { TemporalSafety } from "@/features/about/components/TemporalSafety";
import { ReplayIntelligenceFlow } from "@/features/about/components/ReplayIntelligenceFlow";
import { SimulationStrategy } from "@/features/about/components/SimulationStrategy";
import { Reproducibility } from "@/features/about/components/Reproducibility";
import { AboutLimitations } from "@/features/about/components/AboutLimitations";
import { AboutProvenance } from "@/features/about/components/AboutProvenance";

export const metadata = {
  title: "System Dossier | F1 Intelligence",
  description:
    "Technical system explanation: semantics, architecture, capabilities, data platform, temporal safety, and reproducibility.",
};

export default function AboutPage() {
  const about = getAboutEvidence();
  const models = getModelsEvidence();
  const servedSeasons = models.model_spec.final_fit_seasons;
  const holdoutSeason = String(models.model_spec.holdout_season);
  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-6 sm:px-6">
      <AboutHeader evidence={about} servedSeasons={servedSeasons} />
      <SystemOverview />
      <SystemSemantics evidence={about} />
      <ArchitectureMap evidence={about} />
      <CapabilityMap evidence={about} />
      <DataPlatform
        evidence={about}
        servedSeasons={servedSeasons}
        holdoutSeason={holdoutSeason}
      />
      <TemporalSafety evidence={models} />
      <ReplayIntelligenceFlow about={about} models={models} />
      <SimulationStrategy evidence={about} />
      <Reproducibility evidence={about} />
      <AboutLimitations evidence={about} />
      <AboutProvenance evidence={about} />
    </div>
  );
}
