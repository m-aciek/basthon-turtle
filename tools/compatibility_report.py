"""Headless API and behavior report against this interpreter's stdlib turtle."""

import argparse
import contextlib
import importlib.util
import inspect
import io
import json
import math
from pathlib import Path
import platform
import sys
import sysconfig

from .compatibility_checks import cases, observe


SCHEMA_VERSION = 1
BASELINE = Path(__file__).resolve().parents[1] / "tests/compatibility/baseline.json"
SECTIONS = ("Public API", "Vec2D API", "TNavigator API", "Vec2D", "TNavigator")


def load_implementations():
    if platform.python_implementation() != "CPython":
        raise RuntimeError("The reference requires a CPython interpreter")
    # Neither import turtle nor find_spec('turtle') is safe with our startup hook.
    path = Path(sysconfig.get_path("stdlib")) / "turtle.py"
    spec = importlib.util.spec_from_file_location("_compatibility_stdlib_turtle", path)
    reference = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(reference)
    except ImportError as error:
        raise RuntimeError(
            "Cannot load stdlib turtle; install this interpreter's Tkinter package "
            "(no display is needed)"
        ) from error
    from basthon import turtle as candidate

    if reference is candidate or Path(candidate.__file__).resolve() == path.resolve():
        raise RuntimeError("Reference and candidate must be independent modules")
    return reference, candidate


def public_names(module):
    if hasattr(module, "__all__"):
        return set(module.__all__)
    # Avoid imported helpers and modules if __all__ is unavailable.
    return {
        name
        for name, value in vars(module).items()
        if not name.startswith("_")
        and getattr(value, "__module__", None) == module.__name__
    }


def resolve(obj, path):
    for name in path.split("."):
        obj = getattr(obj, name, None)
    return obj


def signature(value):
    try:
        return inspect.signature(value)
    except (TypeError, ValueError):
        return None


def record(section, name, status, **details):
    return {"id": section + "/" + name, "section": section, "status": status, **details}


def api_checks(reference, candidate, names, section):
    records = []
    for name in sorted(names):
        ref, actual = resolve(reference, name), resolve(candidate, name)
        present = hasattr(candidate, name) if candidate is not None else False
        records.append(
            record(
                section,
                "symbol/" + name,
                "compatible" if present else "missing",
                reason="available" if present else "missing public symbol",
            )
        )
        if inspect.isclass(ref):
            records.append(
                record(
                    section,
                    "class/" + name,
                    "compatible" if inspect.isclass(actual) else "incompatible",
                    reason="class" if inspect.isclass(actual) else "not a class",
                )
            )
        if not callable(ref):
            continue
        expected = signature(ref)
        got = signature(actual) if callable(actual) else None
        if expected is None:
            status, reason = "not_applicable", "reference signature unavailable"
        elif not present:
            status, reason = "not_applicable", "symbol missing (reported above)"
        else:
            status = "compatible" if expected == got else "incompatible"
            reason = (
                "matching signature" if status == "compatible" else "signature differs"
            )
        records.append(
            record(
                section,
                "signature/" + name,
                status,
                reason=reason,
                reference=str(expected) if expected is not None else None,
                candidate=str(got) if got is not None else None,
            )
        )
    return records


def normalize(value):
    if isinstance(value, (tuple, list)):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("Unsupported observation type: " + type(value).__name__)


def equal_observations(left, right):
    if isinstance(left, dict) and isinstance(right, dict):
        # Exception text is diagnostic only; compare the exception type and trace.
        keys = set(left) - ({"message"} if "exception" in left else set())
        other_keys = set(right) - ({"message"} if "exception" in right else set())
        return keys == other_keys and all(
            equal_observations(left[k], right[k]) for k in keys
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(map(equal_observations, left, right))
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-7)
    return type(left) is type(right) and left == right


def exceptions(value):
    if isinstance(value, dict):
        if "exception" in value:
            yield value["exception"]
        else:
            for item in value.values():
                yield from exceptions(item)
    elif isinstance(value, list):
        for item in value:
            yield from exceptions(item)


def run_case(case, reference, candidate):
    required = (case.symbol,) + case.requires
    if any(resolve(reference, name) is None for name in required):
        return record(
            case.symbol,
            case.name,
            "not_applicable",
            reason="feature absent in this reference version",
        )
    expected = normalize(observe(lambda: case.run(reference)))
    expected_errors = [case.expected_exception] if case.expected_exception else []
    if list(exceptions(expected)) != expected_errors:
        raise RuntimeError(
            "Unexpected reference exception in " + case.name + ": " + repr(expected)
        )
    missing = sorted({name for name in required if resolve(candidate, name) is None})
    if missing:
        return record(
            case.symbol,
            case.name,
            "missing",
            reason="missing: " + ", ".join(missing),
            reference=expected,
            candidate=None,
        )
    try:
        actual = normalize(observe(lambda: case.run(candidate)))
    except TypeError as error:
        return record(
            case.symbol,
            case.name,
            "incompatible",
            reason=str(error),
            reference=expected,
            candidate={"unsupported_observation": str(error)},
        )
    compatible = equal_observations(expected, actual)
    return record(
        case.symbol,
        case.name,
        "compatible" if compatible else "incompatible",
        reason="observations match" if compatible else "observations differ",
        reference=expected,
        candidate=actual,
    )


def build_report(reference, candidate):
    names, candidate_names = public_names(reference), public_names(candidate)
    checks = api_checks(reference, candidate, names, "Public API")
    methods = {}
    for name in ("Vec2D", "TNavigator"):
        ref, actual = resolve(reference, name), resolve(candidate, name)
        # TNavigator is deliberately in scope even though CPython omits it from __all__.
        checks.extend(api_checks(reference, candidate, [name], name + " API"))
        ref_methods = {
            n for n in dir(ref) if not n.startswith("_") and callable(getattr(ref, n))
        }
        actual_methods = {
            n
            for n in dir(actual)
            if not n.startswith("_") and callable(getattr(actual, n))
        }
        checks.extend(api_checks(ref, actual, ref_methods, name + " API"))
        methods[name] = {
            "reference": sorted(ref_methods),
            "candidate": sorted(actual_methods),
            "extensions": sorted(actual_methods - ref_methods),
        }
    for case in cases():
        checks.append(run_case(case, reference, candidate))
    return {
        "schema_version": SCHEMA_VERSION,
        "reference": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "python_minor": ".".join(map(str, sys.version_info[:2])),
            "path": reference.__file__,
        },
        "candidate": {"path": candidate.__file__},
        "api": {
            "reference_names": sorted(names),
            "candidate_names": sorted(candidate_names),
            "missing_names": sorted(n for n in names if not hasattr(candidate, n)),
            "extensions": sorted(candidate_names - names),
            "reference_classes": sorted(
                n for n in names if inspect.isclass(resolve(reference, n))
            ),
            "candidate_classes": sorted(
                n for n in candidate_names if inspect.isclass(resolve(candidate, n))
            ),
            "methods": methods,
        },
        "checks": checks,
    }


def make_baseline(report):
    return {
        "schema_version": SCHEMA_VERSION,
        "python_minor": report["reference"]["python_minor"],
        "checks": {check["id"]: check["status"] for check in report["checks"]},
    }


def compare_baseline(report, baseline):
    if baseline["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Unsupported baseline schema")
    if baseline["python_minor"] != report["reference"]["python_minor"]:
        raise ValueError("Baseline requires CPython " + baseline["python_minor"])
    current = make_baseline(report)["checks"]
    previous = baseline["checks"]
    return {
        "regressions": sorted(
            key
            for key, status in previous.items()
            if status == "compatible" and current.get(key) != "compatible"
        ),
        "improvements": sorted(
            key
            for key, status in previous.items()
            if status in ("missing", "incompatible")
            and current.get(key) == "compatible"
        ),
        "new_checks": sorted(current.keys() - previous.keys()),
    }


def human_report(report):
    lines = [
        "CPython turtle compatibility",
        "",
        "Reference: CPython " + report["reference"]["version"],
        "Backend-independent behavior only; API presence does not imply working behavior.",
    ]
    for section in SECTIONS:
        checks = [c for c in report["checks"] if c["section"] == section]
        lines.extend(["", section])
        if section.endswith("API"):
            for kind, label in (
                ("symbol", "available symbols"),
                ("class", "public classes"),
                ("signature", "matching signatures"),
            ):
                selected = [
                    c
                    for c in checks
                    if c["id"].split("/")[1] == kind and c["status"] != "not_applicable"
                ]
                passed = sum(c["status"] == "compatible" for c in selected)
                lines.append(f"  {label}: {passed} / {len(selected)}")
        else:
            applicable = [c for c in checks if c["status"] != "not_applicable"]
            passed = sum(c["status"] == "compatible" for c in applicable)
            lines.extend(
                [
                    f"  applicable checks: {len(applicable)}",
                    f"  passed: {passed}",
                    f"  failed/missing: {len(applicable) - passed}",
                ]
            )
        lines.append(
            "  not applicable: "
            + str(sum(c["status"] == "not_applicable" for c in checks))
        )
    lines.extend(
        [
            "",
            "Extensions (not failures): " + ", ".join(report["api"]["extensions"]),
            "",
            "Failures:",
        ]
    )
    for check in report["checks"]:
        if check["status"] in ("incompatible", "missing"):
            detail = check["reason"]
            if "/signature/" in check["id"]:
                detail += f"; expected {check['reference']}, got {check['candidate']}"
            elif (
                check["section"] in ("Vec2D", "TNavigator")
                and check["candidate"] is not None
            ):
                errors = list(exceptions(check["candidate"]))
                if errors:
                    detail += "; " + ", ".join(errors)
            lines.append("  " + check["id"] + ": " + detail)
    if "baseline" in report:
        for category, entries in report["baseline"].items():
            lines.append(f"\nBaseline {category}: {len(entries)}")
            lines.extend("  " + entry for entry in entries)
        if report["baseline"]["improvements"]:
            lines.append(
                "Regenerate the baseline with --write-baseline to retain these improvements."
            )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", action="store_true", help="emit structured observations"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-baseline", nargs="?", const=BASELINE, type=Path)
    group.add_argument("--write-baseline", nargs="?", const=BASELINE, type=Path)
    args = parser.parse_args(argv)
    try:
        # Keep JSON parseable even if an implementation prints diagnostics.
        with (
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            report = build_report(*load_implementations())
        if args.check_baseline:
            report["baseline"] = compare_baseline(
                report, json.loads(args.check_baseline.read_text())
            )
        if args.write_baseline:
            args.write_baseline.write_text(
                json.dumps(make_baseline(report), indent=2, sort_keys=True) + "\n"
            )
    except (OSError, RuntimeError, TypeError, ValueError, KeyError) as error:
        parser.exit(2, f"compatibility report: {error}\n")
    print(
        json.dumps(report, indent=2, sort_keys=True)
        if args.json
        else human_report(report)
    )
    return int(bool(report.get("baseline", {}).get("regressions")))


if __name__ == "__main__":
    sys.exit(main())
