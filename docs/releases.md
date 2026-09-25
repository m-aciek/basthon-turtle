# Releases

The [Release workflow](../.github/workflows/release.yml) builds a wheel and a
source distribution with `uv`, verifies both, publishes with PyPI Trusted
Publishing, and attaches the same files to the GitHub Release.

## One-time setup

Create GitHub Actions environments named `pypi` and `testpypi` under the
repository's **Settings → Environments**. Restrict the `pypi` environment to
version tags (`v*`). Allow the branches/tags you want to test in `testpypi`.
Leave required reviewers disabled if releases should finish automatically.

Register a GitHub Trusted Publisher for `basthon-turtle` on each service:

| Field | PyPI | TestPyPI |
| --- | --- | --- |
| Owner | `m-aciek` | `m-aciek` |
| Repository | `basthon-turtle` | `basthon-turtle` |
| Workflow filename | `release.yml` | `release.yml` |
| Environment | `pypi` | `testpypi` |

For an existing project, use **Manage → Publishing** on that service. If the
TestPyPI project does not exist, register a pending publisher through the
account's Publishing page, using `basthon-turtle` as the project name.
PyPI and TestPyPI require separate configuration. See the official guides for
[existing projects](https://docs.pypi.org/trusted-publishers/adding-a-publisher/)
and [new projects](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/).

No PyPI API token or GitHub personal access token is needed. The publishing job
alone gets `id-token: write` and requires OIDC with
`uv publish --trusted-publishing always`. A separate job uses GitHub's automatic
token with `contents: write` to create the GitHub Release. See
[uv's publishing guide](https://docs.astral.sh/uv/guides/package/).

## Publish a version

Prepare and commit the release: update `project.version` in `pyproject.toml`,
the changelog, and versioned wheel URLs in `docs/pyodide.md`. Once that commit
is ready, tag it and push the tag:

```console
git tag vX.Y.Z
git push origin vX.Y.Z
```

The workflow requires a stable `X.Y.Z` package version and an exactly matching
`vX.Y.Z` tag. A mismatch fails before building or publishing. Prerelease
automation and generated release notes are follow-up work.

The workflow:

1. Builds the sdist, then builds the wheel from that sdist, using
   `uv build --no-sources`. Twine checks metadata and the PyPI description.
2. Downloads those artifacts on Python 3.11, 3.12 and 3.14. Each archive is
   installed separately into a new virtual environment outside the checkout.
   Checks cover distribution versions, imports from site-packages, the startup
   hook, the runtime-install `turtle` shim, and static SVG drawing.
3. Checks both archives for notebook/Marimo CSS and JavaScript, standalone HTML,
   Pyodide transport code, and startup files. The sdist also needs its build
   metadata, documentation, and Pyodide example host files.
4. Publishes the downloaded, verified artifacts to PyPI without rebuilding.
5. Creates the matching GitHub Release and uploads both artifacts. If a release
   already exists, updates its artifacts and preserves its text and draft state.

These are distribution smoke tests, not a full runtime/browser matrix. The
existing [test workflow](testing.md) provides more extensive runtime coverage;
its jobs run independently. The release checks do not claim coverage of every
Python version allowed by package metadata.

## Test against TestPyPI

After `release.yml` is on the default branch, open **Actions → Release → Run
workflow** and select the branch or tag to test. Every manual run uses TestPyPI,
with the same build and verification steps. It never publishes to production
PyPI or creates a GitHub Release.

Use a stable version not already uploaded to TestPyPI if the package contents
have changed. TestPyPI, like PyPI, does not allow replacing an uploaded file.
After publishing, you can additionally test installation from the index:

```sh
uv venv /tmp/basthon-testpypi
uv pip install --python /tmp/basthon-testpypi/bin/python \
  --index-url https://test.pypi.org/simple/ --no-deps 'basthon-turtle==X.Y.Z'
cd /tmp
/tmp/basthon-testpypi/bin/python -I -c 'import turtle; print(turtle.__file__)'
```

The base package has no runtime dependencies; this command intentionally tests
it without renderer extras or another index.

## Local validation and retries

To run the artifact checks locally with Python 3.11+ and `uv` installed:

```sh
release_dist=$(mktemp -d)
uv build --no-sources --out-dir "$release_dist"
uvx --from 'twine>=6,<7' twine check --strict "$release_dist"/*
uv run --no-project --python 3.12 python tools/check_release.py \
  "$release_dist" --version "$(uv version --short)"
```

If publishing fails partway through, use **Re-run failed jobs** on the same
Actions run so it reuses the original artifacts. `uv publish` checks the target
index and skips files only when their contents match; changed files fail.
If only the GitHub Release step fails, re-run that failed job. Artifact storage
uses the repository's default retention period. Once those artifacts expire,
recover the exact published files before retrying; do not move a published tag
or try to replace a published version with a different build.
