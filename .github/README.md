# GitHub Actions

## CI and PyPI Publish (`ci-and-publish.yml`)

- **On push/PR to `main` or `master`**: runs lint (Black, Flake8) and tests on Python 3.8–3.12.
- **On release published**: runs the same checks, then builds sdist + wheel and publishes to PyPI.

### PyPI setup (token-based)

1. Create an API token at [PyPI](https://pypi.org/manage/account/token/) (scope: entire account or project `agmem`).
2. In GitHub: **Settings** → **Secrets and variables** → **Actions** → **New repository secret**.
3. Name: `PYPI_API_TOKEN`, Value: your token (starts with `pypi-`).
4. Save. The workflow will use it when publishing.

### Releasing (automated)

1. Bump version in `pyproject.toml` and commit to `main`.
2. Create and push a version tag. That creates the GitHub Release and triggers PyPI publish:

   ```bash
   git tag v0.1.2
   git push origin v0.1.2
   ```

   The workflow **Create Release on Tag** creates the release (with generated notes); **CI and PyPI Publish** then builds and publishes to PyPI.

   **Manual alternative:** Create a release in the GitHub UI (Releases → Draft a new release, choose tag, publish). The same PyPI publish runs.

### If CI fails on Lint (Black)

Format the code locally before pushing:

```bash
pip install -e ".[dev]"
black .
git add -A && git commit -m "Format with black" && git push
```

### Optional: TestPyPI

To also publish to TestPyPI on release, add a trusted publisher for TestPyPI and a job that uses `repository-url: https://test.pypi.org/legacy/` with the `pypa/gh-action-pypi-publish` action.
