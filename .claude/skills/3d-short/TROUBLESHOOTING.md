# Troubleshooting

Start with `python engine/setup/doctor.py` - it names what is missing and the fix.

| Symptom | Cause | Fix |
|---|---|---|
| `Blender not found` | not installed or not on PATH | `bash engine/setup/install.sh`, or `export BLENDER=/path/to/blender` (mac: `/Applications/Blender.app/Contents/MacOS/Blender`) |
| `Blender 4.x is too old` | need 4.2+ (tested on 5.2) | install a newer Blender; `BLENDER=` selects it |
| `ModuleNotFoundError: PIL / numpy / piper` | wrong python | use `.venv/bin/python` (Windows `.venv\Scripts\python.exe`) or re-run the installer |
| `ffmpeg: command not found` | not installed | mac `brew install ffmpeg`, linux `sudo apt install ffmpeg`, windows `winget install Gyan.FFmpeg` |
| `voice model not found` | not downloaded | re-run the installer (downloads `assets/voices/en_US-libritts_r-medium.onnx` + `.json`) |
| `validate: lines must be consecutive...` | shots do not cover the script | every script line (0-based) belongs to exactly one shot, in order |
| `validate: reveal must be one of` | typo | `none`, `cutaway`, `xray`, `explode` |
| `label ... unknown part` | label names a part the hero does not have | use a key of the hero's `parts` or `anchors` (Blender prints them in the render log) |
| Render is black / white cube | stale Blender startup scene or missing hero | check `out/<slug>/<mode>/logs/<shot>.log`, the error is at the end |
| Blender exits with a Python traceback | hero script bug | the traceback is in that log; test the hero alone with `--draft --only-shot s01` |
| `EEVEE` engine error | enum name differs by Blender version | the engine tries `BLENDER_EEVEE` then `BLENDER_EEVEE_NEXT`; update Blender if both fail |
| Glow missing | compositor API differs | glare is wrapped in try/except; the look is still correct without it, just less bloom |
| Re-run does nothing | outputs are newer than inputs | `--from render` (or `--from voice`) forces a stage and everything after |
| Frames look stale after changing a shot | shots re-render only when their spec or the engine/hero code changed | changes to `hero.py`, `kit.py`, `studio.py` are detected too; if in doubt add `--from render` |
| Voice says a word oddly | TTS pronunciation | respell it in `script.txt` ("Li-ion" -> "lithium ion") and re-run |
| `speech ratio` gate fails | music too loud for a quiet voice | the mix lowers the music automatically; if it still fails the voice is too quiet or too short - try another `--speaker` |
| `ffmpeg failed while encoding` | out of disk or bad codec build | free space; ensure ffmpeg has libx264 (`ffmpeg -encoders | grep 264`) |
| Final render very slow | 1080x1920 x 32 samples x ~1100 frames | expected (about 2 s per frame on an Apple M4, ~40 min total); run it in the background and always draft first |
| Gemini/ElevenLabs voice fails | no key, quota, or model name | the error shows the HTTP status; fall back to `--voice piper`; Gemini model via `GEMINI_TTS_MODEL` |
| Windows: path errors | spaces / backslashes | run from the repo root, quote paths, use the `.venv\Scripts\python.exe` interpreter |

Logs: `out/<slug>/<mode>/logs/<shot>.log` (one per Blender run). When asking the user for help, show only the last 20 lines.
