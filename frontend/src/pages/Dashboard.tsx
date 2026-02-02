import { useApi } from '../hooks/useApi'

interface StatusData {
    branch: string
    head: string
    staged: string[]
    modified: string[]
    is_clean: boolean
}

export default function Dashboard() {
    const { data: status, loading } = useApi<StatusData>('/status', { interval: 5000 })
    const { data: compliance } = useApi<any>('/compliance')
    const { data: confidence } = useApi<any>('/confidence')

    if (loading) return <div className="loading">Loading...</div>

    return (
        <div className="dashboard">
            <h2>Dashboard</h2>

            <div className="grid">
                <div className="card">
                    <h3>Repository Status</h3>
                    <div className="value">
                        <span className={`status-badge ${status?.is_clean ? 'success' : 'warning'}`}>
                            {status?.is_clean ? 'Clean' : 'Modified'}
                        </span>
                    </div>
                    <p>Branch: <code>{status?.branch}</code></p>
                    <p>HEAD: <code>{status?.head}</code></p>
                </div>

                <div className="card">
                    <h3>Staged Files</h3>
                    <div className="value">{status?.staged?.length || 0}</div>
                </div>

                <div className="card">
                    <h3>Modified Files</h3>
                    <div className="value">{status?.modified?.length || 0}</div>
                </div>
            </div>

            <div className="grid">
                <div className="card">
                    <h3>Privacy Budget</h3>
                    <div className="value">{compliance?.total_queries || 0}</div>
                    <p>Total queries</p>
                </div>

                <div className="card">
                    <h3>Low Confidence</h3>
                    <div className="value">{confidence?.low_confidence_count || 0}</div>
                    <p>Memories below threshold</p>
                </div>
            </div>

            {status?.staged && status.staged.length > 0 && (
                <div className="card">
                    <h3>Staged Files</h3>
                    <ul className="list">
                        {status.staged.map(file => (
                            <li key={file}><code>{file}</code></li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    )
}
