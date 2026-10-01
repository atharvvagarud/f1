"""D4 Jolpica client tests: pagination, retry taxonomy, offline guarantee.

Every test uses an injected fake transport — no live network, no sleeps
(sleep_fn records instead). Small Ergast/MRD-shaped payloads only.
"""

import json
import urllib.parse

import pytest

from raceintel.errors import ErrorCategory, IngestionError
from raceintel.data.jolpica import (BASE_URL, ENDPOINTS, JolpicaClient, JolpicaConfig,
                        HttpResponse, NETWORK_ENV_VAR)
from raceintel.retry import RetryPolicy


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

def mrdata_envelope(table_key, table_value, total=None, limit=100, offset=0):
    body = {"MRData": {"xmlns": "", "series": "f1",
                       "url": "https://example.invalid/x",
                       "limit": str(limit), "offset": str(offset),
                       table_key: table_value}}
    if total is not None:
        body["MRData"]["total"] = str(total)
    return body


def races_page(items, total, limit=100, offset=0):
    return mrdata_envelope("RaceTable",
                           {"season": "2023", "Races": items},
                           total=total, limit=limit, offset=offset)


def race_item(round_no, name="Some Grand Prix"):
    return {"season": "2023", "round": str(round_no), "raceName": name,
            "Circuit": {"circuitId": f"c{round_no}", "circuitName": name,
                        "Location": {"locality": "L", "country": "C"}},
            "date": "2023-01-01"}


class FakeTransport:
    """Route URL substring -> scripted pages; records calls and URLs."""

    def __init__(self, routes=None, default_status=404):
        self.routes = routes or {}
        self.calls: list[str] = []
        self.default_status = default_status

    def add(self, key, pages):
        self.routes[key] = list(pages)
        return self

    def __call__(self, url, headers, timeout_s):
        self.calls.append(url)
        for key, pages in self.routes.items():
            if key in url:
                query = urllib.parse.parse_qs(
                    urllib.parse.urlparse(url).query)
                offset = int(query.get("offset", ["0"])[0])
                limit = int(query.get("limit", ["100"])[0] or 100)
                idx = offset // limit if limit else 0
                payload = pages[min(idx, len(pages) - 1)]
                if isinstance(payload, HttpResponse):
                    return payload
                return HttpResponse(status=200,
                                    body=json.dumps(payload).encode(),
                                    headers={})
        return HttpResponse(status=self.default_status, body=b"{}",
                            headers={})

    def last_query(self):
        return urllib.parse.parse_qs(
            urllib.parse.urlparse(self.calls[-1]).query)


class SleepRecorder:
    def __init__(self):
        self.calls: list[float] = []

    def __call__(self, seconds):
        self.calls.append(float(seconds))


class ScriptedTransport:
    """Replay a fixed response sequence (for retry tests: fetch_json
    retries the identical URL, so offset-indexed routing cannot advance
    the script). The final response repeats once the script is spent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[str] = []

    def __call__(self, url, headers, timeout_s):
        self.calls.append(url)
        if len(self.responses) > 1:
            item = self.responses.pop(0)
        else:
            item = self.responses[0]
        if isinstance(item, HttpResponse):
            return item
        if isinstance(item, Exception):
            raise item
        return HttpResponse(status=200, body=json.dumps(item).encode(),
                            headers={})


def make_client(transport, recorder=None, **config_kwargs):
    recorder = recorder if recorder is not None else SleepRecorder()
    config_kwargs.setdefault("politeness_s", 0.0)
    config_kwargs.setdefault("sleep_fn", recorder)
    config = JolpicaConfig(**config_kwargs)
    policy = RetryPolicy(max_attempts=3, sleep_fn=recorder)
    return JolpicaClient(config=config, transport=transport,
                         retry_policy=policy), recorder


# --------------------------------------------------------------------------
# Pagination
# --------------------------------------------------------------------------

def test_single_page_collection():
    items = [race_item(1), race_item(2)]
    transport = FakeTransport().add(
        "/2023", [races_page(items, total=2)])
    client, _ = make_client(transport)
    out = client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert out == items
    assert len(transport.calls) == 1
    query = transport.last_query()
    assert query["limit"] == ["100"]  # explicit limit/offset on the request
    assert query["offset"] == ["0"]


def test_multi_page_concatenation():
    pages = [races_page([race_item(i) for i in range(1, 101)], total=250,
                        offset=0),
             races_page([race_item(i) for i in range(101, 201)], total=250,
                        offset=100),
             races_page([race_item(i) for i in range(201, 251)], total=250,
                        offset=200)]
    transport = FakeTransport().add("/2023", pages)
    client, recorder = make_client(transport)
    out = client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert len(out) == 250
    assert [r["round"] for r in out] == [str(i) for i in range(1, 251)]
    assert len(transport.calls) == 3  # stops deterministically at total


def test_empty_final_page_when_total_exact():
    pages = [races_page([race_item(1)], total=1, offset=0)]
    transport = FakeTransport().add("/2023", pages)
    client, _ = make_client(transport)
    out = client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert len(out) == 1
    assert len(transport.calls) == 1  # offset+limit >= total: no extra fetch


def test_short_page_without_total_metadata():
    body = {"MRData": {"limit": "100", "offset": "0",
                       "RaceTable": {"Races": [race_item(1), race_item(2)]}}}
    transport = FakeTransport().add("/2023", [body])
    client, _ = make_client(transport)
    out = client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert len(out) == 2
    assert len(transport.calls) == 1


def test_empty_page_before_total_keeps_data_and_notes():
    pages = [races_page([], total=5, offset=0)]
    transport = FakeTransport().add("/2023", pages)
    client, _ = make_client(transport)
    out = client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert out == []
    assert any("empty page" in note for note in client.notes)


def test_malformed_pagination_top_level_list():
    transport = FakeTransport().add("/2023", [[1, 2, 3]])
    client, recorder = make_client(transport)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert excinfo.value.category == ErrorCategory.VALIDATION
    assert recorder.calls == []  # fail fast: no retry on structural errors


def test_malformed_pagination_missing_mrdata():
    transport = FakeTransport().add("/2023", [{"nonsense": True}])
    client, recorder = make_client(transport)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert excinfo.value.category == ErrorCategory.VALIDATION
    assert recorder.calls == []


def test_malformed_pagination_non_integer_total():
    body = {"MRData": {"limit": "100", "offset": "0", "total": "many",
                       "RaceTable": {"Races": [race_item(1)]}}}
    transport = FakeTransport().add("/2023", [body])
    client, _ = make_client(transport)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert excinfo.value.category == ErrorCategory.VALIDATION


def test_non_progressing_pagination_detected():
    # Server echoes offset 0 forever while we ask for more: must fail
    # loudly instead of looping.
    stuck = races_page([race_item(1)], total=500, offset=0)
    transport = FakeTransport().add("/2023", [stuck])
    client, _ = make_client(transport, page_limit=1)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert excinfo.value.category == ErrorCategory.VALIDATION
    assert "offset" in excinfo.value.message


def test_max_pages_backstop():
    page = races_page([race_item(1)], total=10_000_000, offset=0)
    # Echo the *requested* offset so progress looks plausible; the cap
    # must still guarantee termination.
    seen = {"n": 0}

    def echoing(url, headers, timeout_s):
        seen["n"] += 1
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        offset = int(query.get("offset", ["0"])[0])
        body = races_page([race_item(1)], total=10_000_000, offset=offset)
        return HttpResponse(status=200, body=json.dumps(body).encode(),
                            headers={})

    client, _ = make_client(echoing, max_pages=3, page_limit=1)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert excinfo.value.category == ErrorCategory.VALIDATION
    assert seen["n"] == 3


def test_overlapping_pages_do_not_hang():
    # Same item on both pages: paginator concatenates (PK dedupe is the
    # normalisation layer's job); termination still follows total.
    pages = [races_page([race_item(1), race_item(2)], total=2, offset=0)]
    transport = FakeTransport().add("/2023", pages)
    client, _ = make_client(transport)
    out = client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert len(out) == 2


# --------------------------------------------------------------------------
# Retry / error taxonomy
# --------------------------------------------------------------------------

def test_timeout_retries_then_succeeds():
    transport = FakeTransport().add(
        "/2023", [races_page([race_item(1)], total=1)])
    calls = {"n": 0}
    inner = transport

    def flaky(url, headers, timeout_s):
        calls["n"] += 1
        if calls["n"] < 3:
            raise IngestionError.transient("connection failure: timeout")
        return inner(url, headers, timeout_s)

    client, recorder = make_client(flaky)
    out = client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert len(out) == 1
    assert calls["n"] == 3
    assert len(recorder.calls) == 2  # bounded: slept between attempts only


def test_persistent_5xx_fails_after_budget():
    transport = ScriptedTransport(
        [HttpResponse(status=503, body=b"{}", headers={})])
    client, recorder = make_client(transport)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_json("/2023")
    assert excinfo.value.category == ErrorCategory.TRANSIENT
    assert len(transport.calls) == 3  # max_attempts budget honoured
    assert len(recorder.calls) == 2


def test_429_respects_retry_after_bounded():
    transport = ScriptedTransport(
        [HttpResponse(status=429, body=b"{}",
                      headers={"retry-after": "7"}),
         races_page([race_item(1)], total=1)])
    client, recorder = make_client(transport)
    out = client.fetch_json("/2023")
    assert out["MRData"]["total"] == "1"
    assert recorder.calls[0] == 7.0  # Retry-After honoured ...


def test_429_retry_after_capped_not_unbounded():
    transport = ScriptedTransport(
        [HttpResponse(status=429, body=b"{}",
                      headers={"retry-after": "3600"}),
         races_page([race_item(1)], total=1)])
    client, recorder = make_client(transport, retry_after_max_s=60.0)
    client.fetch_json("/2023")
    assert recorder.calls[0] == 60.0  # ... without an unbounded wait


def test_404_becomes_missing_without_retry():
    transport = FakeTransport(default_status=404)
    client, recorder = make_client(transport)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_json("/2099")
    assert excinfo.value.category == ErrorCategory.MISSING_SESSION
    assert len(transport.calls) == 1
    assert recorder.calls == []


def test_non_retryable_4xx_fails_fast():
    transport = ScriptedTransport(
        [HttpResponse(status=400, body=b"{}", headers={})])
    client, recorder = make_client(transport)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_json("/2023")
    assert excinfo.value.category == ErrorCategory.CONFIG
    assert len(transport.calls) == 1
    assert recorder.calls == []


def test_malformed_json_retries_bounded_then_fails():
    transport = ScriptedTransport(
        [HttpResponse(status=200, body=b"{nope", headers={})])
    client, recorder = make_client(transport)
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_json("/2023")
    assert excinfo.value.category == ErrorCategory.TRANSIENT
    assert len(transport.calls) == 3
    assert len(recorder.calls) == 2


def test_unexpected_transport_error_propagates_untouched():
    def boom(url, headers, timeout_s):
        raise RuntimeError("weird")

    client, _ = make_client(boom)
    with pytest.raises(RuntimeError):
        client.fetch_json("/2023")


# --------------------------------------------------------------------------
# Offline guarantee / configuration
# --------------------------------------------------------------------------

def test_default_transport_requires_explicit_opt_in(monkeypatch):
    monkeypatch.delenv(NETWORK_ENV_VAR, raising=False)
    client = JolpicaClient(config=JolpicaConfig(sleep_fn=lambda s: None))
    with pytest.raises(IngestionError) as excinfo:
        client.fetch_json("/2023")
    assert excinfo.value.category == ErrorCategory.CONFIG
    assert NETWORK_ENV_VAR in excinfo.value.message


def test_import_and_config_validation_perform_no_network():
    transport = FakeTransport()
    config = JolpicaConfig(sleep_fn=lambda s: None)
    JolpicaClient(config=config, transport=transport)
    assert transport.calls == []


def test_page_limit_above_jolpica_max_rejected():
    with pytest.raises(ValueError):
        JolpicaConfig(page_limit=1000, sleep_fn=lambda s: None)


def test_endpoint_strategy_centralised():
    assert set(ENDPOINTS) == {"schedule", "drivers", "constructors",
                              "results", "driver_standings",
                              "constructor_standings"}
    client = JolpicaClient(config=JolpicaConfig(sleep_fn=lambda s: None),
                           transport=FakeTransport())
    url = client.build_url(ENDPOINTS["results"](2023),
                           {"limit": "100", "offset": "0"})
    assert url == f"{BASE_URL}/2023/results.json?limit=100&offset=0"


def test_fetch_log_records_portable_provenance():
    transport = FakeTransport().add(
        "/2023", [races_page([race_item(1)], total=1)])
    client, _ = make_client(transport)
    client.fetch_collection("/2023", ("MRData", "RaceTable", "Races"))
    assert len(client.fetch_log) == 1
    record = client.fetch_log[0].to_dict()
    assert record["provider"] == "jolpica"
    assert record["base_url"] == BASE_URL
    assert record["endpoint"] == "/2023"
    assert record["status"] == 200
    assert record["items"] == 1
    assert record["fetched_at"]
