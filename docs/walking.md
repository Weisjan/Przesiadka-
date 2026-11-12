# Saved walking estimates with OpenRouteService

The original optional CLI calculates one directional pair, **`skm:7500 → ztm:2001`**, through OpenRouteService (ORS). A separate [nearby-candidate CLI](nearby.md) now supports bounded, opt-in imports for additional geographic candidates and defaults to dry-run. Results remain **estimates**, not measured walking times or confirmation of platform-to-platform paths. Neither command changes the transfer engine, GTFS files, `transit.db`, scenarios or demos.

## Provider contract and reuse

Checked on **12 November 2026** against primary sources:

- [HeiGIT migration announcement](https://ask.openrouteservice.org/t/deprecating-api-openrouteservice-org-in-favour-of-api-heigit-org/7912/): use `https://api.heigit.org/openrouteservice/v2/directions/foot-walking/json`, replacing the deprecated `api.openrouteservice.org` host.
- [Directions reference](https://giscience.github.io/openrouteservice/api-reference/endpoints/directions/requests-and-return-types): POST JSON; read `routes[0].summary.distance` in metres and `duration` in seconds. The [official FAQ](https://giscience.github.io/openrouteservice/frequently-asked-questions.html) confirms `[longitude, latitude]` order.
- [Current HeiGIT terms](https://account.heigit.org/info/tos): ORS results are **CC-BY-SA 4.0**, with attribution `© openrouteservice by HeiGIT | Data from OpenStreetMap`. The rendered JavaScript page was inspected. The older staging page says CC-BY 4.0 and is not used as the current license.
- [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) permits copying/adaptation subject to attribution, a license link, identifying changes and applicable ShareAlike conditions. Preserve these notices for exported results and derived data. Seconds-to-minutes rounding is explicitly identified; this integration does not change the application's code license.

No explicit persistent-storage prohibition or mandatory deletion period was found in the current terms. Stored results retain attribution, license, terms URL and review date. The cache periods below are **application policy**, not a provider retention rule. Recheck terms before distribution/extension. Requests must respect the actual account quota; no particular plan is assumed.

## Explicit CLI import

From `backend/`, preview the pair without a key, network request or write:

```powershell
uv run python -m app.walking skm:7500 ztm:2001 --dry-run
```

The existing GTFS import supplies these original coordinates, in the order sent to ORS:

```json
{
  "from_stop_id": "skm:7500",
  "to_stop_id": "ztm:2001",
  "coordinates": [
    [18.6443487, 54.3565922],
    [18.645663339105, 54.355509269859]
  ]
}
```

For a real import, put the key only in the CLI process environment. This optional PowerShell prompt avoids placing its value in history or a file:

```powershell
$env:ORS_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'ORS_API_KEY' -AsSecureString)).Password
try {
    uv run python -m app.walking skm:7500 ztm:2001 --max-requests 1
} finally {
    Remove-Item Env:\ORS_API_KEY
}
```

Do not put the key in arguments, the frontend, source/configuration files or chat. Only `ORS_API_KEY` from the process environment is read. The API server needs no key to read saved estimates. Missing/invalid keys produce readable errors without showing their values.

The original CLI prints IDs, coordinates, profile, cache status and request budget **before** sending a request. Its allowlist still enables only the pair above. Additional directional candidates use the separate controlled command documented in [nearby discovery](nearby.md); they do not automatically become journey-search links.

Rerunning the command resumes from a fresh saved result, without a key or another request. `--refresh` explicitly replaces a still-current result. `--max-requests` bounds **all attempts, including retries**, to 1–3 (default 2) for this one command. This is not a shared quota manager across concurrent processes; run imports sequentially.

`--transit-database` overrides the read-only GTFS path; `--database` overrides the separate walking database. Defaults match the API's `PRZESIADKA_TRANSIT_PATH` and `PRZESIADKA_WALKING_PATH`. Keep CLI/API paths consistent. Existing databases with the wrong application ID/schema are rejected before writes or provider requests.

## Network handling

- Fixed HTTPS endpoint, `Authorization` header, no query-string key. Redirects are rejected to prevent forwarding credentials. Geometry/instructions are disabled; only summary metrics are retained.
- Ten-second timeout per attempt; response JSON limited to 64 KiB. Coordinates and finite positive metrics are validated, including MVP limits of 20 km / 180 min.
- Retry only transient network/timeouts and HTTP 408/500/502/503/504 within the budget, waiting 1 then 2 seconds. A provider `Retry-After` stops automatic replay instead of requesting before the required wait. TLS validation failures are not retried.
- HTTP 401 requires checking the key. HTTP 403 can mean permissions or daily quota. HTTP 429 is **not automatically retried**: wait according to the provider quota/Retry-After. The [official quota FAQ](https://giscience.github.io/openrouteservice/frequently-asked-questions.html) distinguishes daily/minutely limits; repeated imports must not evade them.
- Documented route errors 2009/2010 and an explicit empty route list produce `no_route`. Malformed/error responses never become zero-time routes. Provider error text and arbitrary metadata are not printed or stored. Failed refreshes preserve the previous record.

FastAPI startup, our read-only API, course selection and slider movements **never call ORS**. There is no automatic refresh or routing write endpoint.

## SQLite and freshness

`backend/data/walking.db` is created only when saving a result and is ignored by the existing `*.db` rule. Its dedicated application ID/schema protects scenario/GTFS databases. `walking_transfers` has primary key `(from_stop_id,to_stop_id)` and stores:

- directional IDs, status, distance in metres, raw walking seconds, `source="openrouteservice"`, `confidence="estimated"`;
- UTC `calculated_at` (local receipt/save time, not a physical measurement) and `expires_at`;
- both original longitude/latitude pairs, profile and provider endpoint;
- attribution, license, license/terms URLs and terms review date.

An upsert affects only its directional pair. A → B never supplies B → A. Reads never create a missing database. Both GTFS endpoints are read in one snapshot. Freshness requires unchanged coordinates/profile/endpoint/license review, no future calculation timestamp and an unexpired result. Successful entries expire after **30 days**, `no_route` after **24 hours**. A GTFS reimport with identical coordinates does not invalidate an independent walking estimate; moved stops do.

Seconds/metres remain unchanged. The API also returns `walking_minutes=ceil(walking_seconds/60)` and `rounding="ceil_to_full_minutes"`, preserving the existing integer-minute evaluation contract. No-route metrics are `null`, never zero. Expired/coordinate-mismatched rows remain inspectable as `stale` and are not auto-applied.

## Read-only API and frontend

```text
GET /api/transit/walking-transfers?from_stop_id=skm:7500&to_stop_id=ztm:2001
```

Response fields: `status` (`available`, `missing`, `stale`, `no_route`), both IDs and `estimate`. Missing entries have `estimate: null`; other states include saved metrics/provenance. Unknown stops return 404, invalid pairs/coordinates 422 and unavailable/corrupt databases 503. None of these paths requests ORS.

Dark Transit loads the saved estimate when its supported pair becomes available. Fresh results fill the walking field and show **Szacowany czas dojścia na podstawie OpenRouteService**, distance, calculation date, rounding and attribution/license. A manual edit, including one made during the request, takes precedence. Delay slider movements and analysis retries neither refetch the estimate nor overwrite that value. Changing the pair clears the old input and requests the new direction. Pair-switch logic is tested independently; the current UI still supports only the original pair.

Missing/stale/no-route/read-error states retain manual input instead of inventing an estimate. The SKM feed lacks physical platform details and an OSM pedestrian graph does not establish current crossings, platform access or step-free accessibility. Scenarios and fictional demos keep their own walking values.

## Verification and live-data limitation

Run the existing [README test commands](../README.md#testing). `tests/fixtures/ors_walking.json` is **synthetic**, not a measured Gdańsk route. Tests block ORS network calls and cover parsing, coordinate order, errors/retries, secret redaction, directional persistence, freshness/rollback, read-only API and manual-override precedence.

During the initial implementation, the actual CLI dry-run confirmed the pair/coordinates, while the real import stopped at **missing ORS_API_KEY**, before a provider request or database creation. Browser auto-fill checks used a synthetic fixture in a separate temporary walking database with ORS calls blocked; their diagnostic screenshots are not evidence of a real walking route.

On **13 November 2026**, a read-only check confirmed the subsequently imported local result: **213.5 m / 153.7 seconds**, `source=openrouteservice`, `confidence=estimated`, still fresh for the unchanged GTFS coordinates. No new provider request or physical path validation was performed. See [nearby discovery](nearby.md#local-observation-13-november-2026) for candidate counts and a zero-request dry-run. The next step is to review one additional candidate before a bounded execution.
