import { useApi } from '../hooks/useApi'

interface HealthCheck {
    checks: {
        consolidation: { candidate_count: number }
        cleanup: { candidate_count: number }
        duplicates: { duplicate_groups: number }
    }
    alerts: Array<{ id: string; type: string; message: string; severity: string }>
}

export default function Agents() {
    const { data, loading, refetch } = useApi<{ health_check: HealthCheck }>('/archaeology')

    if (loading) return <div className="loading">Loading agents...</div>

    const health = data?.health_check

    return (
        <div className="agents-page">
            <h2>Memory Agents</h2>

            <div className="grid">
                <div className="card">
                    <h3>Consolidation Candidates</h3>
                    <div className="value">{health?.checks?.consolidation?.candidate_count || 0}</div>
                </div>
                <div className="card">
                    <h3>Cleanup Candidates</h3>
                    <div className="value">{health?.checks?.cleanup?.candidate_count || 0}</div>
                </div>
                <div className="card">
                    <h3>Duplicate Groups</h3>
                    <div className="value">{health?.checks?.duplicates?.duplicate_groups || 0}</div>
                </div>
            </div>

            <div className="card">
                <h3>Active Alerts</h3>
                {health?.alerts && health.alerts.length > 0 ? (
                    <ul className="list">
                        {health.alerts.map(alert => (
                            <li key={alert.id}>
                                <span className={`status-badge ${alert.severity === 'warning' ? 'warning' : 'danger'}`}>
                                    {alert.type}
                                </span>
                                <span>{alert.message}</span>
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p>No active alerts</p>
                )}
            </div>

            <button onClick={() => refetch()}>Refresh Health Check</button>
        </div>
    )
}
