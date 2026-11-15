"""Record the actual local Przesiadka+ demo in Edge and edit a 100-second MP4.

No application styling, database contents, API responses or SVG assets are changed.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'demo-video'
WORK = OUT / '.work'
VERIFY = OUT / 'verification'
UI = 'http://127.0.0.1:5173'
API = 'http://127.0.0.1:8000'
FPS = 30
DURATION = 81.2
CASES = [('strzyza', 3, '6', '17:15', '17:36'), ('lawendowe', 2, '11', '17:13', '17:37'), ('przegalina', 5, '112', '17:16', '18:21')]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def signatures():
    paths = ['backend/data/scenarios.db', 'backend/data/gtfs/transit.db', 'backend/data/walking.db',
             'backend/data/demo/transit.db', 'backend/data/demo/walking.db', 'backend/data/demo/manifest.json']
    return {name: {'sha256': sha(ROOT / name), 'size': (ROOT / name).stat().st_size, 'mtime_ns': (ROOT / name).stat().st_mtime_ns}
            for name in paths if (ROOT / name).is_file()}


def http(path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(API + path, data=data, headers={'Content-Type': 'application/json'}), timeout=10) as response:
        return json.load(response)


def responding(url):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError):
        return False


class Services:
    def __init__(self):
        self.owned = []
        self.logs = []
        self.temporary = None

    def start(self, command, name):
        stream = (WORK / f'{name}.log').open('wb')
        self.logs.append(stream)
        process = subprocess.Popen(command, cwd=ROOT / "frontend" if name == "frontend" else ROOT, stdout=stream, stderr=subprocess.STDOUT,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.owned.append(process)

    def ensure(self):
        if not responding(API + '/api/health'):
            self.temporary = tempfile.TemporaryDirectory(prefix='video-demo-', dir=WORK)
            for name in ['transit.db', 'walking.db', 'manifest.json']:
                shutil.copy2(ROOT / 'backend/data/demo' / name, Path(self.temporary.name) / name)
            uv = shutil.which('uv')
            if not uv:
                raise RuntimeError('Brak uv w PATH.')
            self.start([uv, 'run', '--no-sync', '--directory', str(ROOT / 'backend'), 'python', '-m', 'app.demo', 'serve', '--directory', self.temporary.name], 'backend')
        for _ in range(100):
            if responding(API + '/api/health'):
                break
            time.sleep(.1)
        info = http('/api/transit/sources')
        if not (info.get('demo') or {}).get('enabled'):
            raise RuntimeError('Port 8000 nie udostępnia archiwalnego demo. Zatrzymaj zwykły backend i uruchom app.demo serve.')
        if not responding(UI):
            node = shutil.which('node')
            if not node:
                raise RuntimeError('Brak Node.js w PATH.')
            self.start([node, str(ROOT / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '5173', '--strictPort'], 'frontend')
        for _ in range(100):
            if responding(UI):
                return info
            time.sleep(.1)
        raise RuntimeError('Frontend nie odpowiada na 5173.')

    def close(self):
        for process in reversed(self.owned):
            if process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.terminate()
                process.wait(timeout=10)
        for stream in self.logs:
            stream.close()
        if self.temporary:
            self.temporary.cleanup()


def verify_api(info):
    evidence = []
    for key, margin, line, departure, goal in CASES:
        example = next(item for item in info['demo']['examples'] if item['id'] == key)
        body = {'origin_stop_ids': sorted(s['stop_id'] for s in example['origin']['stops']),
                'destination_stop_ids': sorted(s['stop_id'] for s in example['destination']['stops']),
                'departure_date': example['departure_date'], 'departure_time': example['departure_time'], 'max_results': 3}
        result = http('/api/transit/journeys/plan', body)
        item = result['results'][0]
        assert item['origin']['departure_at'][11:16] == '17:02'
        assert item['arrival']['arrival_at'][11:16] == '17:09'
        assert item['departure']['line'] == line and item['departure']['departure_at'][11:16] == departure
        assert item['destination']['arrival_at'][11:16] == goal
        assert item['evaluation']['margin_minutes'] == margin
        assert result['is_realtime'] is False
        evidence.append({'example': example, 'input': body, 'result': result})
    (VERIFY / 'api-checks.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    return evidence


class Recorder:
    def __init__(self, page, ffmpeg):
        self.page, self.ffmpeg = page, ffmpeg
        self.latest = None
        self.serial = 0
        self.sources = set()
        self.events = 0
        self.duplicates = 0
        self.max_lateness = 0
        self.ready = asyncio.Event()

    async def start(self, duration):
        self.session = await self.page.context.new_cdp_session(self.page)
        async def frame(event):
            self.latest = base64.b64decode(event['data'])
            self.serial += 1
            self.events += 1
            self.ready.set()
            try:
                await self.session.send('Page.screencastFrameAck', {'sessionId': event['sessionId']})
            except Exception:
                pass
        self.session.on('Page.screencastFrame', frame)
        await self.session.send('Page.startScreencast', {'format': 'jpeg', 'quality': 92, 'maxWidth': 1920, 'maxHeight': 1080, 'everyNthFrame': 1})
        await asyncio.wait_for(self.ready.wait(), 10)
        self.log = (WORK / 'capture-encode.log').open('wb')
        self.process = await asyncio.create_subprocess_exec(self.ffmpeg, '-y', '-hide_banner', '-loglevel', 'warning',
            '-f', 'image2pipe', '-vcodec', 'mjpeg', '-framerate', str(FPS), '-i', 'pipe:0', '-an',
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '18', '-threads', '4', '-pix_fmt', 'yuv420p',
            '-r', str(FPS), '-map_metadata', '-1', str(WORK / 'capture.mp4'), stdin=asyncio.subprocess.PIPE, stderr=self.log)
        self.started = time.perf_counter()
        self.task = asyncio.create_task(self.write(duration))

    async def write(self, duration):
        previous = None
        for index in range(round(duration * FPS)):
            target = self.started + index / FPS
            await asyncio.sleep(max(0, target - time.perf_counter()))
            self.max_lateness = max(self.max_lateness, time.perf_counter() - target)
            if previous == self.serial:
                self.duplicates += 1
            previous = self.serial
            self.sources.add(self.serial)
            self.process.stdin.write(self.latest)
            await self.process.stdin.drain()
        self.process.stdin.close()
        await self.process.wait()
        if self.process.returncode:
            raise RuntimeError('Kodowanie capture.mp4 nie powiodło się; sprawdź capture-encode.log.')
        await self.session.send('Page.stopScreencast')
        self.log.close()

    async def at(self, second):
        remaining = self.started + second - time.perf_counter()
        if remaining < -.6:
            raise RuntimeError(f'Interakcja nie zdążyła przed punktem {second}s; nagranie przerwane.')
        await asyncio.sleep(max(0, remaining))

    async def finish(self):
        await self.task
        stats = {'fps': FPS, 'captured_events': self.events, 'unique_frames_used': len(self.sources),
                 'duplicated_output_frames': self.duplicates, 'max_writer_lateness_seconds': round(self.max_lateness, 4)}
        (VERIFY / 'capture-stats.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
        return stats


async def expected(page, margin):
    await expect(page.locator(f'output[aria-label="Zapas czasu: {margin:g} minut"]')).to_be_visible()
    state = 'success' if margin >= 2 else 'edge' if margin >= 0 else 'missed'
    await expect(page.locator('[data-figure-state]')).to_have_attribute('data-figure-state', state)


async def example(page, name, margin):
    await page.get_by_role('button', name='Zobacz przykład', exact=True).click(delay=80)
    await expect(page.get_by_role('group', name='Przykłady archiwalnego demo')).to_be_visible()
    async with page.expect_response(lambda response: response.url.endswith('/api/transit/journeys/plan') and response.request.method == 'POST') as reply:
        await page.get_by_role('button', name=name, exact=False).click(delay=90)
    result = await (await reply.value).json()
    assert result['results'][0]['evaluation']['margin_minutes'] == margin
    await expected(page, margin)


async def board(page):
    element = page.get_by_role('region', name='Twój przejazd SKM', exact=True).locator('..')
    summary = element.locator("xpath=preceding-sibling::div[1]")
    await summary.evaluate("el=>scrollTo({top:scrollY+el.getBoundingClientRect().top-32,behavior:'smooth'})")
    await page.wait_for_timeout(650)
    await expect(page.get_by_role('slider')).to_be_in_viewport()


async def drag(page, target):
    slider = page.get_by_role('slider')
    box = await slider.bounding_box()
    current = int(await slider.input_value())
    thumb = 16
    def x(value):
        return box['x'] + thumb / 2 + (box['width'] - thumb) * value / 30
    y = box['y'] + box['height'] / 2
    await page.mouse.move(x(current), y, steps=12)
    await page.mouse.down()
    for index in range(1, 46):
        await page.mouse.move(x(current) + (x(target) - x(current)) * index / 45, y)
        await asyncio.sleep(.025)
    await page.mouse.up()
    await expect(slider).to_have_value(str(target))
    await expected(page, 3 - target)
    await page.get_by_role('region', name='Twój przejazd SKM', exact=True).get_by_role('heading').hover()


async def capture(ffmpeg, evidence, preview):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel='msedge', headless=True)
        context = await browser.new_context(viewport={'width':1920,'height':1080}, screen={'width':1920,'height':1080},
            device_scale_factor=1, locale='pl-PL', timezone_id='Europe/Warsaw', reduced_motion='no-preference', color_scheme='dark')
        page = await context.new_page()
        errors = []
        external_requests = []
        page.on('request', lambda request: external_requests.append(request.url) if not request.url.startswith((UI, API, 'data:', 'blob:')) else None)
        page.on('pageerror', lambda error: errors.append(str(error)))
        await page.goto(UI, wait_until='networkidle')
        await expect(page.get_by_role('button', name='Zobacz przykład', exact=True)).to_be_enabled()
        await expect(page.get_by_text('Archiwalne demo', exact=False).first).to_be_visible()
        # Preflight every real example before recording; no mocked responses or CSS injection.
        for entry in evidence:
            await example(page, entry['example']['name'], entry['result']['results'][0]['evaluation']['margin_minutes'])
        await page.reload(wait_until='networkidle')
        await expect(page.get_by_role('button', name='Zobacz przykład', exact=True)).to_be_enabled()
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(VERIFY / 'initial-page.png'))
        recorder = Recorder(page, ffmpeg)
        await recorder.start(3 if preview else DURATION)
        log = []
        if preview:
            await recorder.finish()
        else:
            print('Recording: planning 0–25.4s', flush=True)
            await recorder.at(4)
            await page.get_by_role('button', name='Zobacz przykład', exact=True).click(delay=90)
            await recorder.at(8)
            async with page.expect_response(lambda r:r.url.endswith('/api/transit/journeys/plan') and r.request.method=='POST') as reply:
                await page.get_by_role('button', name=evidence[0]['example']['name'], exact=False).click(delay=90)
            data = await (await reply.value).json(); assert data['results'][0]['evaluation']['margin_minutes'] == 3
            await expected(page,3)
            await recorder.at(13);await board(page)
            log.append({'scene':'planning','margin':3,'roi':await page.locator('[data-figure-state]').bounding_box()})
            await recorder.at(25.4)
            print('Recording: delay simulation 25.4–55.8s', flush=True)
            for offset, value in [(6.5,2),(14,3),(22,4)]:
                await recorder.at(25.4+offset);await drag(page,value)
                log.append({'scene':'simulation','time':round(time.perf_counter()-recorder.started,3),'delay':value,'margin':3-value})
            await recorder.at(55.8)
            print('Recording: other real examples 55.8–81.2s', flush=True)
            for start, entry, margin in [(56.8,evidence[1],2),(69.3,evidence[2],5)]:
                await recorder.at(start)
                await page.evaluate("scrollTo({top:0,behavior:'smooth'})");await page.wait_for_timeout(650)
                await example(page,entry['example']['name'],margin);await board(page)
                log.append({'scene':entry['example']['id'],'time':round(time.perf_counter()-recorder.started,3),'margin':margin})
            await recorder.finish()
        assert not errors, errors
        assert not external_requests, 'Unexpected non-local browser request'
        (VERIFY / 'recording-checks.json').write_text(json.dumps({'checks':log,'page_errors':errors,'external_requests':external_requests,'browser_version':browser.version,'viewport':{'width':1920,'height':1080},'source':'real Edge CDP frames; real local API'},ensure_ascii=False,indent=2),encoding='utf-8')
        await context.close();await browser.close()
        return recorder


def tool_path(argument, name):
    candidate = argument or shutil.which(name) or str(WORK / 'tools' / (name + ('.exe' if os.name == 'nt' else '')))
    if not Path(candidate).is_file():
        raise RuntimeError(f'Brak {name}. Podaj --{name} lub lokalne .work/tools; skrypt nie instaluje narzędzi.')
    return str(Path(candidate).resolve())


def probe(ffprobe, path):
    return json.loads(subprocess.check_output([ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(path)],encoding='utf-8'))


def edit(ffmpeg, ffprobe):
    capture_metadata = probe(ffprobe,WORK/'capture.mp4')
    assert abs(float(capture_metadata['format']['duration']) - DURATION) < .1, 'Brak pełnego ujęcia; uruchom nagrywanie bez --preview.'
    source = capture_metadata['streams'][0]
    assert (source['width'],source['height'])==(1920,1080)
    font = Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/bahnschrift.ttf'
    if not font.is_file():
        font=font.parent/'segoeui.ttf'
    shutil.copy2(font,WORK/'font.ttf')
    def txt(name,text):
        (WORK/(name+'.txt')).write_text(text,encoding='utf-8')
        return name+'.txt'
    def draw(name,text,size,y,color='F3F2ED',enable=None):
        value=f"drawtext=fontfile=font.ttf:textfile={txt(name,text)}:fontsize={size}:fontcolor=0x{color}:x=(w-text_w)/2:y={y}"
        return value+(f":enable='gte(t,{enable[0]})*lt(t,{enable[1]})'" if enable else '')
    intro=[draw('brand','Przesiadka+',112,370),draw('question','Czy zdążysz na przesiadkę?',48,530),draw('intro_note','SKM i ZTM · archiwalne rozkłady · 13.11.2026',26,900,'B0AFB8')]
    outro=[draw('end_brand','Przesiadka+',100,260),draw('tech','React · TypeScript · FastAPI · GTFS · OpenRouteService',34,435),
        draw('mvp','Prototyp MVP — demonstracja na archiwalnych danych',30,525,'B0AFB8'),
        draw('credit_ztm','Dane: Zarząd Transportu Miejskiego w Gdańsku',22,770,'B0AFB8'),
        draw('credit_skm','PKP Szybka Kolej Miejska w Trójmieście Sp. z o.o.',22,810,'B0AFB8'),
        draw('credit_ors','© openrouteservice by HeiGIT | Data from OpenStreetMap · CC BY-SA 4.0',22,850,'B0AFB8'),
        draw('source_note','GTFS pozyskano 11.11.2026; daty wytworzenia nieustalone.',20,920,'B0AFB8')]
    captions=[
        [(0,8,'Podaj skąd i dokąd. Kursy wyszuka aplikacja.'),(8,16,'Pociąg, przesiadka i tramwaj dobrane z lokalnego GTFS.'),(16,25.4,'Dojście z zapisanej estymacji OpenRouteService: 3 min.')],
        [(0,6.5,'0 min opóźnienia · +3 min zapasu'),(6.5,9.5,'Symulowane opóźnienie. Te same wybrane kursy.'),(9.5,14,'2 min opóźnienia · +1 min zapasu'),(14,17,'Sprawdzamy próg przesiadki.'),(17,22,'3 min opóźnienia · 0 min zapasu'),(22,25,'Opóźnienie przekracza zapas czasu.'),(25,30.4,'4 min opóźnienia · -1 min zapasu')],
        [(0,4.3,'Inny cel. System ponownie wybiera kurs i słupek.'),(4.3,13.5,'Lawendowe Wzgórze · tramwaj 11 · dojście 2 min'),(13.5,17,'Nowy przykład. Inny kurs i czas dotarcia.'),(17,25.4,'Przegalina · autobus 112 · dojście 2 min')]]
    base='fps=30,settb=AVTB,setpts=PTS-STARTPTS,setsar=1'
    filters=[f'[0:v]{base},'+','.join(intro)+'[intro]']
    for index,items in enumerate(captions,1):
        effects=[draw(f'caption_{index}_{j}',text,34,1030,enable=(start,end)) for j,(start,end,text) in enumerate(items)]
        filters.append(f'[{index}:v]{base},crop=1920:1048:0:32,scale=1792:978,pad=1920:1080:64:16:color=0x08080A,'+','.join(effects)+f'[s{index}]')
    filters.append(f'[4:v]{base},'+','.join(outro)+'[outro]')
    filters+=['[intro][s1]xfade=transition=fade:duration=0.4:offset=10[a]',
              '[a][s2]xfade=transition=fade:duration=0.4:offset=35[b]',
              '[b][s3]xfade=transition=fade:duration=0.4:offset=65[c]',
              '[c][outro]xfade=transition=fade:duration=0.4:offset=90,format=yuv420p[v]']
    (WORK/'edit-filter.txt').write_text(';\n'.join(filters),encoding='utf-8')
    stage=WORK/'final.mp4'
    cmd=[ffmpeg,'-y','-hide_banner','-loglevel','warning','-filter_complex_threads','1',
         '-f','lavfi','-i','color=c=0x08080A:s=1920x1080:r=30:d=10.4']
    for start,duration in [(0,25.4),(25.4,30.4),(55.8,25.4)]:
        cmd+=['-ss',str(start),'-t',str(duration),'-i',str(WORK/'capture.mp4')]
    cmd+=['-f','lavfi','-i','color=c=0x08080A:s=1920x1080:r=30:d=10',
          '-filter_complex',';\n'.join(filters),'-map','[v]','-an','-t','100','-r','30',
          '-c:v','libx264','-preset','medium','-crf','18','-profile:v','high','-pix_fmt','yuv420p','-threads','4','-g','60',
          '-map_metadata','-1','-metadata','title=Przesiadka+ — demonstracja MVP','-metadata','comment=Archiwalne dane 13.11.2026; brak realtime; dojście szacunkowe.',
          '-movflags','+faststart',str(stage)]
    with (WORK/'edit.log').open('wb') as log:
        subprocess.run(cmd,cwd=WORK,stderr=log,stdout=log,check=True)
    metadata=probe(ffprobe,stage);video=next(s for s in metadata['streams'] if s['codec_type']=='video')
    assert video['codec_name']=='h264' and (video['width'],video['height'])==(1920,1080)
    assert video['avg_frame_rate']=='30/1' and abs(float(metadata['format']['duration'])-100)<.1
    assert not any(s['codec_type']=='audio' for s in metadata['streams'])
    destination=OUT/'przesiadka-demo.mp4';os.replace(stage,destination)
    metadata['format']['filename']=destination.name
    (VERIFY/'ffprobe.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    for label,second in [('intro',5),('planning',25),('green',39),('red',46),('zero',53),('missed',61),('lawendowe',73),('przegalina',85),('outro',96)]:
        subprocess.run([ffmpeg,'-y','-hide_banner','-loglevel','error','-ss',str(second),'-i',str(destination),'-frames:v','1',str(VERIFY/(label+'.png'))],check=True)
    print('MP4 ready: 100.0 s, 1920x1080, 30 FPS, H.264, no audio',flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ffmpeg');parser.add_argument('--ffprobe')
    parser.add_argument('--preview',action='store_true',help='Three-second capture test, no final movie')
    parser.add_argument('--edit-only',action='store_true',help='Re-edit the existing actual capture')
    args=parser.parse_args()
    WORK.mkdir(parents=True,exist_ok=True);VERIFY.mkdir(parents=True,exist_ok=True)
    ffmpeg,ffprobe=tool_path(args.ffmpeg,'ffmpeg'),tool_path(args.ffprobe,'ffprobe')
    before=signatures();services=Services()
    try:
        if not args.edit_only:
            info=services.ensure();evidence=verify_api(info)
            asyncio.run(capture(ffmpeg,evidence,args.preview))
            if args.preview:
                assert probe(ffprobe,WORK/'capture.mp4')['streams'][0]['width']==1920
                print('Preview ready; inspect capture-stats.json before full recording.',flush=True)
                return
        print('Editing and verifying final MP4…',flush=True)
        edit(ffmpeg,ffprobe)
        subprocess.run([sys.executable,str(OUT/'recording-script/verify_movie.py'),'--ffmpeg',ffmpeg,'--ffprobe',ffprobe],check=True)
    finally:
        services.close()
        after=signatures();assert before==after,'Database contents/mtime changed'
        (VERIFY/'database-check.json').write_text(json.dumps({'before':before,'after':after,'unchanged':True},indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
