const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export async function getRaces() {
  const res = await fetch(`${API_BASE}/races`, { cache: "no-store" });
  if (!res.ok) throw new Error("Failed to load races");
  return res.json();
}

export async function predictEnsemble(year: number, event: string) {
  const res = await fetch(`${API_BASE}/predict/ensemble`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ year, event }),
  });

  if (!res.ok) throw new Error("Failed to predict ensemble");
  return res.json();
}

export async function predictSingleModel(
  year: number,
  event: string,
  model: string
) {
  const res = await fetch(`${API_BASE}/predict/single-model`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ year, event, model }),
  });

  if (!res.ok) throw new Error("Failed to predict single model");
  return res.json();
}