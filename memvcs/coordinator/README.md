# Federated Coordinator Server

Minimal reference implementation of the agmem federated coordinator API.

## Installation

```bash
pip install "agmem[coordinator]"
```

## Running the Server

### Development

```bash
# Option 1: Using uvicorn directly
uvicorn memvcs.coordinator.server:app --reload --host 0.0.0.0 --port 8000

# Option 2: Run as Python module
python -m memvcs.coordinator.server
```

### Production

```bash
# With workers for concurrency
uvicorn memvcs.coordinator.server:app --workers 4 --host 0.0.0.0 --port 8000

# Behind reverse proxy (e.g., nginx)
uvicorn memvcs.coordinator.server:app --proxy-headers --forwarded-allow-ips='*'
```

## Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install "agmem[coordinator]"

EXPOSE 8000
CMD ["uvicorn", "memvcs.coordinator.server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t agmem-coordinator .
docker run -p 8000:8000 agmem-coordinator
```

## API Endpoints

### Health Check
```bash
GET /health
```

Returns:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-01T12:00:00Z"
}
```

### Push Summary
```bash
POST /push
Content-Type: application/json

{
  "summary": {
    "agent_id": "agent-123",
    "timestamp": "2026-02-01T12:00:00Z",
    "topic_counts": {
      "user-preferences": 5,
      "project-context": 3
    },
    "fact_hashes": [
      "abc123...",
      "def456..."
    ],
    "metadata": {
      "version": "0.2.1"
    }
  }
}
```

Returns:
```json
{
  "status": "accepted",
  "agent_id": "agent-123",
  "timestamp": "2026-02-01T12:00:01Z",
  "message": "Summary from agent-123 stored successfully"
}
```

### Pull Merged Summaries
```bash
GET /pull
```

Returns:
```json
{
  "merged_topic_counts": {
    "user-preferences": 15,
    "project-context": 8
  },
  "unique_fact_hashes": [
    "abc123...",
    "def456...",
    "ghi789..."
  ],
  "contributing_agents": 3,
  "last_updated": "2026-02-01T12:00:00Z",
  "metadata": {
    "total_facts": 3,
    "total_topics": 2
  }
}
```

## Client Usage

From agmem client:

```bash
# Configure coordinator URL
agmem config set federated.coordinator_url "http://localhost:8000"

# Push local summary
agmem federated push

# Pull merged summaries
agmem federated pull
```

## Storage

**Current:** In-memory (resets on restart)

**Production:** Replace with persistent storage:
- **PostgreSQL:** Best for structured queries
- **Redis:** Best for high-throughput
- **MongoDB:** Best for flexible schemas

Example PostgreSQL schema:
```sql
CREATE TABLE summaries (
    id SERIAL PRIMARY KEY,
    agent_id VARCHAR(255) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    topic_counts JSONB,
    fact_hashes TEXT[],
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_agent_id ON summaries(agent_id);
CREATE INDEX idx_timestamp ON summaries(timestamp);
```

## Security

**⚠️ Important:** This reference implementation has NO authentication.

For production, add:

1. **API Key Authentication:**
```python
from fastapi import Security, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)):
    if credentials.credentials != os.getenv("API_KEY"):
        raise HTTPException(status_code=401, detail="Invalid API key")
    return credentials.credentials

@app.post("/push")
async def push(request: PushRequest, api_key: str = Depends(verify_api_key)):
    # ...
```

2. **Rate Limiting:**
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/push")
@limiter.limit("10/minute")
async def push(request: Request, data: PushRequest):
    # ...
```

3. **HTTPS:** Use reverse proxy (nginx, Caddy) with SSL certificates

4. **CORS:** Configure allowed origins
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourdomain.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
```

## Monitoring

Interactive API documentation available at:
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

Health check for monitoring tools:
```bash
curl http://localhost:8000/health
```

## Environment Variables

```bash
# Optional: Configure listening address
AGMEM_COORDINATOR_HOST=0.0.0.0
AGMEM_COORDINATOR_PORT=8000

# Optional: Database connection (if using persistent storage)
DATABASE_URL=postgresql://user:pass@localhost/agmem

# Required for production: API authentication
API_KEY=your-secret-key-here
```

## License

MIT License - See main agmem LICENSE file
