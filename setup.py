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
A revised version of CPython's turtle module, browser-friendly.

The optional standalone mode supports interactive CPython use. The abbreviated
docstrings remain less suitable for ``help()`` than CPython's implementation.

All public methods/functions of the CPython version should exist, if only
to print out a warning that they are not implemented. The intent is to make
it easier to "port" any existing turtle program from CPython to the browser.

Initially the code was part of Brython, then ported to Basthon, then published as a standalone package.

Installation
------------

.. code:: bash

    pip install basthon-turtle

For a live, persistent browser window in a regular CPython session, install
the proof-of-concept standalone extra:

.. code:: bash

    pip install "basthon-turtle[standalone]"

or

.. code:: python

    import micropip
    await micropip.install('basthon-turtle')

Usage
-----

Note: if running multiple times you need to restart the state of screen with ``turtle.restart()`` function.

Standalone CPython
==================

The browser starts lazily on the first visible turtle operation. It remains
alive between commands and receives incremental drawing updates:

.. code:: python

    from turtle import forward, left

    forward(100)
    left(90)
    forward(50)

Jupyter
=======

.. code:: python

    from IPython.display import HTML
    from turtle import forward, done, svg

    forward(100)
    done()

    HTML(svg())

Marimo
======

.. code:: python

    import marimo as mo

    from turtle import forward, done, svg

    forward(100)
    done()
    forward(100)
    mo.Html(svg())


Credits
-------
- bearney74
- André Roberge
- Romain Casati

Implementation
--------------

.. important::
    We use SVG for drawing turtles. If we have a turtle at an angle
    of 350 degrees and we rotate it by an additional 20 degrees, we will have
    a turtle at an angle of 370 degrees.  For turtles drawn periodically on
    a screen (like typical animations, including the CPython turtle module),
    drawing a turtle with a rotation of 370 degrees is the same as a rotation of
    10 degrees.  However, using SVG, if we "slowly" animate an object,
    rotating it from 350 to 370 degrees, the result will not be the same
    as rotating it from 350 to 10 degrees. For this reason, we did not use the
    Vec2D class from the CPython module and handle the rotations quite differently.
"""

setuptools.setup(
    name="basthon-turtle",
    version="0.1.1",
    author="Maciej Olko",
    author_email="maciej.olko@gmail.com",
    description="A browser-friendly implementation of Python's turtle module.",
    long_description=long_description,
    url="https://github.com/m-aciek/basthon-turtle",
    project_urls={
        "Changelog": "https://github.com/m-aciek/basthon-turtle/blob/main/CHANGELOG.md",
    },
    packages=setuptools.find_namespace_packages(include=["basthon.*"]),
    py_modules=["turtle"],
    package_data={"basthon.turtle": ["standalone.html"]},
    extras_require={"standalone": ["websockets>=14"]},
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
