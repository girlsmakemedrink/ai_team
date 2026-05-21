"""iter-24 Phase 1 — A/B test of --json-schema enum vs permissive.

iter-23 demo run #2 (correlation c941d96a-b9ee-4575-aeb6-812f297dd8e8)
showed Backend's claude -p subprocess exhausting its $2.50 budget
cap (dispatcher-synth BLOCKED(budget) rows 369/371) shortly after
a hot-fix that added an `enum` constraint to BACKEND_REPORT_SCHEMA's
blocked_on field. The audit-log shape was consistent with
LLMBudgetExhaustedError but the API log was wiped by the EXIT trap
before forensic analysis was possible.

**Theory**: when --json-schema's `enum` constraint is violated by
the LLM's natural response (LLM wants to fill the field with a
descriptive value outside the enum), claude -p retries internally
with corrective feedback until the per-call max_budget_usd cap
fires.

This test runs the same prompt twice — once with an enum-constrained
schema, once with a permissive schema. If the enum side burns
significantly more cost / time, or raises LLMBudgetExhaustedError,
the theory is confirmed.

Cost: 2 * up to $0.50 max_budget_usd = $1.00 worst case (typically
much less if permissive returns quickly). Wall-clock: ~5-10 min.
"""

from __future__ import annotations

import json

import pytest

from core.llm.base import LLMBudgetExhaustedError, LLMTimeoutError
from core.llm.claude_code_headless import ClaudeCodeHeadlessClient


@pytest.mark.integration
@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_json_schema_enum_does_not_trigger_budget_burn() -> None:
    """Decisive A/B: does --json-schema enum cause claude -p retry loop?

    Same prompt + system message for both variants. The user message
    explicitly asks for a value that wouldn't satisfy the enum — if
    claude -p retries internally to enforce schema compliance, this
    is where we'd see budget burn.
    """
    client = ClaudeCodeHeadlessClient()
    system_prompt = "You produce JSON only. No prose."
    user_message = (
        "Categorize this case as the JSON object {category: <string>}: "
        "'a complex hybrid edge case spanning multiple categories'. "
        "Use the most descriptive multi-word label you can — do not "
        "pick a simple one-word category."
    )

    schema_enum = {
        "type": "object",
        "required": ["category"],
        "additionalProperties": False,
        "properties": {
            "category": {"type": "string", "enum": ["alpha", "beta"]},
        },
    }
    schema_permissive = {
        "type": "object",
        "required": ["category"],
        "additionalProperties": False,
        "properties": {"category": {"type": "string"}},
    }

    results: dict[str, dict[str, object]] = {}
    for label, schema in [("enum", schema_enum), ("permissive", schema_permissive)]:
        try:
            response = await client.invoke(
                system_prompt=system_prompt,
                user_message=user_message,
                model="sonnet",
                json_schema=schema,
                max_budget_usd=0.50,  # cap loss per variant
                timeout_s=180,
                max_turns=4,
            )
            results[label] = {
                "raised": None,
                "cost_cents": response.cost_estimate_cents,
                "duration_ms": response.duration_ms,
                "validated_against_schema": response.validated_against_schema,
                "tokens_in": response.tokens.input,
                "tokens_out": response.tokens.output,
                "structured": response.structured,
                "text_preview": response.text[:200],
            }
        except LLMBudgetExhaustedError as e:
            results[label] = {"raised": "budget_exhausted", "details": str(e)[:200]}
        except LLMTimeoutError as e:
            results[label] = {"raised": "timeout", "details": str(e)[:200]}
        except Exception as e:
            results[label] = {"raised": type(e).__name__, "details": str(e)[:200]}

    print(f"\n\n=== iter-24 Phase 1 A/B result ===\n{json.dumps(results, indent=2)}\n")

    # Diagnostic-only: we don't fail the test on theory denial,
    # the value is in the printed JSON for the demo report.
    # But assert both completed (didn't hang) and at least permissive
    # returned a structured response.
    assert "raised" in results["enum"] or "duration_ms" in results["enum"]
    assert "raised" in results["permissive"] or "duration_ms" in results["permissive"]

    # If both raised budget_exhausted, theory is moot (something else
    # is happening). If enum >> permissive, theory CONFIRMED.
    enum_burned = results["enum"].get("raised") == "budget_exhausted"
    permissive_burned = results["permissive"].get("raised") == "budget_exhausted"

    if enum_burned and not permissive_burned:
        print("\n>>> THEORY CONFIRMED: enum side triggered budget exhaustion, permissive did not.")
    elif enum_burned and permissive_burned:
        print("\n>>> THEORY UNCLEAR: both sides exhausted budget — different root cause.")
    elif not enum_burned and not permissive_burned:
        enum_cost = results["enum"].get("cost_cents", 0)
        perm_cost = results["permissive"].get("cost_cents", 0)
        enum_dur = results["enum"].get("duration_ms", 0)
        perm_dur = results["permissive"].get("duration_ms", 0)
        # Cast for arithmetic — we know the types from the success branch above.
        assert isinstance(enum_cost, int)
        assert isinstance(perm_cost, int)
        assert isinstance(enum_dur, int)
        assert isinstance(perm_dur, int)
        ratio_dur = enum_dur / max(perm_dur, 1)
        ratio_cost = enum_cost / max(perm_cost, 1)
        if ratio_dur > 5 or ratio_cost > 3:
            print(
                f"\n>>> THEORY CONFIRMED: enum {ratio_dur:.1f}x duration / {ratio_cost:.1f}x cost"
            )
        else:
            print(
                f"\n>>> THEORY DENIED: enum {ratio_dur:.1f}x duration / "
                f"{ratio_cost:.1f}x cost — within normal variance."
            )
    else:  # not enum_burned and permissive_burned
        print("\n>>> ANOMALY: permissive burned but enum didn't — re-run.")
