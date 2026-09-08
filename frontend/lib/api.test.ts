import { strict as assert } from "node:assert";
import { execFileSync } from "node:child_process";
import { beforeEach, describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping (the runtime resolves it); tsc without
// allowImportingTsExtensions cannot, hence the targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { getRaces, predictEnsemble, predictSingleModel } from "./api.ts";

// Characterisation tests for the centralised API layer (lib/api.ts):
// endpoint URLs, HTTP methods and request bodies the page depends on.
// fetch is stubbed — no network, no server.
// Run with `node --test lib/api.test.ts` (Node >= 22, no new dependencies).

type FetchCall = { url: string; init?: RequestInit };
let calls: FetchCall[];
let payload: unknown;

function stubFetch() {
  calls = [];
  (globalThis as Record<string, unknown>).fetch = async (
    url: string,
    init?: RequestInit,
  ) => {
    calls.push({ url, init });
    return {
      ok: true,
      json: async () => payload,
    };
  };
}

describe("api layer", () => {
  beforeEach(() => {
    stubFetch();
    payload = {};
  });

  it("getRaces calls GET /races on the default base", async () => {
    payload = { races: [] };
    const data = await getRaces();
    assert.deepEqual(data, { races: [] });
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8000/races");
    assert.deepEqual(calls[0].init, { cache: "no-store" });
  });

  it("predictEnsemble POSTs year/event to /predict/ensemble", async () => {
    await predictEnsemble(2023, "Bahrain Grand Prix");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8000/predict/ensemble");
    assert.equal(calls[0].init?.method, "POST");
    assert.deepEqual(JSON.parse(calls[0].init?.body as string), {
      year: 2023,
      event: "Bahrain Grand Prix",
    });
  });

  it("predictSingleModel POSTs year/event/model", async () => {
    await predictSingleModel(2022, "Monaco Grand Prix", "xgboost");
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "http://127.0.0.1:8000/predict/single-model");
    assert.deepEqual(JSON.parse(calls[0].init?.body as string), {
      year: 2022,
      event: "Monaco Grand Prix",
      model: "xgboost",
    });
  });

  it("throws when the API responds with an error", async () => {
    (globalThis as Record<string, unknown>).fetch = async () => ({ ok: false });
    await assert.rejects(getRaces(), /Failed to load races/);
    await assert.rejects(
      predictEnsemble(2023, "Bahrain Grand Prix"),
      /Failed to predict ensemble/,
    );
    await assert.rejects(
      predictSingleModel(2023, "Bahrain Grand Prix", "hgb"),
      /Failed to predict single model/,
    );
  });

  it("honours NEXT_PUBLIC_API_BASE (read at module load)", () => {
    // API_BASE is captured at import time, so verify in a fresh process.
    const out = execFileSync(
      process.execPath,
      [
        "-e",
        "globalThis.fetch = async (u) => { console.log('URL=' + u);" +
          " return { ok: true, json: async () => ({}) }; };" +
          " import('./lib/api.ts').then((m) => m.getRaces());",
      ],
      {
        cwd: new URL("..", import.meta.url),
        env: { ...process.env, NEXT_PUBLIC_API_BASE: "http://api:9000" },
        encoding: "utf8",
      },
    );
    assert.match(out, /URL=http:\/\/api:9000\/races/);
  });
});
