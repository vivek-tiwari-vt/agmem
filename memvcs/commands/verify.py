"""
agmem verify - Belief consistency and cryptographic commit verification.

Scans semantic memories for logical contradictions; optionally verifies commit Merkle/signatures.
"""

import argparse
from pathlib import Path

from ..commands.base import require_repo
from ..core.consistency import ConsistencyChecker, ConsistencyResult


class VerifyCommand:
    """Verify belief consistency and/or cryptographic integrity of commits."""

    name = "verify"
    help = "Scan semantic memories for contradictions; optionally verify commit signatures"

    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            "--consistency",
            "-c",
            action="store_true",
            help="Check semantic memories for contradictions",
        )
        parser.add_argument(
            "--crypto",
            action="store_true",
            help="Verify Merkle tree and signatures for commits",
        )
        parser.add_argument(
            "--ref",
            metavar="REF",
            help="Commit or ref to verify (with --crypto); default HEAD",
        )
        parser.add_argument(
            "--llm",
            action="store_true",
            help="Use LLM for triple extraction (requires OpenAI)",
        )

    @staticmethod
    def _run_crypto_verify(repo, ref: str = None) -> int:
        """Run cryptographic verification. Returns 0 if all OK, 1 on failure."""
        from ..core.crypto_verify import verify_commit, load_public_key

        if ref:
            commit_hash = repo.resolve_ref(ref)
            if not commit_hash:
                print(f"Ref not found: {ref}")
                return 1
        else:
            head = repo.refs.get_head()
            if head["type"] == "branch":
                commit_hash = repo.refs.get_branch_commit(head["value"])
            else:
                commit_hash = head.get("value")
            if not commit_hash:
                print("No commit to verify (empty repo).")
                return 0
        pub = load_public_key(repo.mem_dir)
        ok, err = verify_commit(
            repo.object_store, commit_hash, public_key_pem=pub, mem_dir=repo.mem_dir
        )
        if ok:
            print(f"Commit {commit_hash[:8]} verified (Merkle + signature OK).")
            return 0
        print(f"Commit {commit_hash[:8]} verification failed: {err}")
        return 1

    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code

        run_consistency = args.consistency
        run_crypto = args.crypto
        if not run_consistency and not run_crypto:
            run_consistency = True

        exit_code = 0

        if run_crypto:
            if VerifyCommand._run_crypto_verify(repo, args.ref) != 0:
                exit_code = 1

        if run_consistency:
            checker = ConsistencyChecker(repo, llm_provider="openai" if args.llm else None)
            result = checker.check(use_llm=args.llm)

            print(f"Checked {result.files_checked} semantic file(s)")
            if result.valid:
                print("No contradictions found.")
            else:
                exit_code = 1
                print(f"\nFound {len(result.contradictions)} contradiction(s):")
                for i, c in enumerate(result.contradictions, 1):
                    print(f"\n[{i}] {c.reason}")
                    print(
                        f"    {c.triple1.source}:{c.triple1.line}: {c.triple1.subject} {c.triple1.predicate} {c.triple1.obj}"
                    )
                    print(
                        f"    {c.triple2.source}:{c.triple2.line}: {c.triple2.subject} {c.triple2.predicate} {c.triple2.obj}"
                    )
                print("\nUse 'agmem repair --strategy confidence' to attempt auto-fix.")

        return exit_code
