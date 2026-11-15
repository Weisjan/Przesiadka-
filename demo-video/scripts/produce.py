"""Reproduce the local recruitment film without TTS or external API calls."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VIDEO = ROOT / 'demo-video'


def main():
    # Unset by name without reading the value. Child processes inherit no ORS key.
    os.unsetenv('ORS_API_KEY')
    required = [VIDEO / '.work/tools/ffmpeg.exe', VIDEO / '.work/tools/ffprobe.exe',
                ROOT / 'backend/data/demo/manifest.json', ROOT / 'backend/data/demo/transit.db',
                ROOT / 'backend/data/demo/walking.db']
    for path in required:
        if not path.is_file():
            raise SystemExit('Missing local prerequisite: ' + str(path.relative_to(ROOT)))
    steps = [
        ('capture/capture.py', '--sample', '--tests'),
        ('render/verify.py', '--sample'),
        ('capture/capture.py',),
        ('render/render.py',),
        ('render/verify.py',),
    ]
    for script, *arguments in steps:
        print('Production step: ' + script, flush=True)
        subprocess.run([sys.executable, '-B', str(VIDEO / 'scripts' / script), *arguments],
                       cwd=ROOT, check=True)
    print('Finished: demo-video/final/ (two silent MP4 masters)', flush=True)


if __name__ == '__main__':
    main()
