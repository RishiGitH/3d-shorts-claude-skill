# Example prompts and how each becomes a Short

Say any of these (or your own topic) to Claude Code inside this repo:

| Prompt | Hero | Reveal | Four stages | Flow colours |
|---|---|---|---|---|
| "Make a 3D short about how a jet engine works." | turbofan (built in: `props/jet_engine.py`) | cutaway, xray, explode finale | Fan - Squeeze - Burn - Blast | mint air, yellow fuel, orange exhaust |
| "Make a 3D short about what's inside a lithium battery." | cylindrical 18650 cell (`kit.spiral_layers` for the jelly roll) | cutaway, then xray | Charge in - Ions travel - Store - Power out | violet ions/electrons, mint electrolyte |
| "Show how a heat pump works in a Short." | box with coil, fan, compressor, two copper loops | xray | Absorb - Compress - Release - Expand | orange heat, mint refrigerant |
| "3D short: how does a car turbo work?" | turbo snail housing, two wheels on one shaft | cutaway | Exhaust spins - Shaft - Air squeezed - Boost | orange exhaust, mint air |
| "How does a hydraulic press work, as a Short?" | two pistons, fluid chamber, press plate | cutaway | Small push - Fluid carries it - Big piston - Crush | yellow fluid, white pressure arrows via labels |

## What the skill does with a prompt

1. Picks the hero and 4 stages (a how-it-works object needs a clear in -> out path along one axis).
2. Writes `projects/<slug>/brief.md` + `script.txt` (SCRIPT.md), builds `hero.py` from `kit.py`.
3. Writes `shots.json`, drafts, checks the contact sheet, fixes, renders the final.

## Good topics

- A physical object whose inside shows a sequence: engines, pumps, batteries, turbines, locks, cameras, pens, coffee machines, toilets, zippers.
- One axis, 3-6 visible parts, a thing that moves through it (air, fuel, water, current, light).

## Poor topics

- Abstract ideas (inflation, blockchain), software, people or animals, anything needing a face.
- Objects with no internal sequence (a chair), or with hundreds of unique parts (a whole car).
- Medical or legal claims. Keep it mechanical.
