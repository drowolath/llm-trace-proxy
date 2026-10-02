from pathlib import Path

from app.services import storage


def _record(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "timestamp": 1_700_000_000.0,
        "tenant_id": "acme",
        "model": "gpt-4o-mini",
        "tokens_in": 100,
        "tokens_out": 50,
        "cost_usd": 0.0001,
        "latency_ms": 42.0,
        "ttft_ms": 10.0,
        "streamed": False,
    }
    base.update(overrides)
    return base


def test_summarize_empty_db_returns_zeroes(tmp_path: Path) -> None:
    db_path = str(tmp_path / "traces.db")
    stats = storage.summarize(db_path)
    assert stats == {
        "request_count": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "avg_latency_ms": 0.0,
        "avg_ttft_ms": None,
    }


def test_insert_and_summarize(tmp_path: Path) -> None:
    db_path = str(tmp_path / "traces.db")
    storage.insert_trace(db_path, _record(tokens_in=100, tokens_out=50, cost_usd=0.001, latency_ms=40.0))
    storage.insert_trace(db_path, _record(tokens_in=200, tokens_out=100, cost_usd=0.002, latency_ms=60.0))

    stats = storage.summarize(db_path)
    assert stats["request_count"] == 2
    assert stats["tokens_in"] == 300
    assert stats["tokens_out"] == 150
    assert stats["cost_usd"] == 0.003
    assert stats["avg_latency_ms"] == 50.0


def test_summarize_filters_by_tenant_and_model(tmp_path: Path) -> None:
    db_path = str(tmp_path / "traces.db")
    storage.insert_trace(db_path, _record(tenant_id="acme", model="gpt-4o-mini"))
    storage.insert_trace(db_path, _record(tenant_id="other", model="gpt-4o"))

    stats = storage.summarize(db_path, tenant_id="acme")
    assert stats["request_count"] == 1

    stats = storage.summarize(db_path, model="gpt-4o")
    assert stats["request_count"] == 1

    stats = storage.summarize(db_path, tenant_id="acme", model="gpt-4o")
    assert stats["request_count"] == 0


def test_summarize_filters_by_since_ts(tmp_path: Path) -> None:
    db_path = str(tmp_path / "traces.db")
    storage.insert_trace(db_path, _record(timestamp=1_000.0))
    storage.insert_trace(db_path, _record(timestamp=2_000.0))

    stats = storage.summarize(db_path, since_ts=1_500.0)
    assert stats["request_count"] == 1


def test_list_traces_orders_newest_first_and_respects_limit(tmp_path: Path) -> None:
    db_path = str(tmp_path / "traces.db")
    storage.insert_trace(db_path, _record(timestamp=1_000.0, tenant_id="a"))
    storage.insert_trace(db_path, _record(timestamp=3_000.0, tenant_id="b"))
    storage.insert_trace(db_path, _record(timestamp=2_000.0, tenant_id="c"))

    rows = storage.list_traces(db_path, limit=2)
    assert [row["tenant_id"] for row in rows] == ["b", "c"]


def test_list_traces_empty_db_returns_empty_list(tmp_path: Path) -> None:
    db_path = str(tmp_path / "traces.db")
    assert storage.list_traces(db_path) == []
