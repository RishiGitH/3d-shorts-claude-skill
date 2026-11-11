# Workflow - exact steps and commands

Run every command from the repo root. Use the venv python: `.venv/bin/python` (Windows `.venv\Scripts\python.exe`); below it is written `python`.

## 0. Machine check

```bash
python3 engine/setup/doctor.py      # first run: system python3 (no venv yet); afterwards .venv/bin/python
```

Gate: it prints `READY`. If not, ask the user, then `bash engine/setup/install.sh --yes`, then re-run doctor.
The installer takes about 6 minutes and prints little - run it in the background. Blender 4.2 or newer is needed (tested on 5.2). Set `BLENDER=/path/to/blender` if it is installed somewhere unusual.

## 1. Project folder

```bash
mkdir projects/<slug>            # slug = kebab-case topic, e.g. lithium-battery
```
Files: `brief.md`, `script.txt`, `shots.json`, optional `hero.py`.

`brief.md` (5 lines): topic - the one-sentence promise - your 4 stages in order (jet engine: Fan -> Squeeze -> Burn -> Blast; battery: Charge -> Ions travel -> Store -> Power out) - hero object - the reveal you will use.

## 2. Script

Follow SCRIPT.md. `script.txt` = one narration line per row, 9-10 rows, 100-140 words, blank lines and `# comments` ignored.
Gate: word count 100-140 (`grep -v "^#" projects/<slug>/script.txt | wc -w`) and the read-aloud test from SCRIPT.md. The validate stage checks that shots cover every line.

## 3. Hero

A hero is a Python module with `build()` returning `kit.hero_dict(parts, shell, modules, spin, anchors, flows)`.
Conventions that the camera and reveals rely on:

- Long axis = world **X**, intake/front at **+X**. Centre the object near the origin; units are metres, 1.0 to 8.0 long is fine.
- Meshes are in world space (apply transforms); `parts` maps a name to its objects. Names appear in `shots.json` labels (`"part": "fan"`).
- `shell` = outer casings (cut by `cutaway`, glassy in `xray`, hidden in `explode`). `modules` = axial groups listed from +X to -X, which `explode` slides apart.
- `spin` = `{part: revolutions per second}`; never spin a shell.
- `anchors` = extra label points (`{"fuel": (x, y, z)}`); `flows` = named paths (list of xyz points, +X to -X) that shots draw as glowing lines.
- Helpers in `engine/blender/props/kit.py`: `lathe` (revolved profile), `tube`, `disc`, `box`, `cylinder`, `sphere`, `blade_ring`, `spiral_layers`, `join`, `mat`.
- Material arguments are a `kit.PALETTE` key (string) or the object returned by `mat("name", "#hex", metallic, roughness)`; a custom name as a string raises KeyError.
- A hero may `import studio as S`. To give a thin or inner part (a battery jelly roll) a permanent cut, call `S.cutaway(objs, fill_caps=False)` at build time; `fill_caps=True` on thin sheets gives one big coral wedge.
- Shell casings must be **open tubes** with end plates as separate parts: `cutaway` caps a closed lathe as one huge flat coral wedge that hides everything.
- Fat is better than long for 9:16: a hero whose length is more than about 3x its height fills only a quarter of the frame height. Rotate/pack long things or pick a chunky object.
- Put the hero in `projects/<slug>/hero.py` and reference it with `"hero": {"script": "hero.py"}`; copy `engine/blender/props/jet_engine.py` as the template.

Look at one still of the hero before writing shots:

```bash
python engine/make_short.py projects/<slug> --draft --only-shot s01
```
(the first shot renders in seconds; open `out/<slug>/draft/frames/s01/f_00000.png`).

### Hero from a GLB
If a free CC0/CC-BY model exists, use `"hero": {"glb": "model.glb", "length": 4.0, "groups": {"body": ["Mesh.001", "Mesh.002"]}, "shell": ["body"], "modules": 4}`
(`glb` path relative to the project; `groups` merges mesh names into named parts, `shell` lists casing parts, `modules` = how many axial groups `explode` makes).
`engine/blender/hero_import.py` orients the long axis to X, scales it to `length`, centres it, darkens flat black materials and prints every part name and size on the first run -
re-run once you know them. A GLB hero has no named flow paths and no spin, so use `reveal`, labels and camera moves only (or write a small `hero.py` that wraps the import and adds `flows`). Record the source URL and licence in `assets/LICENSES.md`. Skip NC (non-commercial) licences.

## 4. shots.json

```json
{
  "title": "How a jet engine works",
  "hero": {"module": "jet_engine"},
  "shots": [
    {"id": "s01", "lines": [0], "reveal": "none",
     "camera": {"az": 35, "el": 9, "orbit": 22, "push": 0.05},
     "labels": [{"text": "Turbofan engine", "anchor": "nacelle", "t": 1.6}]},
    {"id": "s02", "lines": [1], "reveal": "cutaway", "badge": {"n": 1, "text": "Fan"},
     "camera": {"az": 42, "el": 12, "orbit": 16, "push": 0.1},
     "flows": [{"path": "bypass", "color": "air", "copies": [-10, 20, 50], "swirl": 30}],
     "labels": [{"text": "Fan", "part": "fan", "t": 0.9}]}
  ]
}
```

| Field | Meaning |
|---|---|
| `title` | shown in the first 1.9 s |
| `hero` | `{"module": name}` (in `engine/blender/props/`), `{"script": "hero.py"}` (in the project) or `{"glb": ...}`; `"args": {...}` is passed to `build()` |
| `shots[].lines` | consecutive script line numbers (0-based) this shot narrates; all lines must be covered in order |
| `reveal` | `none`, `cutaway` (a wedge cut out, coral cut faces), `xray` (see-through shell), `explode` (modules slide apart; `explode_gap` 0.3-0.8) |
| `camera` | `az`/`el` degrees, `orbit` = degrees swept during the shot (10-22), `push` 0-0.15 dolly-in, `focus` = part/anchor to drift towards with `focus_amount` <= 0.6, `open_side` for cutaway (`+Y` default) |
| `badge` | `{"n": 1, "text": "Fan"}` step badge top-left (not in the first shot) |
| `flows[]` | `path` (a name in the hero's `flows`), `color` (`air` mint, `heat` orange, `fuel` yellow, `electric` violet, or `#rrggbb`), `copies` = list of rotation angles about X (one line each), `swirl` degrees of twist, `radius`, `delay` s |
| `labels[]` | `text` (<= 18 chars), one of `part` / `anchor` / `at: [x,y,z]`, `t` seconds into the shot, optional `side` (left/right), `above` (false = below the point), `offset` |

Flow copies are rotations about X; a cutaway opens roughly 0-70 degrees from +Y, so only copies in that range are visible, and opaque parts hide flows entirely (use `xray` or keep flows outside solid parts).

### Shot length
Aim for 3-5 s per shot (one idea per line); shots under 2.2 s feel like glitches - merge them with a neighbour (`"lines": [3, 4]`). `make_short` warns about them.

Rules: 1 shot per 3-5 s; max 3 labels per shot (4 only in an explode finale, staggered by 0.6 s); one reveal change per shot; vary `az` between neighbours by at least 8 degrees.

## 5. Make it

```bash
python engine/make_short.py projects/<slug> --draft     # 540x960, ~2 min, writes out/<slug>/draft.mp4 + draft/contact.jpg
```
Open `out/<slug>/draft/contact.jpg`, run QA.md, fix, repeat (re-runs only redo what changed: voice, timing, render per shot, audio, assemble).

Useful options: `--from render` (force a stage and later), `--only-shot s04` (render one shot), `--voice gemini|elevenlabs`, `--speaker N` (Piper voice number 0-903; `python engine/voice/tts.py projects/<slug>/script.txt out/<slug>/voice --audition` writes 12 samples).

```bash
python engine/make_short.py projects/<slug>              # final 1080x1920, every frame, ~40 min on an M4 - run in the background
```
Final output: `out/<slug>/short.mp4`, `out/<slug>/cover.jpg`, `out/<slug>/audio_report.json`. The last stage (`verify`) checks size, fps, length and loudness and prints PASS or the problem.

Stages: `validate -> voice -> timing -> render -> audio -> assemble -> verify`. A failed stage prints the reason; fix it and run the same command again (it resumes).

## 6. Hand over
Run QA.md. Give the user the path of `short.mp4`.
