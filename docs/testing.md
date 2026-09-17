# Tests and CI

The `Tests` workflow runs on pushes, pull requests, and manual dispatches.
Job names identify the environment and, for host Python tests, the interpreter.
Matrix jobs use `fail-fast: false` so one failure does not cancel other versions
or environments.

| Job | Runtime | Scope |
| --- | --- | --- |
| Core | Python 3.11, 3.12, 3.14 | Base package, colors, SVG and rendering commands with fake transports, startup hooks, wheel/sdist contents, headless navigation and compatibility report tests |
| Notebook / AnyWidget | Python 3.12, `[notebook]` | Notebook, SVG fallback and mocked Marimo behavior; real AnyWidget state, messages and IPython cell events |
| Standalone / WebSocket | Python 3.12, `[standalone]` | Standalone unit tests; real HTTP serving, WebSocket command delivery and event callbacks |
| Sidecar | Python 3.12, `[sidecar]` | Real Sidecar and AnyWidget construction, state and cleanup |
| Pyodide / Chromium | Python 3.12, Node.js 24, Chromium | Python transport tests, Node.js worker regressions, and drawing and keyboard callbacks in the checkout-backed Pyodide example with normal and delayed iframe startup |

The core matrix is representative, not an assertion that every version allowed
by package metadata has been tested. The current test tooling uses Python 3.11+
features such as `tomllib`. Older versions allowed by `requires-python` are not
validated by this initial workflow.

The separate `CPython turtle compatibility` workflow continues to enforce the
existing Python 3.14 baseline and upload detailed observations. Running its
test infrastructure on other versions does not apply the 3.14 baseline to them.
See [the compatibility guide](compatibility.md).

AnyWidget and Sidecar integration checks exercise real Python dependencies with
the display function replaced by a mock. They do not validate frontend widget
rendering or JupyterLab panel placement. Pyodide uses a real browser and the
versioned runtime URL configured in `examples/pyodide/worker.mjs`; it requires
network access to download that runtime. Browser screenshots, diagnostics and
Playwright traces are uploaded as `pyodide-browser-results`.

## Running locally

Run commands from the repository root in a fresh virtual environment. Installing
the package is required: its startup hook makes stdlib demo imports use this
implementation of `turtle`.

```sh
python -m pip install . 'coverage>=7.6,<8' uv
python -m coverage run -m unittest discover -s tests/core -v
python -m coverage run --append -m unittest discover -s tests/compatibility -v
python -m coverage report
```

For each optional environment, use a separate virtual environment to preserve
dependency isolation. For example, the notebook job runs:

```sh
python -m pip install '.[notebook]' 'coverage>=7.6,<8'
python -m coverage run -m unittest discover -s tests -p test_notebook.py -v
python -m coverage run --append -m unittest discover -s tests/integration -p test_notebook.py -v
```

Replace `notebook` with `standalone` for WebSocket tests. For Sidecar, install
`.[sidecar]` and run only the integration command with `test_sidecar.py`.
Integration tests intentionally live outside recursive unit-test discovery;
missing dependencies fail their explicit CI job instead of silently skipping it.
Keep new base-package tests in `tests/core/` and environment integration tests
in the corresponding `tests/integration/test_*.py` file.

The browser job requires Node.js on `PATH` in addition to Python:

```sh
python -m pip install . 'coverage>=7.6,<8' playwright
python -m playwright install --with-deps chromium
python -m coverage run -m unittest discover -s tests -p test_pyodide.py -v
python -m unittest discover -s tests/integration -p test_browser.py -v
```

For an existing Chromium installation, set
`PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH` to its executable. A compatible Node.js
executable can be selected with `PLAYWRIGHT_NODEJS_PATH`.

## Coverage

Coverage is informational: test failures fail CI, but no minimum coverage
percentage is enforced. Each test job prints its coverage and uploads a uniquely
named data file. The `Coverage summary` job combines these files, writes a table
to the workflow summary, and uploads HTML and XML as `python-coverage-report`.
If a test job fails, the summary labels the available coverage as potentially
incomplete.

`.coveragerc` measures Python statements and branches in `basthon.turtle`,
including server threads. Installed-package paths are mapped back to checkout
paths when combining data. Coverage excludes tests and compatibility tooling;
it does not measure JavaScript or Python executing inside Pyodide. Imports
performed by the package startup hook before coverage starts also remain
unmeasured. Per-environment reports can therefore warn that the already imported
top-level module was not measured when a job exercises only a backend module.

To combine downloaded `coverage-*` artifacts, extract their `.coverage.*` files
into the repository root and run:

```sh
python -m coverage combine
python -m coverage report
python -m coverage html
python -m coverage xml
```

Open `htmlcov/index.html` to inspect missing lines and branches. The path mapping
and data combination follow [Coverage.py's configuration](https://coverage.readthedocs.io/en/latest/config.html)
and [combination commands](https://coverage.readthedocs.io/en/latest/commands/cmd_combine.html).

Minimum/latest dependencies, Python prereleases, additional Python versions,
per-version CPython baselines, and a coverage threshold or ratchet are follow-up
work. The initial workflow installs one compatible dependency set per job.
