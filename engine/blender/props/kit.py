"""Procedural prop kit - small helpers for building a hero in bpy (no external assets).

Convention: long axis = world X, centred on the origin, all geometry baked in world space (identity object transforms).
Every helper returns a mesh OBJECT already linked to the scene collection.

    mat(name, hex, metal, rough)                     Principled material
    lathe(profile, name, ...)                        revolve an (x, r) profile around the X axis (closed profile = solid wall)
    tube(x0, x1, r_out, r_in, name, ...)             hollow cylinder along X (solid wall, so cutaways get coral section faces)
    disc(x, r, thick, name, ...)                     flat disc
    blade_ring(n, x, r_hub, r_tip, chord, thick, twist_deg, name, ...)   ring of twisted blades
    box(center, size, name, ...)                     axis-aligned box
    cylinder(p0, p1, r, name, ...)                   cylinder between two points
    sphere(center, r, name, ...)
    spiral_layers(x0, x1, r_in, r_out, turns, n_layers, name, ...)   rolled sheets (battery jelly roll, rolled paper, coil)
    join(objs, name)                                 merge objects into one (keeps materials)
    rotate_about_x(obj, deg)                         bake a rotation about X into the mesh
    hero_dict(parts, shell=[], modules=[], spin={}, anchors={}, flows={})   the structure shots.py expects
"""
import bpy, bmesh, math
from mathutils import Vector, Matrix

PALETTE = {
    "steel": ("#9aa8ae", 0.55, 0.38),
    "steel_mid": ("#7a8b92", 0.55, 0.42),
    "steel_dark": ("#3a484e", 0.5, 0.5),
    "graphite": ("#2a3236", 0.0, 0.35),
    "white": ("#dfe8e8", 0.0, 0.45),
    "copper": ("#c97b4a", 1.0, 0.32),
    "gold": ("#d9b45a", 1.0, 0.3),
    "teal": ("#2fb5a8", 0.0, 0.35),
    "rubber": ("#1b2124", 0.0, 0.7),
}
_mats = {}


def hexlin(h):
    h = h.lstrip("#")
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(f(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4)) + (1.0,)


def mat(name, hexcol=None, metal=None, rough=None):
    """Material by palette name (`mat("steel")`) or custom (`mat("my_red", "#c0392b", 0.0, 0.4)`).
    Helpers such as lathe / tube / spiral_layers take either a PALETTE key (string) or the object returned here -
    for a custom colour create it first (`red = mat("my_red", "#c0392b", 0.0, 0.4)`) and pass `red`, not "my_red"."""
    if hexcol is None:
        if name not in PALETTE:
            raise KeyError(f"material {name!r} is not a palette key {sorted(PALETTE)}; for a custom colour call "
                           f'mat("{name}", "#rrggbb", metallic, roughness) once and pass the returned object')
        hexcol, metal, rough = PALETTE[name]
    if name in _mats and _mats[name].name in bpy.data.materials:
        return _mats[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    p.inputs["Base Color"].default_value = hexlin(hexcol)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    try:
        m.surface_render_method = "DITHERED"
    except Exception:
        pass
    _mats[name] = m
    return m


def _finish(bm, name, material, smooth=True):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if material is not None:
        me.materials.append(mat(material) if isinstance(material, str) else material)
    return ob


def lathe(profile, name, material="steel", steps=64, closed=True, smooth=True):
    """Revolve [(x, r), ...] around the X axis.  closed=True joins the last point to the first (a solid wall section)."""
    bm = bmesh.new()
    verts = [bm.verts.new((x, r, 0)) for x, r in profile]
    edges = [bm.edges.new((verts[i], verts[i + 1])) for i in range(len(verts) - 1)]
    if closed:
        edges.append(bm.edges.new((verts[-1], verts[0])))
    bmesh.ops.spin(bm, geom=verts + edges, cent=(0, 0, 0), axis=(1, 0, 0), angle=2 * math.pi, steps=steps, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    return _finish(bm, name, material, smooth)


def tube(x0, x1, r_out, r_in, name, material="steel", steps=64):
    """Hollow cylinder with a real wall thickness (closed solid)."""
    return lathe([(x0, r_in), (x0, r_out), (x1, r_out), (x1, r_in)], name, material, steps)


def disc(x, r, thick, name, material="steel_mid", r_in=0.0, steps=48):
    if r_in > 0:
        return lathe([(x - thick / 2, r_in), (x - thick / 2, r), (x + thick / 2, r), (x + thick / 2, r_in)], name, material, steps)
    return lathe([(x - thick / 2, 0.0), (x - thick / 2, r), (x + thick / 2, r), (x + thick / 2, 0.0)], name, material, steps, smooth=True)


def box(center, size, name, material="steel_mid"):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=center, verts=bm.verts)
    return _finish(bm, name, material, smooth=False)


def cylinder(p0, p1, r, name, material="steel_mid", steps=32):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=steps, radius1=r, radius2=r, depth=d.length)
    rot = d.to_track_quat("Z", "Y").to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((p0 + p1) / 2) @ rot, verts=bm.verts)
    return _finish(bm, name, material)


def sphere(center, r, name, material="steel_mid", seg=32):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    bmesh.ops.translate(bm, vec=center, verts=bm.verts)
    return _finish(bm, name, material)


def blade_ring(n, x, r_hub, r_tip, chord, thick, twist_deg, name, material="steel", sweep=0.0, taper=0.7):
    """n blades around the X axis between r_hub and r_tip.  chord = width along X at the root, thick = max thickness,
    twist_deg = pitch change root -> tip, sweep = tip offset along X (negative trails downstream), taper = tip chord ratio."""
    bm = bmesh.new()
    sec = [(-0.5, 0.0), (-0.25, 0.5), (0.0, 0.5), (0.25, 0.5), (0.5, 0.0), (0.0, -0.5)]      # lens-shaped section (chord, thickness)
    rings = 4
    for b in range(n):
        ang = 2 * math.pi * b / n
        rows = []
        for k in range(rings):
            t = k / (rings - 1)
            r = r_hub + (r_tip - r_hub) * t
            ch = chord * (1 - (1 - taper) * t)
            tw = math.radians(twist_deg * t)
            row = []
            for cx, cth in sec:
                cx_, cy_ = cx * ch, cth * thick
                # twist the section about the radial axis
                px = cx_ * math.cos(tw) - cy_ * math.sin(tw)
                py = cx_ * math.sin(tw) + cy_ * math.cos(tw)
                # tangential direction = py, axial = px (+ sweep)
                X = x + px + sweep * t
                Y0, Z0 = r, py
                row.append(bm.verts.new((X, Y0 * math.cos(ang) - Z0 * math.sin(ang), Y0 * math.sin(ang) + Z0 * math.cos(ang))))
            rows.append(row)
        ns = len(sec)
        for k in range(rings - 1):
            for i in range(ns):
                j = (i + 1) % ns
                bm.faces.new((rows[k][i], rows[k][j], rows[k + 1][j], rows[k + 1][i]))
        bm.faces.new(rows[0][::-1])
        bm.faces.new(rows[-1])
    return _finish(bm, name, material, smooth=False)


def spiral_layers(x0, x1, r_in, r_out, turns, n_layers, name, material="steel", thick=0.012, steps_per_turn=48):
    """A flat sheet rolled into a spiral (jelly roll, coil, scroll) about the X axis from r_in to r_out.  n_layers > 1
    interleaves several sheets (call once per material for coloured layers, with a small phase offset via r_in)."""
    bm = bmesh.new()
    total = int(turns * steps_per_turn)
    for L in range(n_layers):
        off = L * (r_out - r_in) / max(1, turns) / n_layers
        rows = []
        for i in range(total + 1):
            t = i / total
            ang = 2 * math.pi * turns * t
            r = r_in + off + (r_out - r_in - off) * t
            pair = []
            for dr in (0.0, thick):
                rr = r + dr
                pair.append((bm.verts.new((x0, rr * math.cos(ang), rr * math.sin(ang))), bm.verts.new((x1, rr * math.cos(ang), rr * math.sin(ang)))))
            rows.append(pair)
        for i in range(total):
            a, b = rows[i], rows[i + 1]
            bm.faces.new((a[0][0], b[0][0], b[0][1], a[0][1]))           # inner face
            bm.faces.new((a[1][0], a[1][1], b[1][1], b[1][0]))           # outer face
            bm.faces.new((a[0][0], a[1][0], b[1][0], b[0][0]))           # x0 edge strip
            bm.faces.new((a[0][1], b[0][1], b[1][1], a[1][1]))           # x1 edge strip
    return _finish(bm, name, material, smooth=False)


def join(objs, name):
    """Merge objects into one mesh object (materials kept)."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    ob.data.name = name
    return ob


def rotate_about_x(obj, deg):
    obj.data.transform(Matrix.Rotation(math.radians(deg), 4, "X"))


def hero_dict(parts, shell=(), modules=(), spin=None, anchors=None, flows=None, notes=""):
    """The structure shots.py expects from a hero builder.
    parts    {part_name: [objects]}                    every visible piece, grouped by name
    shell    [part_name]                               outer casings: cut by `cutaway`, made see-through by `xray`, hidden by `explode`
    modules  [[part_name, ...], ...]                   axial modules, +X end first; `explode` slides them apart
    spin     {part_name: revolutions_per_second}       parts that rotate about X (never put a cut shell here)
    anchors  {name: (x, y, z)}                         extra label anchor points (parts are anchored by their bounding-box centre)
    flows    {name: [(x, y, z), ...]}                  named flow paths shots.json can use ("path": "name")
    """
    return {"parts": {k: (list(v) if isinstance(v, (list, tuple)) else [v]) for k, v in parts.items()},
            "shell": list(shell), "modules": [list(m) for m in modules], "spin": dict(spin or {}),
            "anchors": dict(anchors or {}), "flows": dict(flows or {}), "notes": notes}
