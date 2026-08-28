import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


async def upstream_timeout_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=504,
        content={
            "error": {
                "message": "Upstream LLM provider timed out.",
                "type": "upstream_timeout"
            }
        },
    )


async def upstream_connect_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": "Unable to reach upstream LLM provider.",
                "type": "upstream_unreachable"
            }
        },
    )


async def upstream_http_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={
            "error": {
                "message": str(exc),
                "type": "upstream_error"
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Attach proxy-specific exception handlers to the FastAPI app."""
    app.add_exception_handler(httpx.TimeoutException, upstream_timeout_handler)
    app.add_exception_handler(httpx.ConnectError, upstream_connect_error_handler)
    app.add_exception_handler(httpx.HTTPError, upstream_http_error_handler)
