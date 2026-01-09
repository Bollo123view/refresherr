# CI/CD Workflows

This document describes the automated CI/CD workflows configured for the Refresherr project.

## Overview

The project uses GitHub Actions for continuous integration and deployment. Two main workflows are configured:

1. **PR Validation** - Runs on every pull request to ensure code quality
2. **Docker Build and Release** - Builds and publishes Docker images on main branch and tags

## PR Validation Workflow

**File:** `.github/workflows/pr-validation.yml`

**Triggers:**
- Pull requests to `main` or `develop` branches
- Pushes to `main` or `develop` branches

**Jobs:**

### 1. Frontend Tests (`frontend-tests`)
- Runs on: Ubuntu Latest
- Node.js: 18
- Steps:
  - Checkout code
  - Setup Node.js with npm caching
  - Install dependencies (`npm ci`)
  - Run tests (`npm test`)
  - Generate coverage report
  - Upload coverage to Codecov

**Purpose:** Validates React/TypeScript frontend code with Vitest and React Testing Library.

### 2. Backend Tests (`backend-tests`)
- Runs on: Ubuntu Latest
- Python: 3.11
- Steps:
  - Checkout code
  - Setup Python with pip caching
  - Install dependencies (app requirements + test requirements)
  - Run pytest
  - Upload coverage to Codecov

**Purpose:** Validates Python backend code with pytest, including API endpoint tests.

### 3. Frontend Build (`frontend-build`)
- Runs on: Ubuntu Latest
- Node.js: 18
- Steps:
  - Checkout code
  - Setup Node.js with npm caching
  - Install dependencies
  - Build production bundle (`npm run build`)
  - Verify build artifacts exist
  - Upload dist artifacts (retained for 7 days)

**Purpose:** Ensures the frontend builds successfully for production.

### 4. Docker Build (`docker-build`)
- Runs on: Ubuntu Latest
- Steps:
  - Checkout code
  - Setup Docker Buildx
  - Build Docker image (no push)
  - Load and test image
  - Verify container starts successfully
  - Check health endpoint

**Purpose:** Validates the complete Docker image builds and runs.

### 5. Config Validation (`config-validation`)
- Runs on: Ubuntu Latest
- Python: 3.11
- Steps:
  - Checkout code
  - Install PyYAML
  - Validate all YAML files in `config/` directory

**Purpose:** Ensures configuration files have valid YAML syntax.

### 6. Lint Check (`lint-check`)
- Runs on: Ubuntu Latest
- Node.js: 18
- Steps:
  - Checkout code
  - Install frontend dependencies
  - Run TypeScript type checking

**Purpose:** Validates TypeScript types (non-blocking).

### 7. PR Validation Summary (`pr-validation-summary`)
- Runs on: Ubuntu Latest
- Depends on: All previous jobs
- Steps:
  - Check status of all jobs
  - Fail if any required job failed
  - Report success if all passed

**Purpose:** Provides a single status check for the entire PR validation.

## Docker Build and Release Workflow

**File:** `.github/workflows/docker-release.yml`

**Triggers:**
- Pushes to `main` branch
- Version tags (`v*.*.*`)
- Manual workflow dispatch

**Registry:** GitHub Container Registry (ghcr.io)

**Jobs:**

### 1. Build and Push (`build-and-push`)
- Runs on: Ubuntu Latest
- Permissions: Read contents, write packages
- Steps:
  - Checkout code
  - Setup Docker Buildx
  - Login to GitHub Container Registry
  - Extract metadata (tags, labels)
  - Build and push Docker image
  - Generate deployment summary

**Tags Generated:**
- Branch name (e.g., `main`)
- Semver tags for releases (e.g., `v1.2.3`, `1.2`, `1`)
- SHA-based tags (e.g., `main-abc1234`)

**Purpose:** Builds and publishes Docker images to GitHub Container Registry.

### 2. Test Deployment (`test-deployment`)
- Runs on: Ubuntu Latest
- Depends on: `build-and-push`
- Steps:
  - Pull the newly built image
  - Run container with test configuration
  - Wait for startup
  - Verify container is running
  - Cleanup

**Purpose:** Validates the published image can be pulled and runs successfully.

### 3. Create Release (`create-release`)
- Runs on: Ubuntu Latest
- Depends on: `build-and-push`, `test-deployment`
- Runs only for: Version tags (`v*.*.*`)
- Permissions: Write contents
- Steps:
  - Checkout code with full history
  - Generate release notes from git log
  - Create GitHub Release with notes

**Purpose:** Automatically creates GitHub releases for tagged versions.

## Caching Strategy

Both workflows use GitHub Actions caching:

- **npm packages**: Cached based on `package-lock.json`
- **pip packages**: Cached automatically by setup-python action
- **Docker layers**: Cached using GitHub Actions cache (`type=gha`)

This significantly speeds up CI runs by reusing dependencies.

## Status Checks

The following checks must pass before a PR can be merged:

1. ✅ Frontend Tests
2. ✅ Backend Tests
3. ✅ Frontend Build
4. ✅ Docker Build
5. ✅ Config Validation
6. ⚠️ Lint Check (optional, non-blocking)

## Running Workflows Locally

### Frontend Tests
```bash
cd refresherr-dashboard
npm install
npm test
```

### Backend Tests
```bash
cd app
pip install -r requirements.txt -r requirements-test.txt
pytest
```

### Frontend Build
```bash
cd refresherr-dashboard
npm install
npm run build
```

### Docker Build
```bash
docker build -t refresherr:test .
```

### Config Validation
```bash
for config in config/*.yaml; do
  python -c "import yaml; yaml.safe_load(open('$config'))"
done
```

## Troubleshooting

### Test Failures

**Frontend tests fail:**
- Check Node.js version (should be 18+)
- Clear npm cache: `npm clean-cache --force`
- Delete node_modules and reinstall: `rm -rf node_modules && npm install`

**Backend tests fail:**
- Check Python version (should be 3.11+)
- Ensure all dependencies installed: `pip install -r requirements.txt -r requirements-test.txt`
- Check for database schema issues

### Build Failures

**Frontend build fails:**
- Check TypeScript errors: `npx tsc --noEmit`
- Verify all dependencies are installed
- Check for missing assets or imports

**Docker build fails:**
- Ensure multi-stage build completes
- Check Node.js build stage succeeds
- Verify Python dependencies can install

### Workflow Permissions

If workflows fail with permission errors:
1. Check repository Settings → Actions → General
2. Ensure "Read and write permissions" is enabled
3. For GITHUB_TOKEN: Enable "Allow GitHub Actions to create and approve pull requests"

## Continuous Improvement

The CI/CD workflows are continuously improved to:
- Reduce build times through better caching
- Add more comprehensive tests
- Improve error reporting
- Enhance security scanning

See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to contribute to CI/CD improvements.

## Related Documentation

- [CONTRIBUTING.md](../CONTRIBUTING.md) - Contribution guidelines
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment guide
- [README.md](../README.md) - Project overview
