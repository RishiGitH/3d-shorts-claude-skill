"""Procedural music bed: soft chord pad + low pulse + sparse plucks.  No samples, no licence worries.  Mono float32 at SR."""
import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000
# Am - F - C - G, root notes in Hz (octave 2) and chord tones as semitone offsets
PROG = [(110.00, (0, 3, 7, 12)), (87.31, (0, 4, 7, 12)), (130.81, (0, 4, 7, 12)), (98.00, (0, 4, 7, 12))]
PENTA = [0, 3, 5, 7, 10, 12, 15, 17]


def _note(f, dur, kind="pad"):
    n = int(dur * SR)
    t = np.arange(n) / SR
    if kind == "pad":
        w = sum(np.sin(2 * np.pi * f * (1 + d) * t + p) for d, p in ((0.0, 0), (0.003, 1.3), (-0.004, 2.1)))
        w += 0.4 * np.sin(2 * np.pi * f * 2 * t)
        env = np.minimum(1, t / 0.9) * np.minimum(1, (dur - t) / 0.9)
        return (w * env / 3).astype(np.float32)
    w = np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * 2 * f * t)            # pluck
    return (w * np.exp(-t * 7) * np.minimum(1, t / 0.004)).astype(np.float32)


def make_bed(duration, bpm=92, seed=7):
    rng = np.random.default_rng(seed)
    n = int(duration * SR)
    out = np.zeros(n + 2 * SR, np.float32)
    beat = 60.0 / bpm
    bar = 4 * beat
    nbars = int(duration / bar) + 2
    for b in range(nbars):
        root, tones = PROG[b % 4]
        t0 = b * bar
        for k, st in enumerate(tones):
            w = _note(root * 2 ** (st / 12) * (2 if k else 1), bar + 0.6, "pad") * (0.5 if k else 0.9)
            i = int(t0 * SR)
            if i < len(out):
                out[i:i + len(w)] += w[: len(out) - i]
        for q in range(4):                                       # soft low pulse on every beat
            i = int((t0 + q * beat) * SR)
            nn = int(0.25 * SR)
            tt = np.arange(nn) / SR
            thump = np.sin(2 * np.pi * (52 + 40 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 14) * 0.5
            if i + nn < len(out):
                out[i:i + nn] += thump.astype(np.float32)
        for e in range(8):                                       # sparse eighth-note plucks
            if rng.random() < 0.45:
                f = root * 4 * 2 ** (PENTA[rng.integers(0, len(PENTA))] / 12)
                w = _note(f, 0.5, "pluck") * 0.18
                i = int((t0 + e * beat / 2) * SR)
                if i + len(w) < len(out):
                    out[i:i + len(w)] += w
    out = out[:n]
    out = sosfilt(butter(2, 3800, btype="low", fs=SR, output="sos"), out).astype(np.float32)
    fade_in, fade_out = int(1.0 * SR), int(1.6 * SR)
    out[:fade_in] *= np.linspace(0, 1, fade_in)
    out[-fade_out:] *= np.linspace(1, 0, fade_out)
    return out / (np.abs(out).max() + 1e-9) * 0.9
