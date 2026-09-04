"""Persistent renderer for Jupyter and Marimo notebooks.

The optional dependencies are imported only after a supported notebook runtime
is detected. Jupyter commands are buffered while a cell runs and published as
one widget-state update from IPython's ``post_run_cell`` event. Marimo commands
are published immediately to a persistent ``mo.ui.anywidget`` output.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


_USE_SIDECAR = True
_WIDGET_CLASS = None


def _get_shell():
    try:
        from IPython import get_ipython
    except ImportError:
        return None
    return get_ipython()


def is_available():
    """Return whether an active Jupyter kernel can host the turtle widget."""
    shell = _get_shell()
    return (
        shell is not None
        and getattr(shell, "kernel", None) is not None
        and importlib.util.find_spec("anywidget") is not None
        and importlib.util.find_spec("traitlets") is not None
    )


def _is_marimo_available():
    """Return whether code is running in a Marimo notebook."""
    if importlib.util.find_spec("marimo") is None:
        return False
    import marimo

    return (
        marimo.running_in_notebook()
        and importlib.util.find_spec("anywidget") is not None
        and importlib.util.find_spec("traitlets") is not None
    )


def use_sidecar(enabled=True):
    """Place future notebook turtle widgets in a JupyterLab sidecar."""
    global _USE_SIDECAR
    _USE_SIDECAR = bool(enabled)


def create_session():
    """Create a session for the active supported notebook runtime."""
    if _is_marimo_available():
        return MarimoSession()
    if not is_available():
        return None
    return NotebookSession(_get_shell(), use_sidecar=_USE_SIDECAR)


def _get_widget_class():
    global _WIDGET_CLASS
    if _WIDGET_CLASS is not None:
        return _WIDGET_CLASS

    import anywidget
    import traitlets

    assets = Path(__file__).parent

    class TurtleWidget(anywidget.AnyWidget):
        _esm = assets / "notebook.mjs"
        _css = assets / "notebook.css"

        history = traitlets.List(trait=traitlets.Dict(), default_value=[]).tag(
            sync=True
        )
        animation_start = traitlets.Int(0).tag(sync=True)

    _WIDGET_CLASS = TurtleWidget
    return TurtleWidget


class NotebookSession:
    """An ordered command history shared by all views of one Jupyter widget."""

    def __init__(
        self,
        shell,
        use_sidecar=False,
        widget_factory=None,
        display_widget=None,
        sidecar_factory=None,
    ):
        self._shell = shell
        self._use_sidecar = use_sidecar
        self._widget_factory = widget_factory or _get_widget_class()
        self._display_widget = display_widget
        self._sidecar_factory = sidecar_factory
        self._event_handler = None
        self._pending = []
        self._history = []
        self._started = False
        self._closed = False
        self._handling_event = False
        # A session is first created by code running inside a cell.  Registering
        # the pre-run hook happens too late for that first cell, so start active.
        self._cell_active = True
        self.widget = None
        self.sidecar = None

    @property
    def started(self):
        return self._started

    @property
    def pending_count(self):
        return len(self._pending)

    @property
    def history(self):
        return tuple(self._history)

    def start(self):
        """Create and display one widget, then attach cell-boundary hooks."""
        if self._started:
            return
        if self._closed:
            raise RuntimeError("notebook turtle session is closed")

        self.widget = self._widget_factory()
        self.widget.on_msg(self._receive_message)
        self._shell.events.register("pre_run_cell", self._pre_run_cell)
        self._shell.events.register("post_run_cell", self._post_run_cell)
        self._show_widget()
        self._started = True

    def _show_widget(self):
        display_widget = self._display_widget
        if display_widget is None:
            from IPython.display import display

            display_widget = display

        sidecar_available = (
            self._sidecar_factory is not None
            or importlib.util.find_spec("sidecar") is not None
        )
        if not self._use_sidecar or not sidecar_available:
            display_widget(self.widget)
            return

        sidecar_factory = self._sidecar_factory
        if sidecar_factory is None:
            from sidecar import Sidecar

            sidecar_factory = Sidecar
        self.sidecar = sidecar_factory(
            title="Python Turtle Graphics", anchor="split-right"
        )
        with self.sidecar:
            display_widget(self.widget)

    def emit(self, command):
        """Buffer one command until the active cell has finished."""
        self.start()
        self._pending.append(dict(command))
        if not self._cell_active and not self._handling_event:
            self._publish()

    def set_event_handler(self, handler):
        self._event_handler = handler

    def flush(self):
        """Publish pending commands unless a code cell is still executing."""
        if not self._cell_active:
            self._publish()
        return not self._pending

    def _pre_run_cell(self, _info=None):
        self._cell_active = True

    def _post_run_cell(self, _result=None):
        self._publish()
        self._cell_active = False

    def _publish(self):
        if not self._pending or self.widget is None:
            return
        animation_start = len(self._history)
        self._history.extend(self._pending)
        self._pending.clear()
        with self.widget.hold_trait_notifications():
            self.widget.animation_start = animation_start
            self.widget.history = list(self._history)

    def _receive_message(self, _widget, content, _buffers=None):
        if content.get("type") == "rendered":
            count = content.get("count")
            if count == len(self._history):
                self.widget.animation_start = count
            return
        if content.get("type") != "event" or self._event_handler is None:
            return
        self._handling_event = True
        try:
            self._event_handler(content)
        finally:
            self._handling_event = False
            self._publish()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._started:
            for event, callback in (
                ("pre_run_cell", self._pre_run_cell),
                ("post_run_cell", self._post_run_cell),
            ):
                try:
                    self._shell.events.unregister(event, callback)
                except ValueError:
                    pass
        if self.widget is not None:
            self.widget.close()
        if self.sidecar is not None:
            close = getattr(self.sidecar, "close", None)
            if close is not None:
                close()


class MarimoSession(NotebookSession):
    """An immediately synchronized AnyWidget mounted in a Marimo cell."""

    def __init__(
        self,
        widget_factory=None,
        wrap_widget=None,
        replace_output=None,
    ):
        super().__init__(
            shell=None,
            use_sidecar=False,
            widget_factory=widget_factory,
        )
        self._wrap_widget = wrap_widget
        self._replace_output = replace_output
        self._cell_active = False
        self.output = None

    def start(self):
        """Create one AnyWidget and mount it in the current Marimo cell."""
        if self._started:
            return
        if self._closed:
            raise RuntimeError("notebook turtle session is closed")

        self.widget = self._widget_factory()
        self.widget.on_msg(self._receive_message)

        wrap_widget = self._wrap_widget
        replace_output = self._replace_output
        if wrap_widget is None or replace_output is None:
            import marimo

            if wrap_widget is None:
                wrap_widget = marimo.ui.anywidget
            if replace_output is None:
                replace_output = marimo.output.replace

        self.output = wrap_widget(self.widget)
        replace_output(self.output)
        self._started = True

    def _publish(self):
        if not self._pending or self.widget is None:
            return
        # Marimo has no post-cell hook, so several state updates may reach the
        # model before its first view mounts. Keep the last browser-acknowledged
        # boundary so that a newly mounted view animates the full unseen suffix.
        animation_start = min(self.widget.animation_start, len(self._history))
        self._history.extend(self._pending)
        self._pending.clear()
        with self.widget.hold_trait_notifications():
            self.widget.animation_start = animation_start
            self.widget.history = list(self._history)

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.widget is not None:
            self.widget.close()
