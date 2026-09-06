import os

import setuptools
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

long_description = """\
Basthon Turtle is a browser-friendly implementation of Python's
``turtle`` module. It keeps the familiar turtle API while replacing the Tk
canvas with SVG, so turtle programs can run in notebooks and browser-based
Python environments.

The package supports four display environments:

* CPython with an optional standalone browser window;
* Jupyter with a persistent inline SVG widget or optional JupyterLab sidecar;
* Marimo with a persistent AnyWidget canvas; and
* Pyodide, where a Web Worker sends incremental drawing updates to an SVG
  page without a Python server or WebSocket.

The rendering backends share turtle state and drawing operations, while each
environment supplies its own transport and display. The traditional
``done()`` workflow remains available, and ``svg()`` returns the current SVG
scene.

Installation
------------

.. code:: bash

    pip install basthon-turtle

For a live, persistent browser window in a regular CPython session, install
the standalone extra:

.. code:: bash

    pip install "basthon-turtle[standalone]"

or

.. code:: python

    import micropip
    await micropip.install('basthon-turtle')

Usage
-----

When reusing a Python process, call ``turtle.restart()`` to reset the screen
and turtle state.

Standalone CPython
==================

The browser starts lazily on the first visible turtle operation. It remains
alive between commands and receives incremental drawing updates:

.. code:: python

    from turtle import *

    forward(100)
    left(90)
    forward(50)

Jupyter
=======

Install the portable persistent Jupyter renderer with:

.. code:: bash

    pip install "basthon-turtle[notebook]"

Turtle commands are buffered during each cell and animated in one persistent
inline SVG widget after the cell finishes:

.. code:: python

    from turtle import forward, left

    forward(100)
    left(90)
    forward(50)

For a JupyterLab-specific panel, install ``basthon-turtle[sidecar]`` instead.
Call ``jupyter_sidecar(False)`` before drawing to force the portable inline
widget when ``sidecar`` is otherwise available.

Marimo
======

Install the native persistent Marimo renderer with:

.. code:: bash

    pip install "basthon-turtle[notebook]"

.. code:: python

    from turtle import forward, left

    forward(100)
    left(90)
    forward(50)

The first visible operation mounts a persistent AnyWidget in the current cell.
Later turtle calls update the same canvas automatically; no explicit done()
call is required.

Browser-only Pyodide
====================

Plain Pyodide can host the live mode entirely in one browser tab. The example
runs Python in a Web Worker and forwards incremental turtle operations to a
persistent SVG renderer with ``postMessage``. This keeps animation responsive
without a localhost server or WebSocket; see ``docs/pyodide.md`` for a
complete example.


Credits
-------
- bearney74
- André Roberge
- Romain Casati
"""

setuptools.setup(
    name="basthon-turtle",
    version="0.3.0",
    author="Maciej Olko",
    author_email="maciej.olko@gmail.com",
    description="A Python turtle implementation with live SVG rendering across Jupyter, Marimo, Pyodide, and standalone CPython.",
    long_description=long_description,
    long_description_content_type="text/x-rst",
    url="https://github.com/m-aciek/basthon-turtle",
    project_urls={
        "Changelog": "https://github.com/m-aciek/basthon-turtle/blob/main/CHANGELOG.md",
    },
    packages=setuptools.find_namespace_packages(include=["basthon.*"]),
    py_modules=["turtle"],
    package_data={
        "basthon.turtle": ["notebook.css", "notebook.mjs", "standalone.html"]
    },
    extras_require={
        "notebook": ["anywidget>=0.9"],
        "sidecar": ["anywidget>=0.9", "sidecar>=0.8"],
        "standalone": ["websockets>=14"],
    },
    cmdclass={"build_py": BuildPy},
    license="GPL-3.0-or-later",
    classifiers=[
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Interpreters",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
    ],
    python_requires=">=3.4",
)
