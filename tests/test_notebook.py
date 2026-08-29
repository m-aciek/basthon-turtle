import contextlib
import unittest
from unittest import mock

from basthon import turtle
from basthon.turtle import _notebook, _standalone


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


class NotebookBackendSelectionTests(unittest.TestCase):
    def setUp(self):
        self._reset_turtle()

    def tearDown(self):
        self._reset_turtle()
        _notebook.use_sidecar(True)

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
            mock.patch.object(_standalone, "create_session") as standalone,
        ):
            turtle.Turtle()

        standalone.assert_not_called()
        self.assertGreaterEqual(session.emit.call_count, 1)

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


if __name__ == "__main__":
    unittest.main()
