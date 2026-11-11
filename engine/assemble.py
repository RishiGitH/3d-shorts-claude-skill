"""Compose overlay onto rendered frames and encode the Short with ffmpeg (frames are piped, nothing temporary is written)."""
import json, os, subprocess, sys
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from overlay.draw import Overlay

FPS = 30


class Timeline:
    """Maps output time -> (shot, local time, base frame path, projected anchors)."""

    def __init__(self, cfg, timing, frames_root):
        self.cfg, self.timing, self.root = cfg, timing, frames_root
        self.meta = {}
        for s in timing:
            self.meta[s["id"]] = json.load(open(os.path.join(frames_root, s["id"], "meta.json")))
        self.shots = {s["id"]: s for s in cfg["shots"]}
        m0 = next(iter(self.meta.values()))
        self.W, self.H = m0["width"], m0["height"]
        self._cache = (None, None)

    def at(self, t):
        for i, s in enumerate(self.timing):
            if t < s["end"] or i == len(self.timing) - 1:
                break
        meta = self.meta[s["id"]]
        tl = max(0.0, t - s["start"])
        k = min(meta["n"] - 1, int(tl * FPS))
        step = meta["step"]
        k0 = (k // step) * step
        ks = [f["k"] for f in meta["frames"]]
        j = ks.index(k0) if k0 in ks else len(ks) - 1
        a, b = meta["frames"][j], meta["frames"][min(j + 1, len(meta["frames"]) - 1)]
        w = 0.0 if a is b else (k - a["k"]) / max(1, b["k"] - a["k"])
        anchors = {}
        for key, p in a["anchors"].items():
            q = b["anchors"][key]
            anchors[key] = [p[0] + (q[0] - p[0]) * w, p[1] + (q[1] - p[1]) * w, p[2] and q[2]]
        return i, self.shots[s["id"]], tl, os.path.join(self.root, s["id"], f"f_{k0:05d}.png"), anchors

    def base(self, path):
        if self._cache[0] != path:
            self._cache = (path, Image.open(path).convert("RGB"))
        return self._cache[1]


def frame_at(tl, ov, t):
    i, shot, tin, path, anchors = tl.at(t)
    return ov.compose(tl.base(path), t, shot, tin, anchors, first_shot=(i == 0))


def contact_sheet(tl, ov, out_jpg, cols=5, thumb_w=270):
    """One mid-shot frame per shot (with overlay) in a grid - the image QA is done on."""
    from PIL import ImageDraw
    tiles = []
    for s in tl.timing:
        t = s["start"] + (s["end"] - s["start"]) * 0.7
        tiles.append((s["id"], frame_at(tl, ov, t)))
    th = int(thumb_w * tl.H / tl.W)
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * th), (10, 10, 10))
    for n, (sid, im) in enumerate(tiles):
        im = im.resize((thumb_w, th), Image.LANCZOS)
        ImageDraw.Draw(im).text((8, 6), sid, fill=(255, 255, 255))
        sheet.paste(im, ((n % cols) * thumb_w, (n // cols) * th))
    sheet.save(out_jpg, quality=88)


def encode(tl, ov, total_seconds, audio_wav, out_mp4, draft=False):
    n = int(round(total_seconds * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{tl.W}x{tl.H}", "-r", str(FPS), "-i", "-",
           "-i", audio_wav, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast" if draft else "medium",
           "-crf", "24" if draft else "18", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-t", f"{total_seconds:.3f}",
           "-movflags", "+faststart", out_mp4]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame_at(tl, ov, i / FPS).tobytes())
        if i % 150 == 0:
            print(f"  encode {i}/{n}", flush=True)
    p.stdin.close()
    if p.wait() != 0:
        raise SystemExit("ffmpeg failed while encoding - see TROUBLESHOOTING.md (ffmpeg)")
