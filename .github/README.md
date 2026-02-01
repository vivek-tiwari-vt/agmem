# GitHub Actions

## CI and PyPI Publish (`ci-and-publish.yml`)

- **On push/PR to `main` or `master`**: runs lint (Black, Flake8) and tests on Python 3.8–3.12.
- **On release published**: runs the same checks, then builds sdist + wheel and publishes to PyPI.

### PyPI setup (Trusted Publishing, no token)

1. On [PyPI](https://pypi.org), open your project **agmem** (or create it).
2. Go to **Project settings → Publishing → Add a new trusted publisher**.
3. Configure:
   - **Owner**: your GitHub org or username
   - **Repository name**: your repo (e.g. `agmem`)
   - **Workflow name**: `ci-and-publish.yml`
   - **Environment name**: leave empty (or create an environment `pypi` in the repo for approval rules)
4. Save. Future **Published** releases will be uploaded by the workflow automatically.

### Releasing (automated)

1. Bump version in `pyproject.toml` and commit to `main`.
2. Create and push a version tag. That creates the GitHub Release and triggers PyPI publish:

   ```bash
   git tag v0.1.2
   git push origin v0.1.2
   ```

   The workflow **Create Release on Tag** creates the release (with generated notes); **CI and PyPI Publish** then builds and publishes to PyPI.

   **Manual alternative:** Create a release in the GitHub UI (Releases → Draft a new release, choose tag, publish). The same PyPI publish runs.

### Optional: TestPyPI

To also publish to TestPyPI on release, add a trusted publisher for TestPyPI and a job that uses `repository-url: https://test.pypi.org/legacy/` with the `pypa/gh-action-pypi-publish` action.
