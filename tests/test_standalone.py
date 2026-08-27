import ast
import contextlib
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from basthon import turtle
from basthon.turtle import _standalone


PROJECT_ROOT = Path(__file__).parents[1]
PEACE_COLORS = {
    "red3": "#cd0000",
    "orange": "#ffa500",
    "yellow": "#ffff00",
    "seagreen4": "#2e8b57",
    "orchid4": "#8b4789",
    "royalblue1": "#4876ff",
    "dodgerblue4": "#104e8b",
    "white": "#ffffff",
}


class FakeSession:
    def __init__(self):
        self.commands = []
        self.start_count = 0
        self.flush_count = 0
        self.wait_count = 0
        self.started = False
        self.event_handler = None

    def emit(self, command):
        if not self.started:
            self.started = True
            self.start_count += 1
        self.commands.append(command)

    def flush(self):
        self.flush_count += 1

    def set_event_handler(self, handler):
        self.event_handler = handler

    def wait_for_disconnect(self):
        self.wait_count += 1


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
        self.assertEqual(session.wait_count, 0)

    def test_mainloop_waits_when_browser_callbacks_are_registered(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            pen.ondrag(mock.Mock())
            turtle.mainloop()

        self.assertEqual(session.flush_count, 1)
        self.assertEqual(session.wait_count, 1)

    def test_drag_events_use_turtle_coordinates_and_shape_size(self):
        session = FakeSession()
        callback = mock.Mock()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            screen = turtle.Screen()
            screen.setworldcoordinates(-1, -0.3, 3, 1.3)
            pen = turtle.Turtle()
            session.commands.clear()
            pen.resizemode("user")
            pen.shapesize(3, 4, 5)
            pen.ondrag(callback)

        self.assertEqual(pen.resizemode(), "user")
        self.assertEqual(pen.shapesize(), (3, 4, 5))
        self.assertEqual(
            [command["type"] for command in session.commands], ["shape", "bind"]
        )
        x, y = screen._convert_coordinates(1.25, 0.75)
        session.event_handler(
            {
                "type": "event",
                "event": "drag",
                "turtle": pen._live_id,
                "x": x,
                "y": y,
            }
        )
        callback.assert_called_once_with(1.25, 0.75)

    def test_static_svg_output_still_works_without_standalone_extra(self):
        with mock.patch.object(_standalone, "create_session", return_value=None):
            pen = turtle.Turtle()
            pen.forward(100)
            turtle.done()
            output = pen.screen.svg()

        self.assertIn("<svg ", output)
        self.assertIn("<line ", output)
        self.assertIn("<animate ", output)

    def test_turtledemo_peace_colors_render_in_live_and_static_output(self):
        from turtledemo import peace

        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            result = peace.main()
            turtle.done()
            output = turtle.svg()

        self.assertEqual(result, "Done!")
        rendered_line_colors = {
            command["color"]
            for command in session.commands
            if command["type"] == "move" and command["drawing"]
        }
        self.assertLessEqual(set(PEACE_COLORS.values()), rendered_line_colors)
        for name, rendered in PEACE_COLORS.items():
            self.assertEqual(turtle._browser_color(name), rendered)
            self.assertIn(rendered, output)

    def test_turtledemo_yinyang_emits_incremental_live_filled_polygons(self):
        from turtledemo import yinyang

        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            result = yinyang.main()
            turtle.done()
            output = turtle.svg()

        polygons = [
            command for command in session.commands if command["type"] == "polygon"
        ]
        self.assertEqual(result, "Done!")
        self.assertEqual(len(polygons), 4)
        self.assertEqual(
            {command["fill"] for command in polygons}, {"black", "#ffffff"}
        )
        self.assertTrue(all(len(command["points"]) > 2 for command in polygons))
        for command in polygons:
            self.assertNotIn("svg", command)
            self.assertNotIn("scene", command)
        self.assertIn("<polygon ", output)

    def test_turtle_color_getters_preserve_tk_color_names(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            session.commands.clear()
            pen.color("SeaGreen4")
            pen.forward(10)

        self.assertEqual(pen.color(), ("SeaGreen4", "SeaGreen4"))
        self.assertEqual(session.commands[-1]["color"], "#2e8b57")

    def test_turtledemo_colormixer_handles_browser_drag_events(self):
        from turtledemo import colormixer

        session = FakeSession()
        warnings = io.StringIO()
        with (
            mock.patch.object(_standalone, "create_session", return_value=session),
            contextlib.redirect_stderr(warnings),
        ):
            result = colormixer.main()

        self.assertEqual(result, "EVENTLOOP")
        self.assertEqual(warnings.getvalue(), "")
        self.assertEqual(
            [command["type"] for command in session.commands].count("shape"), 3
        )
        self.assertEqual(
            [command["type"] for command in session.commands].count("bind"), 3
        )
        center_x, _ = colormixer.screen._convert_coordinates(1, 0.5)
        self.assertEqual(
            center_x + colormixer.screen.translate_canvas[0],
            colormixer.screen.width / 2,
        )

        x, y = colormixer.screen._convert_coordinates(0, 0.75)
        session.event_handler(
            {
                "type": "event",
                "event": "drag",
                "turtle": colormixer.red._live_id,
                "x": x,
                "y": y,
            }
        )

        self.assertEqual(colormixer.red.ycor(), 0.75)
        backgrounds = [
            command for command in session.commands if command["type"] == "background"
        ]
        self.assertEqual(backgrounds[-1]["color"], "#bf8080")


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
        self.assertIn('drawing.appendChild(polygon)', client)
        self.assertIn("const queue = []", client)
        self.assertIn(
            'socket.send(JSON.stringify({type: "event", event: "drag"', client
        )
        self.assertIn('state.node.addEventListener("pointermove"', client)
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
