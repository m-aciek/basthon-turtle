# Developing the compatibility report

From the checkout, using CPython 3.14 with Tkinter installed:

```console
python -m tools.compatibility_report
python -m tools.compatibility_report --json
python -m tools.compatibility_report --check-baseline
python -m unittest discover -s tests/compatibility -v
```

No third-party Python dependencies, display, Tk initialization, or browser are
needed. The stdlib module imports Tkinter, so an interpreter built without it
cannot run the report. CI uses CPython 3.14 on Linux without a display.

The reference is the running interpreter's `turtle.py`, located with
`sysconfig.get_path("stdlib")` and loaded with
`importlib.util.spec_from_file_location()` under a private module name.
Basthon is imported explicitly as `basthon.turtle`. Neither the checkout's
`turtle.py` shim nor the installed `.pth` startup alias can substitute the
reference. The report includes both source paths and the full interpreter
version; it never uses the adjacent CPython checkout as its runtime reference.

The report measures backend-independent compatibility only. Public module names
and signatures are inspected, but behavioral checks cover only `Vec2D` and bare
`TNavigator`. It does not measure `TPen`, `Turtle`, screen behavior, Tk, rendering,
SVG, browsers, or events. Finding a name or a matching signature is not evidence
that the corresponding function works. There is no combined compatibility score.

The module inventory uses CPython's `__all__`; availability means that the
candidate exposes that attribute, even if its own `__all__` omits it. Both export
lists are included in JSON. Without `__all__`, only public functions/classes
defined in that module are selected, excluding imported helpers. Candidate
exports absent from the reference are extensions, never failures. For example,
`svg()` and `restart()` do not reduce compatibility. The classes and public
methods of `Vec2D` and `TNavigator` are also inspected separately; CPython does
not export `TNavigator` in `__all__`. Inherited public methods are included.
Signature matching uses `inspect.signature()` equality, including defaults and
parameter names. A permissive `(*args, **kwargs)` signature therefore differs;
this metric measures signature equality, not every possible call's validity.
Uninspectable reference signatures are marked `not_applicable`.

Cases in `tools/compatibility_checks.py` are guided by `TestVec2D` and
`TestTNavigator` in CPython's `Lib/test/test_turtle.py` (inspected in the adjacent
checkout). They use positions and headings instead of `_orient` or `_position`.
No adapters implement movement or attach screens to make the candidate pass.
Pickling, pen-dependent circle behavior, and private/Tk tests are omitted.
Navigator cases supply sequences of public calls to the same runner for each
implementation. Tagged arguments construct each implementation's own vectors
or other navigators. Each call's return value and public state are recorded,
including intermediate states, and execution stops at the first exception.
Missing APIs fail gracefully. Features absent from the reference version are
`not_applicable`; unexpected reference exceptions are tooling errors.

Tuple-like coordinate results become JSON arrays; a navigator need not store
`Vec2D` internally. Numeric results use relative tolerance `1e-9` and absolute
tolerance `1e-7`. Exception types are compared, with messages retained only as
diagnostics. Implementation stdout/stderr is suppressed in the CLI to keep JSON
parseable; this report does not measure printed diagnostics.

The initial report is a baseline: known incompatibilities are expected.
The first measurement on CPython 3.14.0 is **114/126** module symbols available,
**80/114** matching inspectable signatures on available symbols, **0/14** passing
`Vec2D` cases, and **7/33** passing `TNavigator` cases. `Vec2D` is absent. Bare
Basthon navigators do not update coordinates through their movement hooks,
turns need screen attributes, navigator arguments to `distance()`/`towards()`
fail, and `teleport()` is missing. These results do not describe `Turtle` behavior.

`tests/compatibility/baseline.json` stores individual check IDs and statuses,
scoped to a CPython minor version. `--check-baseline` exits with status 1 if a
previously compatible check fails, becomes inapplicable, or disappears. Known
failures do not fail CI. Improvements and new checks are listed; improvements
are accepted automatically. Tooling errors and version mismatches exit with
status 2. Ordinary report generation exits successfully despite incompatibilities.
CI uploads the detailed JSON observations as an artifact.

After reviewing improvements, regenerate and inspect the baseline diff:

```console
python -m tools.compatibility_report --write-baseline
git diff -- tests/compatibility/baseline.json
```

Do not regenerate it merely to silence regressions. Keep case IDs stable when
extending coverage. Both baseline options accept an optional path, allowing
separate baselines and CI jobs for additional CPython versions later. The tools
are checkout-local and do not change the package's supported Python versions.
