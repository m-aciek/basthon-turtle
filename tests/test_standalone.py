import ast
import json
import unittest
from pathlib import Path
from unittest import mock

from basthon import turtle
from basthon.turtle import _standalone


PROJECT_ROOT = Path(__file__).parents[1]


class FakeSession:
    def __init__(self):
        self.commands = []
        self.start_count = 0
        self.flush_count = 0
        self.started = False

    def emit(self, command):
        if not self.started:
            self.started = True
            self.start_count += 1
        self.commands.append(command)

    def flush(self):
        self.flush_count += 1


class LiveRenderingTests(unittest.TestCase):
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

    def test_import_and_screen_construction_do_not_start_standalone(self):
        with mock.patch.object(_standalone, "create_session") as create_session:
            turtle.Screen()

        create_session.assert_not_called()

    def test_first_operation_starts_one_session_and_later_operations_reuse_it(self):
        session = FakeSession()
        with mock.patch.object(
            _standalone, "create_session", return_value=session
        ) as factory:
            pen = turtle.Turtle()
            self.assertEqual(session.start_count, 1)
            self.assertEqual(session.commands[0]["type"], "init")
            session.commands.clear()

            pen.forward(100)
            pen.left(90)
            pen.forward(50)

        factory.assert_called_once_with()
        self.assertEqual(
            [command["type"] for command in session.commands],
            ["move", "rotate", "move"],
        )

    def test_protocol_contains_only_new_incremental_operations(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            session.commands.clear()
            pen.forward(100)
            pen.right(90)
            pen.pencolor("red")
            pen.forward(50)

        self.assertEqual(
            [command["type"] for command in session.commands],
            ["move", "rotate", "pen", "move"],
        )
        first, _, pen_command, last = session.commands
        self.assertEqual(first["from"], [0.0, -0.0])
        self.assertEqual(first["to"], [100.0, -0.0])
        self.assertEqual(last["color"], "red")
        self.assertEqual(pen_command["pencolor"], "red")
        for command in session.commands:
            self.assertNotIn("svg", command)
            self.assertNotIn("scene", command)

    def test_supported_style_visibility_background_and_write_commands(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            session.commands.clear()
            pen.penup()
            pen.pendown()
            pen.pensize(4)
            pen.hideturtle()
            pen.showturtle()
            pen.screen.bgcolor("navy")
            pen.write("hello")

        types = [command["type"] for command in session.commands]
        self.assertEqual(types[:3], ["pen", "pen", "pen"])
        self.assertEqual(types.count("visibility"), 2)
        self.assertIn("background", types)
        self.assertIn("write", types)

    def test_backward_goto_and_penup_use_incremental_move_commands(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            session.commands.clear()
            pen.backward(20)
            pen.goto(10, 15)
            pen.penup()
            pen.goto(30, 40)

        moves = [command for command in session.commands if command["type"] == "move"]
        self.assertEqual(len(moves), 3)
        self.assertTrue(moves[0]["drawing"])
        self.assertTrue(moves[1]["drawing"])
        self.assertFalse(moves[2]["drawing"])

    def test_done_is_not_the_start_trigger_and_only_flushes_existing_session(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            self.assertTrue(session.commands)
            turtle.done()

        self.assertEqual(session.start_count, 1)
        self.assertEqual(session.flush_count, 1)

    def test_static_svg_output_still_works_without_standalone_extra(self):
        with mock.patch.object(_standalone, "create_session", return_value=None):
            pen = turtle.Turtle()
            pen.forward(100)
            turtle.done()
            output = pen.screen.svg()

        self.assertIn("<svg ", output)
        self.assertIn("<line ", output)
        self.assertIn("<animate ", output)


class StandaloneSessionTests(unittest.TestCase):
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

    def test_base_package_has_only_an_optional_websocket_dependency(self):
        tree = ast.parse((PROJECT_ROOT / "setup.py").read_text())
        setup_call = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setup"
        )
        keywords = {keyword.arg: keyword.value for keyword in setup_call.keywords}

        self.assertNotIn("install_requires", keywords)
        extras = ast.literal_eval(keywords["extras_require"])
        self.assertEqual(extras, {"standalone": ["websockets>=14"]})

    def test_browser_client_mutates_a_persistent_svg(self):
        path = PROJECT_ROOT / "basthon" / "turtle" / "standalone.html"
        client = path.read_text()

        self.assertIn('drawing.appendChild(line)', client)
        self.assertIn("const queue = []", client)
        self.assertNotIn("document.body.innerHTML", client)


if __name__ == "__main__":
    unittest.main()
