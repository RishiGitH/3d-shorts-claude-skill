"""Check that everything the 3d-short skill needs is installed.  Run:  python engine/setup/doctor.py

Prints one line per check (OK / MISSING) with the exact command that fixes it.  Exit code 0 = ready, 1 = something missing.
"""
import importlib, os, platform, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from common import ROOT, MIN_BLENDER, find_blender, blender_version, venv_python  # noqa: E402

SYSTEM = platform.system()
INSTALL = "bash engine/setup/install.sh" if SYSTEM != "Windows" else r"powershell -ExecutionPolicy Bypass -File engine\setup\install.ps1"
bad = 0


def report(ok, name, detail, fix=None):
    global bad
    print(("  OK       " if ok else "  MISSING  ") + f"{name}: {detail}")
    if not ok:
        bad += 1
        if fix:
            print(f"           fix: {fix}")


# Blender
b = find_blender()
if b:
    v = blender_version(b)
    ok = bool(v and v >= MIN_BLENDER)
    report(ok, "Blender", f"{b} ({'.'.join(map(str, v)) if v else 'unknown version'})",
           f"needs {MIN_BLENDER[0]}.{MIN_BLENDER[1]} or newer - {INSTALL}")
else:
    report(False, "Blender", "not found", INSTALL)

# ffmpeg / ffprobe
for tool in ("ffmpeg", "ffprobe"):
    p = shutil.which(tool)
    report(bool(p), tool, p or "not found", INSTALL)

# python packages (checked with the venv python, which is what make_short uses)
py = venv_python()
for mod, pkg in (("numpy", "numpy"), ("scipy", "scipy"), ("PIL", "pillow"), ("piper", "piper-tts")):
    r = subprocess.run([py, "-c", f"import {mod}"], capture_output=True)
    report(r.returncode == 0, f"python:{pkg}", py if r.returncode == 0 else "import failed", INSTALL)

# fonts + default voice
for f in ("Barlow-Bold.ttf", "Barlow-SemiBold.ttf"):
    p = os.path.join(ROOT, "assets", "fonts", f)
    report(os.path.exists(p), f"font {f}", p if os.path.exists(p) else "missing (should ship with the repo)", "git checkout -- assets/fonts")
for ext in (".onnx", ".onnx.json"):
    p = os.path.join(ROOT, "assets", "voices", "en_US-libritts_r-medium" + ext)
    report(os.path.exists(p), f"voice model {ext}", p if os.path.exists(p) else "not downloaded", INSTALL)

# optional cloud voices
print("  optional  GEMINI_API_KEY:", "set" if os.environ.get("GEMINI_API_KEY") else "not set (Piper local voice is used)")
print("  optional  ELEVENLABS_API_KEY:", "set" if os.environ.get("ELEVENLABS_API_KEY") else "not set")

print()
print("READY" if not bad else f"{bad} problem(s) - fix them, then run this check again.")
sys.exit(1 if bad else 0)
