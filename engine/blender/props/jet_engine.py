"""Example hero: a simple turbofan jet engine, built entirely from kit.py primitives.

Intake at +X, nozzle at -X.  Shows every hero feature: shell parts (nacelle, core casing) for cutaway / x-ray, five axial
modules for the exploded view, spinning blade rows, named label anchors and named flow paths.

Copy this file to projects/<slug>/hero.py as a starting point for your own hero and edit `build()`.
"""
import math
from kit import (lathe, tube, disc, blade_ring, cylinder, sphere, hero_dict)


def _radial(path_xr):
    """(x, r) pairs -> (x, y, z) points in the +Y direction (shots.json can spin copies around X with "copies")."""
    return [(x, r, 0.0) for x, r in path_xr]


def build():
    # ---- shells (cut / x-ray / hidden by explode)
    nacelle = lathe([(2.15, 0.96), (1.0, 0.94), (-0.3, 0.90), (-0.3, 0.99), (0.5, 1.10), (1.6, 1.12), (2.2, 1.06), (2.25, 1.0)],
                    "nacelle", "steel", steps=96)
    core_case = lathe([(1.45, 0.38), (0.5, 0.40), (-0.5, 0.36), (-1.3, 0.30), (-2.4, 0.26),
                       (-2.4, 0.31), (-1.3, 0.37), (-0.5, 0.43), (0.5, 0.47), (1.45, 0.44), (1.5, 0.41)],
                      "core_casing", "steel_mid", steps=96)

    # ---- fan module
    spinner = lathe([(2.6, 0.0), (2.45, 0.09), (2.2, 0.2), (1.9, 0.3), (1.85, 0.0)], "spinner", "white", steps=48)
    fan = [disc(1.78, 0.34, 0.24, "fan_hub", "steel_dark"),
           blade_ring(18, 1.78, 0.30, 0.94, 0.38, 0.05, 38, "fan_blades", "steel", sweep=-0.12)]

    # ---- compressor module: four stages of shrinking blades on a tapered drum
    comp = [lathe([(1.35, 0.0), (1.35, 0.2), (0.1, 0.27), (0.1, 0.0)], "comp_drum", "steel_dark", steps=48)]
    for i, x in enumerate((1.2, 0.9, 0.6, 0.3)):
        comp.append(blade_ring(26, x, 0.21 + 0.015 * i, 0.375 - 0.008 * i, 0.10, 0.018, 30, f"comp_blades{i}", "steel", sweep=-0.02))

    # ---- combustor module
    comb = [tube(-0.05, -0.75, 0.34, 0.30, "combustor_liner", "copper"),
            lathe([(0.0, 0.0), (0.0, 0.22), (-0.8, 0.22), (-0.8, 0.0)], "combustor_core", "steel_dark", steps=48)]
    for k in range(8):
        a = 2 * math.pi * k / 8
        y, z = 0.32 * math.cos(a), 0.32 * math.sin(a)
        comb.append(cylinder((0.12, y, z), (-0.1, y, z), 0.025, f"injector{k}", "gold", steps=12))

    # ---- turbine module: two discs
    turb = [lathe([(-0.85, 0.0), (-0.85, 0.2), (-1.4, 0.2), (-1.4, 0.0)], "turbine_drum", "steel_dark", steps=48)]
    for i, x in enumerate((-0.98, -1.28)):
        turb.append(blade_ring(32, x, 0.19, 0.31 + 0.005 * i, 0.09, 0.016, -28, f"turbine_blades{i}", "gold", sweep=0.0, taper=0.8))

    # ---- nozzle module
    nozzle = [lathe([(-1.6, 0.0), (-1.7, 0.2), (-2.3, 0.17), (-2.95, 0.0)], "tail_cone", "steel_mid", steps=48)]

    shaft = cylinder((1.8, 0, 0), (-1.5, 0, 0), 0.08, "shaft", "steel_dark")

    flows = {
        # (x, r) pairs along +Y; use "copies" in shots.json to spread them around the engine
        "bypass": _radial([(3.5, .60), (2.7, .66), (2.0, .74), (1.3, .78), (0.4, .80), (-0.3, .83), (-1.0, .88), (-2.0, .90), (-3.3, .84)]),
        "core": _radial([(3.5, .20), (2.7, .22), (1.9, .26), (1.1, .28), (0.5, .28), (0.05, .27)]),
        "exhaust": _radial([(-0.2, .20), (-0.7, .24), (-1.3, .26), (-2.0, .26), (-2.9, .21), (-3.7, .14)]),
    }
    anchors = {"nacelle": (0.9, 0.0, 1.12), "fuel": (0.06, 0.0, 0.34), "exhaust": (-3.2, 0.0, 0.0), "intake": (2.45, 0.0, 0.0)}

    return hero_dict(
        parts={"nacelle": nacelle, "core_casing": core_case, "spinner": spinner, "fan": fan, "compressor": comp,
               "combustor": comb, "turbine": turb, "nozzle": nozzle, "shaft": shaft},
        shell=["nacelle", "core_casing"],
        modules=[["spinner", "fan"], ["compressor"], ["combustor"], ["turbine"], ["nozzle"]],
        spin={"fan": 0.40, "compressor": 0.55, "turbine": 0.60},
        anchors=anchors, flows=flows)
