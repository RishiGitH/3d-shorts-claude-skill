"""Procedural sound effects (numpy / scipy only, no sample files).  All return mono float32 arrays at SR."""
import numpy as np
from scipy.signal import butter, sosfilt

SR = 48000


def _rng(seed):
    return np.random.default_rng(seed)


def _env(n, attack, release):
    t = np.arange(n) / SR
    e = np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-np.maximum(0, t - attack) / max(release, 1e-4))
    return e.astype(np.float32)


def _bp(x, lo, hi):
    return sosfilt(butter(2, [lo, hi], btype="band", fs=SR, output="sos"), x).astype(np.float32)


def whoosh(dur=0.8, seed=1):
    """Filtered noise swell: band sweeps 250 -> 4000 Hz, peaks in the middle.  Used at shot cuts."""
    n = int(dur * SR)
    noise = _rng(seed).standard_normal(n).astype(np.float32)
    out = np.zeros(n, np.float32)
    parts = 12
    edges = np.linspace(0, n, parts + 1).astype(int)
    for i in range(parts):
        f = 250 * (4000 / 250) ** (i / (parts - 1))
        seg = _bp(noise, f * 0.7, min(f * 1.4, SR / 2 - 100))
        w = np.zeros(n, np.float32)
        w[edges[i]:edges[i + 1]] = 1.0
        out += seg * np.convolve(w, np.hanning(int(0.12 * SR)) / np.hanning(int(0.12 * SR)).sum(), mode="same")
    t = np.linspace(0, 1, n)
    out *= np.sin(np.pi * t) ** 1.6
    return out / (np.abs(out).max() + 1e-9) * 0.8


def hit(dur=0.7, seed=2):
    """Low thump: sine dropping 150 -> 45 Hz plus a short noise click.  Used on reveals (cut opens, parts fly apart)."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 45 + 105 * np.exp(-t * 18)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * _env(n, 0.003, 0.22)
    click = _bp(_rng(seed).standard_normal(n).astype(np.float32), 1500, 6000) * _env(n, 0.001, 0.02) * 0.35
    out = body + click
    return (out / (np.abs(out).max() + 1e-9) * 0.9).astype(np.float32)


def tick(dur=0.18, freq=1320.0):
    """Short bell-ish blip for a label appearing."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * freq * 2.01 * t)) * _env(n, 0.002, 0.05)
    return (out / np.abs(out).max() * 0.6).astype(np.float32)


def rise(dur=0.9, seed=3):
    """Tension riser: noise + sine sweeping up, ends abruptly (follow with hit())."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 200 * (1800 / 200) ** (t / dur)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR)
    nz = _bp(_rng(seed).standard_normal(n).astype(np.float32), 800, 7000)
    out = (0.55 * s + 0.45 * nz) * (t / dur) ** 2
    return (out / (np.abs(out).max() + 1e-9) * 0.7).astype(np.float32)


KINDS = {"whoosh": whoosh, "hit": hit, "tick": tick, "rise": rise}


def place(events, total_seconds):
    """events: [(time_s, kind, gain_db)] -> one mono track of total_seconds."""
    out = np.zeros(int(total_seconds * SR) + SR, np.float32)
    for t, kind, gdb in events:
        w = KINDS[kind]() * (10 ** (gdb / 20))
        i = int(t * SR)
        j = min(len(out), i + len(w))
        if i < len(out):
            out[i:j] += w[: j - i]
    return out[: int(total_seconds * SR)]
