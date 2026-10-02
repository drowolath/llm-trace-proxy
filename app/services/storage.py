"""SQLite persistence for proxied-request traces.

Kept separate from observability.py (which only logs)
so it can be queried for structured data without parsing log lines.
"""

import sqlite3
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    tenant_id TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms REAL NOT NULL,
    ttft_ms REAL,
    streamed INTEGER NOT NULL
)
"""


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    return conn


def insert_trace(db_path: str, record: dict[str, Any]) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO traces
                (timestamp, tenant_id, model, tokens_in, tokens_out, cost_usd, latency_ms, ttft_ms, streamed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["timestamp"],
                record["tenant_id"],
                record["model"],
                record["tokens_in"],
                record["tokens_out"],
                record["cost_usd"],
                record["latency_ms"],
                record["ttft_ms"],
                int(record["streamed"]),
            ),
        )


def _where_clause(tenant_id: str | None, model: str | None, since_ts: float | None) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if tenant_id is not None:
        clauses.append("tenant_id = ?")
        params.append(tenant_id)
    if model is not None:
        clauses.append("model = ?")
        params.append(model)
    if since_ts is not None:
        clauses.append("timestamp >= ?")
        params.append(since_ts)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params


def summarize(
    db_path: str,
    tenant_id: str | None = None,
    model: str | None = None,
    since_ts: float | None = None,
) -> dict[str, Any]:
    where, params = _where_clause(tenant_id, model, since_ts)
    with _connect(db_path) as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*),
                COALESCE(SUM(tokens_in), 0),
                COALESCE(SUM(tokens_out), 0),
                COALESCE(SUM(cost_usd), 0.0),
                COALESCE(AVG(latency_ms), 0.0),
                AVG(ttft_ms)
            FROM traces
            {where}
            """,
            params,
        ).fetchone()

    request_count, tokens_in, tokens_out, cost_usd, avg_latency_ms, avg_ttft_ms = row
    return {
        "request_count": request_count,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "avg_latency_ms": avg_latency_ms,
        "avg_ttft_ms": avg_ttft_ms,
    }


def list_traces(
    db_path: str,
    limit: int = 20,
    tenant_id: str | None = None,
    model: str | None = None,
) -> list[dict[str, Any]]:
    where, params = _where_clause(tenant_id, model, since_ts=None)
    with _connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT timestamp, tenant_id, model, tokens_in, tokens_out, cost_usd, latency_ms, ttft_ms, streamed
            FROM traces
            {where}
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            [*params, limit],
        ).fetchall()
    return [dict(row) for row in rows]
