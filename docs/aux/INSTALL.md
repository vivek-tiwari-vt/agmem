# Installation Guide

## Quick Install

### From Source (Recommended for Development)

```bash
# Clone or extract the repository
cd /path/to/agmem

# Add to PYTHONPATH
export PYTHONPATH=/path/to/agmem:$PYTHONPATH

# Or install with pip
pip install /path/to/agmem

# Or install in development mode
pip install -e /path/to/agmem
```

### Using the CLI

Once installed, the `agmem` command is available:

```bash
# Verify installation
agmem --version

# Get help
agmem --help
```

## Manual Setup (No Installation)

If you can't install packages, you can run agmem directly:

```bash
# Set PYTHONPATH
cd /path/to/agmem
export PYTHONPATH=$(pwd):$PYTHONPATH

# Run commands
python -m memvcs.cli init
python -m memvcs.cli status
python -m memvcs.cli --help
```

Or create a shell alias:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias agmem='PYTHONPATH=/path/to/agmem python -m memvcs.cli'

# Then use normally
agmem init
agmem status
```

## Testing the Installation

```bash
# Test basic functionality
agmem init --author-name "Test" --author-email "test@example.com"
echo "Test content" > current/semantic/test.md
agmem add .
agmem commit -m "Test commit"
agmem log
```

## Troubleshooting

### Command not found

If `mem` command is not found after installation:

```bash
# Check if Python scripts directory is in PATH
python -c "import site; print(site.USER_BASE + '/bin')"

# Add to PATH
export PATH="$(python -c 'import site; print(site.USER_BASE + "/bin")'):$PATH"
```

### Import errors

If you see import errors:

```bash
# Verify PYTHONPATH is set correctly
echo $PYTHONPATH

# Make sure it includes the parent directory of memvcs
export PYTHONPATH=/path/to/agmem:$PYTHONPATH
```

### Permission errors

If you get permission errors during installation:

```bash
# Install for current user only
pip install --user /path/to/agmem

# Or use a virtual environment
python -m venv venv
source venv/bin/activate
pip install /path/to/agmem
```

## Dependencies

agmem has no required dependencies - it uses only Python standard library.

Optional dependencies:
- `dev`: For development (`pip install agmem[dev]`)

## Uninstallation

```bash
# If installed with pip
pip uninstall agmem

# If using PYTHONPATH, simply remove the directory
rm -rf /path/to/agmem
```
