def install():
    import importlib
    import sys

    sys.modules["turtle"] = importlib.import_module("basthon.turtle")
