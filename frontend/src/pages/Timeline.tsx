import { useApi } from '../hooks/useApi'

interface Commit {
    short_hash: string
    message: string
    author: string
    timestamp: string
}

interface LogData {
    commits: Commit[]
}

export default function Timeline() {
    const { data, loading, error } = useApi<LogData>('/log')

    if (loading) return <div className="loading">Loading timeline...</div>
    if (error) return <div className="error">Error: {error}</div>

    return (
        <div className="timeline-page">
            <h2>Timeline</h2>

            <div className="card">
                <h3>Recent Commits ({data?.commits?.length || 0})</h3>
                <ul className="list">
                    {data?.commits?.slice(0, 20).map((commit) => (
                        <li key={commit.short_hash}>
                            <div>
                                <code>{commit.short_hash}</code>
                                <span style={{ marginLeft: '10px' }}>{commit.message}</span>
                            </div>
                            <span style={{ fontSize: '12px', color: '#888' }}>
                                {new Date(commit.timestamp).toLocaleDateString()}
                            </span>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    )
}
