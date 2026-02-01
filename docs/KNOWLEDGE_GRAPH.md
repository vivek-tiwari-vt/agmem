# Knowledge Graph Feature (agmem graph)

The knowledge graph visualizes connections between memory files so you can spot **contradictions**, **knowledge islands**, and **reference structure**.

## What It Does

- **Nodes**: Each memory file (`.md` in `current/`) is a node, with type inferred from path (`episodic`, `semantic`, `procedural`, etc.).
- **Edges**: Connections between files:
  - **reference**: Wikilinks like `[[user-preferences]]` or `[[target|label]]` that resolve to another file.
  - **same_topic**: Files that share the same tag (from YAML frontmatter).
  - **similarity**: Semantic similarity from embeddings (optional; requires vector store).

## Commands

```bash
# Summary in terminal (default)
agmem graph

# Skip similarity edges (no vector store needed)
agmem graph --no-similarity

# Export JSON for your own tools
agmem graph --format json --output graph.json

# Export D3.js force-graph format for web visualization
agmem graph --format d3 --output graph_d3.json

# Start web server to view interactive graph (requires agmem[web])
agmem graph --serve
```

## Creating Connections (Wikilinks)

Use wikilink syntax in any memory file:

```markdown
See [[user-preferences]] for style.
Related: [[coding-workflow]] and [[session1]].
```

Targets are resolved by name (with `.md`/`.txt` tried) under `current/`, in the same directory as the source file, then in `semantic/`, `episodic/`, `procedural/`.

## Example Output (Summary)

```
Building knowledge graph...

Knowledge Graph Summary
========================================
Total files: 4
Total connections: 5

By Memory Type:
  episodic: 2
  semantic: 1
  procedural: 1

By Edge Type:
  reference: 5

Isolated files (no connections): 1
  - episodic/wip.md

Use --format d3 --output graph.json to export for visualization
```

## D3 Export Format

With `--format d3 --output file.json` you get:

- **nodes**: `id` (path), `name` (stem), `group` (memory type), `size` (from content size).
- **links**: `source`, `target`, `type` (reference | same_topic | similarity), `value` (weight).

You can plug this into [D3 force-graph](https://github.com/vasturiano/force-graph) or the built-in web UI (`agmem graph --serve`).

## Insights

- **Isolated files**: No incoming or outgoing edges (“knowledge islands”) — consider linking or tagging.
- **Potential contradictions**: (When using similarity) Files tagged the same but with low similarity — worth reviewing for consistency.
