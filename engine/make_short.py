#!/usr/bin/env python3
"""One command: project folder -> finished 9:16 Short.

  python engine/make_short.py projects/<slug> [--draft] [--from <stage>] [--voice piper|gemini|elevenlabs] [--speaker N]
                              [--only-shot s03]

Stages (each is skipped when its output is newer than its inputs; --from <stage> forces a stage and everything after it):
  validate -> voice -> timing -> render -> audio -> assemble -> verify
Outputs go to out/<slug>/  (voice/, <mode>/frames, <mode>/contact.jpg, draft.mp4 or short.mp4, cover.jpg), mode = draft | final.
Draft = 540x960, 8 samples, every 3rd frame rendered (~10x faster).  Final = 1080x1920, 32 samples, every frame.
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import ROOT, find_blender, blender_version, venv_python, MIN_BLENDER

STAGES = ["validate", "voice", "timing", "render", "audio", "assemble", "verify"]
REVEALS = ("none", "cutaway", "xray", "explode")
FLOW_COLORS = ("air", "heat", "fuel", "electric")


def die(msg, hint=None):
    print(f"\nERROR: {msg}", file=sys.stderr)
    if hint:
        print(f"  -> {hint}  (see .claude/skills/3d-short/TROUBLESHOOTING.md)", file=sys.stderr)
    sys.exit(1)


def newer(out, *ins):
    return os.path.exists(out) and all(os.path.getmtime(out) >= os.path.getmtime(i) for i in ins if os.path.exists(i))


# ------------------------------------------------------------------ stages
def validate(project):
    cfg_path = os.path.join(project, "shots.json")
    script = os.path.join(project, "script.txt")
    if not os.path.exists(cfg_path):
        die(f"{cfg_path} not found")
    if not os.path.exists(script):
        die(f"{script} not found")
    try:
        cfg = json.load(open(cfg_path))
    except json.JSONDecodeError as e:
        die(f"shots.json is not valid JSON: {e}")
    err = []
    if not cfg.get("title"):
        err.append('"title" is missing')
    h = cfg.get("hero", {})
    if not any(k in h for k in ("module", "script", "glb")):
        err.append('"hero" needs one of "module" (props/<name>.py), "script" (a hero.py in the project) or "glb"')
    shots = cfg.get("shots", [])
    if not shots:
        err.append('"shots" is empty')
    nlines = len([l for l in open(script, encoding="utf-8").read().splitlines() if l.strip() and not l.strip().startswith("#")])
    ids, expect = set(), 0
    for s in shots:
        sid = s.get("id", "?")
        if sid in ids:
            err.append(f"duplicate shot id {sid}")
        ids.add(sid)
        if s.get("reveal", "none") not in REVEALS:
            err.append(f"{sid}: reveal must be one of {REVEALS}")
        ls = s.get("lines")
        if not ls or ls != list(range(ls[0], ls[0] + len(ls))) or ls[0] != expect:
            err.append(f"{sid}: lines must be consecutive and continue from line {expect} (got {ls})")
        else:
            expect = ls[-1] + 1
        for fl in s.get("flows", []):
            if "path" not in fl:
                err.append(f"{sid}: a flow needs a path")
            c = fl.get("color", "air")
            if c not in FLOW_COLORS and not str(c).startswith("#"):
                err.append(f"{sid}: flow colour {c!r} must be one of {FLOW_COLORS} or #rrggbb")
        for lb in s.get("labels", []):
            if not lb.get("text") or not any(k in lb for k in ("part", "anchor", "at")):
                err.append(f'{sid}: every label needs "text" and one of "part" / "anchor" / "at"')
    if expect != nlines:
        err.append(f"shots cover {expect} script lines but script.txt has {nlines}")
    if err:
        die("shots.json problems:\n  - " + "\n  - ".join(err))
    print(f"validate: ok ({len(shots)} shots, {nlines} lines)")
    return cfg


def do_voice(project, out, a):
    vdir = os.path.join(out, "voice")
    script = os.path.join(project, "script.txt")
    marker = os.path.join(vdir, "engine.txt")
    sig = f"{a.voice}|{a.speaker}"
    same = os.path.exists(marker) and open(marker).read() == sig
    if same and newer(os.path.join(vdir, "lines.json"), script):
        print("voice: up to date")
        return
    cmd = [venv_python(), os.path.join(HERE, "voice", "tts.py"), script, vdir, "--engine", a.voice, "--speaker", str(a.speaker)]
    if subprocess.run(cmd).returncode != 0:
        die("voice synthesis failed", "voice / Piper section")
    open(marker, "w").write(sig)


def do_timing(cfg, out):
    lj = json.load(open(os.path.join(out, "voice", "lines.json")))
    lines, total = lj["lines"], lj["duration"]
    timing, t = [], 0.0
    for i, s in enumerate(cfg["shots"]):
        last = i == len(cfg["shots"]) - 1
        end = total if last else round((lines[s["lines"][-1]]["end"] + lines[s["lines"][-1] + 1]["start"]) / 2, 3)
        timing.append({"id": s["id"], "start": round(t, 3), "end": end, "seconds": round(end - t, 3)})
        t = end
    json.dump({"total": total, "shots": timing, "lines": lines}, open(os.path.join(out, "timing.json"), "w"), indent=1)
    short = [s["id"] for s in timing if s["seconds"] < 2.2]
    print(f"timing: {total:.1f}s total, shots {min(s['seconds'] for s in timing):.1f}-{max(s['seconds'] for s in timing):.1f}s")
    if short:
        print(f"  warning: shots under 2.2 s ({short}) - merge them with a neighbour (WORKFLOW.md, Shot length)")
    if not (28 <= total <= 62):
        print(f"  warning: total length {total:.0f}s - a Short should be 30-60 s")
    return timing


def do_render(project, cfg, timing, out, a):
    blender = find_blender()
    if not blender:
        die("Blender not found", "run python engine/setup/doctor.py")
    v = blender_version(blender)
    if v and v < MIN_BLENDER:
        die(f"Blender {v[0]}.{v[1]} is too old (need {MIN_BLENDER[0]}.{MIN_BLENDER[1]}+)", "Blender section")
    mode = "draft" if a.draft else "final"
    froot = os.path.join(out, mode, "frames")
    hero_sig = json.dumps(cfg["hero"], sort_keys=True)
    hero_files = []
    if "module" in cfg["hero"]:
        hero_files.append(os.path.join(HERE, "blender", "props", cfg["hero"]["module"] + ".py"))
    if "script" in cfg["hero"]:
        hero_files.append(os.path.join(project, cfg["hero"]["script"]))
    code_sig = "".join(hashlib.sha1(open(p, "rb").read()).hexdigest() for p in sorted(
        [os.path.join(HERE, "blender", n) for n in ("studio.py", "shots.py", "hero_import.py")] + [os.path.join(HERE, "blender", "props", "kit.py")] + hero_files) if os.path.exists(p))
    shots = {s["id"]: s for s in cfg["shots"]}
    for tm in timing:
        if a.only_shot and tm["id"] != a.only_shot:
            continue
        sid = tm["id"]
        d = os.path.join(froot, sid)
        sig = hashlib.sha1((json.dumps(shots[sid], sort_keys=True) + hero_sig + f"{tm['seconds']:.2f}|{mode}|{code_sig}").encode()).hexdigest()
        sp = os.path.join(d, "spec.sig")
        if os.path.exists(os.path.join(d, "meta.json")) and os.path.exists(sp) and open(sp).read() == sig:
            print(f"render {sid}: up to date")
            continue
        if os.path.isdir(d):
            shutil.rmtree(d)                                           # spec changed -> stale frames
        os.makedirs(d, exist_ok=True)
        cmd = [blender, "-b", "--factory-startup", "-P", os.path.join(HERE, "blender", "shots.py"), "--",
               "--project", project, "--shot", sid, "--outdir", d, "--seconds", f"{tm['seconds']:.3f}", "--t0", f"{tm['start']:.3f}"]
        if a.draft:
            cmd.append("--draft")
        os.makedirs(os.path.join(out, mode, "logs"), exist_ok=True)
        log = os.path.join(out, mode, "logs", f"{sid}.log")
        t0 = time.time()
        with open(log, "w") as lf:
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for ln in p.stdout:
                lf.write(ln)
                if ln.startswith(f"[{sid}]") and "frame" in ln and "done" not in ln and int(ln.split("frame ")[1].split("/")[0]) % 60 == 0:
                    print("  " + ln.strip(), flush=True)
            rc = p.wait()
        tail = open(log).read().splitlines()[-18:]
        if rc != 0 or not os.path.exists(os.path.join(d, "meta.json")):
            print("\n".join(tail))
            die(f"Blender failed on shot {sid} (full log: {log})", "Blender render errors")
        open(sp, "w").write(sig)
        print(f"render {sid}: {tm['seconds']:.1f}s of video in {time.time() - t0:.0f}s")


def build_events(cfg, timing):
    ev = []
    for i, (s, tm) in enumerate(zip(cfg["shots"], timing)):
        t0 = tm["start"]
        if i > 0:
            ev.append([max(0.0, t0 - 0.12), "whoosh", -3])
        if s.get("reveal", "none") != "none":
            ev += [[t0 + 0.15, "rise", -6], [t0 + 1.0, "hit", -1]]
        for k, lb in enumerate(s.get("labels", [])):
            ev.append([t0 + float(lb.get("t", 0.7 + 0.45 * k)), "tick", -8])
    return ev


def do_audio(cfg, timing, out):
    import audio.mix as MIX
    voice = os.path.join(out, "voice", "voice.wav")
    mixp = os.path.join(out, "mix.wav")
    ev = build_events(cfg, timing)
    sig = hashlib.sha1((json.dumps(ev) + str(os.path.getmtime(voice))).encode()).hexdigest()
    sp = mixp + ".sig"
    if os.path.exists(mixp) and os.path.exists(sp) and open(sp).read() == sig:
        print("audio: up to date")
        return mixp
    res = MIX.build(voice, [tuple(e) for e in ev], mixp)
    open(sp, "w").write(sig)
    json.dump(res, open(os.path.join(out, "audio_report.json"), "w"))
    return mixp


def do_assemble(project, cfg, timing, out, a):
    import assemble as AS
    from overlay.draw import Overlay
    mode = "draft" if a.draft else "final"
    tj = json.load(open(os.path.join(out, "timing.json")))
    tl = AS.Timeline(cfg, timing, os.path.join(out, mode, "frames"))
    ov = Overlay(cfg, tj["lines"], tl.W, tl.H)
    contact = os.path.join(out, mode, "contact.jpg")
    AS.contact_sheet(tl, ov, contact)
    print("contact sheet:", contact)
    mp4 = os.path.join(out, "draft.mp4" if a.draft else "short.mp4")
    AS.encode(tl, ov, tj["total"], os.path.join(out, "mix.wav"), mp4, draft=a.draft)
    AS.frame_at(tl, ov, 1.0).save(os.path.join(out, "cover.jpg" if not a.draft else "cover_draft.jpg"), quality=92)
    return mp4


def do_verify(mp4, a):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration",
                        "-of", "json", mp4], capture_output=True, text=True)
    j = json.loads(r.stdout)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    au = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    dur = float(j["format"]["duration"])
    exp = (540, 960) if a.draft else (1080, 1920)
    ok = [(v["width"], v["height"]) == exp, v["r_frame_rate"] == "30/1", au is not None, 28 <= dur <= 62]
    print(f"verify: {v['width']}x{v['height']} {v['r_frame_rate']} fps, {dur:.1f}s, audio={au['codec_name'] if au else 'MISSING'}  ->  "
          + ("OK" if all(ok) else "CHECK (length outside 28-62 s or format mismatch)"))
    rep = os.path.join(os.path.dirname(mp4), "audio_report.json")
    if os.path.exists(rep):
        print("audio:", open(rep).read())
    return all(ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("project")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--from", dest="from_stage", choices=STAGES)
    ap.add_argument("--voice", default=os.environ.get("SHORTS_VOICE", "piper"))
    ap.add_argument("--speaker", type=int, default=int(os.environ.get("SHORTS_SPEAKER", 0)))
    ap.add_argument("--only-shot")
    a = ap.parse_args()
    project = os.path.abspath(a.project)
    slug = os.path.basename(project.rstrip("/\\"))
    out = os.path.join(ROOT, "out", slug)
    os.makedirs(out, exist_ok=True)
    cfg = validate(project)
    if a.from_stage in ("voice",):
        shutil.rmtree(os.path.join(out, "voice"), ignore_errors=True)
    do_voice(project, out, a)
    timing = do_timing(cfg, out)
    do_render(project, cfg, timing, out, a)
    if a.only_shot:
        return
    do_audio(cfg, timing, out)
    mp4 = do_assemble(project, cfg, timing, out, a)
    ok = do_verify(mp4, a)
    print(f"\nDONE: {mp4}" + ("" if ok else "   (format check flagged - see above)"))


if __name__ == "__main__":
    main()
