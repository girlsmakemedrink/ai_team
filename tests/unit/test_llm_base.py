from core.llm.base import (
    DEFAULT_MAX_BUDGET_USD_PER_TIER,
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


def test_default_budget_per_tier_matches_iter8_values() -> None:
    # Pin iter-8 budget caps so a future tightening surfaces in review
    # with reasoning. Sonnet raised $1.50 → $2.50 after iter-7 demo
    # Backend hit $1.50 at 11 turns. See iter_7_demo_report.md
    # Failure 3 + iter_8.md decision #4. Haiku + opus unchanged
    # since iter-6.
    assert DEFAULT_MAX_BUDGET_USD_PER_TIER == {
        "haiku": 0.30,
        "sonnet": 2.50,
        "opus": 4.00,
    }
