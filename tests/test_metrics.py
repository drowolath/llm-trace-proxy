from app.services.metrics import compute_cost


def test_compute_cost_known_model() -> None:
    # gpt-4o-mini: $0.15 / $0.60 per 1M tokens.
    cost = compute_cost("gpt-4o-mini", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost == 0.75


def test_compute_cost_unknown_model_is_zero() -> None:
    assert compute_cost("some-unlisted-model", tokens_in=1000, tokens_out=1000) == 0.0


def test_compute_cost_zero_tokens_is_zero() -> None:
    assert compute_cost("gpt-4o", tokens_in=0, tokens_out=0) == 0.0
