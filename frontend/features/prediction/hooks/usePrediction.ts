import { useEffect, useMemo, useState } from "react";
import { getRaces, predictEnsemble, predictSingleModel } from "@/lib/api";
import type {
  EnsembleResult,
  MainTab,
  ModelId,
  PredictionMode,
  Race,
  SingleModelResult,
} from "@/lib/predictionTypes";

// Prediction page state + data flow, extracted verbatim from app/page.tsx.
// Owns selection state, race loading, prediction requests and tab state.
// No JSX here; rendering lives in the feature components. React state only
// (no global store): the hook instance is local to the page.

export function usePrediction() {
  const [races, setRaces] = useState<Race[]>([]);
  const [year, setYear] = useState<number>(2023);
  const [event, setEvent] = useState<string>("");
  const [mode, setMode] = useState<PredictionMode>("ensemble");
  const [model, setModel] = useState<ModelId>("xgboost");
  const [loading, setLoading] = useState(false);
  const [ensembleResult, setEnsembleResult] = useState<EnsembleResult | null>(
    null,
  );
  const [singleResult, setSingleResult] = useState<SingleModelResult | null>(
    null,
  );
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<MainTab>("overview");

  useEffect(() => {
    async function loadRaces() {
      try {
        const data = await getRaces();
        const loadedRaces: Race[] = data.races;
        setRaces(loadedRaces);

        const years = [...new Set(loadedRaces.map((r) => r.year))].sort();
        const latestYear = years[years.length - 1];
        setYear(latestYear);

        const eventsForLatest = loadedRaces
          .filter((r) => r.year === latestYear)
          .map((r) => r.event_name);

        if (eventsForLatest.length > 0) {
          setEvent(eventsForLatest[0]);
        }
      } catch {
        setError("Failed to load races from API.");
      }
    }

    loadRaces();
  }, []);

  const years = useMemo(() => {
    return [...new Set(races.map((r) => r.year))].sort((a, b) => a - b);
  }, [races]);

  const events = useMemo(() => {
    return races.filter((r) => r.year === year).map((r) => r.event_name);
  }, [races, year]);

  useEffect(() => {
    if (events.length > 0 && !events.includes(event)) {
      setEvent(events[0]);
    }
  }, [events, event]);

  async function handlePredict() {
    if (!event) return;

    setLoading(true);
    setError("");
    setEnsembleResult(null);
    setSingleResult(null);

    try {
      if (mode === "ensemble") {
        const data = await predictEnsemble(year, event);
        setEnsembleResult(data);
      } else {
        const data = await predictSingleModel(year, event, model);
        setSingleResult(data);
      }
      setActiveTab("overview");
    } catch {
      setError("Prediction request failed. Check the API server.");
    } finally {
      setLoading(false);
    }
  }

  const hasPrediction =
    (mode === "ensemble" && ensembleResult !== null) ||
    (mode === "single" && singleResult !== null);

  return {
    races,
    year,
    setYear,
    event,
    setEvent,
    mode,
    setMode,
    model,
    setModel,
    loading,
    ensembleResult,
    singleResult,
    error,
    activeTab,
    setActiveTab,
    years,
    events,
    handlePredict,
    hasPrediction,
  };
}

export type PredictionState = ReturnType<typeof usePrediction>;
