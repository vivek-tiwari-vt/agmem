"""
agmem prove - Generate zero-knowledge proofs (stub).

Prove properties of memory (keyword, freshness) without revealing content.
"""

import argparse

from ..commands.base import require_repo
from ..core.zk_proofs import prove_keyword_containment, prove_memory_freshness


class ProveCommand:
    """Generate zk proofs for memory properties."""

    name = "prove"
    help = "Prove a property of memory without revealing content (zk stub)"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--memory", "-m", required=True, help="Memory file path (under current/)"
        )
        parser.add_argument(
            "--property",
            "-p",
            choices=["keyword", "freshness"],
            required=True,
            help="Property to prove",
        )
        parser.add_argument("--value", "-v", help="Value (e.g. keyword or ISO date)")
        parser.add_argument("--output", "-o", help="Output proof file path")

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        path = repo.current_dir / args.memory
        if not path.exists():
            print(f"Memory file not found: {args.memory}")
            return 1

        out = args.output or "proof.bin"
        out_path = Path(out)
        if not out_path.is_absolute():
            out_path = repo.root / out_path

        if args.property == "keyword":
            if not args.value:
                print("--value required for keyword (the keyword)")
                return 1
            ok = prove_keyword_containment(path, args.value, out_path)
        else:
            if not args.value:
                print("--value required for freshness (ISO date)")
                return 1
            ok = prove_memory_freshness(path, args.value, out_path)

        if not ok:
            print("Proof generation not yet implemented (zk backend required).")
            return 1
        print(f"Proof written to {out_path}")
        return 0
