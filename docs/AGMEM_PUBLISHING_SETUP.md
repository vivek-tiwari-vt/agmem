# PyPI Trusted Publishing Setup

The `ci-and-publish.yml` workflow uses **PyPI Trusted Publishing** (OIDC) to publish packages without API tokens. You need to configure this on PyPI to allow your GitHub repository to upload releases.

## 1. If the project `agmem` ALREADY exists on PyPI

1. Log in to [pypi.org](https://pypi.org/).
2. Go to your project's publishing settings: `https://pypi.org/manage/project/agmem/settings/publishing/`
3. Scroll to **"Add a new publisher"** and select **GitHub**.
4. Fill in the details:
   - **Owner**: `vivek-tiwari-vt`
   - **Repository name**: `agmem`
   - **Workflow name**: `ci-and-publish.yml`
   - **Environment name**: *Leave this blank* (unless you uncommented `environment: pypi` in the YAML).
5. Click **Add**.

## 2. If the project does NOT exist on PyPI yet

You cannot "register" a package via OIDC directly for the very first upload *unless* you use "Pending Publishers".

### Option A: Use Pending Publishers (Recommended)
1. Go to [https://pypi.org/manage/account/publishing/](https://pypi.org/manage/account/publishing/)
2. Click **Add a new pending publisher**.
3. Fill in the details:
   - **Project name**: `agmem`
   - **Owner**: `vivek-tiwari-vt`
   - **Repository name**: `agmem`
   - **Workflow name**: `ci-and-publish.yml`
   - **Environment name**: *Leave blank*.
4. Click **Add**.
5. The next time your GitHub Action runs for a release, PyPI will create the project for you.

### Option B: Manual First Release
1. Build the package locally:
   ```bash
   pip install build twine
   python -m build
   ```
2. Upload manually (requires your username/password or an API token):
   ```bash
   twine upload dist/*
   ```
3. Once created, follow the steps in **Section 1** to enable automation for future releases.

## 3. Triggering the Release

The workflow runs when a **GitHub Release** is published.

1. **Tag**: Push a tag starting with `v` (e.g., `v0.1.2`).
   ```bash
   git tag v0.1.2
   git push origin v0.1.2
   ```
   *(This triggers the `release-on-tag.yml` workflow, which creates the GitHub Release)*

2. **Release**: The `release-on-tag` workflow will create a GitHub Release.
3. **Publish**: The creation of that Release triggers `ci-and-publish.yml`, which runs tests and then uploads to PyPI (if the Trusted Publisher is set up).

## Troubleshooting

- **"OpenID Connect not supported"**: You forgot to set up the Trusted Publisher on PyPI.
- **"File already exists"**: You are trying to publish a version (`0.1.0` or `0.1.1`) that is already on PyPI. Bump the version in `pyproject.toml` and `memvcs/__init__.py` before tagging.
