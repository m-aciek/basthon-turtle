import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.check_release import check_archive, check_version

PROJECT_ROOT = Path(__file__).parents[2]


@unittest.skipUnless(shutil.which("uv"), "uv is required to build distributions")
class PackagingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = tempfile.TemporaryDirectory(prefix="basthon-turtle-build-")
        cls.addClassCleanup(output.cleanup)
        cls.dist = Path(output.name)
        result = subprocess.run(
            [
                "uv",
                "build",
                "--python",
                sys.executable,
                "--out-dir",
                str(cls.dist),
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def test_release_archives(self):
        for path in self.dist.iterdir():
            if path.name == ".gitignore":
                continue
            version = path.name.split("-")[1].removesuffix(".tar.gz")
            with self.subTest(path=path):
                check_archive(path, version)

    def test_release_rejects_missing_notebook_asset(self):
        wheel = next(self.dist.glob("*.whl"))
        version = wheel.name.split("-")[1]
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / wheel.name
            with (
                zipfile.ZipFile(wheel) as source,
                zipfile.ZipFile(broken, "w") as target,
            ):
                for name in source.namelist():
                    if name != "basthon/turtle/notebook.mjs":
                        target.writestr(name, source.read(name))
            with self.assertRaisesRegex(ValueError, "missing files.*notebook.mjs"):
                check_archive(broken, version)

    def test_release_rejects_missing_sdist_startup_hook(self):
        sdist = next(self.dist.glob("*.tar.gz"))
        version = sdist.name.split("-")[1].removesuffix(".tar.gz")
        with tempfile.TemporaryDirectory() as directory:
            broken = Path(directory) / sdist.name
            with (
                tarfile.open(sdist) as source,
                tarfile.open(broken, "w:gz") as target,
            ):
                for member in source.getmembers():
                    if not member.name.endswith("/wheel-data/basthon_turtle.pth"):
                        target.addfile(
                            member,
                            source.extractfile(member) if member.isfile() else None,
                        )
            with self.assertRaisesRegex(ValueError, "missing files.*basthon_turtle.pth"):
                check_archive(broken, version)

    def test_sdist_includes_documentation_examples_and_test_dependencies(self):
        with tarfile.open(next(self.dist.glob("*.tar.gz"))) as archive:
            names = {name.split("/", 1)[-1] for name in archive.getnames()}
        for directory in ("docs", "examples", "tests", "tools"):
            for path in (PROJECT_ROOT / directory).rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    with self.subTest(path=path):
                        self.assertIn(
                            path.relative_to(PROJECT_ROOT).as_posix(), names
                        )
        self.assertFalse(any("__pycache__" in name for name in names))

    def test_wheel_includes_runtime_files_and_startup_hooks(self):
        with zipfile.ZipFile(next(self.dist.glob("*.whl"))) as archive:
            names = set(archive.namelist())
        for filename in (
            "__init__.py",
            "_startup.py",
            "_pyodide.py",
            "notebook.css",
            "notebook.mjs",
            "standalone.html",
        ):
            with self.subTest(filename=filename):
                self.assertIn("basthon/turtle/" + filename, names)
        for filename in (
            "turtle.py", "basthon_turtle.pth", "basthon_turtle.start"
        ):
            with self.subTest(filename=filename):
                self.assertTrue(
                    any(
                        name == filename
                        or name.endswith(".data/purelib/" + filename)
                        for name in names
                    )
                )
        self.assertNotIn("basthon/__init__.py", names)
        self.assertFalse(any("__pycache__" in name for name in names))
        self.assertFalse(
            any(
                name.startswith(("docs/", "examples/", "tests/", "tools/"))
                for name in names
            )
        )


class ReleaseVersionTests(unittest.TestCase):
    def test_stable_tag_and_manual_run(self):
        check_version("1.2.3", "v1.2.3")
        check_version("1.2.3")

    def test_mismatched_tag(self):
        for tag in ("v1.2.4", "1.2.3", "v1.2.3rc1"):
            with (
                self.subTest(tag=tag),
                self.assertRaisesRegex(ValueError, "does not match"),
            ):
                check_version("1.2.3", tag)

    def test_non_stable_or_noncanonical_version(self):
        for version in ("1.2", "1.2.3rc1", "1.2.3.dev1", "01.2.3", "1.2.3+local"):
            with (
                self.subTest(version=version),
                self.assertRaisesRegex(ValueError, "stable"),
            ):
                check_version(version)


if __name__ == "__main__":
    unittest.main()
