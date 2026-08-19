import importlib
import sys
import unittest

from basthon import turtle as basthon_turtle
from basthon.turtle import _startup


class StartupTests(unittest.TestCase):
    def test_compatibility_shim_overrides_turtle_module(self):
        previous = sys.modules.pop("turtle", None)
        self.addCleanup(self._restore_turtle, previous)

        turtle = importlib.import_module("turtle")

        self.assertIs(turtle, basthon_turtle)

    def test_install_overrides_turtle_module(self):
        previous = sys.modules.get("turtle")
        self.addCleanup(self._restore_turtle, previous)

        _startup.install()

        self.assertIs(sys.modules["turtle"], basthon_turtle)

    @staticmethod
    def _restore_turtle(previous):
        if previous is None:
            sys.modules.pop("turtle", None)
        else:
            sys.modules["turtle"] = previous


if __name__ == "__main__":
    unittest.main()
