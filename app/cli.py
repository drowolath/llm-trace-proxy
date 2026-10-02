"""CLI for inspecting proxy traces (cost, tokens, latency) without going
through the HTTP API.

Reads the same SQLite database that app.services.observability writes to,
so it works whether or not the proxy server is currently running.
"""

from datetime import datetime, timedelta, timezone

import click

from app.core.config import get_settings
from app.services import storage


@click.group()
def cli() -> None:
    """Inspect traces recorded by the llm-trace-proxy."""


@cli.command()
@click.option("--tenant-id", default=None, help="Filter by tenant.")
@click.option("--model", default=None, help="Filter by model.")
@click.option("--since-hours", type=float, default=None, help="Only include traces from the last N hours.")
def summary(tenant_id: str | None, model: str | None, since_hours: float | None) -> None:
    """Print aggregate request count, tokens, cost, and latency."""
    since_ts = None
    if since_hours is not None:
        since_ts = (datetime.now(timezone.utc) - timedelta(hours=since_hours)).timestamp()

    stats = storage.summarize(get_settings().db_path, tenant_id=tenant_id, model=model, since_ts=since_ts)

    click.echo(f"Requests:    {stats['request_count']}")
    click.echo(f"Tokens in:   {stats['tokens_in']}")
    click.echo(f"Tokens out:  {stats['tokens_out']}")
    click.echo(f"Cost (USD):  {stats['cost_usd']:.6f}")
    click.echo(f"Avg latency: {stats['avg_latency_ms']:.2f} ms")
    if stats["avg_ttft_ms"] is not None:
        click.echo(f"Avg TTFT:    {stats['avg_ttft_ms']:.2f} ms")


@cli.command("list")
@click.option("--limit", default=20, help="Number of most recent traces to show.")
@click.option("--tenant-id", default=None, help="Filter by tenant.")
@click.option("--model", default=None, help="Filter by model.")
def list_traces(limit: int, tenant_id: str | None, model: str | None) -> None:
    """Print the most recent traces, newest first."""
    rows = storage.list_traces(get_settings().db_path, limit=limit, tenant_id=tenant_id, model=model)
    if not rows:
        click.echo("No traces recorded yet.")
        return
    for row in rows:
        when = datetime.fromtimestamp(row["timestamp"], tz=timezone.utc).isoformat()
        click.echo(
            f"{when}  tenant={row['tenant_id']:<12} model={row['model']:<14} "
            f"tokens={row['tokens_in']}/{row['tokens_out']} cost=${row['cost_usd']:.6f} "
            f"latency={row['latency_ms']:.1f}ms streamed={bool(row['streamed'])}"
        )


if __name__ == "__main__":
    cli()
