"""Jolpica F1 (Ergast-compatible) source client (D4 — Tier-B ingestion).

Focused adapter plumbing that plugs into the D3 orchestration core
(``v2.ingestion.run_unit``): HTTP response -> parsed pages -> caller-owned
normalisation (``v2.tierb``) -> D3 validation -> atomic Parquet -> manifest
state. This module owns source access + pagination + bounded retries only;
it never writes canonical output and never touches manifests.

Design rules (from the D4 brief):
- STDLIB ONLY (urllib). No framework-heavy client, no new dependency.
- Centralised identity: base URL, User-Agent, timeout, page limit and the
  retryable-status policy live in ``JolpicaConfig`` — endpoint strings are
  built in exactly one place (``ENDPOINTS`` + ``build_url``).
- OFFLINE BY DEFAULT: importing this module, building a client, or running
  config validation performs zero network I/O. Real HTTP requires an
  explicitly injected ``transport`` (tests) or the ``V2_ALLOW_NETWORK=1``
  environment opt-in (CLI real ingestion). There is no implicit download.
- Pagination honours the D1 finding (Jolpica max page size 100): every
  request carries explicit ``limit``/``offset``; the loop reads MRData
  ``total``/``limit``/``offset`` metadata, stops deterministically, handles
  empty pages, and fails loudly on malformed or non-progressing pagination
  instead of looping forever.
- Retries reuse the D3 taxonomy (``v2.errors``) and ``RetryPolicy`` budget
  fields. ``sleep_fn`` is injectable so tests never sleep.
- Provenance: every fetch appends a portable ``FetchRecord`` (provider,
  base URL identity, endpoint/query scope, timestamp, run-agnostic request
  detail). Run ID / schema version / season scope join at the orchestration
  layer (run scope + manifest entry), keeping this module free of D3 types.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable

from raceintel.errors import ErrorCategory, IngestionError
from raceintel.retry import RetryPolicy, compute_backoff

# --------------------------------------------------------------------------
# Centralised API identity (D4 §3). Exactly one place defines these.
# --------------------------------------------------------------------------

PROVIDER_NAME = "jolpica"
BASE_URL = "https://api.jolpi.ca/ergast/f1"
# Custom User-Agent per provider requirement. Generic product token only:
# no credentials, no personal information, no contact details.
USER_AGENT = "f1-intelligence-v2-data-platform/1.0"
CLIENT_VERSION = "1"

# Explicit opt-in for real network I/O. Normal unit tests never set this;
# the CLI refuses live ingestion without it (clear CONFIG failure).
NETWORK_ENV_VAR = "V2_ALLOW_NETWORK"

# HTTP statuses worth a bounded retry. Everything else 4xx fails fast;
# 404 means "no such season/scope upstream" (skip, don't retry).
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
NOT_FOUND_STATUS = 404

# Hard ceiling on pages per collection fetch: termination is guaranteed
# even if a server ignores limit/offset (non-progress is detected earlier;
# this is the backstop, not the mechanism).
DEFAULT_MAX_PAGES = 1000


@dataclass(frozen=True)
class JolpicaConfig:
    """All client behaviour in one value object (injectable in tests)."""

    base_url: str = BASE_URL
    user_agent: str = USER_AGENT
    timeout_s: float = 30.0
    page_limit: int = 100  # D1: Jolpica maximum page size
    max_pages: int = DEFAULT_MAX_PAGES
    # Politeness delay between paginated requests (rate respect). Zero in
    # tests via explicit config; never sleeps unless a fetch actually runs.
    # Default 8.0 s: sustained ~1 req/s ingestion was observed to trip the
    # provider's HTTP 429 rate limit after ~10 seasons, and ~0.3 req/s after
    # ~12 more (2026-09-08); ~0.12 req/s plus burst/cooldown operation stays
    # under it. Keeps full-history runs polite without touching
    # timeout/retry budgets.
    politeness_s: float = 8.0
    # Upper bound for any single sleep honouring Retry-After: respected
    # "where practical without creating an unbounded wait".
    retry_after_max_s: float = 60.0
    sleep_fn: Callable[[float], None] = time.sleep

    def __post_init__(self):
        if self.page_limit < 1 or self.page_limit > 100:
            raise ValueError("page_limit must be within 1..100 (Jolpica max)")
        if self.timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        if self.max_pages < 1:
            raise ValueError("max_pages must be >= 1")


@dataclass(frozen=True)
class HttpResponse:
    """Transport-level response (real or fake). Headers lower-cased."""

    status: int
    body: bytes
    headers: dict = field(default_factory=dict)


# ``transport(url, headers, timeout_s) -> HttpResponse``. Plain callable:
# the default urllib transport is used only for live ingestion; tests
# inject fakes, so normal tests never touch the network.
TransportFn = Callable[[str, dict, float], HttpResponse]


@dataclass
class FetchRecord:
    """Portable provenance for one HTTP request (no absolute paths)."""

    provider: str
    base_url: str
    endpoint: str  # path relative to base_url, e.g. "/2023/results.json"
    query: dict  # effective query params actually sent
    status: int
    fetched_at: str  # UTC ISO, set at response time
    items: int | None = None  # collection items on this page, if known

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "endpoint": self.endpoint,
            "query": dict(self.query),
            "status": self.status,
            "fetched_at": self.fetched_at,
            "items": self.items,
        }


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def urllib_transport(url: str, headers: dict, timeout_s: float) -> HttpResponse:
    """Real stdlib transport. Raises mapped IngestionError, never raw."""
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as resp:
            status = int(resp.status)
            body = resp.read()
            raw_headers = dict(resp.headers or {})
    except urllib.error.HTTPError as exc:
        # HTTPError still carries the response body; read it for debugging
        # context, then map the status through the shared classifier.
        try:
            exc.read()
        except Exception:
            pass
        raise _classify_status(exc.code, url) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # DNS failure, refused connection, reset, socket timeout, ... all
        # transient: bounded retry, never fail-fast on first blip.
        raise IngestionError.transient(
            f"connection failure for {url}: {type(exc).__name__}") from None
    except Exception as exc:  # boundary: preserve category + context
        raise IngestionError(
            ErrorCategory.UNEXPECTED,
            f"{type(exc).__name__} during fetch of {url}") from exc
    return HttpResponse(status=status, body=body,
                        headers={k.lower(): v
                                 for k, v in raw_headers.items()})


def _classify_status(status: int, url: str) -> IngestionError:
    if status in RETRYABLE_STATUS:
        return IngestionError.transient(f"HTTP {status} for {url}")
    if status == NOT_FOUND_STATUS:
        return IngestionError.missing(f"HTTP 404 for {url}")
    if 400 <= status < 500:
        # Our request is wrong (bad scope/path/params): retrying the same
        # request cannot fix it — fail fast, never retry.
        return IngestionError(
            ErrorCategory.CONFIG, f"HTTP {status} for {url}")
    if 500 <= status < 600:
        return IngestionError.transient(f"HTTP {status} for {url}")
    return IngestionError(
        ErrorCategory.UNEXPECTED, f"HTTP {status} for {url}")


def _parse_retry_after(headers: dict, cap_s: float) -> float | None:
    """Retry-After in delta-seconds form, bounded by ``cap_s``.

    HTTP-date form is deliberately NOT parsed: clock-skew arithmetic risks
    unbounded waits; the bounded exponential backoff covers that case.
    Returns None when absent/unparseable (caller falls back to backoff).
    """
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, min(float(str(raw).strip()), cap_s))
    except (ValueError, TypeError):
        return None


class JolpicaClient:
    """Bounded, paginated Jolpica reader. No writes, no manifests."""

    def __init__(self, config: JolpicaConfig | None = None,
                 transport: TransportFn | None = None,
                 retry_policy: RetryPolicy | None = None):
        self.config = config or JolpicaConfig()
        self._transport = transport
        # Default is a SINGLE attempt: D3 orchestration (run_with_retry via
        # run_unit) owns the retry budget, so live ingestion never nests two
        # budgets (client 3 x orchestration 3 = 9 HTTP requests per failed
        # operation). Callers may inject an explicit multi-attempt policy
        # (unit tests do); the live Tier-B path uses this default. The wait
        # loop below honours Retry-After within the injected bounds (see
        # fetch_json); with the single-attempt default a 429 surfaces as
        # TRANSIENT immediately and the D3 exponential backoff applies.
        self.retry_policy = retry_policy or RetryPolicy(
            max_attempts=1, sleep_fn=self.config.sleep_fn)
        self.fetch_log: list[FetchRecord] = []
        self.notes: list[str] = []  # source anomalies worth reporting

    # -- URL construction (single place; no scattered endpoint strings) --
    def build_url(self, endpoint: str, params: dict | None = None) -> str:
        base = self.config.base_url.rstrip("/")
        path = endpoint if endpoint.startswith("/") else f"/{endpoint}"
        query = urllib.parse.urlencode(params or {})
        # Ergast-compatible identity: every resource ends in ".json".
        return f"{base}{path}.json" + (f"?{query}" if query else "")

    def _transport_or_live(self) -> TransportFn:
        if self._transport is not None:
            return self._transport
        if os.environ.get(NETWORK_ENV_VAR) != "1":
            raise IngestionError.config(
                f"real network ingestion requires {NETWORK_ENV_VAR}=1 "
                f"(refusing live request to {self.config.base_url}); "
                f"tests must inject a fake transport")
        return urllib_transport

    def _headers(self) -> dict:
        return {"User-Agent": self.config.user_agent,
                "Accept": "application/json"}

    # -- bounded single GET ------------------------------------------------
    def fetch_json(self, endpoint: str,
                   params: dict | None = None) -> dict:
        """GET one endpoint with bounded retries. Returns parsed MRData.

        Error mapping (D3 taxonomy):
        - timeout / connection failure / 429 / retryable 5xx -> TRANSIENT
          (bounded retry; Retry-After honoured up to ``retry_after_max_s``,
          never an unbounded wait; then standard exponential backoff);
        - 404 -> MISSING_SESSION (skip, no retry);
        - other 4xx -> CONFIG (fail fast, no retry);
        - malformed JSON -> TRANSIENT (bounded: truncation is the common
          cause; persistent garbage exhausts the budget and FAILS);
        - valid JSON with wrong shape -> returned as-is; shape validation
          is the caller's job (structural errors -> VALIDATION there).
        """
        url = self.build_url(endpoint, params)
        transport = self._transport_or_live()
        policy = self.retry_policy
        last_error: IngestionError | None = None
        for attempt in range(1, policy.max_attempts + 1):
            try:
                resp = transport(url, self._headers(),
                                 self.config.timeout_s)
            except IngestionError as exc:
                last_error = exc
                if (exc.category not in policy.retryable
                        or attempt >= policy.max_attempts):
                    raise
                self.config.sleep_fn(compute_backoff(
                    attempt, policy.backoff_base_s,
                    policy.backoff_factor, policy.backoff_max_s))
                continue
            if resp.status != 200:
                exc = _classify_status(resp.status, url)
                last_error = exc
                if (exc.category not in policy.retryable
                        or attempt >= policy.max_attempts):
                    raise exc
                wait = _parse_retry_after(
                    resp.headers, self.config.retry_after_max_s)
                if wait is None:
                    wait = compute_backoff(
                        attempt, policy.backoff_base_s,
                        policy.backoff_factor, policy.backoff_max_s)
                self.config.sleep_fn(wait)
                continue
            try:
                parsed = json.loads(resp.body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = IngestionError.transient(
                    f"malformed JSON from {url}: {type(exc).__name__}")
                if attempt >= policy.max_attempts:
                    raise last_error from None
                self.config.sleep_fn(compute_backoff(
                    attempt, policy.backoff_base_s,
                    policy.backoff_factor, policy.backoff_max_s))
                continue
            self.fetch_log.append(FetchRecord(
                provider=PROVIDER_NAME, base_url=self.config.base_url,
                endpoint=endpoint, query=dict(params or {}),
                status=resp.status, fetched_at=_utc_now_iso()))
            return parsed
        assert last_error is not None  # max_attempts >= 1 guarantees a pass
        raise last_error

    # -- paginated collection fetch ----------------------------------------
    def fetch_collection(self, endpoint: str,
                         collection_path: tuple[str, ...],
                         params: dict | None = None,
                         limit: int | None = None) -> list:
        """Fetch every page of an MRData collection (list of raw dicts).

        ``collection_path`` walks from the parsed body to the item list,
        e.g. ``("MRData", "RaceTable", "Races")``. Requests carry explicit
        ``limit``/``offset``; MRData ``total``/``limit``/``offset`` metadata
        (strings or ints upstream) drives deterministic termination:

        - stop when ``offset + limit >= total`` (total known);
        - else stop on an empty page or a short page (total unknown);
        - empty page before ``total`` is reached ends the loop with a
          recorded anomaly note (data kept, incompleteness flagged);
        - a page whose echoed ``offset`` differs from the requested one,
          unparseable MRData metadata, or ``max_pages`` exhaustion raises
          VALIDATION (never an infinite loop, never silent truncation).
        """
        wanted = limit or self.config.page_limit
        collected: list = []
        offset = 0
        pages = 0
        total: int | None = None
        while True:
            pages += 1
            if pages > self.config.max_pages:
                raise IngestionError.validation(
                    f"pagination exceeded max_pages={self.config.max_pages} "
                    f"for {endpoint} (non-progressing or runaway collection)")
            query = dict(params or {})
            query["limit"] = str(wanted)
            query["offset"] = str(offset)
            parsed = self.fetch_json(endpoint, query)
            items, meta = _extract_collection(parsed, collection_path,
                                              endpoint)
            if total is None:
                total = meta.get("total")
            echoed = meta.get("offset")
            if echoed is not None and echoed != offset:
                raise IngestionError.validation(
                    f"non-progressing pagination for {endpoint}: requested "
                    f"offset {offset}, server echoed {echoed}")
            if self.fetch_log:
                self.fetch_log[-1].items = len(items)
            if len(items) == 0:
                if total is not None and offset < total:
                    self.notes.append(
                        f"empty page at offset {offset} of total {total} "
                        f"for {endpoint}: stopped early, data incomplete")
                break
            collected.extend(items)
            if total is not None and offset + wanted >= total:
                break
            if total is None and len(items) < wanted:
                break  # short final page, no total metadata to lean on
            offset += wanted
            self.config.sleep_fn(self.config.politeness_s)
        return collected


def _extract_collection(parsed: object, collection_path: tuple[str, ...],
                        endpoint: str) -> tuple[list, dict]:
    """Walk ``collection_path``; parse MRData paging metadata.

    Raises VALIDATION on structurally invalid responses (valid JSON, wrong
    shape) — fail fast, never retry what a retry cannot fix.
    """
    if not isinstance(parsed, dict):
        raise IngestionError.validation(
            f"structurally invalid response for {endpoint}: top level is "
            f"{type(parsed).__name__}, expected object with MRData")
    node: object = parsed
    for key in collection_path:
        if not isinstance(node, dict) or key not in node:
            raise IngestionError.validation(
                f"structurally invalid response for {endpoint}: missing key "
                f"'{key}' along {'/'.join(collection_path)}")
        node = node[key]
    if not isinstance(node, list):
        raise IngestionError.validation(
            f"structurally invalid response for {endpoint}: "
            f"{'/'.join(collection_path)} is {type(node).__name__}, "
            f"expected list")
    meta: dict = {}
    mrdata = parsed.get("MRData")
    if not isinstance(mrdata, dict):
        raise IngestionError.validation(
            f"structurally invalid response for {endpoint}: missing MRData "
            f"pagination metadata")
    for key in ("total", "limit", "offset"):
        raw = mrdata.get(key)
        if raw is None:
            continue
        try:
            meta[key] = int(str(raw).strip())
        except (ValueError, TypeError):
            raise IngestionError.validation(
                f"malformed pagination metadata for {endpoint}: "
                f"{key}={raw!r} is not an integer") from None
    return node, meta


# --------------------------------------------------------------------------
# Tier-B endpoint strategy (one table; D4 §2 "do not scatter endpoint
# strings"). Paths are relative to BASE_URL; the ".json" suffix is added by
# build_url uniformly.
# --------------------------------------------------------------------------

def season_schedule_endpoint(season: int) -> str:
    return f"/{season}"


def season_drivers_endpoint(season: int) -> str:
    return f"/{season}/drivers"


def season_constructors_endpoint(season: int) -> str:
    return f"/{season}/constructors"


def season_results_endpoint(season: int) -> str:
    return f"/{season}/results"


def season_driver_standings_endpoint(season: int) -> str:
    return f"/{season}/driverStandings"


def season_constructor_standings_endpoint(season: int) -> str:
    return f"/{season}/constructorStandings"


ENDPOINTS = {
    "schedule": season_schedule_endpoint,
    "drivers": season_drivers_endpoint,
    "constructors": season_constructors_endpoint,
    "results": season_results_endpoint,
    "driver_standings": season_driver_standings_endpoint,
    "constructor_standings": season_constructor_standings_endpoint,
}
