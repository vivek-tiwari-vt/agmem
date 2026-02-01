#!/usr/bin/env python3
"""
agmem Demo Script

This script demonstrates the full agmem workflow.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from memvcs.core.repository import Repository  # noqa: E402


def print_section(title):
    """Print a section header."""
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)
    print()


def main():
    """Run the demo."""

    # Create temporary directory
    demo_dir = Path(tempfile.mkdtemp(prefix="agmem-demo-"))
    print(f"Demo directory: {demo_dir}")

    try:
        # Step 1: Initialize repository
        print_section("1. Initialize Repository")

        repo = Repository.init(
            path=demo_dir, author_name="DemoAgent", author_email="demo@example.com"
        )
        print(f"Initialized repository at: {repo.mem_dir}")
        print(f"Working directory: {repo.current_dir}")

        # Step 2: Create memory files
        print_section("2. Create Memory Files")

        # Episodic memory
        episodic_file = repo.current_dir / "episodic" / "session1.md"
        episodic_file.write_text(
            """# Session 1

## User Interaction
- User asked about Python best practices
- Explained PEP 8 guidelines
- User preferred concise examples

## Key Learnings
- User is experienced developer
- Prefers practical over theoretical
"""
        )
        print(f"Created: {episodic_file.relative_to(demo_dir)}")

        # Semantic memory
        semantic_file = repo.current_dir / "semantic" / "user-preferences.md"
        semantic_file.write_text(
            """# User Preferences

## Communication Style
- Prefers concise, direct communication
- Likes code examples
- Experienced developer

## Technical Interests
- Python
- Code quality
- Best practices
"""
        )
        print(f"Created: {semantic_file.relative_to(demo_dir)}")

        # Procedural memory
        procedural_file = repo.current_dir / "procedural" / "coding-workflow.md"
        procedural_file.write_text(
            """# Coding Workflow

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
"""
        )
        print(f"Created: {procedural_file.relative_to(demo_dir)}")

        # Step 3: Stage files
        print_section("3. Stage Files")

        staged = repo.stage_directory()
        print(f"Staged {len(staged)} file(s):")
        for f in staged:
            print(f"  - {f}")

        # Step 4: Commit
        print_section("4. Commit Changes")

        commit_hash = repo.commit("Initial memory: user preferences and coding workflow")
        print(f"Created commit: {commit_hash[:16]}...")
        print("Message: Initial memory: user preferences and coding workflow")

        # Step 5: View log
        print_section("5. View Commit History")

        log = repo.get_log(max_count=5)
        for entry in log:
            print(f"{entry['short_hash']} - {entry['message']}")
            print(f"  Author: {entry['author']}")
            print(f"  Date: {entry['timestamp']}")
            print()

        # Step 6: Create branch
        print_section("6. Create and Switch Branch")

        repo.refs.create_branch("experiment")
        print("Created branch: experiment")

        repo.refs.set_head_branch("experiment")
        print(f"Switched to branch: {repo.refs.get_current_branch()}")

        # Step 7: Make changes on branch
        print_section("7. Make Changes on Branch")

        # Modify existing file
        semantic_file.write_text(
            semantic_file.read_text()
            + """
## New Learning
- User also likes TypeScript
- Interested in static typing
"""
        )
        print("Modified: semantic/user-preferences.md")

        # Stage and commit
        repo.stage_file("semantic/user-preferences.md")
        commit_hash = repo.commit("Added TypeScript preference")
        print(f"Created commit: {commit_hash[:16]}...")

        # Step 8: Switch back and merge
        print_section("8. Merge Branch")

        repo.refs.set_head_branch("main")
        print(f"Switched to branch: {repo.refs.get_current_branch()}")

        # Get commits for merge
        main_commit = repo.refs.get_branch_commit("main")
        exp_commit = repo.refs.get_branch_commit("experiment")

        print(f"Main commit: {main_commit[:16]}...")
        print(f"Experiment commit: {exp_commit[:16]}...")
        print("Merge would happen here (fast-forward possible)")

        # Step 9: View final state
        print_section("9. Final State")

        log = repo.get_log(max_count=5)
        print(f"Total commits: {len(log)}")
        print()
        print("Branches:")
        for branch in repo.refs.list_branches():
            current = "* " if branch == repo.refs.get_current_branch() else "  "
            print(f"{current}{branch}")

        # Step 10: Show content
        print_section("10. Memory Content")

        print("User Preferences:")
        print("-" * 40)
        print(semantic_file.read_text())

        # Summary
        print_section("Demo Complete")

        print(f"Repository location: {demo_dir}")
        print()
        print("Key agmem concepts demonstrated:")
        print("  - Repository initialization")
        print("  - Memory file organization (episodic/semantic/procedural)")
        print("  - Staging and committing")
        print("  - Branching for experimentation")
        print("  - Commit history and navigation")
        print()
        print("To explore further:")
        print(f"  cd {demo_dir}")
        print("  agmem log              # View history")
        print("  agmem status           # Check status")
        print("  agmem branch           # List branches")
        print()
        print(f"To clean up: rm -rf {demo_dir}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Don't clean up so user can explore
        pass


if __name__ == "__main__":
    main()
