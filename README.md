# agmem - Agentic Memory Version Control System

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
- ✅ **Remote (file://)** — `clone`, `push`, `pull`, `remote`; pull merges into current branch
- ✅ **Search** — Semantic with `agmem[vector]`, or plain text over `current/` when vector deps missing
- ✅ **Knowledge graph** — `agmem graph` from wikilinks/tags; `--no-similarity`, `--format d3`, `--serve` (optional `agmem[web]`)
- ✅ **Integrity** — `agmem fsck`; path/ref/hash validation throughout (no path traversal)
- ✅ **Optional** — `serve`, `daemon` (watch + auto-commit), `garden` (episode archival), MCP server; install extras as needed

## Quick Start

### Installation

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
```

## Commands

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
| `agmem blame <file>` | Per-line blame |
| `agmem reflog` | HEAD change history |

### Remote & integrity

| Command | Description |
|---------|-------------|
| `agmem clone <url> [dir]` | Clone repo (file:// URLs); path-validated |
| `agmem remote add <name> <url>` | Add remote |
| `agmem remote show` | List remotes |
| `agmem push <remote> <branch>` | Push branch (refs validated) |
| `agmem pull [--remote <name>] [--branch <b>]` | Fetch and merge into current branch |
| `agmem fsck` | Check objects, refs, optional vector store |

### Optional (install extras)

| Command | Extra | Description |
|---------|-------|-------------|
| `agmem search <query>` | `agmem[vector]` | Semantic search; else plain text over `current/` |
| `agmem graph` | — | Knowledge graph from wikilinks/tags; `--no-similarity` skips vector |
| `agmem graph --serve` | `agmem[web]` | Serve graph UI (same as `agmem serve`) |
| `agmem serve` | `agmem[web]` | Web UI for history and diffs |
| `agmem daemon` | `agmem[daemon]` | Watch `current/`, optional auto-commit |
| `agmem garden` | — | Episode archival, consolidation (paths under `current/`) |
| `agmem mcp` | `agmem[mcp]` | MCP server for Cursor/Claude |

### Refs and optional extras

- **Branch and tag names** can include `/` (e.g. `feature/test`, `releases/v1`); the resolved path must stay under `refs/heads` or `refs/tags` (Git-style).
- **HEAD~n** is supported for walking the commit parent chain (e.g. `agmem log HEAD~5`, `agmem show HEAD~1`).
- **Search:** Semantic search when `pip install agmem[vector]`; otherwise `agmem search` falls back to plain text (grep-style) search over `current/`.
- **Web:** `agmem serve` and `agmem graph --serve` require `pip install agmem[web]`.
- **Daemon:** `agmem daemon` requires `pip install agmem[daemon]`.
- **MCP:** `agmem mcp` requires `pip install agmem[mcp]`.

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
  }
}
```

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
- [x] Remote operations (clone, push, pull, remote) — file:// URLs; pull merges into current branch
- [x] Search — semantic with `agmem[vector]`, plain text fallback
- [x] Knowledge graph (`agmem graph`) — wikilinks, tags, optional similarity; `--no-similarity`, `--serve`
- [x] Integrity (`agmem fsck`); path/ref/hash validation (security)
- [x] Web UI (`agmem serve`); MCP server (`agmem mcp`); daemon (`agmem daemon`); garden (`agmem garden`)
- [ ] Garbage collection
- [ ] Pack files for efficiency

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

- Full history: `agmem log`, `agmem reflog`
- Blame: `agmem blame current/semantic/user-preferences.md`
- Visual audit: `agmem serve` for browser-based history and diff viewer

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

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

agmem is inspired by Git's elegant design and the growing need for agent memory management in the AI ecosystem. Thanks to the Git team for proving that distributed version control can be both powerful and usable.

---

**Made with ❤️ for AI agents and their developers**
