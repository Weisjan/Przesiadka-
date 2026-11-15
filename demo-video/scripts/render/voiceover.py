"""Synchronize scene WAVs with the existing film; preserve every original input.

shortcut: sentence mapping uses scene filenames and matching long-pause counts;
spoken content must be listened to before recruiter delivery. Use Polish ASR/forced
alignment if inputs change structure. This script refuses a count mismatch.
"""
import array
import hashlib
import json
import re
import subprocess
import textwrap
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
VIDEO = ROOT / 'demo-video'
WORK = VIDEO / '.production-work/voiceover'
QA = VIDEO / 'qa'
FF = str(VIDEO / '.work/tools/ffmpeg.exe')
PROBE = str(VIDEO / '.work/tools/ffprobe.exe')
GENERATED = VIDEO / 'voiceover/generated'
OUTPUT = VIDEO / 'final/przesiadka-demo-ai-voice.mp4'
AUDIO = GENERATED / 'final-voiceover.wav'
RATE = 48000
DURATION = 165


def run(arguments):
    return subprocess.run([FF, '-hide_banner', '-nostdin', *arguments], capture_output=True, text=True, check=True)


def probe(path):
    return json.loads(subprocess.check_output([PROBE, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(path)]))


def signature(path):
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    stat = path.stat()
    return {'sha256': digest, 'size': stat.st_size, 'mtime_ns': stat.st_mtime_ns}


def loudness(path):
    log = run(['-i', str(path), '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-']).stderr
    return json.JSONDecoder().raw_decode(log[log.rfind('{'):])[0]


def stamp(seconds, separator=','):
    value = round(seconds * 1000)
    hours, value = divmod(value, 3600000)
    minutes, value = divmod(value, 60000)
    seconds, millis = divmod(value, 1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{separator}{millis:03}'


def main():
    assert not OUTPUT.exists() and not AUDIO.exists(), 'Refusing to overwrite an existing voice export'
    WORK.mkdir(parents=True, exist_ok=True)
    QA.mkdir(exist_ok=True)
    originals = [VIDEO / 'final/przesiadka-demo-clean.mp4', VIDEO / 'final/przesiadka-demo-subtitled.mp4', *sorted(GENERATED.glob('scene-*.wav'))]
    before = {str(p.relative_to(ROOT)): signature(p) for p in originals}
    inputs = sorted(GENERATED.glob('scene-*.wav'))
    assert [p.name for p in inputs] == [f'scene-{i:02}.wav' for i in range(1, 6)]
    assert len({signature(p)['sha256'] for p in inputs}) == 5, 'Duplicate input audio'
    segments = json.loads((VIDEO / 'voiceover/voiceover-segments.json').read_text(encoding='utf-8'))
    old_cues = json.loads((QA / 'caption-cues.json').read_text(encoding='utf-8'))
    rows = []; input_report = []
    for scene, path in enumerate(inputs, 1):
        meta = probe(path)
        detected = run(['-i', str(path), '-af', 'silencedetect=noise=-40dB:d=0.7', '-f', 'null', '-']).stderr
        ends = [float(v) for v in re.findall(r'silence_start: ([0-9.]+)', detected)]
        silence_ends = [float(v) for v in re.findall(r'silence_end: ([0-9.]+)', detected)]
        assert abs(silence_ends[-1] - float(meta['format']['duration'])) < .05, 'Missing trailing pause'
        starts = [0.] + silence_ends[:-1]
        expected = []
        for segment in segments:
            if segment['scene_id'] == f'scene-{scene}':
                expected += [(sentence, segment['segment_id']) for sentence in re.split(r'(?<=[.!?])\s+', segment['text'])]
        assert len(starts) == len(ends) == len(expected), (path.name, 'Sentence count mismatch')
        measurement = loudness(path)
        gain = min(-16 - float(measurement['input_i']), -1.5 - float(measurement['input_tp']))
        input_report.append({'file': path.name, 'duration': float(meta['format']['duration']), 'sentence_count': len(expected), 'loudness': measurement, 'gain_db': gain})
        for (a, b), (text, segment_id) in zip(zip(starts, ends), expected):
            old = old_cues[len(rows)]
            assert old['text'] == text
            cut_start = max(0, a - .08); cut_end = b + .12
            rows.append({'scene': scene, 'source': path.name, 'segment_id': segment_id, 'text': text,
                         'source_start': cut_start, 'source_end': cut_end, 'duration': cut_end - cut_start,
                         'start': old['start'] + .12, 'slot_end': old['end'], 'gain_db': gain})
    assert len(rows) == 37
    # Keep every spoken sentence within its real scene/state window. Move an earlier
    # phrase later if it would otherwise leave a long avoidable pause before the next.
    for i in range(len(rows)-2, -1, -1):
        row, following = rows[i], rows[i+1]
        wanted = following['start'] - 3.0 - row['duration']
        latest = row['slot_end'] - .08 - row['duration']
        row['start'] = max(row['start'], min(latest, wanted))
    samples = array.array('h', [0]) * (DURATION * RATE)
    for i, row in enumerate(rows):
        assert row['start'] + row['duration'] <= row['slot_end'] + .01
        if i:
            assert rows[i-1]['start'] + rows[i-1]['duration'] + .08 <= row['start']
        length = row['duration']
        filters = f"atrim=start={row['source_start']}:end={row['source_end']},asetpts=PTS-STARTPTS,volume={row['gain_db']}dB,afade=t=in:d=0.015,afade=t=out:st={length-.025}:d=0.025"
        pcm = WORK / f'sentence-{i+1:02}.wav'
        run(['-y', '-i', str(GENERATED / row['source']), '-af', filters, '-ar', str(RATE), '-ac', '1', '-c:a', 'pcm_s16le', str(pcm)])
        with wave.open(str(pcm), 'rb') as wav:
            chunk = array.array('h', wav.readframes(wav.getnframes()))
        offset = round(row['start'] * RATE)
        assert offset + len(chunk) <= len(samples)
        samples[offset:offset+len(chunk)] = chunk
        row['audio_end'] = row['start'] + len(chunk) / RATE
        print('Aligned', i+1, row['segment_id'], round(row['start'], 3), flush=True)
    raw = WORK / 'mix.wav'
    with wave.open(str(raw), 'wb') as wav:
        wav.setparams((1, 2, RATE, 0, 'NONE', 'not compressed')); wav.writeframes(samples.tobytes())
    measured = loudness(raw)
    norm = f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}:measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}:offset={measured['target_offset']}:linear=true:print_format=json"
    staged_audio = WORK / 'final-voiceover.wav'
    run(['-y', '-i', str(raw), '-af', norm, '-ar', str(RATE), '-c:a', 'pcm_s24le', str(staged_audio)])
    final_loudness = loudness(staged_audio)
    assert abs(float(final_loudness['input_i']) + 16) < 1
    assert float(final_loudness['input_tp']) <= -1.4
    srt = ''; vtt = 'WEBVTT\n\n'
    ass = (VIDEO / 'subtitles/captions.ass').read_text(encoding='utf-8').split('Dialogue:')[0]
    def ass_time(second): return stamp(second, '.')[1:-1]
    for i, row in enumerate(rows):
        limit = rows[i+1]['start'] - .06 if i+1 < len(rows) else DURATION
        end = min(limit, max(row['audio_end']+.25, row['start']+len(row['text'])/17))
        row['caption_end'] = end
        row['caption_cps'] = len(row['text']) / (end-row['start'])
        assert row['caption_cps'] <= 24
        lines = textwrap.wrap(row['text'], width=58, break_long_words=False, break_on_hyphens=False)
        assert len(lines) <= 2
        text = '\n'.join(lines)
        srt += f"{i+1}\n{stamp(row['start'])} --> {stamp(end)}\n{text}\n\n"
        vtt += f"{stamp(row['start'], '.')} --> {stamp(end, '.')}\n{text}\n\n"
        ass += f"Dialogue: 0,{ass_time(row['start'])},{ass_time(end)},Default,,0,0,0,," + r'\N'.join(lines) + '\n'
    for extension, text in [('srt', srt), ('vtt', vtt), ('ass', ass)]:
        (VIDEO / f'subtitles/captions-ai.{extension}').write_text(text.rstrip()+'\n', encoding='utf-8')
    stage = WORK / 'ai-voice.mp4'
    print('Rendering captioned H.264/AAC film', flush=True)
    run(['-y', '-i', str(originals[0]), '-i', str(staged_audio), '-vf', 'ass=demo-video/subtitles/captions-ai.ass:fontsdir=demo-video/.production-work/fonts',
         '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'libx264', '-preset', 'fast', '-crf', '17', '-threads', '4', '-pix_fmt', 'yuv420p', '-r', '30',
         '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-metadata:s:a:0', 'language=pol', '-map_metadata', '-1', '-movflags', '+faststart', str(stage)])
    meta = probe(stage); video, audio = meta['streams']
    assert (video['codec_name'], video['width'], video['height'], video['avg_frame_rate'], video['nb_frames']) == ('h264',1920,1080,'30/1','4950')
    assert audio['codec_name'] == 'aac' and abs(float(meta['format']['duration'])-165) < .1
    decoded = run(['-v', 'error', '-i', str(stage), '-f', 'null', '-'])
    assert not decoded.stderr.strip(), decoded.stderr
    assert before == {str(p.relative_to(ROOT)): signature(p) for p in originals}
    assert rows[-1]['audio_end'] < 165
    gaps = [rows[i+1]['start'] - row['audio_end'] for i, row in enumerate(rows[:-1])]
    assert max(gaps) < 4.1, max(gaps)
    staged_audio.replace(AUDIO); stage.replace(OUTPUT)
    report = {'status': 'TECHNICAL_PASS_LISTENING_REQUIRED', 'duration':165, 'scene_length_changes':False, 'voice_speed_changes':False,
              'spoken_content_verified':False, 'mapping_basis':'explicit scene filenames plus exactly matching sentence/long-pause counts; not semantic speech recognition',
              'inputs':input_report, 'sentences':rows, 'loudness':final_loudness, 'max_inserted_gap_seconds':max(gaps),
              'original_inputs_and_movies_unchanged':True, 'full_decode':'PASS', 'ffprobe':meta,
              'listening_required':['whole film for spoken text and pronunciation', '0/4/5/6 delay result transitions', 'sentence joins and last word'],
              'max_caption_cps':max(r['caption_cps'] for r in rows)}
    report['ffprobe']['format']['filename'] = OUTPUT.name
    (QA / 'voiceover-sync.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Exported:', OUTPUT.name, '165s; listen before delivery', flush=True)


if __name__ == '__main__': main()
