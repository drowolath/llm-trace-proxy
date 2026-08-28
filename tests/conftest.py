"""Shared pytest fixtures: an ASGI-wired async client that runs app lifespan."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio

from app.core.config import get_settings
from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """An httpx client talking to the app in-process, with lifespan (and thus
    app.state.http_client, which the proxy route depends on) started."""
    get_settings.cache_clear()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
    get_settings.cache_clear()
