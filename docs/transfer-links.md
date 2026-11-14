# Approved directional links

`LINKS` in `backend/app/gtfs/transfer_search.py` explicitly approves four destinations from `skm:7500`. Nearby discovery and walking-cache rows remain independent of approval.

| ID | Destination | Audited courses on 2026-11-13 |
| --- | --- | --- |
| `gdansk-glowny-skm-ztm-01` | `ztm:2001`, Dworzec Główny 01 | 637 departures, tram lines including 2, 6, 8, 12 |
| `gdansk-glowny-skm-pks-01` | `ztm:2135`, Dworzec PKS 01 | 59 departures, tram 11 toward Strzyża PKM |
| `gdansk-glowny-skm-pks-02` | `ztm:2136`, Dworzec PKS 02 | 63 departures, tram 11 toward Lawendowe Wzgórze |
| `gdansk-glowny-skm-ztm-08` | `ztm:1021`, Dworzec Główny 08 | 168 departures, bus routes including 106, 111, 112 |

All audited stops have location_type=0. Approval uses exact IDs and scheduled boarding occurrences. Physical SKM platforms and access paths remain unverified. Cache values are read at request time.

## Screen contract

`GET /api/transit/journeys` takes `leg`, `date`, optional `link_id`, and optional departure `after`. Dates are civil Warsaw dates; occurrences retain service date and stop sequence. Omitting link_id selects the original 2001 pair.

`POST /api/transit/transfers/search` requires link_id, arrival_trip_id, arrival_service_date, departure_route_id, departure_trip_id and departure_service_date. Optional arrival_stop_sequence/departure_stop_sequence disambiguate repeated stops. delay_minutes ranges from 0 to 30. The selected departure must fall within six hours of scheduled arrival.

The result includes the exact arrival/departure and evaluation margin/status. Walking comes exclusively from a fresh directional cache entry whose coordinates match the GTFS snapshot. Missing/stale/no_route returns 422, cache errors 503. The API never calls ORS. The pure evaluator performs UTC arithmetic; the frontend displays its result.

The single screen presents the SKM train picker, a destination field, course cards, status figure and slider. The backend selects a boarding stop from approved links. Pair/course changes invalidate old results. Both request aborts and input identity checks guard against late responses. Provider attribution accompanies the cached walking estimate.

## Suggestions for a selected train

`POST /api/transit/transfers/suggest` reads the local GTFS and walking stores. Its JSON body contains `arrival_stop_id`, `arrival_trip_id`, `arrival_service_date`, `arrival_stop_sequence`, `query`, optional `delay_minutes` (0–30, default 0) and optional `limit` (1–20, default 12). The arrival identifies one exact stop occurrence and service day. The frontend sends zero delay for initial selection and uses the existing `/transfers/search` endpoint when the slider changes.

The search covers six elapsed hours from the scheduled arrival, across approved links from that SKM station. A link needs current directional walking cache. A destination name must match an accessible downstream stop of the exact ZTM trip, with a known arrival time. Line and direction searches retain each trip's exact route, stop, direction and service date. Calendars and extended GTFS hours use the existing schedule helpers.

Ranking uses three bands in order of preference. Courses with at least two minutes of margin come first, followed by courses with a margin from zero to under two minutes, followed by missed courses. Each band sorts by remaining waiting time after walking, then departure instant, walking minutes, link ID, route ID, trip ID, service date and stop sequence. A recommendation always has a nonnegative margin. Walking minutes are the cache's conservative ceiling of walking seconds.

Responses include `recommendation`, ranked `results`, `reason`, available `directions`, `excluded_links`, `search_window`, `limitations` and `is_realtime=false`. Outcomes are `choose_destination`, `recommended`, `no_match`, `no_reachable` or `walking_unavailable`. An empty query returns direction suggestions without choosing a destination. Responses contain at most 20 courses and 12 directions, with `has_more` indicating additional matched courses. Feed coverage failures return HTTP 422, missing arrival/link HTTP 404 and candidate overflow HTTP 409. Each approved stop has a hard limit of 2000 departures per search window.

The screen keeps the selected departure fixed during delay simulation. A new train or goal clears old results. Manual alternatives come from the current query's matching courses. Fetch cancellation, input keys and response validation protect against older suggestions, walking estimates and evaluations.

