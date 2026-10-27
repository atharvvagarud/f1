// Shared frontend HTTP transport (post-V3 C5).
//
// Single ownership for: base-URL resolution, the injectable fetch shape,
// and fetch -> JSON -> typed-error handling. Endpoint modules (lib/v2.ts,
// lib/spatial.ts, feature *Client.ts, lib/api.ts) keep their routes,
// request construction, response types, and error classes; they delegate
// only the identical transport mechanics here.
//
// Behaviour contract (pinned by lib/http.test.ts + existing client tests):
// - API_BASE is captured at module load from NEXT_PUBLIC_API_BASE.
// - readJson parses JSON once, then throws the caller's error factory on
//   !ok, else returns the typed body. Factories preserve each client's
//   exact legacy error type and message.

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export type FetchLike = (
  url: string,
  init?: RequestInit,
) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

export type ErrorFactory = (status: number, body: unknown) => Error;

export async function readJson<T>(
  fetcher: FetchLike,
  url: string,
  init: RequestInit | undefined,
  toError: ErrorFactory,
): Promise<T> {
  const res = await fetcher(url, init);
  const body = (await res.json()) as T;
  if (!res.ok) {
    throw toError(res.status, body);
  }
  return body;
}

export const resolveBase = (base?: string): string => base ?? API_BASE;
