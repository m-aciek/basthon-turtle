const DEFAULT_PYODIDE_URL =
  "https://cdn.jsdelivr.net/pyodide/v314.0.6/full/pyodide.mjs";
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
      eventHandler(pendingEvents.shift());
    }
  }
};

async function createRuntime(packageSpec) {
  const { loadPyodide } = await import(pyodideURL);
  const pyodide = await loadPyodide({
    stdout: text => self.postMessage({type: "stdout", text}),
    stderr: text => self.postMessage({type: "stderr", text})
  });

  // This explicit module is the only browser-host API used by the Python
  // package. Register it before installation because startup hooks may import
  // basthon.turtle immediately in some environments.
  pyodide.registerJsModule("basthon_turtle_transport", transport);
  await pyodide.loadPackage("micropip");
  const micropip = pyodide.pyimport("micropip");
  try {
    await micropip.install(packageSpec);
  } finally {
    micropip.destroy();
  }
  pyodide.runPython(`
from basthon.turtle._startup import install
install()
`);
  return pyodide;
}

let runtimePromise = null;
let runChain = Promise.resolve();

function reportError(error) {
  self.postMessage({
    type: "error",
    message: error && error.stack ? error.stack : String(error)
  });
}

self.addEventListener("message", event => {
  const message = event.data;

  if (message.type === "initialize") {
    if (runtimePromise === null) {
      runtimePromise = createRuntime(message.package);
      runtimePromise.then(
        () => self.postMessage({type: "ready"}),
        reportError
      );
    }
    return;
  }

  if (message.type === "event") {
    const payload = JSON.stringify(message.event);
    if (eventHandler === null) pendingEvents.push(payload);
    else eventHandler(payload);
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
