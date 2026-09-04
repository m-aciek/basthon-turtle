# Changelog

* Unreleased:
  * Added a native persistent Marimo renderer through the shared ``notebook``
    extra, which depends only on AnyWidget.
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
