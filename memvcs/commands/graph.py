"""
agmem graph - Visualize the knowledge graph.
"""

import argparse
import json
from pathlib import Path

from ..commands.base import require_repo


class GraphCommand:
    """Visualize connections between memory files."""
    
    name = 'graph'
    help = 'Visualize the knowledge graph of memory files'
    
    @staticmethod
    def add_arguments(parser: argparse.ArgumentParser):
        parser.add_argument(
            '--output', '-o',
            help='Output file for graph data (JSON)'
        )
        parser.add_argument(
            '--format',
            choices=['json', 'd3', 'summary'],
            default='summary',
            help='Output format (default: summary)'
        )
        parser.add_argument(
            '--no-similarity',
            action='store_true',
            help='Skip similarity-based edges (faster)'
        )
        parser.add_argument(
            '--threshold',
            type=float,
            default=0.7,
            help='Similarity threshold for edges (default: 0.7)'
        )
        parser.add_argument(
            '--serve',
            action='store_true',
            help='Start web server to view interactive graph'
        )
    
    @staticmethod
    def execute(args) -> int:
        repo, code = require_repo()
        if code != 0:
            return code
        
        # Try to get vector store for similarity
        vector_store = None
        if not args.no_similarity:
            try:
                from ..core.vector_store import VectorStore
                vector_store = VectorStore(repo.root / '.mem')
            except ImportError:
                print("Note: Vector store not available, skipping similarity edges")
        
        # Build graph
        from ..core.knowledge_graph import KnowledgeGraphBuilder
        
        builder = KnowledgeGraphBuilder(repo, vector_store)
        
        print("Building knowledge graph...")
        graph_data = builder.build_graph(
            include_similarity=not args.no_similarity,
            similarity_threshold=args.threshold
        )
        
        if args.serve:
            return GraphCommand._serve_graph(repo, graph_data)
        
        if args.format == 'summary':
            GraphCommand._print_summary(graph_data, builder)
        
        elif args.format == 'json':
            output = graph_data.to_json()
            if args.output:
                Path(args.output).write_text(output)
                print(f"Graph data written to: {args.output}")
            else:
                print(output)
        
        elif args.format == 'd3':
            output = builder.export_for_d3()
            if args.output:
                Path(args.output).write_text(output)
                print(f"D3 graph data written to: {args.output}")
            else:
                print(output)
        
        return 0
    
    @staticmethod
    def _print_summary(graph_data, builder):
        """Print a text summary of the graph."""
        meta = graph_data.metadata
        
        print("\nKnowledge Graph Summary")
        print("=" * 40)
        print(f"Total files: {meta['total_nodes']}")
        print(f"Total connections: {meta['total_edges']}")
        
        print("\nBy Memory Type:")
        for mtype, count in meta['memory_types'].items():
            if count > 0:
                print(f"  {mtype}: {count}")
        
        print("\nBy Edge Type:")
        for etype, count in meta['edge_types'].items():
            if count > 0:
                print(f"  {etype}: {count}")
        
        # Find isolated nodes
        isolated = builder.find_isolated_nodes()
        if isolated:
            print(f"\nIsolated files (no connections): {len(isolated)}")
            for path in isolated[:5]:
                print(f"  - {path}")
            if len(isolated) > 5:
                print(f"  ... and {len(isolated) - 5} more")
        
        # Find potential contradictions
        contradictions = builder.find_potential_contradictions()
        if contradictions:
            print(f"\nPotential contradictions: {len(contradictions)}")
            for path1, path2, sim in contradictions[:3]:
                print(f"  - {path1} <-> {path2} (similarity: {sim:.2%})")
        
        print("\nUse --format d3 --output graph.json to export for visualization")
    
    @staticmethod
    def _serve_graph(repo, graph_data):
        """Start web server to view interactive graph."""
        try:
            import uvicorn
            from ..integrations.web_ui.server import create_app
        except ImportError:
            print("Error: Web server requires fastapi and uvicorn.")
            print("Install with: pip install agmem[web]")
            return 1
        
        print("Starting graph visualization server...")
        print("Open http://localhost:8080/graph in your browser")
        
        app = create_app(repo.root)
        uvicorn.run(app, host="127.0.0.1", port=8080)
        return 0
