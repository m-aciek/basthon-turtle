"""Exercise real Sidecar construction; JupyterLab docking needs a frontend."""

import unittest
from unittest import mock

import anywidget
from IPython.core.interactiveshell import InteractiveShell
from sidecar import Sidecar

from basthon.turtle import _notebook


class SidecarIntegrationTests(unittest.TestCase):
    def test_sidecar_hosts_widget_and_closes_with_session(self):
        shell = InteractiveShell()
        display = mock.Mock()
        session = _notebook.NotebookSession(
            shell, use_sidecar=True, display_widget=display
        )
        self.addCleanup(session.close)

        session.emit({"type": "init"})
        shell.run_cell("pass")

        self.assertIsInstance(session.widget, anywidget.AnyWidget)
        self.assertIsInstance(session.sidecar, Sidecar)
        self.assertEqual(session.sidecar.get_state()["anchor"], "split-right")
        self.assertEqual(session.widget.history, [{"type": "init"}])
        display.assert_called_once_with(session.widget)

        session.close()
        self.assertIsNone(session.widget.comm)
        self.assertIsNone(session.sidecar.comm)
