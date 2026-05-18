from core.llm.base import (
    PRICE_TABLE_CENTS_PER_MTOK,
    TokensUsage,
    estimate_cost_cents,
)


def test_price_table_has_three_tiers() -> None:
    assert "claude-haiku-4-5" in PRICE_TABLE_CENTS_PER_MTOK
    assert "claude-sonnet-4-6" in PRICE_TABLE_CENTS_PER_MTOK
    assert "claude-opus-4-7" in PRICE_TABLE_CENTS_PER_MTOK


def test_estimate_cost_haiku_trivial() -> None:
    tokens = TokensUsage(input=1_000_000, output=0, model="claude-haiku-4-5")
    cents = estimate_cost_cents("claude-haiku-4-5", tokens)
    # Haiku input price = 80 cents per Mtok
    assert cents == 80


def test_estimate_cost_unknown_model_zero() -> None:
    tokens = TokensUsage(input=999_999, output=999_999, model="not-real")
    assert estimate_cost_cents("not-real", tokens) == 0


def test_tokens_total() -> None:
    t = TokensUsage(input=10, output=5, cached_input=3, model="x")
    assert t.total == 15
