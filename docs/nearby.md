# Nearby GTFS stops and controlled walking imports

Nearby discovery proposes **geographic candidates**, not validated interchange links. It uses only the imported GTFS database and the saved walking cache. It does not call ORS, change schedules or create transfer links. Search/UI availability is controlled by the separate [approved-link registry](transfer-links.md).

## Candidate helper

The internal nearby helper supplies geographic candidates to the explicit CLI, independently of approved links.

## Default dry-run CLI

Run from the repository root:

```powershell
uv run --directory backend python -m app.walking.candidates skm:7500 --max-pairs 3 --max-requests 3
```

This command defaults to **dry-run**, requires no key and makes no network requests or database writes. `--dry-run` is also accepted explicitly. It prints the total/returned candidates, cache hits, selected IDs and coordinates, rejected counts, deferred pairs, planned initial requests and the request budget. `has_more_candidates` warns about discovery truncation; `deferred_pairs` counts pending returned candidates beyond `max-pairs`.

Only `--execute` enables provider calls. For a deliberate one-pair execution, with the key already in the process environment:

```powershell
uv run --directory backend python -m app.walking.candidates skm:7500 --execute --max-pairs 1 --max-requests 1 --interval-seconds 2
```

This chooses the nearest pending candidate, not necessarily `ztm:2001`. Review the dry-run first. The original `python -m app.walking skm:7500 ztm:2001` command retains its original one-pair allowlist and behavior; the new module is a separate, controlled candidate importer.

- `max-pairs` and `max-requests` each default to 3 and have hard limits **1–20**. Every actual attempt, including retries, consumes the global request budget. Retries can leave selected pairs unfinished; `remaining_selected_pairs` and `stopped_reason` identify this explicitly.
- `interval-seconds` defaults to 2, range **1–60**; it spaces every attempt, including retries, using a monotonic clock. Existing transient-error backoff also applies.
- Fresh positive and negative cache entries are skipped unless `--refresh` is explicit. Each successful result is committed independently, so rerunning resumes from saved pairs.
- Any provider failure stops the batch. HTTP 429 or a `Retry-After` response is not replayed automatically. Resume manually after the provider's required interval/quota reset; do not repeatedly restart to evade it.
- Limits apply to one process. Run imports sequentially: this is not an account-wide or cross-process quota manager.
- `--radius-m`, `--limit`, `--transit-database` and `--database` control discovery and local paths. Defaults match the existing API configuration.
- IDs/coordinates and budgets are printed **before** any provider request. The key stays in the Authorization header, read only from `ORS_API_KEY`; it is never printed or stored.

No ORS calls run at FastAPI startup, in GET requests or on slider movements. No real ORS calls were made while implementing this extension.

## Cache quality and attribution

The existing [walking cache policy](walking.md#sqlite-and-freshness) remains unchanged: directional upserts, raw fractional seconds, `confidence=estimated`, source coordinates and provenance; 30-day positive/24-hour negative expiry. Any change to either GTFS coordinate invalidates the estimate immediately, even before expiry. A failed refresh preserves the old row. `no_route` has null metrics, never zero. Consumers needing integer minutes must round **up**, not down.

Saved results retain `© openrouteservice by HeiGIT | Data from OpenStreetMap`, license/terms links and the terms review date. See [provider contract and reuse](walking.md#provider-contract-and-reuse) for CC BY-SA 4.0 obligations. Discovery distances are independent geometric calculations; they are not ORS results.

## Local observation: 13 November 2026

With the existing local imports, `skm:7500` yields **23 candidates within 500 m, 1 cache hit**. Some actual results:

| Destination | GTFS name | Straight-line metres | Cache |
| --- | --- | ---: | --- |
| `ztm:2135` | Dworzec PKS 01 | 62.8 | missing |
| `ztm:2136` | Dworzec PKS 02 | 68.1 | missing |
| `ztm:1021` | Dworzec Główny 08 | 75.9 | missing |
| `ztm:1023` | Dworzec Główny 06 | 89.0 | missing |
| `ztm:1257` | Dworzec PKS 03 | 93.0 | missing |
| `ztm:2001` | Dworzec Główny 01 | 147.5 | available |

The existing `skm:7500 → ztm:2001` row still reads **213.5 walking metres / 153.7 seconds** (3 minutes rounded up), source `openrouteservice`, confidence `estimated`. This was a read of the previously saved result, not a new provider call or physical route validation.

The default dry-run selects three missing pairs, skips one fresh cache entry, defers 19 pending pairs and plans up to three initial requests within a three-attempt budget. **Actual ORS requests: zero.** These observations depend on the local feed/cache snapshot and expiry; they are not a current transport timetable guarantee.

## Verification

Run the [repository test commands](../README.md#testing). `backend/tests/test_nearby.py` uses isolated synthetic GTFS/walking databases and blocks external calls. It covers geographic boundaries, multiple poles/IDs, coordinate rejection, directional cache/freshness, GTFS coordinate changes, read-only API errors, request budgets, rate limiting/retries, refresh, resume and secret-safe dry-runs. Existing walking tests cover provider response validation and persistence. Automated tests do not contact ORS.
