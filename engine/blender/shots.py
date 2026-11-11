"""Render one shot of a project to PNG frames + meta.json (runs INSIDE Blender; make_short.py calls it).

  blender -b --factory-startup -P shots.py -- --project projects/<slug> --shot s01 --outdir out/<slug>/frames/s01 \
          --seconds 4.2 [--t0 0.0] [--draft] [--samples N] [--step N]

Reads <project>/shots.json (see WORKFLOW.md for the schema).  Per frame it writes f_<k>.png (k = frame index inside the
shot at 30 fps) and finally meta.json with the projected pixel position of every label anchor for the overlay stage.
Frames that already exist are not re-rendered (resumable).
"""
import bpy, os, sys, json, math, importlib.util, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "props"))
import numpy as np
import studio as S


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"project": None, "shot": None, "outdir": None, "seconds": 4.0, "t0": 0.0, "draft": False, "samples": None, "step": None}
    i = 0
    while i < len(argv):
        k = argv[i].lstrip("-")
        if k == "draft":
            a["draft"] = True
            i += 1
            continue
        v = argv[i + 1]
        a[k] = type(a[k])(v) if a.get(k) is not None else v
        i += 2
    return a


def load_hero(spec, project_dir):
    if "glb" in spec:
        import hero_import
        return hero_import.from_glb(spec, project_dir)
    if "script" in spec:
        path = spec["script"] if os.path.isabs(spec["script"]) else os.path.join(project_dir, spec["script"])
    else:
        path = os.path.join(HERE, "props", spec["module"] + ".py")
    sp = importlib.util.spec_from_file_location("hero_mod", path)
    mod = importlib.util.module_from_spec(sp)
    sp.loader.exec_module(mod)
    return mod.build(**spec.get("args", {}))


def objs_of(hero, names):
    out = []
    for n in names:
        out += hero["parts"].get(n, [])
    return out


def main():
    a = parse_args()
    for o in list(bpy.data.objects):          # factory startup ships a default cube / camera / light
        bpy.data.objects.remove(o)
    project = os.path.abspath(a["project"])
    cfg = json.load(open(os.path.join(project, "shots.json")))
    shot = next(s for s in cfg["shots"] if s["id"] == a["shot"])
    os.makedirs(a["outdir"], exist_ok=True)
    fps = S.SHOT_FPS
    n = max(2, int(round(float(a["seconds"]) * fps)))
    step = int(a["step"] or (3 if a["draft"] else 1))
    samples = int(a["samples"] or (8 if a["draft"] else 32))
    res = (540, 960) if a["draft"] else (1080, 1920)

    hero = load_hero(cfg["hero"], project)
    all_objs = [o for v in hero["parts"].values() for o in v]
    P = S.hero_points(all_objs)
    floor_z = float(P[:, 2].min()) - 0.08
    cam = shot.get("camera", {})
    az0, el0 = float(cam.get("az", 35)), float(cam.get("el", 9))
    S.build_studio("9:16", res=res, samples=samples, floor_z=floor_z, az_deg=az0, el_deg=el0)

    shell = objs_of(hero, hero["shell"])
    body = [o for nme, v in hero["parts"].items() if nme not in hero["shell"] for o in v]
    reveal = shot.get("reveal", "none")
    explode = None
    if reveal == "cutaway" and shell:
        rep = S.cutaway(shell, open_side=cam.get("open_side", "+Y"))
        print("cutaway:", rep, flush=True)
    elif reveal == "xray" and shell:
        S.xray(shell)
    elif reveal == "explode":
        for o in shell:
            o.hide_render = True
        mods = hero["modules"] or [[n_] for n_ in hero["parts"] if n_ not in hero["shell"]]
        gap = float(shot.get("explode_gap", 0.7))
        ext = []
        for m in mods:
            Pm = S.hero_points(objs_of(hero, m))
            ext.append((float(Pm[:, 0].min()), float(Pm[:, 0].max())))
        total = sum(hi - lo for lo, hi in ext) + gap * (len(mods) - 1)
        cursor, offs = total / 2, []
        for (lo, hi) in ext:                      # modules are listed +X first -> place left to right from +X
            offs.append(cursor - hi)
            cursor -= (hi - lo) + gap
        explode = list(zip(mods, offs))
        shell = []

    # ---- flows
    flow_objs = []
    for fi, fl in enumerate(shot.get("flows", [])):
        path = fl["path"]
        pts = hero["flows"][path] if isinstance(path, str) else path
        angles = fl.get("copies", [0])
        for ci, ang in enumerate(angles):
            p = S.rotate_path_about_x(pts, ang, fl.get("swirl", 0.0)) if (ang or fl.get("swirl")) else pts
            ob = S.flow_lines(p, fl.get("color", "air"), radius=float(fl.get("radius", 0.02)), name=f"flow{fi}_{ci}",
                              strength=float(fl.get("strength", 2.2)))
            ob["delay"] = float(fl.get("delay", 0.0))
            flow_objs.append(ob)

    S.add_glow()
    S.add_contact_shadow(all_objs)

    def set_explode(e):
        if not explode:
            return
        for mods, off in explode:
            for o in objs_of(hero, mods):
                o.location.x = off * e

    # ---- camera fit (explode evaluated fully open; flows fully grown)
    set_explode(1.0)
    extra = flow_objs or None
    orbit = float(cam.get("orbit", 18))
    fits = [S.frame_hero(all_objs if reveal != "explode" else body, az0 + orbit * d, el0, extra=extra,
                         target_w=float(cam.get("width", 0.86))) for d in (-0.5, 0.5)]
    fit = max(fits, key=lambda f: f["distance"])
    set_explode(0.0)

    # ---- label anchors
    labels = shot.get("labels", [])

    def anchor_points():
        pts = {}
        for i, lb in enumerate(labels):
            if "at" in lb:
                pts[str(i)] = tuple(lb["at"])
            elif lb.get("anchor") in hero["anchors"] and "part" not in lb:
                pts[str(i)] = tuple(hero["anchors"][lb["anchor"]])
            else:
                nm = lb.get("part") or lb.get("anchor")
                objs = hero["parts"].get(nm)
                if not objs:
                    raise SystemExit(f"label {lb.get('text')!r}: unknown part/anchor {nm!r}. Parts: {list(hero['parts'])}  Anchors: {list(hero['anchors'])}")
                Pp = S.hero_points(objs, 800)
                c = (Pp.min(0) + Pp.max(0)) / 2
                pts[str(i)] = tuple(c + np.array(lb.get("offset", (0, 0, 0))))
        return pts

    focus = None
    if cam.get("focus"):
        f = cam["focus"]
        if isinstance(f, str):
            focus = hero["anchors"].get(f) or tuple((lambda Pp: (Pp.min(0) + Pp.max(0)) / 2)(S.hero_points(objs_of(hero, [f]), 800)))
        else:
            focus = tuple(f)

    sc = bpy.context.scene
    frames_meta = []
    t_start = time.time()
    spin_items = [(objs_of(hero, [nm]), rps) for nm, rps in hero["spin"].items() if nm not in hero["shell"] or reveal not in ("cutaway",)]
    for k in range(0, n, step):
        s = k / (n - 1)
        t = float(a["t0"]) + k / fps
        for objs, rps in spin_items:
            for o in objs:
                o.rotation_euler.x = math.radians(rps * 360.0 * t)
        set_explode(S.smooth01(min(1.0, s / 0.55)))
        for fo in flow_objs:
            g = S.smooth01(max(0.0, (s - fo["delay"]) / 0.55))
            fo.data.bevel_factor_end = max(0.001, g)
            fo.hide_render = g <= 0.002
        S.place_camera(fit, az0, el0, orbit_deg=orbit, push=float(cam.get("push", 0.08)), focus=focus,
                       focus_amount=float(cam.get("focus_amount", 0.55)), s=s)
        frames_meta.append({"k": k, "anchors": S.project_points(anchor_points())})
        out = os.path.join(a["outdir"], f"f_{k:05d}.png")
        if not os.path.exists(out):
            sc.render.filepath = out
            bpy.ops.render.render(write_still=True)
        if (k // step) % 10 == 0:
            print(f"[{a['shot']}] frame {k}/{n}  {time.time() - t_start:.0f}s", flush=True)
    json.dump({"width": res[0], "height": res[1], "fps": fps, "step": step, "n": n, "frames": frames_meta},
              open(os.path.join(a["outdir"], "meta.json"), "w"))
    print(f"[{a['shot']}] done {n} frames (step {step}) in {time.time() - t_start:.0f}s", flush=True)


main()
