# Release and Publishing

Shelfline is being prepared for PyPI publishing. Do not upload a release until
the project metadata, release notes, and PyPI Trusted Publishing setup have all
been reviewed.

## Pre-Release Checklist

- Confirm the intended package version in `pyproject.toml`.
- Run the focused packaging and CLI tests:

  ```powershell
  python -m pytest tests/test_package.py tests/test_cli.py -v
  ```

- Run the full test suite when preparing an actual release:

  ```powershell
  python -m pytest -v
  ```

- Remove old build artifacts so the release starts from a clean `dist`
  directory.
- Build the source distribution and wheel.
- Check the distributions with Twine.
- Review README rendering and release notes.
- Commit the version bump and release documentation updates before tagging.

## Local Build

Install or update the local build tools:

```powershell
python -m pip install --upgrade build twine
```

Build the package:

```powershell
python -m build
```

Validate the distributions:

```powershell
python -m twine check dist/*
```

## Trusted Publishing Setup

Shelfline should publish to PyPI and TestPyPI through GitHub Actions Trusted
Publishing, not through long-lived API tokens.

On PyPI, create the project or pending publisher with these exact values:

- PyPI project name: `shelfline`
- Owner: `nikhilsahoo`
- Repository: `shelfline`
- Workflow name: `publish.yml`
- Environment name: `pypi`

On TestPyPI, create the project or pending publisher with these exact values:

- TestPyPI project name: `shelfline`
- Owner: `nikhilsahoo`
- Repository: `shelfline`
- Workflow name: `publish-testpypi.yml`
- Environment name: `testpypi`

The PyPI workflow lives at `.github/workflows/publish.yml`. It runs when a
GitHub Release is published, builds on Python 3.12, and uses
`pypa/gh-action-pypi-publish@release/v1` with GitHub OIDC permissions.

The TestPyPI workflow lives at `.github/workflows/publish-testpypi.yml`. It is
manual-only through `workflow_dispatch`, uses the `testpypi` environment, and
sets `repository-url` to `https://test.pypi.org/legacy/`.

## TestPyPI Dry Run

Use TestPyPI for a packaging dry run before the first real PyPI release and
before any release where packaging metadata changed.

Recommended dry-run flow:

1. Confirm the intended package version in `pyproject.toml`. TestPyPI and PyPI
   reject reusing a version that has already been uploaded to the same index.
2. Run the pre-release checks and local build validation.
3. Commit the release changes before publishing from GitHub Actions.
4. In GitHub Actions, run `Publish to TestPyPI` from the `main` branch.
5. Confirm the workflow publishes through the `testpypi` environment with
   Trusted Publishing.
6. Install from TestPyPI in a clean environment:

   ```powershell
   python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ shelfline
   ```

The `--extra-index-url` option is important because Shelfline's dependencies may
not all exist on TestPyPI; it allows dependencies to resolve from real PyPI
while the Shelfline package is installed from TestPyPI.

## Release Flow

1. Update `version` in `pyproject.toml` to the intended `X.Y.Z`.
2. Run the pre-release checks and local build validation.
3. Commit the release changes.
4. Create and push a `vX.Y.Z` tag.
5. Create a GitHub Release for `vX.Y.Z`.
6. Publishing the GitHub Release triggers `.github/workflows/publish.yml`, which
   builds the distributions and publishes them to PyPI through Trusted
   Publishing.
7. Confirm the package page and release files on PyPI.

## Post-Release Check

After the package is available on PyPI, verify installation with `pipx`:

```powershell
pipx install shelfline
shelfline --help
```
