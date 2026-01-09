# Contributing to Refresherr

Thank you for your interest in contributing to Refresherr! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Commit Messages](#commit-messages)

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code. Please be respectful and constructive in all interactions.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/refresherr.git
   cd refresherr
   ```
3. **Create a branch** for your changes:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Setup

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for frontend development)
- Python 3.11+ (for backend development)
- Git

### Local Development Environment

#### Backend Development

```bash
# Navigate to app directory
cd app

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt

# Run tests
pytest

# Run scanner locally
python -m cli run
```

#### Frontend Development

```bash
# Navigate to dashboard directory
cd refresherr-dashboard

# Install dependencies
npm install

# Run development server
npm run dev

# Run tests
npm test

# Run tests in watch mode
npm run test:watch

# Build for production
npm run build
```

### Using Development Configuration

Use the development configuration file for local testing:

```bash
# Copy development config
cp config/config.dev.yaml config/config.yaml

# Set development environment variables
export DRYRUN=true
export SCAN_INTERVAL=30
```

## Testing

### Running Frontend Tests

```bash
cd refresherr-dashboard

# Run all tests
npm test

# Run with coverage
npm run test:coverage

# Watch mode for development
npm run test:watch
```

### Running Backend Tests

```bash
cd app

# Run all tests
pytest

# Run with coverage
pytest --cov=refresher --cov-report=html

# Run specific test file
pytest tests/test_api_endpoints.py

# Run specific test
pytest tests/test_api_endpoints.py::test_health_endpoint
```

### Writing Tests

#### Frontend Tests

- Place tests in `refresherr-dashboard/src/test/`
- Name test files: `*.test.tsx` or `*.test.ts`
- Use React Testing Library for component tests
- Mock external dependencies and API calls

Example:
```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import MyComponent from '../MyComponent';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
```

#### Backend Tests

- Place tests in `app/tests/`
- Name test files: `test_*.py`
- Use pytest fixtures from `conftest.py`
- Test API endpoints and business logic

Example:
```python
def test_api_endpoint(client):
    """Test an API endpoint."""
    response = client.get('/api/endpoint')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert 'expected_field' in data
```

## Pull Request Process

### Before Submitting

1. **Run all tests** and ensure they pass:
   ```bash
   # Frontend
   cd refresherr-dashboard && npm test
   
   # Backend
   cd app && pytest
   ```

2. **Build the project** to ensure no build errors:
   ```bash
   # Frontend
   cd refresherr-dashboard && npm run build
   
   # Docker
   docker build -t refresherr:test .
   ```

3. **Update documentation** if you've made changes to:
   - Configuration options
   - API endpoints
   - User-facing features

4. **Validate configuration files**:
   ```bash
   python -c "import yaml; yaml.safe_load(open('config/config.sample.yaml'))"
   ```

### Submitting a Pull Request

1. **Push your changes** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Open a Pull Request** on GitHub with:
   - Clear title describing the change
   - Detailed description of what changed and why
   - Link to any related issues
   - Screenshots for UI changes

3. **Ensure CI passes**: All automated checks must pass:
   - ✅ Frontend tests
   - ✅ Backend tests
   - ✅ Frontend build
   - ✅ Docker build
   - ✅ Configuration validation

4. **Address review feedback** promptly

5. **Squash commits** if requested before merging

### PR Title Format

Use conventional commit format for PR titles:

- `feat: Add new feature`
- `fix: Fix bug in component`
- `docs: Update documentation`
- `test: Add tests for feature`
- `chore: Update dependencies`
- `refactor: Refactor code structure`
- `ci: Update CI configuration`

## Coding Standards

### Frontend (TypeScript/React)

- Use TypeScript for type safety
- Follow React best practices and hooks guidelines
- Use functional components
- Keep components small and focused
- Write self-documenting code with clear variable names
- Add JSDoc comments for complex functions

### Backend (Python)

- Follow PEP 8 style guide
- Use type hints where appropriate
- Write docstrings for functions and classes
- Keep functions focused and single-purpose
- Use meaningful variable and function names

### Configuration

- Keep configuration files in YAML format
- Add comments explaining complex options
- Provide example values
- Document environment variable alternatives

## Commit Messages

Write clear, descriptive commit messages:

```
feat: Add automated testing for dashboard API

- Add pytest configuration and fixtures
- Create tests for /api/config and /api/stats endpoints
- Add test coverage reporting
- Update CI workflow to run backend tests

Closes #123
```

### Commit Message Format

```
<type>: <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `test`: Adding or updating tests
- `chore`: Maintenance tasks
- `refactor`: Code refactoring
- `ci`: CI/CD changes
- `perf`: Performance improvements

## Questions?

If you have questions or need help:

1. Check existing [Issues](https://github.com/Bollo123view/refresherr/issues)
2. Open a new [Discussion](https://github.com/Bollo123view/refresherr/discussions)
3. Join our community chat (if available)

Thank you for contributing to Refresherr! 🎉
