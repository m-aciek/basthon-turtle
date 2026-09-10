import contextlib
import types
import unittest
import warnings
import xml.etree.ElementTree as ET
from unittest import mock

from basthon import turtle
from basthon.turtle import _notebook, _pyodide, _standalone


class FakeEvents:
    def __init__(self):
        self.callbacks = {"pre_run_cell": [], "post_run_cell": []}

    def register(self, event, callback):
        self.callbacks[event].append(callback)

    def unregister(self, event, callback):
        self.callbacks[event].remove(callback)

    def trigger(self, event, argument=None):
        for callback in tuple(self.callbacks[event]):
            callback(argument)


class FakeShell:
    def __init__(self):
        self.kernel = object()
        self.events = FakeEvents()


class FakeWidget:
    def __init__(self):
        self.history = []
        self.animation_start = 0
        self.message_handler = None
        self.closed = False
        self.notification_batches = 0

    def on_msg(self, handler):
        self.message_handler = handler

    @contextlib.contextmanager
    def hold_trait_notifications(self):
        self.notification_batches += 1
        yield

    def receive(self, content):
        self.message_handler(self, content, None)

    def close(self):
        self.closed = True


class FakeSidecar:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.entered = 0
        self.closed = False

    def __enter__(self):
        self.entered += 1
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        self.closed = True


class NotebookSessionTests(unittest.TestCase):
    def make_session(self, **kwargs):
        shell = kwargs.pop("shell", FakeShell())
        widget = FakeWidget()
        display = mock.Mock()
        session = _notebook.NotebookSession(
            shell,
            widget_factory=lambda: widget,
            display_widget=display,
            **kwargs,
        )
        return session, shell, widget, display

    def test_commands_are_published_as_one_batch_after_the_cell(self):
        session, shell, widget, display = self.make_session()

        session.emit({"type": "init"})
        session.emit({"type": "move", "to": [100, 0]})

        display.assert_called_once_with(widget)
        self.assertEqual(widget.history, [])
        self.assertEqual(session.pending_count, 2)

        shell.events.trigger("post_run_cell")

        self.assertEqual(
            [command["type"] for command in widget.history], ["init", "move"]
        )
        self.assertEqual(widget.animation_start, 0)
        self.assertEqual(widget.notification_batches, 1)
        self.assertEqual(session.pending_count, 0)

    def test_later_cells_animate_only_the_new_history_suffix(self):
        session, shell, widget, _display = self.make_session()
        session.emit({"type": "init"})
        session.emit({"type": "move", "to": [100, 0]})
        shell.events.trigger("post_run_cell")
        widget.receive({"type": "rendered", "count": 2})
        self.assertEqual(widget.animation_start, 2)

        shell.events.trigger("pre_run_cell")
        session.emit({"type": "rotate", "to": 90})
        session.emit({"type": "move", "to": [100, -50]})
        shell.events.trigger("post_run_cell")

        self.assertEqual(widget.animation_start, 2)
        self.assertEqual(
            [command["type"] for command in widget.history],
            ["init", "move", "rotate", "move"],
        )

    def test_browser_events_can_emit_and_publish_new_commands(self):
        session, shell, widget, _display = self.make_session()
        session.emit({"type": "init"})
        shell.events.trigger("post_run_cell")
        published_batches = widget.notification_batches

        def handle(event):
            session.emit({"type": "background", "color": event["color"]})
            session.emit({"type": "focus"})

        session.set_event_handler(handle)
        widget.receive({"type": "event", "event": "drag", "color": "red"})

        self.assertEqual(
            widget.history[-2:],
            [{"type": "background", "color": "red"}, {"type": "focus"}],
        )
        self.assertEqual(widget.animation_start, 1)
        self.assertEqual(widget.notification_batches, published_batches + 1)

    def test_post_run_cell_publishes_commands_even_after_an_error(self):
        session, shell, widget, _display = self.make_session()
        session.emit({"type": "move", "to": [20, 0]})

        shell.events.trigger("post_run_cell", RuntimeError("cell failed"))

        self.assertEqual(widget.history, [{"type": "move", "to": [20, 0]}])
        self.assertEqual(session.pending_count, 0)

    def test_sidecar_is_used_when_requested_and_available(self):
        sidecars = []

        def sidecar_factory(**kwargs):
            sidecar = FakeSidecar(**kwargs)
            sidecars.append(sidecar)
            return sidecar

        session, _shell, widget, display = self.make_session(
            use_sidecar=True, sidecar_factory=sidecar_factory
        )
        session.emit({"type": "init"})

        self.assertEqual(len(sidecars), 1)
        self.assertEqual(
            sidecars[0].kwargs,
            {"title": "Python Turtle Graphics", "anchor": "split-right"},
        )
        self.assertEqual(sidecars[0].entered, 1)
        display.assert_called_once_with(widget)

    def test_missing_sidecar_falls_back_to_inline_widget(self):
        session, _shell, widget, display = self.make_session(use_sidecar=True)
        original_find_spec = _notebook.importlib.util.find_spec

        def find_spec(name):
            if name == "sidecar":
                return None
            return original_find_spec(name)

        with mock.patch.object(_notebook.importlib.util, "find_spec", find_spec):
            session.emit({"type": "init"})

        self.assertIsNone(session.sidecar)
        display.assert_called_once_with(widget)

    def test_close_unregisters_hooks_and_closes_views(self):
        session, shell, widget, _display = self.make_session(
            use_sidecar=True, sidecar_factory=FakeSidecar
        )
        session.emit({"type": "init"})

        session.close()

        self.assertEqual(shell.events.callbacks["pre_run_cell"], [])
        self.assertEqual(shell.events.callbacks["post_run_cell"], [])
        self.assertTrue(widget.closed)
        self.assertTrue(session.sidecar.closed)


class MarimoSessionTests(unittest.TestCase):
    def make_session(self):
        widget = FakeWidget()
        wrap_widget = mock.Mock(return_value=object())
        replace_output = mock.Mock()
        session = _notebook.MarimoSession(
            widget_factory=lambda: widget,
            wrap_widget=wrap_widget,
            replace_output=replace_output,
            register_cleanup=mock.Mock(),
        )
        return session, widget, wrap_widget, replace_output

    def test_widget_is_wrapped_and_mounted_as_marimo_output(self):
        session, widget, wrap_widget, replace_output = self.make_session()

        session.emit({"type": "init"})

        wrap_widget.assert_called_once_with(widget)
        replace_output.assert_called_once_with(session.output)
        self.assertEqual(widget.history, [{"type": "init"}])
        self.assertEqual(widget.animation_start, 0)

    def test_commands_are_published_immediately(self):
        session, widget, _wrap_widget, _replace_output = self.make_session()

        session.emit({"type": "init"})
        session.emit({"type": "move", "to": [100, 0]})

        self.assertEqual(
            [command["type"] for command in widget.history], ["init", "move"]
        )
        self.assertEqual(widget.animation_start, 0)
        self.assertEqual(widget.notification_batches, 2)

        widget.receive({"type": "rendered", "count": 2})
        session.emit({"type": "rotate", "to": 90})

        self.assertEqual(widget.animation_start, 2)

    def test_close_closes_widget(self):
        session, widget, _wrap_widget, _replace_output = self.make_session()
        session.emit({"type": "init"})

        session.close()

        self.assertTrue(widget.closed)

    def test_cell_reruns_restore_history_in_a_new_widget(self):
        session, _widget, wrap, replace = self.make_session()
        session._widget_factory = FakeWidget
        widgets = []

        for count in range(1, 4):
            session.emit({"type": "move", "to": [100 * count, 0]})
            widget = session.widget
            widgets.append(widget)
            self.assertEqual(len(widget.history), count)
            self.assertEqual(widget.animation_start, count - 1)
            self.assertEqual(widget.history[-1]["to"], [100 * count, 0])
            self.assertEqual(replace.call_count, count)
            self.assertEqual(wrap.call_count, count)

            # Marimo disposes the owning cell before executing it again.
            cleanup = session._register_cleanup.call_args.args[0]
            cleanup()
            self.assertTrue(widget.closed)
            self.assertFalse(session.started)

        self.assertEqual(len({id(widget) for widget in widgets}), 3)

    def test_other_cells_keep_using_the_mounted_widget(self):
        session, widget, wrap, replace = self.make_session()
        session.emit({"type": "init"})
        session.emit({"type": "move", "to": [100, 0]})

        wrap.assert_called_once_with(widget)
        replace.assert_called_once_with(session.output)
        session._register_cleanup.assert_called_once()

    def test_disposed_widget_events_cannot_update_replacement(self):
        session, old_widget, _wrap, _replace = self.make_session()
        handler = mock.Mock()
        session.set_event_handler(handler)
        session.emit({"type": "init"})
        session._register_cleanup.call_args.args[0]()
        session._widget_factory = FakeWidget
        session.emit({"type": "move", "to": [100, 0]})

        old_widget.receive({"type": "rendered", "count": 2})
        old_widget.receive({"type": "event", "event": "click"})
        self.assertEqual(session.widget.animation_start, 1)
        handler.assert_not_called()

        session.widget.receive({"type": "event", "event": "click"})
        handler.assert_called_once()

    def test_cell_cleanup_after_close_is_idempotent(self):
        session, widget, _wrap, _replace = self.make_session()
        session.emit({"type": "init"})
        cleanup = session._register_cleanup.call_args.args[0]
        session.close()
        cleanup()

        self.assertTrue(widget.closed)
        with self.assertRaisesRegex(RuntimeError, "closed"):
            session.emit({"type": "move"})


class NotebookBackendSelectionTests(unittest.TestCase):
    def setUp(self):
        self._reset_turtle()

    def tearDown(self):
        self._reset_turtle()
        _notebook.use_sidecar(True)
        _notebook._RENDERER = "widget"

    @staticmethod
    def _reset_turtle():
        screen = turtle.Singleton._instances.pop(turtle.Screen, None)
        if screen is not None and screen._standalone_session is not None:
            close = getattr(screen._standalone_session, "close", None)
            if close is not None:
                close()
        turtle.Turtle._pen = None
        turtle.Turtle.screen = None

    def test_notebook_backend_takes_priority_over_standalone(self):
        session = mock.Mock()
        session.started = True
        with (
            mock.patch.object(_notebook, "create_session", return_value=session),
            mock.patch.object(_pyodide, "create_session") as pyodide,
            mock.patch.object(_standalone, "create_session") as standalone,
        ):
            turtle.Turtle()

        pyodide.assert_not_called()
        standalone.assert_not_called()
        self.assertGreaterEqual(session.emit.call_count, 1)

    def test_missing_widget_dependencies_warn_without_starting_standalone(self):
        for host in ("jupyter", "marimo"):
            with self.subTest(host=host):
                self._reset_turtle()
                shell = mock.Mock() if host == "jupyter" else None
                marimo = types.SimpleNamespace(running_in_notebook=lambda: True)
                with (
                    mock.patch.object(_notebook, "_get_shell", return_value=shell),
                    mock.patch.dict("sys.modules", {"marimo": marimo}),
                    mock.patch.object(
                        _notebook.importlib.util,
                        "find_spec",
                        side_effect=lambda name: object()
                        if name == "marimo" and host == "marimo"
                        else None,
                    ),
                    mock.patch.object(_pyodide, "create_session") as pyodide,
                    mock.patch.object(_standalone, "create_session") as standalone,
                    warnings.catch_warnings(record=True) as caught,
                ):
                    warnings.simplefilter("always")
                    self.assertTrue(_notebook.is_notebook())
                    pen = turtle.Turtle()
                    pen.forward(10)
                    pen.left(90)

                self.assertEqual(len(caught), 1)
                self.assertIn("basthon-turtle[notebook]", str(caught[0].message))
                pyodide.assert_not_called()
                standalone.assert_not_called()

    def test_terminal_ipython_is_not_a_notebook(self):
        with (
            mock.patch.object(_notebook, "_is_marimo_running", return_value=False),
            mock.patch.object(
                _notebook, "_get_shell", return_value=types.SimpleNamespace()
            ),
        ):
            self.assertFalse(_notebook.is_notebook())

    def test_marimo_backend_takes_priority_over_jupyter(self):
        with (
            mock.patch.object(_notebook, "_is_marimo_available", return_value=True),
            mock.patch.object(_notebook, "is_available") as jupyter_available,
            mock.patch.object(_notebook, "_get_widget_class", return_value=FakeWidget),
        ):
            session = _notebook.create_session()

        self.assertIsInstance(session, _notebook.MarimoSession)
        jupyter_available.assert_not_called()

    def test_sidecar_preference_must_be_set_before_drawing(self):
        turtle.jupyter_sidecar(False)
        self.assertFalse(_notebook._USE_SIDECAR)

        session = mock.Mock()
        session.started = True
        with mock.patch.object(_notebook, "create_session", return_value=session):
            turtle.Turtle()

        with self.assertRaisesRegex(RuntimeError, "before drawing"):
            turtle.jupyter_sidecar(True)


class SVGNotebookTests(unittest.TestCase):
    def setUp(self):
        NotebookBackendSelectionTests._reset_turtle()
        self.shell = FakeShell()
        self.handle = mock.Mock()
        self.display = mock.Mock(return_value=self.handle)
        patches = (
            mock.patch.object(_notebook, "_get_shell", return_value=self.shell),
            mock.patch.object(_notebook, "_is_marimo_running", return_value=False),
            mock.patch.object(
                _notebook, "_get_widget_class", side_effect=AssertionError
            ),
            mock.patch.dict(
                "sys.modules",
                {
                    "IPython.display": types.SimpleNamespace(
                        SVG=lambda data: data, display=self.display
                    ),
                },
            ),
        )
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(NotebookBackendSelectionTests._reset_turtle)
        self.addCleanup(setattr, _notebook, "_RENDERER", "widget")
        turtle.jupyter_renderer("svg")

    def finish_cell(self, error=None):
        self.shell.events.trigger("post_run_cell", error)
        call = self.handle.update.call_args or self.display.call_args
        return ET.fromstring(call.args[0])

    def nodes(self, root, tag):
        nodes = root.findall(".//{http://www.w3.org/2000/svg}" + tag)
        if tag == "line":
            # Turtle initialization also adds a zero-length segment.
            nodes = [
                node
                for node in nodes
                if (node.get("x1"), node.get("y1")) != (node.get("x2"), node.get("y2"))
            ]
        return nodes

    def test_drawing_accumulates_in_one_display_without_finalizing(self):
        namespace = {}
        exec(
            "from basthon.turtle import *\n"
            "jupyter_renderer('svg')\n"
            "pen = Turtle()\n"
            "pen.forward(100)",
            namespace,
        )
        pen = namespace["pen"]
        self.display.assert_not_called()
        first = self.finish_cell()
        self.display.assert_called_once()
        self.assertEqual(self.display.call_args.kwargs, {"display_id": True})
        self.assertEqual(len(self.nodes(first, "line")), 1)
        self.assertEqual(self.nodes(first, "line")[0].get("x2"), "100")
        self.assertFalse(pen.screen._scene_finished)
        self.assertEqual(pen.screen.turtle_canvas._children, [])

        self.shell.events.trigger("pre_run_cell")
        pen.left(90)
        pen.forward(50)
        second = self.finish_cell()
        self.display.assert_called_once()
        self.handle.update.assert_called_once()
        self.assertEqual(len(self.nodes(second, "line")), 2)
        self.assertEqual(self.nodes(second, "line")[-1].get("y2"), "-50")
        self.assertEqual(len(self.nodes(second, "polygon")), 1)
        self.assertEqual(
            self.nodes(second, "polygon")[0].get("transform"),
            "translate(100.0, -50.0) rotate(-180.0, 0, 0)",
        )
        self.assertFalse(self.nodes(second, "animate"))

    def test_idle_cells_do_not_refresh_and_errors_still_publish(self):
        turtle.forward(20)
        self.finish_cell(RuntimeError("after drawing"))
        self.shell.events.trigger("pre_run_cell")
        self.finish_cell()
        self.handle.update.assert_not_called()

    def test_clear_preserves_other_turtles_and_later_drawing(self):
        first = turtle.Turtle()
        second = turtle.Turtle()
        first.forward(10)
        second.forward(20)
        self.finish_cell()
        self.shell.events.trigger("pre_run_cell")
        first.clear()
        first.forward(5)
        svg = self.finish_cell()
        self.assertEqual([n.get("x2") for n in self.nodes(svg, "line")], ["20", "15"])
        self.assertEqual(len(self.nodes(svg, "polygon")), 2)

    def test_new_turtles_shapes_and_done_do_not_duplicate_turtles(self):
        first = turtle.Turtle()
        first.forward(10)
        turtle.done()
        self.display.assert_not_called()
        self.finish_cell()
        self.shell.events.trigger("pre_run_cell")
        second = turtle.Turtle(shape="circle")
        second.forward(20)
        first.shape("square")
        svg = self.finish_cell()
        self.assertEqual(len(self.nodes(svg, "circle")), 1)
        self.assertEqual(len(self.nodes(svg, "rect")), 1)
        self.assertTrue(
            all(n.get("opacity") == "0" for n in self.nodes(svg, "polygon"))
        )

    def test_stamp_and_restart_refresh_without_live_commands(self):
        turtle.forward(10)
        self.finish_cell()
        self.shell.events.trigger("pre_run_cell")
        turtle.stamp()
        svg = self.finish_cell()
        self.assertEqual(len(self.nodes(svg, "polygon")), 2)
        self.shell.events.trigger("pre_run_cell")
        turtle.restart()
        svg = self.finish_cell()
        self.assertFalse(self.nodes(svg, "line"))
        self.assertFalse(self.nodes(svg, "polygon"))
        self.shell.events.trigger("pre_run_cell")
        turtle.forward(30)
        svg = self.finish_cell()
        self.assertEqual(len(self.nodes(svg, "line")), 1)
        self.assertEqual(len(self.nodes(svg, "polygon")), 1)
        self.display.assert_called_once()

    def test_configuration_and_animation_are_validated(self):
        with self.assertRaisesRegex(ValueError, "renderer"):
            turtle.jupyter_renderer("unknown")
        screen = turtle.Screen()
        self.assertFalse(screen._animate)
        turtle.jupyter_renderer("widget")
        self.assertTrue(screen._animate)
        turtle.jupyter_renderer("svg")
        with self.assertRaisesRegex(ValueError, "animation"):
            turtle.animation("on")
        turtle.forward(10)
        with self.assertRaisesRegex(RuntimeError, "before drawing"):
            turtle.jupyter_renderer("widget")

    def test_close_removes_hooks_and_prevents_further_updates(self):
        turtle.forward(10)
        self.finish_cell()
        session = turtle.Screen()._standalone_session
        session.close()
        session.close()
        self.assertFalse(session.flush())
        self.assertEqual(
            self.shell.events.callbacks, {"pre_run_cell": [], "post_run_cell": []}
        )
        with self.assertRaisesRegex(RuntimeError, "closed"):
            session.emit({"type": "move"})

    def test_svg_selection_does_not_affect_other_hosts(self):
        with mock.patch.object(_notebook, "_get_shell", return_value=None):
            self.assertFalse(_notebook.uses_svg_renderer())
            self.assertTrue(turtle.Screen()._animate)
        with mock.patch.object(_notebook, "_is_marimo_running", return_value=True):
            self.assertFalse(_notebook.uses_svg_renderer())


if __name__ == "__main__":
    unittest.main()
