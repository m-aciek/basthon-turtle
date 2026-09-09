import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


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
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

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


if __name__ == "__main__":
    unittest.main()
