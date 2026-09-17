"""Exercise the real AnyWidget and IPython event APIs without a frontend."""

import unittest
from unittest import mock

import anywidget
from IPython.core.interactiveshell import InteractiveShell

from basthon.turtle import _notebook


class AnyWidgetIntegrationTests(unittest.TestCase):
    def test_cell_events_publish_synced_widget_state_and_cleanup(self):
        shell = InteractiveShell()
        display = mock.Mock()
        session = _notebook.NotebookSession(shell, display_widget=display)
        self.addCleanup(session.close)

        session.emit({"type": "init"})
        self.assertIsInstance(session.widget, anywidget.AnyWidget)
        self.assertEqual(session.widget.get_state()["history"], [])
        shell.run_cell("pass")
        self.assertEqual(session.widget.get_state()["history"], [{"type": "init"}])
        self.assertIn("change:history", session.widget.get_state()["_esm"])
        display.assert_called_once_with(session.widget)

        received = []
        session.set_event_handler(received.append)
        event = {"type": "event", "event": "keypress", "key": "space"}
        session.widget._handle_custom_msg(event, [])
        self.assertEqual(received, [event])

        session.close()
        self.assertIsNone(session.widget.comm)
        self.assertNotIn(session._pre_run_cell, shell.events.callbacks["pre_run_cell"])
        self.assertNotIn(
            session._post_run_cell, shell.events.callbacks["post_run_cell"]
        )
