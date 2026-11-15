# One-transfer journey planner

The screen accepts an SKM origin station, Warsaw departure date/time and a ZTM destination name. It plans exactly **SKM → approved cached walk → ZTM**, using local static feeds. It does not provide realtime, arbitrary transfers or global routing. No feed downloads, ORS calls or database writes occur during search.

## Stop lookup

`GET /api/transit/journeys/stops?operator=skm&query=Wrzeszcz&limit=25`

`operator` is `skm` or `ztm`, `query` has at most 120 characters, and `limit` is 1–100. Results include `is_realtime=false`, `groups`, and `has_more`. A group contains `name`, `operator` and concrete `stops` with their original namespaced IDs and metadata. The UI uses names, not stop IDs.

SKM groups share an exact normalized name. ZTM grouping removes only a trailing two-digit pole suffix and then groups the exact normalized name. This is a destination selection convention, **not approval of walking access or geographic merging**. Distinct names remain distinct. Location types other than 0 are excluded. Coordinates are not used to invent transfers. The plan input supports up to 32 concrete stops per selected group.

## Plan request

`POST /api/transit/journeys/plan`

Example using real origin/destination IDs from the inspected local feeds:

```json
{
  "origin_stop_id": "skm:7534",
  "destination_stop_id": "ztm:2033",
  "departure_date": "2026-11-13",
  "departure_time": "17:00",
  "max_results": 3
}
```

For a name with multiple poles, replace the singular field with `origin_stop_ids` or `destination_stop_ids`. Each side requires exactly one singular ID or nonempty list; duplicates are removed and IDs must match the operator. `max_results` is 1–3. IDs are verified in the imported database.

Date/time represents Warsaw civil time, not the GTFS service date. For a repeated DST hour add `departure_offset` (`+02:00` or `+01:00`). Ambiguous hours without an offset and nonexistent hours return 422 with a readable explanation. The UI asks which occurrence to use. GTFS times retain the existing local-noon-minus-12-elapsed-hours interpretation and support values above 24:00. All ordering and duration comparisons use UTC instants.

## Search and ranking

1. Search SKM departures at/after the requested instant within six elapsed hours.
2. For each exact trip/service-day/boarding occurrence, examine all later usable alighting occurrences at registered transfer stations.
3. Examine every approved directional link at those stops, requiring fresh ORS cache with matching current coordinates. Never infer links from names or distances.
4. Compare scheduled ZTM departures from each exact approved pole and usable destination occurrences later on the same ZTM trip. Boarding and destination arrival must fall inside the search horizon. Reject negative-margin transfers using the existing pure evaluator.
5. Rank reachable journeys by margin band (≥2 minutes before 0–<2), destination arrival instant, total duration from SKM boarding, waiting after the walk, and deterministic IDs/occurrences. For repeated stops in a destination group keep the earliest usable destination arrival per exact journey.

The ranking does not prefer Gdańsk Główny, Zaspa, line 158 or a particular operator route. The **current registry** has only four links from `skm:7500` to `ztm:2001`, `ztm:2135`, `ztm:2136`, `ztm:1021`. Walking-cache entries alone do not extend it. Synthetic tests register another downstream interchange to verify cross-hub comparison. Extending real coverage requires separate approval and fresh directional walking data.

The first ranked result is recommended; at most two alternatives follow. A safe-margin journey can rank ahead of a faster tight transfer. Results are explicitly limited to supported links and the six-hour window; they are not claimed to be globally fastest. Walking remains estimated, rounded up to full minutes, without a physical SKM platform guarantee.

## Response

Every result contains:

- `origin`: exact SKM boarding stop, trip, route, service day, sequence and departure;
- `arrival`: later stop occurrence of that same SKM trip at the interchange;
- `link`: approved directional pair, stops, current cache metrics/provenance and conservative walking minutes;
- `departure`: exact ZTM boarding occurrence and departure;
- `destination`: usable later stop on that same ZTM trip, including arrival;
- `evaluation`: existing pure transfer result at zero simulated delay;
- `total_minutes`: destination arrival minus SKM boarding;
- `initial_wait_minutes`, `elapsed_from_request_minutes`, `waiting_minutes` and `risk` (`estimated` or `tight`).

The envelope includes `is_realtime=false`, `schedule_status=planned`, selected stop IDs, the requested departure instant, search window, source metadata/validity/attribution, excluded links, counts, ranking reason, limitations and `has_more`. The API preserves trip/route/service/sequence identity and full offset-aware datetimes.

Empty outcomes: `no_skm`, `no_transfer_link`, `walking_unavailable`, `no_destination_service`, `no_reachable`. A found result uses `found`. No route is represented as an explicit state, never an invented zero-minute walk. Source/operator/date errors return 404/422/503 as appropriate. A whole-window coverage failure returns 422 rather than a successful partial search.

## Bounds and isolation

Per request: 200 SKM departures, 100 registered links, 2,000 ZTM departures per pole, 2,000 matching downstream occurrences per query and 50,000 comparison operations. Exceeding a count returns 409 `search_limit_exceeded` instead of selecting the best of a silently truncated candidate set. A SQLite progress handler interrupts SQL work after an eight-second deadline; store errors return 503. This is bounded local-MVP search, not a general network router.

GTFS is read within one read-only snapshot. Walking estimates are read once per registered pair for the request. Scenario storage is untouched. Search and stop lookup never initialize a database or call ORS.

## Simulation and UI

The UI validates response identities and clears old results as soon as search fields change. AbortController, disposed flags and request/course keys prevent older plans/evaluations from replacing current selections. Native name suggestions preserve exact IDs internally. Grouped poles are all submitted; the backend selects the actual alighting occurrence.

`POST /api/transit/transfers/search` evaluates the selected exact SKM interchange arrival and ZTM departure using the existing pure engine. The UI also compares both sources' archive SHA-256 and import timestamps against the plan, rejecting an evaluation after reimport even if the interchange times are unchanged: origin and destination legs may have changed. The 0–30 slider changes only simulated delay, keeping both courses fixed. Its value is retained on alternative selection and search edits; while a new plan is absent the screen is neutral. It does not update scheduled destination arrival or fetch a different train. Re-searching refreshes cache assumptions explicitly. Original SVG assets/SMIL, Kinetic background and reduced-motion handling remain intact.

## Verification

Backend fixtures cover multiple downstream hubs, exact poles, destination sequence, calendar exceptions, conservative walking, stale/missing/no_route cache, 2/0/−1 margins, ranking, bounds, midnight, extended GTFS hours and both DST transitions. Frontend tests validate identity/provenance and stale-response rejection. The Edge suite uses only synthetic API responses and checks the form, alternatives, retained delay, errors, keyboard, geometry and original animations.

The inspected local-feed smoke case (historical 2026-11-13, not live information): Gdańsk Wrzeszcz `skm:7534`, SKM `skm:284819` at 17:02 → Gdańsk Główny 17:09 → 3 minutes estimated walk to `ztm:2001` → tram 6 `ztm:6202611131653_21_006-08` at 17:15 → Strzyża PKM 01 `ztm:2033` at 17:36; initial margin 3 minutes. Selection is based on the imported snapshot and current cache; it is not a route recommendation for another date.
