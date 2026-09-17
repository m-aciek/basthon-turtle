import json
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from basthon.turtle import _standalone


PROJECT_ROOT = Path(__file__).parents[1]


class StandaloneSessionTests(unittest.TestCase):
    def test_received_browser_events_are_dispatched(self):
        session = _standalone.StandaloneSession()
        handler = mock.Mock()
        connection = mock.Mock()
        connection.recv.side_effect = [
            json.dumps(
                {
                    "type": "event",
                    "event": "drag",
                    "turtle": "turtle-id",
                    "x": 10,
                    "y": 20,
                }
            ),
            None,
        ]
        session.set_event_handler(handler)

        session._receive_events(connection)

        handler.assert_called_once_with(
            {
                "type": "event",
                "event": "drag",
                "turtle": "turtle-id",
                "x": 10,
                "y": 20,
            }
        )

    def test_commands_wait_for_connection_and_are_delivered_in_order(self):
        session = _standalone.StandaloneSession()
        with mock.patch.object(session, "start"):
            session.emit({"type": "move", "to": [100, 0]})
            session.emit({"type": "rotate", "to": 90})
            session.emit({"type": "move", "to": [100, -50]})

        self.assertEqual(session.pending_count, 3)
        connection = mock.Mock()
        session._drain_pending(connection)

        self.assertEqual(
            [
                json.loads(call.args[0])["type"]
                for call in connection.send.call_args_list
            ],
            ["move", "rotate", "move"],
        )
        self.assertEqual(session.pending_count, 0)

    def test_server_socket_is_bound_only_to_loopback(self):
        sock = _standalone.StandaloneSession._create_socket()
        self.addCleanup(sock.close)

        host, port = sock.getsockname()
        self.assertEqual(host, "127.0.0.1")
        self.assertGreater(port, 0)

    def test_start_is_idempotent_and_opens_one_browser_page(self):
        browser_open = mock.Mock()
        session = _standalone.StandaloneSession(browser_open=browser_open)
        fake_socket = mock.Mock()
        fake_socket.getsockname.return_value = ("127.0.0.1", 43210)

        with (
            mock.patch.object(session, "_create_socket", return_value=fake_socket),
            mock.patch.object(session, "_serve"),
            mock.patch("basthon.turtle._standalone.threading.Thread") as thread,
            mock.patch("basthon.turtle._standalone.atexit.register"),
        ):
            session.start()
            session.start()

        self.assertEqual(thread.call_count, 2)
        self.assertEqual(
            thread.call_args_list[1].kwargs,
            {
                "target": browser_open,
                "args": ("http://127.0.0.1:43210/",),
                "name": "basthon-turtle-browser",
                "daemon": True,
            },
        )
        browser_thread = thread.call_args_list[1].return_value
        browser_thread.start.assert_called_once_with()
        self.assertEqual(session.port, 43210)

    def test_renderer_extras_separate_portable_and_sidecar_dependencies(self):
        config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
        project = config["project"]

        self.assertFalse(project.get("dependencies"))
        extras = project["optional-dependencies"]
        self.assertEqual(
            extras,
            {
                "notebook": ["anywidget>=0.9"],
                "sidecar": ["anywidget>=0.9", "sidecar>=0.8"],
                "standalone": ["websockets>=14"],
            },
        )

    def test_notebook_client_rehydrates_history_and_animates_only_the_suffix(self):
        path = PROJECT_ROOT / "basthon" / "turtle" / "notebook.mjs"
        client = path.read_text()

        self.assertIn('model.get("history")', client)
        self.assertIn('model.get("animation_start")', client)
        self.assertIn("history.slice(0, animationStart)", client)
        self.assertIn("queue.push({command, instant: true})", client)
        self.assertIn("history.slice(animationStart)", client)
        self.assertIn("queue.push({command, instant: false})", client)
        self.assertIn('model.on("change:history", historyChanged)', client)
        self.assertIn('model.send({type: "event", event: "drag"', client)
        self.assertIn('model.send({type: "rendered", count: applied})', client)

    def test_browser_client_mutates_a_persistent_svg(self):
        path = PROJECT_ROOT / "basthon" / "turtle" / "standalone.html"
        client = path.read_text()

        self.assertIn('drawing.appendChild(line)', client)
        self.assertIn('drawing.appendChild(polygon)', client)
        self.assertIn("const queue = []", client)
        self.assertIn(
            'sendEvent({type: "event", event: "drag"', client
        )
        self.assertIn('state.node.addEventListener("pointermove"', client)
        self.assertIn('node = element("rect"', client)
        self.assertIn('if (command.type === "turtle_shape")', client)
        self.assertIn(
            'screen.addEventListener("keydown", event => sendKeyEvent', client
        )
        self.assertIn(
            'screen.addEventListener("keyup", event => sendKeyEvent', client
        )
        self.assertIn('message.type !== "command"', client)
        self.assertIn('{source: "basthon-turtle", type: "ready"}', client)
        self.assertIn('sendEvent({type: "event", event: "drag"', client)
        self.assertIn('ArrowUp: "Up"', client)
        self.assertIn('" ": "space"', client)
        self.assertIn('if (command.type === "clear")', client)
        self.assertIn('"data-turtle": command.turtle', client)
        self.assertNotIn("document.body.innerHTML", client)

    def test_browser_client_fills_the_viewport_without_scaling_the_drawing(self):
        path = PROJECT_ROOT / "basthon" / "turtle" / "standalone.html"
        client = path.read_text()

        self.assertIn("width: 100vw; height: 100vh", client)
        self.assertIn(
            'window.addEventListener("resize", resizeScreenToViewport)', client
        )
        self.assertIn("(logicalWidth - viewportWidth) / 2", client)
        self.assertIn("(logicalHeight - viewportHeight) / 2", client)
        self.assertIn(
            '`${x} ${y} ${viewportWidth} ${viewportHeight}`',
            client,
        )


if __name__ == "__main__":
    unittest.main()
