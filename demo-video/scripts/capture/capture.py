"""Capture real Edge frames and validate live local-demo results. Never calls ORS."""
import argparse
import asyncio
import importlib.util
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[3]
VIDEO = ROOT / 'demo-video'
WORK = VIDEO / '.production-work'
QA = VIDEO / 'qa'
RECORDINGS = VIDEO / 'source/recordings'
FFMPEG = str(VIDEO / '.work/tools/ffmpeg.exe')
FFPROBE = str(VIDEO / '.work/tools/ffprobe.exe')
spec = importlib.util.spec_from_file_location('previous_capture', VIDEO / 'recording-script/record.py')
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
legacy.WORK, legacy.VERIFY = WORK, QA


def backup(path):
    if path.exists():
        archive = path.parent / 'archive'
        archive.mkdir(exist_ok=True)
        path.replace(archive / f'{path.stem}-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}{path.suffix}')


def run_tests():
    folder = WORK / ('tests-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    folder.mkdir(parents=True,exist_ok=False)
    env = os.environ.copy()
    env['PRZESIADKA_TRANSIT_PATH'] = str(folder / 'unused-transit.db')
    env['PRZESIADKA_WALKING_PATH'] = str(folder / 'unused-walking.db')
    commands = {
        'backend': [shutil.which('uv'), 'run', '--no-sync', '--directory', str(ROOT/'backend'), 'python', '-B', '-m', 'pytest', '-q', '--basetemp', str(folder/'pytest')],
        'frontend': ['cmd.exe', '/d', '/c', 'npm.cmd', 'test', '--prefix', str(ROOT/'frontend')],
        'browser': [sys.executable, '-B', str(ROOT/'frontend/tests/stop_selection_browser.py')],
    }
    env['PRZESIADKA_ARTIFACTS'] = str(QA/'browser')
    results = {}
    for name, command in commands.items():
        print('Testing ' + name, flush=True)
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=180)
        output = (result.stdout + result.stderr).decode('utf-8', errors='replace')
        (QA/f'{name}-tests.log').write_text(output, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(f'{name} tests failed; inspect local qa log.')
        pattern = {'backend': r'(\d+) passed', 'frontend': r'pass (\d+)', 'browser': r'Ran (\d+) tests'}[name]
        match = re.search(pattern, output)
        assert match, f'Cannot parse actual {name} test result'
        results[name] = {'passed': int(match[1]), 'exit_code': 0, 'scope': 'synthetic API in Edge' if name=='browser' else 'isolated tests'}
    (QA/'tests.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results), flush=True)


async def manual_plan(page, recorder=None):
    async def at(second):
        if recorder: await recorder.at(second)
    origin = page.get_by_label('Skąd jedziesz?', exact=True)
    await at(.8); await origin.click()
    await origin.press_sequentially('GDAŃSK WRZESZCZ', delay=80 if recorder else 1)
    await expect(page.locator('datalist option[value="GDAŃSK WRZESZCZ"]')).to_have_count(1)
    await origin.press('Tab')
    await at(4.5); await page.get_by_label('Data wyjazdu', exact=True).fill('2026-11-13')
    await at(7); await page.get_by_label('Godzina wyjazdu', exact=True).fill('17:00')
    goal = page.get_by_label('Dokąd jedziesz?', exact=True)
    await at(10); await goal.click(); await goal.press_sequentially('Przegalina', delay=90 if recorder else 1)
    await expect(page.locator('datalist option[value="Przegalina"]')).to_have_count(1)
    await goal.press('Tab')
    button = page.get_by_role('button', name='Szukaj podróży', exact=True)
    await expect(button).to_be_enabled()
    await at(14)
    async with page.expect_response(lambda r:r.url.endswith('/api/transit/journeys/plan') and r.request.method=='POST') as reply:
        await button.click(delay=80)
    data = await (await reply.value).json()
    item = data['results'][0]
    assert item['departure']['trip_id']=='ztm:112202611131713_201_112-02'
    assert item['departure']['departure_at'][11:16]=='17:16'
    assert item['destination']['arrival_at'][11:16]=='18:21'
    assert item['link']['walking_minutes']==2 and item['evaluation']['margin_minutes']==5
    await legacy.expected(page, 5)
    return item


async def drag(page, target):
    slider = page.get_by_role('slider')
    box = await slider.bounding_box()
    current = int(await slider.input_value())
    # Native range geometry uses its actual DOM bounds and the existing 16px thumb.
    def x(value): return box['x'] + 8 + (box['width'] - 16) * value / 30
    y = box['y'] + box['height'] / 2
    await page.mouse.move(x(current), y, steps=10)
    await page.mouse.down()
    for step in range(1, 46):
        await page.mouse.move(x(current) + (x(target)-x(current))*step/45, y)
        await asyncio.sleep(.025)
    await page.mouse.up()
    await expect(slider).to_have_value(str(target))
    await legacy.expected(page, 5-target)
    await page.get_by_role('region', name='Twój przejazd SKM', exact=True).get_by_role('heading').hover()


async def capture(sample):
    kind = 'sample' if sample else 'main'
    duration = 18 if sample else 100
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel='msedge', headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080},screen={'width':1920,'height':1080},device_scale_factor=1,
            locale='pl-PL',timezone_id='Europe/Warsaw',reduced_motion='no-preference',color_scheme='dark')
        page = await context.new_page(); errors=[]; external=[]; checks=[]
        page.on('pageerror', lambda error:errors.append(str(error)))
        page.on('request', lambda request:external.append(request.url) if not request.url.startswith((legacy.UI,legacy.API,'data:','blob:')) else None)
        await page.goto(legacy.UI, wait_until='networkidle')
        await expect(page.get_by_text('Archiwalne demo',exact=False).first).to_be_visible()
        item = await manual_plan(page)
        await legacy.board(page)
        if not sample:
            await page.reload(wait_until='networkidle')
            await expect(page.get_by_role('button',name='Zobacz przykład',exact=True)).to_be_enabled()
            await page.wait_for_timeout(300)
        recorder = legacy.Recorder(page, FFMPEG)
        try:
            await recorder.start(duration)
            if sample:
                roi=await page.locator('[data-figure-state]').bounding_box()
                for second,value in [(4,4),(9,5),(13,6)]:
                    await recorder.at(second);await drag(page,value)
                    checks.append({'at':round(time.perf_counter()-recorder.started,3),'delay':value,'margin':5-value})
            else:
                print('Recording actual form and recommendation',flush=True)
                item=await manual_plan(page,recorder)
                await recorder.at(18);await legacy.board(page)
                roi=await page.locator('[data-figure-state]').bounding_box()
                print('Recording real delay slider',flush=True)
                for second,value in [(45,4),(53,5),(60.5,6),(73,0)]:
                    await recorder.at(second);await drag(page,value)
                    checks.append({'at':round(time.perf_counter()-recorder.started,3),'delay':value,'margin':5-value})
                await recorder.at(78)
                await page.get_by_text('Dlaczego ta podróż?',exact=True).click()
                await expect(page.get_by_text('Zatwierdzone powiązania:',exact=False)).to_be_visible()
            await recorder.finish()
            assert not errors and not external, 'Unexpected browser error or external request'
            destination=RECORDINGS/f'{kind}.mp4';backup(destination)
            shutil.move(WORK/'capture.mp4',destination)
            shutil.copy2(QA/'capture-stats.json',QA/f'{kind}-capture-stats.json')
            report={'kind':kind,'duration':duration,'viewport':[1920,1080],'device_scale_factor':1,'reduced_motion':'no-preference',
                'browser':browser.version,'figure_roi':roi,'checks':checks,'page_errors':errors,'external_requests':external,
                'selected_trip':item['departure']['trip_id'],'source':'actual Edge CDP frames, no mocked API or DOM/CSS replacement'}
            (QA/f'{kind}-capture.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(f'Captured {kind}: {duration}s',flush=True)
        finally:
            if hasattr(recorder,'task') and not recorder.task.done():
                recorder.task.cancel()
                try: await recorder.task
                except asyncio.CancelledError: pass
            if hasattr(recorder,'process') and recorder.process.returncode is None:
                recorder.process.kill();await recorder.process.wait()
            if hasattr(recorder,'log') and not recorder.log.closed:recorder.log.close()
            await context.close();await browser.close()


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sample',action='store_true');parser.add_argument('--tests',action='store_true');args=parser.parse_args()
    for p in (WORK,QA,RECORDINGS):p.mkdir(parents=True,exist_ok=True)
    before=legacy.signatures();services=legacy.Services()
    try:
        # Refuse occupied non-demo ports instead of launching duplicate servers.
        for port,url in [(8000,legacy.API+'/api/health'),(5173,legacy.UI)]:
            with socket.socket() as sock:
                occupied=sock.connect_ex(('127.0.0.1',port))==0
            if occupied and not legacy.responding(url):raise RuntimeError(f'Port {port} occupied by another service')
        info=services.ensure();legacy.verify_api(info)
        if args.tests:run_tests()
        asyncio.run(capture(args.sample))
    finally:
        services.close();after=legacy.signatures();assert before==after,'Local database changed'
        (QA/'databases.json').write_text(json.dumps({'unchanged':True,'before':before,'after':after},indent=2),encoding='utf-8')


if __name__=='__main__':main()
