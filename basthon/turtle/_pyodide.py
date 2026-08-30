"""In-browser transport for a Pyodide worker.

The JavaScript host registers a ``basthon_turtle_transport`` module before
importing :mod:`turtle`.  Commands cross that deliberately small boundary as
JSON strings, leaving DOM ownership and animation on the browser main thread.
"""

from __future__ import annotations

import importlib
import json
import sys


_TRANSPORT_MODULE = "basthon_turtle_transport"


def _get_transport():
    try:
        return importlib.import_module(_TRANSPORT_MODULE)
    except ImportError:
        return None


def is_available():
    """Return whether a browser host registered the Pyodide transport."""
    return sys.platform == "emscripten" and _get_transport() is not None


def create_session():
    """Create a live session for an explicitly configured Pyodide host."""
    if sys.platform != "emscripten":
        return None
    transport = _get_transport()
    if transport is None:
        return None
    return PyodideSession(transport)


class PyodideSession:
    """Send incremental commands and receive events through a JS module."""

    def __init__(self, transport, proxy_factory=None):
        self._transport = transport
        self._proxy_factory = proxy_factory
        self._event_handler = None
        self._event_proxy = None
        self._started = False
        self._closed = False

    @property
    def started(self):
        return self._started

    def start(self):
        if self._closed:
            raise RuntimeError("Pyodide turtle session is closed")
        if self._started:
            return

        proxy_factory = self._proxy_factory
        if proxy_factory is None:
            from pyodide.ffi import create_proxy

            proxy_factory = create_proxy
        self._event_proxy = proxy_factory(self._receive_event)
        self._transport.set_event_handler(self._event_proxy)
        self._started = True

    def emit(self, command):
        """Send one JSON command without waiting for browser animation."""
        self.start()
        self._transport.emit(json.dumps(command, separators=(",", ":")))

    def set_event_handler(self, handler):
        self._event_handler = handler

    def _receive_event(self, payload):
        if self._event_handler is not None:
            self._event_handler(json.loads(str(payload)))

    def flush(self):
        """Commands are synchronously handed to the worker message queue."""
        return True

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._started:
            self._transport.set_event_handler(None)
        if self._event_proxy is not None:
            self._event_proxy.destroy()
            self._event_proxy = None
