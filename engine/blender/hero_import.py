"""Import a GLB / glTF model (e.g. a CC0 download) as a hero: orient, scale, centre, restyle, group.

hero spec in shots.json:
  {"glb": "projects/<slug>/model.glb",      path relative to the repo root (or absolute)
   "length": 5.0,                           world length of the long axis (default 5.0)
   "shell": ["Mesh_3"],                     object names that are outer casings (cutaway / x-ray / hidden when exploded)
   "groups": {"wheel": ["Mesh_1","Mesh_2"]} optional: name parts yourself (otherwise one part per object, named after it)
   "modules": 5}                            optional: auto-split into N axial modules by x position for the exploded view

shots.py prints every part name and its size to the log, so a first --draft render of a "glb" hero tells you what to put
in shell / groups.
"""
import bpy, os, math
import numpy as np
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))


def _points(objs):
    pts = []
    for o in objs:
        n = len(o.data.vertices)
        if n == 0:
            continue
        a = np.empty(n * 3, dtype=np.float32)
        o.data.vertices.foreach_get("co", a)
        pts.append(a.reshape(-1, 3))
    return np.concatenate(pts)


def _restyle(objs):
    """Lift near-black base colours and tame extreme metal/roughness so the model reads on the dark studio."""
    seen = set()
    for o in objs:
        for m in o.data.materials:
            if not m or m.name in seen or not m.use_nodes:
                continue
            seen.add(m.name)
            for n in m.node_tree.nodes:
                if n.type != "BSDF_PRINCIPLED":
                    continue
                bc = n.inputs["Base Color"]
                if not bc.is_linked:
                    r, g, b, a = bc.default_value
                    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                    if lum < 0.04:
                        k = 0.04 / max(lum, 1e-4)
                        bc.default_value = (min(r * k, 1), min(g * k, 1), min(b * k, 1), a)
                n.inputs["Metallic"].default_value = min(n.inputs["Metallic"].default_value, 0.9)
                n.inputs["Roughness"].default_value = max(n.inputs["Roughness"].default_value, 0.25)
            try:
                m.surface_render_method = "DITHERED"
            except Exception:
                pass


def from_glb(spec, project_dir=None):
    path = spec["glb"]
    if not os.path.isabs(path):
        cands = [os.path.join(ROOT, path)] + ([os.path.join(project_dir, path)] if project_dir else [])
        path = next((c for c in cands if os.path.exists(c)), cands[0])
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=path)
    new = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in new if o.type == "MESH"]
    for o in meshes:                                   # bake parent transforms, detach
        mw = o.matrix_world.copy()
        o.parent = None
        o.data.transform(mw)
        o.matrix_world = Matrix.Identity(4)
    for o in new:
        if o.type != "MESH":
            bpy.data.objects.remove(o)
    P = _points(meshes)
    ext = P.max(0) - P.min(0)
    axis = int(np.argmax(ext))                         # long axis -> world X
    if axis == 1:
        R = Matrix.Rotation(-math.pi / 2, 4, "Z")
    elif axis == 2:
        R = Matrix.Rotation(math.pi / 2, 4, "Y")
    else:
        R = Matrix.Identity(4)
    for o in meshes:
        o.data.transform(R)
    P = _points(meshes)
    lo, hi = P.min(0), P.max(0)
    scale = float(spec.get("length", 5.0)) / float(hi[0] - lo[0])
    c = (lo + hi) / 2
    T = Matrix.Scale(scale, 4) @ Matrix.Translation(-Vector(c))
    for o in meshes:
        o.data.transform(T)
    _restyle(meshes)
    by_name = {o.name: o for o in meshes}
    if spec.get("groups"):
        parts = {k: [by_name[n] for n in v] for k, v in spec["groups"].items()}
        used = {n for v in spec["groups"].values() for n in v}
        for n, o in by_name.items():
            if n not in used:
                parts[n] = [o]
    else:
        parts = {n: [o] for n, o in by_name.items()}
    shell = [n for n in spec.get("shell", []) if n in parts]
    modules = []
    nmod = spec.get("modules")
    if nmod:
        body = [n for n in parts if n not in shell]
        cx = {n: float(np.mean([(o.bound_box[0][0] + o.bound_box[6][0]) / 2 for o in parts[n]])) for n in body}
        order = sorted(body, key=lambda n: -cx[n])            # +X first
        k = max(1, math.ceil(len(order) / nmod))
        modules = [order[i:i + k] for i in range(0, len(order), k)]
    print("GLB parts:", flush=True)
    for n, objs in parts.items():
        e = _points(objs)
        print(f"  {n:30s} size {np.round(e.max(0) - e.min(0), 2)}", flush=True)
    return {"parts": parts, "shell": shell, "modules": modules, "spin": {}, "anchors": {}, "flows": {}, "notes": ""}
