# Changelog

* 0.4.1:
  * Fixed the Marimo canvas disappearing when its cell is rerun, preserving
    the existing drawing and animating new commands in a replacement widget.
  * Added `jupyter_renderer("svg")` for JupyterLite sites without the anywidget
    browser extension, updating one SVG output after each cell and preserving
    the accumulated drawing across cell reruns, including after a cell error.
* 0.4.0:
  * Added CPython-compatible `Vec2D` vectors and screen-independent navigation,
    with `pos()` and `position()` returning vectors while preserving SVG
    animation paths across zero and through full turns.
  * Migrated package configuration from `setup.py` to `pyproject.toml`,
    using the uv build backend.
  * Added warnings on the first visible turtle operation when optional rendering
    dependencies are missing, suggesting the `notebook` or `standalone` extra
    for the current environment.
* 0.3.1:
  * Improve package descriptions.
* 0.3.0:
  * Added a native persistent Marimo renderer through the shared ``notebook``
    extra, which depends only on AnyWidget.
  * Added a browser-only Pyodide worker transport and example for persistent,
    incremental live rendering without a localhost Python server or WebSocket.
  * Added a headless CPython turtle compatibility report and a regression
    baseline for public API coverage and `Vec2D`/`TNavigator` behavior.
* 0.2.0:
  * Added an optional persistent Jupyter renderer that batches turtle commands
    per cell and animates them in one shared SVG widget.
  * Added a portable inline canvas by default, with an explicitly optional
    JupyterLab sidecar and support for synchronized cloned output views.
* 0.1.2:
  * Added live turtle dragging and shape sizing, enabling `turtledemo.colormixer`
    in standalone mode.
  * Added standalone key press and release events through `onkeypress()`,
    `onkey()`, and `onkeyrelease()`.
  * Implemented `Turtle.clear()` for static and standalone drawings.
  * Added live rendering for built-in turtle shapes, including the rectangular
    blocks used by `turtledemo.sorting_animate`.
  * Fixed horizontal scaling in custom world coordinates.
* 0.1.1:
  * Added support for RGB sequences and separate RGB components in `color()`, `pencolor()`, `fillcolor()`,
    and `bgcolor()`, enabling `turtledemo.rosette`.
  * Implemented `colormode()` with the CPython-compatible `1.0` and `255` color ranges.
  * Fixed `fillcolor()` returning the pen color instead of the fill color.
* 0.1.0:
  * Added a proof-of-concept live standalone browser renderer with incremental movement and polygon-fill updates.
  * Added support for the Tk color names used by `turtledemo.peace`.
* 0.0.5: Fix typo in package description.
* 0.0.4: Added a compatibility shim so `import turtle` works after runtime installation with tools such as `micropip`.
* 0.0.3: Moved the implementation to `basthon.turtle` and improved the mechanism for overriding the standard-library `turtle` module.
* 0.0.2: Expanded the package description.
* 0.0.1: Initial release.
