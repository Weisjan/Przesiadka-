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
            "sha256": "0" * 64, "imported_at": f"{DAY}T00:00:00+01:00",
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


class PlannerUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(channel="msedge", headless=True)
        self.context = await self.browser.new_context(viewport={"width":1440,"height":900},locale="pl-PL",timezone_id="Europe/Warsaw")
        self.page = await self.context.new_page()
        self.requests=[]; self.errors=[]; self.margin_override=None; self.cache_minutes=None
        self.demo_info = None
        self.hold_path=None; self.hold_code=None
        self.held=asyncio.Event(); self.release=asyncio.Event(); self.delivered=asyncio.Event()
        self.artifacts=Path(os.environ.get("PRZESIADKA_ARTIFACTS", tempfile.mkdtemp(prefix="przesiadka-planner-ui-")))
        self.artifacts.mkdir(parents=True,exist_ok=True)
        await self.context.route("http://127.0.0.1:8000/api/**",self.route_api)
        self.page.on('pageerror',lambda error:self.errors.append(str(error)))
        await self.page.goto(os.environ.get("PRZESIADKA_UI_URL","http://127.0.0.1:5173"))
        self.goal=self.page.get_by_label("Dokąd jedziesz?",exact=True)
        self.origin=self.page.get_by_label("Skąd jedziesz?",exact=True)
        self.slider=self.page.get_by_role("slider")
        self.margin=self.page.locator('output[aria-label^="Zapas czasu:"]')
        self.figure=self.page.locator('[data-figure-state]')
        self.card=self.page.get_by_role('region',name='Twój przejazd ZTM',exact=True)
        self.arrival_card=self.page.get_by_role('region',name='Twój przejazd SKM',exact=True)

    async def asyncTearDown(self):
        self.release.set()
        await self.context.close();await self.browser.close();await self.playwright.stop()
        self.assertEqual(self.errors,[])

    def evaluation(self,margin):
        return {"margin_minutes":margin,"delay_threshold_minutes":6,"status":"Zdążysz" if margin>0 else "Na styk" if margin==0 else "Nie zdążysz",
                "has_safe_margin":True,"expected_stop_arrival_at":f"{DAY}T17:45:00+01:00"}

    def groups(self,operator):
        names=[('Stacja początkowa','origin'),('Inna stacja','second-origin')] if operator=='skm' else [('Oliwa','oliwa'),('Uniwersytet','university'),('Brak kursów','none'),('Brak dojścia','missing'),('Błąd API','error')]
        return [{"name":name,"operator":operator,"stops":[{"operator":operator,"stop_id":f"{operator}:{code}","stop_name":name,"location_type":0,"parent_station":None}]} for name,code in names]

    def item(self,stop,body):
        a=journey('arrival');a['stop_sequence']=2
        origin={**a,'stop_id':body['origin_stop_ids'][0],'stop_name':'Stacja początkowa','stop_sequence':1,'arrival_at':f'{DAY}T17:30:00+01:00','departure_at':f'{DAY}T17:30:00+01:00'}
        d=journey('departure',stop)
        goal={**d,'stop_id':body['destination_stop_ids'][0],'stop_name':'Cel podróży','stop_sequence':2,'arrival_at':f'{DAY}T18:10:00+01:00','departure_at':f'{DAY}T18:10:00+01:00'}
        link=transfer_link(stop);minutes=self.cache_minutes if self.cache_minutes is not None else stop[3]
        link['walking']['estimate'].update(walking_minutes=minutes,walking_seconds=minutes*60)
        link.update(walking_minutes=minutes)
        return {'origin':origin,'arrival':a,'departure':d,'destination':goal,'link':link,'evaluation':self.evaluation(stop[4]-(minutes-stop[3])),
                'total_minutes':40,'waiting_minutes':stop[4],'elapsed_from_request_minutes':70,'initial_wait_minutes':30,'risk':'estimated'}

    async def route_api(self,route):
        request=route.request;path=urlsplit(request.url).path;query={k:v[0] for k,v in parse_qs(urlsplit(request.url).query).items()}
        headers={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'content-type','Access-Control-Allow-Methods':'GET,POST'}
        if request.method=='OPTIONS':return await route.fulfill(status=204,headers=headers)
        body=request.post_data_json if request.method=='POST' else {};self.requests.append((path,query,body));status=200
        if path.endswith('/sources'):
            data={'is_realtime':False,'sources':SOURCES,'demo':self.demo_info};identity='sources'
        elif path.endswith('/journeys/stops'):
            data={'is_realtime':False,'groups':[g for g in self.groups(query['operator']) if query.get('query','').lower() in g['name'].lower()],'has_more':False}
            identity=query.get('query','')
        elif path.endswith('/journeys/plan'):
            identity=body['destination_stop_ids'][0]
            stop=STOPS[2] if identity.endswith('university') else STOPS[0]
            items=[self.item(s,body) for s in ([stop,STOPS[1],STOPS[3]])]
            outcome='walking_unavailable' if identity.endswith('missing') else 'no_destination_service' if identity.endswith('none') else 'found'
            data={'is_realtime':False,'schedule_status':'planned','outcome':outcome,'origin_stop_ids':body['origin_stop_ids'],'destination_stop_ids':body['destination_stop_ids'],
                  'requested_departure_at':body['departure_date']+'T'+body['departure_time']+':00'+body.get('departure_offset','+01:00'),
                  'results':items if outcome=='found' else [],'reason':'Dane testowe rankingu.','limitations':['Dane testowe, ograniczony zasięg.'],
                  'sources':SOURCES,'has_more':False,'scope':{'approved_links':4,'available_links':4}}
            if identity.endswith('error'):status=503;data={'detail':{'message':'Brak lokalnych danych (fixture).'}}
        elif path.endswith('/transfers/search'):
            stop=next(s for s in STOPS if body['link_id']==f'fixture-{s[0]}');identity=stop[0]
            margin=self.margin_override if self.margin_override is not None else stop[4]-body['delay_minutes']
            minutes=self.cache_minutes if self.cache_minutes is not None else stop[3]
            margin-=minutes-stop[3]
            a=journey('arrival');a['stop_sequence']=2
            data={'is_realtime':False,'schedule_status':'planned','arrival':a,'link':{'id':body['link_id'],'walking_minutes':minutes},'sources':SOURCES,
                  'search_window':{'start_at':a['arrival_at'],'end_at_exclusive':f'{DAY}T23:42:00+01:00'},'limitations':['Dane testowe'],
                  'results':[{'departure':journey('departure',stop),'evaluation':self.evaluation(margin)}]}
        else:
            self.errors.append('Unexpected API '+path);return await route.abort()
        held=path==self.hold_path and identity==self.hold_code
        if held:self.hold_path=None;self.held.set();await self.release.wait()
        try:await route.fulfill(status=status,json=data,headers=headers)
        except Exception:
            if not held:raise
        finally:
            if held:self.delivered.set()

    async def fill_form(self,goal='Oliwa',origin='Stacja początkowa'):
        await self.origin.fill(origin);await self.goal.fill(goal)
        await self.page.get_by_label('Data wyjazdu',exact=True).fill(DAY)
        await self.page.get_by_label('Godzina wyjazdu',exact=True).fill('17:00')
        await expect(self.page.get_by_role('button',name='Szukaj podróży',exact=True)).to_be_enabled()

    async def start_analysis(self):
        await self.fill_form();await self.page.get_by_role('button',name='Szukaj podróży',exact=True).click();await self.expect_margin(6)

    async def expect_margin(self,value):
        await expect(self.margin).to_have_attribute('aria-label',f'Zapas czasu: {value:g} minut')

    async def delay(self,value):
        await self.slider.evaluate("""(el,value)=>{Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,String(value));el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));}""",value)

    async def choose_alternative(self,index):
        trigger=self.page.get_by_role('button',name='Inne podróże',exact=False)
        await trigger.click();button=self.page.get_by_role('group',name='Warianty podróży').get_by_role('button').nth(index)
        await button.focus();await self.page.keyboard.press('Enter');await expect(trigger).to_be_focused()

    async def test_form_and_alternative_keep_delay_and_exact_pole(self):
        await self.start_analysis();await self.delay(8);await self.expect_margin(-2)
        await self.choose_alternative(1);await self.expect_margin(-5);await expect(self.slider).to_have_value('8')
        await expect(self.card).to_contain_text('Dworzec PKS 01')

    async def test_demo_example_runs_normal_planner_with_editable_fields(self):
        self.demo_info={'enabled':True,'label':'Archiwalne demo, dane testowe, nie aktualny rozkład','departure_date':DAY,
            'min_departure_time':'16:00','max_departure_time':'18:00','walking_reference_at':f'{DAY}T00:00:00+01:00',
            'examples':[{'id':'fixture','name':'Testowy przykład','description':'Fixture only','origin':self.groups('skm')[0],
                'destination':self.groups('ztm')[0],'departure_date':DAY,'departure_time':'17:00'}]}
        await self.page.reload();await self.page.get_by_role('button',name='Zobacz przykład').click()
        await self.page.get_by_role('button',name='Testowy przykład',exact=False).click();await self.expect_margin(6)
        await expect(self.origin).to_have_value('Stacja początkowa');await expect(self.goal).to_have_value('Oliwa')
        self.assertTrue(any(path.endswith('/journeys/plan') for path,_,_ in self.requests))
        await expect(self.page.get_by_label('Data wyjazdu')).to_have_attribute('min',DAY)
        await expect(self.page.get_by_label('Godzina wyjazdu')).to_have_attribute('max','18:00')

    async def test_mobile_result_collapses_form_and_can_be_edited(self):
        await self.page.set_viewport_size({'width':390,'height':844});await self.start_analysis()
        await expect(self.origin).not_to_be_visible();await expect(self.slider).to_be_in_viewport()
        await self.page.wait_for_function("""() => {
            const selectors=['[data-figure-state]','output[aria-label^="Zapas czasu:"]','input[type="range"]'];
            return selectors.every(s=>{const r=document.querySelector(s)?.getBoundingClientRect();return r && r.top>=0 && r.bottom<=innerHeight;});
        }""")
        await self.page.get_by_role('button',name='Zmień podróż',exact=True).click();await expect(self.origin).to_be_visible()
        await self.delay(3);await self.goal.fill('Uniwersytet');await expect(self.margin).to_have_count(0)
        await expect(self.slider).to_have_value('3')

    async def test_goal_edit_clears_result_and_keeps_delay(self):
        await self.start_analysis();await self.delay(8);await self.goal.fill('Uniwersytet')
        await expect(self.margin).to_have_count(0);await expect(self.card.locator('time')).to_have_count(0)
        await expect(self.page.get_by_role('button',name='Szukaj podróży')).to_be_enabled()
        await self.page.get_by_role('button',name='Szukaj podróży').click();await self.expect_margin(-4)
        await expect(self.slider).to_have_value('8');await expect(self.card).to_contain_text('Dworzec PKS 02')

    async def test_late_plan_cannot_restore_old_goal(self):
        await self.fill_form();self.hold_path='/api/transit/journeys/plan';self.hold_code='ztm:oliwa'
        await self.page.get_by_role('button',name='Szukaj podróży').click();await asyncio.wait_for(self.held.wait(),5)
        await self.goal.fill('Uniwersytet');await expect(self.page.get_by_role('button',name='Szukaj podróży')).to_be_enabled()
        await self.page.get_by_role('button',name='Szukaj podróży').click();await self.expect_margin(4)
        self.release.set();await self.delivered.wait();await self.expect_margin(4);await expect(self.card).to_contain_text('Dworzec PKS 02')

    async def test_late_analysis_cannot_restore_old_alternative(self):
        await self.start_analysis();self.hold_path='/api/transit/transfers/search';self.hold_code='2001'
        await self.delay(7);await asyncio.wait_for(self.held.wait(),5);await self.choose_alternative(1);await self.expect_margin(-4)
        self.release.set();await self.delivered.wait();await self.expect_margin(-4)

    async def test_origin_edit_invalidates_old_plan(self):
        await self.start_analysis();await self.origin.fill('Inna stacja');await expect(self.margin).to_have_count(0)
        await expect(self.goal).to_have_value('Oliwa');await expect(self.figure).to_have_attribute('data-figure-state','idle')

    async def test_fast_slider_keeps_course_and_animation(self):
        await self.start_analysis();before=len([x for x in self.requests if x[0].endswith('/plan')])
        await self.figure.evaluate('el=>window.originalSvg=el.querySelector("svg")')
        for n in [1,7,8,2,0]:await self.delay(n)
        await self.expect_margin(6)
        self.assertEqual(before,len([x for x in self.requests if x[0].endswith('/plan')]))
        self.assertTrue(await self.figure.locator('svg').first.evaluate('el=>el===window.originalSvg'))

    async def test_cache_change_requires_new_plan(self):
        await self.start_analysis();self.cache_minutes=4;await self.delay(1)
        await expect(self.margin).to_have_count(0);await expect(self.page.get_by_role('alert').filter(has_text='szacunek')).to_be_visible()
        await self.page.get_by_role('button',name='Szukaj podróży').click();await self.expect_margin(4);await expect(self.slider).to_have_value('1')

    async def test_empty_and_error_states_have_no_false_result(self):
        for goal,message in [('Brak kursów','Nie znaleziono kursu'),('Brak dojścia','Brak aktualnego szacunku'),('Błąd API','Brak lokalnych danych')]:
            await self.fill_form(goal);await self.page.get_by_role('button',name='Szukaj podróży').click()
            await expect(self.page.get_by_text(message,exact=False)).to_be_visible();await expect(self.margin).to_have_count(0)
            await expect(self.figure).to_have_attribute('data-figure-state','idle')

    async def test_responsive_keyboard_and_single_visible_model(self):
        await self.start_analysis();await self.page.wait_for_timeout(280)
        for width in [390,768,1440]:
            await self.page.set_viewport_size({'width':width,'height':900})
            self.assertTrue(await self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            blocks = [await element.bounding_box() for element in (self.arrival_card, self.card, self.page.locator('[aria-busy]'), self.slider)]
            for i, a in enumerate(blocks):
                for b in blocks[i+1:]:
                    overlap_x=min(a['x']+a['width'],b['x']+b['width'])-max(a['x'],b['x'])
                    overlap_y=min(a['y']+a['height'],b['y']+b['height'])-max(a['y'],b['y'])
                    self.assertFalse(overlap_x>1 and overlap_y>1, (width,a,b))
            await self.slider.focus();await self.page.keyboard.press('ArrowRight');await self.expect_margin(5)
            self.assertNotEqual(await self.slider.evaluate('e=>getComputedStyle(e).outlineStyle'),'none')
            await self.delay(0);await self.expect_margin(6)
            await self.page.screenshot(path=str(self.artifacts/f'planner-{width}.png'),full_page=True)
        self.assertEqual(sorted(await self.figure.locator('[data-model]').evaluate_all('es=>es.map(e=>Number(getComputedStyle(e).opacity))')),[0,0,1])

    async def test_kinetic_background_moves_and_stops_for_reduced_motion(self):
        bg=self.page.locator('[data-kinetic-background]');await expect(bg).to_have_attribute('aria-hidden','true')
        self.assertEqual(await bg.evaluate('e=>getComputedStyle(e).pointerEvents'),'none')
        before=await bg.locator('g').first.evaluate('e=>getComputedStyle(e).transform');await self.page.wait_for_timeout(650)
        self.assertNotEqual(before,await bg.locator('g').first.evaluate('e=>getComputedStyle(e).transform'))
        await self.page.emulate_media(reduced_motion='reduce');await self.page.wait_for_timeout(100)
        self.assertEqual(await bg.locator('svg,g,path').evaluate_all('es=>es.filter(e=>getComputedStyle(e).animationName!=="none").length'),0)

    async def test_dst_requires_choosing_repeated_hour(self):
        await self.fill_form();await self.page.get_by_label('Data wyjazdu').fill('2026-10-25');await self.page.get_by_label('Godzina wyjazdu').fill('02:30')
        await expect(self.page.get_by_role('button',name='Szukaj podróży')).to_be_disabled()
        await self.page.get_by_label('Godzina występuje dwukrotnie').select_option('+01:00')
        await expect(self.page.get_by_role('button',name='Szukaj podróży')).to_be_enabled()

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
