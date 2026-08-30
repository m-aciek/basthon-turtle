import ast
import json
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
    def test_worker_registers_transport_before_runtime_install(self):
        worker = (
            PROJECT_ROOT / "examples" / "pyodide" / "worker.mjs"
        ).read_text()

        register = worker.index(
            'registerJsModule("basthon_turtle_transport", transport)'
        )
        install = worker.index("await micropip.install(packageSpec)")
        self.assertLess(register, install)
        page = (
            PROJECT_ROOT / "examples" / "pyodide" / "index.html"
        ).read_text()
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

    def test_sdist_includes_all_browser_example_files(self):
        manifest = (PROJECT_ROOT / "MANIFEST.in").read_text()
        self.assertIn("recursive-include examples *.html *.mjs *.py", manifest)

    def test_python_backend_is_part_of_the_discovered_package(self):
        tree = ast.parse((PROJECT_ROOT / "setup.py").read_text())
        setup_call = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setup"
        )
        keywords = {keyword.arg: keyword.value for keyword in setup_call.keywords}
        self.assertIn("packages", keywords)
        backend = PROJECT_ROOT / "basthon" / "turtle" / "_pyodide.py"
        self.assertTrue(backend.is_file())


if __name__ == "__main__":
    unittest.main()
