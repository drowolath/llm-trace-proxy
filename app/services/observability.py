import json
import logging
import time

logger = logging.getLogger("llm_trace_proxy.observability")


def export_trace(
    tenant_id: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: float,
    ttft_ms: float | None,
    streamed: bool,
) -> None:
    """Emit one structured JSON trace line per proxied request.

    Called from a FastAPI BackgroundTask, after the response has already
    been sent to the caller. Swap this body for a Sentry span / Betterstack
    HTTP sink later without touching the proxy route itself.
    """
    record = {
        "timestamp": time.time(),
        "tenant_id": tenant_id,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost_usd, 8),
        "latency_ms": round(latency_ms, 2),
        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
        "streamed": streamed,
    }
    logger.info(json.dumps(record))
