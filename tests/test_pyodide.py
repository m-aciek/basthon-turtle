import json
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from basthon import turtle
from basthon.turtle import _notebook, _pyodide, _standalone


PROJECT_ROOT = Path(__file__).parents[1]


class FakeTransport:
    def __init__(self):
        self.payloads = []
        self.event_handler = None

    def emit(self, payload):
        self.payloads.append(payload)

    def set_event_handler(self, handler):
        self.event_handler = handler


class FakeProxy:
    def __init__(self, callback):
        self.callback = callback
        self.destroyed = False

    def __call__(self, payload):
        self.callback(payload)

    def destroy(self):
        self.destroyed = True


class PyodideSessionTests(unittest.TestCase):
    def test_commands_cross_the_transport_as_compact_json(self):
        transport = FakeTransport()
        session = _pyodide.PyodideSession(transport, proxy_factory=FakeProxy)

        session.emit({"type": "move", "to": [10, -20]})

        self.assertTrue(session.started)
        self.assertEqual(
            transport.payloads, ['{"type":"move","to":[10,-20]}']
        )
        self.assertIsInstance(transport.event_handler, FakeProxy)

    def test_browser_events_are_decoded_and_forwarded(self):
        transport = FakeTransport()
        session = _pyodide.PyodideSession(transport, proxy_factory=FakeProxy)
        events = []
        session.set_event_handler(events.append)
        session.emit({"type": "focus"})

        transport.event_handler(
            json.dumps(
                {"type": "event", "event": "drag", "x": 12.5, "y": -4}
            )
        )

        self.assertEqual(
            events,
            [{"type": "event", "event": "drag", "x": 12.5, "y": -4}],
        )

    def test_close_releases_the_python_proxy(self):
        transport = FakeTransport()
        session = _pyodide.PyodideSession(transport, proxy_factory=FakeProxy)
        session.emit({"type": "focus"})
        proxy = transport.event_handler

        session.close()
        session.close()

        self.assertIsNone(transport.event_handler)
        self.assertTrue(proxy.destroyed)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            session.emit({"type": "focus"})

    def test_factory_requires_emscripten_and_registered_transport(self):
        transport = FakeTransport()
        with (
            mock.patch.object(_pyodide.sys, "platform", "emscripten"),
            mock.patch.object(_pyodide, "_get_transport", return_value=transport),
        ):
            session = _pyodide.create_session()

        self.assertIsInstance(session, _pyodide.PyodideSession)

        with mock.patch.object(_pyodide.sys, "platform", "darwin"):
            self.assertIsNone(_pyodide.create_session())
        with (
            mock.patch.object(_pyodide.sys, "platform", "emscripten"),
            mock.patch.object(_pyodide, "_get_transport", return_value=None),
        ):
            self.assertIsNone(_pyodide.create_session())


class PyodideBackendSelectionTests(unittest.TestCase):
    def setUp(self):
        self._reset_turtle()

    def tearDown(self):
        self._reset_turtle()

    @staticmethod
    def _reset_turtle():
        screen = turtle.Singleton._instances.pop(turtle.Screen, None)
        if screen is not None and screen._standalone_session is not None:
            close = getattr(screen._standalone_session, "close", None)
            if close is not None:
                close()
        turtle.Turtle._pen = None
        turtle.Turtle.screen = None

    def test_pyodide_transport_precedes_standalone_transport(self):
        session = mock.Mock()
        session.started = True
        with (
            mock.patch.object(_notebook, "create_session", return_value=None),
            mock.patch.object(_pyodide, "create_session", return_value=session),
            mock.patch.object(_standalone, "create_session") as standalone,
        ):
            turtle.Turtle()

        standalone.assert_not_called()
        self.assertGreaterEqual(session.emit.call_count, 1)


class PyodideBrowserAssetsTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is required")
    def test_browser_transport_regressions(self):
        result = subprocess.run(
            [
                shutil.which("node"),
                str(PROJECT_ROOT / "tests" / "pyodide_browser.cjs"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_worker_registers_transport_before_runtime_install(self):
        worker = (
            PROJECT_ROOT / "examples" / "pyodide" / "worker.mjs"
        ).read_text()

        register = worker.index(
            'registerJsModule("basthon_turtle_transport", transport)'
        )
        checkout = worker.index("await loadCheckoutSources(pyodide)")
        install = worker.index("await installPackage(pyodide, packageSpec)")
        self.assertLess(register, checkout)
        self.assertLess(register, install)
        self.assertIn(
            'const SOURCE_ROOT = "/tmp/basthon-turtle-example"', worker
        )
        for source in (PROJECT_ROOT / "basthon" / "turtle").glob("*.py"):
            self.assertIn(f'"{source.name}"', worker)
        self.assertIn('summary: "Could not initialize', worker)
        page = (
            PROJECT_ROOT / "examples" / "pyodide" / "index.html"
        ).read_text()
        self.assertIn(
            'const initialization = {type: "initialize"};', page
        )
        self.assertIn('message.type === "status"', page)
        self.assertIn('"Initialization failed"', page)
        self.assertIn(
            'run.disabled = message.phase === "initialize";', page
        )
        self.assertIn("new URL", page)
        self.assertIn('self.postMessage({type: "command", payload})', worker)
        self.assertIn("pyodide.runPythonAsync(message.code)", worker)

    def test_example_connects_worker_to_parent_renderer(self):
        page = (
            PROJECT_ROOT / "examples" / "pyodide" / "index.html"
        ).read_text()

        self.assertIn('new Worker(workerURL, {type: "module"})', page)
        self.assertIn("standalone.html?transport=parent", page)
        self.assertIn('worker.postMessage({type: "event"', page)
        self.assertIn('source: marker, type: "command", command', page)


if __name__ == "__main__":
    unittest.main()
