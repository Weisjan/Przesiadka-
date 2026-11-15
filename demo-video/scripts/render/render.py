"""Render both 165-second masters from actual recordings and explanatory SVG stages."""
import argparse
import json
import math
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
import assets

ROOT=Path(__file__).resolve().parents[3]
VIDEO=ROOT/'demo-video';WORK=VIDEO/'.production-work';FINAL=VIDEO/'final'
FFMPEG=str(VIDEO/'.work/tools/ffmpeg.exe');FFPROBE=str(VIDEO/'.work/tools/ffprobe.exe')
ENC=['-c:v','libx264','-preset','fast','-crf','17','-profile:v','high','-pix_fmt','yuv420p','-threads','4','-g','60','-r','30','-an']


def probe(path):
    return json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_streams','-show_format','-of','json',str(path)]))


def run(name,args):
    print('Rendering '+name,flush=True)
    with (WORK/(name+'.log')).open('wb') as log:
        subprocess.run([FFMPEG,'-y','-hide_banner','-loglevel','warning','-filter_complex_threads','1',*args],cwd=WORK,stdout=log,stderr=log,check=True)


def commit(stage,destination):
    if destination.exists():
        archive=destination.parent/'archive';archive.mkdir(exist_ok=True)
        shutil.copy2(destination,archive/(destination.stem+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+destination.suffix))
    stage.replace(destination)


def ui_clip(name,start,duration,credits=False):
    effects=['crop=1920:930:0:32','pad=1920:1080:0:16:color=0x08080A','setsar=1']
    if credits:
        effects+=['drawbox=x=1602:y=220:w=302:h=590:color=0x08080A@0.97:t=fill']
        lines=[('Źródła danych',25),('Zarząd Transportu',19),('Miejskiego w Gdańsku',19),('',10),
               ('PKP Szybka Kolej Miejska',19),('w Trójmieście Sp. z o.o.',19),('',10),
               ('© openrouteservice',19),('by HeiGIT |',19),('Data from OpenStreetMap',19),('CC BY-SA 4.0',19),('',10),
               ('GTFS pozyskano 11.11.2026',17),('Data wytworzenia:',17),('nieustalona.',17)]
        y=255
        for i,(line,size) in enumerate(lines):
            if line:
                filename=f'credit-{i}.txt';(WORK/filename).write_text(line,encoding='utf-8')
                effects.append(f'drawtext=fontfile=fonts/bahnschrift.ttf:textfile={filename}:fontsize={size}:fontcolor=0xB0AFB8:x=1616:y={y}')
            y+=size+9
    run(name,['-ss',str(start),'-t',str(duration),'-i',str(VIDEO/'source/recordings/main.mp4'),'-vf',','.join(effects),*ENC,str(WORK/(name+'.mp4'))])


def diagram_clip(kind):
    args=[]
    for i in range(5):args+=['-loop','1','-framerate','30','-t','7.4','-i',str(VIDEO/f'source/graphics/{kind}-{i}.png')]
    filters=[f'[{i}:v]fps=30,settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[s{i}]' for i in range(5)]
    previous='s0'
    for i in range(1,5):
        output=f'x{i}';filters.append(f'[{previous}][s{i}]xfade=transition=fade:duration=0.2:offset={i*7}[{output}]');previous=output
    run(kind,[*args,'-filter_complex',';'.join(filters),'-map',f'[{previous}]','-t','35.25',*ENC,str(WORK/(kind+'.mp4'))])


def render():
    raw=probe(VIDEO/'source/recordings/main.mp4');assert abs(float(raw['format']['duration'])-100)<.05
    fonts=WORK/'fonts';fonts.mkdir(exist_ok=True)
    for name in ['bahnschrift.ttf','segoeui.ttf']:
        source=Path('C:/Windows/Fonts')/name
        assert source.is_file();shutil.copy2(source,fonts/name)
    ui_clip('live',0,70.25)
    diagram_clip('algorithm');diagram_clip('architecture')
    run('tests',['-loop','1','-framerate','30','-i',str(VIDEO/'source/graphics/tests-0.png'),'-t','8.25','-vf','format=yuv420p,setsar=1',*ENC,str(WORK/'tests.mp4')])
    ui_clip('ending',83,17,True)
    args=[]
    for name in ['live','algorithm','architecture','tests','ending']:args+=['-i',str(WORK/(name+'.mp4'))]
    filters=[f'[{i}:v]fps=30,settb=AVTB,setpts=PTS-STARTPTS[s{i}]' for i in range(5)]
    previous='s0'
    for i,offset in enumerate([70,105,140,148],1):
        label=f'j{i}';filters.append(f'[{previous}][s{i}]xfade=transition=fade:duration=0.25:offset={offset}[{label}]');previous=label
    clean=WORK/'clean-final.mp4'
    run('clean-master',[*args,'-filter_complex',';'.join(filters),'-map',f'[{previous}]','-t','165',*ENC,'-map_metadata','-1',
        '-metadata','title=Przesiadka+ | demo rekrutacyjne | clean','-metadata','comment=Archiwalne GTFS 13.11.2026. Dojście szacunkowe. Bez realtime i narracji.',
        '-movflags','+faststart',str(clean)])
    burned=WORK/'subtitled-final.mp4'
    run('subtitled-master',['-i',str(clean),'-vf','ass=filename=../subtitles/captions.ass:fontsdir=fonts',*ENC,
        '-map_metadata','-1','-metadata','title=Przesiadka+ | demo rekrutacyjne | napisy PL','-metadata','comment=Archiwalne GTFS 13.11.2026. Bez narracji i muzyki.',
        '-movflags','+faststart',str(burned)])
    metadata={}
    for path in [clean,burned]:
        value=probe(path);stream=value['streams'][0]
        assert stream['codec_name']=='h264' and (stream['width'],stream['height'],stream['avg_frame_rate'])==(1920,1080,'30/1')
        assert abs(float(value['format']['duration'])-165)<.04 and len(value['streams'])==1
        value['format']['filename']=path.name;metadata[path.stem]=value
    FINAL.mkdir(exist_ok=True)
    commit(clean,FINAL/'przesiadka-demo-clean.mp4');commit(burned,FINAL/'przesiadka-demo-subtitled.mp4')
    (VIDEO/'qa/ffprobe.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Both masters rendered: 165s, 1920x1080, 30 FPS, H.264; no audio',flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--assets-only',action='store_true');args=parser.parse_args()
    WORK.mkdir(exist_ok=True);assets.main()
    if not args.assets_only:render()


if __name__=='__main__':main()
