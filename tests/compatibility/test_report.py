import contextlib
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

from basthon.turtle import _startup
from tools import compatibility_report as report
from tools.compatibility_checks import Case, cases, navigation


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference, cls.candidate = report.load_implementations()
        cls.report = report.build_report(cls.reference, cls.candidate)

    def test_reference_bypasses_startup_alias(self):
        with mock.patch.dict(sys.modules):
            _startup.install()
            reference, candidate = report.load_implementations()
            self.assertIs(sys.modules["turtle"], candidate)
            self.assertIsNot(reference, candidate)
            self.assertNotEqual(
                Path(reference.__file__).resolve(), Path(candidate.__file__).resolve()
            )
            self.assertEqual(reference.TNavigator.__module__, reference.__name__)

    def test_missing_tkinter_is_actionable(self):
        with mock.patch.dict(sys.modules, {"tkinter": None}):
            with self.assertRaisesRegex(
                RuntimeError, "install this interpreter's Tkinter"
            ):
                report.load_implementations()

    def test_report_never_initializes_a_backend(self):
        with (
            mock.patch("tkinter.Tk", side_effect=AssertionError("Tk opened")) as tk,
            mock.patch(
                "_tkinter.create", side_effect=AssertionError("Tcl opened")
            ) as tcl,
            mock.patch(
                "webbrowser.open", side_effect=AssertionError("browser opened")
            ) as browser,
            mock.patch.object(
                self.candidate, "Screen", side_effect=AssertionError("Screen created")
            ) as screen,
            mock.patch.object(self.candidate._notebook, "create_session") as notebook,
            mock.patch.object(
                self.candidate._standalone, "create_session"
            ) as standalone,
        ):
            report.build_report(*report.load_implementations())
        for backend in (tk, tcl, browser, screen, notebook, standalone):
            backend.assert_not_called()

    def test_missing_symbol_and_whole_behavior_section(self):
        candidate = types.SimpleNamespace()
        checks = report.api_checks(self.reference, candidate, ["Vec2D"], "API")
        self.assertEqual(checks[0]["status"], "missing")
        case = Case("construction", "Vec2D", lambda m: m.Vec2D(1, 2))
        self.assertEqual(
            report.run_case(case, self.reference, candidate)["status"], "missing"
        )
        # A missing class must account for every applicable case, including error cases.
        vector_checks = [
            report.run_case(c, self.reference, candidate)
            for c in cases()
            if c.symbol == "Vec2D"
        ]
        self.assertEqual(len(vector_checks), 14)
        self.assertTrue(all(c["status"] == "missing" for c in vector_checks))

    def test_extensions_are_not_failures(self):
        candidate = types.ModuleType("extended_turtle")
        candidate.__dict__.update(vars(self.reference))
        candidate.__all__ = [*self.reference.__all__, "svg", "restart"]
        candidate.svg = lambda: None
        candidate.restart = lambda: None
        result = report.build_report(self.reference, candidate)
        self.assertEqual(result["api"]["extensions"], ["restart", "svg"])
        self.assertTrue(
            all(
                c["status"] in ("compatible", "not_applicable")
                for c in result["checks"]
            )
        )

    def test_fallback_excludes_imports(self):
        module = types.ModuleType("example")
        exec(
            "import math\nfrom math import sin\ndef public(): pass\ndef _private(): pass",
            vars(module),
        )
        self.assertEqual(report.public_names(module), {"public"})
        module.__all__ = ["sin"]
        self.assertEqual(report.public_names(module), {"sin"})

    def test_equal_and_different_behavior(self):
        case = Case("value", "Vec2D", lambda m: m.Vec2D(1, 2))
        same = report.run_case(case, self.reference, self.reference)
        different = report.run_case(
            case, self.reference, types.SimpleNamespace(Vec2D=lambda x, y: (y, x))
        )
        self.assertEqual(same["status"], "compatible")
        self.assertEqual(different["status"], "incompatible")

    def test_intermediate_state_is_not_hidden_by_home(self):
        class BrokenNavigator(self.reference.TNavigator):
            def forward(self, distance):
                pass

        case = Case("walk_home", "TNavigator", navigation([("forward", 10), ("home",)]))
        result = report.run_case(
            case, self.reference, types.SimpleNamespace(TNavigator=BrokenNavigator)
        )
        self.assertEqual(result["status"], "incompatible")

    def test_unexpected_candidate_return_type_is_a_failure(self):
        case = Case("value", "Vec2D", lambda m: m.Vec2D(1, 2))
        candidate = types.SimpleNamespace(Vec2D=lambda x, y: object())
        result = report.run_case(case, self.reference, candidate)
        self.assertEqual(result["status"], "incompatible")
        self.assertIn("Unsupported observation type", result["reason"])

    def test_float_tolerance_and_json_normalization(self):
        self.assertTrue(
            report.equal_observations(
                {"position": (0.0, 100.0)}, {"position": [1e-10, 100.00000001]}
            )
        )
        self.assertFalse(report.equal_observations([100.0], [100.01]))
        self.assertFalse(report.equal_observations(True, 1))
        self.assertFalse(report.equal_observations([1], [1, 2]))
        self.assertEqual(report.normalize(self.reference.Vec2D(1, 2)), [1, 2])

    def test_exception_type_matters_but_message_does_not(self):
        case = Case(
            "invalid", "Vec2D", lambda m: m.Vec2D(), expected_exception="TypeError"
        )

        def raise_error(error):
            raise error("different message")

        for error, status in ((TypeError, "compatible"), (ValueError, "incompatible")):
            candidate = types.SimpleNamespace(Vec2D=lambda: raise_error(error))
            self.assertEqual(
                report.run_case(case, self.reference, candidate)["status"], status
            )

    def test_unexpected_reference_error_is_a_tooling_error(self):
        case = Case("broken", "Vec2D", lambda m: m.Vec2D())
        with self.assertRaisesRegex(RuntimeError, "Unexpected reference exception"):
            report.run_case(case, self.reference, self.candidate)

    def test_reference_feature_absent_is_not_applicable(self):
        case = Case("future", "Vec2D", lambda m: None, ("Vec2D.future_method",))
        self.assertEqual(
            report.run_case(case, self.reference, self.candidate)["status"],
            "not_applicable",
        )

    def test_signature_comparison_and_uninspectable_reference(self):
        expected = types.SimpleNamespace(f=lambda x=1: x, builtin=dict)
        actual = types.SimpleNamespace(f=lambda y=1: y, builtin=dict)
        checks = report.api_checks(expected, actual, ["f", "builtin"], "API")
        signatures = {c["id"]: c["status"] for c in checks if "/signature/" in c["id"]}
        self.assertEqual(
            signatures,
            {
                "API/signature/f": "incompatible",
                "API/signature/builtin": "not_applicable",
            },
        )

    def test_baseline_regressions_improvements_and_deleted_checks(self):
        current = {
            "reference": {"python_minor": "3.14"},
            "checks": [
                {"id": "pass", "status": "compatible"},
                {"id": "fail", "status": "incompatible"},
            ],
        }
        baseline = report.make_baseline(current)
        self.assertEqual(report.compare_baseline(current, baseline)["regressions"], [])
        current["checks"][0]["status"] = "not_applicable"
        current["checks"][1]["status"] = "compatible"
        comparison = report.compare_baseline(current, baseline)
        self.assertEqual(comparison["regressions"], ["pass"])
        self.assertEqual(comparison["improvements"], ["fail"])
        current["checks"].pop(0)
        self.assertEqual(
            report.compare_baseline(current, baseline)["regressions"], ["pass"]
        )
        baseline["python_minor"] = "3.13"
        with self.assertRaisesRegex(ValueError, "requires CPython 3.13"):
            report.compare_baseline(current, baseline)

    def test_ids_are_unique_and_output_is_stable(self):
        ids = [c["id"] for c in self.report["checks"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(
            self.report, report.build_report(self.reference, self.candidate)
        )

    def test_cli_json_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline_path = Path(directory) / "baseline.json"
            for option in ("--write-baseline", "--check-baseline"):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = report.main(["--json", option, str(baseline_path)])
                self.assertEqual(status, 0)
                self.assertEqual(
                    json.loads(output.getvalue())["checks"], self.report["checks"]
                )
            broken = copy.deepcopy(self.report)
            passing = next(c for c in broken["checks"] if c["status"] == "compatible")
            passing["status"] = "incompatible"
            with mock.patch.object(report, "build_report", return_value=broken):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(
                        report.main(["--check-baseline", str(baseline_path)]), 1
                    )


if __name__ == "__main__":
    unittest.main()
