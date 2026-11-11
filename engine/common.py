"""Shared helpers: repo paths, finding Blender / ffmpeg, version checks."""
import glob, os, platform, re, shutil, subprocess, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MIN_BLENDER = (4, 2)


def venv_python():
    for p in (os.path.join(ROOT, ".venv", "bin", "python"), os.path.join(ROOT, ".venv", "Scripts", "python.exe")):
        if os.path.exists(p):
            return p
    return sys.executable


def find_blender():
    """BLENDER env -> PATH -> default install locations.  Returns a path or None."""
    cands = [os.environ.get("BLENDER")]
    cands.append(shutil.which("blender"))
    system = platform.system()
    if system == "Darwin":
        cands.append("/Applications/Blender.app/Contents/MacOS/Blender")
        cands += glob.glob("/Applications/Blender*.app/Contents/MacOS/Blender")
    elif system == "Windows":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
            cands += sorted(glob.glob(os.path.join(base, "Blender Foundation", "Blender *", "blender.exe")), reverse=True)
    cands += sorted(glob.glob(os.path.expanduser("~/.local/blender/*/blender")), reverse=True)
    cands += sorted(glob.glob(os.path.expanduser("~/.local/blender/blender")), reverse=True)
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def blender_version(path):
    try:
        out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=60).stdout
        m = re.search(r"Blender (\d+)\.(\d+)", out)
        return (int(m.group(1)), int(m.group(2))) if m else None
    except Exception:
        return None


def find_tool(name):
    return shutil.which(name)
