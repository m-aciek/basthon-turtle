import os

from setuptools.command.build_py import build_py as _build_py


_STARTUP_FILES = ("basthon_turtle.pth", "basthon_turtle.start")


class BuildPy(_build_py):
    """Install interpreter startup hooks at the site-packages root."""

    def run(self):
        _build_py.run(self)
        project_root = os.path.dirname(os.path.abspath(__file__))
        for filename in _STARTUP_FILES:
            self.copy_file(
                os.path.join(project_root, filename),
                os.path.join(self.build_lib, filename),
            )

    def get_outputs(self, include_bytecode=1):
        outputs = _build_py.get_outputs(self, include_bytecode)
        outputs.extend(
            os.path.join(self.build_lib, filename)
            for filename in _STARTUP_FILES
        )
        return outputs
