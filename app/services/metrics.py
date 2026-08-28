# USD price per 1M tokens, as (input_price, output_price).
MODEL_PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
    "gpt-3.5-turbo": (0.50, 1.50),
}

DEFAULT_PRICING_PER_MILLION_TOKENS: tuple[float, float] = (0.0, 0.0)


def compute_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    """Return the USD cost of a request given its model and token usage."""
    price_in, price_out = MODEL_PRICING_PER_MILLION_TOKENS.get(
        model, DEFAULT_PRICING_PER_MILLION_TOKENS
    )
    return (tokens_in / 1_000_000) * price_in + (tokens_out / 1_000_000) * price_out
