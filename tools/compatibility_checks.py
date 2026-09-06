"""Small differential cases guided by CPython Lib/test/test_turtle.py.

Only public observations are used; no screen, pen, or private state adapters.
Navigator operations are data so generated sequences can use the same runner.
"""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Case:
    name: str
    symbol: str
    run: object
    # Missing reference features on older CPython versions are not applicable.
    requires: tuple = ()
    expected_exception: str = None


def observe(operation):
    try:
        return {"value": operation()}
    except Exception as error:
        return {"exception": type(error).__name__, "message": str(error)}


def navigation(operations, mode="standard"):
    def run(module):
        nav = module.TNavigator(mode=mode)

        def argument(value):
            if isinstance(value, dict):
                if "navigator" in value:
                    other = module.TNavigator()
                    other.goto(*value["navigator"])
                    return other
                if "vector" in value:
                    return module.Vec2D(*value["vector"])
            return value

        observations = []
        for name, *args in operations:
            result = observe(
                lambda: getattr(nav, name)(*(argument(arg) for arg in args))
            )
            observations.append(
                {
                    "result": result,
                    "position": tuple(nav.position()),
                    "heading": nav.heading(),
                    "xcor": nav.xcor(),
                    "ycor": nav.ycor(),
                }
            )
            if "exception" in result:
                break
        return observations

    return run


VECTOR_CASES = [
    ("construction", lambda v: (isinstance(v(0.5, 2), v), tuple(v(0.5, 2)))),
    (
        "tuple_behavior",
        lambda v: (
            isinstance(v(1, 2), tuple),
            len(v(1, 2)),
            v(1, 2)[0],
            v(1, 2)[-1],
            v(1, 2)[:],
        ),
    ),
    (
        "equality",
        lambda v: (
            v(0, 1) == v(0.0, 1),
            v(0, 1) == (0, 1),
            (0, 1) == v(0, 1),
            v(0, 1) != v(42, 1),
        ),
    ),
    ("repr", lambda v: repr(v(0.567, 1.234))),
    ("addition", lambda v: v(-1.5, 0) + v(2, 2)),
    ("subtraction", lambda v: v(10.625, 0.125) - v(10, 0)),
    ("scalar_multiply", lambda v: v(0.5, 3) * 10),
    ("reverse_multiply", lambda v: 10.0 * v(0.5, 3)),
    ("dot_product", lambda v: v(10, 10) * v(0.5, 3)),
    ("negation", lambda v: -v(10, -10)),
    ("abs", lambda v: (abs(v(6, 8)), abs(v(0, 0)), abs(v(2.5, 6)))),
    ("rotate", lambda v: [v(0, 1).rotate(a) for a in (0, 90, -90, 180, 360)]),
    ("constructor_missing_arg", lambda v: v(0)),
    ("constructor_tuple_arg", lambda v: v((0, 1))),
]

NAVIGATOR_CASES = [
    ("initial_state", [("position",), ("heading",)]),
    ("goto_xy", [("goto", 100, -100)]),
    ("goto_tuple", [("goto", (100, -100))]),
    ("position_aliases", [("goto", 100, -100), ("pos",), ("position",)]),
    ("forward", [("forward", 150)]),
    ("backward", [("backward", 200)]),
    ("negative_forward", [("forward", -200)]),
    ("left", [("left", 90)]),
    ("right", [("right", 90)]),
    ("walk", [("forward", 100), ("left", 90), ("forward", 50)]),
    (
        "aliases",
        [
            ("fd", 10),
            ("bk", 5),
            ("back", 2),
            ("lt", 90),
            ("rt", 45),
            ("setpos", (3, 4)),
            ("setposition", 5, 6),
            ("seth", 30),
        ],
    ),
    ("heading_wrap", [("left", a) for a in (10, 20, -170, 300, -210, 34.3, 500)]),
    ("setheading", [("setheading", a) for a in (102.32, -123.23, -1000.34, 300000)]),
    ("home", [("goto", 30, -40), ("setheading", 30), ("home",)]),
    ("reset", [("goto", 30, -40), ("reset",)]),
    ("setx_sety", [("setx", -1023.2334), ("sety", 193323.234)]),
    ("distance_xy", [("distance", 30, 40)]),
    ("distance_tuple", [("distance", (0.22, 0.001))]),
    ("distance_navigator", [("distance", {"navigator": (30, 40)})]),
    (
        "towards_xy",
        [
            ("towards", x, y)
            for x, y in (
                (100, 0),
                (100, 100),
                (0, 100),
                (-100, 100),
                (-100, 0),
                (-100, -100),
                (0, -100),
                (100, -100),
            )
        ],
    ),
    ("towards_tuple", [("towards", (-100, -100))]),
    ("towards_navigator", [("towards", {"navigator": (30, 40)})]),
    ("degrees", [("degrees", 400), ("towards", 0, 100), ("left", 100)]),
    ("radians", [("radians",), ("towards", 0, 100), ("left", math.pi / 2)]),
    ("units_roundtrip", [("left", 90), ("radians",), ("degrees",)]),
    ("invalid_forward", [("forward", "invalid")]),
    ("invalid_right", [("right", "invalid")]),
    ("teleport", [("teleport", 20, -30), ("teleport", -20, 30)]),
]


def cases():
    for name, operation in VECTOR_CASES:
        yield Case(
            name,
            "Vec2D",
            lambda module, op=operation: op(module.Vec2D),
            expected_exception="TypeError" if name.startswith("constructor_") else None,
        )
    for name, operations in NAVIGATOR_CASES:
        required = tuple("TNavigator." + op[0] for op in operations)
        yield Case(
            name,
            "TNavigator",
            navigation(operations),
            required,
            "TypeError" if name.startswith("invalid_") else None,
        )
    for mode in ("logo", "world"):
        yield Case(
            "mode_" + mode,
            "TNavigator",
            navigation([("heading",), ("towards", 100, 0), ("forward", 10)], mode),
        )
    for method in ("goto", "distance", "towards"):
        yield Case(
            method + "_vector",
            "TNavigator",
            navigation([(method, {"vector": (30, 40)})]),
            ("Vec2D",),
        )
