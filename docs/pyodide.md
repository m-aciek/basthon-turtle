# Browser-only Pyodide live mode

The live renderer can run entirely inside one browser tab without PyScript, a
localhost Python process, or a WebSocket. The included example uses plain
Pyodide in a Web Worker so a running Python program does not block SVG
animation on the browser's main thread.

```text
Pyodide worker
    -> JSON turtle command
    -> postMessage
    -> persistent SVG renderer on the main thread

pointer or key event
    -> postMessage
    -> registered Python callback in the worker
```

## Try the source checkout

Serve the repository over HTTP:

```console
python -m http.server 8000
```

Then open:

```text
http://localhost:8000/examples/pyodide/
```

By default, the example loads the package's Python sources directly from the
adjacent `basthon/turtle` directory, so it does not depend on a published
package. The `package` query parameter overrides those checkout sources and may
be either a wheel URL or another package requirement. For example, after
running `python -m build`:

```text
http://localhost:8000/examples/pyodide/?package=../../dist/basthon_turtle-0.3.0-py3-none-any.whl
```

The page is only a small demonstration host: it supplies an editor, creates
the worker, and embeds the existing live SVG page in its transport-neutral
`parent` mode.

By default the worker imports the versioned Pyodide release used by the
example. A self-hosted build can be selected with another query parameter:

```text
?package=../../dist/basthon_turtle-0.3.0-py3-none-any.whl&pyodide=/pyodide/pyodide.mjs
```

## Host contract

Before the package is imported, a Pyodide host registers a JavaScript module
named `basthon_turtle_transport`:

```javascript
const transport = {
  emit(payload) {
    // payload is one JSON-encoded semantic turtle command.
    postMessage({type: "command", payload});
  },
  set_event_handler(handler) {
    // Retain this PyProxy until it is replaced with null. Call it with a
    // JSON-encoded browser event when a pointer or key event occurs.
    eventHandler = handler;
  }
};

pyodide.registerJsModule("basthon_turtle_transport", transport);
```

Install `basthon-turtle` with `micropip`, then call the runtime-install shim so
ordinary `import turtle` selects this package:

```javascript
await pyodide.loadPackage("micropip");
const micropip = pyodide.pyimport("micropip");
await micropip.install(packageSpec);
micropip.destroy();
pyodide.runPython(`
from basthon.turtle._startup import install
install()
`);
```

When this module is present on an Emscripten build, `basthon.turtle` creates a
Pyodide session automatically. Notebook/Marimo rendering retains priority in
those environments; regular CPython retains the existing standalone
WebSocket backend.

## Main-thread Pyodide

The same transport contract can be implemented with Pyodide on the main
thread, which is adequate for a REPL that runs one short command at a time.
For complete programs, prefer the worker layout: synchronous Python execution
on the main thread prevents `requestAnimationFrame` from advancing until the
Python call finishes.
