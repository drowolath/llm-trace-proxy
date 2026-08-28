"""Forwards requests to the configured upstream LLM provider with httpx,
streaming SSE chunks back to the caller with O(1) memory (no buffering
of the full response), while scanning the stream for the final `usage`
object so cost/tokens/latency can be exported after the response closes.
"""

import json
import time
from typing import Annotated, Any, AsyncGenerator, cast

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import Response, StreamingResponse

from app.api.dependencies import get_tenant_id
from app.core.config import get_settings
from app.services.metrics import compute_cost
from app.services.observability import export_trace

router = APIRouter(tags=["proxy"])

CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

# Headers that are connection-specific and must not be blindly forwarded
# upstream (host/content-length are recomputed by httpx for the new request).
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


def _build_upstream_headers(request: Request) -> dict[str, str]:
    """Forward inbound headers, swapping in the proxy's own upstream API key."""
    settings = get_settings()
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
    }
    if settings.upstream_api_key:
        headers["authorization"] = f"Bearer {settings.upstream_api_key}"
    return headers


def _extract_usage(chunk: dict[str, Any]) -> dict[str, Any] | None:
    usage = chunk.get("usage")
    if isinstance(usage, dict):
        return cast(dict[str, Any], usage)
    return None


@router.post(CHAT_COMPLETIONS_PATH)
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    tenant_id: Annotated[str, Depends(get_tenant_id)],
) -> Response:
    """Drop-in replacement for OpenAI's chat completions endpoint."""
    settings = get_settings()
    body: dict[str, Any] = await request.json()
    model = str(body.get("model", "unknown"))
    is_streaming = bool(body.get("stream", False))

    if is_streaming:
        stream_options = body.get("stream_options")
        body["stream_options"] = {**stream_options, "include_usage": True} if stream_options else {"include_usage": True}

    client: httpx.AsyncClient = request.app.state.http_client
    url = f"{str(settings.upstream_base_url).rstrip('/')}{CHAT_COMPLETIONS_PATH}"
    headers = _build_upstream_headers(request)
    started_at = time.perf_counter()

    if is_streaming:
        return await _proxy_stream(client, url, body, headers, tenant_id, model, started_at, background_tasks)
    return await _proxy_json(client, url, body, headers, tenant_id, model, started_at, background_tasks)


async def _proxy_json(
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    tenant_id: str,
    model: str,
    started_at: float,
    background_tasks: BackgroundTasks,
) -> Response:
    """Forward a non-streaming request and relay the upstream JSON response as-is."""
    upstream_response = await client.post(url, json=body, headers=headers)
    latency_ms = (time.perf_counter() - started_at) * 1000

    usage = _extract_usage(upstream_response.json()) if upstream_response.status_code < 400 else None
    if usage is not None:
        background_tasks.add_task(
            export_trace,
            tenant_id=tenant_id,
            model=model,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            cost_usd=compute_cost(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            ttft_ms=None,
            streamed=False,
        )

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "application/json"),
    )


async def _proxy_stream(
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    tenant_id: str,
    model: str,
    started_at: float,
    background_tasks: BackgroundTasks,
) -> StreamingResponse:
    """Forward a streaming SSE request, relaying chunks live while scanning for `usage`.

    The upstream connection is opened here, outside the generator, so
    network failures (timeout/connect errors) surface as normal exceptions
    handled by the global handlers instead of being swallowed after a 200
    has already been committed to the client.
    """
    stream_ctx = client.stream("POST", url, json=body, headers=headers)
    upstream_response = await stream_ctx.__aenter__()

    async def event_stream() -> AsyncGenerator[bytes, None]:
        ttft_ms: float | None = None
        usage: dict[str, Any] = {}
        try:
            async for line in upstream_response.aiter_lines():
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - started_at) * 1000
                if line.startswith("data: "):
                    payload = line[len("data: ") :].strip()
                    if payload and payload != "[DONE]":
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            chunk = None
                        if chunk is not None:
                            found_usage = _extract_usage(chunk)
                            if found_usage is not None:
                                usage = found_usage
                yield f"{line}\n".encode()
        finally:
            await stream_ctx.__aexit__(None, None, None)
            latency_ms = (time.perf_counter() - started_at) * 1000
            background_tasks.add_task(
                export_trace,
                tenant_id=tenant_id,
                model=model,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                cost_usd=compute_cost(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)),
                latency_ms=latency_ms,
                ttft_ms=ttft_ms,
                streamed=True,
            )

    return StreamingResponse(
        event_stream(),
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "text/event-stream"),
        background=background_tasks,
    )
