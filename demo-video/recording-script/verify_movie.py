"""Check the actual final movie using local FFmpeg/ffprobe; no servers or network."""
import argparse
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

OUT = Path(__file__).resolve().parents[1]
VERIFY = OUT / 'verification'


def tool(value, name):
    path = value or shutil.which(name) or str(OUT / '.work/tools' / (name + '.exe'))
    if not Path(path).is_file():
        raise RuntimeError(f'Missing {name}; pass --{name}.')
    return str(Path(path).resolve())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--ffmpeg')
    parser.add_argument('--ffprobe')
    args = parser.parse_args()
    ffmpeg, ffprobe = tool(args.ffmpeg, 'ffmpeg'), tool(args.ffprobe, 'ffprobe')
    movie = OUT / 'przesiadka-demo.mp4'
    metadata = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(movie)]))
    video = metadata['streams'][0]
    assert video['codec_name'] == 'h264'
    assert (video['width'], video['height'], video['avg_frame_rate'], video['nb_frames']) == (1920, 1080, '30/1', '3000')
    assert len(metadata['streams']) == 1 and float(metadata['format']['duration']) == 100
    # Decode every frame and detect almost entirely black intervals, not the intended dark palette.
    result = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'info', '-i', str(movie), '-vf',
        'blackdetect=d=0.033:pix_th=0.04:pic_th=0.998', '-an', '-f', 'null', '-'], capture_output=True, text=True, check=True)
    (VERIFY / 'full-decode.log').write_text(result.stderr, encoding='utf-8')
    assert 'black_start:' not in result.stderr, 'Unexpected black interval'
    assert 'Error' not in result.stderr and 'corrupt' not in result.stderr.lower()
    checks = json.loads((VERIFY / 'recording-checks.json').read_text(encoding='utf-8'))
    assert not checks['page_errors'] and not checks['external_requests']
    roi = checks['checks'][0]['roi']
    factor = 1792 / 1920
    x = math.floor(64 + roi['x'] * factor) // 2 * 2
    y = math.floor(16 + (roi['y'] - 32) * 978 / 1048) // 2 * 2
    size = math.ceil(roi['width'] * factor) // 2 * 2
    motion = []
    for name, second in [('green', 39), ('red', 46), ('grey', 61)]:
        frames = subprocess.check_output([ffmpeg, '-hide_banner', '-loglevel', 'error', '-ss', str(second), '-i', str(movie),
            '-t', '1', '-vf', f'crop={size}:{size}:{x}:{y}', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'])
        frame_size = size * size * 3
        chunks = [frames[start:start + frame_size] for start in range(0, len(frames), frame_size)]
        assert len(chunks) == 30 and len(chunks[-1]) == frame_size
        unique = len({hashlib.sha256(frame).digest() for frame in chunks})
        first, opposite = chunks[0], chunks[11]
        changed_pixels = sum(max(abs(first[i + c] - opposite[i + c]) for c in range(3)) > 16 for i in range(0, frame_size, 3))
        assert unique >= 8 and changed_pixels >= 20, f'No convincing figure movement: {name}'
        motion.append({'state': name, 'start_second': second, 'sample_frames': 30, 'unique_decoded_frames': unique,
                       'pixels_changed_over_16_rgb_levels_after_11_frames': changed_pixels, 'crop': [x, y, size, size]})
    with movie.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    report = {'result': 'PASS', 'duration_seconds': 100, 'resolution': [1920, 1080], 'fps': '30/1', 'frames': 3000,
              'codec': 'h264', 'audio': False, 'bytes': movie.stat().st_size, 'sha256': digest,
              'full_decode': 'PASS', 'unexpected_black_intervals': 0, 'figure_motion': motion,
              'page_errors': [], 'external_browser_requests': [],
              'limitation': 'CFR sampler may repeat source frames; see capture-stats.json. This is not a complete application regression suite.'}
    (VERIFY / 'movie-check.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
