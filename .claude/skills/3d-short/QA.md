# QA - before you show anything

Do the draft pass on `out/<slug>/draft/contact.jpg` (open the image) and the final pass on `short.mp4`.
Fix anything that fails and re-render; say what you fixed. Never say "looks good" without having opened the contact sheet.

## A. Contact sheet (draft and final)

One frame per shot at 70% of the shot, overlay included.

- [ ] The hero is fully inside the frame in every tile - nothing cropped by the sides, nothing hidden behind the caption band (66-80%).
- [ ] The look is the same in every tile (teal void, silver hero). No tile is washed out, blown white or near-black.
- [ ] Reveal is readable: cutaway shows coral faces, xray shows the internals through the shell, explode shows the modules apart.
- [ ] Flow lines are visible and the colour matches what they carry (mint air, orange heat, yellow fuel, violet electric).
- [ ] Every label is readable, inside the side margins, not overlapping another label or the caption, and points at the part it names.
- [ ] Neighbouring tiles have visibly different camera angles.
- [ ] The title card (first shot) and a step badge (stage shots) show where expected.

## B. Numbers (`python engine/make_short.py` prints these in `verify`; `out/<slug>/audio_report.json` has the audio)

- [ ] 1080x1920, 30 fps, H.264 + AAC, length 28-62 s (target 35-45).
- [ ] Integrated loudness -14 LUFS (+-1), true peak <= -1 dBTP.
- [ ] Speech-to-music ratio >= 15 dB (the mix stage fails otherwise).
- [ ] Every script line is audible and complete (listen to the first and last line: `ffmpeg -i short.mp4 -ss 0 -t 5 -f null -` is not enough - open the file or ask the user).

## C. Story

- [ ] Line 0 hooks within 3 seconds; the hero is on screen in the first frame.
- [ ] The four stages appear in the order the script says them, each with a badge or label.
- [ ] Nothing on screen contradicts the narration (a label saying "Turbine" must sit on the turbine).
- [ ] Every number in the narration has a source in `brief.md`.

## D. Final pass only

- [ ] Scrub the final at 4 points (1 s, 10 s, 25 s, last 2 s): captions in sync with the voice, no flicker in the flow lines, no popping geometry.
- [ ] `cover.jpg` (the frame used as thumbnail) shows the hero clearly with the title text.
- [ ] File opens in a normal player; size under about 60 MB.

## Fix recipes

| Problem | Fix |
|---|---|
| Hero cropped in a focus shot | lower `focus_amount` (<= 0.5) and `push` (<= 0.1) |
| Labels crowded | stagger `t` by 0.6 s, set `"above": false` on every second one, drop to 3 labels |
| Flow lines invisible | raise `copies`, add `radius` 0.025, check the path name exists in the hero's `flows` |
| Too long (> 45 s) | cut a line from SCRIPT; re-run (voice and timing recalculate) |
| Flat/washed look | do not add lights; check no part uses pure white material |
