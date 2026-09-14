"""Exercise the HTTP renderer and a real loopback WebSocket connection."""

import json
import threading
import unittest
from urllib.request import urlopen

from websockets.sync.client import connect

from basthon.turtle import _standalone


class WebSocketIntegrationTests(unittest.TestCase):
    def test_http_commands_and_browser_events(self):
        session = _standalone.StandaloneSession(browser_open=lambda url: None)
        self.addCleanup(session.close)
        received = []
        event_received = threading.Event()

        def handle(event):
            received.append(event)
            event_received.set()

        session.set_event_handler(handle)
        commands = [{"type": "init"}, {"type": "move", "to": [100, 0]}]
        for command in commands:
            session.emit(command)

        origin = f"http://127.0.0.1:{session.port}"
        with urlopen(origin, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"<svg", response.read())

        with connect(
            f"ws://127.0.0.1:{session.port}/ws",
            origin=origin,
            open_timeout=10,
            close_timeout=5,
        ) as client:
            self.assertEqual(
                [json.loads(client.recv(timeout=10)) for _ in commands], commands
            )
            self.assertTrue(session.flush(timeout=5))
            event = {"type": "event", "event": "keypress", "key": "space"}
            client.send(json.dumps(event))
            self.assertTrue(event_received.wait(timeout=10))
            self.assertEqual(received, [event])

        session.close()
        session._server_thread.join(timeout=10)
        self.assertFalse(session._server_thread.is_alive())
