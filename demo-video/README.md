# Recruitment video production

The current film is **2:45, 1920?1080, 30 FPS, H.264**. It records the real Kinetic Transit application in Edge and uses separate diagrams to explain the implemented planner. The narrated recruitment MP4 is selected for Git. Other movies and source audio remain local and excluded from Git.

## Exports and sources

| Local path under `demo-video/` | Purpose |
|---|---|
| `final/przesiadka-demo-ai-voice.mp4` | Polish TTSMaker narration, AAC audio and captions |
| `final/przesiadka-demo-clean.mp4` | Silent master without narrator captions; UI, diagram labels and attribution remain |
| `final/przesiadka-demo-subtitled.mp4` | Silent captioned version |
| `voiceover/generated/final-voiceover.wav` | Separate 48 kHz, 24-bit mono voice mix |
| `source/recordings/` | Actual Edge recordings, including the 18-second motion sample |
| `source/graphics/` | Versioned SVG diagram sources and ignored generated PNGs |

The root README links to `final/przesiadka-demo-ai-voice.mp4`, the only movie allowed by .gitignore for the recruitment submission. It has Polish AI narration and captions and needs a final listening check. Do not distribute databases or TTS inputs alongside the film by default.

[Storyboard](storyboard.md) ? [Narration](voiceover/voiceover-script.md) ? [Narration timeline](voiceover/narration-timeline.md)

The film follows Wrzeszcz ? Przegalina on 13 November 2026: SKM 17:02?17:09, Dworzec G??wny 08, two estimated walking minutes, bus 112 at 17:16, destination 18:21. Delay 0/4/5/6 produces margin +5/+1/0/?1. Original SVG/SMIL and the background remain animated; courses remain fixed during simulation.

| Time | Scene |
|---|---|
| 0:00?0:40 | Real form entry, search and recommendation, without an intro title card |
| 0:40?1:10 | Delay slider and three animated status figures |
| 1:10?1:45 | Planner diagram following exact train and bus stop occurrences |
| 1:45?2:20 | React/FastAPI, the pure evaluator, GTFS and walking-cache diagram |
| 2:20?2:45 | Test evidence, limited coverage and return to the application |

Diagram sources correspond to [planner.py](../backend/app/gtfs/planner.py), [transfer_logic.py](../backend/app/transfer_logic.py), [transfer_search.py](../backend/app/gtfs/transfer_search.py) and [Transit.tsx](../frontend/src/Transit.tsx). The diagrams explain code; they do not impersonate app UI. Keep provider attribution and the archival/estimated-data notices. [Demo provenance and limitations](../docs/demo.md).

## Reproduce the silent masters

Run from the repository root in Windows PowerShell. Prerequisites must already exist:

- Python with Playwright, Microsoft Edge, uv, Node/npm and the installed application dependencies;
- the existing `backend/data/demo/{transit.db,walking.db,manifest.json}` bundle, described in [demo setup](../docs/demo.md);
- local `demo-video/.work/tools/ffmpeg.exe` and `ffprobe.exe`, with libx264, drawtext and libass;
- Windows Bahnschrift and Segoe UI fonts.

No binaries, fonts or provider databases are distributed with the scripts. No script installs tools, downloads feeds, generates TTS or calls ORS.

```powershell
$RecordingPython = Read-Host 'Path to an existing python.exe with Playwright'
& $RecordingPython -B .\demo-video\scripts\produce.py
```

The runner performs a motion sample with fresh tests, sample verification, full capture, asset generation, editing and final verification. It unsets `ORS_API_KEY` by name without reading its value. Existing capture and master outputs are archived before replacement. It reuses a running demo only after validation; otherwise it starts its own services on a temporary copy and closes only those services. An ordinary backend occupying port 8000 is rejected.

`scripts/capture/capture.py` uses shared helpers in `recording-script/record.py`; retain that module. The older standalone 100-second recording workflow is documented in [recording-script/README.md](recording-script/README.md). It is not the current film pipeline. Its standalone command can replace the old root-level movie, so preserve that movie before intentionally rerunning it. `recording-script/verify_movie.py` verifies that older format. The old storyboard in `source/previous/` is a retained reference for that workflow.

To rerender without recording:

```powershell
& $RecordingPython -B .\demo-video\scripts\render\render.py
& $RecordingPython -B .\demo-video\scripts\render\verify.py
```

This requires the local `source/recordings/main.mp4`, `qa/tests.json` and `qa/main-capture.json`. A fresh clone does not contain them. The renderer crops 32 top pixels and keeps 930 pixels of native UI height, then pads the frame for subtitles without scaling. Main transitions last 250 ms. Test counts in the graphic come from the actual local test report.

## Narration and captions

The final text has 260 words in [voiceover-script.md](voiceover/voiceover-script.md). [voiceover-segments.json](voiceover/voiceover-segments.json) stores 22 target slots. Original silent-film captions are [SRT](subtitles/captions.srt) and [VTT](subtitles/captions.vtt); [SSML](voiceover/voiceover-ssml.xml) requires checking the chosen provider's dialect. See the [pronunciation guide](voiceover/pronunciation-guide.md) and [future TTS integration](voiceover/voiceover-integration.md) for replacing or recording another voice.

The current supplied recordings are five WAVs named `voiceover/generated/scene-01.wav` through `scene-05.wav`, not MP3s. The narrated version uses separate [SRT](subtitles/captions-ai.srt), [VTT](subtitles/captions-ai.vtt) and [ASS](subtitles/captions-ai.ass). The original masters, recordings, text and captions remain intact.

To assemble supplied audio, from the repository root:

```powershell
& .\backend\.venv\Scripts\python.exe -B .\demo-video\scripts\render\voiceover.py
```

The script needs the existing clean master, `qa/caption-cues.json`, local FFmpeg/ffprobe and fonts prepared by the silent render. It refuses to overwrite an existing narrated MP4 or final WAV. Keep those outputs in another local folder before a deliberate rerun. It matches scene filenames and long-pause counts, not recognized speech. [Audio synchronization and listening checklist](voiceover/ai-sync-notes.md) explains this limitation and the measured sentence mapping. Do not approve a replacement voice solely because technical checks pass.

## Verification and local artifacts

Run the video verifiers against their matching exports, not as substitutes for the application tests in the [root README](../README.md#testing). Logs, frame samples, input signatures and measured parameters are stored under ignored `qa/`; render intermediates and temporary copies are under `.production-work/`.

The silent export verifier checks parameters, full decoding, black frames, sampled figure/background motion, caption consistency and caption separation from the clean master. CDP capture uses constant 30 FPS and reports duplicated source frames; it does not promise 30 unique captures every second. The narrated export checks H.264/AAC, complete decoding, source preservation, loudness, caption text and timing bounds. Semantic speech verification and final listening remain manual.

Keep all other MP4s, WAVs, original TTS audio, downloaded tools, databases and working files on disk outside Git. Only `final/przesiadka-demo-ai-voice.mp4` is the recruitment deliverable selected for version control. Version scripts, source SVGs, configuration, captions and documentation. No provider license is automatically applied to application code. GTFS/ORS attribution and redistribution conditions are documented in [GTFS](../docs/gtfs.md), [walking](../docs/walking.md) and [demo](../docs/demo.md).
