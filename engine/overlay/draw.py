"""2D overlay for the Short (Pillow): title card, step badge, label pills with leader lines, captions.

Everything is drawn per output frame at 30 fps on top of the rendered Blender frame, so overlay changes never need a
re-render.  Safe areas (1080x1920): captions sit at 66-80% of the height, labels stay inside the 6% side margins, nothing is
placed in the bottom 18% (platform buttons) or the top 8%.
"""
import os, math, re
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
FONT_BOLD = os.path.join(ROOT, "assets", "fonts", "Barlow-Bold.ttf")
FONT_SEMI = os.path.join(ROOT, "assets", "fonts", "Barlow-SemiBold.ttf")
CORAL = (232, 87, 63)
INK = (8, 38, 40)
WHITE = (255, 255, 255)
MINT = (95, 242, 192)
_fonts = {}


def font(path, size):
    k = (path, size)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(path, size)
    return _fonts[k]


def ease(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def wrap(draw, text, fnt, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def caption_chunks(lines, max_words=3):
    """[(start, end, text)] - each narration line split into 2-3 word chunks timed by character share."""
    out = []
    for ln in lines:
        groups = []
        # split at punctuation first so a caption never straddles a clause ("back," | "and the pull")
        clauses = [c.split() for c in re.findall(r"[^,;:.!?\u2014]+[,;:.!?\u2014]*", ln["text"]) if c.strip()]
        merged = []
        for words in clauses:                            # one-word clauses ("Fan," "squeeze,") flash too fast: pair them
            if merged and len(merged[-1]) == 1 and len(merged[-1]) + len(words) <= max_words:
                merged[-1] = merged[-1] + words
            else:
                merged.append(words)
        for words in merged:
            n = len(words)
            k = -(-n // max_words)                      # fewest chunks, then spread the words evenly
            base, extra = divmod(n, k)
            i = 0
            for j in range(k):
                take = base + (1 if j < extra else 0)
                groups.append(" ".join(words[i:i + take]))
                i += take
        weights = [len(g) + 3 for g in groups]
        tot = float(sum(weights))
        t = ln["start"]
        dur = ln["end"] - ln["start"]
        for g, w in zip(groups, weights):
            out.append((t, t + dur * w / tot, g))
            t += dur * w / tot
    return out


class Overlay:
    def __init__(self, cfg, lines, W, H):
        self.cfg, self.W, self.H = cfg, W, H
        self.s = W / 1080.0
        self.chunks = caption_chunks(lines)
        self.title = cfg.get("title", "")

    # ------------------------------------------------------------ pieces
    def _caption(self, layer, t):
        d = ImageDraw.Draw(layer)
        cur = next(((a, b, g) for a, b, g in self.chunks if a <= t < b), None)
        if not cur:
            return
        a, b, text = cur
        k = ease((t - a) / 0.08)                                  # tiny pop-in
        fnt = font(FONT_BOLD, int(88 * self.s))
        lines = wrap(d, text.upper() if self.cfg.get("caption_caps", False) else text, fnt, self.W * 0.86)
        lh = int(100 * self.s)
        y0 = int(self.H * 0.70) - (len(lines) * lh) // 2 + int((1 - k) * 12 * self.s)
        for i, ln in enumerate(lines):
            w = d.textlength(ln, font=fnt)
            d.text(((self.W - w) / 2, y0 + i * lh), ln, font=fnt, fill=WHITE + (int(255 * k),),
                   stroke_width=int(9 * self.s), stroke_fill=INK + (int(255 * k),))

    def _title(self, layer, t):
        if t > 1.9:
            return
        a = ease(t / 0.3) * (1 - ease((t - 1.5) / 0.4))
        if a <= 0:
            return
        d = ImageDraw.Draw(layer)
        fnt = font(FONT_BOLD, int(104 * self.s))
        lines = wrap(d, self.title, fnt, self.W * 0.84)
        lh = int(116 * self.s)
        y0 = int(self.H * 0.085) + int((1 - ease(t / 0.4)) * -30 * self.s)
        for i, ln in enumerate(lines):
            w = d.textlength(ln, font=fnt)
            d.text(((self.W - w) / 2, y0 + i * lh), ln, font=fnt, fill=WHITE + (int(255 * a),),
                   stroke_width=int(8 * self.s), stroke_fill=INK + (int(255 * a),))
        bw = int(min(self.W * 0.5, 460 * self.s) * ease(t / 0.5))
        yb = y0 + len(lines) * lh + int(14 * self.s)
        d.rounded_rectangle(((self.W - bw) / 2, yb, (self.W + bw) / 2, yb + int(10 * self.s)), radius=int(5 * self.s), fill=CORAL + (int(255 * a),))

    def _badge(self, layer, badge, t_in_shot):
        if not badge:
            return
        a = ease(t_in_shot / 0.3)
        d = ImageDraw.Draw(layer)
        r = int(44 * self.s)
        cx, cy = int(self.W * 0.06) + r, int(self.H * 0.115)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=CORAL + (int(255 * a),))
        f1 = font(FONT_BOLD, int(54 * self.s))
        n = str(badge.get("n", ""))
        w = d.textlength(n, font=f1)
        d.text((cx - w / 2, cy - int(34 * self.s)), n, font=f1, fill=WHITE + (int(255 * a),))
        f2 = font(FONT_BOLD, int(56 * self.s))
        d.text((cx + r + int(20 * self.s), cy - int(36 * self.s)), badge.get("text", ""), font=f2, fill=WHITE + (int(255 * a),),
               stroke_width=int(7 * self.s), stroke_fill=INK + (int(255 * a),))

    def _labels(self, layer, labels, anchors_now, t_in_shot):
        d = ImageDraw.Draw(layer)
        fnt = font(FONT_SEMI, int(48 * self.s))
        placed = []
        items = []
        for i, lb in enumerate(labels):
            an = anchors_now.get(str(i))
            if not an:
                continue
            t0 = float(lb.get("t", 0.7 + 0.45 * i))
            a = ease((t_in_shot - t0) / 0.28)
            if not an[2]:
                a *= 0.0
            if a <= 0.01:
                continue
            items.append((i, lb, an, a))
        items.sort(key=lambda it: it[2][1])
        for i, lb, an, a in items:
            ax, ay = an[0], an[1]
            text = lb["text"]
            tw = d.textlength(text, font=fnt)
            padx, h = int(34 * self.s), int(84 * self.s)
            w = tw + padx * 2 + int(34 * self.s)
            side = lb.get("side") or ("right" if ax < self.W * 0.5 else "left")
            dx = int(60 * self.s)
            px = ax + dx if side == "right" else ax - dx - w
            px = max(self.W * 0.05, min(self.W * 0.95 - w, px))
            py = ay - int(150 * self.s) * (1 if lb.get("above", True) else -1) - h / 2
            for (qx0, qy0, qx1, qy1) in placed:                          # keep pills apart
                if px < qx1 and px + w > qx0 and abs(py - qy0) < h + 14 * self.s:
                    py = qy0 + h + 18 * self.s
            py = max(self.H * 0.08, min(self.H * 0.78 - h, py))
            placed.append((px, py, px + w, py + h))
            al = int(255 * a)
            ex = px if side == "right" else px + w                            # leader attaches to the near edge
            d.line((ax, ay, ex, py + h / 2), fill=WHITE + (int(200 * a),), width=max(2, int(4 * self.s)))
            r = int(11 * self.s * (0.6 + 0.4 * a))
            d.ellipse((ax - r - 5 * self.s, ay - r - 5 * self.s, ax + r + 5 * self.s, ay + r + 5 * self.s), fill=CORAL + (al,))
            d.ellipse((ax - r, ay - r, ax + r, ay + r), fill=WHITE + (al,))
            d.rounded_rectangle((px, py, px + w, py + h), radius=int(h / 2), fill=(255, 255, 255, int(245 * a)))
            cr = int(11 * self.s)
            cx, cy = px + padx * 0.75 + cr, py + h / 2
            d.ellipse((cx - cr, cy - cr, cx + cr, cy + cr), fill=CORAL + (al,))
            d.text((px + padx + int(30 * self.s), py + (h - fnt.size) / 2 - int(6 * self.s)), text, font=fnt, fill=INK + (al,))

    # ------------------------------------------------------------ frame
    def compose(self, base, t_global, shot, t_in_shot, anchors_now, first_shot):
        """base: RGB PIL image from Blender -> RGB image with overlay."""
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        if first_shot:
            self._title(layer, t_global)
        elif shot.get("badge"):
            self._badge(layer, shot["badge"], t_in_shot)
        self._labels(layer, shot.get("labels", []), anchors_now, t_in_shot)
        self._caption(layer, t_global)
        out = base.convert("RGBA")
        out.alpha_composite(layer)
        return out.convert("RGB")
