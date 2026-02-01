# Contributing to agmem

Thank you for your interest in contributing to agmem! We welcome contributions from the community. This document provides guidelines and instructions for contributing.

## Code of Conduct

Please be respectful and constructive in all interactions. We aim to maintain a welcoming and inclusive community for all contributors.

## Getting Started

### Prerequisites
- Python 3.9+
- Git
- Virtual environment (recommended: `python -m venv venv`)

### Local Development Setup

1. **Fork the repository** on GitHub
2. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/agmem.git
   cd agmem
   ```

3. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

4. **Install development dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

5. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Code Style
- We use **black** for code formatting (100 character line length)
- We use **flake8** for linting
- We use **mypy** for type checking
- We use **bandit** for security scanning

Run all checks:
```bash
black . --line-length=100
flake8 memvcs tests
mypy memvcs
bandit -r memvcs
```

### Testing
Run the test suite:
```bash
pytest tests/ -v --cov=memvcs --cov-report=html
```

Specific test file:
```bash
pytest tests/test_repository.py -v
```

Single test:
```bash
pytest tests/test_repository.py::test_init -v
```

### Before Submitting

1. **Format your code:**
   ```bash
   black . --line-length=100
   ```

2. **Run linting:**
   ```bash
   flake8 memvcs tests
   ```

3. **Run type checking:**
   ```bash
   mypy memvcs
   ```

4. **Run security check:**
   ```bash
   bandit -r memvcs
   ```

5. **Run tests:**
   ```bash
   pytest tests/ -v
   ```

6. **Update documentation** if needed

## Commit Guidelines

- Use clear, descriptive commit messages
- Format: `type: description` (e.g., `fix: resolve blob integrity verification`)
- Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`
- Example:
  ```
  feat: add memory decay functionality
  
  - Implement exponential decay for episodic memories
  - Add decay command with customizable half-life
  - Update tests for decay module
  ```

## Pull Request Process

1. **Push to your fork:**
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Open a Pull Request** with a clear title and description
   - Reference any related issues (e.g., "Closes #123")
   - Describe the changes made
   - Explain the motivation and context

3. **Ensure all CI/CD checks pass:**
   - GitHub Actions will automatically run tests
   - All checks must pass before merging

4. **Respond to review feedback** promptly

## Reporting Issues

### Bug Reports
Include:
- Python version
- Steps to reproduce
- Expected behavior
- Actual behavior
- Error messages/tracebacks
- Environment details

### Feature Requests
Include:
- Use case and motivation
- Expected behavior
- Example usage (if applicable)

## Project Structure

```
agmem/
├── memvcs/              # Main package
│   ├── commands/        # CLI commands (40+)
│   ├── core/            # Core functionality
│   │   ├── storage/     # Storage backends
│   │   └── llm/         # LLM integrations
│   ├── integrations/    # External integrations (MCP, Web UI)
│   ├── retrieval/       # Retrieval strategies
│   └── utils/           # Utility functions
├── tests/               # Test suite (40+ test files)
├── docs/                # Documentation
├── examples/            # Usage examples
└── scripts/             # Utility scripts
```

## Key Technologies

- **Python 3.9+** - Primary language
- **pytest** - Testing framework
- **PyYAML** - Configuration and serialization
- **Ed25519** - Cryptographic signatures
- **zlib** - Compression
- **asyncio** - Asynchronous operations

## Memory Types

agmem supports three distinct memory types with different semantics:

1. **Episodic** - Chronological event logs (append-only)
2. **Semantic** - Fact/relationship stores (conflict detection)
3. **Procedural** - Instructions and skills (prefer-new merge strategy)

Ensure your changes respect these distinctions.

## Questions?

- Check existing issues and discussions
- Review documentation in `/docs`
- Open a discussion on GitHub

Thank you for contributing to agmem! 🚀
