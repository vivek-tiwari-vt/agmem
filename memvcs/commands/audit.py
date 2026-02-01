"""
agmem audit - Tamper-evident audit trail.

Read and verify the append-only audit log.
"""

import argparse

from ..commands.base import require_repo
from ..core.audit import read_audit, verify_audit


class AuditCommand:
    """Show and verify the tamper-evident audit log."""

    name = "audit"
    help = "Show and verify the tamper-evident audit log"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "-n", "--max",
            type=int,
            default=50,
            metavar="N",
            help="Show at most N entries (default 50)",
        )
        parser.add_argument(
            "--verify",
            action="store_true",
            help="Verify the audit chain and report first tampering point",
        )

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        if args.verify:
            valid, first_bad = verify_audit(repo.mem_dir)
            if valid:
                print("Audit log chain is valid.")
                return 0
            print(f"Audit log chain invalid at entry index {first_bad}.")
            return 1

        entries = read_audit(repo.mem_dir, max_entries=args.max)
        if not entries:
            print("No audit entries.")
            return 0
        for e in entries:
            ts = e.get("timestamp", "")
            op = e.get("operation", "")
            details = e.get("details", {})
            detail_str = " ".join(f"{k}={v}" for k, v in sorted(details.items()) if v is not None)
            print(f"{ts}  {op}  {detail_str}")
        return 0
