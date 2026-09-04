"use strict";

const ns = "http://www.w3.org/2000/svg";

function render({model, el, signal}) {
  el.classList.add("basthon-turtle-widget");
  const screen = element("svg", {
    role: "img", "aria-label": "Python turtle graphics", tabindex: 0
  });
  const drawing = element("g");
  const writing = element("g");
  const turtleLayer = element("g");
  screen.append(drawing, writing, turtleLayer);
  el.replaceChildren(screen);

  const turtles = new Map();
  const queue = [];
  const keyBindings = {keypress: new Set(), keyrelease: new Set()};
  let consuming = false;
  let applied = 0;
  let translate = [0, 0];
  let logicalWidth = 0;
  let logicalHeight = 0;

  function resizeScreen() {
    const viewportWidth = el.clientWidth;
    const viewportHeight = el.clientHeight;
    if (!logicalWidth || !logicalHeight || !viewportWidth || !viewportHeight) return;
    const x = (logicalWidth - viewportWidth) / 2;
    const y = (logicalHeight - viewportHeight) / 2;
    screen.setAttribute("viewBox", `${x} ${y} ${viewportWidth} ${viewportHeight}`);
  }

  const resizeObserver = new ResizeObserver(resizeScreen);
  resizeObserver.observe(el);

  function element(tag, attributes = {}) {
    const node = document.createElementNS(ns, tag);
    for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
    return node;
  }

  function turtleKey(event) {
    const names = {
      " ": "space", ArrowUp: "Up", ArrowDown: "Down",
      ArrowLeft: "Left", ArrowRight: "Right", Enter: "Return",
      Backspace: "BackSpace", PageUp: "Prior", PageDown: "Next"
    };
    return names[event.key] || event.key;
  }

  function sendKeyEvent(eventName, event) {
    const key = turtleKey(event);
    const bindings = keyBindings[eventName];
    const wildcard = eventName === "keypress" && bindings.has(null);
    if (!bindings.has(key) && !wildcard) return;
    model.send({type: "event", event: eventName, key});
    event.preventDefault();
  }

  screen.addEventListener("keydown", event => sendKeyEvent("keypress", event));
  screen.addEventListener("keyup", event => sendKeyEvent("keyrelease", event));
  screen.addEventListener("pointerdown", () => screen.focus());

  function shapeElement(geometry) {
    let node;
    if (geometry.kind === "polygon") {
      node = element("polygon", {
        points: geometry.points.map(point => point.join(",")).join(" ")
      });
    } else if (geometry.kind === "rectangle") {
      node = element("rect", {
        x: -geometry.width / 2, y: -geometry.height / 2,
        width: geometry.width, height: geometry.height
      });
    } else if (geometry.kind === "circle") {
      node = element("circle", {cx: 0, cy: 0, r: geometry.radius});
    } else {
      throw new Error(`Unsupported turtle shape: ${geometry.kind}`);
    }
    node.setAttribute("vector-effect", "non-scaling-stroke");
    return node;
  }

  function replaceTurtleShape(state, geometry) {
    state.shape = shapeElement(geometry);
    state.node.replaceChildren(state.shape);
  }

  function turtle(id) {
    if (!turtles.has(id)) {
      const node = element("g", {
        stroke: "black", fill: "black", "stroke-width": 1, opacity: 0
      });
      const state = {
        node, shape: null, x: 0, y: 0, angle: -90,
        stretchWidth: 1, stretchLength: 1, outline: 1,
        dragEnabled: false, dragButton: 1, dragging: false
      };
      turtles.set(id, state);
      turtleLayer.appendChild(node);
      replaceTurtleShape(state, {
        kind: "polygon",
        points: [[0,16],[-2,14],[-1,10],[-4,7],[-7,9],[-9,8],[-6,5],[-7,1],[-5,-3],[-8,-6],[-6,-8],[-4,-5],[0,-7],[4,-5],[6,-8],[8,-6],[5,-3],[7,1],[6,5],[9,8],[7,9],[4,7],[1,10],[2,14]]
      });
      installTurtleEvents(id, state);
      positionTurtle(state);
    }
    return turtles.get(id);
  }

  function positionTurtle(state) {
    state.node.setAttribute(
      "transform",
      `translate(${state.x} ${state.y}) rotate(${state.angle}) ` +
        `scale(${state.stretchWidth} ${state.stretchLength})`
    );
  }

  function pointerPosition(event) {
    const point = screen.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    const local = point.matrixTransform(screen.getScreenCTM().inverse());
    return [local.x - translate[0], local.y - translate[1]];
  }

  function sendDragEvent(id, event) {
    const [x, y] = pointerPosition(event);
    model.send({type: "event", event: "drag", turtle: id, x, y});
  }

  function installTurtleEvents(id, state) {
    state.node.style.touchAction = "none";
    state.node.addEventListener("pointerdown", event => {
      if (!state.dragEnabled || event.button + 1 !== state.dragButton) return;
      state.dragging = true;
      state.node.setPointerCapture(event.pointerId);
      state.node.style.cursor = "grabbing";
      event.preventDefault();
    });
    state.node.addEventListener("pointermove", event => {
      if (!state.dragging) return;
      sendDragEvent(id, event);
      event.preventDefault();
    });
    for (const name of ["pointerup", "pointercancel"]) {
      state.node.addEventListener(name, event => {
        if (!state.dragging) return;
        state.dragging = false;
        state.node.style.cursor = state.dragEnabled ? "grab" : "default";
        if (state.node.hasPointerCapture(event.pointerId)) {
          state.node.releasePointerCapture(event.pointerId);
        }
      });
    }
  }

  function animate(duration, update) {
    if (duration <= 1) { update(1); return Promise.resolve(); }
    return new Promise(resolve => {
      const start = performance.now();
      function frame(now) {
        const progress = Math.min(1, (now - start) / duration);
        update(progress);
        if (progress < 1) requestAnimationFrame(frame); else resolve();
      }
      requestAnimationFrame(frame);
    });
  }

  async function apply(command, instant) {
    if (command.type === "init") {
      logicalWidth = command.width;
      logicalHeight = command.height;
      screen.setAttribute("width", command.width);
      screen.setAttribute("height", command.height);
      resizeScreen();
      screen.style.backgroundColor = command.background;
      translate = command.translate;
      for (const layer of [drawing, writing, turtleLayer]) layer.replaceChildren();
      for (const layer of [drawing, writing, turtleLayer]) {
        layer.setAttribute("transform", `translate(${translate[0]} ${translate[1]})`);
      }
      turtles.clear();
      return;
    }

    if (command.type === "move") {
      const state = turtle(command.turtle);
      let line = null;
      if (command.drawing) {
        line = element("line", {
          x1: command.from[0], y1: command.from[1],
          x2: command.from[0], y2: command.from[1],
          stroke: command.color, "stroke-width": command.width,
          "stroke-linecap": command.width > 2 ? "round" : "butt",
          "data-turtle": command.turtle
        });
        drawing.appendChild(line);
      }
      const duration = instant ? 0 : command.duration;
      await animate(duration, progress => {
        const x = command.from[0] + (command.to[0] - command.from[0]) * progress;
        const y = command.from[1] + (command.to[1] - command.from[1]) * progress;
        if (line) { line.setAttribute("x2", x); line.setAttribute("y2", y); }
        state.x = x; state.y = y; positionTurtle(state);
      });
      return;
    }

    if (command.type === "polygon") {
      drawing.appendChild(element("polygon", {
        points: command.points.map(point => point.join(",")).join(" "),
        fill: command.fill === null ? "none" : command.fill,
        stroke: command.outline === null ? "none" : command.outline,
        "stroke-width": command.width, "data-turtle": command.turtle
      }));
      return;
    }

    if (command.type === "rotate") {
      const state = turtle(command.turtle);
      const duration = instant ? 0 : command.duration;
      await animate(duration, progress => {
        state.angle = command.from + (command.to - command.from) * progress;
        positionTurtle(state);
      });
      return;
    }

    if (command.type === "visibility") {
      const state = turtle(command.turtle);
      state.x = command.x; state.y = command.y; state.angle = command.angle;
      state.node.setAttribute("opacity", command.visible ? 1 : 0);
      positionTurtle(state);
      return;
    }

    if (command.type === "pen") {
      const state = turtle(command.turtle);
      state.node.setAttribute("stroke", command.pencolor);
      state.node.setAttribute("fill", command.fillcolor);
      return;
    }

    if (command.type === "turtle_shape") {
      replaceTurtleShape(turtle(command.turtle), command.geometry);
      return;
    }

    if (command.type === "shape") {
      const state = turtle(command.turtle);
      state.stretchWidth = command.stretch_width;
      state.stretchLength = command.stretch_length;
      state.outline = command.outline;
      state.node.setAttribute("stroke-width", state.outline);
      positionTurtle(state);
      return;
    }

    if (command.type === "bind" && command.event === "drag") {
      const state = turtle(command.turtle);
      state.dragEnabled = command.enabled;
      state.dragButton = command.button;
      state.dragging = false;
      state.node.style.cursor = state.dragEnabled ? "grab" : "default";
      return;
    }

    if (command.type === "bind" && command.target === "screen") {
      const bindings = keyBindings[command.event];
      if (command.enabled) bindings.add(command.key); else bindings.delete(command.key);
      return;
    }

    if (command.type === "focus") { screen.focus(); return; }

    if (command.type === "clear") {
      for (const layer of [drawing, writing]) {
        for (const node of [...layer.children]) {
          if (node.dataset.turtle === command.turtle) node.remove();
        }
      }
      return;
    }

    if (command.type === "background") {
      screen.style.backgroundColor = command.color;
      return;
    }

    if (command.type === "write") {
      const node = element("text", {
        x: command.position[0], y: command.position[1], fill: command.color,
        "font-family": command.font[0], "font-size": command.font[1],
        "font-style": command.font[2], "text-anchor": command.anchor,
        "data-turtle": command.turtle
      });
      node.textContent = command.text;
      writing.appendChild(node);
    }
  }

  async function consume() {
    if (consuming) return;
    consuming = true;
    while (queue.length) {
      const item = queue.shift();
      await apply(item.command, item.instant);
    }
    consuming = false;
    model.send({type: "rendered", count: applied});
  }

  function enqueue(commands, instant) {
    for (const command of commands) queue.push({command, instant});
    consume();
  }

  function historyChanged() {
    const history = model.get("history") || [];
    if (history.length < applied) {
      applied = 0;
      queue.length = 0;
    }
    const commands = history.slice(applied);
    applied = history.length;
    enqueue(commands, false);
  }

  const history = model.get("history") || [];
  const animationStart = Math.min(model.get("animation_start") || 0, history.length);
  applied = history.length;
  for (const command of history.slice(0, animationStart)) {
    queue.push({command, instant: true});
  }
  for (const command of history.slice(animationStart)) {
    queue.push({command, instant: false});
  }
  consume();
  model.on("change:history", historyChanged);

  if (signal) {
    signal.addEventListener("abort", () => {
      resizeObserver.disconnect();
      model.off("change:history", historyChanged);
    });
  }
}

export default {render};
