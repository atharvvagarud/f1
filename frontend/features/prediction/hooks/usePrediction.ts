import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getRaces, predictEnsemble, predictSingleModel } from "@/lib/api";
import type {
  EnsembleResult,
  MainTab,
  ModelId,
  PredictionMode,
  Race,
  SingleModelResult,
} from "@/lib/predictionTypes";
import {
  sameSelection,
  type PredictionSelection,
} from "@/features/prediction/lib/predictionSelection";

// Prediction page state + data flow, extracted verbatim from app/page.tsx.
// Owns selection state, race loading, prediction requests and tab state.
// No JSX here; rendering lives in the feature components. React state only
// (no global store): the hook instance is local to the page.
//
// Stale-result rule (UI6): a displayed result belongs only to the exact
// season + Grand Prix + mode + model that produced it. Any selection change
// clears the previous result (never re-labelled with the new selection) and
// invalidates an in-flight request; Run stays an explicit action.

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
  const [activeTab, setActiveTab] = useState<MainTab>("field");

  const requestIdRef = useRef(0);
  const selectionRef = useRef<PredictionSelection>({ year, event, mode, model });
  selectionRef.current = { year, event, mode, model };

  // Clear the result and logically cancel any in-flight request. A late
  // response for a superseded selection is dropped, never rendered.
  const invalidate = useCallback(() => {
    requestIdRef.current += 1;
    setEnsembleResult(null);
    setSingleResult(null);
    setError("");
    setLoading(false);
  }, []);

  const selectYear = useCallback(
    (value: number) => {
      invalidate();
      setYear(value);
    },
    [invalidate],
  );

  const selectEvent = useCallback(
    (value: string) => {
      invalidate();
      setEvent(value);
    },
    [invalidate],
  );

  const selectMode = useCallback(
    (value: PredictionMode) => {
      invalidate();
      setMode(value);
    },
    [invalidate],
  );

  const selectModel = useCallback(
    (value: ModelId) => {
      invalidate();
      setModel(value);
    },
    [invalidate],
  );

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
      selectEvent(events[0]);
    }
  }, [events, event, selectEvent]);

  async function handlePredict() {
    if (!event) return;

    const requestSelection = selectionRef.current;
    const requestId = ++requestIdRef.current;

    setLoading(true);
    setError("");
    setEnsembleResult(null);
    setSingleResult(null);

    try {
      if (mode === "ensemble") {
        const data = await predictEnsemble(year, event);
        if (
          requestIdRef.current !== requestId ||
          !sameSelection(requestSelection, selectionRef.current)
        ) {
          return;
        }
        setEnsembleResult(data);
      } else {
        const data = await predictSingleModel(year, event, model);
        if (
          requestIdRef.current !== requestId ||
          !sameSelection(requestSelection, selectionRef.current)
        ) {
          return;
        }
        setSingleResult(data);
      }
      setActiveTab("field");
    } catch {
      if (requestIdRef.current !== requestId) return;
      setError("Prediction request failed. Check the API server.");
    } finally {
      if (requestIdRef.current === requestId) setLoading(false);
    }
  }

  const hasPrediction =
    (mode === "ensemble" && ensembleResult !== null) ||
    (mode === "single" && singleResult !== null);

  return {
    races,
    year,
    setYear: selectYear,
    event,
    setEvent: selectEvent,
    mode,
    setMode: selectMode,
    model,
    setModel: selectModel,
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
