"""Local, incremental browser renderer used by the standalone extra.

This module deliberately imports the optional ``websockets`` dependency only
after the first visible turtle operation starts a session.
"""

from __future__ import annotations

import atexit
import importlib.util
import json
import os
import socket
import sys
import threading
import time
import traceback
import webbrowser
from collections import deque


_HOST = "127.0.0.1"


def is_available():
    """Return whether the optional standalone renderer can run."""
    return (
        sys.platform not in {"emscripten", "wasi"}
        and importlib.util.find_spec("websockets") is not None
    )


def create_session():
    """Create a session when the standalone extra is installed."""
    if not is_available():
        return None
    return StandaloneSession()


class StandaloneSession:
    """A persistent localhost server and ordered outbound command queue."""

    def __init__(self, browser_open=None):
        self._browser_open = browser_open or webbrowser.open
        self._condition = threading.Condition()
        self._pending = deque()
        self._started = False
        self._closed = False
        self._connection = None
        self._connected_once = False
        self._event_handler = None
        self._server = None
        self._socket = None
        self._server_thread = None
        self._browser_thread = None
        self.port = None

    @property
    def started(self):
        return self._started

    @property
    def pending_count(self):
        with self._condition:
            return len(self._pending)

    @staticmethod
    def _create_socket():
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((_HOST, 0))
            sock.listen()
        except BaseException:
            sock.close()
            raise
        return sock

    def start(self):
        """Start the server and browser once, without occupying the caller."""
        with self._condition:
            if self._started:
                return
            if self._closed:
                raise RuntimeError("standalone turtle session is closed")
            self._socket = self._create_socket()
            self.port = self._socket.getsockname()[1]
            self._started = True

        self._server_thread = threading.Thread(
            target=self._serve,
            args=(self._socket,),
            name="basthon-turtle-server",
            daemon=True,
        )
        self._server_thread.start()

        url = "http://{}:{}/".format(_HOST, self.port)
        self._browser_thread = threading.Thread(
            target=self._browser_open,
            args=(url,),
            name="basthon-turtle-browser",
            daemon=True,
        )
        self._browser_thread.start()
        atexit.register(self.close)

    def emit(self, command):
        """Queue one JSON command; commands survive the connection race."""
        self.start()
        payload = json.dumps(command, separators=(",", ":"))
        with self._condition:
            self._pending.append(payload)
            self._condition.notify_all()

    def set_event_handler(self, handler):
        """Set the callback for messages received from the browser."""
        self._event_handler = handler

    def flush(self, timeout=5):
        """Wait briefly for queued commands to reach the browser.

        This doesn't wait for browser-side animation. It primarily makes
        short scripts ending in ``done()`` reliable during the initial
        connection race.
        """
        deadline = time.monotonic() + timeout
        with self._condition:
            self._condition.notify_all()
            while self._pending and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            return not self._pending

    def wait_for_disconnect(self):
        """Wait for the first browser client to connect and then disconnect."""
        with self._condition:
            while not self._closed and not self._connected_once:
                self._condition.wait(0.5)
            while not self._closed and self._connection is not None:
                self._condition.wait(0.5)

    def _serve(self, sock):
        # Keep this import lazy so the base package has no WebSocket dependency.
        from websockets.datastructures import Headers
        from websockets.http11 import Response
        from websockets.sync.server import serve

        html = self._client_html()

        def process_request(_connection, request):
            if request.path.split("?", 1)[0] == "/ws":
                return None
            return Response(
                200,
                "OK",
                Headers(
                    [
                        ("Content-Type", "text/html; charset=utf-8"),
                        ("Content-Length", str(len(html))),
                        ("Cache-Control", "no-store"),
                    ]
                ),
                html,
            )

        try:
            with serve(
                self._handle_connection,
                sock=sock,
                origins=["http://{}:{}".format(_HOST, self.port), None],
                process_request=process_request,
            ) as server:
                self._server = server
                server.serve_forever()
        finally:
            with self._condition:
                self._server = None
                self._condition.notify_all()

    @staticmethod
    def _client_html():
        path = os.path.join(os.path.dirname(__file__), "standalone.html")
        with open(path, "rb") as client_file:
            return client_file.read()

    def _handle_connection(self, connection):
        with self._condition:
            self._connection = connection
            self._connected_once = True
            self._condition.notify_all()

        event_thread = threading.Thread(
            target=self._receive_events,
            args=(connection,),
            name="basthon-turtle-events",
            daemon=True,
        )
        event_thread.start()

        try:
            while True:
                with self._condition:
                    while (
                        not self._pending
                        and not self._closed
                        and self._connection is connection
                    ):
                        self._condition.wait()
                    if self._closed or self._connection is not connection:
                        return
                    payload = self._pending[0]

                try:
                    connection.send(payload)
                except Exception:
                    # Keep the unsent command for a reconnecting browser.
                    return

                with self._condition:
                    if self._pending and self._pending[0] == payload:
                        self._pending.popleft()
                    self._condition.notify_all()
        finally:
            with self._condition:
                if self._connection is connection:
                    self._connection = None
                self._condition.notify_all()

    def _receive_events(self, connection):
        try:
            while True:
                try:
                    message = connection.recv()
                except Exception:
                    return
                if message is None:
                    return
                try:
                    event = json.loads(message)
                    if self._event_handler is not None:
                        self._event_handler(event)
                except Exception:
                    traceback.print_exc()
        finally:
            with self._condition:
                if self._connection is connection:
                    self._connection = None
                self._condition.notify_all()

    def _drain_pending(self, connection):
        """Send all currently queued messages (a non-blocking test seam)."""
        while True:
            with self._condition:
                if not self._pending:
                    return
                payload = self._pending[0]
            connection.send(payload)
            with self._condition:
                self._pending.popleft()

    def close(self):
        with self._condition:
            if self._closed:
                return
            self._closed = True
            server = self._server
            sock = self._socket
            self._condition.notify_all()

        if server is not None:
            server.shutdown()
        elif sock is not None:
            sock.close()
