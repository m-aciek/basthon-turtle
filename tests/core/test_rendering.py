import contextlib
import io
import math
import unittest
import warnings
import xml.etree.ElementTree as ET
from unittest import mock

from basthon import turtle
from basthon.turtle import _notebook, _pyodide, _standalone


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

    def test_missing_standalone_dependency_warns_once_and_preserves_svg(self):
        with (
            mock.patch.object(_notebook, "create_session", return_value=None),
            mock.patch.object(_notebook, "is_notebook", return_value=False),
            mock.patch.object(_pyodide, "create_session", return_value=None),
            mock.patch.object(
                _standalone.importlib.util, "find_spec", return_value=None
            ),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            screen = turtle.Screen()
            self.assertEqual(caught, [])
            screen.animation("off")
            pen = turtle.Turtle()
            pen.forward(100)
            pen.left(90)
            pen.forward(50)
            turtle.done()
            svg = ET.fromstring(screen.svg())

        self.assertEqual(len(caught), 1)
        self.assertIn("basthon-turtle[standalone]", str(caught[0].message))
        lines = svg.findall(".//{http://www.w3.org/2000/svg}line")
        self.assertTrue(any(line.get("x2") == "100" for line in lines))

    def test_installing_standalone_dependency_after_warning_enables_renderer(self):
        session = FakeSession()
        with (
            mock.patch.object(_notebook, "create_session", return_value=None),
            mock.patch.object(_notebook, "is_notebook", return_value=False),
            mock.patch.object(_pyodide, "create_session", return_value=None),
            mock.patch.object(
                _standalone, "create_session", return_value=None
            ) as factory,
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            pen = turtle.Turtle()
            factory.return_value = session
            pen.forward(10)

        self.assertEqual(len(caught), 1)
        self.assertEqual(session.start_count, 1)
        self.assertEqual(session.commands[0]["type"], "init")

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

    def test_svg_and_live_rotations_preserve_wraparound_and_full_turns(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            pen.left(350)
            session.commands.clear()
            start = pen._old_heading
            for method, angle, delta, heading in (
                ("left", 20, -20, 10),
                ("right", 20, 20, 350),
                ("left", 720, -720, 350),
                ("right", 1080, 1080, 350),
                ("left", -20, 20, 330),
                ("setheading", 360010, -40, 10),
            ):
                with self.subTest(method=method, angle=angle):
                    getattr(pen, method)(angle)
                    command = session.commands[-1]
                    self.assertEqual(command["type"], "rotate")
                    self.assertAlmostEqual(command["from"], start)
                    self.assertAlmostEqual(command["to"], start + delta)
                    self.assertGreater(command["duration"], 0)
                    self.assertAlmostEqual(pen.heading(), heading)
                    root = ET.fromstring(str(pen.svg))
                    animation = root.findall("animateTransform")[-1]
                    self.assertAlmostEqual(
                        float(animation.attrib["from"].split(",")[0]), start
                    )
                    self.assertAlmostEqual(
                        float(animation.attrib["to"].split(",")[0]), start + delta
                    )
                    start += delta

    def test_rotation_units_and_hidden_turns(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            pen.radians()
            pen.left(4 * math.pi)
            self.assertAlmostEqual(
                session.commands[-1]["to"] - session.commands[-1]["from"], -720
            )
            pen.seth(math.pi / 2)
            self.assertAlmostEqual(pen.heading(), math.pi / 2)
            pen.hideturtle()
            session.commands.clear()
            pen.right(6 * math.pi)
            self.assertEqual(session.commands, [])
            pen.showturtle()
            visibility = next(
                c for c in session.commands if c["type"] == "visibility"
            )
            self.assertAlmostEqual(visibility["angle"], 180)
            pen.forward(10)
            self.assertAlmostEqual(pen.xcor(), 0)
            self.assertAlmostEqual(pen.ycor(), 10)

    def test_logo_initial_orientation_and_reset(self):
        session = FakeSession()
        with (
            mock.patch.dict(turtle._CFG, {"mode": "logo"}),
            mock.patch.object(_standalone, "create_session", return_value=session),
        ):
            pen = turtle.Turtle()
            self.assertEqual(pen.heading(), 0)
            self.assertEqual(session.commands[-1]["to"], -180)
            pen.forward(10)
            self.assertEqual(pen.pos(), (0, 10))
            pen.right(90)
            self.assertEqual(pen.heading(), 90)
            self.assertEqual(session.commands[-1]["to"], -90)
            pen.forward(5)
            self.assertAlmostEqual(pen.xcor(), 5)
            pen.reset()
            self.assertEqual(pen.pos(), (0, 0))
            self.assertEqual(pen.heading(), 0)
            rotations = [c for c in session.commands if c["type"] == "rotate"]
            self.assertEqual(rotations[-1]["to"], -180)

    def test_reversed_world_axis_changes_rendering_not_navigation(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            screen = turtle.Screen()
            screen.setworldcoordinates(-100, 100, 100, -100)
            pen = turtle.Turtle()
            pen.left(90)
            self.assertEqual(session.commands[-1]["to"], 0)
            pen.forward(10)
            self.assertAlmostEqual(pen.xcor(), 0)
            self.assertAlmostEqual(pen.ycor(), 10)
            self.assertGreater(session.commands[-1]["to"][1], 0)

    def test_world_angle_units_preserve_home_and_svg_orientation(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            screen = turtle.Screen()
            screen.setworldcoordinates(-100, -100, 100, 100)
            pen = turtle.Turtle()
            for units, args in (
                ("degrees", ()), ("degrees", (400,)), ("radians", ())
            ):
                with self.subTest(units=units, args=args):
                    getattr(pen, units)(*args)
                    self.assertEqual(pen.heading(), 0)
                    pen.home()
                    pen.forward(10)
                    self.assertAlmostEqual(pen.xcor(), 10)
                    self.assertAlmostEqual(pen.ycor(), 0)
                    rotation = next(
                        c for c in reversed(session.commands)
                        if c["type"] == "rotate"
                    )
                    self.assertAlmostEqual(rotation["to"], -90)
                    root = ET.fromstring(str(pen.svg))
                    animation = root.findall("animateTransform")[-1]
                    self.assertAlmostEqual(
                        float(animation.attrib["to"].split(",")[0]), -90
                    )

    def test_instant_rotation_and_clone_keep_vector_state(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            pen.screen.animation("off")
            pen.goto(turtle.Vec2D(3, 4))
            pen.left(450)
            root = ET.fromstring(str(pen.svg))
            self.assertIn("rotate(-540.0, 0, 0)", root.attrib["transform"])
            clone = pen.clone()
            self.assertIsInstance(clone.pos(), turtle.Vec2D)
            self.assertEqual(clone.pos(), pen.pos())
            self.assertEqual(clone.heading(), pen.heading())
            clone.forward(10)
            self.assertAlmostEqual(clone.xcor(), 3)
            self.assertAlmostEqual(clone.ycor(), 14)
            self.assertEqual(pen.pos(), (3, 4))

    def test_forward_and_backward_have_equal_animation_duration(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle()
            session.commands.clear()
            pen.forward(100)
            pen.back(100)
            pen.forward(-100)
        durations = [c["duration"] for c in session.commands]
        self.assertGreater(durations[0], 1)
        self.assertEqual(durations, [durations[0]] * 3)

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

    def test_clear_is_scoped_to_one_turtle_and_preserves_state(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            first = turtle.Turtle()
            first.goto(25, 30)
            first.write("first")
            second = turtle.Turtle()
            second.forward(40)
            first_state = (first.pos(), first.heading(), first.pen())
            first_items = list(first._drawing_items)
            second_items = list(second._drawing_items)
            first.clear()

        self.assertEqual((first.pos(), first.heading(), first.pen()), first_state)
        self.assertEqual(first._drawing_items, [])
        self.assertEqual(second._drawing_items, second_items)
        self.assertTrue(first_items)
        self.assertTrue(all(item in parent._children for parent, item in first_items))
        self.assertTrue(
            all(item._children[-1]._tag == "set" for _parent, item in first_items)
        )
        self.assertTrue(all(item in parent._children for parent, item in second_items))
        self.assertEqual(
            session.commands[-1], {"type": "clear", "turtle": first._live_id}
        )
        writes = [command for command in session.commands if command["type"] == "write"]
        self.assertEqual(writes[-1]["turtle"], first._live_id)

    def test_clear_removes_static_items_when_animation_is_off(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            screen = turtle.Screen()
            screen.animation("off")
            first = turtle.Turtle()
            first.forward(20)
            first.write("remove me")
            second = turtle.Turtle()
            second.forward(20)
            first_items = list(first._drawing_items)
            second_items = list(second._drawing_items)
            first.clear()

        self.assertTrue(
            all(item not in parent._children for parent, item in first_items)
        )
        self.assertTrue(all(item in parent._children for parent, item in second_items))

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

    def test_screen_key_press_release_focus_and_unbinding(self):
        session = FakeSession()
        up = mock.Mock()
        any_key = mock.Mock()
        space = mock.Mock()
        escape = mock.Mock()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            screen = turtle.Screen()
            screen.onkeypress(up, "Up")
            screen.onkeypress(any_key)
            screen.onkey(space, "space")
            screen.onkeyrelease(escape, "Escape")
            screen.listen()

        self.assertEqual(
            [command["type"] for command in session.commands],
            ["init", "bind", "bind", "bind", "bind", "focus"],
        )
        self.assertEqual(
            [
                (command["event"], command["key"], command["enabled"])
                for command in session.commands
                if command["type"] == "bind"
            ],
            [
                ("keypress", "Up", True),
                ("keypress", None, True),
                ("keyrelease", "space", True),
                ("keyrelease", "Escape", True),
            ],
        )

        session.event_handler(
            {"type": "event", "event": "keypress", "key": "Up"}
        )
        up.assert_called_once_with()
        any_key.assert_not_called()
        session.event_handler(
            {"type": "event", "event": "keypress", "key": "x"}
        )
        any_key.assert_called_once_with()
        session.event_handler(
            {"type": "event", "event": "keyrelease", "key": "space"}
        )
        session.event_handler(
            {"type": "event", "event": "keyrelease", "key": "Escape"}
        )
        space.assert_called_once_with()
        escape.assert_called_once_with()

        screen.onkey(None, "space")
        self.assertFalse(session.commands[-1]["enabled"])
        session.event_handler(
            {"type": "event", "event": "keyrelease", "key": "space"}
        )
        space.assert_called_once_with()

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

    def test_shape_changes_update_live_geometry_and_public_state(self):
        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            pen = turtle.Turtle(visible=False)
            session.commands.clear()
            pen.shape("circle")

        self.assertEqual(pen.shape(), "circle")
        self.assertEqual(
            session.commands,
            [
                {
                    "type": "turtle_shape",
                    "turtle": pen._live_id,
                    "name": "circle",
                    "geometry": {"kind": "circle", "radius": 10},
                }
            ],
        )

    def test_turtledemo_sorting_blocks_use_live_rectangles(self):
        from turtledemo.sorting_animate import Block

        session = FakeSession()
        with mock.patch.object(_standalone, "create_session", return_value=session):
            block = Block(4)

        shape_commands = [
            command
            for command in session.commands
            if command["type"] == "turtle_shape"
            and command["turtle"] == block._live_id
        ]
        self.assertEqual(
            shape_commands,
            [
                {
                    "type": "turtle_shape",
                    "turtle": block._live_id,
                    "name": "square",
                    "geometry": {
                        "kind": "rectangle",
                        "width": 20,
                        "height": 20,
                    },
                }
            ],
        )
        self.assertEqual(block.shapesize(), (6.0, 1.5, 2))
        self.assertEqual(
            [
                command["visible"]
                for command in session.commands
                if command["type"] == "visibility"
                and command["turtle"] == block._live_id
            ],
            [True],
        )

    def test_turtledemo_sorting_keys_trigger_sort(self):
        from turtledemo import sorting_animate

        session = FakeSession()
        warnings = io.StringIO()
        with (
            mock.patch.object(_standalone, "create_session", return_value=session),
            contextlib.redirect_stderr(warnings),
        ):
            sorting_animate.init_shelf()
            sorting_animate.enable_keys()
            turtle.listen()
            session.event_handler(
                {"type": "event", "event": "keyrelease", "key": "i"}
            )

        self.assertEqual(
            [block.size for block in sorting_animate.s], list(range(1, 11))
        )
        self.assertEqual(warnings.getvalue(), "")
        self.assertEqual(
            [command["type"] for command in session.commands].count("clear"), 2
        )

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


if __name__ == "__main__":
    unittest.main()
