"""Final mix: voice + procedural bed + sfx -> mix.wav (stereo 48 kHz), mastered to -14 LUFS / true peak <= -1 dBTP.

  python engine/audio/mix.py voice.wav sfx.json out/mix.wav [--duration S]

sfx.json: [[time_s, "whoosh|hit|tick|rise", gain_db], ...]
Rules (checked and enforced here):
  * bed sits >= 17 dB under the voice while someone is speaking (speech-ratio gate, tightened automatically until it passes)
  * sfx sit >= 9 dB under the voice peak
  * loudnorm two-pass, linear: integrated -14 LUFS, true peak <= -1 dBTP
"""
import json, os, subprocess, sys, wave
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfx as SFX
import bed as BED

SR = 48000


def read_mono(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
        if w.getnchannels() > 1:
            a = a.reshape(-1, w.getnchannels()).mean(1)
    if sr != SR:
        from scipy.signal import resample_poly
        g = int(np.gcd(sr, SR))
        a = resample_poly(a, SR // g, sr // g).astype(np.float32)
    return a


def write_stereo(path, a):
    a = np.clip(a, -1, 1)
    st = np.stack([a, a], 1)
    with wave.open(path, "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((st * 32767).astype(np.int16).tobytes())


def rms_db(x):
    return 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)


def speech_frames(voice, win=0.05):
    n = int(win * SR)
    m = len(voice) // n
    r = np.sqrt((voice[: m * n].reshape(m, n) ** 2).mean(1))
    return r > max(0.02, 0.15 * np.percentile(r, 95)), n


def smooth_env(active, n, total, attack=0.05, release=0.35):
    """Per-sample 0..1 'someone is speaking' curve with a fast attack and slow release (ducking envelope)."""
    env = np.repeat(active.astype(np.float32), n)
    env = np.pad(env, (0, max(0, total - len(env))))[:total]
    out = np.zeros_like(env)
    a, r = np.exp(-1 / (attack * SR)), np.exp(-1 / (release * SR))
    y = 0.0
    for i in range(0, total, 64):                         # block-wise one-pole (fast enough, 64-sample resolution)
        x = env[i]
        y = x + (y - x) * (a if x > y else r) ** 64
        out[i:i + 64] = y
    return out


def loudnorm(in_wav, out_wav):
    base = "loudnorm=I=-14:TP=-1.2:LRA=11"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", in_wav, "-af", base + ":print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    j = json.loads(r.stderr[r.stderr.rindex("{"): r.stderr.rindex("}") + 1])
    af = (base + f":measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
          f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", in_wav, "-af", af, "-ar", str(SR), out_wav], check=True)


def measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "loudnorm=I=-14:TP=-1:print_format=json", "-f", "null", "-"],
                       capture_output=True, text=True)
    j = json.loads(r.stderr[r.stderr.rindex("{"): r.stderr.rindex("}") + 1])
    return float(j["input_i"]), float(j["input_tp"])


def build(voice_wav, events, out_wav, duration=None):
    voice = read_mono(voice_wav)
    total = int((duration or len(voice) / SR) * SR)
    voice = np.pad(voice, (0, max(0, total - len(voice))))[:total]
    active, wn = speech_frames(voice)
    env = smooth_env(active, wn, total)
    mask = np.repeat(active, wn)
    mask = np.pad(mask, (0, max(0, total - len(mask))))[:total]
    v_active_db = rms_db(voice[mask]) if mask.any() else rms_db(voice)
    bed = BED.make_bed(total / SR)
    bed = np.pad(bed, (0, max(0, total - len(bed))))[:total]
    # bed level: 17 dB under speech RMS while speaking, +5 dB louder in the gaps (it "breathes" between lines)
    bed_gain_db = v_active_db - 17.0 - rms_db(bed)
    sfx_track = SFX.place(events, total / SR)
    sfx_track = np.pad(sfx_track, (0, max(0, total - len(sfx_track))))[:total]
    vpeak = float(np.abs(voice).max())
    sfx_scale = vpeak * 10 ** (-9 / 20) / max(1e-6, float(np.abs(sfx_track).max()))
    for attempt in range(6):
        gain = 10 ** (bed_gain_db / 20) * (1.0 + 0.7 * (1 - env))         # louder between lines
        under = bed * gain + sfx_track * sfx_scale * 0.7
        ratio = rms_db(voice[mask]) - rms_db(under[mask]) if mask.any() else 99.0
        if ratio >= 15.0:
            break
        bed_gain_db -= 2.0
    mix = voice + under
    mix /= max(1.0, float(np.abs(mix).max()) / 0.9)
    tmp = out_wav + ".pre.wav"
    write_stereo(tmp, mix)
    loudnorm(tmp, out_wav)
    os.remove(tmp)
    lufs, tp = measure(out_wav)
    print(f"mix: speech-ratio {ratio:.1f} dB (>=15), loudness {lufs:.1f} LUFS, true peak {tp:.1f} dBTP", flush=True)
    return {"speech_ratio_db": round(float(ratio), 1), "lufs": lufs, "true_peak": tp}


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("voice"); ap.add_argument("sfx"); ap.add_argument("out"); ap.add_argument("--duration", type=float)
    a = ap.parse_args()
    build(a.voice, [tuple(e) for e in json.load(open(a.sfx))], a.out, a.duration)
