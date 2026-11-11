# Look - "Studio Glow"

One generic look for every topic. It is defined in `engine/blender/studio.py` (3D) and `engine/overlay/draw.py` (2D); you rarely change it.
The goal: a silver, realistic-but-simple object floating in a dark teal studio, opened up so the viewer sees the mechanism, with glowing coloured lines showing what moves through it.

## Palette

| Role | Colour |
|---|---|
| Background gradient | top `#0e4a50` -> bottom `#030c0d` (deep teal to near-black) |
| Floor | `#071a1c` with a faint grid `#7fe8dc` fading out with distance |
| Hero metal | silver `#9aa8ae` (metallic 0.55, roughness 0.38); mid steel `#7a8b92` and dark steel `#3a484e` for contrast between parts |
| Accent parts | copper, gold, teal, rubber, graphite (see `kit.PALETTE`) - at most 2 accents per hero |
| Cut faces (cutaway) | coral `#e8573f` |
| Flow: air | mint `#5ff2c0` |
| Flow: heat | orange `#ff8a2a` |
| Flow: fuel | yellow `#ffd23f` |
| Flow: electric | violet `#9a6bff` |
| Overlay | white pills with ink `#082628` text, coral dot; captions white with ink outline |

Colour meaning is fixed across all Shorts: mint = air/gas/coolant, orange = heat/exhaust, yellow = fuel/liquid, violet = electricity/ions. Pick the flow colour by what it carries.

## Rendering numbers

- EEVEE, view transform **Khronos PBR Neutral**, no exposure tweaks. Three-point lighting from the studio rig (key 800 W, two teal rims, fill 160 W) plus a dark soft-box environment.
- Glow = compositor glare on the emission pass; flow lines are emissive bevelled curves, strength 2.2.
- Contact shadow under the hero, floor 0.08 m below its lowest point.
- Draft 540x960 / 8 samples / every 3rd frame; final 1080x1920 / 32 samples / every frame, 30 fps.

## Camera rules

- Hero fills about 86% of the frame width at both ends of the orbit. Centre of the hero sits at 54% of the height (captions live below at 66-80%).
- Slow orbit of 10-22 degrees per shot, `push` at most 0.15, `focus_amount` at most 0.6. More than that crops the hero and the label points fall off screen.
- Elevation 7-16 degrees (low, heroic); never straight on, never top-down.
- Neighbouring shots differ by at least 8 degrees of azimuth so every cut reads as a new angle.

## Reveals - choose by what the viewer must see

| Reveal | Use for | Do not use for |
|---|---|---|
| `cutaway` | an internal sequence along an axis (engine, pump, battery) | objects whose inside is a single cavity |
| `xray` | seeing moving parts through the casing, long flow paths | when you need coral cut faces |
| `explode` | the finale: "all the parts, in order" | the first shots (the viewer has not seen the whole yet) |
| `none` | hook and closing hero shots | explaining anything |

A typical Short: hook (none) -> 4 stage shots (cutaway / xray) -> payoff (none or explode).

## Overlay rules (1080x1920 safe areas)

- Captions: chunks of up to 3 words that break at commas and full stops, Barlow Bold 88 px, at 70% height. Nothing else in the 66-80% band.
- Labels: white pill, 48 px, max 18 characters, inside the 5% side margins, never in the bottom 18% or top 8%.
- Step badge: coral circle with the step number + word, top-left, only in stage shots.
- Title: first 1.9 s only, top.
- Sound design: whoosh on every cut, rise + hit on reveals, a tick as each label pops in; music is a quiet synthetic pad, 17-19 dB under the voice.

## Known weak spots (judge before you ship)

- Long thin heroes shrink in 9:16; prefer chunky objects or shorter proportions.
- Small flow streaks (ions, electrons) are easy to miss: use `radius` 0.03+, more `copies`, longer paths.
- `xray` can look milky with bloom: keep the hero lighter materials out of the shell, avoid white parts.
- Black insulator discs look odd in `explode`: use `steel_dark`, not pure black.

## Making a new hero look right

- Silver metal everywhere except the 1-2 parts the story is about; make those a contrasting material (copper coil, gold contact, teal housing).
- Add detail only where the camera goes: blades, stages, injectors. Skip bolts and fillets.
- Check one still before animating anything (`--draft --only-shot s01`).
