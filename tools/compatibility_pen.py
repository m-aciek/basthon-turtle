"""Public pen-state observations with no Tk or live renderer.

CPython's bare TPen already provides no-op drawing hooks. Basthon's TPen
requires a Turtle, so use its real SVG objects and suppress only live output.
No fixture implements pen operations or repairs missing state.
"""

from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import patch


@contextmanager
def pen_instance(module):
    if module.TPen.__module__ == "basthon.turtle":
        # Screen is a singleton: preserve any caller-owned screen and isolate
        # every case. Disabling the output boundary prevents session creation.
        with (
            patch.dict(module.Singleton._instances, clear=True),
            patch.object(module.Screen, "_emit_live", lambda self, command: None),
        ):
            yield module.Turtle()
    else:
        yield module.TPen()


def state(pen):
    return {
        "down": pen.isdown(),
        "width": pen.pensize(),
        "speed": pen.speed(),
        "visible": pen.isvisible(),
        "resizemode": pen.resizemode(),
    }


def pen_sequence(operations):
    def run(module):
        from .compatibility_checks import observe

        with pen_instance(module) as pen:
            observations = [{"state": state(pen)}]
            for name, arguments, keywords in operations:
                # pen() may mutate its input dictionary; each implementation
                # must receive its own inputs, including on repeated runs.
                args, kwargs = deepcopy((arguments, keywords))
                result = observe(lambda: getattr(pen, name)(*args, **kwargs))
                observations.append(
                    deepcopy(
                        {
                            "result": result,
                            "state": state(pen),
                            "arguments": args,
                            "keywords": kwargs,
                        }
                    )
                )
                if "exception" in result:
                    break
            return observations

    return run


def pen_roundtrip(module):
    with pen_instance(module) as pen:
        saved = pen.pen()
        before = state(pen)
        pen.pen(pendown=False, pensize=5, speed=8)
        changed = state(pen)
        pen.pen(saved.copy())
        return {
            "before": before,
            "changed": changed,
            "restored": state(pen),
        }


def pen_snapshot_independence(module):
    with pen_instance(module) as pen:
        snapshot = pen.pen()
        pen.pensize(7)
        previous_width = snapshot["pensize"]
        snapshot.update(pensize=99, pendown=False, speed=9)
        return {"previous_width": previous_width, "state": state(pen)}


def calls(name, values):
    return [(name, (value,), {}) for value in values]


PEN_CASES = [
    ("initial_state", [], None),
    ("penup_pendown", [("penup", (), {}), ("pendown", (), {})], None),
    (
        "repeated_penup_pendown",
        [(name, (), {}) for name in ("penup", "penup", "pendown", "pendown")],
        None,
    ),
    ("drawing_aliases", [(name, (), {}) for name in ("pu", "pd", "up", "down")], None),
    ("pensize", calls("pensize", (2, 0.5, 10, 1)), None),
    ("width_alias", calls("width", (4, 1.5, 1)), None),
    ("speed_numbers", calls("speed", range(11)), None),
    (
        "speed_names",
        calls("speed", ("fastest", "fast", "normal", "slow", "slowest")),
        None,
    ),
    ("speed_boundaries", calls("speed", (-1, 0.5, 0.51, 10.49, 10.5, 20)), None),
    ("speed_rounding", calls("speed", (1.5, 2.5, 3.5, 4.5)), None),
    ("invalid_speed", calls("speed", ("invalid",)), "TypeError"),
    ("pen_snapshot", [("pen", (), {})], None),
    (
        "pen_dictionary",
        [("pen", ({"pendown": False, "pensize": 3, "speed": 7},), {})],
        None,
    ),
    (
        "pen_keywords",
        [("pen", (), {"pendown": False, "pensize": 3, "speed": 7})],
        None,
    ),
    (
        "pen_keyword_precedence",
        [("pen", ({"pensize": 3, "speed": 7},), {"pensize": 5})],
        None,
    ),
    ("pen_unknown_key", [("pen", (), {"unknown": 1})], "KeyError"),
]


def pen_cases():
    from .compatibility_checks import Case

    getters = tuple(
        "TPen." + name
        for name in ("isdown", "pensize", "speed", "isvisible", "resizemode")
    )
    for name, operations, error in PEN_CASES:
        required = getters + tuple("TPen." + op[0] for op in operations)
        yield Case(name, "TPen", pen_sequence(operations), required, error)
    for name, operation in (
        ("pen_restore", pen_roundtrip),
        ("pen_snapshot_independence", pen_snapshot_independence),
    ):
        yield Case(name, "TPen", operation, getters + ("TPen.pen",))
