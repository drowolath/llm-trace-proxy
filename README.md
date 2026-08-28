# LLM-Trace-Proxy

A zero-code, asynchronous HTTP reverse proxy for LLM traffic. It sits between your services and an LLM provider (OpenAI-compatible endpoints — OpenAI, Anthropic-via-compat, vLLM, Ollama), forwarding `POST /v1/chat/completions` requests unmodified while recording per-tenant cost, token usage, and latency with no change required in the calling application.

## Features

- **Multi-tenant attribution** : every request must have a `X-Tenant-ID` header, used to attribute cost and usage.
- **Zero-buffer SSE streaming** : streamed responses are relayed chunk-by-chunk as they arrive (O(1) memory).
- **Token usage interception** : `stream_options.include_usage` is injected into requests, and the final `usage` chunk is read in an unblocking way.
- **Cost calculation** : per-model USD pricing table, computed from prompt/completion token counts.
- **Async observability export** : tenant, model, tokens in/out, cost, latency, and time-to-first-token can be exported, after the response has already been sent.
- **Resilient upstream handling** : upstream timeouts and connection failures are mapped to `504`/`502` responses instead of leaking as unhandled errors, even mid-stream.

## Configuration

All settings are environment variables (optionally via a `.env` file), see `app/core/config.py`:

| Variable | Default | Description |
| --- | --- | --- |
| `UPSTREAM_BASE_URL` | `https://api.openai.com` | Base URL of the upstream LLM provider |
| `UPSTREAM_API_KEY` | _(unset)_ | Injected as `Authorization: Bearer <key>` on upstream requests |
| `CONNECT_TIMEOUT`, `READ_TIMEOUT`, `WRITE_TIMEOUT`, `POOL_TIMEOUT` | `5.0`, `60.0`, `10.0`, `5.0` | `httpx.AsyncClient` timeouts, in seconds |
| `CORS_ALLOW_ORIGINS` | `["*"]` | Allowed CORS origins |
| `SENTRY_DSN` | _(unset)_ | Reserved for future Sentry export |
| `BETTERSTACK_SOURCE_TOKEN` | _(unset)_ | Reserved for future Betterstack export |

## Running locally

Requires Python 3.12+ and [Poetry](https://python-poetry.org/).

```bash
poetry install
poetry run uvicorn app.main:app --reload
```

The proxy listens on `http://127.0.0.1:8000`. Example request:

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "X-Tenant-ID: acme" \
  -H "Content-Type: application/json" \
  -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]}'
```

## Tests

```bash
poetry run pytest
```

## Docker

```bash
docker build -t llm-trace-proxy .
docker run -p 8000:8000 -e UPSTREAM_API_KEY=sk-... llm-trace-proxy
```

The image is a multi-stage build (Poetry-installed venv copied into a slim runtime layer), runs as a non-root user, and exposes a container-level `HEALTHCHECK` against `/healthz`.
