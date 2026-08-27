# Live standalone browser mode (proof of concept)

Install the optional WebSocket dependency with:

```console
pip install "basthon-turtle[standalone]"
```

Then use the normal `turtle` API in CPython:

```pycon
>>> from turtle import *
>>> forward(100)
>>> left(90)
>>> pencolor("red")
>>> forward(50)
```

Importing `turtle` has no visible side effects. The first operation that draws
or changes a visible screen starts a server bound to `127.0.0.1` on an
available port and opens the default browser. Server work runs in daemon
threads, so ordinary turtle commands do not take over the Python main thread.
The same server, browser page, WebSocket connection, and SVG element remain
alive for later REPL commands.

The standalone extra is detected by the availability of its optional
`websockets` dependency. A base install without that dependency retains the
existing static SVG behavior. Environments that already provide `websockets`
also enable this PoC automatically on CPython; Pyodide and WASI stay in static
mode.

## Architecture

The existing turtle code remains the source of navigation and pen state. Each
supported operation still updates the cumulative static SVG representation,
and a small additional seam emits a semantic live command:

```text
turtle operation
    ├── existing SVG element / animation timeline (static output)
    └── one incremental JSON command (standalone browser)
```

The standalone session starts lazily on the first emitted command. Commands
are placed in a Python-side FIFO before the browser connection exists, so the
initial connection race cannot discard them. Once connected, the session sends
them in order over a WebSocket. The browser adds incoming messages to its own
FIFO and awaits each animation before starting the next one, which preserves
ordering when Python runs ahead of rendering.

The page owns one persistent SVG tree. A `move` command appends at most one new
line and changes the existing turtle's transform; a `rotate` command only
changes that transform. Browser animation uses `requestAnimationFrame`, and
the final coordinates remain as ordinary DOM attributes. No complete SVG
document is transmitted, and no earlier operation is replayed.

The PoC covers movement and rotation plus pen up/down, pen color and size,
turtle visibility, background color, and text. Browser-to-Python events,
dialogs, and multiple clients are intentionally out of scope.

`done()` is not a startup trigger. In standalone mode it finalizes the normal
static scene and waits up to five seconds for queued commands to be handed to
the browser; it does not wait for their animations. Unlike Tk's `mainloop()`,
it does not block an interactive session indefinitely.

Run the example with:

```console
python examples/standalone_live.py
```

## Turtle demo

The non-interactive `peace` demo can use the live browser renderer directly:

```console
python -m turtledemo.peace
```

Its Tk/X11 color names are translated to equivalent browser colors while
rendering. The public turtle color getters continue to return the original
names. The full `python -m turtledemo` Tk viewer and interactive demos remain
outside the standalone proof of concept.
