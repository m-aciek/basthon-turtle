"""Verify release archives and fresh installs without importing the checkout."""

import argparse
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

RUNTIME_FILES = (
    "__init__.py", "svg.py", "_startup.py", "_notebook.py", "_standalone.py",
    "_pyodide.py", "notebook.css", "notebook.mjs", "standalone.html",
)
STARTUP_FILES = ("turtle.py", "basthon_turtle.pth", "basthon_turtle.start")


def check_version(version, tag=""):
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError("Releases currently require a stable X.Y.Z version")
    if tag and tag != "v" + version:
        raise ValueError(f"Tag {tag!r} does not match package version {version!r}")


def check_archive(path, version):
    """Check metadata and files needed by every supported renderer."""
    stem = f"basthon_turtle-{version}"
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            files = {name: archive.read(name) for name in archive.namelist()
                     if not name.endswith("/")}
        metadata = files[f"{stem}.dist-info/METADATA"]
        for name in STARTUP_FILES:
            relocated = f"{stem}.data/purelib/{name}"
            if relocated in files:
                files[name] = files.pop(relocated)
        required = set(STARTUP_FILES)
    else:
        with tarfile.open(path) as archive:
            files = {member.name.removeprefix(stem + "/"):
                     archive.extractfile(member).read()
                     for member in archive.getmembers() if member.isfile()}
        metadata = files["PKG-INFO"]
        required = {"wheel-data/" + name for name in STARTUP_FILES}
        required.update((
            "pyproject.toml", "docs/pypi.rst", "README.md", "CHANGELOG.md",
            "examples/pyodide/worker.mjs", "examples/pyodide/index.html",
        ))
    required.update("basthon/turtle/" + name for name in RUNTIME_FILES)
    missing = required - files.keys()
    if missing:
        raise ValueError(f"{path.name}: missing files: {sorted(missing)}")
    empty = {name for name in required if not files[name].strip()}
    if empty:
        raise ValueError(f"{path.name}: empty files: {sorted(empty)}")
    if "basthon/__init__.py" in files:
        raise ValueError("basthon must remain a namespace package")
    if any("__pycache__" in name.split("/") for name in files):
        raise ValueError(f"{path.name}: contains bytecode caches")
    parsed = BytesParser().parsebytes(metadata)
    if parsed["Name"] != "basthon-turtle" or parsed["Version"] != version:
        raise ValueError(f"{path.name}: unexpected package metadata")


SMOKE_TEST = r'''
import importlib
from importlib.metadata import distribution
from pathlib import Path
import sys
import sysconfig
from unittest import mock
import xml.etree.ElementTree as ET

# Check the startup hook before explicitly importing the implementation.
assert "turtle" in sys.modules, "startup hook did not install turtle"
import turtle
from basthon import turtle as implementation
assert turtle is implementation
purelib = Path(sysconfig.get_path("purelib")).resolve()
assert Path(turtle.__file__).resolve().is_relative_to(purelib), turtle.__file__
assert distribution("basthon-turtle").version == sys.argv[1]
for module in ("svg", "_startup", "_notebook", "_standalone", "_pyodide"):
    loaded = importlib.import_module("basthon.turtle." + module)
    assert Path(loaded.__file__).resolve().is_relative_to(purelib)
for filename in ("notebook.css", "notebook.mjs", "standalone.html"):
    assert Path(turtle.__file__).with_name(filename).read_text().strip()
for filename in ("turtle.py", "basthon_turtle.pth", "basthon_turtle.start"):
    assert (purelib / filename).read_text().strip()

# Exercise the installed runtime shim with its directory first, since host
# CPython otherwise resolves the standard library before site-packages.
del sys.modules["turtle"]
with mock.patch.object(sys, "path", [str(purelib), *sys.path]):
    assert importlib.import_module("turtle") is implementation

# Exercise drawing without opening a browser or installing optional renderers.
screen = turtle.Screen()
with mock.patch.object(screen, "_emit_live"):
    screen.animation("off")
    pen = turtle.Turtle()
    pen.forward(100)
    pen.left(90)
    pen.forward(50)
    assert tuple(pen.position()) == (100, 50)
    turtle.done()
    svg = ET.fromstring(screen.svg())
    assert svg.findall(".//{http://www.w3.org/2000/svg}line")
print("Verified installed", sys.argv[1], "from", turtle.__file__)
'''


def check_install(path, version, python):
    with tempfile.TemporaryDirectory(prefix="basthon-release-") as directory:
        work = Path(directory)
        venv = work / "venv"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)

        def run(*args):
            subprocess.run(args, cwd=work, env=env, check=True)

        run("uv", "venv", "--no-project", "--python", python, str(venv))
        executable = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        # A new environment for each archive; the sdist must build on its own.
        run("uv", "pip", "install", "--python", str(executable), "--no-cache",
            "--no-deps", str(path.resolve()))
        run(str(executable), "-I", "-c", SMOKE_TEST, version)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    check_version(args.version)
    expected = {
        f"basthon_turtle-{args.version}-py3-none-any.whl",
        f"basthon_turtle-{args.version}.tar.gz",
    }
    paths = sorted(path for path in args.dist.iterdir() if path.name != ".gitignore")
    if {path.name for path in paths} != expected:
        parser.error(f"Expected exactly these artifacts: {sorted(expected)}")
    for path in paths:
        check_archive(path, args.version)
        check_install(path, args.version, args.python)


if __name__ == "__main__":
    main()
