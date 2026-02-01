# agmem - Agentic Memory Version Control System

[![PyPI version](https://img.shields.io/pypi/v/agmem.svg)](https://pypi.org/project/agmem/)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Git for AI Agent Memories**

agmem is a version control system specifically designed for AI agent memory artifacts. It brings Git's proven concepts—commits, branches, merging, and distributed collaboration—to the world of agent episodic logs, semantic knowledge, and procedural workflows.

## Why agmem?

AI agents accumulate vast amounts of memory: conversation histories, learned facts, user preferences, and problem-solving strategies. But unlike code, agent memory lacks:

- **Version history** - See what an agent learned and when
- **Branching** - Experiment safely with different memory strategies
- **Merging** - Combine knowledge from multiple agents
- **Collaboration** - Share and fork agent memories
- **Rollback** - Undo when agents learn the wrong things

agmem solves all of these problems with a familiar Git-like interface.

## Features

- ✅ **Git-like workflow** — `init`, `add`, `commit`, `status`, `log`, `branch`, `checkout`, `merge`, `diff`, `show`, `reset`, `tag`, `stash`, `reflog`, `blame`, `tree`, `clean`
- ✅ **HEAD~n** — Walk parent chain: `agmem log HEAD~5`, `agmem show HEAD~1`
- ✅ **Branch/tag names with `/`** — Git-style refs: `feature/test`, `releases/v1` (path-validated)
- ✅ **Content-addressable storage** — SHA-256 deduplication like Git
- ✅ **Memory-type-aware merging** — Episodic append, semantic consolidate, procedural prefer-new
- ✅ **Remote (file://)** — `clone`, `push`, `pull`, `remote`; pull merges into current branch; push conflict detection (non–fast-forward reject)
- ✅ **Search** — Semantic with `agmem[vector]`, or plain text over `current/` when vector deps missing
- ✅ **Knowledge graph** — `agmem graph` from wikilinks/tags; `--no-similarity`, `--format d3`, `--serve` (optional `agmem[web]`)
- ✅ **Integrity** — `agmem fsck` (objects, refs, vector store, Merkle/signature); `agmem verify --crypto`; path/ref/hash validation (no path traversal)
- ✅ **Cryptographic commit verification** — Merkle tree over blobs; Ed25519 signing of root; verify on checkout, pull, `verify`, `fsck`; Merkle proofs for single-blob verification
- ✅ **Encryption at rest** — Optional AES-256-GCM with Argon2id key derivation; hash-then-encrypt preserves deduplication
- ✅ **Tamper-evident audit trail** — Append-only hash-chained log (init, add, commit, checkout, merge, push, pull, config); `agmem audit` and `agmem audit --verify`
- ✅ **Multi-agent trust** — Trust store (full / conditional / untrusted) per public key; applied on pull/merge; clone copies remote keys
- ✅ **Conflict resolution** — `agmem resolve` with ours/theirs/both; conflicts persisted in `.mem/merge/`; path-safe
- ✅ **Differential privacy** — Epsilon/delta budget in `.mem/privacy_budget.json`; `--private` on `agmem distill` and `agmem garden` when enabled
- ✅ **Pack files & GC** — `agmem gc` (reachable from refs, prune loose, optional repack); pack format and index in core
- ✅ **Multi-provider LLM** — OpenAI and Anthropic via `memvcs.core.llm`; config/repo or env; used by gardener, distiller, consistency, merge
- ✅ **Temporal querying** — Point-in-time and range queries in temporal index; frontmatter timestamps
- ✅ **Federated collaboration** — `agmem federated push|pull` (stub) for coordinator-based summary sharing
- ✅ **Zero-knowledge proofs** — `agmem prove` (stub) for keyword containment and memory freshness
- ✅ **Daemon health** — Periodic Merkle verification in daemon loop; safe auto-remediation hooks
- ✅ **GPU acceleration** — Vector store detects GPU for embedding model when available
- ✅ **Optional** — `serve`, `daemon` (watch + auto-commit), `garden` (episode archival), MCP server; install extras as needed

## Quick Start

### Installation

**From PyPI** ([pypi.org/project/agmem](https://pypi.org/project/agmem/)):

```bash
pip install agmem
```

Or install from source:

```bash
git clone https://github.com/vivek-tiwari-vt/agmem.git
cd agmem
pip install -e .
```

### Initialize a Repository

```bash
agmem init
```

This creates a `.mem/` directory and a `current/` working directory with subdirectories for different memory types:

```
.mem/                      # Repository internals
├── objects/               # Content-addressable storage
├── refs/                  # Branch and tag references
├── staging/               # Staging area
├── index.json             # Staging index
└── config.json            # Repository configuration

current/                   # Working directory
├── episodic/              # Session logs, conversation history
├── semantic/              # Facts, user preferences, knowledge
├── procedural/            # Workflows, prompt templates
├── checkpoints/           # Agent state snapshots
└── session-summaries/     # AI-generated summaries
```

### Basic Workflow

```bash
# Add memory files
agmem add episodic/session-2026-01-31.md
agmem add semantic/user-preferences.md

# Or add all changes
agmem add .

# Check status
agmem status

# Commit changes
agmem commit -m "Learned user prefers dark mode and Python"

# View history
agmem log

# Create a branch for experimentation
agmem branch experiment
agmem checkout experiment

# Make changes and commit
agmem add .
agmem commit -m "Experimenting with new workflow"

# Switch back and merge
agmem checkout main
agmem merge experiment

# See who changed each line of a memory file (like git blame)
agmem blame current/semantic/user-preferences.md

# Stash work in progress, then restore
agmem stash push -m "WIP"
agmem stash list
agmem stash pop

# View HEAD history (reflog)
agmem reflog
```

## Commands

All commands are listed below. Highlights: **`agmem blame <file>`** (who changed each line), **`agmem daemon`** (watch + optional auto-commit), **`agmem garden`** (episode archival & consolidation), **`agmem fsck`** (integrity check). See [Inspection & maintenance](#inspection--maintenance) for blame, daemon, and garden details.

### Core (Git-like)

| Command | Description |
|---------|-------------|
| `agmem init` | Initialize a new repository |
| `agmem add <file>` | Stage files (paths under `current/` validated) |
| `agmem commit -m "msg"` | Save staged changes |
| `agmem status` | Show working tree status |
| `agmem log [ref]` | Commit history; supports `HEAD~n`, `--oneline`, `-n` |
| `agmem branch` | List branches |
| `agmem branch <name>` | Create branch (names like `feature/test` allowed) |
| `agmem checkout <ref>` | Switch branch or detached commit |
| `agmem merge <branch>` | Merge into current branch |
| `agmem diff [ref1 [ref2]]` | Show changes |
| `agmem show <object>` | Show commit/blob/tree (supports `HEAD~n`) |
| `agmem tag <name>` | Create tag at HEAD |
| `agmem reset <ref>` | Reset HEAD or file |
| `agmem tree [ref]` | Directory tree of `current/` |
| `agmem stash` | push / pop / list |
| `agmem clean -f` | Remove untracked files |
| `agmem blame <file>` | **Who changed each line** — commit hash, author, line number, content (like `git blame`) |
| `agmem reflog` | HEAD change history (branch/checkout/commit) |

### Remote & integrity

| Command | Description |
|---------|-------------|
| `agmem clone <url> [dir]` | Clone repo (file:// URLs); path-validated; copies remote public keys |
| `agmem remote add <name> <url>` | Add remote |
| `agmem remote show` | List remotes |
| `agmem push <remote> <branch>` | Push branch (refs validated); rejects non–fast-forward |
| `agmem pull [--remote <name>] [--branch <b>]` | Fetch and merge into current branch; optional crypto/trust checks |
| `agmem fsck` | Check objects, refs, optional vector store, Merkle roots and signatures |
| `agmem verify [ref]` | Belief consistency (contradictions); use `--crypto` to verify commit Merkle/signature |
| `agmem audit [--verify] [--max n]` | Show tamper-evident audit log; `--verify` checks hash chain |
| `agmem resolve [path]` | Resolve merge conflicts (ours/theirs/both); path under `current/` |
| `agmem gc [--dry-run] [--prune-days n]` | Garbage collection: delete unreachable loose objects; optional repack |
| `agmem prove --memory <path> --property keyword\|freshness --value <v> [-o out]` | Generate ZK proofs (stub) |
| `agmem federated push\|pull` | Federated collaboration (stub; requires coordinator in config) |

### Optional (install extras)

| Command | Extra | Description |
|---------|-------|-------------|
| `agmem search <query>` | `agmem[vector]` | Semantic search; else plain text over `current/` |
| `agmem graph` | — | Knowledge graph from wikilinks/tags; `--no-similarity` skips vector |
| `agmem graph --serve` | `agmem[web]` | Serve graph UI (same as `agmem serve`) |
| `agmem serve` | `agmem[web]` | Web UI for history and diffs |
| `agmem daemon` | `agmem[daemon]` | **Watch `current/`** — optional auto-commit after debounce; `daemon run` / `status` / `start` / `stop` |
| `agmem garden` | — | **Episode archival & consolidation** — archive old episodic files, merge semantic facts; `--dry-run` supported |
| `agmem mcp` | `agmem[mcp]` | MCP server for Cursor/Claude |

### Refs and optional extras

- **Branch and tag names** can include `/` (e.g. `feature/test`, `releases/v1`); the resolved path must stay under `refs/heads` or `refs/tags` (Git-style).
- **HEAD~n** is supported for walking the commit parent chain (e.g. `agmem log HEAD~5`, `agmem show HEAD~1`).
- **Search:** Semantic search when `pip install agmem[vector]`; otherwise `agmem search` falls back to plain text (grep-style) search over `current/`.
- **Web:** `agmem serve` and `agmem graph --serve` require `pip install agmem[web]`.
- **Daemon:** `agmem daemon` requires `pip install agmem[daemon]`.
- **MCP:** `agmem mcp` requires `pip install agmem[mcp]`.

---

## Inspection & maintenance

### Blame — who changed each line

See which commit and author last modified each line of a memory file (like `git blame`):

```bash
agmem blame current/semantic/user-preferences.md
agmem blame episodic/session1.md
```

Output: commit hash (short), author, line number, and line content. Use this to trace where a fact or session line came from, or for audits.

### Daemon — watch and auto-commit (optional)

Run a background process that watches `current/` and can auto-commit when files change. Requires the `daemon` extra (watchdog).

```bash
pip install agmem[daemon]
agmem daemon run          # Watch current/, optional auto-commit after debounce
agmem daemon status       # Show if daemon is running
agmem daemon start        # Start in background (uses .mem/daemon.pid by default)
agmem daemon stop         # Stop the daemon
```

Use when you want memory changes to be committed automatically after a short idle period, or to keep a live view of the repo.

### Garden — episode archival & consolidation (optional)

Archive old episodic files and consolidate semantic memory. All paths stay under `current/` (path-validated).

```bash
agmem garden              # Run archival and consolidation (see config)
agmem garden --dry-run    # Show what would be archived/consolidated without writing
```

Configure in `.mem/config.json` (e.g. `archive_dir`, consolidation thresholds). Use to keep `current/episodic/` manageable and to merge related semantic facts.

### Integrity check

```bash
agmem fsck
```

Verifies objects, refs, and (if installed) the vector store. When commit metadata includes `merkle_root` and optionally `signature`, fsck also runs cryptographic verification. Run after cloning or if something looks wrong.

---

## Security, trust & advanced features

The following 18 capabilities are implemented (or stubbed) per the agmem features implementation plan. They are grouped by tier.

### Tier 1 — Security and trust

| # | Feature | Description |
|---|---------|-------------|
| **1** | **Cryptographic commit verification** | Merkle tree over commit blobs; Ed25519 signing of Merkle root; verification on checkout, pull, `agmem verify --crypto`, and `agmem fsck`. Merkle proofs for single-blob verification. Keys: `.mem/keys/`; private key from env `AGMEM_SIGNING_PRIVATE_KEY` or `AGMEM_SIGNING_PRIVATE_KEY_FILE`. Old commits without `merkle_root` are unverified. |
| **2** | **Encryption at rest** | Optional AES-256-GCM for object contents; key from passphrase via Argon2id; hash-then-encrypt preserves deduplication. Config in `.mem/encryption.json` or repo config; opt-in. |
| **3** | **Tamper-evident audit trail** | Append-only, hash-chained log in `.mem/audit/` for init, add, commit, checkout, merge, push, pull, config. **Commands:** `agmem audit` (show entries), `agmem audit --verify` (verify chain). |

### Tier 2 — Multi-agent collaboration

| # | Feature | Description |
|---|---------|-------------|
| **4** | **Multi-agent trust and identity** | Trust store (full / conditional / untrusted) per public key; applied on pull and merge. Clone copies remote public keys; user adds them to trust store. Identity = keypair (same as commit signing). |
| **5** | **Federated memory collaboration** | Agents share summaries or aggregated updates via a coordinator. **Command:** `agmem federated push` / `agmem federated pull` (stub). Config: `federated.enabled`, `coordinator_url`. |
| **6** | **Conflict resolution interface** | Structured resolution: ours / theirs / both per path. **Command:** `agmem resolve [path]`. Conflicts persisted in `.mem/merge/conflicts.json`; path traversal protected. |

### Tier 3 — Privacy

| # | Feature | Description |
|---|---------|-------------|
| **7** | **Differential privacy** | Epsilon/delta budget per repo in `.mem/privacy_budget.json`. **Usage:** `agmem distill --private`, `agmem garden --private`; blocks when budget exceeded. Config: `differential_privacy.max_epsilon`, `delta`. |
| **8** | **Zero-knowledge proofs** | zk-SNARK-style proofs for keyword containment and memory freshness. **Command:** `agmem prove --memory <path> --property keyword|freshness --value <v> [-o out]` (stub). |

### Tier 4 — Storage and distribution

| # | Feature | Description |
|---|---------|-------------|
| **9** | **Decentralized storage (IPFS)** | Push/pull via IPFS CIDs; pinning and gateway fallback. Stub in `memvcs.core.ipfs_remote`; optional dependency. |
| **10** | **Pack files and garbage collection** | Pack loose objects into pack file + index; GC deletes unreachable objects. **Command:** `agmem gc [--dry-run] [--prune-days n]`. Config: `gc_prune_days` (default 90). |
| **11** | **Enhanced cloud remote operations** | Push conflict detection: non–fast-forward push rejected with a clear message. S3/GCS remotes and distributed locking in storage layer. |

### Tier 5 — Intelligence and retrieval

| # | Feature | Description |
|---|---------|-------------|
| **12** | **Multi-provider LLM** | `memvcs.core.llm`: OpenAI and Anthropic; factory by config or env. Used by gardener, distiller, consistency checker, merge. Credentials via env (e.g. `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`). |
| **13** | **Enhanced semantic compression** | Multi-stage pipeline (chunk → fact extraction → dedup → embed → tiered storage); hybrid retrieval. Docstrings and design in distiller/vector store. |
| **14** | **Temporal querying and time-travel** | Point-in-time and range queries in `memvcs.core.temporal_index`; frontmatter timestamps; “state at T” resolution. |
| **15** | **Cross-memory relationship graph** | Knowledge graph extended with co-occurrence, semantic similarity, causal and entity edges; incremental updates. Docstrings in `knowledge_graph.py`. |

### Tier 6 — Operations and maintenance

| # | Feature | Description |
|---|---------|-------------|
| **16** | **Automated memory health monitoring** | Daemon runs periodic Merkle verification; safe auto-remediation hooks; unsafe actions alert only. |
| **17** | **GPU-accelerated operations** | Vector store detects GPU for embedding model (e.g. sentence-transformers with CUDA/Metal); transparent CPU fallback. |
| **18** | **Test suite and quality** | Broad tests: object store, merge, crypto (Merkle, proofs, verify), trust, privacy budget, pack/GC, resolve helpers, encryption, LLM provider; CI with coverage. |

### New files and config (summary)

| Addition | Purpose |
|----------|---------|
| `memvcs/core/crypto_verify.py` | Merkle build/verify, Ed25519 sign/verify, Merkle proofs |
| `memvcs/core/audit.py` | Tamper-evident audit append and verify |
| `memvcs/core/trust.py` | Trust store (key → level) |
| `memvcs/core/privacy_budget.py` | Epsilon/delta budget for DP |
| `memvcs/core/pack.py` | Pack format, index, GC |
| `memvcs/core/encryption.py` | AES-256-GCM, Argon2id, config |
| `memvcs/core/llm/` | LLM provider interface and OpenAI/Anthropic |
| `memvcs/core/zk_proofs.py` | ZK proof stubs |
| `memvcs/core/federated.py` | Federated push/pull stubs |
| `.mem/audit/` | Audit log |
| `.mem/keys/` | Public (and optional private) keys |
| `.mem/trust/` or config | Trust store |
| `.mem/privacy_budget.json` | DP budget state |
| `.mem/merge/conflicts.json` | Unresolved merge conflicts |
| Commit `metadata` | `merkle_root`, `signature` |

---

## Memory Types

agmem recognizes three types of agent memory:

### Episodic Memory
Time-stamped records of agent interactions:
```
current/episodic/
├── 2026-01-31-session1.md
├── 2026-01-31-session2.md
└── 2026-02-01-session1.md
```

**Merge strategy:** Append chronologically (no conflicts)

### Semantic Memory
Factual knowledge and learned patterns:
```
current/semantic/
├── user-preferences.md
├── project-context.md
└── domain-knowledge.md
```

**Merge strategy:** Smart consolidation with conflict markers

### Procedural Memory
Workflows and prompt templates:
```
current/procedural/
├── coding-workflow.md
└── debugging-process.md
```

**Merge strategy:** Prefer newer, flag for manual review

## How It Works

### Memory Flow

```
  current/                    staging                    .mem/
  ╭────────────────────┐    ╭─────────────┐    ╭──────────────────────┐
  │ episodic/           │    │             │    │  objects/            │
  │   session logs      │    │  index.json  │    │  blobs → trees →     │
  │ semantic/           │───►│  (staged)   │───►│  commits             │
  │   facts, prefs      │    │             │    │  (content-addressable)│
  │ procedural/         │    │             │    │                      │
  │   workflows         │    ╰─────────────╯    ╰──────────────────────╯
  ╰────────────────────┘
         │                         │
    agmem add               agmem commit
```

### Merge Strategies

```
  Episodic      Branch A ──╮
  (append)      Branch B ──╯──►  chronological append  ──►  ✓ no conflicts

  Semantic      Branch A ──╮
  (consolidate) Branch B ──╯──►  conflict markers      ──►  ⚠ manual review

  Procedural    Branch A ──╮
  (prefer new)  Branch B ──╯──►  newer wins            ──►  ⚠ flag for review
```

### How Others Handle Memory vs agmem

| Tool | Approach | Gap |
|------|----------|-----|
| **Cursor** | Ephemeral, session-based context; no persistent version control | No history, branching, or merge for agent memory |
| **Claude Code** | File-based (CLAUDE.md, .claude/rules); loaded at launch | No built-in version control; Git is not memory-type-aware |
| **Mem0** | Cloud/API; vector-based persistence | No branching, merging, or "git log" for what the agent learned |
| **agmem** | Git-like version control for memory | Version history, branching, merging, local-first, memory-type-aware |

## Example: Multi-Agent Collaboration

```bash
# Agent A creates base memory
agmem init --author-name "Agent-A"
echo "User prefers Python" > current/semantic/preferences.md
agmem add .
agmem commit -m "Initial preferences"

# Agent B clones and extends
# cd agent-b-memory
# agmem clone file:///path/to/agent-a
# echo "User also likes TypeScript" >> current/semantic/preferences.md
# agmem add .
# agmem commit -m "Added TypeScript preference"

# Agent A pulls and merges Agent B's changes
# agmem pull
# agmem merge agent-b/main
```

## Storage (Git-Like)

agmem stores agent memory exactly like Git stores code:

| Git | agmem |
|-----|-------|
| `.git/objects/` | `.mem/objects/` |
| Blob, Tree, Commit | Same (content-addressable) |
| SHA-1 | SHA-256 |
| zlib compression | zlib compression |
| Deduplication | Deduplication |
| `refs/heads/` | `refs/heads/` |
| `refs/tags/` | `refs/tags/` |
| Reflog | Reflog |
| Stash | Stash |

**Working directory:** `current/` with episodic, semantic, procedural, checkpoints, session-summaries. Same mental model as Git's working tree.

**Security:** Paths, refs, and object hashes are validated everywhere (no path traversal). Branch/tag names may include `/` but must resolve under `refs/heads` or `refs/tags`. Remote URLs (file://) and clone targets are validated. `serve` binds to 127.0.0.1 by default.

- **Content-addressable objects** — Blobs, trees, commits hashed with SHA-256
- **Compression** — zlib for efficient storage
- **Deduplication** — Same content = same hash, stored once
- **Reflog** — History of HEAD changes (commit, checkout)
- **Stash** — Temporary storage for work-in-progress

## Configuration

### Repository config (`.mem/config.json`)

Repository configuration is stored in `.mem/config.json`:

```json
{
  "author": {
    "name": "Agent",
    "email": "agent@example.com"
  },
  "core": {
    "default_branch": "main",
    "compression": true,
    "gc_prune_days": 90
  },
  "memory": {
    "auto_summarize": true,
    "summarizer_model": "default",
    "max_episode_size": 1048576,
    "consolidation_threshold": 100
  },
  "differential_privacy": {
    "max_epsilon": 1.0,
    "delta": 1e-5
  },
  "federated": {
    "enabled": false,
    "coordinator_url": ""
  }
}
```

Optional sections: **`differential_privacy`** (for `--private` on distill/garden); **`federated`** (for `agmem federated`); **`signing`** (public key for commit verification); trust store under `.mem/trust/` or config; encryption in `.mem/encryption.json` when enabled.

### agmem config (cloud and PII)

Optional user/repo config for S3/GCS and PII hooks:

- **User-level**: `~/.config/agmem/config.yaml` (or `$XDG_CONFIG_HOME/agmem/config.yaml`)
- **Repo-level**: `<repo>/.agmemrc` or `<repo>/.mem/config.yaml` (YAML)

Repo overrides user. **Never put secrets in config files.** Credentials are supplied via environment variables (or standard AWS/GCP mechanisms). Config may reference env var *names* only (e.g. `access_key_var: AWS_ACCESS_KEY_ID`). See [docs/CONFIG.md](docs/CONFIG.md) for schema and examples.

- **Cloud (S3/GCS)**: region, endpoint, env var names for credentials; GCS can use `credentials_path` (validated under repo/home) or `credentials_json_var` (env var containing JSON key).
- **PII**: `pii.enabled` (default true) to enable/disable pre-commit PII scanning; `pii.allowlist` (path globs) to skip scanning certain files.

## Architecture

agmem follows Git's proven architecture:

```
  ╔═══════════════════════════════════════════════════════════════════════╗
  ║  PORCELAIN  ·  What you type                                         ║
  ╠═══════════════════════════════════════════════════════════════════════╣
  ║    init  add  commit  status  log   ·   branch  checkout  merge       ║
  ║    diff  show  tag  reset  tree     ·   stash  clean  blame  reflog   ║
  ║    clone  push  pull  remote  fsck  ·   graph  search  serve  daemon   ║
  ╠═══════════════════════════════════════════════════════════════════════╣
  ║  PLUMBING  ·  What happens under the hood                             ║
  ╠═══════════════════════════════════════════════════════════════════════╣
  ║    objects (blob, tree, commit)  ·  refs (HEAD, branches, tags)      ║
  ║    staging area                                                       ║
  ╠═══════════════════════════════════════════════════════════════════════╣
  ║  STORAGE  ·  On disk                                                 ║
  ╠═══════════════════════════════════════════════════════════════════════╣
  ║    SHA-256 hashing  ·  zlib compression  ·  deduplication            ║
  ╚═══════════════════════════════════════════════════════════════════════╝
```

## Development

```bash
# Clone repository
git clone https://github.com/vivek-tiwari-vt/agmem.git
cd agmem

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black memvcs/

# Type check
mypy memvcs/
```

## Roadmap

- [x] Core object storage (blob, tree, commit)
- [x] Basic commands (init, add, commit, status, log, diff, show, reset, tag, stash, reflog, blame, tree, clean)
- [x] HEAD~n resolution; branch/tag names with `/` (Git-style)
- [x] Branching and checkout; merging with memory-type-aware strategies
- [x] Remote operations (clone, push, pull, remote) — file:// URLs; pull merges into current branch; push conflict detection
- [x] Search — semantic with `agmem[vector]`, plain text fallback
- [x] Knowledge graph (`agmem graph`) — wikilinks, tags, optional similarity; `--no-similarity`, `--serve`
- [x] Integrity (`agmem fsck`); path/ref/hash validation; Merkle/signature verification
- [x] Web UI (`agmem serve`); MCP server (`agmem mcp`); daemon (`agmem daemon`); garden (`agmem garden`)
- [x] Cryptographic commit verification (Merkle tree, Ed25519 signing, verify on checkout/pull/fsck)
- [x] Tamper-evident audit trail (`agmem audit`); multi-agent trust store; conflict resolution (`agmem resolve`)
- [x] Encryption at rest (optional AES-256-GCM); differential privacy budget (`--private` on distill/garden)
- [x] Pack files and garbage collection (`agmem gc`); ZK proofs and federated stubs (`agmem prove`, `agmem federated`)
- [x] Multi-provider LLM (OpenAI, Anthropic); temporal range queries; daemon health checks; GPU detection; test suite and CI
- [ ] IPFS remote (stub in place); full ZK circuits and federated coordinator

## Integrations

```
  Cursor ────────╮
  Claude Code ───┼──►  MCP Server  ──►  current/  ──►  .mem/
  Windsurf ──────┤     (agmem mcp)      episodic/
  Continue ──────╯                      semantic/
                                         procedural/

  Python API ────►  Repository()  ──►  (same)
  LangChain
  LangGraph
```

### Cursor

1. Install: `pip install agmem[mcp]`
2. Add MCP server to Cursor settings (Settings → MCP → Edit Config):

```json
{
  "mcpServers": {
    "agmem": {
      "command": "agmem",
      "args": ["mcp"]
    }
  }
}
```

3. Use memory tools in chat: `memory_read`, `memory_search`, `memory_add`, `memory_log`, `memory_diff`
4. Optional: Add Cursor rules pointing to `current/` for automatic context loading

### Claude Code

Same MCP setup as Cursor. Claude Desktop uses MCP natively. File-based memory (CLAUDE.md, .claude/rules) can coexist with agmem—agmem adds version control on top.

### Other IDEs

Any MCP-compatible client (Windsurf, Continue, etc.) works with the same config. Use the Python API for custom integrations.

### Vector Search

```bash
pip install agmem[vector]
agmem search "user prefers Python"
agmem search "workflow" --rebuild   # Rebuild index after many changes
```

When `agmem[vector]` is not installed, `agmem search` uses plain text (grep-style) search over `current/**/*.md` and `*.txt`.

### Knowledge graph

```bash
agmem graph                    # Summary: nodes, edges by type, isolated files
agmem graph --no-similarity     # Wikilinks + tags only (no vector store)
agmem graph --format json      # Full graph JSON
agmem graph --format d3 -o g.json   # D3 nodes/links for visualization
agmem graph --serve            # Serve graph UI (requires agmem[web])
```

Edges come from **wikilinks** (`[[target]]`, `[[target|label]]`) and shared **YAML frontmatter tags**. Use `--no-similarity` when vector deps are not installed.

### Web UI

```bash
pip install agmem[web]
agmem serve          # Browse history, view diffs in browser
agmem graph --serve  # Serve knowledge graph UI (same extra)
```

## Use Cases

### Multi-Agent Collaboration

- **Agent A** develops memory on `main`
- **Agent B** clones, branches, and extends: `agmem clone file:///path/to/agent-a`
- **Agent A** pulls and merges: `agmem pull` then `agmem merge agent-b/main`
- Memory-type-aware merge: episodic appends, semantic uses conflict markers, procedural prefers newer

### Experiment Tracking

- Branch per experiment: `agmem branch exp-v2-prompt`
- Compare results: `agmem diff main exp-v2-prompt`
- Tag successful runs: `agmem tag v1.0`
- Roll back: `agmem reset --hard HEAD~1`

### Compliance and Audit

- **Full history:** `agmem log`, `agmem reflog`
- **Line-level attribution:** `agmem blame <file>` — see which commit and author last changed each line (e.g. `agmem blame current/semantic/user-preferences.md`)
- **Tamper-evident audit:** `agmem audit` and `agmem audit --verify` for hash-chained operation log
- **Cryptographic verification:** `agmem verify --crypto` and `agmem fsck` for Merkle roots and Ed25519 signatures
- **Visual audit:** `agmem serve` for browser-based history and diff viewer
- **Integrity:** `agmem fsck` to verify objects, refs, and commit signatures

## Ecosystem Plugin Patterns

### LangChain / LangGraph

Use the agmem Python API or MCP tools as a memory backend:

```python
from pathlib import Path
from memvcs.core.repository import Repository

repo = Repository(Path("."))
repo.stage_file("semantic/learned.md", content=b"Agent learned X")
repo.commit("Learned X")
```

Or connect via MCP and call `memory_add` from your agent.

### MCP Resource URIs

- `mem://current/semantic/user-preferences.md` — Read memory file
- `mem://current/episodic/session1.md` — Session log
- `mem://current/procedural/workflow.md` — Procedural memory

### Plugin Checklist

1. Detect agmem repo: `.mem/` directory exists
2. Read from `current/` for context
3. Write via `agmem add` + `agmem commit` or MCP `memory_add`
4. Optional: Use `agmem search` for semantic retrieval

## Links

- **PyPI:** [pypi.org/project/agmem](https://pypi.org/project/agmem/) — `pip install agmem`

**GitHub repo (About):** Use this description and topics in your repo’s **About** (gear → Description & topics):

- **Description:** Git for AI agent memories. Version control for episodic logs, semantic knowledge, and procedural workflows.
- **Topics:** `ai` `agent` `memory` `version-control` `git` `vcs` `llm` `python`

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

agmem is inspired by Git's elegant design and the growing need for agent memory management in the AI ecosystem. Thanks to the Git team for proving that distributed version control can be both powerful and usable.

---

**Made with ❤️ for AI agents and their developers**
