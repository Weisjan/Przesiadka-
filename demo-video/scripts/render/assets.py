"""Build source SVG diagrams and editable voiceover/subtitle layers. No TTS calls."""
import asyncio
import copy
import html
import json
import re
import textwrap
import xml.etree.ElementTree as ET
from pathlib import Path
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[3]
VIDEO=ROOT/'demo-video'
INK='#F3F2ED';SLATE='#B0AFB8';READY='#ABE58A';LINE='#34343C'


def production():
    value=json.loads((VIDEO/'scripts/production.json').read_text(encoding='utf-8'))
    checks=json.loads((VIDEO/'qa/main-capture.json').read_text(encoding='utf-8'))['checks']
    # Subtitles must never announce a numerical state before its observed API/UI result.
    for delay,identifier in [(4,'seg-07'),(5,'seg-08'),(6,'seg-09')]:
        observed=next(c['at'] for c in checks if c['delay']==delay)
        segment=next(s for s in value['segments'] if s['segment_id']==identifier)
        segment['start_time']=max(segment['start_time'],round(observed+.18,2))
    return value


def stamp(second,separator=','):
    millis=round(second*1000);hours,millis=divmod(millis,3600000);minutes,millis=divmod(millis,60000);seconds,millis=divmod(millis,1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{separator}{millis:03}'


def cues(segments):
    result=[]
    for segment in segments:
        sentences=re.split(r'(?<=[.!?])\s+',segment['text'])
        total=sum(len(s.split()) for s in sentences);cursor=segment['start_time']
        for sentence in sentences:
            end=cursor+(segment['end_time']-segment['start_time'])*len(sentence.split())/total
            lines=textwrap.wrap(sentence,width=58,break_long_words=False,break_on_hyphens=False)
            assert len(lines)<=2,(sentence,lines)
            result.append({'start':round(cursor,3),'end':round(end,3),'text':sentence,'lines':lines})
            cursor=end
    return result


def voice_layers(data):
    segments=data['segments'];words=sum(len(s['text'].split()) for s in segments);assert 260<=words<=330
    voice=VIDEO/'voiceover';sub=VIDEO/'subtitles';voice.mkdir(exist_ok=True);sub.mkdir(exist_ok=True)
    (voice/'voiceover-segments.json').write_text(json.dumps(segments,ensure_ascii=False,indent=2),encoding='utf-8')
    narrative='\n\n'.join(' '.join(s['text'] for s in segments if s['scene_id']==scene['scene_id']) for scene in data['scenes'])
    (voice/'voiceover-script.md').write_text(narrative+'\n',encoding='utf-8')
    ns='http://www.w3.org/2001/10/synthesis';ET.register_namespace('',ns)
    speak=ET.Element('{'+ns+'}speak',{'version':'1.0','{http://www.w3.org/XML/1998/namespace}lang':'pl-PL'})
    for segment in segments:
        paragraph=ET.SubElement(speak,'{'+ns+'}p');paragraph.text=segment['text']
        ET.SubElement(paragraph,'{'+ns+'}break',{'time':str(segment['pause_after_ms'])+'ms'})
    ET.indent(speak);ET.ElementTree(speak).write(voice/'voiceover-ssml.xml',encoding='utf-8',xml_declaration=True)
    timeline='# Mapa narracji\n\nCzas w sekundach od początku filmu. Sloty docelowe, nie pomierzone audio. TTS nie został wygenerowany. Niewielkie korekty początku segmentów wynikają z rzeczywistych odpowiedzi UI.\n\n| Segment | Scena | Od | Do | Tekst |\n|---|---|---:|---:|---|\n'
    for s in segments:timeline+=f"| {s['segment_id']} | {s['scene_id']} | {s['start_time']} | {s['end_time']} | {s['text']} |\n"
    (voice/'narration-timeline.md').write_text(timeline,encoding='utf-8')
    items=cues(segments);srt='';vtt='WEBVTT\n\n'
    for index,item in enumerate(items,1):
        lines='\n'.join(item['lines']);srt+=f"{index}\n{stamp(item['start'])} --> {stamp(item['end'])}\n{lines}\n\n"
        vtt+=f"{stamp(item['start'],'.')} --> {stamp(item['end'],'.')}\n{lines}\n\n"
    (sub/'captions.srt').write_text(srt.rstrip()+'\n',encoding='utf-8');(sub/'captions.vtt').write_text(vtt.rstrip()+'\n',encoding='utf-8')
    header='[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nWrapStyle: 2\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Bahnschrift,34,&H00EDF2F3,&H00EDF2F3,&H000A0808,&H000A0808,0,0,0,0,100,100,0,0,1,0,0,2,100,100,24,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'
    def ass_time(t):
        return stamp(t,'.')[1:-1]  # h:mm:ss.cc
    for item in items:
        content=r'\N'.join(item['lines'])
        header+=f"Dialogue: 0,{ass_time(item['start'])},{ass_time(item['end'])},Default,,0,0,0,,{content}\n"
    (sub/'captions.ass').write_text(header,encoding='utf-8')
    (VIDEO/'qa/caption-cues.json').write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding='utf-8')
    return words,len(items)


def text(x,y,value,size=30,color=INK,weight=400):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" font-weight="{weight}">{html.escape(value)}</text>'


def base(title):
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080" viewBox="0 0 1920 1080"><rect width="1920" height="1080" fill="#08080A"/><g font-family="Bahnschrift, Segoe UI, Arial, sans-serif">'+text(130,112,title,52)+f'<path d="M130 160H1790" stroke="{LINE}"/>'


def algorithm(stage):
    labels=[('SKM','17:02','Wrzeszcz'),('Przesiadka','17:09','Gdańsk Główny'),('Dojście','2 min','Szacunek ORS'),('Autobus 112','17:16','Dworzec Główny 08'),('Cel','18:21','Przegalina 02')]
    value=base('Jak wybierana jest podróż')+text(130,210,'Ten sam kurs SKM. Dokładny słupek. Cel na tym samym kursie ZTM.',27,SLATE)
    active=[0,1,4,2,4][stage]
    for i,(label,clock,stop) in enumerate(labels):
        x=130+i*348;color=READY if active==i else LINE
        value+=f'<path d="M{x} 300H{x+268}V540H{x}Z" fill="none" stroke="{color}" stroke-width="{3 if active==i else 1}"/>'
        value+=text(x+18,344,label,25,SLATE)+text(x+18,425,clock,52)+text(x+18,489,stop,24)
        if i<4:value+=f'<path d="M{x+282} 420H{x+332}m-10 -8 10 8-10 8" fill="none" stroke="{READY if active>i else LINE}" stroke-width="2"/>'
    notes=[('Dalsze postoje konkretnego pociągu','Sprawdzam kolejność zdarzeń tego samego kursu SKM.'),
           ('Tylko zatwierdzone przejścia','W tym przykładzie: Dworzec Główny 08.'),
           ('Cel musi leżeć dalej na trasie autobusu','Sprawdzam późniejszy postój tego samego kursu 112.'),
           ('Dojście jest częścią oceny','Zapisane 82,2 s zaokrąglam w górę do 2 min.'),
           ('Porównuję zapas i czas dotarcia do celu','Najpierw pasmo co najmniej 2 min. Tylko obsługiwany zakres.')]
    value+=text(130,675,notes[stage][0],40)+text(130,735,notes[stage][1],30,SLATE)
    return value+text(130,905,'Schemat działania kodu. Dane archiwalne: 13.11.2026.',22,SLATE)+'</g></svg>'


def architecture(stage):
    value=base('Obliczenia i dane')
    boxes=[(200,240,620,120,'React / TypeScript','Wybór podróży i prezentacja'),(200,430,620,120,'Python / FastAPI','REST API i walidacja'),(200,620,620,140,'Journey Planner','Wyszukiwanie i czysta ocena'),(1140,320,590,140,'GTFS / SQLite','transit.db: lokalne rozkłady'),(1140,560,590,140,'Walking cache / SQLite','walking.db: szacunki ORS')]
    chosen={0:{0},1:{1,2},2:{3},3:{4},4:{4}}[stage]
    for i,(x,y,w,h,title,subtitle) in enumerate(boxes):
        color=READY if i in chosen else LINE
        value+=f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{color}" stroke-width="{3 if i in chosen else 1}"/>'
        value+=text(x+25,y+48,title,36)+text(x+25,y+91,subtitle,25,SLATE)
    for top in (360,550):value+=f'<path d="M510 {top+12}V{top+58}m-8-10 8 10 8-10" stroke="{SLATE}" fill="none" stroke-width="2"/>'
    value+=f'<path d="M1140 390H995V655H832m10-8-10 8 10 8M1140 630H1035V715H832m10-8-10 8 10 8" fill="none" stroke="{SLATE}" stroke-width="2"/>'
    value+=text(875,300,'Odczyt danych',24,SLATE)
    notes=['Interfejs wysyła parametry. Backend zwraca kursy i wynik.',
           'Czystą funkcję oceny testuję niezależnie od HTTP i SQLite.',
           'Jawny import GTFS. Podczas wyszukiwania wystarczają lokalne dane.',
           'ORS wyznacza dojście wcześniej. Suwak korzysta z zapisanego wyniku.',
           'Zaokrąglenie w górę do minut. Nieaktualny wpis wyklucza przejście.']
    return value+text(130,855,notes[stage],29)+text(130,910,'Podczas wyszukiwania i symulacji nie ma nowych żądań ORS.',22,SLATE)+'</g></svg>'


def tests_graphic():
    tests=json.loads((VIDEO/'qa/tests.json').read_text(encoding='utf-8'))
    value=base('Sprawdzone w testach')+text(130,210,'Rzeczywisty wynik lokalnego uruchomienia',27,SLATE)
    for i,(key,label) in enumerate([('backend','Backend / pytest'),('frontend','Frontend / Node'),('browser','Przeglądarka / Edge')]):
        y=330+i*160
        value+=text(150,y,label,38)+text(1420,y,f"{tests[key]['passed']} PASS",46,READY)
        value+=f'<path d="M150 {y+40}H1770" stroke="{LINE}"/>'
    value+=text(150,805,'Kalendarze i północ. Zmiana czasu. Stare odpowiedzi. SVG/SMIL.',29)
    return value+text(150,875,'Edge używa syntetycznych odpowiedzi API; demo korzysta z rzeczywistego lokalnego GTFS.',23,SLATE)+'</g></svg>'


async def graphics():
    folder=VIDEO/'source/graphics';folder.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='msedge',headless=True)
        page=await browser.new_page(viewport={'width':1920,'height':1080},device_scale_factor=1)
        for kind,make,count in [('algorithm',algorithm,5),('architecture',architecture,5),('tests',lambda _:tests_graphic(),1)]:
            for stage in range(count):
                path=folder/f'{kind}-{stage}.svg';path.write_text(make(stage),encoding='utf-8')
                await page.goto(path.as_uri());await page.evaluate('document.fonts.ready.then(()=>true)')
                await page.screenshot(path=str(path.with_suffix('.png')))
        await browser.close()


def main():
    data=production();words,count=voice_layers(data);asyncio.run(graphics())
    print(f'Assets ready: {words} words, {count} caption cues, 11 SVG/PNG graphics',flush=True)


if __name__=='__main__':main()
