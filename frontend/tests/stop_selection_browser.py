"""Browser regression tests with synthetic API responses and no database access.

Start Vite with npm run dev, then run this file with a Python environment that
already provides Playwright and Chromium (or Edge on Windows). Override the UI
address with PRZESIADKA_UI_URL and screenshot directory with PRZESIADKA_ARTIFACTS.
"""

import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from playwright.async_api import async_playwright, expect


DAY = "2026-11-13"
ORIGIN = {"operator": "skm", "stop_id": "skm:7500", "stop_name": "Gdańsk Główny"}
STOPS = [
    ("2001", "Dworzec Główny 01", "17:51", 3, 6),
    ("2135", "Dworzec PKS 01", "17:47", 2, 3),
    ("2136", "Dworzec PKS 02", "17:50", 4, 4),
    ("1021", "Dworzec Główny 08", "17:49", 5, 2),
]
SOURCES = [{"operator": operator, "name": operator, "imported": True,
            "service_start_date": DAY, "service_end_date": DAY,
            "attribution": "Dane testowe", "documentation_url": "https://example.invalid"}
           for operator in ("skm", "ztm")]


def walking(stop):
    code, _, _, minutes, _ = stop
    return {"status": "available", "from_stop_id": ORIGIN["stop_id"], "to_stop_id": f"ztm:{code}",
            "estimate": {"status": "available", "source": "openrouteservice", "confidence": "estimated",
                         "walking_seconds": minutes * 60, "walking_minutes": minutes, "distance_m": 200,
                         "calculated_at": f"{DAY}T00:00:00+01:00", "expires_at": "2026-12-13T00:00:00+01:00",
                         "attribution": "Dane testowe ORS/OSM", "license": "CC-BY-SA-4.0",
                         "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                         "terms_url": "https://account.heigit.org/info/tos", "rounding": "ceil_to_full_minutes"}}


def transfer_link(stop):
    code, name, *_ = stop
    return {"id": f"fixture-{code}", "arrival_stop": ORIGIN,
            "departure_stop": {"operator": "ztm", "stop_id": f"ztm:{code}", "stop_name": name, "stop_code": code},
            "walking_time_source": "estimated", "approval_status": "approved", "walking": walking(stop)}


LINKS = [transfer_link(stop) for stop in STOPS]


def journey(leg, stop=STOPS[0]):
    code, name, time, *_ = stop
    operator = "skm" if leg == "arrival" else "ztm"
    instant = f"{DAY}T{'17:42' if leg == 'arrival' else time}:00+01:00"
    return {"operator": operator, "operator_name": operator, "stop_id": ORIGIN["stop_id"] if leg == "arrival" else f"ztm:{code}",
            "stop_name": ORIGIN["stop_name"] if leg == "arrival" else name,
            "trip_id": f"{operator}:fixture-{code}", "route_id": f"{operator}:fixture-route-{code}",
            "line": "S1" if leg == "arrival" else "8", "route_type": 2 if leg == "arrival" else 0,
            "direction": "Gdańsk" if leg == "arrival" else {"2001": "Oliwa", "2135": "Strzyża PKM", "2136": "Uniwersytet", "1021": "Przegalina"}[code], "direction_id": 0,
            "service_id": f"{operator}:fixture-service", "service_date": DAY, "stop_sequence": 1,
            "arrival_at": instant, "departure_at": instant, "pickup_type": 0, "drop_off_type": 0}


class SuggestionUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        self.addAsyncCleanup(self.playwright.stop)
        self.browser = await self.playwright.chromium.launch(channel="msedge" if os.name == "nt" else "chromium", headless=True)
        self.addAsyncCleanup(self.browser.close)
        self.context = await self.browser.new_context(viewport={"width": 1440, "height": 1000}, locale="pl-PL")
        self.requests, self.errors = [], []
        self.margin_override = None
        self.cache_minutes = None
        self.hold_path = self.hold_code = None
        self.held, self.release, self.delivered = asyncio.Event(), asyncio.Event(), asyncio.Event()
        self.addCleanup(self.release.set)
        await self.context.route("**/api/**", self.route_api)
        self.page = await self.context.new_page()
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        await self.page.goto(os.environ.get("PRZESIADKA_UI_URL", "http://127.0.0.1:5173"))
        self.arrival_card = self.page.get_by_role("region", name="Twój pociąg SKM", exact=True)
        self.card = self.page.get_by_role("region", name="Sugerowana przesiadka ZTM", exact=True)
        self.goal = self.card.get_by_role("searchbox", name="Dokąd chcesz jechać?", exact=True)
        self.slider = self.page.get_by_role("slider", name="Opóźnienie pociągu SKM", exact=True)
        self.margin = self.page.locator('output[aria-label^="Zapas czasu:"]')
        self.figure = self.page.locator('[data-figure-state]')
        await expect(self.arrival_card.get_by_role("button")).to_be_enabled()
        self.artifacts = Path(os.environ.get("PRZESIADKA_ARTIFACTS") or tempfile.mkdtemp(prefix="przesiadka-suggestions-ui-"))
        self.artifacts.mkdir(parents=True, exist_ok=True)

    async def asyncTearDown(self):
        self.release.set()
        self.assertEqual(self.errors, [])

    def candidate(self, stop):
        link = transfer_link(stop)
        minutes = self.cache_minutes if self.cache_minutes is not None and stop[0] == '2001' else stop[3]
        link['walking']['estimate'].update(walking_minutes=minutes, walking_seconds=minutes*60)
        return {"link": {**link, "walking_minutes": minutes}, "departure": journey("departure", stop),
                "match": {"kind": "stop" if stop[0] == "2136" else "direction", "stop_id": "ztm:test-destination", "stop_name": "Uniwersytet"},
                "evaluation": self.evaluation(stop[4] - (minutes-stop[3]))}

    def evaluation(self, margin):
        return {"margin_minutes": margin, "delay_threshold_minutes": 6,
                "status": "Zdążysz" if margin > 0 else "Na styk" if margin == 0 else "Nie zdążysz",
                "has_safe_margin": True, "expected_stop_arrival_at": f"{DAY}T17:45:00+01:00"}

    def requested_arrival(self, trip_id=None):
        item = journey("arrival")
        if trip_id == "skm:second":
            item.update(trip_id=trip_id, arrival_at=f"{DAY}T17:43:00+01:00", departure_at=f"{DAY}T17:43:00+01:00")
        return item

    async def route_api(self, route):
        request = route.request
        path = urlsplit(request.url).path
        query = {key: values[0] for key, values in parse_qs(urlsplit(request.url).query).items()}
        headers = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "content-type"}
        if request.method == "OPTIONS":
            await route.fulfill(status=204, headers={**headers, "Access-Control-Allow-Methods": "GET,POST"})
            return
        body = request.post_data_json if request.method == "POST" else None
        self.requests.append((path, query, body))
        identity = (body or {}).get("query", "")
        code = ((body or {}).get("link_id") or query.get("link_id") or "fixture-2001").removeprefix("fixture-")
        stop = next((item for item in STOPS if item[0] == code), STOPS[0])
        if path == "/api/transit/sources":
            data = {"is_realtime": False, "sources": SOURCES}
        elif path == "/api/transit/transfer-links":
            other = {**LINKS[0], "id": "fixture-other-station", "arrival_stop": {**ORIGIN, "stop_id": "skm:other"}}
            other.pop("walking")
            data = {"is_realtime": False, "links": [*LINKS, other]}
        elif path == "/api/transit/journeys":
            data = {"is_realtime": False, "realtime_delay": None, "has_more": False,
                    "journeys": [self.requested_arrival(), self.requested_arrival("skm:second")], "source": SOURCES[0]}
        elif path == "/api/transit/transfers/suggest":
            if identity == "expired":
                await route.fulfill(status=422, json={"detail": {"code": "feed_out_of_range", "message": "Data poza zakresem lokalnego feedu."}}, headers=headers)
                return
            stop = STOPS[1] if "strzy" in identity.lower() else STOPS[2] if "uniwersytet" in identity.lower() else STOPS[0]
            results = [self.candidate(item) for item in STOPS] if identity == "8" else [self.candidate(stop)]
            outcome = "recommended" if identity else "choose_destination"
            if identity == "none":
                outcome, results = "no_match", []
            elif identity == "missing":
                outcome, results = "walking_unavailable", []
            elif identity == "unreachable":
                outcome = "no_reachable"
                results[0]["evaluation"] = self.evaluation(-1)
            if body["arrival_trip_id"] == "skm:second":
                for item in results:
                    item["evaluation"]["margin_minutes"] -= 1
            data = {"is_realtime": False, "schedule_status": "planned", "query": identity, "arrival": self.requested_arrival(body["arrival_trip_id"]),
                    "outcome": outcome, "recommendation": results[0] if outcome == "recommended" else None,
                    "results": results if identity else [], "reason": "Preferowany zapas co najmniej 2 min, potem krótsze oczekiwanie.",
                    "has_more": False, "excluded_links": [], "limitations": ["Dojście szacunkowe. Rozkład planowany."],
                    "directions": [{"line": "8", "direction": journey("departure", item)["direction"], "query": "8 " + journey("departure", item)["direction"]} for item in STOPS]}
        elif path == "/api/transit/transfers/search":
            margin = self.margin_override if self.margin_override is not None else stop[4] - body["delay_minutes"]
            minutes = self.cache_minutes if self.cache_minutes is not None and code == '2001' else stop[3]
            margin -= minutes - stop[3]
            if body["arrival_trip_id"] == "skm:second":
                margin -= 1
            data = {"is_realtime": False, "schedule_status": "planned", "arrival": self.requested_arrival(body["arrival_trip_id"]),
                    "link": {"id": body["link_id"], "walking_minutes": minutes},
                    "search_window": {"start_at": f"{DAY}T17:42:00+01:00", "end_at_exclusive": f"{DAY}T23:42:00+01:00"},
                    "limitations": ["Dane testowe"], "results": [{"departure": journey("departure", stop), "evaluation": self.evaluation(margin)}]}
        else:
            self.errors.append(f"Unexpected API request: {path}")
            await route.abort()
            return
        held = path == self.hold_path and self.hold_code in (identity, code)
        if held:
            self.hold_path = None
            self.held.set()
            await self.release.wait()
        try:
            await route.fulfill(json=data, headers=headers)
        except Exception:
            if not held:
                raise
        finally:
            if held:
                self.delivered.set()

    async def choose_train(self, second=False):
        await self.arrival_card.get_by_role("button").click()
        dialog = self.page.get_by_role("dialog")
        await dialog.get_by_label("Data przyjazdu", exact=True).fill(DAY)
        item = self.requested_arrival("skm:second" if second else None)
        courses = dialog.get_by_role("combobox", name="Konkretny kurs", exact=True)
        await expect(courses).to_be_enabled()
        await courses.select_option(json.dumps([item["trip_id"], DAY, 1], separators=(",", ":")))
        await dialog.get_by_role("button", name="Wybierz kurs", exact=True).click()

    async def expect_margin(self, value):
        await expect(self.margin).to_have_attribute("aria-label", f"Zapas czasu: {value:g} minut")

    async def delay(self, value):
        await self.slider.evaluate("""(el,value) => {
            Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el,String(value));
            el.dispatchEvent(new Event('input',{bubbles:true}));
            el.dispatchEvent(new Event('change',{bubbles:true}));
        }""", value)

    async def start_analysis(self):
        await self.choose_train()
        await self.goal.fill("8")
        await self.expect_margin(6)

    async def test_goal_and_manual_course_use_correct_pole_and_walking(self):
        await self.choose_train()
        await expect(self.page.get_by_role("button", name="8 · Oliwa", exact=True)).to_be_visible()
        await expect(self.margin).to_have_count(0)
        await self.page.get_by_role("button", name="8 · Oliwa", exact=True).click()
        await self.expect_margin(6)
        for query, time, margin, minutes in [("Strzyża", "17:47", 3, 2), ("Uniwersytet", "17:50", 4, 4)]:
            await self.goal.fill(query)
            await expect(self.card.locator("time")).to_have_count(0)
            await expect(self.margin).to_have_count(0)
            await self.expect_margin(margin)
            await expect(self.card.locator("time")).to_have_text(time)
            await expect(self.page.get_by_text(f"Szacowane dojście {minutes} min.", exact=False)).to_be_visible()
        await self.goal.fill("8")
        await self.expect_margin(6)
        await self.card.get_by_role("button", name="Inny kurs", exact=False).click()
        alternatives = self.card.get_by_role("group", name="Inne kursy ZTM")
        button = alternatives.get_by_role("button").filter(has_text="Dworzec PKS 01")
        await button.click()
        await self.expect_margin(3)
        await expect(self.card.locator("time")).to_have_text("17:47")
        self.assertEqual([body for path, _, body in self.requests if path.endswith("/search")][-1]["link_id"], "fixture-2135")
        await self.card.get_by_role("button", name="Inny kurs", exact=False).click()
        await button.click()
        await self.expect_margin(3)
        await self.choose_train()
        await self.expect_margin(3)
        await expect(self.page.get_by_role("combobox", name="Przystanek przesiadkowy", exact=True)).to_have_count(0)

    async def test_late_suggestions_cannot_restore_an_old_goal_or_walking(self):
        await self.choose_train()
        self.hold_path, self.hold_code = "/api/transit/transfers/suggest", "8"
        await self.goal.fill("8")
        await asyncio.wait_for(self.held.wait(), 5)
        await self.goal.fill("Strzyża")
        await self.expect_margin(3)
        self.release.set()
        await asyncio.wait_for(self.delivered.wait(), 5)
        await self.expect_margin(3)
        await expect(self.card.locator("time")).to_have_text("17:47")
        await expect(self.page.get_by_text("Szacowane dojście 2 min.", exact=False)).to_be_visible()

    async def test_late_analysis_cannot_restore_an_old_selection(self):
        await self.start_analysis()
        self.hold_path, self.hold_code = "/api/transit/transfers/search", "2001"
        await self.delay(5)
        await asyncio.wait_for(self.held.wait(), 5)
        await self.goal.fill("Strzyża")
        await expect(self.card.locator("time")).to_have_count(0)
        await self.expect_margin(3)
        self.release.set()
        await asyncio.wait_for(self.delivered.wait(), 5)
        await self.expect_margin(3)

    async def test_new_train_invalidates_old_suggestions_and_retains_goal(self):
        await self.start_analysis()
        self.hold_path, self.hold_code = "/api/transit/transfers/suggest", "Strzyża"
        await self.goal.fill("Strzyża")
        await asyncio.wait_for(self.held.wait(), 5)
        await self.choose_train(second=True)
        await self.expect_margin(2)
        self.release.set()
        await asyncio.wait_for(self.delivered.wait(), 5)
        await self.expect_margin(2)
        await expect(self.arrival_card.locator('time')).to_have_text('17:43')
        await expect(self.goal).to_have_value('Strzyża')

    async def test_fast_slider_keeps_course_and_animation(self):
        await self.start_analysis()
        before = sum(path.endswith("/suggest") for path, _, _ in self.requests)
        await self.figure.locator('svg').first.evaluate('el => window.originalSvg = el')
        self.hold_path, self.hold_code = "/api/transit/transfers/search", "2001"
        await self.delay(4)
        await asyncio.wait_for(self.held.wait(), 5)
        await expect(self.figure).to_have_attribute("data-figure-state", "success")
        await self.delay(6)
        await self.delay(8)
        await self.expect_margin(-2)
        self.release.set()
        await asyncio.wait_for(self.delivered.wait(), 5)
        await self.expect_margin(-2)
        await expect(self.card.locator("time")).to_have_text("17:51")
        self.assertEqual(before, sum(path.endswith("/suggest") for path, _, _ in self.requests))
        self.assertTrue(await self.figure.locator('svg').first.evaluate('el => el === window.originalSvg'))

    async def test_refresh_recovers_a_changed_walking_estimate(self):
        await self.start_analysis()
        self.cache_minutes = 4
        await self.delay(1)
        await expect(self.page.get_by_role('alert').filter(has_text='Powiązanie lub szacunek dojścia zmienił się.')).to_be_visible()
        await expect(self.margin).to_have_count(0)
        await self.page.get_by_role('button',name='Odśwież propozycje',exact=True).click()
        await self.expect_margin(5)
        await expect(self.page.get_by_text('Szacowane dojście 4 min.',exact=False)).to_be_visible()
        await expect(self.slider).to_have_value('0')

    async def test_smil_motion_boundaries_crossfade_and_reduced_motion(self):
        await self.start_analysis()
        await self.page.wait_for_timeout(280)
        await self.figure.evaluate("""el => {
            window.fadeSample = null;
            new MutationObserver(() => {
                if (el.dataset.figureState === 'missed' && !window.fadeSample) {
                    setTimeout(() => { window.fadeSample = Array.from(el.querySelectorAll('[data-model]'),
                        model => Number(getComputedStyle(model).opacity)); },90);
                }
            }).observe(el,{attributes:true,attributeFilter:['data-figure-state']});
        }""")
        evidence = []
        previous_time = await self.figure.locator('svg').first.evaluate('el => el.getCurrentTime()')
        bounds = await self.figure.bounding_box()
        for index, (margin, state, cycle) in enumerate([(-1, "missed", "2.4s"), (0, "edge", "0.6s"),
                                                       (1.99, "edge", "0.6s"), (2, "success", "1.2s"), (5, "success", "1.2s")], 1):
            self.margin_override = margin
            await self.delay(index)
            await self.expect_margin(margin)
            await expect(self.figure).to_have_attribute("data-figure-state", state)
            await self.page.wait_for_timeout(280)
            model = self.figure.locator(f'[data-model="{state}"]')
            await expect(model.locator('animate').first).to_have_attribute('dur', cycle)
            before = await model.locator('polyline').first.evaluate('el => Array.from({length:el.animatedPoints.numberOfItems},(_,i)=>{let p=el.animatedPoints.getItem(i);return [p.x,p.y]})')
            first = await self.figure.screenshot()
            current_time = await model.locator('svg').evaluate('el => el.getCurrentTime()')
            self.assertGreater(current_time, previous_time)
            previous_time = current_time
            self.assertEqual(await self.figure.bounding_box(), bounds)
            await self.page.wait_for_timeout(170)
            second = await self.figure.screenshot()
            after = await model.locator('polyline').first.evaluate('el => Array.from({length:el.animatedPoints.numberOfItems},(_,i)=>{let p=el.animatedPoints.getItem(i);return [p.x,p.y]})')
            self.assertNotEqual(before, after)
            self.assertNotEqual(first, second)
            self.assertGreater(await model.locator('svg').evaluate('el => el.getCurrentTime()'), current_time)
            (self.artifacts / f'{state}-{index}-first.png').write_bytes(first)
            (self.artifacts / f'{state}-{index}-second.png').write_bytes(second)
            evidence.append({'margin': margin, 'state': state, 'cycle': cycle, 'points_before': before, 'points_after': after, 'pixels_changed': True})
        fade = await self.page.evaluate('window.fadeSample')
        self.assertTrue(any(0 < opacity < 1 for opacity in fade), fade)
        self.assertAlmostEqual(sum(fade), 1, delta=.1)
        self.assertEqual(await self.figure.locator('[data-model]').first.evaluate('el => getComputedStyle(el).transitionDuration'), '0.25s')
        await self.page.emulate_media(reduced_motion='reduce')
        for svg in await self.figure.locator('svg').all():
            self.assertTrue(await svg.evaluate('el => el.animationsPaused()'))
            self.assertEqual(await svg.evaluate('el => el.getCurrentTime()'), 0)
        static_frame = await self.figure.screenshot()
        await self.page.wait_for_timeout(200)
        self.assertEqual(static_frame, await self.figure.screenshot())
        (self.artifacts/'motion-evidence.json').write_text(json.dumps({'cases':evidence,'crossfade_opacities':fade,'reduced_motion_static':True},indent=2),encoding='utf-8')

    async def test_empty_and_error_states_have_no_false_result(self):
        await self.start_analysis()
        for query, message in [("none", "Brak pasującego kursu"), ("unreachable", "Brak osiągalnego kursu"),
                               ("missing", "Brak aktualnego szacunku dojścia"), ("expired", "Data poza zakresem lokalnego feedu.")]:
            await self.goal.fill(query)
            await expect(self.card.get_by_text(message, exact=False)).to_be_visible()
            await expect(self.margin).to_have_count(0)
            await expect(self.card.locator('time')).to_have_count(0)
            await expect(self.figure).to_have_attribute('data-figure-state','idle')

    async def test_responsive_keyboard_and_single_visible_model(self):
        await self.start_analysis()
        await self.page.wait_for_timeout(280)
        for width in (1440, 768, 390):
            await self.page.set_viewport_size({'width':width,'height':1000})
            self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            card, goal = await self.card.bounding_box(), await self.goal.bounding_box()
            self.assertGreaterEqual(goal['x'], card['x'])
            self.assertLessEqual(goal['x']+goal['width'], card['x']+card['width'])
            self.assertGreaterEqual(goal['height'],44)
            await self.goal.focus()
            await self.page.keyboard.press('Tab')
            await expect(self.card.get_by_role('button',name='Inny kurs',exact=False)).to_be_focused()
            self.assertNotEqual(await self.card.get_by_role('button',name='Inny kurs',exact=False).evaluate('el=>getComputedStyle(el).outlineStyle'),'none')
            await self.page.screenshot(path=str(self.artifacts/f'suggestions-{width}.png'),full_page=True)
        opacity = await self.figure.locator('[data-model]').evaluate_all('els=>els.map(el=>Number(getComputedStyle(el).opacity))')
        self.assertEqual(sorted(opacity),[0,0,1])
        print(f'Screenshots and motion evidence: {self.artifacts}')

    async def test_kinetic_background_moves_and_stops_for_reduced_motion(self):
        background = self.page.locator('[data-kinetic-background]')
        await expect(background).to_have_attribute('aria-hidden', 'true')
        self.assertEqual(await background.evaluate('el => getComputedStyle(el).pointerEvents'), 'none')
        await self.page.wait_for_timeout(650)
        strand = background.locator('g').first
        transform_before = await strand.evaluate('el => getComputedStyle(el).transform')
        first = await background.screenshot()
        await self.page.wait_for_timeout(1100)
        second = await background.screenshot()
        self.assertNotEqual(first, second)
        self.assertNotEqual(transform_before, await strand.evaluate('el => getComputedStyle(el).transform'))
        (self.artifacts/'background-first.png').write_bytes(first)
        (self.artifacts/'background-second.png').write_bytes(second)
        await self.start_analysis()
        performance = []
        for width in (1440, 390):
            await self.page.set_viewport_size({'width': width, 'height': 1000})
            await self.page.wait_for_timeout(100)
            measurement = await self.page.evaluate("""() => new Promise(resolve => {
                const intervals = [];
                const longTasks = [];
                const observer = new PerformanceObserver(entries => {
                    for (const entry of entries.getEntries()) longTasks.push(entry.duration);
                });
                observer.observe({ type: 'longtask' });
                let previous;
                const start = performance.now();
                function sample(now) {
                    if (previous !== undefined) intervals.push(now - previous);
                    previous = now;
                    if (now - start < 1800) requestAnimationFrame(sample);
                    else {
                        observer.disconnect();
                        intervals.sort((a,b) => a-b);
                        resolve({ width: innerWidth, frameCount: intervals.length,
                            medianFrameMs: intervals[Math.floor(intervals.length/2)],
                            p95FrameMs: intervals[Math.floor(intervals.length*.95)],
                            longTasks, animationCount: document.querySelector('[data-kinetic-background]').getAnimations({subtree:true}).length });
                    }
                }
                requestAnimationFrame(sample);
            })""")
            self.assertGreater(measurement['frameCount'], 10)
            performance.append(measurement)
        await self.page.emulate_media(reduced_motion='reduce')
        await self.page.wait_for_function("document.querySelector('[data-kinetic-background]').getAnimations({subtree:true}).length === 0")
        await self.page.wait_for_timeout(100)
        static = await background.screenshot()
        await self.page.wait_for_timeout(250)
        self.assertEqual(static, await background.screenshot())
        (self.artifacts/'background-verification.json').write_text(json.dumps({
            'pixels_changed': True, 'strand_transform_changed': True,
            'reduced_motion_static': True, 'performance': performance,
        }, indent=2), encoding='utf-8')

    async def test_fractional_margin_fits_without_moving_result(self):
        await self.start_analysis()
        for width in (1440, 768, 390):
            await self.page.set_viewport_size({'width': width, 'height': 1000})
            self.margin_override = 6
            await self.delay(0)
            await self.expect_margin(6)
            initial = await self.margin.bounding_box()
            figure = await self.figure.bounding_box()
            for delay, margin in enumerate((1.983333, -1.983333, 358.983333), 1):
                self.margin_override = margin
                await self.delay(delay)
                await expect(self.margin).to_have_attribute('aria-label', f'Zapas czasu: {margin} minut')
                self.assertAlmostEqual((await self.margin.bounding_box())['height'], initial['height'], delta=1)
                self.assertEqual(await self.figure.bounding_box(), figure)
                self.assertTrue(await self.margin.evaluate('el => el.scrollWidth <= el.clientWidth'))
                self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

    async def test_setup_loading_does_not_move_the_screen(self):
        self.hold_path, self.hold_code = '/api/transit/transfer-links', '2001'
        await self.page.reload()
        await asyncio.wait_for(self.held.wait(), 5)
        await expect(self.page.get_by_text('Sprawdzanie lokalnych rozkładów…', exact=True)).to_be_visible()
        card = await self.arrival_card.bounding_box()
        figure = await self.figure.bounding_box()
        self.release.set()
        await expect(self.arrival_card.get_by_role('button')).to_be_enabled()
        self.assertEqual(await self.arrival_card.bounding_box(), card)
        self.assertEqual(await self.figure.bounding_box(), figure)


if __name__ == '__main__':
    unittest.main(verbosity=2)
