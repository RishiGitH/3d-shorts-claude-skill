"""Studio Glow - reusable Blender studio library (EEVEE, tested on Blender 5.2).

Used by shots.py (inside Blender).  Import with:  sys.path.insert(0, <this dir>); import studio as S

Conventions
  * The hero's long axis is world X, centred on the origin, parts are baked in world space (identity transforms).
  * The floor sits at S.FLOOR_Z (set it with build_studio(floor_z=...)).
  * Flow runs +X -> -X by convention (not enforced).

Public API
  hexlin(hex)                          colour helper (sRGB hex -> linear rgba)
  build_studio(aspect, res, samples, floor_z, az, el)  void + floor + 4 lights + camera + render settings
  frame_hero(objs, az, el, ...)        camera distance / shift so the hero fills the vertical-video safe area
  place_camera(...)                    per-frame orbit / push / focus
  add_glow()                           bloom on emissive flow lines only
  add_contact_shadow(objs)             soft blob under the hero
  xray(shell_objs)                     see-through fresnel shell
  cutaway(objs)                        remove a wedge, cap the cut with the coral section colour
  flow_lines(points, color)            glowing tube (bevel_factor_end can be animated to grow it)
  anchors_for(...)                     project 3D points to pixel coordinates for the overlay stage
"""
import bpy, bmesh, math, os, json
import numpy as np
from mathutils import Vector, Matrix

# ------------------------------------------------------------------ palette ("Studio Glow")
BG_TOP = "#0e4a50"          # deep teal at the top of the frame ...
BG_BOT = "#030c0d"          # ... falling to near-black at the bottom
FLOOR_BASE = "#071a1c"
GRID_COL = "#7fe8dc"
GRID_STRENGTH = 0.05
ENV_LO, ENV_HI = "#050a0b", "#34464a"   # lighting environment (never seen by the camera)
COL_CUT = "#e8573f"         # warm coral section faces
CUT_SPEC = 0.15
FLOW_COLORS = {"air": "#5ff2c0", "heat": "#ff8a2a", "fuel": "#ffd23f", "electric": "#9a6bff"}
GLOW = (0.8, 1.0, 0.55)     # bloom threshold, strength, size
FLOOR_Z = -1.25
SHOT_FPS = 30


# ------------------------------------------------------------------ helpers
def srgb_to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hexlin(h, gain=(1, 1, 1)):
    h = h.lstrip("#")
    return tuple(srgb_to_lin(int(h[i:i + 2], 16) / 255) * g for i, g in zip((0, 2, 4), gain)) + (1.0,)


def _n(nt, typ, x=0, y=0, **kw):
    n = nt.nodes.new(typ)
    n.location = (x, y)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def _look_at(obj, target):
    d = Vector(target) - obj.location
    obj.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def _new_mat(name, blended=False):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    try:
        m.surface_render_method = "BLENDED" if blended else "DITHERED"
    except Exception:
        pass
    return m


def _principled(m):
    return next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


def hero_points(objs, stride_target=2500):
    """World-space sample points of meshes (vertex subsample) and curves (spline points) -> (N, 3) array."""
    pts = []
    for o in objs:
        if o.hide_render:
            continue
        M = np.array(o.matrix_world)
        if o.type == "MESH":
            n = len(o.data.vertices)
            if n == 0:
                continue
            a = np.empty(n * 3, dtype=np.float32)
            o.data.vertices.foreach_get("co", a)
            a = a.reshape(-1, 3)[:: max(1, n // stride_target)]
        elif o.type == "CURVE":
            a = np.array([p.co[:3] for sp in o.data.splines for p in sp.points], dtype=np.float32)
            if len(a) == 0:
                continue
        else:
            continue
        pts.append((M[:3, :3] @ a.T).T + M[:3, 3])
    return np.concatenate(pts)


# ------------------------------------------------------------------ studio
def _clear_studio():
    coll = bpy.data.collections.get("Studio")
    if coll:
        for o in list(coll.objects):
            d = o.data
            bpy.data.objects.remove(o)
            if d and d.users == 0:
                (bpy.data.lights if isinstance(d, bpy.types.Light) else bpy.data.meshes if isinstance(d, bpy.types.Mesh)
                 else bpy.data.cameras).remove(d)
        bpy.data.collections.remove(coll)


_CAM = {"az": math.radians(35), "el": math.radians(9)}


def _world():
    w = bpy.data.worlds.get("Studio_World") or bpy.data.worlds.new("Studio_World")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = _n(nt, "ShaderNodeOutputWorld", 1600, 0)
    # camera-visible background: vertical gradient in screen space
    tc = _n(nt, "ShaderNodeTexCoord", -900, 300)
    sep = _n(nt, "ShaderNodeSeparateXYZ", -700, 300)
    ramp = _n(nt, "ShaderNodeValToRGB", -480, 300)
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = hexlin(BG_BOT)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = hexlin(BG_TOP)
    ramp.color_ramp.interpolation = "EASE"
    nt.links.new(tc.outputs["Window"], sep.inputs[0])
    nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    bg_cam = _n(nt, "ShaderNodeBackground", -200, 300)
    nt.links.new(ramp.outputs["Color"], bg_cam.inputs["Color"])
    # lighting environment: dim gradient + soft boxes so metals have something to reflect
    d = _n(nt, "ShaderNodeTexCoord", -900, -200)
    vm = _n(nt, "ShaderNodeVectorMath", -700, -420, operation="SCALE")
    vm.inputs["Scale"].default_value = 2.0
    nt.links.new(d.outputs["Generated"], vm.inputs[0])
    vm2 = _n(nt, "ShaderNodeVectorMath", -520, -420, operation="SUBTRACT")
    vm2.inputs[1].default_value = (1, 1, 1)
    nt.links.new(vm.outputs[0], vm2.inputs[0])
    sepz = _n(nt, "ShaderNodeSeparateXYZ", -340, -420)
    nt.links.new(vm2.outputs[0], sepz.inputs[0])
    gr = _n(nt, "ShaderNodeValToRGB", -140, -200)
    gr.color_ramp.elements[0].position = 0.35
    gr.color_ramp.elements[0].color = hexlin(ENV_LO)
    gr.color_ramp.elements[1].position = 1.0
    gr.color_ramp.elements[1].color = hexlin(ENV_HI)
    nt.links.new(sepz.outputs["Z"], gr.inputs["Fac"])
    ca, ce = _CAM["az"], _CAM["el"]
    u = Vector((math.cos(ca) * math.cos(ce), math.sin(ca) * math.cos(ce), math.sin(ce)))
    r = Vector((-math.sin(ca), math.cos(ca), 0))
    z = Vector((0, 0, 1))
    boxes = [
        ((u * 0.75 - r * 0.55 + z * 0.55).normalized(), "#fff1de", 2.0, 0.80),   # key: warm, front-left, high
        ((-u * 0.7 + r * 0.7 + z * 0.35).normalized(), "#c4f3ec", 1.2, 0.88),    # rim: mint, back-right
        ((z * 0.95 + u * 0.1).normalized(), "#e3f1f0", 1.1, 0.90),               # top strip
        ((u * 0.9 + r * 0.55 + z * 0.1).normalized(), "#bcd3d4", 0.6, 0.82),     # low fill
    ]
    prev = gr.outputs["Color"]
    for i, (dv, col, strength, thr) in enumerate(boxes):
        dot = _n(nt, "ShaderNodeVectorMath", -140 + i * 240, -560, operation="DOT_PRODUCT")
        dot.inputs[1].default_value = tuple(dv)
        nt.links.new(vm2.outputs[0], dot.inputs[0])
        mr = _n(nt, "ShaderNodeMapRange", -140 + i * 240, -720)
        mr.inputs["From Min"].default_value = thr
        mr.inputs["From Max"].default_value = thr + 0.07
        nt.links.new(dot.outputs["Value"], mr.inputs["Value"])
        c = _n(nt, "ShaderNodeRGB", -140 + i * 240, -860)
        c.outputs[0].default_value = hexlin(col)
        sc = _n(nt, "ShaderNodeVectorMath", -140 + i * 240, -980, operation="SCALE")
        sc.inputs["Scale"].default_value = strength
        nt.links.new(c.outputs[0], sc.inputs[0])
        add = _n(nt, "ShaderNodeMixRGB", 300 + i * 200, -200, blend_type="ADD")
        nt.links.new(mr.outputs["Result"], add.inputs["Fac"])
        nt.links.new(prev, add.inputs["Color1"])
        nt.links.new(sc.outputs[0], add.inputs["Color2"])
        prev = add.outputs["Color"]
    bg_env = _n(nt, "ShaderNodeBackground", 1200, -200)
    nt.links.new(prev, bg_env.inputs["Color"])
    lp = _n(nt, "ShaderNodeLightPath", 1000, 400)
    mix = _n(nt, "ShaderNodeMixShader", 1400, 0)
    nt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    nt.links.new(bg_env.outputs["Background"], mix.inputs[1])
    nt.links.new(bg_cam.outputs["Background"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    return w


def _cyc_floor(coll, az, grid=True):
    """Curved cyclorama: flat floor sweeping up into a back wall, curve placed behind the view.  The far field is an
    emission of the same screen-space gradient as the world, so floor and background join seamlessly."""
    prof = [(-45.0, 0.0), (6.0, 0.0)]
    R = 9.0
    for k in range(1, 13):
        t = k / 12 * math.pi / 2
        prof.append((6.0 + R * math.sin(t), R * (1 - math.cos(t))))
    prof.append((6.0 + R, R + 25.0))
    xs = np.linspace(-60, 60, 25)
    verts, faces = [], []
    for py, pz in prof:
        for x in xs:
            verts.append((x, py, pz))
    nx = len(xs)
    for i in range(len(prof) - 1):
        for j in range(nx - 1):
            a = i * nx + j
            faces.append((a, a + 1, a + nx + 1, a + nx))
    me = bpy.data.meshes.new("Studio_cyc")
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new("Studio_cyc", me)
    coll.objects.link(ob)
    ob.rotation_euler = (0, 0, az - math.pi / 2 + math.pi)
    ob.location = (0, 0, FLOOR_Z)
    ob.visible_shadow = False
    me.shade_smooth()
    m = _new_mat("Studio_floor")
    nt = m.node_tree
    nt.nodes.clear()
    out = _n(nt, "ShaderNodeOutputMaterial", 1500, 0)
    geo = _n(nt, "ShaderNodeNewGeometry", -1200, 500)
    sepp = _n(nt, "ShaderNodeSeparateXYZ", -1000, 500)
    nt.links.new(geo.outputs["Position"], sepp.inputs[0])
    sx = _n(nt, "ShaderNodeMath", -800, 560, operation="MULTIPLY")
    sy = _n(nt, "ShaderNodeMath", -800, 420, operation="MULTIPLY")
    nt.links.new(sepp.outputs["X"], sx.inputs[0]); nt.links.new(sepp.outputs["X"], sx.inputs[1])
    nt.links.new(sepp.outputs["Y"], sy.inputs[0]); nt.links.new(sepp.outputs["Y"], sy.inputs[1])
    ad = _n(nt, "ShaderNodeMath", -620, 500, operation="ADD")
    nt.links.new(sx.outputs[0], ad.inputs[0]); nt.links.new(sy.outputs[0], ad.inputs[1])
    rr = _n(nt, "ShaderNodeMath", -460, 500, operation="SQRT")
    nt.links.new(ad.outputs[0], rr.inputs[0])
    fade = _n(nt, "ShaderNodeMapRange", -280, 500, interpolation_type="SMOOTHSTEP")
    fade.inputs["From Min"].default_value = 1.6
    fade.inputs["From Max"].default_value = 4.8
    nt.links.new(rr.outputs[0], fade.inputs["Value"])
    gfade = _n(nt, "ShaderNodeMapRange", -280, 300, interpolation_type="SMOOTHSTEP")
    gfade.inputs["From Min"].default_value = 2.0
    gfade.inputs["From Max"].default_value = 8.0
    gfade.inputs["To Min"].default_value = 1.0
    gfade.inputs["To Max"].default_value = 0.0
    nt.links.new(rr.outputs[0], gfade.inputs["Value"])
    # grid: brick texture as square cells -> lines = 1 - brick
    gt = _n(nt, "ShaderNodeTexBrick", -800, -100, offset=0.0, squash=1.0)
    gt.inputs["Scale"].default_value = 1.0
    gt.inputs["Mortar Size"].default_value = 0.014
    gt.inputs["Mortar Smooth"].default_value = 0.35
    gt.inputs["Brick Width"].default_value = 0.5
    gt.inputs["Row Height"].default_value = 0.5
    gt.inputs["Color1"].default_value = (1, 1, 1, 1)
    gt.inputs["Color2"].default_value = (1, 1, 1, 1)
    gt.inputs["Mortar"].default_value = (0, 0, 0, 1)
    nt.links.new(geo.outputs["Position"], gt.inputs["Vector"])
    inv = _n(nt, "ShaderNodeMath", -620, -100, operation="SUBTRACT")
    inv.inputs[0].default_value = 1.0
    nt.links.new(gt.outputs["Color"], inv.inputs[1])
    gm = _n(nt, "ShaderNodeMath", -500, -100, operation="MULTIPLY")
    nt.links.new(inv.outputs[0], gm.inputs[0])
    nt.links.new(gfade.outputs["Result"], gm.inputs[1])
    gmul = _n(nt, "ShaderNodeMath", -380, -100, operation="MULTIPLY")
    gmul.inputs[1].default_value = GRID_STRENGTH if grid else 0.0
    nt.links.new(gm.outputs[0], gmul.inputs[0])
    base = _n(nt, "ShaderNodeRGB", -560, 100)
    base.outputs[0].default_value = hexlin(FLOOR_BASE)
    pr = _n(nt, "ShaderNodeBsdfPrincipled", 100, 150)
    nt.links.new(base.outputs[0], pr.inputs["Base Color"])
    pr.inputs["Roughness"].default_value = 0.85
    pr.inputs["Metallic"].default_value = 0.0
    try:
        pr.inputs["Specular IOR Level"].default_value = 0.1
    except KeyError:
        pass
    win = _n(nt, "ShaderNodeTexCoord", -1200, -400)
    wsep = _n(nt, "ShaderNodeSeparateXYZ", -1000, -400)
    nt.links.new(win.outputs["Window"], wsep.inputs[0])
    wr = _n(nt, "ShaderNodeValToRGB", -800, -400)
    wr.color_ramp.elements[0].position = 0.0
    wr.color_ramp.elements[0].color = hexlin(BG_BOT)
    wr.color_ramp.elements[1].position = 1.0
    wr.color_ramp.elements[1].color = hexlin(BG_TOP)
    wr.color_ramp.interpolation = "EASE"
    nt.links.new(wsep.outputs["Y"], wr.inputs["Fac"])
    em = _n(nt, "ShaderNodeEmission", -500, -400)
    nt.links.new(wr.outputs["Color"], em.inputs["Color"])
    mx = _n(nt, "ShaderNodeMixShader", 1000, 0)
    nt.links.new(fade.outputs["Result"], mx.inputs["Fac"])
    nt.links.new(pr.outputs["BSDF"], mx.inputs[1])
    nt.links.new(em.outputs["Emission"], mx.inputs[2])
    ge = _n(nt, "ShaderNodeEmission", 700, -300)
    ge.inputs["Color"].default_value = hexlin(GRID_COL)
    nt.links.new(gmul.outputs[0], ge.inputs["Strength"])
    ad2 = _n(nt, "ShaderNodeAddShader", 1250, 0)
    nt.links.new(mx.outputs["Shader"], ad2.inputs[0])
    nt.links.new(ge.outputs["Emission"], ad2.inputs[1])
    nt.links.new(ad2.outputs["Shader"], out.inputs["Surface"])
    ob.data.materials.append(m)
    return ob


def build_studio(aspect="9:16", res=None, samples=32, floor_z=-1.25, az_deg=35, el_deg=9, grid=True):
    """Create (or rebuild) the studio: world, cyc floor, lights, camera, render + colour settings."""
    global FLOOR_Z
    FLOOR_Z = floor_z
    sc = bpy.context.scene
    _CAM["az"], _CAM["el"] = math.radians(az_deg), math.radians(el_deg)
    _clear_studio()
    coll = bpy.data.collections.new("Studio")
    sc.collection.children.link(coll)
    cd = bpy.data.cameras.new("Studio_Cam")
    cd.sensor_fit = "HORIZONTAL"
    cd.sensor_width = 36
    cd.lens = 60
    cd.clip_start, cd.clip_end = 0.5, 120
    cam = bpy.data.objects.new("Studio_Cam", cd)
    coll.objects.link(cam)
    sc.camera = cam
    if res is None:
        res = (1080, 1920) if aspect == "9:16" else (1920, 1080)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.fps = SHOT_FPS
    for eng in ("BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"):     # 5.x name first, 4.2 name second
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    ee = sc.eevee
    ee.taa_render_samples = samples
    for k, v in (("use_raytracing", True), ("use_shadows", True), ("shadow_ray_count", 2), ("shadow_step_count", 8)):
        if hasattr(ee, k):
            try:
                setattr(ee, k, v)
            except Exception:
                pass
    try:
        ee.fast_gi_method = "AMBIENT_OCCLUSION_ONLY"    # no screen-space GI bounce: emissive flow lines would flood the floor
    except Exception:
        pass
    vs = sc.view_settings
    for vt in ("Khronos PBR Neutral", "Standard"):
        try:
            vs.view_transform = vt
            break
        except TypeError:
            continue
    try:
        vs.look = "None"
    except TypeError:
        pass
    vs.exposure = 0.0
    sc.display_settings.display_device = "sRGB"
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.world = _world()
    _cyc_floor(coll, _CAM["az"], grid)
    ca, ce = _CAM["az"], _CAM["el"]
    u = Vector((math.cos(ca) * math.cos(ce), math.sin(ca) * math.cos(ce), math.sin(ce)))
    r = Vector((-math.sin(ca), math.cos(ca), 0))
    z = Vector((0, 0, 1))

    def light(name, dirv, dist, power, size, col, sizey=None):
        ld = bpy.data.lights.new(name, "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = size, sizey or size
        ld.energy = power
        ld.color = col[:3]
        ld.use_shadow = True
        lo = bpy.data.objects.new(name, ld)
        coll.objects.link(lo)
        lo.location = dirv.normalized() * dist
        _look_at(lo, (0, 0, 0))
        return lo

    light("Studio_key", u * 0.7 - r * 0.6 + z * 0.75, 7.5, 800, 6.0, hexlin("#fff1e2"), 4.5)
    light("Studio_rim", -u * 0.8 + r * 0.7 + z * 0.55, 7.0, 260, 2.2, hexlin("#8ff0dd"), 6.0)
    light("Studio_rim2", -u * 0.7 - r * 0.8 + z * 0.35, 7.0, 140, 2.0, hexlin("#7fd6e8"), 5.0)
    light("Studio_fill", u * 0.8 + r * 0.7 + z * 0.15, 8.0, 160, 7.0, hexlin("#cfe4e4"), 4.0)
    return {"camera": cam, "collection": coll}


# ------------------------------------------------------------------ camera
def _project_fit(cam, f, W, H, P, tgt, dirv, dist):
    cam.location = tgt + dirv * dist
    _look_at(cam, tgt)
    bpy.context.view_layer.update()
    Mi = np.array(cam.matrix_world.inverted())
    Pc = (Mi[:3, :3] @ P.T).T + Mi[:3, 3]
    return f * Pc[:, 0] / -Pc[:, 2] + 0.5, f * Pc[:, 1] / -Pc[:, 2] * (W / H) + 0.5


def frame_hero(objs, az_deg, el_deg, extra=None, target_w=0.86, cap_w=0.94, vcenter=0.54):
    """Compute camera distance + lens shift so the hero is `target_w` of the frame width (flow lines `extra` stay inside
    `cap_w`), centred at `vcenter` of the frame height from the bottom (keeps clear of caption / platform UI).
    Evaluates at the given azimuth only; place_camera() calls it at both ends of an orbit and takes the larger distance."""
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    cam = sc.camera
    cam.data.lens = 60
    cam.data.shift_x = cam.data.shift_y = 0
    P = hero_points(objs)
    Pe = P if not extra else np.concatenate([P, hero_points(extra)])
    tgt = Vector((P.min(0) + P.max(0)) / 2)
    az, el = math.radians(az_deg), math.radians(el_deg)
    dirv = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    W, H = sc.render.resolution_x, sc.render.resolution_y
    f = cam.data.lens / cam.data.sensor_width
    dist = 9.0
    for _ in range(8):
        u_, v_ = _project_fit(cam, f, W, H, P, tgt, dirv, dist)
        dist *= (u_.max() - u_.min()) / target_w
    for _ in range(6):
        ue, ve = _project_fit(cam, f, W, H, Pe, tgt, dirv, dist)
        wd = ue.max() - ue.min()
        if wd <= cap_w * 1.002:
            break
        dist *= wd / cap_w
    u_, v_ = _project_fit(cam, f, W, H, P, tgt, dirv, dist)
    return {"distance": dist, "target": tgt,
            "shift_x": float((u_.max() + u_.min()) / 2 - 0.5),
            "shift_y": float(((v_.max() + v_.min()) / 2 - vcenter) * (H / W))}


def smooth01(t):
    t = min(1.0, max(0.0, t))
    return t * t * (3 - 2 * t)


def place_camera(fit, az_deg, el_deg, orbit_deg=0.0, push=0.0, focus=None, focus_amount=0.55, s=0.0):
    """Position the camera for shot progress s in [0, 1].  Orbit swings the azimuth by orbit_deg over the shot, push
    shrinks the distance by that fraction by the end, focus (xyz) drifts the look-at point toward a part."""
    cam = bpy.context.scene.camera
    e = smooth01(s)
    az = math.radians(az_deg + orbit_deg * (e - 0.5))
    el = math.radians(el_deg)
    dirv = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
    tgt = Vector(fit["target"])
    if focus is not None:
        tgt = tgt.lerp(Vector(focus), focus_amount * e)
    cam.location = tgt + dirv * fit["distance"] * (1.0 - push * e)
    _look_at(cam, tgt)
    cam.data.shift_x, cam.data.shift_y = fit["shift_x"], fit["shift_y"]


# ------------------------------------------------------------------ glow + shadow
def add_glow(threshold=None, strength=None, size=None):
    """Bloom on the EMISSION pass only (flow lines glow, shell speculars never bloom). Returns False (no glow) if the
    compositor API differs from Blender 5.x - the Short still renders, just without bloom."""
    sc = bpy.context.scene
    threshold = GLOW[0] if threshold is None else threshold
    strength = GLOW[1] if strength is None else strength
    size = GLOW[2] if size is None else size
    try:
        sc.view_layers[0].use_pass_emit = True
        ng = bpy.data.node_groups.new("Studio_comp", "CompositorNodeTree")
        ng.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
        rl = ng.nodes.new("CompositorNodeRLayers")
        gl = ng.nodes.new("CompositorNodeGlare")
        go = ng.nodes.new("NodeGroupOutput")
        mx = ng.nodes.new("ShaderNodeMix")
        mx.data_type = "RGBA"
        mx.blend_type = "ADD"
        for k, v in (("Type", "Bloom"), ("Threshold", threshold), ("Strength", strength), ("Size", size), ("Quality", "Medium")):
            if k in gl.inputs:
                try:
                    gl.inputs[k].default_value = v
                except Exception:
                    pass
        ng.links.new(rl.outputs["Emission"], gl.inputs["Image"])
        ab = [i for i in mx.inputs if i.name in ("A", "B") and i.enabled]
        fac = [i for i in mx.inputs if i.name == "Factor" and i.enabled]
        fac[0].default_value = 1.0
        ng.links.new(rl.outputs["Image"], ab[0])
        ng.links.new(gl.outputs["Glare"], ab[1])
        res = [o for o in mx.outputs if o.name == "Result" and o.enabled][0]
        ng.links.new(res, go.inputs[0])
        sc.compositing_node_group = ng
        sc.render.use_compositing = True
        return True
    except Exception as e:
        print("GLOW unavailable:", e, flush=True)
        return False


def add_contact_shadow(objs, opacity=0.5):
    """Soft dark blob on the floor under the hero so it never floats."""
    P = hero_points(objs)
    lo, hi = P.min(0), P.max(0)
    ax = (hi[0] - lo[0]) / 2 * 1.15 + 0.4
    ay = max(abs(lo[1]), abs(hi[1])) * 1.35 + 0.35
    me = bpy.data.meshes.new("Studio_shadow")
    me.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("Studio_shadow", me)
    coll = bpy.data.collections.get("Studio") or bpy.context.scene.collection
    coll.objects.link(ob)
    ob.location = ((lo[0] + hi[0]) / 2, 0, FLOOR_Z + 0.004)
    ob.scale = (ax, ay, 1)
    ob.visible_shadow = False
    m = _new_mat("Studio_shadow", blended=True)
    nt = m.node_tree
    nt.nodes.clear()
    out = _n(nt, "ShaderNodeOutputMaterial", 900, 0)
    tc = _n(nt, "ShaderNodeTexCoord", -700, 0)
    sp = _n(nt, "ShaderNodeSeparateXYZ", -500, 0)
    nt.links.new(tc.outputs["Object"], sp.inputs[0])
    sx = _n(nt, "ShaderNodeMath", -300, 100, operation="MULTIPLY")
    sy = _n(nt, "ShaderNodeMath", -300, -100, operation="MULTIPLY")
    nt.links.new(sp.outputs["X"], sx.inputs[0]); nt.links.new(sp.outputs["X"], sx.inputs[1])
    nt.links.new(sp.outputs["Y"], sy.inputs[0]); nt.links.new(sp.outputs["Y"], sy.inputs[1])
    ad = _n(nt, "ShaderNodeMath", -120, 0, operation="ADD")
    nt.links.new(sx.outputs[0], ad.inputs[0]); nt.links.new(sy.outputs[0], ad.inputs[1])
    rr = _n(nt, "ShaderNodeMath", 50, 0, operation="SQRT")
    nt.links.new(ad.outputs[0], rr.inputs[0])
    mr = _n(nt, "ShaderNodeMapRange", 220, 0, interpolation_type="SMOOTHSTEP")
    mr.inputs["From Min"].default_value = 0.1
    mr.inputs["From Max"].default_value = 1.0
    mr.inputs["To Min"].default_value = opacity
    mr.inputs["To Max"].default_value = 0.0
    nt.links.new(rr.outputs[0], mr.inputs["Value"])
    tr = _n(nt, "ShaderNodeBsdfTransparent", 450, 150)
    bk = _n(nt, "ShaderNodeEmission", 450, -50)
    bk.inputs["Color"].default_value = (0, 0, 0, 1)
    mx = _n(nt, "ShaderNodeMixShader", 650, 0)
    nt.links.new(mr.outputs["Result"], mx.inputs["Fac"])
    nt.links.new(tr.outputs[0], mx.inputs[1])
    nt.links.new(bk.outputs[0], mx.inputs[2])
    nt.links.new(mx.outputs[0], out.inputs["Surface"])
    me.materials.append(m)
    return ob


# ------------------------------------------------------------------ overlay anchors
def project_points(points):
    """World points {name: (x, y, z)} -> {name: [x_px, y_px, visible]} for the current frame / camera (origin top-left)."""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    W, H = sc.render.resolution_x, sc.render.resolution_y
    bpy.context.view_layer.update()
    a = {}
    for k, p in points.items():
        c = world_to_camera_view(sc, sc.camera, Vector(p))
        vis = c.z > 0 and 0 <= c.x <= 1 and 0 <= c.y <= 1
        a[k] = [round(c.x * W, 2), round((1 - c.y) * H, 2), bool(vis)]
    return a


# ------------------------------------------------------------------ reveals
def xray(shell_objs, tint=(0.45, 0.95, 0.85)):
    """See-through shell: alpha 0.08 in the centre -> 0.65 at grazing edges, no refraction."""
    m = _new_mat("Studio_xray", blended=True)
    nt = m.node_tree
    p = _principled(m)
    p.inputs["Base Color"].default_value = (tint[0] * 0.25, tint[1] * 0.25, tint[2] * 0.25, 1.0)
    p.inputs["Metallic"].default_value = 0.0
    p.inputs["Roughness"].default_value = 0.16
    p.inputs["Emission Color"].default_value = (*tint, 1.0)
    p.inputs["Emission Strength"].default_value = 0.0
    try:
        p.inputs["Specular IOR Level"].default_value = 0.25
    except KeyError:
        pass
    lw = _n(nt, "ShaderNodeLayerWeight", -500, 0)
    lw.inputs["Blend"].default_value = 0.42
    mr = _n(nt, "ShaderNodeMapRange", -250, 0)
    mr.inputs["To Min"].default_value = 0.08
    mr.inputs["To Max"].default_value = 0.65
    nt.links.new(lw.outputs["Fresnel"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], p.inputs["Alpha"])
    em = _n(nt, "ShaderNodeMath", -250, -200, operation="MULTIPLY")
    em.inputs[1].default_value = 0.45
    nt.links.new(lw.outputs["Fresnel"], em.inputs[0])
    nt.links.new(em.outputs[0], p.inputs["Emission Strength"])
    try:
        m.use_backface_culling = True
    except Exception:
        pass
    for o in shell_objs:
        o.data.materials.clear()
        o.data.materials.append(m)
        o.visible_shadow = False
    return m


def _cap_material():
    m = _new_mat("Studio_cut")
    p = _principled(m)
    p.inputs["Base Color"].default_value = hexlin(COL_CUT)
    p.inputs["Metallic"].default_value = 0.0
    p.inputs["Roughness"].default_value = 0.6
    try:
        p.inputs["Specular IOR Level"].default_value = CUT_SPEC
    except KeyError:
        pass
    return m


def cutaway(objs, open_side="+Y", tilt_deg=25.0, span_deg=90.0, fill_caps=True):
    """Remove a quarter wedge (span_deg) of every mesh in objs around the X axis.  The wedge opens toward `open_side`
    (+Y or -Y), raised tilt_deg toward +Z so a slightly raised camera looks into it.  Meshes are bisected exactly on the
    two wedge planes, the wedge faces deleted, and the section holes capped with the flat coral cut material.
    Works best on closed (solid-wall) meshes.  Returns {obj name: (closed_before, cap_faces)}."""
    open_dir = {"+Y": 1, "-Y": -1}[open_side]
    th0 = math.radians(tilt_deg) - math.radians(span_deg) / 2 + (0 if open_dir > 0 else math.pi)
    th1 = th0 + math.radians(span_deg)
    n0 = Vector((0, -math.sin(th0), math.cos(th0)))
    n1 = Vector((0, -math.sin(th1), math.cos(th1)))
    capm = _cap_material()
    report = {}
    for o in objs:
        me = o.data
        bm = bmesh.new()
        bm.from_mesh(me)
        closed_before = all(len(e.link_faces) == 2 for e in bm.edges)
        for n in (n0, n1):
            geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
            bmesh.ops.bisect_plane(bm, geom=geom, dist=1e-6, plane_co=(0, 0, 0), plane_no=tuple(n))
        dele = [f for f in bm.faces if n0.dot(f.calc_center_median()) > 1e-5 and n1.dot(f.calc_center_median()) < -1e-5]
        bmesh.ops.delete(bm, geom=dele, context="FACES")
        bedges = [e for e in bm.edges if len(e.link_faces) == 1
                  and (all(abs(n0.dot(v.co)) < 1e-4 for v in e.verts) or all(abs(n1.dot(v.co)) < 1e-4 for v in e.verts))]
        ncap = 0
        if fill_caps and bedges:
            before = set(bm.faces)
            try:
                bmesh.ops.holes_fill(bm, edges=bedges, sides=0)
            except Exception:
                pass
            new = [f for f in bm.faces if f not in before]
            if not new:
                try:
                    bmesh.ops.triangle_fill(bm, use_beauty=True, use_dissolve=False, edges=bedges)
                    new = [f for f in bm.faces if f not in before]
                except Exception:
                    new = []
            if new:
                if capm.name not in [m.name for m in me.materials if m]:
                    me.materials.append(capm)
                idx = [m.name for m in me.materials if m].index(capm.name)
                for f in new:
                    f.material_index = idx
                    f.smooth = False
            ncap = len(new)
        bm.to_mesh(me)
        bm.free()
        report[o.name] = (closed_before, ncap)
    return report


# ------------------------------------------------------------------ flow lines
def catmull(pts, n_per=14):
    P = [Vector(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n_per):
            t = k / n_per
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(P[-2])
    return out


_flow_mats = {}


def _flow_mat(color, strength):
    hexcol = FLOW_COLORS.get(color, color)
    key = (hexcol, strength)
    if key in _flow_mats and _flow_mats[key].name in bpy.data.materials:
        return _flow_mats[key]
    m = _new_mat("Studio_flow_" + str(len(_flow_mats)))
    nt = m.node_tree
    nt.nodes.clear()
    out = _n(nt, "ShaderNodeOutputMaterial", 600, 0)
    em = _n(nt, "ShaderNodeEmission", 300, 0)
    em.inputs["Strength"].default_value = strength
    em.inputs["Color"].default_value = hexlin(hexcol)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    _flow_mats[key] = m
    return m


def flow_lines(path_points, color="air", radius=0.02, name="flow", strength=2.2, taper=True):
    """One glowing tube streak through path_points (xyz list), Catmull-Rom smoothed, thin -> thick -> thin.
    color: air | heat | fuel | electric | '#rrggbb'.  Animate growth with obj.data.bevel_factor_end (0..1)."""
    pts = catmull(path_points)
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    n = len(pts)
    for i, p in enumerate(pts):
        sp.points[i].co = (p.x, p.y, p.z, 1.0)
        t = i / (n - 1)
        sp.points[i].radius = (0.08 + 0.92 * min(smooth01(t / 0.22), smooth01((1 - t) / 0.22))) if taper else 1.0
    ob = bpy.data.objects.new(name, cu)
    bpy.context.scene.collection.objects.link(ob)
    cu.materials.append(_flow_mat(color, strength))
    ob.visible_shadow = False
    return ob


def rotate_path_about_x(pts, angle_deg, swirl_deg=0.0):
    """Copy of an (x, y, z) path rotated about the X axis by angle_deg, with an optional extra twist that builds up
    along the path (swirl_deg total) - gives a bundle of parallel streaks around an axial machine."""
    a = math.radians(angle_deg)
    xs = [p[0] for p in pts]
    x0, x1 = max(xs), min(xs)
    out = []
    for x, y, z in pts:
        tw = math.radians(swirl_deg) * smooth01((x0 - x) / (x0 - x1)) if x0 != x1 else 0.0
        c, s = math.cos(a + tw), math.sin(a + tw)
        out.append((x, y * c - z * s, y * s + z * c))
    return out
