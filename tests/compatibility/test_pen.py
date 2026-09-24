import copy
import types
import unittest
from unittest import mock

from tools import compatibility_report as report
from tools.compatibility_checks import Case
from tools.compatibility_pen import PEN_CASES, pen_cases, pen_instance, pen_sequence


class PenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference, cls.candidate = report.load_implementations()

    def test_selected_pen_behavior(self):
        for case in pen_cases():
            with self.subTest(case=case.name):
                reference = report.run_case(case, self.reference, self.reference)
                self.assertEqual(reference["status"], "compatible", reference)
                if case.name == "pen_snapshot":
                    continue  # Known difference; the baseline permits improvements.
                result = report.run_case(case, self.reference, self.candidate)
                self.assertEqual(result["status"], "compatible", result)

    def test_incomplete_pen_snapshot_is_a_failure(self):
        class IncompletePen(self.reference.TPen):
            def pen(self, *args, **kwargs):
                result = super().pen(*args, **kwargs)
                if isinstance(result, dict):
                    del result["resizemode"]
                return result

        case = next(case for case in pen_cases() if case.name == "pen_snapshot")
        result = report.run_case(
            case, self.reference, types.SimpleNamespace(TPen=IncompletePen)
        )
        self.assertEqual(result["status"], "incompatible")

    def test_intermediate_regression_is_not_hidden_by_restoring_width(self):
        class BrokenPen(self.reference.TPen):
            def pensize(self, width=None):
                if width == 5:
                    return None
                return super().pensize(width)

        case = Case(
            "width_roundtrip",
            "TPen",
            pen_sequence([("pensize", (5,), {}), ("pensize", (1,), {})]),
        )
        result = report.run_case(
            case, self.reference, types.SimpleNamespace(TPen=BrokenPen)
        )
        self.assertEqual(result["status"], "incompatible")

    def test_candidate_pen_logic_is_not_replaced_by_fixture(self):
        case = next(case for case in pen_cases() if case.name == "penup_pendown")
        with mock.patch.object(self.candidate.TPen, "penup", lambda self: None):
            result = report.run_case(case, self.reference, self.candidate)
        self.assertEqual(result["status"], "incompatible")

    def test_missing_pen_fails_every_applicable_case(self):
        for case in pen_cases():
            with self.subTest(case=case.name):
                result = report.run_case(case, self.reference, types.SimpleNamespace())
                self.assertEqual(result["status"], "missing")

    def test_case_input_dictionaries_are_isolated(self):
        original = copy.deepcopy(PEN_CASES)
        for case in pen_cases():
            first = report.run_case(case, self.reference, self.candidate)
            second = report.run_case(case, self.reference, self.candidate)
            self.assertEqual(first, second)
        self.assertEqual(PEN_CASES, original)

    def test_fixture_restores_existing_screen_even_on_error(self):
        module = self.candidate
        marker = object()
        emit = module.Screen._emit_live
        with mock.patch.dict(module.Singleton._instances, {module.Screen: marker}):
            with self.assertRaisesRegex(RuntimeError, "operation failed"):
                with pen_instance(module) as pen:
                    self.assertIsInstance(pen, module.Turtle)
                    self.assertIsNot(pen.screen, marker)
                    raise RuntimeError("operation failed")
            self.assertIs(module.Singleton._instances[module.Screen], marker)
            self.assertIs(module.Screen._emit_live, emit)


if __name__ == "__main__":
    unittest.main()
