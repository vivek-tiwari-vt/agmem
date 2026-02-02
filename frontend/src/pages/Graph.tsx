import { useRef, useState, useCallback, useMemo, useEffect } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { useApi } from '../hooks/useApi'

interface Node {
    id: string
    name: string
    group: string
    size?: number
}

interface Link {
    source: string
    target: string
    type: string
    value: number
}

interface GraphData {
    nodes: Node[]
    links: Link[]
    metadata: {
        total_nodes: number
        total_edges: number
        memory_types: Record<string, number>
        edge_types: Record<string, number>
    }
}

const GROUP_COLORS: Record<string, string> = {
    episodic: '#f97316',   // Orange
    semantic: '#22c55e',   // Green
    procedural: '#3b82f6', // Blue
    unknown: '#8b5cf6',    // Purple
    other: '#8b5cf6',      // Purple
}

const EDGE_COLORS: Record<string, string> = {
    same_topic: '#f59e0b',
    co_occurrence: '#6366f1',
    related: '#10b981',
    default: '#4b5563',
}

export default function Graph() {
    const { data, loading, error } = useApi<GraphData>('/graph')
    const graphRef = useRef<any>(null)
    const [searchQuery, setSearchQuery] = useState('')
    const [selectedNode, setSelectedNode] = useState<Node | null>(null)
    const [highlightNodes, setHighlightNodes] = useState<Set<string>>(new Set())
    const [highlightLinks, setHighlightLinks] = useState<Set<string>>(new Set())
    const [hoverNode, setHoverNode] = useState<string | null>(null)
    const [dimensions, setDimensions] = useState({ width: 800, height: 600 })

    // Update dimensions on mount
    useEffect(() => {
        const updateDimensions = () => {
            const container = document.querySelector('.graph-container')
            if (container) {
                setDimensions({
                    width: container.clientWidth || 800,
                    height: Math.max(500, window.innerHeight - 250)
                })
            }
        }
        updateDimensions()
        window.addEventListener('resize', updateDimensions)
        return () => window.removeEventListener('resize', updateDimensions)
    }, [])

    // Transform data for force graph
    const graphData = useMemo(() => {
        if (!data) return { nodes: [], links: [] }
        return {
            nodes: data.nodes.map(n => ({
                ...n,
                color: GROUP_COLORS[n.group] || GROUP_COLORS.other,
                val: n.size || 5,
            })),
            links: data.links.map(l => ({
                ...l,
                color: EDGE_COLORS[l.type] || EDGE_COLORS.default,
            })),
        }
    }, [data])

    // Filter nodes by search
    const filteredData = useMemo(() => {
        if (!searchQuery.trim()) return graphData

        const query = searchQuery.toLowerCase()
        const matchingNodeIds = new Set(
            graphData.nodes
                .filter(n => n.name.toLowerCase().includes(query) || n.group.toLowerCase().includes(query))
                .map(n => n.id)
        )

        // Include connected nodes
        graphData.links.forEach(link => {
            const sourceId = typeof link.source === 'object' ? (link.source as any).id : link.source
            const targetId = typeof link.target === 'object' ? (link.target as any).id : link.target
            if (matchingNodeIds.has(sourceId)) matchingNodeIds.add(targetId)
            if (matchingNodeIds.has(targetId)) matchingNodeIds.add(sourceId)
        })

        return {
            nodes: graphData.nodes.filter(n => matchingNodeIds.has(n.id)),
            links: graphData.links.filter(link => {
                const sourceId = typeof link.source === 'object' ? (link.source as any).id : link.source
                const targetId = typeof link.target === 'object' ? (link.target as any).id : link.target
                return matchingNodeIds.has(sourceId) && matchingNodeIds.has(targetId)
            }),
        }
    }, [graphData, searchQuery])

    // Node click handler
    const handleNodeClick = useCallback((node: any) => {
        setSelectedNode(node)

        // Highlight connected nodes and links
        const connectedNodes = new Set<string>([node.id])
        const connectedLinks = new Set<string>()

        graphData.links.forEach(link => {
            const sourceId = typeof link.source === 'object' ? (link.source as any).id : link.source
            const targetId = typeof link.target === 'object' ? (link.target as any).id : link.target
            if (sourceId === node.id || targetId === node.id) {
                connectedNodes.add(sourceId)
                connectedNodes.add(targetId)
                connectedLinks.add(`${sourceId}-${targetId}`)
            }
        })

        setHighlightNodes(connectedNodes)
        setHighlightLinks(connectedLinks)

        // Center on node
        if (graphRef.current) {
            graphRef.current.centerAt(node.x, node.y, 500)
            graphRef.current.zoom(2, 500)
        }
    }, [graphData])

    // Node hover handler
    const handleNodeHover = useCallback((node: any) => {
        setHoverNode(node ? node.id : null)
    }, [])

    // Clear selection
    const clearSelection = useCallback(() => {
        setSelectedNode(null)
        setHighlightNodes(new Set())
        setHighlightLinks(new Set())
        if (graphRef.current) {
            graphRef.current.zoomToFit(400)
        }
    }, [])

    // Node canvas render
    const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const label = node.name
        const fontSize = 12 / globalScale
        ctx.font = `${fontSize}px Inter, sans-serif`

        const isHighlighted = highlightNodes.size === 0 || highlightNodes.has(node.id)
        const isHovered = hoverNode === node.id

        // Node circle
        ctx.beginPath()
        const radius = (node.val || 5) * (isHovered ? 1.3 : 1)
        ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI)
        ctx.fillStyle = isHighlighted ? node.color : `${node.color}33`
        ctx.fill()

        // Glow effect for hovered node
        if (isHovered) {
            ctx.shadowColor = node.color
            ctx.shadowBlur = 15
            ctx.stroke()
            ctx.shadowBlur = 0
        }

        // Border
        ctx.strokeStyle = isHighlighted ? '#fff' : '#333'
        ctx.lineWidth = isHovered ? 2 / globalScale : 1 / globalScale
        ctx.stroke()

        // Label
        if (globalScale > 0.8 || isHovered || selectedNode?.id === node.id) {
            ctx.textAlign = 'center'
            ctx.textBaseline = 'middle'
            ctx.fillStyle = isHighlighted ? '#fff' : '#666'
            ctx.fillText(label, node.x, node.y + radius + fontSize)
        }
    }, [highlightNodes, hoverNode, selectedNode])

    // Link canvas render
    const linkCanvasObject = useCallback((link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
        const sourceId = typeof link.source === 'object' ? link.source.id : link.source
        const targetId = typeof link.target === 'object' ? link.target.id : link.target
        const linkId = `${sourceId}-${targetId}`
        const isHighlighted = highlightLinks.size === 0 || highlightLinks.has(linkId)

        ctx.beginPath()
        ctx.moveTo(link.source.x, link.source.y)
        ctx.lineTo(link.target.x, link.target.y)
        ctx.strokeStyle = isHighlighted ? (link.color || '#666') : '#222'
        ctx.lineWidth = (link.value || 1) * (isHighlighted ? 2 : 0.5) / globalScale
        ctx.stroke()
    }, [highlightLinks])

    if (loading) return <div className="loading">Loading graph...</div>
    if (error) return <div className="error">Error: {error}</div>

    return (
        <div className="graph-page">
            <h2>Memory Graph</h2>

            {/* Stats */}
            <div className="grid" style={{ marginBottom: '20px' }}>
                <div className="card" style={{ padding: '12px' }}>
                    <h3 style={{ fontSize: '14px' }}>Nodes</h3>
                    <div className="value" style={{ fontSize: '24px' }}>{data?.metadata?.total_nodes || graphData.nodes.length}</div>
                </div>
                <div className="card" style={{ padding: '12px' }}>
                    <h3 style={{ fontSize: '14px' }}>Connections</h3>
                    <div className="value" style={{ fontSize: '24px' }}>{data?.metadata?.total_edges || graphData.links.length}</div>
                </div>
                <div className="card" style={{ padding: '12px' }}>
                    <h3 style={{ fontSize: '14px' }}>Showing</h3>
                    <div className="value" style={{ fontSize: '24px' }}>{filteredData.nodes.length}</div>
                </div>
            </div>

            {/* Search and Controls */}
            <div className="card" style={{ padding: '16px', marginBottom: '20px' }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
                    <input
                        type="text"
                        placeholder="Search memories..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        style={{
                            flex: 1,
                            minWidth: '200px',
                            padding: '10px 16px',
                            background: 'var(--bg-tertiary)',
                            border: '1px solid var(--bg-tertiary)',
                            borderRadius: '8px',
                            color: 'var(--text-primary)',
                            fontSize: '14px',
                        }}
                    />
                    <button onClick={clearSelection}>Reset View</button>
                    <button onClick={() => graphRef.current?.zoomToFit(400)}>Fit All</button>
                </div>

                {/* Legend */}
                <div style={{ display: 'flex', gap: '16px', marginTop: '12px', flexWrap: 'wrap' }}>
                    {Object.entries(GROUP_COLORS).map(([type, color]) => (
                        <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <div style={{ width: 12, height: 12, borderRadius: '50%', background: color }} />
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{type}</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Graph Container */}
            <div className="card graph-container" style={{ padding: 0, overflow: 'hidden', position: 'relative' }}>
                <ForceGraph2D
                    ref={graphRef}
                    graphData={filteredData}
                    width={dimensions.width - 50}
                    height={dimensions.height}
                    backgroundColor="#1a1a35"
                    nodeCanvasObject={nodeCanvasObject}
                    linkCanvasObject={linkCanvasObject}
                    onNodeClick={handleNodeClick}
                    onNodeHover={handleNodeHover}
                    onBackgroundClick={clearSelection}
                    enableNodeDrag={true}
                    enableZoomInteraction={true}
                    enablePanInteraction={true}
                    cooldownTime={3000}
                    d3AlphaDecay={0.02}
                    d3VelocityDecay={0.3}
                    linkDirectionalParticles={2}
                    linkDirectionalParticleWidth={2}
                    linkDirectionalParticleSpeed={0.01}
                />

                {/* Node Details Panel */}
                {selectedNode && (
                    <div style={{
                        position: 'absolute',
                        top: 16,
                        right: 16,
                        background: 'rgba(26, 26, 53, 0.95)',
                        border: '1px solid var(--bg-tertiary)',
                        borderRadius: '12px',
                        padding: '16px',
                        maxWidth: '280px',
                        backdropFilter: 'blur(8px)',
                    }}>
                        <h4 style={{ margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <div style={{
                                width: 10,
                                height: 10,
                                borderRadius: '50%',
                                background: GROUP_COLORS[selectedNode.group] || GROUP_COLORS.other
                            }} />
                            {selectedNode.name}
                        </h4>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '8px 0' }}>
                            Type: <span className="status-badge success">{selectedNode.group}</span>
                        </p>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0' }}>
                            Path: <code>{selectedNode.id}</code>
                        </p>
                        <p style={{ fontSize: '12px', color: 'var(--text-secondary)', margin: '4px 0' }}>
                            Connections: {highlightLinks.size}
                        </p>
                        <button
                            onClick={clearSelection}
                            style={{ marginTop: '12px', padding: '6px 12px', fontSize: '12px' }}
                        >
                            Close
                        </button>
                    </div>
                )}
            </div>

            {/* Edge Type Legend */}
            <div className="card" style={{ padding: '12px', marginTop: '20px' }}>
                <h3 style={{ fontSize: '14px', marginBottom: '8px' }}>Relationship Types</h3>
                <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap' }}>
                    {Object.entries(data?.metadata?.edge_types || {}).map(([type, count]) => (
                        <div key={type} style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <div style={{
                                width: 20,
                                height: 3,
                                background: EDGE_COLORS[type] || EDGE_COLORS.default,
                                borderRadius: '2px'
                            }} />
                            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                                {type.replace('_', ' ')} ({count})
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    )
}
