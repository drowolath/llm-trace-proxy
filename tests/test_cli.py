from pathlib import Path

import pytest
from click.testing import CliRunner

from app.cli import cli
from app.core.config import get_settings
from app.services import storage


@pytest.fixture(autouse=True)
def _db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    db_path = str(tmp_path / "traces.db")
    monkeypatch.setenv("DB_PATH", db_path)
    get_settings.cache_clear()
    yield db_path
    get_settings.cache_clear()


def test_summary_with_no_traces(_db_path: str) -> None:
    result = CliRunner().invoke(cli, ["summary"])
    assert result.exit_code == 0
    assert "Requests:    0" in result.output


def test_summary_aggregates_recorded_traces(_db_path: str) -> None:
    storage.insert_trace(
        _db_path,
        {
            "timestamp": 1_700_000_000.0,
            "tenant_id": "acme",
            "model": "gpt-4o-mini",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.001,
            "latency_ms": 40.0,
            "ttft_ms": 10.0,
            "streamed": False,
        },
    )

    result = CliRunner().invoke(cli, ["summary"])
    assert result.exit_code == 0
    assert "Requests:    1" in result.output
    assert "Tokens in:   100" in result.output
    assert "Cost (USD):  0.001000" in result.output


def test_summary_filters_by_tenant(_db_path: str) -> None:
    storage.insert_trace(
        _db_path,
        {
            "timestamp": 1_700_000_000.0,
            "tenant_id": "acme",
            "model": "gpt-4o-mini",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.001,
            "latency_ms": 40.0,
            "ttft_ms": None,
            "streamed": False,
        },
    )

    result = CliRunner().invoke(cli, ["summary", "--tenant-id", "other"])
    assert result.exit_code == 0
    assert "Requests:    0" in result.output


def test_list_with_no_traces(_db_path: str) -> None:
    result = CliRunner().invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "No traces recorded yet." in result.output


def test_list_shows_recorded_trace(_db_path: str) -> None:
    storage.insert_trace(
        _db_path,
        {
            "timestamp": 1_700_000_000.0,
            "tenant_id": "acme",
            "model": "gpt-4o-mini",
            "tokens_in": 100,
            "tokens_out": 50,
            "cost_usd": 0.001,
            "latency_ms": 40.0,
            "ttft_ms": None,
            "streamed": False,
        },
    )

    result = CliRunner().invoke(cli, ["list"])
    assert result.exit_code == 0
    assert "tenant=acme" in result.output
    assert "model=gpt-4o-mini" in result.output
