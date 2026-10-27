import { strict as assert } from "node:assert";
import { describe, it } from "node:test";
// Explicit .ts extension: required for dependency-free `node --test`
// type-stripping (the runtime resolves it); tsc without
// allowImportingTsExtensions cannot, hence the targeted suppression below.
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { API_BASE, readJson, resolveBase, type FetchLike } from "./http.ts";

// Characterisation tests for the shared HTTP transport (lib/http.ts):
// every endpoint module delegates fetch -> JSON -> typed-error here.
// Run with `node --test lib/http.test.ts` (Node >= 22, no new dependencies).

function okFetcher(payload: unknown): FetchLike {
  return (async () => ({ ok: true, status: 200, json: async () => payload })) as FetchLike;
}

describe("http transport", () => {
  it("readJson returns the parsed body on ok", async () => {
    const data = await readJson<{ a: number }>(
      okFetcher({ a: 1 }),
      "http://x/y",
      undefined,
      () => new Error("must not throw"),
    );
    assert.deepEqual(data, { a: 1 });
  });

  it("readJson throws the caller factory on !ok with status and body", async () => {
    const fetcher = (async () => ({
      ok: false,
      status: 422,
      json: async () => ({ error: "nope" }),
    })) as FetchLike;
    await assert.rejects(
      readJson(
        fetcher,
        "http://x/y",
        { cache: "no-store" },
        (status, body) => new Error(`E${status}:${JSON.stringify(body)}`),
      ),
      /E422:\{"error":"nope"\}/,
    );
  });

  it("readJson passes url and init to the fetcher untouched", async () => {
    let seen: { url: string; init?: RequestInit } | null = null;
    const fetcher = (async (url: string, init?: RequestInit) => {
      seen = { url, init };
      return { ok: true, status: 200, json: async () => ({}) };
    }) as FetchLike;
    const init = { method: "POST", cache: "no-store" as RequestCache };
    await readJson(fetcher, "http://x/y?z=1", init, () => new Error("x"));
    assert.equal(seen!.url, "http://x/y?z=1");
    assert.deepEqual(seen!.init, init);
  });

  it("resolveBase prefers the explicit base and falls back to API_BASE", () => {
    assert.equal(resolveBase("http://custom:1"), "http://custom:1");
    assert.equal(resolveBase(undefined), API_BASE);
  });

  it("API_BASE defaults to the local backend", () => {
    assert.equal(API_BASE, "http://127.0.0.1:8000");
  });
});
