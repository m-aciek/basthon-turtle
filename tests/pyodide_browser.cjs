// Run with Node.js; no npm dependencies are required.
const assert = require("assert");
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const root = path.resolve(__dirname, "..");

function checkCallbacks(queued) {
  const messages = [];
  let receive;
  let calls = 0;
  const context = vm.createContext({
    URLSearchParams,
    self: {
      location: {search: ""},
      postMessage: message => messages.push(message),
      addEventListener: (type, handler) => { receive = handler; }
    },
    callback: payload => {
      assert.strictEqual(JSON.parse(payload).event, "keypress");
      if (++calls === 1) throw new Error("callback failed");
    }
  });
  vm.runInContext(fs.readFileSync(
    path.join(root, "examples/pyodide/worker.mjs"), "utf8"
  ), context);
  const register = () => vm.runInContext(
    "transport.set_event_handler(callback)", context
  );
  if (!queued) register();
  for (let i = 0; i < 2; i++) {
    receive({data: {type: "event", event: {event: "keypress"}}});
  }
  if (queued) register();
  assert.strictEqual(calls, 2, "A failed callback must not stop later events");
  assert.strictEqual(messages.length, 1);
  assert.strictEqual(messages[0].type, "error");
  assert.strictEqual(messages[0].phase, "run");
  assert(messages[0].detail.includes("callback failed"));
}

function checkRendererStartup(early) {
  const html = fs.readFileSync(
    path.join(root, "examples/pyodide/index.html"), "utf8"
  );
  const listeners = {};
  const commands = [];
  const origin = "http://localhost:8000";
  const nodes = {};
  for (const id of ["canvas", "code", "output", "run", "status"]) {
    nodes[id] = {dataset: {}, addEventListener() {}};
  }
  const canvas = nodes.canvas;
  canvas.contentWindow = {postMessage: message => commands.push(message)};
  const ready = () => {
    if (listeners.message) listeners.message({
      source: canvas.contentWindow, origin,
      data: {source: "basthon-turtle", type: "ready"}
    });
  };
  let rendererLoaded = false;
  Object.defineProperty(canvas, "src", {set(url) {
    assert(url.endsWith("standalone.html?transport=parent"));
    rendererLoaded = true;
    if (early) ready();
  }});
  // An eager iframe can finish before the remaining host HTML arrives.
  const initialSrc = html.match(/<iframe\b[^>]*\bsrc="([^"]+)"/);
  if (initialSrc) canvas.src = initialSrc[1];
  let worker;
  class Worker {
    constructor() { worker = this; this.listeners = {}; }
    postMessage() {}
    addEventListener(type, handler) { this.listeners[type] = handler; }
  }
  vm.runInNewContext(html.match(/<script type="module">([\s\S]*?)<\/script>/)[1], {
    URL, URLSearchParams, Worker,
    document: {getElementById: id => nodes[id]},
    window: {
      location: {origin, href: `${origin}/examples/pyodide/`, search: ""},
      addEventListener: (type, handler) => { listeners[type] = handler; }
    }
  });
  assert(rendererLoaded);
  for (const type of ["init", "move"]) {
    worker.listeners.message({data: {
      type: "command", payload: JSON.stringify({type})
    }});
  }
  if (!early) {
    assert.strictEqual(commands.length, 0);
    ready();
  }
  assert.deepStrictEqual(commands.map(message => message.command.type), ["init", "move"]);
}

checkCallbacks(false);
checkCallbacks(true);
checkRendererStartup(true);
checkRendererStartup(false);
