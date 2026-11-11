---
name: 3d-short
description: Make a finished vertical 3D explainer Short (1080x1920, 30 fps, ~40 s MP4 with voice, captions, labels and music) from one prompt such as "make a Short about how a jet engine works". Builds a stylized 3D object in Blender, opens it up (cutaway, X-ray or exploded view), animates flow lines, adds a free local voice and a mixed soundtrack. Use when the user asks for a 3D short, a "how does X work" Short, a cutaway / exploded-view animation, or a Blender explainer video.
---

# 3d-short - one prompt in, finished Short out

The user gives a topic. You deliver `out/<slug>/short.mp4` (1080x1920, 30 fps, 35-45 s, -14 LUFS) plus a cover image.
Everything runs locally: Blender (3D), ffmpeg, Python, and the free Piper voice. No account, no API key needed.

## Files in this skill

| File | Read it when |
|---|---|
| `WORKFLOW.md` | always - the steps, exact commands, `shots.json` format |
| `SCRIPT.md` | writing the narration |
| `LOOK.md` | building the hero object, choosing camera/reveal/flow colours |
| `QA.md` | before you show the user anything |
| `TROUBLESHOOTING.md` | any command fails |
| `examples/prompts.md` | the user asks "what can I make?" or you need a topic-to-hero example |

The working example is `projects/demo-jet-engine/` - copy its shape for every new Short.

## The five steps (details in WORKFLOW.md)

1. **Check the machine**: `python3 engine/setup/doctor.py` (use `python3` here: the venv does not exist yet). If anything is MISSING, tell the user in one line what will be installed
   (Blender, ffmpeg, Python packages, a ~75 MB voice) and **wait for a yes**, then run `bash engine/setup/install.sh --yes` (about 6 minutes, prints little; run it in the background and wait)
   (Windows: `engine\setup\install.ps1`).
2. **Plan**: pick the hero object and the 4 stages of how it works. Write `projects/<slug>/brief.md` (5 lines) and `script.txt`
   (100-140 words, one idea per line - see SCRIPT.md). Tell the user the hook line and the 4 stages; do not wait for an answer unless the topic is unclear.
3. **Build the hero**: a `projects/<slug>/hero.py` that returns a hero dict (see `engine/blender/props/kit.py`, example `props/jet_engine.py`), or import a free
   CC0/CC-BY `.glb` (see WORKFLOW.md "Hero from a GLB"). Look at one still before going on.
4. **Shots**: write `projects/<slug>/shots.json` - one shot per script line group, a camera, a reveal, flows, labels.
5. **Make it**: `python engine/make_short.py projects/<slug> --draft` (about 2 minutes) -> look at `out/<slug>/draft/contact.jpg` ->
   fix with notes -> run without `--draft` for the final (about 40 minutes). Verify, then run the QA checklist.

## Hard rules

- Ask before installing anything. Never run `sudo` without telling the user why.
- Draft first, always. Never start a final render before the contact sheet of the draft passes QA.
- Look at the contact sheet yourself (open the JPG). A render you did not look at is not done.
- One idea per script line; the shot count equals the number of line groups; every label names a real part of the hero.
- Keep the Studio Glow look (LOOK.md): dark teal void, silver hero, coral cut faces, mint/orange/yellow/violet flow lines. Do not invent a new look per video.
- The voice is Piper by default. If the user has `GEMINI_API_KEY` or `ELEVENLABS_API_KEY` and asks for a nicer voice, use `--voice gemini` / `--voice elevenlabs`.
- Never claim a facts-heavy script is correct without checking it: every number in the narration must be one you can source (SCRIPT.md, "Facts").
- Output stays in `out/` (git-ignored). Do not commit videos, `.blend` files, or voices.

## What to tell the user at the end

Three lines: the path of `short.mp4`, its length, and the one thing you would change if they want a second pass.
Offer the contact sheet path so they can judge the look without watching.
