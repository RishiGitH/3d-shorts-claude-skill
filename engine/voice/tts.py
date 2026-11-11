#!/usr/bin/env python3
"""Script -> voice.wav + lines.json (real per-line timings, no speech recognition needed).

  python engine/voice/tts.py projects/<slug>/script.txt out/<slug>/voice [--engine piper|gemini|elevenlabs]
                             [--speaker N] [--speed 1.0] [--audition]

script.txt: one narration line per text line (a line = one caption group = usually one shot beat).  Blank lines and lines
starting with # are ignored.
Engines
  piper       (default) free, local, offline.  Voice = assets/voices/en_US-libritts_r-medium.onnx (CC BY 4.0), 904 speakers.
  gemini      needs GEMINI_API_KEY (Google AI Studio key).  Model: env GEMINI_TTS_MODEL (default gemini-2.5-flash-preview-tts),
              voice: env GEMINI_VOICE (default Kore).
  elevenlabs  needs ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID.
--audition writes a short sample for speakers 0..11 so you can pick a Piper voice (then pass --speaker N).
Per-line takes are cached by content hash in <out>/takes/, so re-running after a script edit only synthesises changed lines.
"""
import argparse, base64, hashlib, json, os, subprocess, sys, urllib.request, urllib.error, wave
import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RATE = 24000
LEAD, GAP, TAIL = 0.45, 0.28, 0.9     # silence before the first line, between lines, after the last (seconds)
PIPER_MODEL = os.path.join(ROOT, "assets", "voices", "en_US-libritts_r-medium.onnx")
DEFAULT_SPEAKER = 0


def read_lines(path):
    out = []
    for ln in open(path, encoding="utf-8").read().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            out.append(ln)
    return out


def read_wav(path):
    with wave.open(path, "rb") as w:
        sr, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype={1: np.uint8, 2: np.int16, 4: np.int32}[sw]).astype(np.float32)
    if sw == 2:
        a /= 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(1)
    return a, sr


def resample(a, sr):
    if sr == RATE:
        return a
    from scipy.signal import resample_poly
    g = int(np.gcd(sr, RATE))
    return resample_poly(a, RATE // g, sr // g).astype(np.float32)


def write_wav(path, a):
    a = np.clip(a, -1, 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((a * 32767).astype(np.int16).tobytes())


def trim_silence(a, thresh=0.004, keep=0.06):
    idx = np.where(np.abs(a) > thresh)[0]
    if len(idx) == 0:
        return a
    k = int(keep * RATE)
    return a[max(0, idx[0] - k): idx[-1] + k]


# ---------------------------------------------------------------- engines
def synth_piper(text, out_wav, speaker, speed):
    if not os.path.exists(PIPER_MODEL):
        sys.exit("Piper voice missing: %s\nRun engine/setup/install.sh (or: python -m piper.download_voices en_US-libritts_r-medium "
                 "--download-dir assets/voices)" % PIPER_MODEL)
    cmd = [sys.executable, "-m", "piper", "-m", PIPER_MODEL, "-f", out_wav, "-s", str(speaker),
           "--length-scale", str(1.0 / speed), "--sentence-silence", "0.12"]
    r = subprocess.run(cmd, input=text.encode("utf-8"), capture_output=True)
    if r.returncode != 0 or not os.path.exists(out_wav):
        sys.exit("piper failed:\n" + r.stderr.decode("utf-8", "replace")[-800:])


def _http_json(url, payload, headers):
    req = urllib.request.Request(url, json.dumps(payload).encode(), {"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code} from {url.split('?')[0]}: {e.read().decode('utf-8', 'replace')[:400]}")


def synth_gemini(text, out_wav):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY is not set (get a key at https://aistudio.google.com/apikey) - or use --engine piper")
    model = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
    voice = os.environ.get("GEMINI_VOICE", "Kore")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    d = _http_json(url, {"contents": [{"parts": [{"text": text}]}],
                         "generationConfig": {"responseModalities": ["AUDIO"],
                                              "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}},
                   {"x-goog-api-key": key})
    pcm = base64.b64decode(d["candidates"][0]["content"]["parts"][0]["inlineData"]["data"])      # 24 kHz mono 16-bit PCM
    with wave.open(out_wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)


def synth_elevenlabs(text, out_wav):
    key, vid = os.environ.get("ELEVENLABS_API_KEY"), os.environ.get("ELEVENLABS_VOICE_ID")
    if not key or not vid:
        sys.exit("ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID must be set - or use --engine piper")
    req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
                                 json.dumps({"text": text, "model_id": os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")}).encode(),
                                 {"Content-Type": "application/json", "xi-api-key": key, "Accept": "audio/mpeg"})
    try:
        mp3 = urllib.request.urlopen(req, timeout=120).read()
    except urllib.error.HTTPError as e:
        sys.exit(f"ElevenLabs HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:400]}")
    tmp = out_wav + ".mp3"
    open(tmp, "wb").write(mp3)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ac", "1", "-ar", str(RATE), out_wav], check=True)
    os.remove(tmp)


def take(text, engine, speaker, speed, takes_dir):
    h = hashlib.sha1(f"{engine}|{speaker}|{speed}|{os.environ.get('GEMINI_VOICE', '')}|{text}".encode()).hexdigest()[:16]
    p = os.path.join(takes_dir, f"{h}.wav")
    if os.path.exists(p) and os.path.getsize(p) < 2048:      # truncated by an interrupted run
        os.remove(p)
    if not os.path.exists(p):
        if engine == "piper":
            synth_piper(text, p, speaker, speed)
        elif engine == "gemini":
            synth_gemini(text, p)
        elif engine == "elevenlabs":
            synth_elevenlabs(text, p)
        else:
            sys.exit(f"unknown engine {engine!r}")
    a, sr = read_wav(p)
    return trim_silence(resample(a, sr))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("outdir")
    ap.add_argument("--engine", default=os.environ.get("SHORTS_VOICE", "piper"))
    ap.add_argument("--speaker", type=int, default=int(os.environ.get("SHORTS_SPEAKER", DEFAULT_SPEAKER)))
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--audition", action="store_true")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.outdir, "takes"), exist_ok=True)
    takes_dir = os.path.join(a.outdir, "takes")
    if a.audition:
        for sid in range(12):
            w = take("A jet engine sucks in air and squeezes it, then burns it with fuel.", "piper", sid, a.speed, takes_dir)
            write_wav(os.path.join(a.outdir, f"audition_speaker{sid:02d}.wav"), w)
        print("wrote", a.outdir + "/audition_speaker00..11.wav")
        return
    lines = read_lines(a.script)
    if not lines:
        sys.exit("script.txt has no lines")
    chunks, meta, t = [np.zeros(int(LEAD * RATE), np.float32)], [], LEAD
    for i, text in enumerate(lines):
        w = take(text, a.engine, a.speaker, a.speed, takes_dir)
        meta.append({"id": i, "text": text, "start": round(t, 3), "end": round(t + len(w) / RATE, 3)})
        chunks.append(w)
        t += len(w) / RATE
        gap = GAP if i < len(lines) - 1 else TAIL
        chunks.append(np.zeros(int(gap * RATE), np.float32))
        t += gap
    voice = np.concatenate(chunks)
    write_wav(os.path.join(a.outdir, "voice.wav"), voice)
    json.dump({"duration": round(len(voice) / RATE, 3), "lines": meta}, open(os.path.join(a.outdir, "lines.json"), "w"), indent=1)
    print(f"voice.wav {len(voice) / RATE:.1f}s, {len(lines)} lines ({a.engine})")


if __name__ == "__main__":
    main()
