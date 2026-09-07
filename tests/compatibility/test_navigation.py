import copy
import math
import pickle
import unittest

from tools import compatibility_report as report
from tools.compatibility_checks import cases, navigation


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference, cls.candidate = report.load_implementations()

    def test_vector_and_supported_navigation_cases(self):
        for case in cases():
            if case.name == "teleport":
                continue  # Not implemented by Basthon yet.
            with self.subTest(case=case.name, symbol=case.symbol):
                result = report.run_case(case, self.reference, self.candidate)
                self.assertEqual(result["status"], "compatible", result)

    def test_turns_and_angle_units_in_all_modes(self):
        for mode in ("standard", "logo", "world"):
            for fullcircle in (360, 400, math.tau):
                with self.subTest(mode=mode, fullcircle=fullcircle):
                    run = navigation(
                        [
                            ("degrees", fullcircle),
                            ("left", fullcircle * 20 + fullcircle / 8),
                            ("forward", 30),
                            ("setheading", fullcircle * 1000 + fullcircle / 4),
                            ("forward", 40),
                            ("right", fullcircle * 2),
                            ("setheading", -fullcircle / 2),
                            ("radians",),
                            ("setheading", math.pi / 3),
                            ("back", 5),
                            ("home",),
                            ("reset",),
                        ],
                        mode,
                    )
                    self.assertTrue(
                        report.equal_observations(
                            run(self.reference), run(self.candidate)
                        )
                    )

    def test_position_is_a_vector_snapshot(self):
        nav = self.candidate.TNavigator()
        nav.goto(3, 4)
        position = nav.position()
        self.assertIsInstance(position, self.candidate.Vec2D)
        self.assertEqual(abs(position), 5)
        self.assertEqual(position + self.candidate.Vec2D(1, 2), (4, 6))
        nav.forward(10)
        self.assertEqual(position, (3, 4))
        self.assertEqual(nav.pos() - position, (10, 0))

    def test_vector_copy_and_pickle(self):
        vector = self.candidate.Vec2D(1.25, -2.5)
        copies = [copy.copy(vector), copy.deepcopy(vector)]
        copies.extend(
            pickle.loads(pickle.dumps(vector, protocol))
            for protocol in range(pickle.HIGHEST_PROTOCOL + 1)
        )
        for result in copies:
            self.assertIsInstance(result, self.candidate.Vec2D)
            self.assertEqual(result, vector)

    def test_vector_is_exported(self):
        self.assertIn("Vec2D", self.candidate.__all__)
