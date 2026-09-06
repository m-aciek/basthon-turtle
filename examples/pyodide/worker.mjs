const DEFAULT_PYODIDE_URL =
  "https://cdn.jsdelivr.net/pyodide/v314.0.6/full/pyodide.mjs";
const SOURCE_ROOT = "/tmp/basthon-turtle-example";
const SOURCE_FILES = [
  "__init__.py",
  "_notebook.py",
  "_pyodide.py",
  "_standalone.py",
  "_startup.py",
  "svg.py"
];
const parameters = new URLSearchParams(self.location.search);
const pyodideURL = parameters.get("pyodide") || DEFAULT_PYODIDE_URL;

let eventHandler = null;
const pendingEvents = [];

const transport = {
  emit(payload) {
    self.postMessage({type: "command", payload});
  },

  set_event_handler(handler) {
    eventHandler = handler;
    while (eventHandler !== null && pendingEvents.length) {
      dispatchEvent(pendingEvents.shift());
    }
  }
};

function reportStatus(message) {
  self.postMessage({type: "status", message});
}

async function loadCheckoutSources(pyodide) {
  reportStatus("Loading basthon-turtle from this checkout…");
  const packageDirectory = `${SOURCE_ROOT}/basthon/turtle`;
  pyodide.FS.mkdirTree(packageDirectory);

  await Promise.all(SOURCE_FILES.map(async filename => {
    const url = new URL(
      `../../basthon/turtle/${filename}`, self.location.href
    );
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(
        `Could not load ${url.href} (${response.status} ${response.statusText})`
      );
    }
    pyodide.FS.writeFile(
      `${packageDirectory}/${filename}`, await response.text()
    );
  }));

  pyodide.runPython(`
import sys
sys.path.insert(0, ${JSON.stringify(SOURCE_ROOT)})
`);
}

async function installPackage(pyodide, packageSpec) {
  reportStatus(`Installing ${packageSpec}…`);
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  try {
    await micropip.install(packageSpec);
  } finally {
    micropip.destroy();
  }
}

async function createRuntime(packageSpec) {
  reportStatus("Loading Pyodide…");
  const { loadPyodide } = await import(pyodideURL);
  const pyodide = await loadPyodide({
    stdout: text => self.postMessage({type: "stdout", text}),
    stderr: text => self.postMessage({type: "stderr", text})
  });

  // This explicit module is the only browser-host API used by the Python
  // package. Register it before installation because startup hooks may import
  // basthon.turtle immediately in some environments.
  pyodide.registerJsModule("basthon_turtle_transport", transport);
  if (packageSpec) await installPackage(pyodide, packageSpec);
  else await loadCheckoutSources(pyodide);
  reportStatus("Configuring turtle…");
  pyodide.runPython(`
from basthon.turtle import _pyodide
from basthon.turtle._startup import install

if not _pyodide.is_available():
    raise RuntimeError("basthon-turtle has no usable Pyodide worker backend")
install()
`);
  return pyodide;
}

let runtimePromise = null;
let runChain = Promise.resolve();

function reportError(error, options = {}) {
  self.postMessage({
    type: "error",
    phase: options.phase || "run",
    summary: options.summary || "Python execution failed.",
    hint: options.hint || "",
    detail: error && error.stack ? error.stack : String(error)
  });
}

function dispatchEvent(payload) {
  try {
    eventHandler(payload);
  } catch (error) {
    reportError(error, {summary: "Python event callback failed."});
  }
}

self.addEventListener("message", event => {
  const message = event.data;

  if (message.type === "initialize") {
    if (runtimePromise === null) {
      const packageSpec = message.package || null;
      runtimePromise = createRuntime(packageSpec);
      runtimePromise.then(
        () => self.postMessage({type: "ready"}),
        error => reportError(error, {
          phase: "initialize",
          summary: "Could not initialize the Pyodide turtle runtime.",
          hint: packageSpec
            ? `Check the package requirement or wheel URL: ${packageSpec}`
            : "Serve the repository root so the checkout turtle sources " +
              "are available."
        })
      );
    }
    return;
  }

  if (message.type === "event") {
    const payload = JSON.stringify(message.event);
    if (eventHandler === null) pendingEvents.push(payload);
    else dispatchEvent(payload);
    return;
  }

  if (message.type === "run") {
    if (runtimePromise === null) {
      reportError(new Error("Pyodide worker has not been initialized"));
      return;
    }
    runChain = runChain.then(async () => {
      const pyodide = await runtimePromise;
      await pyodide.runPythonAsync(message.code);
      self.postMessage({type: "finished"});
    }).catch(reportError);
  }
});
