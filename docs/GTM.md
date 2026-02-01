# agmem Go-to-Market Guide

Documentation for tutorials, use cases, and ecosystem integrations.

---

## 1. Tutorials: "Git for your AI Agent"

### Quick Tutorial

```bash
# Initialize agent memory
agmem init

# Your AI agent learns something - save it
echo "User prefers Python and dark mode" > current/semantic/user-preferences.md
agmem add .
agmem commit -m "Learned user preferences"

# Experiment with different strategies
agmem branch experiment
agmem checkout experiment
# ... make changes ...
agmem add .
agmem commit -m "Trying new workflow"
agmem checkout main
agmem merge experiment

# Browse history
agmem log
agmem diff HEAD~1 HEAD
agmem serve   # Web UI
```

### Cursor/Claude Integration

1. **Install agmem**: `pip install agmem[mcp]`
2. **Add MCP server** to Cursor/Claude config:

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

3. **Use memory tools** in chat: `memory_read`, `memory_search`, `memory_add`, `memory_log`, `memory_diff`
4. **Cursor rules**: Copy `.cursor/rules/agmem-memory.mdc` into your project for automatic context loading from `current/`

### Semantic Search

```bash
# First search builds the index
agmem search "user prefers Python"

# Rebuild index after many changes
agmem search "workflow" --rebuild
```

---

## 2. Use Cases

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

---

## 3. Ecosystem Plugin Patterns

### LangChain / LangGraph

Use the agmem Python API or MCP tools as a memory backend:

```python
from memvcs.core.repository import Repository

repo = Repository(Path("."))
repo.stage_file("semantic/learned.md", content=b"Agent learned X")
repo.commit("Learned X")
```

Or connect via MCP and call `memory_add` from your agent.

### MCP Resource URIs

- `mem://current/semantic/user-preferences.md` - Read memory file
- `mem://current/episodic/session1.md` - Session log
- `mem://current/procedural/workflow.md` - Procedural memory

### Plugin Checklist

1. Detect agmem repo: `.mem/` directory exists
2. Read from `current/` for context
3. Write via `agmem add` + `agmem commit` or MCP `memory_add`
4. Optional: Use `agmem search` for semantic retrieval
