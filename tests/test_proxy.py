import json
import logging

import httpx
import pytest
import respx

from app.core.config import get_settings

UPSTREAM_URL = "https://api.openai.com/v1/chat/completions"
TENANT_HEADERS = {"X-Tenant-ID": "acme"}


async def test_missing_tenant_header_returns_400(client: httpx.AsyncClient) -> None:
    response = await client.post("/v1/chat/completions", json={"model": "gpt-4o-mini", "messages": []})
    assert response.status_code == 400


@respx.mock
async def test_non_streaming_forwards_upstream_response(client: httpx.AsyncClient) -> None:
    respx.post(UPSTREAM_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "x",
                "choices": [{"message": {"role": "assistant", "content": "hello"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )
    )

    response = await client.post(
        "/v1/chat/completions",
        headers=TENANT_HEADERS,
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "hello"


@respx.mock
async def test_non_streaming_exports_trace(client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture) -> None:
    respx.post(UPSTREAM_URL).mock(
        return_value=httpx.Response(
            200,
            json={"id": "x", "choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
        )
    )

    with caplog.at_level(logging.INFO, logger="llm_trace_proxy.observability"):
        response = await client.post(
            "/v1/chat/completions",
            headers=TENANT_HEADERS,
            json={"model": "gpt-4o-mini", "messages": []},
        )

    assert response.status_code == 200
    trace = json.loads(caplog.records[-1].message)
    assert trace["tenant_id"] == "acme"
    assert trace["model"] == "gpt-4o-mini"
    assert trace["tokens_in"] == 5
    assert trace["tokens_out"] == 2
    assert trace["cost_usd"] == pytest.approx(5 / 1_000_000 * 0.15 + 2 / 1_000_000 * 0.60)
    assert trace["streamed"] is False


@respx.mock
async def test_upstream_error_status_is_passed_through(client: httpx.AsyncClient) -> None:
    respx.post(UPSTREAM_URL).mock(
        return_value=httpx.Response(400, json={"error": {"message": "bad request upstream"}})
    )

    response = await client.post(
        "/v1/chat/completions",
        headers=TENANT_HEADERS,
        json={"model": "gpt-4o-mini", "messages": []},
    )

    assert response.status_code == 400
    assert response.json() == {"error": {"message": "bad request upstream"}}


@respx.mock
async def test_upstream_timeout_returns_504(client: httpx.AsyncClient) -> None:
    respx.post(UPSTREAM_URL).mock(side_effect=httpx.TimeoutException("boom"))

    response = await client.post(
        "/v1/chat/completions",
        headers=TENANT_HEADERS,
        json={"model": "gpt-4o-mini", "messages": []},
    )

    assert response.status_code == 504


@respx.mock
async def test_upstream_connect_error_returns_502(client: httpx.AsyncClient) -> None:
    respx.post(UPSTREAM_URL).mock(side_effect=httpx.ConnectError("boom"))

    response = await client.post(
        "/v1/chat/completions",
        headers=TENANT_HEADERS,
        json={"model": "gpt-4o-mini", "messages": []},
    )

    assert response.status_code == 502


@respx.mock
async def test_streaming_relays_chunks_and_extracts_usage(client: httpx.AsyncClient) -> None:
    sse_body = (
        b'data: {"choices": [{"delta": {"content": "tok0 "}}]}\n\n'
        b'data: {"choices": [{"delta": {"content": "tok1 "}}]}\n\n'
        b'data: {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3}}\n\n'
        b"data: [DONE]\n\n"
    )
    respx.post(UPSTREAM_URL).mock(
        return_value=httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})
    )

    async with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=TENANT_HEADERS,
        json={"model": "gpt-4o-mini", "messages": [], "stream": True},
    ) as response:
        assert response.status_code == 200
        chunks = [line async for line in response.aiter_lines()]

    assert "data: [DONE]" in chunks
    assert any("tok0" in line for line in chunks)


@respx.mock
async def test_streaming_injects_include_usage(client: httpx.AsyncClient) -> None:
    route = respx.post(UPSTREAM_URL).mock(
        return_value=httpx.Response(200, content=b"data: [DONE]\n\n", headers={"content-type": "text/event-stream"})
    )

    async with client.stream(
        "POST",
        "/v1/chat/completions",
        headers=TENANT_HEADERS,
        json={"model": "gpt-4o-mini", "messages": [], "stream": True, "stream_options": {"foo": "bar"}},
    ) as response:
        async for _ in response.aiter_lines():
            pass

    sent_body = json.loads(route.calls.last.request.content)
    assert sent_body["stream_options"] == {"foo": "bar", "include_usage": True}


@respx.mock
async def test_streaming_exports_trace_with_ttft(
    client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    sse_body = (
        b'data: {"choices": [{"delta": {"content": "tok0 "}}]}\n\n'
        b'data: {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3}}\n\n'
        b"data: [DONE]\n\n"
    )
    respx.post(UPSTREAM_URL).mock(
        return_value=httpx.Response(200, content=sse_body, headers={"content-type": "text/event-stream"})
    )

    with caplog.at_level(logging.INFO, logger="llm_trace_proxy.observability"):
        async with client.stream(
            "POST",
            "/v1/chat/completions",
            headers=TENANT_HEADERS,
            json={"model": "gpt-4o-mini", "messages": [], "stream": True},
        ) as response:
            async for _ in response.aiter_lines():
                pass

    trace = json.loads(caplog.records[-1].message)
    assert trace["tokens_in"] == 10
    assert trace["tokens_out"] == 3
    assert trace["streamed"] is True
    assert trace["ttft_ms"] is not None


@respx.mock
async def test_upstream_api_key_injected_as_bearer_token(client: httpx.AsyncClient) -> None:
    get_settings.cache_clear()
    route = respx.post(UPSTREAM_URL).mock(return_value=httpx.Response(200, json={"choices": [], "usage": {}}))

    import os

    os.environ["UPSTREAM_API_KEY"] = "sk-test-123"
    try:
        get_settings.cache_clear()
        response = await client.post(
            "/v1/chat/completions",
            headers=TENANT_HEADERS,
            json={"model": "gpt-4o-mini", "messages": []},
        )
    finally:
        del os.environ["UPSTREAM_API_KEY"]
        get_settings.cache_clear()

    assert response.status_code == 200
    assert route.calls.last.request.headers["authorization"] == "Bearer sk-test-123"
