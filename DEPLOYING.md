# Deploying Project Unemploy Joel

## Quick Start

```bash
# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Set your domain (omit for localhost)
export DOMAIN=crossword.example.com
export ALLOWED_ORIGINS=https://crossword.example.com

# Build and run
docker compose up -d
```

The app will be available on ports 80/443. Caddy auto-provisions TLS when `DOMAIN` is a real domain.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Anthropic API key for clue generation and fill judging |
| `DOMAIN` | No | `localhost` | Domain for Caddy TLS. Use a real domain for auto-HTTPS |
| `ALLOWED_ORIGINS` | No | `http://localhost:5173` | Comma-separated CORS origins |
| `LOG_LEVEL` | No | `info` | Logging level (debug, info, warning, error) |

## Running Without Caddy

To run just the app (e.g., behind your own reverse proxy):

```bash
docker compose up -d app
```

The app listens on port 8000. Map it as needed:

```yaml
# Add to docker-compose.yml under app service:
ports:
  - "8000:8000"
```

## Local Development

```bash
pip install -e ".[dev]"
cd frontend && npm install && npm run dev &
uvicorn server.app:app --reload
```

Frontend dev server (port 5173) proxies `/api` to the backend (port 8000).

## Cost Estimates

Each puzzle generation costs approximately **$0.05** in Anthropic API calls:
- Fill judging: ~15 calls × $0.003 = $0.045
- Clue generation: ~$0.006

Rate limiting is set to 5 generations per minute per IP.

## Budget & Alerts

Set spending limits on your [Anthropic Console](https://console.anthropic.com/settings/limits):
1. Set a monthly spend limit appropriate for your expected usage
2. Enable email alerts at 50% and 80% thresholds
3. Monitor usage on the Console dashboard

## Health Check

```bash
curl http://localhost:8000/api/health
# {"status":"ok","words":48000}
```

## Cloud Deployment Notes

For cloud platforms (AWS ECS, GCP Cloud Run, Fly.io, etc.):
- Use the platform's secrets manager for `ANTHROPIC_API_KEY`
- The Docker `HEALTHCHECK` is already configured
- The app binds to `0.0.0.0:8000` with 4 uvicorn workers
- If the platform provides its own reverse proxy/TLS, run just the `app` service
