export function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatGap(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(2)}s`;
}

export function formatWhole(value: number | null | undefined) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value)}`;
}

export function getConfidenceTone(value: number) {
  if (value >= 0.75) {
    return {
      pill: "border-emerald-400/20 bg-emerald-500/10 text-emerald-200",
      bar: "from-emerald-400 via-cyan-400 to-sky-400",
      glow: "from-emerald-500/18 via-cyan-400/8 to-transparent",
    };
  }

  if (value >= 0.55) {
    return {
      pill: "border-amber-400/20 bg-amber-500/10 text-amber-200",
      bar: "from-amber-400 via-orange-400 to-yellow-300",
      glow: "from-amber-500/18 via-orange-400/8 to-transparent",
    };
  }

  return {
    pill: "border-red-400/20 bg-red-500/10 text-red-200",
    bar: "from-red-500 via-orange-400 to-amber-300",
    glow: "from-red-500/18 via-orange-400/8 to-transparent",
  };
}

export function titleCaseModelName(value: string) {
  const map: Record<string, string> = {
    logreg: "Logistic Regression",
    hgb: "HistGradientBoosting",
    xgboost: "XGBoost",
    LOGREG: "Logistic Regression",
    HGB: "HistGradientBoosting",
    XGBOOST: "XGBoost",
    "Logistic Regression": "Logistic Regression",
    HistGradientBoosting: "HistGradientBoosting",
    XGBoost: "XGBoost",
  };

  return map[value] ?? value;
}

export function formatDriverName(value: string | null | undefined) {
  if (!value) return "N/A";

  const map: Record<string, string> = {
    VER: "Max Verstappen",
    PER: "Sergio Perez",
    LEC: "Charles Leclerc",
    SAI: "Carlos Sainz",
    HAM: "Lewis Hamilton",
    RUS: "George Russell",
    NOR: "Lando Norris",
    PIA: "Oscar Piastri",
    ALO: "Fernando Alonso",
    STR: "Lance Stroll",
    GAS: "Pierre Gasly",
    OCO: "Esteban Ocon",
    ALB: "Alex Albon",
    SAR: "Logan Sargeant",
    BOT: "Valtteri Bottas",
    ZHO: "Zhou Guanyu",
    TSU: "Yuki Tsunoda",
    RIC: "Daniel Ricciardo",
    DEV: "Nyck de Vries",
    MAG: "Kevin Magnussen",
    HUL: "Nico Hulkenberg",
    LAW: "Liam Lawson",
    BEA: "Oliver Bearman",
    COL: "Franco Colapinto",
  };

  return map[value] ?? value;
}