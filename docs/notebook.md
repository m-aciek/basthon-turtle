# Persistent notebook canvas

## Jupyter

Install the portable Jupyter renderer with:

```console
pip install "basthon-turtle[notebook]"
```

Then use the normal `turtle` API in separate cells. There is no need to call
`done()` or display `svg()` explicitly:

```python
from turtle import *

forward(100)
```

```python
left(90)
forward(50)
```

With the `notebook` extra alone, the first visible turtle operation creates one
persistent inline SVG widget. This is the portable default because an ordinary
widget works across JupyterLab, Notebook 7, VS Code, Colab, and other
widget-capable frontends.

For a JupyterLab-specific side panel, explicitly install the sidecar extra:

```console
pip install "basthon-turtle[sidecar]"
```

The sidecar is anchored to the right of the notebook and can be rearranged like
other JupyterLab tabs. The kernel cannot reliably identify every frontend
connected to it, so the frontend-specific dependency and behavior are kept
behind this explicitly named extra. If `sidecar` is not importable, the
renderer automatically falls back to the inline widget. When it is installed
but the active frontend does not support it, disable it before the first turtle
operation:

```python
from turtle import jupyter_sidecar

jupyter_sidecar(False)
```

An inline widget remains associated with its original cell, but JupyterLab can
mirror it into an independent panel. Right-click its output, choose **Create
New View for Cell Output**, then dock the synchronized view beside the
notebook.

## Cell behavior

The notebook renderer uses the same semantic commands as standalone mode, but
does not use a localhost server or WebSocket:

```text
turtle operation
    -> Python command buffer
    -> IPython post_run_cell
    -> one anywidget state update
    -> browser-side FIFO
    -> persistent SVG
```

Commands remain buffered until IPython fires `post_run_cell`, including when a
cell ends with an exception. The JavaScript client awaits each movement or
rotation before applying the next command, so operations remain ordered even
though the Python cell has already completed.

The widget stores its command history as synchronized state. Its original view
animates only each newly published suffix. A view opened later first applies
the acknowledged history without animation, leaving it at the current state;
future commands are then animated normally. Browser callbacks such as turtle
dragging and key events send messages back through the widget communication
channel, and drawing produced by a callback is published immediately.

The renderer currently covers the same incremental operations as standalone
mode: movement, rotation, polygon fills, pen state and colors, built-in turtle
shapes, visibility and sizing, background color, text, owner-scoped `clear()`,
dragging, and key events. Static `done()`/`svg()` output remains available with
or without the notebook extra.

## Marimo

Install the shared notebook integration with:

```console
pip install "basthon-turtle[notebook]"
```

Then use the normal `turtle` API. The first visible operation mounts a
persistent AnyWidget in that cell, and later cells update the same canvas:

```python
from turtle import *

forward(100)
```

```python
left(90)
forward(50)
```

Marimo does not expose the IPython cell hooks used by the Jupyter backend, so
each semantic command is synchronized immediately. The browser still consumes
the commands in FIFO order and preserves the drawing between cells. Browser
callbacks use the same bidirectional widget connection as in Jupyter.

The renderer uses Marimo's native `mo.ui.anywidget` integration and mounts it
through `mo.output.replace`; users do not need to import `marimo`, call
`done()`, or wrap `svg()` in `mo.Html`.
