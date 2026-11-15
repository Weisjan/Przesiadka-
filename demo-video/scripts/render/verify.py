"""Verify both real exports, motion, captions, metadata and the future voiceover contract."""
import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3];VIDEO=ROOT/'demo-video';QA=VIDEO/'qa'
FFMPEG=str(VIDEO/'.work/tools/ffmpeg.exe');FFPROBE=str(VIDEO/'.work/tools/ffprobe.exe')


def probe(p):
    return json.loads(subprocess.check_output([FFPROBE,'-v','error','-show_streams','-show_format','-of','json',str(p)]))


def pixels(path,t,crop,duration=None):
    args=[FFMPEG,'-v','error','-ss',str(t),'-i',str(path)]
    args+=['-t',str(duration)] if duration else ['-frames:v','1']
    return subprocess.check_output([*args,'-vf',crop,'-pix_fmt','rgb24','-f','rawvideo','-'])


def motion(path,t,roi):
    x,y,w,h=roi;data=pixels(path,t,f'crop={w}:{h}:{x}:{y}',1)
    size=w*h*3;frames=[data[i:i+size] for i in range(0,len(data),size)];assert len(frames)==30
    changed=sum(max(abs(frames[0][i+c]-frames[11][i+c]) for c in range(3))>16 for i in range(0,size,3))
    unique=len({hashlib.sha256(frame).digest() for frame in frames})
    assert changed>20 and unique>=15,(t,changed,unique)
    return {'second':t,'crop':roi,'frames':30,'unique_decoded_frames':unique,'changed_pixels_over_16':changed}


def normalize(text):return ' '.join(text.split())


def layers():
    config=json.loads((VIDEO/'scripts/production.json').read_text(encoding='utf-8'))
    segments=json.loads((VIDEO/'voiceover/voiceover-segments.json').read_text(encoding='utf-8'))
    voice=(VIDEO/'voiceover/voiceover-script.md').read_text(encoding='utf-8')
    assert normalize(voice)==normalize(' '.join(s['text'] for s in segments))
    assert 260<=len(voice.split())<=330 and len({s['segment_id'] for s in segments})==len(segments)
    previous=0
    for s in segments:
        assert previous<=s['start_time']<s['end_time']<=165
        scene=next(item for item in config['scenes'] if item['scene_id']==s['scene_id'])
        assert scene['start_time']<=s['start_time'] and s['end_time']<=scene['end_time']
        assert isinstance(s['pause_after_ms'],int) and s['pause_after_ms']>=0
        previous=s['end_time']
    xml=ET.parse(VIDEO/'voiceover/voiceover-ssml.xml')
    assert normalize(' '.join(xml.getroot().itertext()))==normalize(voice)
    items=json.loads((QA/'caption-cues.json').read_text(encoding='utf-8'))
    assert normalize(' '.join(i['text'] for i in items))==normalize(voice)
    srt=(VIDEO/'subtitles/captions.srt').read_text(encoding='utf-8');vtt=(VIDEO/'subtitles/captions.vtt').read_text(encoding='utf-8')
    assert vtt.startswith('WEBVTT\n')
    srt_text=' '.join(line for line in srt.splitlines() if line and not line.isdigit() and '-->' not in line)
    vtt_text=' '.join(line for line in vtt.splitlines() if line and line!='WEBVTT' and '-->' not in line)
    assert normalize(srt_text)==normalize(voice)==normalize(vtt_text)
    last=0;max_cps=0
    for item in items:
        assert last<=item['start']<item['end']<=165
        assert 1<=len(item['lines'])<=2 and max(map(len,item['lines']))<=58
        max_cps=max(max_cps,len(item['text'])/(item['end']-item['start']));last=item['end']
    assert max_cps<=25,max_cps
    checks=json.loads((QA/'main-capture.json').read_text(encoding='utf-8'))
    assert not checks['page_errors'] and not checks['external_requests']
    for delay,key in [(4,'seg-07'),(5,'seg-08'),(6,'seg-09')]:
        assert next(s['start_time'] for s in segments if s['segment_id']==key)>=next(c['at'] for c in checks['checks'] if c['delay']==delay)
    return {'words':len(voice.split()),'segments':len(segments),'caption_cues':len(items),'max_caption_characters_per_second':round(max_cps,2),'ssml':'well-formed; provider dialect still requires checking','tts_generated':False}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sample',action='store_true');args=parser.parse_args()
    if args.sample:
        path=VIDEO/'source/recordings/sample.mp4';meta=probe(path);assert float(meta['format']['duration'])==18
        r=json.loads((QA/'sample-capture.json').read_text())['figure_roi'];roi=[int(r['x'])//2*2,int(r['y'])//2*2,208,208]
        data={'result':'PASS','duration':18,'motion':[motion(path,t,roi) for t in (2,7,16)]}
        (QA/'sample-check.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2));return
    layer_report=layers();files={};frames=QA/'keyframes';frames.mkdir(exist_ok=True)
    for kind in ('clean','subtitled'):
        path=VIDEO/f'final/przesiadka-demo-{kind}.mp4';meta=probe(path);stream=meta['streams'][0]
        assert (stream['codec_name'],stream['width'],stream['height'],stream['avg_frame_rate'],stream['nb_frames'])==('h264',1920,1080,'30/1','4950')
        assert float(meta['format']['duration'])==165 and len(meta['streams'])==1
        assert not re.search(r'[A-Za-z]:[\\/]',json.dumps(meta['format'].get('tags',{})))
        result=subprocess.run([FFMPEG,'-hide_banner','-loglevel','info','-i',str(path),'-vf','blackdetect=d=0.033:pix_th=0.04:pic_th=0.998','-an','-f','null','-'],capture_output=True,text=True,check=True)
        (QA/f'{kind}-decode.log').write_text(result.stderr,encoding='utf-8')
        assert 'black_start:' not in result.stderr and 'corrupt' not in result.stderr.lower() and 'Error' not in result.stderr
        labels=[('first',.2),('form',10),('recommendation',30),('green',42),('red',50),('zero',57),('grey',65),('algorithm',87),('ranking',101),('architecture',110),('cache',130),('tests',144),('ending',160),('last',164.9)]
        for label,t in labels:
            subprocess.run([FFMPEG,'-y','-v','error','-ss',str(t),'-i',str(path),'-frames:v','1',str(frames/f'{kind}-{label}.png')],check=True)
        with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        files[kind]={'duration':165,'fps':'30/1','resolution':[1920,1080],'codec':'h264','frames':4950,'audio':False,'bytes':path.stat().st_size,'sha256':digest,'full_decode':'PASS','unexpected_black_intervals':0}
        print(kind+' full decode and keyframes PASS',flush=True)
    clean=VIDEO/'final/przesiadka-demo-clean.mp4';burned=VIDEO/'final/przesiadka-demo-subtitled.mp4'
    cap=json.loads((QA/'main-capture.json').read_text())['figure_roi'];roi=[int(cap['x'])//2*2,int(cap['y']-32+16)//2*2,208,208]
    moves={name:motion(clean,t,roi) for name,t in [('green',42),('red',50),('grey',65)]}
    moves['kinetic_background']=motion(clean,42,[20,20,240,280])
    differences=[]
    for t in (30,50,87,110,144,160):
        a=pixels(clean,t,'crop=1920:130:0:950');b=pixels(burned,t,'crop=1920:130:0:950')
        clean_bright=sum(max(a[i:i+3])>80 for i in range(0,len(a),3));changed=sum(max(abs(a[i+c]-b[i+c]) for c in range(3))>20 for i in range(0,len(a),3))
        assert clean_bright<100 and changed>500,(t,clean_bright,changed)
        differences.append({'second':t,'clean_bright_pixels_in_caption_band':clean_bright,'pixels_changed_by_captions':changed})
    # First image is the actual application capture, with only the documented crop/pad.
    a=pixels(VIDEO/'source/recordings/main.mp4',0,'crop=1920:930:0:32');b=pixels(clean,0,'crop=1920:930:0:16')
    mae=sum(abs(x-y) for x,y in zip(a,b))/len(a);assert mae<4,mae
    report={'result':'PASS','files':files,'layers':layer_report,'motion':moves,'caption_separation':differences,'first_frame_source_mean_pixel_difference':round(mae,4),
            'capture':json.loads((QA/'main-capture-stats.json').read_text()),'scope':'Automated full timeline decode, sampled motion and keyframes; no generated TTS or manual full-length playback claim.'}
    (QA/'final-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
