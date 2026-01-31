#!/bin/bash
# agmem Basic Workflow Example
# This script demonstrates the basic agmem workflow

set -e

echo "=== agmem Basic Workflow Example ==="
echo

# Create a temporary directory for the example
EXAMPLE_DIR=$(mktemp -d)
cd "$EXAMPLE_DIR"

echo "Working in: $EXAMPLE_DIR"
echo

# Initialize repository
echo "1. Initialize repository"
agmem init --author-name "ExampleAgent" --author-email "agent@example.com"
echo

# Create some memory files
echo "2. Create memory files"
mkdir -p current/episodic current/semantic current/procedural

cat > current/episodic/session1.md << 'EOF'
# Session 1 - 2026-01-31

## User Interaction
- User asked about Python best practices
- Explained PEP 8 guidelines
- User preferred concise examples

## Key Learnings
- User is experienced developer
- Prefers practical over theoretical
- Interested in code quality
EOF

cat > current/semantic/user-preferences.md << 'EOF'
# User Preferences

## Communication Style
- Prefers concise, direct communication
- Likes code examples
- Experienced developer

## Technical Interests
- Python
- Code quality
- Best practices
EOF

cat > current/procedural/coding-workflow.md << 'EOF'
# Coding Workflow

## When Writing Code
1. Follow PEP 8 guidelines
2. Add type hints
3. Include docstrings
4. Write tests

## Code Review Checklist
- [ ] Passes linting
- [ ] Has tests
- [ ] Documentation updated
- [ ] No security issues
EOF

echo "Created memory files:"
find current -type f
echo

# Stage files
echo "3. Stage files"
agmem add .
echo

# Check status
echo "4. Check status"
agmem status
echo

# Commit
echo "5. Commit changes"
agmem commit -m "Initial memory: user preferences and coding workflow"
echo

# View log
echo "6. View commit log"
agmem log
echo

# Create a branch
echo "7. Create experiment branch"
agmem branch experiment
agmem checkout experiment
echo

# Make changes
echo "8. Make changes on experiment branch"
cat >> current/semantic/user-preferences.md << 'EOF'

## New Learning
- User also likes TypeScript
- Interested in static typing
EOF

agmem add .
agmem commit -m "Added TypeScript preference"
echo

# View branches
echo "9. List branches"
agmem branch
echo

# Switch back to main
echo "10. Switch back to main"
agmem checkout main
echo

# Merge
echo "11. Merge experiment branch"
agmem merge experiment
echo

# View final log
echo "12. Final commit log"
agmem log
echo

# Show content
echo "13. Show user preferences"
cat current/semantic/user-preferences.md
echo

echo "=== Example Complete ==="
echo "Repository location: $EXAMPLE_DIR"
echo
echo "To clean up: rm -rf $EXAMPLE_DIR"
