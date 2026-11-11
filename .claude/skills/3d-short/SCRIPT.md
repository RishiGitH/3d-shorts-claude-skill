# Script - 100-140 words, 35-45 seconds

Narration is spoken by a text-to-speech voice at about 3.4 words a second, so **140 words = about 37 s** with the default voice
(the demo script is 140 words / 37.1 s). Under 90 words feels thin; over 150 breaks the 45 s target.

## Shape (9 lines numbered 0-8, one idea each; 10 is fine)

| Line | Job | Example (jet engine) |
|---|---|---|
| 0 | **Hook** - a surprising fact or question the object answers, <= 14 words | "This engine swallows a bus-sized volume of air every second." |
| 1 | Name the object and show the first part | "Air enters through the fan, the big spinning wheel at the front." |
| 2-5 | **Four stages**, one line each, in the order the thing really works. Each starts with a verb or the stage name. | "Squeeze. The compressor packs that air into a tiny space." |
| 6 | The part that ties it together (shaft, wire, circuit) | "One shaft links the turbine to the fan." |
| 7 | The result / why it matters | "The hot blast leaving the back pushes the plane forward." |
| 8 | **Payoff** - the stages in a row, or a closing twist; ends the loop | "Fan, squeeze, burn, blast. Over and over." |

Each line should fit one shot of 3-5 s (8-16 words).

## Writing rules

- Short spoken sentences; read every line aloud once. If you run out of breath, split it.
- Concrete nouns and verbs. No "essentially", "basically", "it's important to note".
- No lists of three adjectives. No rhetorical "But here's the thing". No "Let's dive in" - TTS makes these sound robotic.
- Numbers: only ones you can source; say them naturally ("about five hundred") and spell out the unit.
- Spell out symbols and abbreviations for TTS: "lithium-ion" not "Li-ion", "twenty twenty-six" not "2026" if the voice stumbles.
- Ban list: "game-changer", "revolutionary", "mind-blowing", "Did you know" as an opener, "In this video".
- The last line should not say "follow for more".

## Facts

1. Write the numbers you want to use with a one-line source each in `brief.md` (`## Facts`).
2. If you cannot source it from memory with confidence, use a web search or leave the number out and say "a lot", "thousands of times a second".
3. Never invent a statistic to make a hook stronger.

## Checks before voice

```bash
grep -v "^#" projects/<slug>/script.txt | wc -w      # 100-140 (comments excluded)
```
- Lines are numbered from 0 in `shots.json`; the number of non-empty, non-`#` lines = what the shots must cover.
- Every stage you name in the script has a shot, a badge and a label.

## Voice

- Default: Piper `en_US-libritts_r-medium`, speaker 0 (calm, neutral). `python engine/voice/tts.py projects/<slug>/script.txt out/<slug>/voice --audition` writes `audition_speaker00..11.wav` into that folder; listen, pick one and pass `--speaker N`.
- Better quality with a key: `--voice gemini` with `GEMINI_API_KEY` set (voice name via `GEMINI_VOICE`) or `--voice elevenlabs` (needs `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID`). Only when the user asks; these send the script text to that provider.
- Re-running only re-records lines that changed (takes are cached per line).
