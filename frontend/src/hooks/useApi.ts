import { useState, useEffect, useCallback, useRef } from 'react'

// API fetching hook
export function useApi<T>(endpoint: string, options?: { interval?: number }) {
    const [data, setData] = useState<T | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const fetchData = useCallback(async () => {
        try {
            const response = await fetch(`/api${endpoint}`)
            if (!response.ok) throw new Error('API error')
            const json = await response.json()
            setData(json)
            setError(null)
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Unknown error')
        } finally {
            setLoading(false)
        }
    }, [endpoint])

    useEffect(() => {
        fetchData()

        if (options?.interval) {
            const id = setInterval(fetchData, options.interval)
            return () => clearInterval(id)
        }
    }, [fetchData, options?.interval])

    return { data, loading, error, refetch: fetchData }
}

// WebSocket hook
export function useWebSocket(topics: string[] = ['all']) {
    const [connected, setConnected] = useState(false)
    const [messages, setMessages] = useState<any[]>([])
    const wsRef = useRef<WebSocket | null>(null)

    useEffect(() => {
        const ws = new WebSocket(`ws://${window.location.host}/ws`)
        wsRef.current = ws

        ws.onopen = () => {
            setConnected(true)
            // Subscribe to topics
            topics.forEach(topic => {
                ws.send(JSON.stringify({ action: 'subscribe', topic }))
            })
        }

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)
                setMessages(prev => [...prev.slice(-99), data])
            } catch (e) {
                console.error('WebSocket parse error:', e)
            }
        }

        ws.onclose = () => {
            setConnected(false)
        }

        return () => {
            ws.close()
        }
    }, [topics.join(',')])

    const send = useCallback((message: object) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify(message))
        }
    }, [])

    return { connected, messages, send }
}
