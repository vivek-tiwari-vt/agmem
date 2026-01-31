#!/usr/bin/env python3
"""
agmem - Agentic Memory Version Control System

A Git-inspired version control system for AI agent memory artifacts.

Usage:
    agmem init                    Initialize a new repository
    agmem add <file>              Stage files for commit
    agmem commit -m "message"     Save staged changes
    agmem status                  Show working tree status
    agmem log                     Show commit history
    agmem branch                  List branches
    agmem checkout <branch>       Switch branches
    agmem merge <branch>          Merge branches
    agmem diff                    Show changes
"""

import argparse
import sys
from typing import List

from .commands.init import InitCommand
from .commands.add import AddCommand
from .commands.commit import CommitCommand
from .commands.status import StatusCommand
from .commands.log import LogCommand
from .commands.branch import BranchCommand
from .commands.checkout import CheckoutCommand
from .commands.merge import MergeCommand
from .commands.diff import DiffCommand
from .commands.show import ShowCommand
from .commands.reset import ResetCommand
from .commands.tag import TagCommand
from .commands.tree import TreeCommand
from .commands.stash import StashCommand
from .commands.clean import CleanCommand
from .commands.blame import BlameCommand
from .commands.reflog import ReflogCommand
from .commands.mcp import McpCommand
from .commands.search import SearchCommand
from .commands.clone import CloneCommand
from .commands.push import PushCommand
from .commands.pull import PullCommand
from .commands.remote import RemoteCommand
from .commands.serve import ServeCommand
from .commands.test import TestCommand
from .commands.fsck import FsckCommand
from .commands.graph import GraphCommand
from .commands.daemon import DaemonCommand
from .commands.garden import GardenCommand


# List of available commands
COMMANDS = [
    InitCommand,
    AddCommand,
    CommitCommand,
    StatusCommand,
    LogCommand,
    BranchCommand,
    CheckoutCommand,
    MergeCommand,
    DiffCommand,
    ShowCommand,
    ResetCommand,
    TagCommand,
    TreeCommand,
    StashCommand,
    CleanCommand,
    BlameCommand,
    ReflogCommand,
    McpCommand,
    SearchCommand,
    CloneCommand,
    PushCommand,
    PullCommand,
    RemoteCommand,
    ServeCommand,
    TestCommand,
    FsckCommand,
    GraphCommand,
    DaemonCommand,
    GardenCommand,
]


def create_parser() -> argparse.ArgumentParser:
    """Create the main argument parser."""
    parser = argparse.ArgumentParser(
        prog='agmem',
        description='agmem - Agentic Memory Version Control System',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  agmem init                              Initialize a new repository
  agmem add episodic/session.md           Stage a file
  agmem add .                             Stage all changes
  agmem commit -m "Learned user prefs"    Save snapshot
  agmem status                            Show current status
  agmem log                               Show commit history
  agmem branch experiment                 Create a branch
  agmem checkout experiment               Switch to branch
  agmem merge experiment                  Merge branch into current
  agmem diff                              Show unstaged changes
  agmem diff HEAD~1 HEAD                  Show changes between commits
  agmem show HEAD                         Show commit details
  agmem tag v1.0                          Create a tag
  agmem reset --hard HEAD~1               Reset to previous commit
  agmem tree                              Show directory tree visually

For more information: https://github.com/vivek-tiwari-vt/agmem
        """
    )
    
    parser.add_argument(
        '--version', '-v',
        action='version',
        version='%(prog)s 0.1.0'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )
    
    # Create subparsers for commands
    subparsers = parser.add_subparsers(
        dest='command',
        help='Available commands',
        metavar='COMMAND'
    )
    
    # Add each command
    for cmd_class in COMMANDS:
        cmd_parser = subparsers.add_parser(
            cmd_class.name,
            help=cmd_class.help
        )
        cmd_class.add_arguments(cmd_parser)
    
    return parser


def main(args: List[str] = None) -> int:
    """Main entry point."""
    parser = create_parser()
    parsed_args = parser.parse_args(args)
    
    # No command specified
    if not parsed_args.command:
        parser.print_help()
        return 0
    
    # Find and execute the command
    for cmd_class in COMMANDS:
        if cmd_class.name == parsed_args.command:
            try:
                return cmd_class.execute(parsed_args)
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                return 130
            except Exception as e:
                if parsed_args.verbose:
                    import traceback
                    traceback.print_exc()
                else:
                    print(f"Error: {e}")
                return 1
    
    # Unknown command
    print(f"Unknown command: {parsed_args.command}")
    return 1


if __name__ == '__main__':
    sys.exit(main())
