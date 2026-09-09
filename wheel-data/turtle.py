"""Compatibility alias for environments that install packages at runtime."""

import sys

from basthon import turtle as _implementation


sys.modules[__name__] = _implementation
