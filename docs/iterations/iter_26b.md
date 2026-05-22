# Iter-26b Implementation Plan — Single-candidate product validator

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Validate one product candidate (`telegram-tech-publisher`, owner-picked from iter-26a) with a 4-agent diligence chain — MR deep competitor scan, Architect technical-risk register, PM revenue-model stress-test, QA go/no-go synthesis — before committing to iter-27 MVP build.

**Architecture:** New CLI `ai-team validate-product` extracts the slug's section from the iter-26a brainstorm file, submits one root task with `inputs.intent = "validate_product"`. TL receives it, decomposes into 4 subtasks via the existing `DECOMPOSITION_SCHEMA` (no schema change — the optional `inputs` field on subtasks landed in iter-26a commit `68e8c31`): 3 parallel (MR `validate_competitors`, Architect `validate_tech_risk`, PM `validate_revenue_model`) + 1 gated (QA `synthesize_validation`, depends_on the other 3). Each agent gets a new `inputs.intent`-keyed mode dispatch, a new JSON schema enforced via `--json-schema`, a deterministic markdown renderer writing to `docs/products/<slug>/`, and an explicit `max_budget_usd` bump (defaults trip on every agent). QA reads the 3 upstream artifacts, emits a structured `pending_review` with `recommendation ∈ {go, go_with_caveats, pivot, kill}` plus risk register. Owner approves with `decision: go|pivot|kill — <rationale>` comment, seeding iter-27 (build) or iter-26b' (next slug).

**Tech Stack:** Python 3.11, Pydantic v2 (`extra="forbid"`), Click (CLI), FastAPI (API, unchanged), pytest + pytest-asyncio + testcontainers (tests), `claude -p` subprocess via `ClaudeCodeHeadlessClient`, `MockLLMClient` for unit/integration. Four new JSON schema constants enforced via `--json-schema`. No new dependencies.

**Source spec:** `docs/superpowers/specs/2026-05-22-iter-26b-single-candidate-validator-design.md` (commit `07c6c1c`).

**Reuses from iter-26a (no rework needed):**
- `SubmitTaskRequest.inputs: dict[str, Any] | None` (commit `2817888`).
- `DECOMPOSITION_SCHEMA.subtasks.items.properties.inputs` optional field (commit `68e8c31`).
- TL `build_outputs` propagation: `inputs=sub.get("inputs") or {}` at `agents/team_lead/agent.py:200`.
- Pattern: per-`inputs.intent` mode dispatch in agent `handle()` + `build_outputs()`. MR + QA already practice this; Architect + PM gain it in this iteration.
- Pattern: deterministic agent-side markdown render alongside LLM tool-use writes (authoritative path is agent-side; LLM tool-use is fallback).
- Pattern: monkeypatched `_REPO_ROOT` + `*_DIR` constants in integration tests to prevent repo pollution (commit `94d7d0e`).

---

## File Structure

**Modified:**
- `apps/cli/main.py` — new `validate-product` sub-command (~50 lines) + `_extract_candidate_section(file_text, slug)` helper (~25 lines).
- `agents/market_researcher/agent.py` — `VALIDATE_COMPETITORS_SCHEMA` constant + `_render_competitors_markdown()` helper + `validate_competitors` branch in `handle()` + `build_outputs()` + `max_budget_usd=5.50` per-mode override + path-prefix env for `docs/products/<slug>`.
- `agents/architect/agent.py` — gains intent dispatch (currently single-mode). Adds `VALIDATE_TECH_RISK_SCHEMA` constant + `_render_tech_risk_markdown()` helper + `validate_tech_risk` branch in `handle()` + `build_outputs()` + `max_budget_usd=4.50` override + path-prefix env.
- `agents/product_manager/agent.py` — gains intent dispatch (currently single-mode). Adds `VALIDATE_REVENUE_SCHEMA` constant + `_render_revenue_markdown()` helper + `validate_revenue_model` branch in `handle()` + `build_outputs()` + `max_budget_usd=3.50` override + path-prefix env.
- `agents/qa_engineer/agent.py` — `SYNTHESIZE_VALIDATION_SCHEMA` constant + `_render_validation_summary_markdown()` helper + `synthesize_validation` intent branch in `handle()` + `build_outputs()` + `max_budget_usd=2.50` override + path-prefix env + fatal_flaws cross-field invariant + upstream task_report aggregation.
- `prompts/team_lead.md` — `Intent: validate_product` workflow section.
- `prompts/market_researcher.md` — `Workflow: validate-competitors mode` section.
- `prompts/architect.md` — `Workflow: validate-tech-risk mode` section.
- `prompts/product_manager.md` — `Workflow: validate-revenue-model mode` section.
- `prompts/qa_engineer.md` — `Intent: synthesize_validation` section.
- `CLAUDE.md` — one paragraph in "Where to look" pointing at per-candidate `docs/products/<slug>/` dirs; one line in the agents/CLI section flagging `ai-team validate-product`.

**Created:**
- `scripts/demo_iter_26b.sh` — orchestrates demo: preflight → `make up` → migrations → API start → submit validate-product → 30-min poll → 60s drain → final report.
- `scripts/iter_26b_constraints.json` — default `--constraints-json` payload.
- `tests/unit/test_cli_validate_product.py`
- `tests/unit/test_team_lead_validate_decomposition.py`
- `tests/unit/test_market_researcher_validate_competitors.py`
- `tests/unit/test_architect_validate_tech_risk.py`
- `tests/unit/test_product_manager_validate_revenue.py`
- `tests/unit/test_qa_synthesize_validation.py`
- `tests/integration/test_iter_26b_e2e_validate.py`
- `tests/integration/test_validator_one_agent_real_llm.py` (gated by `--real-llm`)

**Files NOT touched** (out of scope; spec §3, §14, §15): `apps/api/main.py` (already accepts `inputs`); `DECOMPOSITION_SCHEMA` (already optional `inputs`); HoldQueue persistence; GitHubTargetRepo; `BaseAgent.handle()` refactor; dispatcher per-role parallelism; 2-pending_reviews anomaly; hash-chain alert job.

---

## Task 1: CLI `ai-team validate-product` subcommand

Add the entry-point that extracts the slug's section from a brainstorm file, parses constraints, and POSTs `/api/tasks` with `inputs.intent = "validate_product"`. No API changes — `SubmitTaskRequest.inputs` already accepts the payload (iter-26a commit `2817888`).

**Files:**
- Modify: `apps/cli/main.py` — add `validate_product` command + `_extract_candidate_section` helper.
- Create: `tests/unit/test_cli_validate_product.py`.

- [ ] **Step 1: Write failing test (section extractor)**

Create `tests/unit/test_cli_validate_product.py`:

```python
"""validate-product CLI: extracts the slug's section from a brainstorm
file, loads constraints JSON, posts inputs.intent='validate_product'."""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from apps.cli.main import _extract_candidate_section


SAMPLE_BRAINSTORM = """# Brainstorm: creator_tools — 5 Candidates

Generated: 2026-05-22 | Niche: creator_tools

## 1. AI Content Engine for Telegram Developer Channels

**Slug:** telegram-tech-publisher
**Monetization:** subscription
**Target Buyer:** Developer-influencers running Telegram channels.

**One Paragraph:** Telegram is the dominant technical content platform.

**Scores:** tam_signal=3, solo_fit=5, llm_opex_fit=5, defensibility=4, time_to_first_revenue=5
**Composite:** 22

## 2. Another Idea

**Slug:** ai-technical-repurposer
**Monetization:** subscription

**One Paragraph:** Different content.
"""


def test_extracts_slug_section_exact_match() -> None:
    section = _extract_candidate_section(SAMPLE_BRAINSTORM, "telegram-tech-publisher")
    assert section.startswith("## 1. AI Content Engine for Telegram")
    assert "**Slug:** telegram-tech-publisher" in section
    assert "Composite:** 22" in section
    # Stops before the next H2.
    assert "ai-technical-repurposer" not in section


def test_extracts_second_section_when_slug_matches_it() -> None:
    section = _extract_candidate_section(SAMPLE_BRAINSTORM, "ai-technical-repurposer")
    assert section.startswith("## 2. Another Idea")
    assert "**Slug:** ai-technical-repurposer" in section
    # Should not include the first idea.
    assert "telegram-tech-publisher" not in section


def test_raises_on_unknown_slug() -> None:
    with pytest.raises(ValueError, match="not found"):
        _extract_candidate_section(SAMPLE_BRAINSTORM, "no-such-slug")


def test_raises_on_empty_file() -> None:
    with pytest.raises(ValueError):
        _extract_candidate_section("", "any-slug")
```

- [ ] **Step 2: Run test, verify it fails**

```bash
uv run pytest tests/unit/test_cli_validate_product.py::test_extracts_slug_section_exact_match -v
```
Expected: `FAILED` — `ImportError: cannot import name '_extract_candidate_section'`.

- [ ] **Step 3: Implement `_extract_candidate_section`**

In `apps/cli/main.py`, after the existing helper functions and before the `@cli.command(name="brainstorm-products")` block, add:

```python
def _extract_candidate_section(file_text: str, slug: str) -> str:
    """Return the H2 section from a brainstorm markdown whose body contains
    `**Slug:** <slug>`. Stops at the next H2 or end of file. Raises
    ValueError if no matching section exists.
    """
    if not file_text:
        raise ValueError("brainstorm file is empty")
    lines = file_text.splitlines(keepends=True)
    h2_indices: list[int] = [i for i, line in enumerate(lines) if line.startswith("## ")]
    if not h2_indices:
        raise ValueError("no H2 sections found in brainstorm file")
    slug_marker = f"**Slug:** {slug}"
    for idx, start in enumerate(h2_indices):
        end = h2_indices[idx + 1] if idx + 1 < len(h2_indices) else len(lines)
        section_text = "".join(lines[start:end])
        if slug_marker in section_text:
            return section_text.rstrip() + "\n"
    raise ValueError(f"slug {slug!r} not found in brainstorm file")
```

- [ ] **Step 4: Run section-extractor tests, verify pass**

```bash
uv run pytest tests/unit/test_cli_validate_product.py -k extract -v
```
Expected: 4 passed.

- [ ] **Step 5: Write failing test (CLI command end-to-end)**

Append to `tests/unit/test_cli_validate_product.py`:

```python
from unittest.mock import patch, MagicMock
from uuid import uuid4

from click.testing import CliRunner

from apps.cli.main import cli


def _write_constraints(tmp_path: Path) -> Path:
    p = tmp_path / "constraints.json"
    p.write_text(json.dumps({"owner_profile": "solo_developer", "max_total_dev_time_weeks": 12}))
    return p


def _write_brainstorm(tmp_path: Path) -> Path:
    p = tmp_path / "brainstorm.md"
    p.write_text(SAMPLE_BRAINSTORM)
    return p


def test_validate_product_posts_with_expected_inputs(tmp_path: Path) -> None:
    brainstorm = _write_brainstorm(tmp_path)
    constraints = _write_constraints(tmp_path)

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"task_id": str(uuid4()), "correlation_id": str(uuid4())}

    with patch("apps.cli.main.httpx.post", return_value=fake_resp) as post_mock:
        result = CliRunner().invoke(
            cli,
            [
                "validate-product",
                "--slug", "telegram-tech-publisher",
                "--candidate-file", str(brainstorm),
                "--depth", "standard",
                "--constraints-json", str(constraints),
            ],
            env={"OWNER_TOKEN": "test-token"},
        )

    assert result.exit_code == 0, result.output
    post_mock.assert_called_once()
    posted_json = post_mock.call_args.kwargs["json"]
    assert posted_json["title"] == "Validate product: telegram-tech-publisher"
    assert "**Slug:** telegram-tech-publisher" in posted_json["description"]
    inputs = posted_json["inputs"]
    assert inputs["intent"] == "validate_product"
    assert inputs["slug"] == "telegram-tech-publisher"
    assert inputs["depth"] == "standard"
    assert inputs["constraints"]["owner_profile"] == "solo_developer"
    assert "candidate_brief" in inputs
    assert inputs["candidate_brief"].startswith("## 1. AI Content Engine for Telegram")


def test_validate_product_rejects_unknown_slug(tmp_path: Path) -> None:
    brainstorm = _write_brainstorm(tmp_path)
    constraints = _write_constraints(tmp_path)

    result = CliRunner().invoke(
        cli,
        [
            "validate-product",
            "--slug", "no-such-slug",
            "--candidate-file", str(brainstorm),
            "--constraints-json", str(constraints),
        ],
        env={"OWNER_TOKEN": "test-token"},
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower()
```

- [ ] **Step 6: Run CLI command tests, verify they fail**

```bash
uv run pytest tests/unit/test_cli_validate_product.py -v
```
Expected: 4 extractor tests pass; 2 command tests `FAILED` — `Error: No such command 'validate-product'`.

- [ ] **Step 7: Implement `validate-product` Click command**

In `apps/cli/main.py`, after the `brainstorm_products` command, add:

```python
@cli.command(name="validate-product")
@click.option("--slug", required=True, help="Candidate slug to validate (matches **Slug:** in --candidate-file).")
@click.option("--candidate-file", required=True, type=click.Path(exists=True, dir_okay=False),
              help="Brainstorm markdown containing the slug's section.")
@click.option("--depth", type=click.Choice(["quick", "standard", "deep"]), default="standard",
              help="Competitor-scan breadth (quick=5, standard=15, deep=30).")
@click.option("--constraints-json", type=click.Path(exists=True, dir_okay=False),
              default="scripts/iter_26b_constraints.json", show_default=True,
              help="Owner-profile + budget envelope JSON.")
@click.pass_context
def validate_product(
    ctx: click.Context,
    slug: str,
    candidate_file: str,
    depth: str,
    constraints_json: str,
) -> None:
    """Submit a single-candidate validation task.

    Reads the slug's H2 section from --candidate-file, parses
    --constraints-json, and POSTs /api/tasks with
    inputs.intent='validate_product'.
    """
    try:
        brainstorm_text = Path(candidate_file).read_text()
        candidate_brief = _extract_candidate_section(brainstorm_text, slug)
    except (OSError, ValueError) as exc:
        console.print(f"[red]Candidate brief: {exc}[/]")
        sys.exit(1)

    try:
        constraints = json.loads(Path(constraints_json).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        console.print(f"[red]Constraints JSON: {exc}[/]")
        sys.exit(1)

    payload = {
        "title": f"Validate product: {slug}",
        "description": candidate_brief,
        "priority": "p2",
        "inputs": {
            "intent": "validate_product",
            "slug": slug,
            "depth": depth,
            "candidate_brief": candidate_brief,
            "constraints": constraints,
        },
    }
    resp = httpx.post(
        f"{_api_base(ctx)}/api/tasks",
        json=payload,
        headers=_token_header(ctx),
        timeout=15.0,
    )
    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.status_code} {resp.text}[/]")
        sys.exit(1)
    data = resp.json()
    correlation_short = str(data["correlation_id"])[:8]
    console.print(
        Panel(
            f"[bold]Validation submitted.[/]\n"
            f"  task_id:        {data['task_id']}\n"
            f"  correlation_id: {data['correlation_id']}\n"
            f"  slug:           {slug}\n"
            f"  depth:          {depth}\n\n"
            f"[dim]Tail with:[/] ai-team watch --correlation {correlation_short}",
            title="validate-product",
            style="green",
        )
    )
```

Confirm imports at top of `apps/cli/main.py` include `json`, `sys`, `Path` (from pathlib), `httpx`, `click`. They almost certainly do — iter-26a's `brainstorm-products` uses the same set.

- [ ] **Step 8: Run all CLI tests, verify pass**

```bash
uv run pytest tests/unit/test_cli_validate_product.py -v
```
Expected: 6 passed.

- [ ] **Step 9: Commit**

```bash
git add apps/cli/main.py tests/unit/test_cli_validate_product.py
git commit -m "feat(iter-26b): ai-team validate-product CLI subcommand"
```

---

## Task 2: Default constraints JSON

Concrete constraints file `scripts/iter_26b_constraints.json` becomes the default `--constraints-json` payload and the input every validator agent reads.

**Files:**
- Create: `scripts/iter_26b_constraints.json`.

- [ ] **Step 1: Write the constraints file**

```bash
cat > scripts/iter_26b_constraints.json <<'JSON'
{
  "owner_profile": "solo_developer",
  "owner_languages": ["russian_native", "english_fluent"],
  "owner_distribution_assets": "CIS_telegram_dev_channels",
  "max_product_llm_opex_usd_per_day_per_user": 3,
  "max_time_to_first_revenue_months": 6,
  "max_total_dev_time_weeks": 12,
  "max_paid_acquisition_cost_per_user_usd": 0,
  "target_market": "developer_influencers_telegram_500_to_100k_subs",
  "monetization_model": "subscription"
}
JSON
```

- [ ] **Step 2: Verify it parses as valid JSON**

```bash
python -c "import json; json.load(open('scripts/iter_26b_constraints.json'))" && echo OK
```
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add scripts/iter_26b_constraints.json
git commit -m "chore(iter-26b): default constraints JSON for validate-product"
```

---

## Task 3: Team Lead `validate_product` intent (prompt-only)

TL receives `inputs.intent = "validate_product"` and decomposes into 4 subtasks via the existing `DECOMPOSITION_SCHEMA`. The schema already has optional `inputs` on subtask items (iter-26a `68e8c31`), so this is prompt-only — no code change required in `agents/team_lead/agent.py`.

**Files:**
- Modify: `prompts/team_lead.md` — append `Intent: validate_product` section.
- Create: `tests/unit/test_team_lead_validate_decomposition.py`.

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_team_lead_validate_decomposition.py`:

```python
"""TL `validate_product` intent: 4-subtask DAG with 3-parallel + 1-gated.
Validates inputs propagation, depends_on shape, recipients, and slug
propagation across subtasks."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.team_lead.agent import TeamLead, DECOMPOSITION_SCHEMA
from core.llm.base import LLMResponse
from core.messaging.schemas import (
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)
from tests.helpers.message_factories import make_incoming_assignment


_FAKE_DECOMP = {
    "task_overview": "Validate telegram-tech-publisher candidate",
    "subtasks": [
        {
            "id": "comp",
            "recipient": "market_researcher",
            "title": "Deep competitor scan for telegram-tech-publisher",
            "description": "Standard-depth competitor + signal scrape.",
            "depends_on": [],
            "inputs": {
                "intent": "validate_competitors",
                "slug": "telegram-tech-publisher",
                "depth": "standard",
                "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
                "target_market": "developer_influencers_telegram_500_to_100k_subs",
                "constraints": {"owner_profile": "solo_developer"},
            },
        },
        {
            "id": "tech",
            "recipient": "architect",
            "title": "Tech-risk register for telegram-tech-publisher",
            "description": "Telegram Bot API limits + voice calibration feasibility.",
            "depends_on": [],
            "inputs": {
                "intent": "validate_tech_risk",
                "slug": "telegram-tech-publisher",
                "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
                "constraints": {"owner_profile": "solo_developer"},
            },
        },
        {
            "id": "rev",
            "recipient": "product_manager",
            "title": "Revenue model stress-test for telegram-tech-publisher",
            "description": "Pricing tiers + CAC/LTV envelope + break-even.",
            "depends_on": [],
            "inputs": {
                "intent": "validate_revenue_model",
                "slug": "telegram-tech-publisher",
                "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
                "target_market": "developer_influencers_telegram_500_to_100k_subs",
                "constraints": {"owner_profile": "solo_developer"},
            },
        },
        {
            "id": "synth",
            "recipient": "qa_engineer",
            "title": "Validation synthesis + go/no-go for telegram-tech-publisher",
            "description": "Read 3 upstream artifacts; emit recommendation.",
            "depends_on": ["comp", "tech", "rev"],
            "inputs": {
                "intent": "synthesize_validation",
                "slug": "telegram-tech-publisher",
                "upstream_ids": ["comp", "tech", "rev"],
            },
        },
    ],
}


def test_validate_product_decomposition_passes_schema_validation() -> None:
    """The four-subtask DAG validates against DECOMPOSITION_SCHEMA."""
    import jsonschema
    jsonschema.validate(_FAKE_DECOMP, DECOMPOSITION_SCHEMA)


def test_validate_product_inputs_propagate_to_subtasks() -> None:
    """build_outputs propagates inputs into TaskAssignmentPayload.inputs
    for every subtask (iter-26a 68e8c31 plumbing)."""
    tl = TeamLead()
    incoming = make_incoming_assignment(
        title="Validate product: telegram-tech-publisher",
        description="**Slug:** telegram-tech-publisher\n...",
        inputs={
            "intent": "validate_product",
            "slug": "telegram-tech-publisher",
            "depth": "standard",
            "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
            "constraints": {"owner_profile": "solo_developer"},
        },
    )
    response = LLMResponse(content="", structured_output=_FAKE_DECOMP, metadata={})

    outputs = tl.build_outputs(response, incoming)
    assignments = [m for m in outputs if m.message_type == MessageType.TASK_ASSIGNMENT]
    assert len(assignments) == 4
    recipients = {a.recipient for a in assignments}
    assert recipients == {"market_researcher", "architect", "product_manager", "qa_engineer"}

    intents = {a.payload.inputs.get("intent") for a in assignments}
    assert intents == {
        "validate_competitors",
        "validate_tech_risk",
        "validate_revenue_model",
        "synthesize_validation",
    }


def test_synth_subtask_depends_on_other_three() -> None:
    tl = TeamLead()
    incoming = make_incoming_assignment(
        title="Validate product: telegram-tech-publisher",
        description="...",
        inputs={"intent": "validate_product", "slug": "telegram-tech-publisher"},
    )
    response = LLMResponse(content="", structured_output=_FAKE_DECOMP, metadata={})

    outputs = tl.build_outputs(response, incoming)
    assignments = [m for m in outputs if m.message_type == MessageType.TASK_ASSIGNMENT]
    synth = next(a for a in assignments if a.recipient == "qa_engineer")
    assert len(synth.payload.depends_on) == 3
    # depends_on contains task_ids (UUIDs), not slugs — verify the count
    # and that the other 3 assignments' task_ids match.
    other_task_ids = {
        str(a.payload.task_id)
        for a in assignments
        if a.recipient != "qa_engineer"
    }
    assert set(synth.payload.depends_on) == other_task_ids
```

The `make_incoming_assignment` helper exists in `tests/helpers/message_factories.py` from iter-26a (Task 5 work).

- [ ] **Step 2: Run test, verify it fails for the right reason**

```bash
uv run pytest tests/unit/test_team_lead_validate_decomposition.py -v
```
Expected: tests fail because the prompt doesn't teach TL to emit this decomposition shape — but `test_validate_product_decomposition_passes_schema_validation` and the propagation tests will pass once we run them (the schema and `build_outputs` already accept it). Verify which fail and why before proceeding.

Actually, run them — schema validation + build_outputs propagation are pure-Python tests with a fake response, so they should pass NOW. The prompt-only change comes next. Confirm: 3 passed.

```
PASSED  test_validate_product_decomposition_passes_schema_validation
PASSED  test_validate_product_inputs_propagate_to_subtasks
PASSED  test_synth_subtask_depends_on_other_three
```

If they don't pass, there's an existing-code bug to fix — `agents/team_lead/agent.py:200` should have `inputs=sub.get("inputs") or {}` from iter-26a.

- [ ] **Step 3: Update `prompts/team_lead.md`**

Append to `prompts/team_lead.md` (after the existing `Intent: brainstorm_products` section):

```markdown
## Intent: validate_product

When you receive a `task_assignment` with `inputs.intent == "validate_product"`, you are orchestrating diligence on **one** product candidate (`inputs.slug`). You must emit a decomposition with **exactly four subtasks** in this shape:

1. **`comp`** → `market_researcher`, `depends_on=[]`
   - `inputs`: `{intent: "validate_competitors", slug, depth, candidate_brief, constraints, target_market}`
2. **`tech`** → `architect`, `depends_on=[]`
   - `inputs`: `{intent: "validate_tech_risk", slug, candidate_brief, constraints}`
3. **`rev`** → `product_manager`, `depends_on=[]`
   - `inputs`: `{intent: "validate_revenue_model", slug, candidate_brief, target_market, constraints}`
4. **`synth`** → `qa_engineer`, `depends_on=["comp", "tech", "rev"]`
   - `inputs`: `{intent: "synthesize_validation", slug, upstream_ids: ["comp", "tech", "rev"]}`

### How to fill the fields

- `slug`, `depth` (`quick|standard|deep`), `candidate_brief`, and `constraints` come verbatim from your own `inputs`.
- `target_market` you extract from the `Target Buyer:` line in `candidate_brief` (single string, e.g. `"developer_influencers_telegram_500_to_100k_subs"`). If the brief has no clear target buyer, use `constraints.target_market` if present, otherwise the literal string `"unknown"`.
- `upstream_ids` is always `["comp", "tech", "rev"]` — these are the **subtask IDs** of the parallel siblings, not external references.

### Rules

- Do not invent additional subtasks. The chain is exactly four.
- Do not change subtask `id`s — `comp`/`tech`/`rev`/`synth` are referenced by `depends_on` and by downstream prompt logic.
- `depends_on=["comp", "tech", "rev"]` on the `synth` subtask is what gates QA on the other three. Without it, QA fires before the upstreams complete.
- Recipients are fixed per subtask. Do not swap MR with Architect, etc.
- The three parallel subtasks (`comp`, `tech`, `rev`) target three different agent roles, so the dispatcher parallelism limitation (per-role serialization at `core/dispatcher.py:96`) does not apply.

### Example task_overview

`"Validate <slug> candidate via 4-agent diligence: MR competitor scan, Architect tech-risk, PM revenue model, QA go/no-go synthesis."`
```

- [ ] **Step 4: Re-run TL decomposition tests**

```bash
uv run pytest tests/unit/test_team_lead_validate_decomposition.py -v
```
Expected: 3 passed (prompt change doesn't affect these — they test the structural propagation, which works with any decomposition shape).

- [ ] **Step 5: Quick sanity — full TL suite still green**

```bash
uv run pytest tests/unit/test_team_lead*.py -v
```
Expected: all existing TL tests pass (no behavior change for non-`validate_product` intents).

- [ ] **Step 6: Commit**

```bash
git add prompts/team_lead.md tests/unit/test_team_lead_validate_decomposition.py
git commit -m "feat(iter-26b): TL validate_product intent — 4-subtask DAG prompt"
```

---

## Task 4: Market Researcher `validate_competitors` mode

MR gets a third mode (alongside `market_scan` and `brainstorm_niche`). New schema, new render helper, new dispatch branch, new max_budget override, new path scope, new prompt section.

**Files:**
- Modify: `agents/market_researcher/agent.py`.
- Modify: `prompts/market_researcher.md`.
- Create: `tests/unit/test_market_researcher_validate_competitors.py`.

- [ ] **Step 1: Write failing test (schema)**

Create `tests/unit/test_market_researcher_validate_competitors.py`:

```python
"""MR validate-competitors mode: schema + render + dispatch + max_budget."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, AsyncMock

import jsonschema
import pytest

from agents.market_researcher.agent import (
    MarketResearcher,
    VALIDATE_COMPETITORS_SCHEMA,
    _render_competitors_markdown,
)
from core.llm.base import LLMResponse
from core.messaging.schemas import MessageType
from tests.helpers.message_factories import make_incoming_assignment


_GOOD_OUTPUT = {
    "intent_completed": "validate_competitors",
    "competitors_found": 15,
    "pain_signals_found": 7,
    "distribution_feasibility": {
        "channel_estimate": "~120 CIS dev Telegram channels with 5k+ subs",
        "audience_reach_estimate": "~800k aggregate addressable subs",
        "conversion_to_paid_estimate": "0.5-1.5% based on observed Telegram bot subscriptions",
        "notes": "Owner's existing network covers ~15 channels directly.",
    },
    "verdict": "underserved",
    "summary": "Niche has 3-4 partial competitors but none specifically targeting Telegram dev channels.",
    "artifacts": ["docs/products/telegram-tech-publisher/competitors.md"],
}


def test_schema_accepts_valid_output() -> None:
    jsonschema.validate(_GOOD_OUTPUT, VALIDATE_COMPETITORS_SCHEMA)


def test_schema_rejects_wrong_intent_completed() -> None:
    bad = {**_GOOD_OUTPUT, "intent_completed": "market_scan"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_COMPETITORS_SCHEMA)


def test_schema_rejects_unknown_verdict() -> None:
    bad = {**_GOOD_OUTPUT, "verdict": "amazing"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_COMPETITORS_SCHEMA)


def test_schema_requires_distribution_feasibility_subfields() -> None:
    bad = {**_GOOD_OUTPUT, "distribution_feasibility": {"channel_estimate": "x"}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_COMPETITORS_SCHEMA)


def test_schema_rejects_extra_top_level_keys() -> None:
    bad = {**_GOOD_OUTPUT, "extra_field": "not allowed"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_COMPETITORS_SCHEMA)


def test_render_competitors_markdown_includes_all_sections() -> None:
    md = _render_competitors_markdown(_GOOD_OUTPUT, slug="telegram-tech-publisher")
    assert "# Competitor scan: telegram-tech-publisher" in md
    assert "## Distribution feasibility" in md
    assert "CIS dev Telegram channels" in md
    assert "Verdict: **underserved**" in md
    assert "15" in md  # competitors_found
    assert "7" in md   # pain_signals_found
```

- [ ] **Step 2: Run schema/render tests, verify they fail**

```bash
uv run pytest tests/unit/test_market_researcher_validate_competitors.py -v
```
Expected: `ImportError: cannot import name 'VALIDATE_COMPETITORS_SCHEMA' from 'agents.market_researcher.agent'`.

- [ ] **Step 3: Add `VALIDATE_COMPETITORS_SCHEMA` constant**

In `agents/market_researcher/agent.py`, after the existing `BRAINSTORM_NICHE_SCHEMA` constant (around line 82), add:

```python
VALIDATE_COMPETITORS_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed", "competitors_found", "pain_signals_found",
        "distribution_feasibility", "verdict", "summary", "artifacts",
    ],
    "properties": {
        "intent_completed": {"const": "validate_competitors"},
        "competitors_found": {"type": "integer", "minimum": 0},
        "pain_signals_found": {"type": "integer", "minimum": 0},
        "distribution_feasibility": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "channel_estimate",
                "audience_reach_estimate",
                "conversion_to_paid_estimate",
                "notes",
            ],
            "properties": {
                "channel_estimate": {"type": "string", "maxLength": 500},
                "audience_reach_estimate": {"type": "string", "maxLength": 500},
                "conversion_to_paid_estimate": {"type": "string", "maxLength": 500},
                "notes": {"type": "string", "maxLength": 1000},
            },
        },
        "verdict": {"enum": ["underserved", "saturated", "marginal"]},
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
    },
}
```

- [ ] **Step 4: Add `_render_competitors_markdown` helper**

After `_render_brainstorm_markdown` (around line 174-225), add:

```python
def _render_competitors_markdown(response: dict[str, Any], slug: str) -> str:
    """Render VALIDATE_COMPETITORS_SCHEMA output as competitors.md."""
    lines: list[str] = []
    lines.append(f"# Competitor scan: {slug}\n")
    lines.append(f"- Competitors found: **{response['competitors_found']}**")
    lines.append(f"- Pain signals found: **{response['pain_signals_found']}**")
    lines.append(f"- Verdict: **{response['verdict']}**\n")
    lines.append("## Summary\n")
    lines.append(response["summary"])
    lines.append("")
    lines.append("## Distribution feasibility\n")
    df = response["distribution_feasibility"]
    lines.append(f"- **Channel estimate**: {df['channel_estimate']}")
    lines.append(f"- **Audience reach estimate**: {df['audience_reach_estimate']}")
    lines.append(f"- **Conversion-to-paid estimate**: {df['conversion_to_paid_estimate']}")
    lines.append("")
    lines.append("### Notes\n")
    lines.append(df["notes"])
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 5: Re-run schema + render tests, verify pass**

```bash
uv run pytest tests/unit/test_market_researcher_validate_competitors.py -v -k "schema or render"
```
Expected: 6 passed.

- [ ] **Step 6: Write failing dispatch + max_budget test**

Append to `tests/unit/test_market_researcher_validate_competitors.py`:

```python
@pytest.mark.asyncio
async def test_handle_dispatches_validate_schema_on_intent(monkeypatch, tmp_path) -> None:
    """When inputs.intent='validate_competitors', handle() uses
    VALIDATE_COMPETITORS_SCHEMA and the agent writes
    docs/products/<slug>/competitors.md."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.market_researcher.agent._VALIDATE_DIR", tmp_path / "docs" / "products")

    captured_kwargs: dict = {}

    async def _fake_invoke(self, **kwargs):
        captured_kwargs.update(kwargs)
        return LLMResponse(content="", structured_output=_GOOD_OUTPUT, metadata={"cost_cents": 100})

    with patch("agents.market_researcher.agent.MarketResearcher._invoke_llm", _fake_invoke):
        mr = MarketResearcher()
        incoming = make_incoming_assignment(
            title="Validate competitors: telegram-tech-publisher",
            description="**Slug:** telegram-tech-publisher\n...",
            inputs={
                "intent": "validate_competitors",
                "slug": "telegram-tech-publisher",
                "depth": "standard",
                "candidate_brief": "...",
                "target_market": "...",
                "constraints": {"owner_profile": "solo_developer"},
            },
        )
        outputs = await mr.handle(incoming)

    assert captured_kwargs["json_schema"] is VALIDATE_COMPETITORS_SCHEMA
    assert captured_kwargs["max_budget_usd"] == 5.50
    artifact_path = tmp_path / "docs" / "products" / "telegram-tech-publisher" / "competitors.md"
    assert artifact_path.exists()
    body = artifact_path.read_text()
    assert "Verdict: **underserved**" in body
    # The agent emits a single task_report with status=DONE.
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    assert reports[0].payload.status == "DONE"


@pytest.mark.asyncio
async def test_handle_blocks_on_invalid_slug(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.market_researcher.agent._VALIDATE_DIR", tmp_path / "docs" / "products")

    mr = MarketResearcher()
    incoming = make_incoming_assignment(
        title="Validate competitors: bad slug",
        description="...",
        inputs={
            "intent": "validate_competitors",
            "slug": "../escaped/slug",   # path traversal attempt
            "depth": "standard",
            "candidate_brief": "...",
            "target_market": "...",
            "constraints": {},
        },
    )
    outputs = await mr.handle(incoming)
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    assert reports[0].payload.status == "BLOCKED"
    assert "input_validation" in (reports[0].payload.summary or "").lower() or \
           "slug" in (reports[0].payload.summary or "").lower()


@pytest.mark.asyncio
async def test_handle_non_validate_intent_falls_through_to_existing_modes(
    monkeypatch, tmp_path,
) -> None:
    """Pre-existing brainstorm_niche / market_scan modes are unaffected."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)

    captured_schema = [None]
    async def _fake_invoke(self, **kwargs):
        captured_schema[0] = kwargs.get("json_schema")
        return LLMResponse(content="", structured_output={}, metadata={"cost_cents": 0})

    with patch("agents.market_researcher.agent.MarketResearcher._invoke_llm", _fake_invoke):
        mr = MarketResearcher()
        incoming = make_incoming_assignment(
            title="Brainstorm",
            description="...",
            inputs={"mode": "brainstorm_niche", "niche": "dev_tools"},
        )
        await mr.handle(incoming)

    from agents.market_researcher.agent import BRAINSTORM_NICHE_SCHEMA
    assert captured_schema[0] is BRAINSTORM_NICHE_SCHEMA
```

- [ ] **Step 7: Run dispatch tests, verify they fail**

```bash
uv run pytest tests/unit/test_market_researcher_validate_competitors.py -v -k "dispatches or blocks or falls_through"
```
Expected: `AttributeError: module 'agents.market_researcher.agent' has no attribute '_VALIDATE_DIR'`. Or, if that module attr exists from earlier, dispatch-routing failures.

- [ ] **Step 8: Wire dispatch + max_budget + path scope in MR**

At the top of `agents/market_researcher/agent.py` (near other `_*_DIR` module constants), add:

```python
_VALIDATE_DIR = _REPO_ROOT / "docs" / "products"
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,50}$")
```

Add `import re` if not present.

In `handle()` (currently around line 401-427), replace the body:

```python
async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
    inputs = msg.payload.inputs or {}
    intent = inputs.get("intent")
    mode = inputs.get("mode")

    if intent == "validate_competitors":
        slug = inputs.get("slug", "")
        if not _SLUG_RE.match(slug):
            return [
                self._build_report(
                    msg,
                    status="BLOCKED",
                    summary=f"validate_competitors: input_validation — invalid slug {slug!r}",
                )
            ]
        schema = VALIDATE_COMPETITORS_SCHEMA
        max_budget = 5.50
        session_id = str(msg.payload.task_id)
        path_prefixes = f"docs/sandbox/ideas,docs/market,docs/products/_candidates,docs/products/{slug}"
    elif mode == "brainstorm_niche":
        schema = BRAINSTORM_NICHE_SCHEMA
        max_budget = None
        session_id = str(msg.payload.task_id)
        path_prefixes = "docs/sandbox/ideas,docs/market,docs/products/_candidates"
    else:
        schema = MARKET_SCAN_SCHEMA
        max_budget = None
        session_id = None
        path_prefixes = "docs/sandbox/ideas,docs/market"

    mcp_env = {"AI_TEAM_PATH_PREFIXES": path_prefixes}

    invoke_kwargs: dict[str, Any] = dict(
        model=self.model_tier,
        system_prompt=self._system_prompt(),
        user_message=self._render_user_message(msg),
        allowed_tools=self.allowed_tools,
        json_schema=schema,
        session_id=session_id,
        mcp_env=mcp_env,
        timeout_s=600,
    )
    if max_budget is not None:
        invoke_kwargs["max_budget_usd"] = max_budget

    response = await self._invoke_llm(**invoke_kwargs)
    return self._stamp_metrics(self.build_outputs(response, msg), response)
```

Then update `build_outputs()` (around line 292-400) to handle the new intent. Insert at the top of the method body, before the existing `mode == "brainstorm_niche"` check:

```python
def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
    inputs = incoming.payload.inputs or {}
    intent = inputs.get("intent")
    mode = inputs.get("mode")

    if intent == "validate_competitors":
        return self._build_validate_competitors_outputs(response, incoming)

    # ... existing brainstorm_niche / market_scan branches unchanged ...
```

Add the new method below `build_outputs()`:

```python
def _build_validate_competitors_outputs(
    self, response: LLMResponse, incoming: AgentMessage,
) -> list[AgentMessage]:
    inputs = incoming.payload.inputs or {}
    slug = inputs["slug"]  # already validated in handle()
    scan = response.structured_output or {}

    if not scan or scan.get("intent_completed") != "validate_competitors":
        return [
            self._build_report(
                incoming,
                status="BLOCKED",
                summary="validate_competitors: missing or malformed structured_output",
            )
        ]

    out_dir = _VALIDATE_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "competitors.md"
    artifact_path.write_text(_render_competitors_markdown(scan, slug=slug))

    summary = scan.get("summary") or "validate_competitors completed"

    return [
        self._build_report(
            incoming,
            status="DONE",
            summary=summary,
            structured=scan,
            artifacts=[str(artifact_path.relative_to(_REPO_ROOT))],
        )
    ]
```

Confirm `_build_report` exists on `MarketResearcher` (or its base) — iter-26a's brainstorm path uses it. If the existing brainstorm branch uses inline `TaskReportPayload(...)` instead, mirror that style here.

- [ ] **Step 9: Run full MR test suite, verify pass**

```bash
uv run pytest tests/unit/test_market_researcher*.py -v
```
Expected: all previous MR tests still pass; new validate tests all pass.

- [ ] **Step 10: Update `prompts/market_researcher.md`**

Append:

```markdown
## Workflow: validate-competitors mode

When `inputs.intent == "validate_competitors"`, you are stress-testing **one** product candidate (`inputs.slug`) against its competitive landscape. The candidate brief (from iter-26a brainstorm) is in `inputs.candidate_brief`. Constraints in `inputs.constraints`. Target market in `inputs.target_market`. Scan depth in `inputs.depth`:

- `quick` → 5 competitors + 3 pain signals
- `standard` → 15 competitors + 7 pain signals
- `deep` → 30 competitors + 12 pain signals

### Output structure (matches VALIDATE_COMPETITORS_SCHEMA)

You return one JSON object with these fields:

- `intent_completed`: literal `"validate_competitors"`.
- `competitors_found`: integer count of competitors you actually found and recorded.
- `pain_signals_found`: integer count of distinct buyer-pain quotes.
- `distribution_feasibility`: object with `channel_estimate`, `audience_reach_estimate`, `conversion_to_paid_estimate`, `notes`. For `telegram-tech-publisher` this is the CIS Telegram dev-channel reach.
- `verdict`: one of `"underserved" | "saturated" | "marginal"`.
- `summary`: one-paragraph defense of the verdict, ≤ 2000 chars.
- `artifacts`: list of file paths you wrote.

### Process

1. Use `WebFetch` (you have it in your allowed tools) to load competitor websites, pricing pages, and Reddit / Indie Hackers / forum threads. Cite real URLs in your reasoning.
2. For each competitor: name, URL, positioning sentence, current pricing (specific tier — not "starts at"), audience-size estimate (Twitter followers, GitHub stars, podcast subs), last-shipped-date signal (changelog, blog post, social), gap (what they don't do that this candidate would).
3. For pain signals: verbatim quotes from buyers expressing the pain this product solves OR criticizing existing alternatives. Include source URL + approximate date.
4. For distribution feasibility: for `telegram-tech-publisher` specifically, count CIS dev Telegram channels (5k+ subs), estimate aggregate addressable subs, and a realistic conversion-to-paid rate based on observed Telegram bot subscription patterns.
5. Verdict — `"underserved"` if ≤ 2 competitors directly address the same buyer with the same offering; `"saturated"` if ≥ 5 do; `"marginal"` if 3-4 partial matches exist.

You may use `write_file_in_scope` to draft the competitors.md content during reasoning — the agent's deterministic renderer is authoritative, so your tool-use writes are optional. Do not write outside `docs/products/<slug>/`.
```

- [ ] **Step 11: Quick smoke that the prompt file parses + the schema integration works**

```bash
uv run pytest tests/unit/test_market_researcher_validate_competitors.py -v
```
Expected: 9 passed.

```bash
uv run python -c "from agents.market_researcher.agent import MarketResearcher; mr = MarketResearcher(); print(mr._system_prompt()[:200])"
```
Expected: first 200 chars of the system prompt print without exception.

- [ ] **Step 12: Commit**

```bash
git add agents/market_researcher/agent.py prompts/market_researcher.md tests/unit/test_market_researcher_validate_competitors.py
git commit -m "feat(iter-26b): MR validate_competitors mode + max_budget bump"
```

---

## Task 5: Architect `validate_tech_risk` mode

Architect currently has single-mode dispatch (ADR_SCHEMA at `agents/architect/agent.py:42`). It gains intent dispatch in this task. Same pattern as MR.

**Files:**
- Modify: `agents/architect/agent.py`.
- Modify: `prompts/architect.md`.
- Create: `tests/unit/test_architect_validate_tech_risk.py`.

- [ ] **Step 1: Write failing tests (schema + render)**

Create `tests/unit/test_architect_validate_tech_risk.py`:

```python
"""Architect validate-tech-risk mode: schema + render + dispatch + max_budget."""

from __future__ import annotations

from unittest.mock import patch

import jsonschema
import pytest

from agents.architect.agent import (
    Architect,
    VALIDATE_TECH_RISK_SCHEMA,
    _render_tech_risk_markdown,
)
from core.llm.base import LLMResponse
from core.messaging.schemas import MessageType
from tests.helpers.message_factories import make_incoming_assignment


_GOOD_OUTPUT = {
    "intent_completed": "validate_tech_risk",
    "components": [
        {
            "name": "Telegram Bot API ingestion",
            "complexity": 3,
            "dependency": "Telegram Bot API (3rd-party, free)",
            "scaling_limit": "30 msg/sec to different users, 1/sec per chat",
            "gotchas": ["per-chat rate limits", "message length 4096 chars"],
        },
        {
            "name": "Source curator (GitHub + RSS)",
            "complexity": 2,
            "dependency": "GitHub REST API + RSS libs",
            "scaling_limit": "GitHub 5000 req/hr authenticated",
            "gotchas": ["RSS feed flake"],
        },
        {
            "name": "LLM voice calibration",
            "complexity": 4,
            "dependency": "Claude API via owner subscription",
            "scaling_limit": "subscription quota",
            "gotchas": ["voice drift between sessions", "prompt caching invalidation"],
        },
    ],
    "risks_found": 4,
    "top_risk": "Voice calibration drift undermines the 'authentic-creator-voice' moat over time.",
    "llm_opex_at_scale": {
        "per_user_per_day_at_100": 0.50,
        "per_user_per_day_at_1000": 0.40,
        "per_user_per_day_at_10000": 0.30,
    },
    "build_window_weeks": "6-8 weeks",
    "verdict": "feasible_with_caveats",
    "summary": "Telegram Bot API + Python + Claude is feasible; voice calibration is the long-tail risk.",
    "artifacts": ["docs/products/telegram-tech-publisher/tech_risk.md"],
}


def test_schema_accepts_valid_output() -> None:
    jsonschema.validate(_GOOD_OUTPUT, VALIDATE_TECH_RISK_SCHEMA)


def test_schema_rejects_components_below_minimum() -> None:
    bad = {**_GOOD_OUTPUT, "components": _GOOD_OUTPUT["components"][:2]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_TECH_RISK_SCHEMA)


def test_schema_rejects_unknown_build_window() -> None:
    bad = {**_GOOD_OUTPUT, "build_window_weeks": "5-7 weeks"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_TECH_RISK_SCHEMA)


def test_schema_rejects_complexity_out_of_range() -> None:
    bad_components = list(_GOOD_OUTPUT["components"])
    bad_components[0] = {**bad_components[0], "complexity": 6}
    bad = {**_GOOD_OUTPUT, "components": bad_components}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_TECH_RISK_SCHEMA)


def test_render_includes_component_table_and_opex() -> None:
    md = _render_tech_risk_markdown(_GOOD_OUTPUT, slug="telegram-tech-publisher")
    assert "# Tech-risk register: telegram-tech-publisher" in md
    assert "Telegram Bot API ingestion" in md
    assert "## LLM opex at scale" in md
    assert "0.5" in md or "0.50" in md
    assert "feasible_with_caveats" in md
    assert "6-8 weeks" in md
```

- [ ] **Step 2: Run tests, verify they fail**

```bash
uv run pytest tests/unit/test_architect_validate_tech_risk.py -v
```
Expected: `ImportError: cannot import name 'VALIDATE_TECH_RISK_SCHEMA'`.

- [ ] **Step 3: Add `VALIDATE_TECH_RISK_SCHEMA` + render helper**

In `agents/architect/agent.py`, after `ADR_SCHEMA` (around line 42-97), add:

```python
VALIDATE_TECH_RISK_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed", "components", "risks_found", "top_risk",
        "llm_opex_at_scale", "build_window_weeks", "verdict",
        "summary", "artifacts",
    ],
    "properties": {
        "intent_completed": {"const": "validate_tech_risk"},
        "components": {
            "type": "array",
            "minItems": 3,
            "maxItems": 12,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "complexity", "dependency", "scaling_limit", "gotchas"],
                "properties": {
                    "name": {"type": "string", "maxLength": 200},
                    "complexity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "dependency": {"type": "string", "maxLength": 300},
                    "scaling_limit": {"type": "string", "maxLength": 300},
                    "gotchas": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 300},
                    },
                },
            },
        },
        "risks_found": {"type": "integer", "minimum": 0},
        "top_risk": {"type": "string", "maxLength": 500},
        "llm_opex_at_scale": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "per_user_per_day_at_100",
                "per_user_per_day_at_1000",
                "per_user_per_day_at_10000",
            ],
            "properties": {
                "per_user_per_day_at_100": {"type": "number", "minimum": 0},
                "per_user_per_day_at_1000": {"type": "number", "minimum": 0},
                "per_user_per_day_at_10000": {"type": "number", "minimum": 0},
            },
        },
        "build_window_weeks": {
            "enum": ["4-6 weeks", "6-8 weeks", "8-12 weeks", "12+ weeks", "unknown"],
        },
        "verdict": {"enum": ["feasible", "feasible_with_caveats", "blocked"]},
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
    },
}


def _render_tech_risk_markdown(response: dict[str, Any], slug: str) -> str:
    """Render VALIDATE_TECH_RISK_SCHEMA output as tech_risk.md."""
    lines: list[str] = []
    lines.append(f"# Tech-risk register: {slug}\n")
    lines.append(f"- Verdict: **{response['verdict']}**")
    lines.append(f"- Build window: **{response['build_window_weeks']}**")
    lines.append(f"- Risks found: **{response['risks_found']}**\n")
    lines.append("## Summary\n")
    lines.append(response["summary"])
    lines.append("")
    lines.append("## Top risk\n")
    lines.append(response["top_risk"])
    lines.append("")
    lines.append("## Components\n")
    lines.append("| Name | Complexity (1-5) | Dependency | Scaling limit | Gotchas |")
    lines.append("|---|---|---|---|---|")
    for comp in response["components"]:
        gotchas = "; ".join(comp.get("gotchas", []) or [])
        lines.append(
            f"| {comp['name']} | {comp['complexity']} | {comp['dependency']} | "
            f"{comp['scaling_limit']} | {gotchas} |"
        )
    lines.append("")
    lines.append("## LLM opex at scale\n")
    opex = response["llm_opex_at_scale"]
    lines.append(f"- 100 users:    ${opex['per_user_per_day_at_100']:.2f} / user / day")
    lines.append(f"- 1000 users:   ${opex['per_user_per_day_at_1000']:.2f} / user / day")
    lines.append(f"- 10000 users:  ${opex['per_user_per_day_at_10000']:.2f} / user / day")
    lines.append("")
    return "\n".join(lines)
```

Ensure `from typing import Any` is imported at the top.

- [ ] **Step 4: Run schema + render tests, verify pass**

```bash
uv run pytest tests/unit/test_architect_validate_tech_risk.py -v -k "schema or render"
```
Expected: 5 passed.

- [ ] **Step 5: Add dispatch + max_budget tests**

Append to `tests/unit/test_architect_validate_tech_risk.py`:

```python
@pytest.mark.asyncio
async def test_handle_dispatches_validate_schema_on_intent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agents.architect.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.architect.agent._VALIDATE_DIR", tmp_path / "docs" / "products")

    captured: dict = {}
    async def _fake_invoke(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(content="", structured_output=_GOOD_OUTPUT, metadata={"cost_cents": 200})

    with patch("agents.architect.agent.Architect._invoke_llm", _fake_invoke):
        a = Architect()
        incoming = make_incoming_assignment(
            title="Validate tech-risk: telegram-tech-publisher",
            description="...",
            inputs={
                "intent": "validate_tech_risk",
                "slug": "telegram-tech-publisher",
                "candidate_brief": "...",
                "constraints": {},
            },
        )
        outputs = await a.handle(incoming)

    assert captured["json_schema"] is VALIDATE_TECH_RISK_SCHEMA
    assert captured["max_budget_usd"] == 4.50
    assert (tmp_path / "docs" / "products" / "telegram-tech-publisher" / "tech_risk.md").exists()
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    assert reports[0].payload.status == "DONE"


@pytest.mark.asyncio
async def test_handle_blocks_on_invalid_slug(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agents.architect.agent._REPO_ROOT", tmp_path)
    a = Architect()
    incoming = make_incoming_assignment(
        title="Validate", description="...",
        inputs={"intent": "validate_tech_risk", "slug": "../escape", "candidate_brief": "...", "constraints": {}},
    )
    outputs = await a.handle(incoming)
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert reports[0].payload.status == "BLOCKED"


@pytest.mark.asyncio
async def test_handle_no_intent_falls_through_to_adr(monkeypatch, tmp_path) -> None:
    """Pre-existing ADR-emitting flow still works when no intent is set."""
    captured: dict = {}
    async def _fake_invoke(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(content="", structured_output={"title": "x", "context": "x", "decision": "x", "consequences": "x"}, metadata={"cost_cents": 0})

    with patch("agents.architect.agent.Architect._invoke_llm", _fake_invoke):
        a = Architect()
        incoming = make_incoming_assignment(title="Design",
                                            description="...",
                                            inputs=None)
        await a.handle(incoming)

    from agents.architect.agent import ADR_SCHEMA
    assert captured["json_schema"] is ADR_SCHEMA
```

- [ ] **Step 6: Run dispatch tests, verify they fail**

```bash
uv run pytest tests/unit/test_architect_validate_tech_risk.py -v -k "handle"
```
Expected: failures (Architect currently has no intent dispatch; the new tests cannot find `_VALIDATE_DIR`).

- [ ] **Step 7: Add intent dispatch to Architect**

In `agents/architect/agent.py`, near the top, add:

```python
import re

_VALIDATE_DIR = _REPO_ROOT / "docs" / "products"
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,50}$")
```

Replace the existing `handle()` (around line 225-239) with intent-aware dispatch:

```python
async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
    inputs = msg.payload.inputs or {}
    intent = inputs.get("intent")

    if intent == "validate_tech_risk":
        slug = inputs.get("slug", "")
        if not _SLUG_RE.match(slug):
            return [
                self._build_report(
                    msg,
                    status="BLOCKED",
                    summary=f"validate_tech_risk: input_validation — invalid slug {slug!r}",
                )
            ]
        schema = VALIDATE_TECH_RISK_SCHEMA
        max_budget = 4.50
        path_prefixes = f"docs/adr,docs/architecture,docs/products/{slug}"
    else:
        schema = ADR_SCHEMA
        max_budget = None
        path_prefixes = "docs/adr,docs/architecture"

    mcp_env = {"AI_TEAM_PATH_PREFIXES": path_prefixes}

    invoke_kwargs: dict[str, Any] = dict(
        model=self.model_tier,
        system_prompt=self._system_prompt(),
        user_message=self._render_user_message(msg),
        allowed_tools=self.allowed_tools,
        json_schema=schema,
        mcp_env=mcp_env,
        timeout_s=600,
    )
    if max_budget is not None:
        invoke_kwargs["max_budget_usd"] = max_budget

    response = await self._invoke_llm(**invoke_kwargs)
    return self._stamp_metrics(self.build_outputs(response, msg), response)
```

Update `build_outputs()` (around line 177-223). Insert at top:

```python
def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
    inputs = incoming.payload.inputs or {}
    intent = inputs.get("intent")

    if intent == "validate_tech_risk":
        return self._build_validate_tech_risk_outputs(response, incoming)

    # ... existing ADR-emitting branch unchanged ...
```

Add the new method:

```python
def _build_validate_tech_risk_outputs(
    self, response: LLMResponse, incoming: AgentMessage,
) -> list[AgentMessage]:
    inputs = incoming.payload.inputs or {}
    slug = inputs["slug"]
    out = response.structured_output or {}
    if not out or out.get("intent_completed") != "validate_tech_risk":
        return [
            self._build_report(
                incoming,
                status="BLOCKED",
                summary="validate_tech_risk: missing or malformed structured_output",
            )
        ]

    out_dir = _VALIDATE_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "tech_risk.md"
    artifact_path.write_text(_render_tech_risk_markdown(out, slug=slug))

    return [
        self._build_report(
            incoming,
            status="DONE",
            summary=out.get("summary") or "validate_tech_risk completed",
            structured=out,
            artifacts=[str(artifact_path.relative_to(_REPO_ROOT))],
        )
    ]
```

Confirm `_build_report` exists (or mirror the existing ADR branch's report-construction style).

- [ ] **Step 8: Run full Architect test suite, verify pass**

```bash
uv run pytest tests/unit/test_architect*.py -v
```
Expected: all pre-existing Architect tests still pass; 8 new validate-tech-risk tests pass.

- [ ] **Step 9: Update `prompts/architect.md`**

Append:

```markdown
## Workflow: validate-tech-risk mode

When `inputs.intent == "validate_tech_risk"`, you are stress-testing the technical feasibility of one product candidate (`inputs.slug`). The candidate brief is in `inputs.candidate_brief`. Constraints in `inputs.constraints`.

### Output structure (matches VALIDATE_TECH_RISK_SCHEMA)

- `intent_completed`: literal `"validate_tech_risk"`.
- `components`: 3-12 items. Each `{name, complexity (1-5), dependency, scaling_limit, gotchas[]}`.
- `risks_found`: integer count.
- `top_risk`: single-sentence description of the highest-impact risk.
- `llm_opex_at_scale`: `{per_user_per_day_at_100, _at_1000, _at_10000}` in USD.
- `build_window_weeks`: one of `"4-6 weeks" | "6-8 weeks" | "8-12 weeks" | "12+ weeks" | "unknown"`.
- `verdict`: one of `"feasible" | "feasible_with_caveats" | "blocked"`.
- `summary`: ≤ 2000 chars, one-paragraph defense.
- `artifacts`: paths you wrote.

### Process

1. Read the candidate brief end-to-end. Identify the architectural components needed.
2. For each component (3-12 of them): name it, rate complexity 1-5, name the 3rd-party dependency (be specific — "Telegram Bot API" not "messaging"), the scaling limit (rate limits, quota), and 1-3 gotchas you'd hit shipping it.
3. For `telegram-tech-publisher` specifically, address:
   - Telegram Bot API rate limits (30 msg/sec to different users, 1/sec per chat). Validate against expected post volume.
   - Message formatting (Markdown/HTML, code blocks, file attachments).
   - Payment options (Telegram Stars vs Stripe redirect vs invoice link).
   - Webhook vs long-polling tradeoff.
   - Voice-tone calibration approach (few-shot vs embeddings vs fine-tune).
4. LLM opex — model per-user-per-day cost at 100, 1000, 10000 users. Identify which user-bucket breaks the `inputs.constraints.max_product_llm_opex_usd_per_day_per_user` ceiling.
5. Build window — pick from the 5-value enum based on per-component time estimates.
6. Top risk — the single highest-impact risk in one sentence.
7. Verdict — `"feasible"` (no blockers, all risks have mitigations), `"feasible_with_caveats"` (1-2 risks lack mitigation), `"blocked"` (a component is fundamentally infeasible at the constraint envelope).

Write `docs/products/<slug>/tech_risk.md` if you want to scratchpad during reasoning — the agent's deterministic renderer is authoritative.
```

- [ ] **Step 10: Run all Architect tests + quick LLM smoke**

```bash
uv run pytest tests/unit/test_architect*.py -v
uv run python -c "from agents.architect.agent import Architect; print(Architect()._system_prompt()[:200])"
```
Expected: all green; system prompt loads.

- [ ] **Step 11: Commit**

```bash
git add agents/architect/agent.py prompts/architect.md tests/unit/test_architect_validate_tech_risk.py
git commit -m "feat(iter-26b): Architect validate_tech_risk mode + intent dispatch"
```

---

## Task 6: Product Manager `validate_revenue_model` mode

PM also currently has single-mode dispatch (USER_STORIES_SCHEMA at `agents/product_manager/agent.py:31`). Same pattern as Architect.

**Files:**
- Modify: `agents/product_manager/agent.py`.
- Modify: `prompts/product_manager.md`.
- Create: `tests/unit/test_product_manager_validate_revenue.py`.

- [ ] **Step 1: Write failing tests (schema + render)**

Create `tests/unit/test_product_manager_validate_revenue.py`:

```python
"""PM validate-revenue-model mode: schema + render + dispatch + max_budget."""

from __future__ import annotations

from unittest.mock import patch

import jsonschema
import pytest

from agents.product_manager.agent import (
    ProductManager,
    VALIDATE_REVENUE_SCHEMA,
    _render_revenue_markdown,
)
from core.llm.base import LLMResponse
from core.messaging.schemas import MessageType
from tests.helpers.message_factories import make_incoming_assignment


_GOOD_OUTPUT = {
    "intent_completed": "validate_revenue_model",
    "buyer_persona": "Developer-influencer running a 5k-100k-sub Telegram channel, posting 3-5x weekly, currently spending 30-60 min/day on content.",
    "addressable_population_estimate": "~120 active CIS dev Telegram channels with 5k+ subs; ~2k globally if expanded.",
    "pricing_tiers": [
        {"name": "Free", "price_usd_monthly": 0, "target_user": "trial / <500 subs"},
        {"name": "Pro", "price_usd_monthly": 19, "target_user": "5k-50k subs"},
        {"name": "Power", "price_usd_monthly": 49, "target_user": "50k+ subs, daily volume"},
    ],
    "cac_envelope_usd": 0,
    "ltv_envelope_usd": 320,
    "time_to_first_revenue_weeks": 10,
    "time_to_1k_mrr_weeks": 24,
    "break_even_users": 35,
    "revenue_forecast": {
        "conservative_mrr_month_6": 800,
        "base_mrr_month_6": 1900,
        "optimistic_mrr_month_6": 4500,
    },
    "verdict": "viable",
    "summary": "$0 CAC via owner channel + $19 Pro tier + 35-user break-even is achievable in 6 months.",
    "artifacts": ["docs/products/telegram-tech-publisher/revenue.md"],
}


def test_schema_accepts_valid_output() -> None:
    jsonschema.validate(_GOOD_OUTPUT, VALIDATE_REVENUE_SCHEMA)


def test_schema_rejects_single_pricing_tier() -> None:
    bad = {**_GOOD_OUTPUT, "pricing_tiers": _GOOD_OUTPUT["pricing_tiers"][:1]}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_REVENUE_SCHEMA)


def test_schema_rejects_negative_break_even_users() -> None:
    bad = {**_GOOD_OUTPUT, "break_even_users": 0}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_REVENUE_SCHEMA)


def test_schema_rejects_unknown_verdict() -> None:
    bad = {**_GOOD_OUTPUT, "verdict": "great"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, VALIDATE_REVENUE_SCHEMA)


def test_render_includes_pricing_table_and_break_even() -> None:
    md = _render_revenue_markdown(_GOOD_OUTPUT, slug="telegram-tech-publisher")
    assert "# Revenue model: telegram-tech-publisher" in md
    assert "## Pricing tiers" in md
    assert "Pro" in md and "$19" in md
    assert "Break-even" in md
    assert "35" in md
    assert "viable" in md.lower()
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest tests/unit/test_product_manager_validate_revenue.py -v
```
Expected: ImportError on `VALIDATE_REVENUE_SCHEMA`.

- [ ] **Step 3: Add `VALIDATE_REVENUE_SCHEMA` + renderer**

In `agents/product_manager/agent.py`, after `USER_STORIES_SCHEMA` (around line 31-68), add:

```python
VALIDATE_REVENUE_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed", "buyer_persona", "addressable_population_estimate",
        "pricing_tiers", "cac_envelope_usd", "ltv_envelope_usd",
        "time_to_first_revenue_weeks", "time_to_1k_mrr_weeks",
        "break_even_users", "revenue_forecast", "verdict",
        "summary", "artifacts",
    ],
    "properties": {
        "intent_completed": {"const": "validate_revenue_model"},
        "buyer_persona": {"type": "string", "maxLength": 1000},
        "addressable_population_estimate": {"type": "string", "maxLength": 500},
        "pricing_tiers": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "price_usd_monthly", "target_user"],
                "properties": {
                    "name": {"type": "string", "maxLength": 100},
                    "price_usd_monthly": {"type": "number", "minimum": 0},
                    "target_user": {"type": "string", "maxLength": 300},
                },
            },
        },
        "cac_envelope_usd": {"type": "number", "minimum": 0},
        "ltv_envelope_usd": {"type": "number", "minimum": 0},
        "time_to_first_revenue_weeks": {"type": "integer", "minimum": 1},
        "time_to_1k_mrr_weeks": {"type": "integer", "minimum": 1},
        "break_even_users": {"type": "integer", "minimum": 1},
        "revenue_forecast": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "conservative_mrr_month_6",
                "base_mrr_month_6",
                "optimistic_mrr_month_6",
            ],
            "properties": {
                "conservative_mrr_month_6": {"type": "number", "minimum": 0},
                "base_mrr_month_6": {"type": "number", "minimum": 0},
                "optimistic_mrr_month_6": {"type": "number", "minimum": 0},
            },
        },
        "verdict": {"enum": ["viable", "viable_with_caveats", "not_viable"]},
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
    },
}


def _render_revenue_markdown(response: dict[str, Any], slug: str) -> str:
    """Render VALIDATE_REVENUE_SCHEMA output as revenue.md."""
    lines: list[str] = []
    lines.append(f"# Revenue model: {slug}\n")
    lines.append(f"- Verdict: **{response['verdict']}**")
    lines.append(f"- Break-even users: **{response['break_even_users']}**")
    lines.append(f"- Time to first revenue: **{response['time_to_first_revenue_weeks']} weeks**")
    lines.append(f"- Time to $1k MRR: **{response['time_to_1k_mrr_weeks']} weeks**\n")
    lines.append("## Summary\n")
    lines.append(response["summary"])
    lines.append("")
    lines.append("## Buyer persona\n")
    lines.append(response["buyer_persona"])
    lines.append("")
    lines.append("## Addressable population\n")
    lines.append(response["addressable_population_estimate"])
    lines.append("")
    lines.append("## Pricing tiers\n")
    lines.append("| Tier | $/month | Target user |")
    lines.append("|---|---|---|")
    for t in response["pricing_tiers"]:
        lines.append(f"| {t['name']} | ${t['price_usd_monthly']:g} | {t['target_user']} |")
    lines.append("")
    lines.append("## Unit economics\n")
    lines.append(f"- CAC envelope: **${response['cac_envelope_usd']:g}** / user")
    lines.append(f"- LTV envelope: **${response['ltv_envelope_usd']:g}** / user")
    lines.append("")
    lines.append("## Revenue forecast (month 6)\n")
    rf = response["revenue_forecast"]
    lines.append(f"- Conservative: ${rf['conservative_mrr_month_6']:.0f} MRR")
    lines.append(f"- Base:         ${rf['base_mrr_month_6']:.0f} MRR")
    lines.append(f"- Optimistic:   ${rf['optimistic_mrr_month_6']:.0f} MRR")
    lines.append("")
    return "\n".join(lines)
```

Add `from typing import Any` import if missing.

- [ ] **Step 4: Run schema + render tests, verify pass**

```bash
uv run pytest tests/unit/test_product_manager_validate_revenue.py -v -k "schema or render"
```
Expected: 5 passed.

- [ ] **Step 5: Add dispatch tests**

Append to the test file:

```python
@pytest.mark.asyncio
async def test_handle_dispatches_validate_schema_on_intent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agents.product_manager.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.product_manager.agent._VALIDATE_DIR", tmp_path / "docs" / "products")

    captured: dict = {}
    async def _fake_invoke(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(content="", structured_output=_GOOD_OUTPUT, metadata={"cost_cents": 100})

    with patch("agents.product_manager.agent.ProductManager._invoke_llm", _fake_invoke):
        pm = ProductManager()
        incoming = make_incoming_assignment(
            title="Validate revenue: telegram-tech-publisher",
            description="...",
            inputs={
                "intent": "validate_revenue_model",
                "slug": "telegram-tech-publisher",
                "candidate_brief": "...",
                "target_market": "...",
                "constraints": {},
            },
        )
        outputs = await pm.handle(incoming)

    assert captured["json_schema"] is VALIDATE_REVENUE_SCHEMA
    assert captured["max_budget_usd"] == 3.50
    assert (tmp_path / "docs" / "products" / "telegram-tech-publisher" / "revenue.md").exists()
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert reports[0].payload.status == "DONE"


@pytest.mark.asyncio
async def test_handle_blocks_on_invalid_slug(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agents.product_manager.agent._REPO_ROOT", tmp_path)
    pm = ProductManager()
    incoming = make_incoming_assignment(
        title="x", description="...",
        inputs={"intent": "validate_revenue_model", "slug": "BAD slug", "candidate_brief": "...", "target_market": "...", "constraints": {}},
    )
    outputs = await pm.handle(incoming)
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert reports[0].payload.status == "BLOCKED"


@pytest.mark.asyncio
async def test_handle_no_intent_falls_through_to_user_stories(monkeypatch, tmp_path) -> None:
    captured: dict = {}
    async def _fake_invoke(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(content="", structured_output={"user_stories": [], "acceptance_criteria": []}, metadata={})

    with patch("agents.product_manager.agent.ProductManager._invoke_llm", _fake_invoke):
        pm = ProductManager()
        incoming = make_incoming_assignment(title="Clarify", description="...", inputs=None)
        await pm.handle(incoming)

    from agents.product_manager.agent import USER_STORIES_SCHEMA
    assert captured["json_schema"] is USER_STORIES_SCHEMA
```

- [ ] **Step 6: Run dispatch tests, verify they fail**

```bash
uv run pytest tests/unit/test_product_manager_validate_revenue.py -v -k handle
```
Expected: failures — PM has no intent dispatch.

- [ ] **Step 7: Add intent dispatch to PM**

In `agents/product_manager/agent.py`, near top, add:

```python
import re

_VALIDATE_DIR = _REPO_ROOT / "docs" / "products"
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,50}$")
```

Replace existing `handle()` (around line 155-169):

```python
async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
    inputs = msg.payload.inputs or {}
    intent = inputs.get("intent")

    if intent == "validate_revenue_model":
        slug = inputs.get("slug", "")
        if not _SLUG_RE.match(slug):
            return [
                self._build_report(
                    msg,
                    status="BLOCKED",
                    summary=f"validate_revenue_model: input_validation — invalid slug {slug!r}",
                )
            ]
        schema = VALIDATE_REVENUE_SCHEMA
        max_budget = 3.50
        path_prefixes = f"docs/backlog,docs/products/{slug}"
    else:
        schema = USER_STORIES_SCHEMA
        max_budget = None
        path_prefixes = "docs/backlog"

    mcp_env = {"AI_TEAM_PATH_PREFIXES": path_prefixes}

    invoke_kwargs: dict[str, Any] = dict(
        model=self.model_tier,
        system_prompt=self._system_prompt(),
        user_message=self._render_user_message(msg),
        allowed_tools=self.allowed_tools,
        json_schema=schema,
        mcp_env=mcp_env,
        timeout_s=600,
    )
    if max_budget is not None:
        invoke_kwargs["max_budget_usd"] = max_budget

    response = await self._invoke_llm(**invoke_kwargs)
    return self._stamp_metrics(self.build_outputs(response, msg), response)
```

Update `build_outputs()` (around line 119-153):

```python
def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
    inputs = incoming.payload.inputs or {}
    intent = inputs.get("intent")

    if intent == "validate_revenue_model":
        return self._build_validate_revenue_outputs(response, incoming)

    # ... existing user-stories branch unchanged ...
```

Add new method:

```python
def _build_validate_revenue_outputs(
    self, response: LLMResponse, incoming: AgentMessage,
) -> list[AgentMessage]:
    inputs = incoming.payload.inputs or {}
    slug = inputs["slug"]
    out = response.structured_output or {}
    if not out or out.get("intent_completed") != "validate_revenue_model":
        return [
            self._build_report(
                incoming,
                status="BLOCKED",
                summary="validate_revenue_model: missing or malformed structured_output",
            )
        ]

    out_dir = _VALIDATE_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "revenue.md"
    artifact_path.write_text(_render_revenue_markdown(out, slug=slug))

    return [
        self._build_report(
            incoming,
            status="DONE",
            summary=out.get("summary") or "validate_revenue_model completed",
            structured=out,
            artifacts=[str(artifact_path.relative_to(_REPO_ROOT))],
        )
    ]
```

- [ ] **Step 8: Run full PM tests, verify pass**

```bash
uv run pytest tests/unit/test_product_manager*.py -v
```
Expected: all pre-existing + 8 new green.

- [ ] **Step 9: Update `prompts/product_manager.md`**

Append:

```markdown
## Workflow: validate-revenue-model mode

When `inputs.intent == "validate_revenue_model"`, you are stress-testing the monetization model for one product candidate (`inputs.slug`). Candidate brief in `inputs.candidate_brief`. Constraints in `inputs.constraints` (especially `max_paid_acquisition_cost_per_user_usd`, `max_time_to_first_revenue_months`). Target market in `inputs.target_market`.

### Output structure (matches VALIDATE_REVENUE_SCHEMA)

- `intent_completed`: literal `"validate_revenue_model"`.
- `buyer_persona`: who specifically buys (role, income, currently-paid tools, pain).
- `addressable_population_estimate`: best-effort size of the niche.
- `pricing_tiers`: 2-4 tiers `{name, price_usd_monthly, target_user}`.
- `cac_envelope_usd`: realistic CAC. **For owner-distributed channels this is typically $0.**
- `ltv_envelope_usd`: average lifetime value per paid user.
- `time_to_first_revenue_weeks`: integer.
- `time_to_1k_mrr_weeks`: integer.
- `break_even_users`: integer count needed to cover LLM opex + $5k/month owner cost-of-time.
- `revenue_forecast`: month-6 MRR `{conservative, base, optimistic}`.
- `verdict`: one of `"viable" | "viable_with_caveats" | "not_viable"`.
- `summary`: ≤ 2000 chars.
- `artifacts`: paths you wrote.

### Process

1. Buyer persona — single concrete description. Include income bracket and currently-paid alternatives.
2. Addressable population — count the niche. Cite sources where possible.
3. Pricing tiers — 3 is typical (Free / Pro / Power). Anchor prices to what the buyer already pays for adjacent tools.
4. CAC — if `inputs.constraints.max_paid_acquisition_cost_per_user_usd == 0`, model fully-organic acquisition; otherwise estimate paid-channel CAC for the niche.
5. LTV — months-to-churn × monthly MRR. For subscription tools the median is 12-24 months churn for engaged creators.
6. Time to first revenue — weeks from launch (assumes the build window from Architect's report). Compare to `inputs.constraints.max_time_to_first_revenue_months * 4.3`.
7. Time to $1k MRR — weeks from launch. Used to gauge slope.
8. Break-even — paid-users needed to cover LLM opex (from candidate brief's opex estimate) + $5k/month owner cost-of-time.
9. Revenue forecast at month 6 — conservative / base / optimistic MRR. Justify in summary.
10. Verdict — `"viable"` (break-even ≤ 200 users AND TTFR ≤ constraint), `"viable_with_caveats"` (one of the two strains), `"not_viable"` (both strain).
```

- [ ] **Step 10: Final PM run + commit**

```bash
uv run pytest tests/unit/test_product_manager*.py -v
```
Expected: green.

```bash
git add agents/product_manager/agent.py prompts/product_manager.md tests/unit/test_product_manager_validate_revenue.py
git commit -m "feat(iter-26b): PM validate_revenue_model mode + intent dispatch"
```

---

## Task 7: QA `synthesize_validation` intent

QA already has intent dispatch (`rank_brainstorm_candidates` vs `QA_REPORT`). Adding `synthesize_validation` is the 3rd intent. This task also implements:

- The `fatal_flaws ⇒ recommendation ∈ {kill, pivot}` cross-field invariant.
- Upstream task_report aggregation (read 3 sibling artifacts).
- The structured `pending_review` payload (6 owner-facing fields plus 3 routing fields).

**Files:**
- Modify: `agents/qa_engineer/agent.py`.
- Modify: `prompts/qa_engineer.md`.
- Create: `tests/unit/test_qa_synthesize_validation.py`.

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_qa_synthesize_validation.py`:

```python
"""QA synthesize_validation: schema + render + fatal_flaws invariant +
upstream aggregation + dispatch."""

from __future__ import annotations

from unittest.mock import patch

import jsonschema
import pytest

from agents.qa_engineer.agent import (
    QAEngineer,
    SYNTHESIZE_VALIDATION_SCHEMA,
    _render_validation_summary_markdown,
    _coerce_recommendation_for_fatal_flaws,
)
from core.llm.base import LLMResponse
from core.messaging.schemas import MessageType
from tests.helpers.message_factories import make_incoming_assignment


_GOOD_OUTPUT = {
    "intent_completed": "synthesize_validation",
    "recommendation": "go_with_caveats",
    "confidence": 4,
    "top_risks": [
        {"name": "Voice calibration drift", "severity": 3, "mitigation": "monthly recalibration script"},
        {"name": "Telegram Bot API rate limit on broadcast channels", "severity": 2, "mitigation": "per-chat queue with backoff"},
    ],
    "fatal_flaws": [],
    "build_window": "6-8 weeks",
    "next_steps": [
        "Draft iter-27 spec with first-sprint scope: source curator + single-channel pipeline",
        "Validate Telegram Stars vs Stripe payment flow before week 2",
        "Set up voice-calibration test harness before LLM integration",
    ],
    "summary": "All three upstream reports return positive verdicts with mitigable risks; recommend go_with_caveats.",
    "artifacts": ["docs/products/telegram-tech-publisher/_validation_summary.md"],
}


def test_schema_accepts_valid_output() -> None:
    jsonschema.validate(_GOOD_OUTPUT, SYNTHESIZE_VALIDATION_SCHEMA)


def test_schema_accepts_recommendation_kill_with_fatal_flaws() -> None:
    bad = {
        **_GOOD_OUTPUT,
        "recommendation": "kill",
        "fatal_flaws": ["Telegram ToS prohibits commercial bots"],
        "top_risks": [],
    }
    jsonschema.validate(bad, SYNTHESIZE_VALIDATION_SCHEMA)


def test_schema_rejects_unknown_recommendation() -> None:
    bad = {**_GOOD_OUTPUT, "recommendation": "maybe"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SYNTHESIZE_VALIDATION_SCHEMA)


def test_schema_rejects_confidence_out_of_range() -> None:
    bad = {**_GOOD_OUTPUT, "confidence": 6}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, SYNTHESIZE_VALIDATION_SCHEMA)


def test_coerce_recommendation_no_change_when_no_fatal_flaws() -> None:
    out = _coerce_recommendation_for_fatal_flaws(_GOOD_OUTPUT)
    assert out["recommendation"] == "go_with_caveats"


def test_coerce_recommendation_no_change_when_already_kill() -> None:
    inp = {**_GOOD_OUTPUT, "recommendation": "kill", "fatal_flaws": ["x"]}
    out = _coerce_recommendation_for_fatal_flaws(inp)
    assert out["recommendation"] == "kill"


def test_coerce_recommendation_no_change_when_already_pivot() -> None:
    inp = {**_GOOD_OUTPUT, "recommendation": "pivot", "fatal_flaws": ["x"]}
    out = _coerce_recommendation_for_fatal_flaws(inp)
    assert out["recommendation"] == "pivot"


def test_coerce_recommendation_forces_kill_when_go_with_fatal_flaws() -> None:
    """The fatal_flaws ⇒ {kill, pivot} cross-field invariant: if the LLM
    sets recommendation=go but lists fatal_flaws, override to kill and
    record the original in metadata."""
    inp = {
        **_GOOD_OUTPUT,
        "recommendation": "go",
        "fatal_flaws": ["LLM hallucinates pricing in 8% of generated posts"],
    }
    out = _coerce_recommendation_for_fatal_flaws(inp)
    assert out["recommendation"] == "kill"
    assert out.get("_coerced_from") == "go"


def test_render_validation_summary_includes_yaml_block_and_sections() -> None:
    md = _render_validation_summary_markdown(_GOOD_OUTPUT, slug="telegram-tech-publisher")
    # Top-of-file YAML block
    assert md.startswith("---\n")
    assert "recommendation: go_with_caveats" in md
    assert "confidence: 4" in md
    assert "build_window: 6-8 weeks" in md
    # Prose
    assert "# Validation summary: telegram-tech-publisher" in md
    assert "## Risk register" in md
    assert "Voice calibration drift" in md
    assert "## Next steps" in md
```

- [ ] **Step 2: Run, verify failure**

```bash
uv run pytest tests/unit/test_qa_synthesize_validation.py -v
```
Expected: ImportError on `SYNTHESIZE_VALIDATION_SCHEMA` and helpers.

- [ ] **Step 3: Add schema + render + invariant helper**

In `agents/qa_engineer/agent.py`, after `RANK_BRAINSTORM_SCHEMA` (around line 65-85), add:

```python
SYNTHESIZE_VALIDATION_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed", "recommendation", "confidence",
        "top_risks", "fatal_flaws", "build_window",
        "next_steps", "summary", "artifacts",
    ],
    "properties": {
        "intent_completed": {"const": "synthesize_validation"},
        "recommendation": {"enum": ["go", "go_with_caveats", "pivot", "kill"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 5},
        "top_risks": {
            "type": "array",
            "minItems": 0,
            "maxItems": 5,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "severity", "mitigation"],
                "properties": {
                    "name": {"type": "string", "maxLength": 200},
                    "severity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "mitigation": {"type": "string", "maxLength": 500},
                },
            },
        },
        "fatal_flaws": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "default": [],
        },
        "build_window": {
            "enum": ["4-6 weeks", "6-8 weeks", "8-12 weeks", "12+ weeks", "unknown"],
        },
        "next_steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 7,
            "items": {"type": "string", "maxLength": 300},
        },
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
    },
}


def _coerce_recommendation_for_fatal_flaws(response: dict[str, Any]) -> dict[str, Any]:
    """Enforce the cross-field invariant: fatal_flaws non-empty ⇒
    recommendation ∈ {kill, pivot}. JSON Schema can't express
    conditional constraints, so we override here.
    """
    fatal = response.get("fatal_flaws") or []
    rec = response.get("recommendation")
    if fatal and rec not in {"kill", "pivot"}:
        coerced = dict(response)
        coerced["recommendation"] = "kill"
        coerced["_coerced_from"] = rec
        return coerced
    return response


def _render_validation_summary_markdown(response: dict[str, Any], slug: str) -> str:
    """Render SYNTHESIZE_VALIDATION_SCHEMA output as _validation_summary.md
    with a top-of-file YAML block followed by prose sections."""
    lines: list[str] = []
    lines.append("---")
    lines.append(f"slug: {slug}")
    lines.append(f"recommendation: {response['recommendation']}")
    lines.append(f"confidence: {response['confidence']}")
    lines.append(f"build_window: {response['build_window']}")
    lines.append(f"fatal_flaws_count: {len(response.get('fatal_flaws') or [])}")
    if "_coerced_from" in response:
        lines.append(f"recommendation_coerced_from: {response['_coerced_from']}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Validation summary: {slug}\n")
    lines.append("## Recommendation\n")
    lines.append(f"**{response['recommendation']}** (confidence {response['confidence']}/5)\n")
    lines.append("## Summary\n")
    lines.append(response["summary"])
    lines.append("")

    fatal = response.get("fatal_flaws") or []
    if fatal:
        lines.append("## Fatal flaws\n")
        for item in fatal:
            lines.append(f"- {item}")
        lines.append("")

    risks = response.get("top_risks") or []
    if risks:
        lines.append("## Risk register\n")
        lines.append("| # | Risk | Severity (1-5) | Mitigation |")
        lines.append("|---|---|---|---|")
        for i, r in enumerate(risks, 1):
            lines.append(f"| {i} | {r['name']} | {r['severity']} | {r['mitigation']} |")
        lines.append("")

    lines.append("## Next steps\n")
    for step in response["next_steps"]:
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)
```

Add `from typing import Any` if not present.

- [ ] **Step 4: Re-run unit tests**

```bash
uv run pytest tests/unit/test_qa_synthesize_validation.py -v -k "schema or coerce or render"
```
Expected: 9 passed (the new tests for schema, coerce, render).

- [ ] **Step 5: Add dispatch + upstream-aggregation test**

Append to `tests/unit/test_qa_synthesize_validation.py`:

```python
@pytest.mark.asyncio
async def test_handle_dispatches_synthesize_schema_on_intent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.qa_engineer.agent._VALIDATE_DIR", tmp_path / "docs" / "products")

    # Seed the 3 upstream artifacts the synth agent will read.
    out_dir = tmp_path / "docs" / "products" / "telegram-tech-publisher"
    out_dir.mkdir(parents=True)
    (out_dir / "competitors.md").write_text("# Competitor scan\nverdict: underserved\n")
    (out_dir / "tech_risk.md").write_text("# Tech risk\nverdict: feasible_with_caveats\n")
    (out_dir / "revenue.md").write_text("# Revenue\nverdict: viable\n")

    captured: dict = {}
    async def _fake_invoke(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(content="", structured_output=_GOOD_OUTPUT, metadata={"cost_cents": 100})

    with patch("agents.qa_engineer.agent.QAEngineer._invoke_llm", _fake_invoke):
        qa = QAEngineer()
        incoming = make_incoming_assignment(
            title="Synthesize validation",
            description="...",
            inputs={
                "intent": "synthesize_validation",
                "slug": "telegram-tech-publisher",
                "upstream_ids": ["comp", "tech", "rev"],
            },
        )
        outputs = await qa.handle(incoming)

    assert captured["json_schema"] is SYNTHESIZE_VALIDATION_SCHEMA
    assert captured["max_budget_usd"] == 2.50
    summary_path = tmp_path / "docs" / "products" / "telegram-tech-publisher" / "_validation_summary.md"
    assert summary_path.exists()
    body = summary_path.read_text()
    assert "recommendation: go_with_caveats" in body
    assert "## Risk register" in body

    # QA emits a task_report AND a request_human_review.
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    reviews = [m for m in outputs if m.message_type == MessageType.REQUEST_HUMAN_REVIEW]
    assert len(reports) == 1
    assert reports[0].payload.status == "DONE"
    assert len(reviews) >= 1


@pytest.mark.asyncio
async def test_handle_coerces_fatal_flaws_to_kill(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.qa_engineer.agent._VALIDATE_DIR", tmp_path / "docs" / "products")
    out_dir = tmp_path / "docs" / "products" / "telegram-tech-publisher"
    out_dir.mkdir(parents=True)

    bad_output = {
        **_GOOD_OUTPUT,
        "recommendation": "go",
        "fatal_flaws": ["Telegram ToS prohibits commercial bots in this category"],
    }
    async def _fake_invoke(self, **kwargs):
        return LLMResponse(content="", structured_output=bad_output, metadata={"cost_cents": 100})

    with patch("agents.qa_engineer.agent.QAEngineer._invoke_llm", _fake_invoke):
        qa = QAEngineer()
        incoming = make_incoming_assignment(
            title="Synthesize",
            description="...",
            inputs={"intent": "synthesize_validation", "slug": "telegram-tech-publisher", "upstream_ids": ["comp", "tech", "rev"]},
        )
        outputs = await qa.handle(incoming)

    summary_md = (tmp_path / "docs" / "products" / "telegram-tech-publisher" / "_validation_summary.md").read_text()
    assert "recommendation: kill" in summary_md
    assert "recommendation_coerced_from: go" in summary_md


@pytest.mark.asyncio
async def test_handle_other_intent_falls_through_to_existing_branches(
    monkeypatch, tmp_path,
) -> None:
    """rank_brainstorm_candidates branch still works."""
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)

    captured: dict = {}
    async def _fake_invoke(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(content="", structured_output={
            "intent_completed": "rank_brainstorm_candidates",
            "ranking_summary": "x",
            "top_3_overall": [],
        }, metadata={})

    with patch("agents.qa_engineer.agent.QAEngineer._invoke_llm", _fake_invoke):
        qa = QAEngineer()
        incoming = make_incoming_assignment(
            title="Rank",
            description="...",
            inputs={"intent": "rank_brainstorm_candidates"},
        )
        await qa.handle(incoming)

    from agents.qa_engineer.agent import RANK_BRAINSTORM_SCHEMA
    assert captured["json_schema"] is RANK_BRAINSTORM_SCHEMA
```

- [ ] **Step 6: Run, verify failure**

```bash
uv run pytest tests/unit/test_qa_synthesize_validation.py -v -k "handle"
```
Expected: failures — no `synthesize_validation` dispatch yet.

- [ ] **Step 7: Add dispatch + build_outputs to QA**

In `agents/qa_engineer/agent.py`, near top, add:

```python
import re

_VALIDATE_DIR = _REPO_ROOT / "docs" / "products"
_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{1,50}$")
```

Update `handle()` (around line 239-258). The body should now route on three intents:

```python
async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
    inputs = msg.payload.inputs or {}
    intent = inputs.get("intent")

    if intent == "synthesize_validation":
        slug = inputs.get("slug", "")
        if not _SLUG_RE.match(slug):
            return [
                self._build_report(
                    msg,
                    status="BLOCKED",
                    summary=f"synthesize_validation: input_validation — invalid slug {slug!r}",
                )
            ]
        schema = SYNTHESIZE_VALIDATION_SCHEMA
        max_budget = 2.50
        path_prefixes = f"docs/sandbox/ideas,docs/market,docs/products/_candidates,docs/products/{slug}"
    elif intent == "rank_brainstorm_candidates":
        schema = RANK_BRAINSTORM_SCHEMA
        max_budget = None
        path_prefixes = "docs/sandbox/ideas,docs/market,docs/products/_candidates"
    else:
        schema = QA_REPORT_SCHEMA
        max_budget = None
        path_prefixes = None  # leave default

    mcp_env = {"AI_TEAM_PATH_PREFIXES": path_prefixes} if path_prefixes else None

    invoke_kwargs: dict[str, Any] = dict(
        model=self.model_tier,
        system_prompt=self._system_prompt(),
        user_message=self._render_user_message(msg),
        allowed_tools=self.allowed_tools,
        json_schema=schema,
        timeout_s=600,
    )
    if max_budget is not None:
        invoke_kwargs["max_budget_usd"] = max_budget
    if mcp_env is not None:
        invoke_kwargs["mcp_env"] = mcp_env

    response = await self._invoke_llm(**invoke_kwargs)
    outputs = self._stamp_metrics(self.build_outputs(response, msg), response)
    return outputs
```

Add new branch to `build_outputs()` at top:

```python
def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
    inputs = incoming.payload.inputs or {}
    intent = inputs.get("intent")

    if intent == "synthesize_validation":
        return self._build_synthesize_validation_outputs(response, incoming)

    if intent == "rank_brainstorm_candidates":
        # ... existing branch ...
```

Add the new builder method:

```python
def _build_synthesize_validation_outputs(
    self, response: LLMResponse, incoming: AgentMessage,
) -> list[AgentMessage]:
    inputs = incoming.payload.inputs or {}
    slug = inputs["slug"]
    raw = response.structured_output or {}
    if not raw or raw.get("intent_completed") != "synthesize_validation":
        return [
            self._build_report(
                incoming,
                status="BLOCKED",
                summary="synthesize_validation: missing or malformed structured_output",
            )
        ]

    coerced = _coerce_recommendation_for_fatal_flaws(raw)

    out_dir = _VALIDATE_DIR / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / "_validation_summary.md"
    artifact_path.write_text(_render_validation_summary_markdown(coerced, slug=slug))

    report_summary = (
        coerced.get("summary")
        or f"{slug}: recommendation={coerced['recommendation']}, "
           f"confidence={coerced['confidence']}, "
           f"fatal_flaws={len(coerced.get('fatal_flaws') or [])}"
    )

    return [
        self._build_report(
            incoming,
            status="DONE",
            summary=report_summary,
            structured=coerced,
            artifacts=[str(artifact_path.relative_to(_REPO_ROOT))],
        ),
        self._build_human_review_request(
            incoming,
            summary=report_summary,
            structured=coerced,
        ),
    ]
```

If `_build_human_review_request` doesn't exist verbatim, use the same construct the existing `rank_brainstorm_candidates` branch uses to emit `REQUEST_HUMAN_REVIEW` messages (mirror it line-for-line).

- [ ] **Step 8: Run full QA tests**

```bash
uv run pytest tests/unit/test_qa*.py -v
```
Expected: all pre-existing + new 13 green. The QA safety-net summary (`report.get("summary") or report.get("ranking_summary")`) handles the new branch without changes because `summary` is the field name in `SYNTHESIZE_VALIDATION_SCHEMA`.

- [ ] **Step 9: Update `prompts/qa_engineer.md`**

Append:

```markdown
## Intent: synthesize_validation

When `inputs.intent == "synthesize_validation"`, you are synthesizing a build-or-pivot recommendation for one product candidate (`inputs.slug`) from three upstream agent reports already on disk:

- `docs/products/<slug>/competitors.md` (MR)
- `docs/products/<slug>/tech_risk.md` (Architect)
- `docs/products/<slug>/revenue.md` (PM)

Read all three before responding.

### Output structure (matches SYNTHESIZE_VALIDATION_SCHEMA)

- `intent_completed`: literal `"synthesize_validation"`.
- `recommendation`: one of `"go" | "go_with_caveats" | "pivot" | "kill"`.
- `confidence`: 0-5 integer.
- `top_risks`: 0-5 items `{name, severity (1-5), mitigation}`.
- `fatal_flaws`: array of strings. **If non-empty, recommendation MUST be `kill` or `pivot`.** Python will coerce to `kill` if you violate this.
- `build_window`: one of `"4-6 weeks" | "6-8 weeks" | "8-12 weeks" | "12+ weeks" | "unknown"`.
- `next_steps`: 1-7 strings.
- `summary`: ≤ 2000 chars, one-paragraph defense of the recommendation.
- `artifacts`: paths you wrote.

### Process

1. Read the three upstream artifacts. Note each agent's verdict.
2. Side-by-side cross-cuts:
   - MR's `verdict` (`underserved` / `saturated` / `marginal`)
   - Architect's `verdict` (`feasible` / `feasible_with_caveats` / `blocked`)
   - PM's `verdict` (`viable` / `viable_with_caveats` / `not_viable`)
3. Look for emergent cross-agent risks — risks that appear when combining two reports but not in either alone (e.g., MR finds competitor X with same moat AND PM confirms competitor X has same pricing → moat doesn't hold).
4. Risk register — top 5 deduped risks across the three reports + cross-cuts. Each `{name, severity (1-5), mitigation}`. Severity 5 is "could end the product"; severity 1 is "annoying but routine."
5. Fatal flaws — list specific show-stoppers (ToS violation, already-saturated niche, sub-$0 unit economics, blocked component). Each in one sentence. Empty array if none.
6. Recommendation:
   - `go` — no fatal flaws, all top risks have mitigations.
   - `go_with_caveats` — no fatal flaws, 1-2 risks lack mitigation.
   - `pivot` — at least one high-severity risk dominates the pick; a backup candidate would be better.
   - `kill` — at least one fatal flaw.
7. Confidence — 0 (coin flip) to 5 (highly confident).
8. Next steps:
   - If `go` / `go_with_caveats`: top-3 open questions for iter-27 + suggested first-iteration scope.
   - If `pivot`: top-2 backup slugs from `docs/products/_candidates/_combined_ranking.md` to validate next.
   - If `kill`: what changed in our understanding (1-3 bullets).
9. Build window from Architect's report (do not invent a new one).
10. Summary — one paragraph defending the recommendation, citing specific evidence from the three reports.

### Hard rule

If `fatal_flaws` is non-empty and `recommendation` is `go` or `go_with_caveats`, Python overrides your recommendation to `kill` and records your original in `_coerced_from`. This is the only place the framework second-guesses you; behave accordingly.
```

- [ ] **Step 10: Final QA run + commit**

```bash
uv run pytest tests/unit/test_qa*.py -v
```
Expected: all green.

```bash
git add agents/qa_engineer/agent.py prompts/qa_engineer.md tests/unit/test_qa_synthesize_validation.py
git commit -m "feat(iter-26b): QA synthesize_validation intent + fatal_flaws invariant"
```

---

## Task 8: Integration e2e test — full chain on mocked LLM

Wire the four new modes together. End-to-end on the mocked LLM with monkeypatched `_REPO_ROOT` + `_VALIDATE_DIR` per agent (so the test never writes to the real repo).

**Files:**
- Create: `tests/integration/test_iter_26b_e2e_validate.py`.

- [ ] **Step 1: Write the integration test**

```python
"""End-to-end validate-product chain on mocked LLM. Owner-pick of
recommendation field arrives in the pending_review payload at the end."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from core.llm.base import LLMResponse


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


_TL_DECOMPOSITION = {
    "task_overview": "Validate telegram-tech-publisher",
    "subtasks": [
        {
            "id": "comp", "recipient": "market_researcher",
            "title": "Comp scan", "description": "...",
            "depends_on": [],
            "inputs": {
                "intent": "validate_competitors",
                "slug": "telegram-tech-publisher",
                "depth": "quick",
                "candidate_brief": "...",
                "target_market": "...",
                "constraints": {},
            },
        },
        {
            "id": "tech", "recipient": "architect",
            "title": "Tech risk", "description": "...",
            "depends_on": [],
            "inputs": {
                "intent": "validate_tech_risk",
                "slug": "telegram-tech-publisher",
                "candidate_brief": "...",
                "constraints": {},
            },
        },
        {
            "id": "rev", "recipient": "product_manager",
            "title": "Revenue", "description": "...",
            "depends_on": [],
            "inputs": {
                "intent": "validate_revenue_model",
                "slug": "telegram-tech-publisher",
                "candidate_brief": "...",
                "target_market": "...",
                "constraints": {},
            },
        },
        {
            "id": "synth", "recipient": "qa_engineer",
            "title": "Synth", "description": "...",
            "depends_on": ["comp", "tech", "rev"],
            "inputs": {
                "intent": "synthesize_validation",
                "slug": "telegram-tech-publisher",
                "upstream_ids": ["comp", "tech", "rev"],
            },
        },
    ],
}

_MR_OUTPUT = {
    "intent_completed": "validate_competitors",
    "competitors_found": 5, "pain_signals_found": 3,
    "distribution_feasibility": {
        "channel_estimate": "x", "audience_reach_estimate": "x",
        "conversion_to_paid_estimate": "x", "notes": "x",
    },
    "verdict": "underserved",
    "summary": "MR: underserved.",
    "artifacts": ["docs/products/telegram-tech-publisher/competitors.md"],
}

_ARCH_OUTPUT = {
    "intent_completed": "validate_tech_risk",
    "components": [
        {"name": "Bot API", "complexity": 2, "dependency": "x", "scaling_limit": "x", "gotchas": []},
        {"name": "Curator", "complexity": 2, "dependency": "x", "scaling_limit": "x", "gotchas": []},
        {"name": "LLM", "complexity": 3, "dependency": "x", "scaling_limit": "x", "gotchas": []},
    ],
    "risks_found": 2,
    "top_risk": "Voice drift",
    "llm_opex_at_scale": {"per_user_per_day_at_100": 0.4, "per_user_per_day_at_1000": 0.3, "per_user_per_day_at_10000": 0.2},
    "build_window_weeks": "6-8 weeks",
    "verdict": "feasible_with_caveats",
    "summary": "Arch: feasible_with_caveats.",
    "artifacts": ["docs/products/telegram-tech-publisher/tech_risk.md"],
}

_PM_OUTPUT = {
    "intent_completed": "validate_revenue_model",
    "buyer_persona": "Dev creator",
    "addressable_population_estimate": "120 channels",
    "pricing_tiers": [
        {"name": "Free", "price_usd_monthly": 0, "target_user": "trial"},
        {"name": "Pro", "price_usd_monthly": 19, "target_user": "5k-50k"},
    ],
    "cac_envelope_usd": 0, "ltv_envelope_usd": 320,
    "time_to_first_revenue_weeks": 10, "time_to_1k_mrr_weeks": 24,
    "break_even_users": 35,
    "revenue_forecast": {"conservative_mrr_month_6": 800, "base_mrr_month_6": 1900, "optimistic_mrr_month_6": 4500},
    "verdict": "viable",
    "summary": "PM: viable.",
    "artifacts": ["docs/products/telegram-tech-publisher/revenue.md"],
}

_QA_OUTPUT = {
    "intent_completed": "synthesize_validation",
    "recommendation": "go_with_caveats",
    "confidence": 4,
    "top_risks": [{"name": "Voice drift", "severity": 3, "mitigation": "recal script"}],
    "fatal_flaws": [],
    "build_window": "6-8 weeks",
    "next_steps": ["Draft iter-27 spec", "Validate Telegram Stars flow", "Set up voice harness"],
    "summary": "All three reports positive; go_with_caveats.",
    "artifacts": ["docs/products/telegram-tech-publisher/_validation_summary.md"],
}


def _mock_llm_router(role: str):
    """Return a fake LLM response keyed off the agent role."""
    mapping = {
        "team_lead": _TL_DECOMPOSITION,
        "market_researcher": _MR_OUTPUT,
        "architect": _ARCH_OUTPUT,
        "product_manager": _PM_OUTPUT,
        "qa_engineer": _QA_OUTPUT,
    }
    payload = mapping[role]
    return LLMResponse(content="", structured_output=payload, metadata={"cost_cents": 10})


async def test_full_validate_product_chain_emits_pending_review(
    monkeypatch, tmp_path, owner_token,
) -> None:
    # Monkeypatch every agent's _REPO_ROOT and _VALIDATE_DIR so file writes
    # land in tmp_path rather than the real repo.
    for module in [
        "agents.market_researcher.agent",
        "agents.architect.agent",
        "agents.product_manager.agent",
        "agents.qa_engineer.agent",
    ]:
        monkeypatch.setattr(f"{module}._REPO_ROOT", tmp_path)
        monkeypatch.setattr(f"{module}._VALIDATE_DIR", tmp_path / "docs" / "products")

    async def _fake_invoke(self, **kwargs):
        return _mock_llm_router(self.role)

    with patch("agents._base.base_agent.BaseAgent._invoke_llm", _fake_invoke):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://t") as client:
            resp = await client.post(
                "/api/tasks",
                json={
                    "title": "Validate product: telegram-tech-publisher",
                    "description": "**Slug:** telegram-tech-publisher\n...",
                    "priority": "p2",
                    "inputs": {
                        "intent": "validate_product",
                        "slug": "telegram-tech-publisher",
                        "depth": "quick",
                        "candidate_brief": "**Slug:** telegram-tech-publisher\n...",
                        "constraints": {"owner_profile": "solo_developer"},
                    },
                },
                headers={"Authorization": f"Bearer {owner_token}"},
            )
            assert resp.status_code == 200
            correlation_id = resp.json()["correlation_id"]

            # Wait for the dispatcher to drain the queue.
            for _ in range(60):
                pr = await client.get(
                    "/api/reviews",
                    headers={"Authorization": f"Bearer {owner_token}"},
                )
                if pr.status_code == 200 and pr.json():
                    rows = pr.json()
                    if any(r["correlation_id"] == correlation_id for r in rows):
                        break
                await asyncio.sleep(0.5)
            else:
                raise AssertionError("pending_review never appeared")

    # Verify file artifacts.
    out = tmp_path / "docs" / "products" / "telegram-tech-publisher"
    assert (out / "competitors.md").exists()
    assert (out / "tech_risk.md").exists()
    assert (out / "revenue.md").exists()
    summary_md = (out / "_validation_summary.md").read_text()
    assert "recommendation: go_with_caveats" in summary_md
```

If `BaseAgent._invoke_llm` is not the right hook (per the existing pattern from iter-26a integration test), use the same patch surface that `tests/integration/test_iter_26a_e2e_brainstorm.py` uses.

- [ ] **Step 2: Run the integration test**

```bash
uv run pytest tests/integration/test_iter_26b_e2e_validate.py -v --integration
```
Expected: 1 passed. If it fails, debug — most likely:
- `_invoke_llm` patch path is wrong (mirror iter-26a's path)
- `_REPO_ROOT` monkeypatch missed an agent module
- Dispatcher hasn't drained — increase the poll attempts

- [ ] **Step 3: Run the existing integration suite to ensure no regression**

```bash
uv run pytest tests/integration -v --integration
```
Expected: all pre-existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_iter_26b_e2e_validate.py
git commit -m "test(iter-26b): e2e validate-product chain on mocked LLM"
```

---

## Task 9: Real-LLM smoke (single MR agent at `depth=quick`)

A one-agent real-LLM smoke that owner runs manually with `--real-llm`. Targets MR `validate_competitors` at `depth=quick` (~$0.50-1.50 spend, ~5-8 min wall clock) — cheap enough to be a daily sanity check, deep enough to exercise the full claude -p + json-schema + WebFetch path.

**Files:**
- Create: `tests/integration/test_validator_one_agent_real_llm.py`.

- [ ] **Step 1: Write the real-LLM smoke**

```python
"""Owner-run real-LLM smoke for iter-26b validator.

Run with:
    uv run pytest tests/integration/test_validator_one_agent_real_llm.py \\
        --real-llm -v -s

Targets MR validate_competitors at depth=quick (~$0.50-1.50, ~5-8 min).
"""

from __future__ import annotations

import pytest
from pathlib import Path

from agents.market_researcher.agent import (
    MarketResearcher,
    VALIDATE_COMPETITORS_SCHEMA,
)
from core.messaging.schemas import MessageType
from tests.helpers.message_factories import make_incoming_assignment


pytestmark = [pytest.mark.real_llm, pytest.mark.integration]


CANDIDATE_BRIEF = """## 1. AI Content Engine for Telegram Developer Channels

**Slug:** telegram-tech-publisher
**Monetization:** subscription
**Target Buyer:** Developer-influencers running Telegram channels (500–100k subscribers) in Russian-speaking and global developer communities who want to post consistently without writing each post manually.

**One Paragraph:** Telegram is the dominant technical content platform in the CIS developer community. This tool monitors the creator's specified sources (GitHub, RSS, Hacker News) and drafts 3-5 Telegram-formatted posts per day in the creator's established voice, including code blocks, inline links, and optional Telegra.ph long-reads for deep dives.

**Scores:** tam_signal=3, solo_fit=5, llm_opex_fit=5, defensibility=4, time_to_first_revenue=5
**Composite:** 22

**Known Competitors:**
- Buffer (https://buffer.com)
- Typefully (https://typefully.com)
"""


@pytest.mark.asyncio
async def test_mr_validate_competitors_quick_depth_real_llm(
    real_llm: bool, tmp_path: Path, monkeypatch,
) -> None:
    if not real_llm:
        pytest.skip("--real-llm not passed; this is the owner-run smoke")

    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr("agents.market_researcher.agent._VALIDATE_DIR", tmp_path / "docs" / "products")

    mr = MarketResearcher()
    incoming = make_incoming_assignment(
        title="Validate competitors: telegram-tech-publisher",
        description=CANDIDATE_BRIEF,
        inputs={
            "intent": "validate_competitors",
            "slug": "telegram-tech-publisher",
            "depth": "quick",
            "candidate_brief": CANDIDATE_BRIEF,
            "target_market": "developer_influencers_telegram_500_to_100k_subs",
            "constraints": {
                "owner_profile": "solo_developer",
                "monetization_model": "subscription",
            },
        },
    )

    outputs = await mr.handle(incoming)
    reports = [m for m in outputs if m.message_type == MessageType.TASK_REPORT]
    assert len(reports) == 1
    assert reports[0].payload.status == "DONE", f"MR did not return DONE: {reports[0]}"

    structured = reports[0].payload.structured or {}
    assert structured.get("intent_completed") == "validate_competitors"
    assert structured["competitors_found"] >= 3  # depth=quick targets 5
    assert structured["verdict"] in {"underserved", "saturated", "marginal"}

    artifact = tmp_path / "docs" / "products" / "telegram-tech-publisher" / "competitors.md"
    assert artifact.exists()
    print(f"\n--- Real-LLM competitors.md ---\n{artifact.read_text()[:2000]}")
```

The `real_llm` and `--real-llm` fixtures/flags must exist already (iter-26a uses them at `tests/integration/test_mr_brainstorm_one_niche_real_llm.py`). If not, mirror that file's gating logic.

- [ ] **Step 2: Verify it skips without `--real-llm`**

```bash
uv run pytest tests/integration/test_validator_one_agent_real_llm.py -v --integration
```
Expected: 1 skipped (no `--real-llm`).

- [ ] **Step 3: Owner runs it manually**

```bash
uv run pytest tests/integration/test_validator_one_agent_real_llm.py --real-llm --integration -v -s
```
Expected: 1 passed, ~5-8 min, ~$0.50-1.50 spend, `competitors.md` content printed.

- [ ] **Step 4: Commit (after owner confirms the real-LLM run works)**

```bash
git add tests/integration/test_validator_one_agent_real_llm.py
git commit -m "test(iter-26b): real-LLM smoke for MR validate_competitors"
```

---

## Task 10: Demo script `scripts/demo_iter_26b.sh`

Owner-run end-to-end demo. Mirrors `scripts/demo_iter_26a.sh` (preflight → up → migrate → API → submit → poll → drain → report) with the validate-product call and a 30-min poll deadline.

**Files:**
- Create: `scripts/demo_iter_26b.sh`.

- [ ] **Step 1: Write the demo script**

Use the same skeleton as `scripts/demo_iter_26a.sh`. Replace the Phase 5 submit call:

```bash
#!/usr/bin/env bash
set -euo pipefail

# scripts/demo_iter_26b.sh — owner-run end-to-end iter-26b demo.

BOLD_BLUE='\033[1;34m'
BOLD_GREEN='\033[1;32m'
NC='\033[0m'

SLUG="${1:-telegram-tech-publisher}"
DEPTH="${2:-standard}"
CANDIDATE_FILE="docs/products/_candidates/_brainstorm_creator_tools.md"
CONSTRAINTS_JSON="scripts/iter_26b_constraints.json"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="docs/iterations/iter_26b_demo_logs"
mkdir -p "$LOG_DIR"

echo -e "${BOLD_BLUE}▶ 1/7 — Preflight quota check${NC}"
./scripts/preflight_quota_check.sh

echo -e "${BOLD_BLUE}▶ 2/7 — Start infra${NC}"
make up

echo -e "${BOLD_BLUE}▶ 3/7 — Apply migrations${NC}"
uv run alembic upgrade head

echo -e "${BOLD_BLUE}▶ 4/7 — Start API + dispatcher in background${NC}"
API_LOG="$LOG_DIR/${SLUG}_api_${TIMESTAMP}.log"
OWNER_TOKEN_FILE="$(pwd)/.env" uv run uvicorn apps.api.main:app \
    --host 127.0.0.1 --port 8000 --log-level info > "$API_LOG" 2>&1 &
API_PID=$!
trap "kill $API_PID 2>/dev/null || true" EXIT
sleep 4
echo -e "${BOLD_GREEN}✓ API ready (pid $API_PID)${NC}"

echo -e "${BOLD_BLUE}▶ 5/7 — Submit validate-product task${NC}"
SUBMIT_OUT="$(uv run ai-team validate-product \
    --slug "$SLUG" \
    --candidate-file "$CANDIDATE_FILE" \
    --depth "$DEPTH" \
    --constraints-json "$CONSTRAINTS_JSON" 2>&1)"
echo "$SUBMIT_OUT"
CORRELATION="$(echo "$SUBMIT_OUT" | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | head -1)"
echo -e "${BOLD_GREEN}✓ submitted (correlation ${CORRELATION:0:8})${NC}"

echo -e "${BOLD_BLUE}▶ 6/7 — Poll for QA pending_review (≤30 min)${NC}"
DEADLINE=$((SECONDS + 30 * 60))
LAST_AUDIT=0; LAST_QA=0
while [[ $SECONDS -lt $DEADLINE ]]; do
    sleep 60
    ELAPSED_MIN=$(( (SECONDS) / 60 ))
    AUDIT_ROWS=$(uv run python -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
async def main():
    eng = create_async_engine(os.environ['DATABASE_URL'])
    async with eng.connect() as c:
        from sqlalchemy import text
        r = await c.execute(text('SELECT COUNT(*) FROM audit_log WHERE correlation_id = :c'), {'c': '$CORRELATION'})
        print(r.scalar())
asyncio.run(main())
" 2>/dev/null || echo 0)
    QA_REVIEWS=$(uv run python -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
async def main():
    eng = create_async_engine(os.environ['DATABASE_URL'])
    async with eng.connect() as c:
        from sqlalchemy import text
        r = await c.execute(text(\"SELECT COUNT(*) FROM pending_reviews WHERE correlation_id = :c AND requesting_agent = 'qa_engineer' AND status = 'pending'\"), {'c': '$CORRELATION'})
        print(r.scalar())
asyncio.run(main())
" 2>/dev/null || echo 0)
    echo "[t+${ELAPSED_MIN}m] audit_rows=$AUDIT_ROWS qa_reviews=$QA_REVIEWS"
    if [[ "$QA_REVIEWS" -ge 1 ]]; then
        echo -e "${BOLD_GREEN}✓ QA produced a pending_review (qa_engineer count=$QA_REVIEWS)${NC}"
        break
    fi
done

if [[ "$QA_REVIEWS" -lt 1 ]]; then
    echo "⚠ poll deadline reached, no QA pending_review for $CORRELATION"
fi

echo "Draining 60s for QA task_report audit write..."
sleep 60
FINAL_AUDIT=$(uv run python -c "
import asyncio, os
from sqlalchemy.ext.asyncio import create_async_engine
async def main():
    eng = create_async_engine(os.environ['DATABASE_URL'])
    async with eng.connect() as c:
        from sqlalchemy import text
        r = await c.execute(text('SELECT COUNT(*) FROM audit_log WHERE correlation_id = :c'), {'c': '$CORRELATION'})
        print(r.scalar())
asyncio.run(main())
" 2>/dev/null || echo 0)
echo "[drain complete] audit_rows=$FINAL_AUDIT"

echo ""
echo -e "${BOLD_BLUE}▶ 6.5/7 — List pending_reviews (DO NOT auto-approve)${NC}"
uv run ai-team list-pending | head -40

echo ""
echo "Owner: review docs/products/$SLUG/_validation_summary.md, then approve with"
echo "   uv run ai-team approve <id> --comment 'decision: go|pivot|kill — <rationale>'"

echo ""
echo -e "${BOLD_BLUE}▶ 7/7 — Collect demo report${NC}"
REPORT="$LOG_DIR/demo_report_${TIMESTAMP}.md"
{
    echo "# iter-26b demo report — $TIMESTAMP"
    echo
    echo "- slug: $SLUG"
    echo "- depth: $DEPTH"
    echo "- correlation: $CORRELATION"
    echo "- audit_rows: $FINAL_AUDIT"
    echo "- qa_reviews_pending: $QA_REVIEWS"
    echo
    echo "## Recommendation preview"
    grep -E '^recommendation: ' "docs/products/$SLUG/_validation_summary.md" 2>/dev/null || echo "  (no _validation_summary.md found yet)"
    echo
    echo "## Artifacts"
    ls -la "docs/products/$SLUG/" 2>/dev/null || echo "  (no per-candidate dir)"
} > "$REPORT"
echo "==> Report: $REPORT"
echo "API log preserved: $API_LOG"
```

Stdin EOF safety carries over from iter-26a (the no-read variant above already avoids stdin reads).

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/demo_iter_26b.sh
```

- [ ] **Step 3: Verify bash syntax**

```bash
bash -n scripts/demo_iter_26b.sh && echo OK
```
Expected: `OK`.

- [ ] **Step 4: Commit**

```bash
git add scripts/demo_iter_26b.sh
git commit -m "feat(iter-26b): demo script (validate-product end-to-end)"
```

---

## Task 11: CLAUDE.md update — flag new CLI + per-candidate dir

One paragraph in "Where to look" + one line in the agents/CLI section.

**Files:**
- Modify: `CLAUDE.md`.

- [ ] **Step 1: Update `docs/products/_candidates/` paragraph in "Where to look"**

Find the existing `docs/products/_candidates/` block (added in iter-26a) and append:

```markdown
docs/products/<slug>/        # iter-26b: per-candidate diligence
                             # outputs. competitors.md (MR),
                             # tech_risk.md (Architect), revenue.md
                             # (PM), _validation_summary.md (QA) +
                             # owner-approved pending_review payload
                             # with go|pivot|kill recommendation.
                             # Per-candidate dir is the staging ground
                             # between brainstorm and iter-27 build.
```

- [ ] **Step 2: Add `ai-team validate-product` to the CLI list** (if there is one — otherwise mention it in the Make targets section)

Add a line near the `ai-team brainstorm-products` mention:

```
ai-team validate-product --slug <slug> --candidate-file <md> --depth standard
  # iter-26b: single-candidate diligence via 4-agent chain.
  # ~$8-14 spend, ~15-25 min wall-clock at depth=standard.
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(iter-26b): CLAUDE.md flags per-candidate diligence dir + CLI"
```

---

## Task 12: Run the demo end-to-end (owner-manual)

The acceptance criterion for iter-26b is a full real-LLM run that produces all 4 artifacts and a structured pending_review the owner approves.

**Files:**
- None modified. This is validation.

- [ ] **Step 1: Verify CI-equivalent suite green locally**

```bash
make lint && make typecheck && make sec
uv run pytest tests/unit -v
uv run pytest tests/integration --integration -v
```
Expected: all green.

- [ ] **Step 2: Make smoke-llm**

```bash
make smoke-llm
```
Expected: green.

- [ ] **Step 3: Owner runs the demo**

```bash
./scripts/demo_iter_26b.sh telegram-tech-publisher standard
```

Expected (~15-25 min wall clock, ~$8-14 spend):
- `docs/products/telegram-tech-publisher/competitors.md` exists
- `docs/products/telegram-tech-publisher/tech_risk.md` exists
- `docs/products/telegram-tech-publisher/revenue.md` exists
- `docs/products/telegram-tech-publisher/_validation_summary.md` exists with `recommendation:` YAML field
- `audit_log` rows for the full 5-stage chain (TL decomp + 3 upstream task_reports + 1 QA task_report)
- ≥ 1 (and probably 2) `pending_reviews` rows for `qa_engineer` with the structured payload

- [ ] **Step 4: Owner inspects the QA recommendation**

```bash
cat docs/products/telegram-tech-publisher/_validation_summary.md
uv run ai-team list-pending
```

- [ ] **Step 5: Owner approves with the decision**

```bash
uv run ai-team approve <pending_review_id> --comment "decision: <go|pivot|kill> — <rationale>"
```

- [ ] **Step 6: Commit the artifacts**

```bash
git add docs/products/telegram-tech-publisher/ docs/iterations/iter_26b_demo_logs/
git commit -m "chore(iter-26b): record validation artifacts + demo report"
```

API logs are gitignored (`*.log` glob); the demo report markdown is committed.

- [ ] **Step 7: If recommendation is `go` — open the door to iter-27**

Update `project_ai_team.md` auto-memory: "iter-26b validated `telegram-tech-publisher` → iter-27 build approved in separate repo per ADR-009."

If recommendation is `pivot` — update memory and prepare to re-run iter-26b' on the next slug.

If recommendation is `kill` — update memory and return to iter-26a with adjusted niches/constraints.

---

## Final sanity checklist (run after all tasks done)

- [ ] All 12 tasks marked complete.
- [ ] `git log --oneline` shows one commit per task (12 commits, plus the artifact commit).
- [ ] `make lint && make typecheck && make sec` clean.
- [ ] Unit + integration tests green (mocked LLM).
- [ ] `make smoke-llm` passes.
- [ ] Demo script ran end-to-end; 4 artifacts produced; pending_review approved.
- [ ] `project_ai_team.md` updated with iter-26b outcome.

---

## Notes for the executor

- **Reuse iter-26a's patterns ruthlessly.** Every architectural decision in this iteration (intent dispatch, deterministic agent-side renders, monkeypatched dirs in tests, structured `pending_review` payloads, `*.log` gitignore, owner-manual demo) has a direct precedent in iter-26a code that landed in commits `2817888` through `542168a`. When in doubt, find the matching iter-26a code path and mirror it.
- **Architect and PM gain intent dispatch for the first time.** Mirror MR's pattern (which already has 2 intents) verbatim — don't invent a new dispatch shape.
- **`max_budget_usd` bumps are not optional.** Every agent's default trips. If a real-LLM run returns `BLOCKED(budget)` with `total_cost_usd` near the cap, the bump didn't land. Verify with the dispatch tests.
- **The `fatal_flaws ⇒ {kill, pivot}` invariant is enforced in Python, not in JSON schema.** Don't try to encode it in the schema; the spec covers why.
- **No new agent classes. No new bus/dispatch/audit work.** Spec §3 is firm.
- **The dispatcher per-role serialization issue does not apply here** because the 3 parallel subtasks target 3 different roles. If a future iteration validates multiple candidates of the same role in parallel, the issue resurfaces — defer it to stabilization.
- **Owner controls the demo run timing.** Do not run `./scripts/demo_iter_26b.sh` yourself unless explicitly instructed; it costs $8-14 and takes 15-25 min.
- **Branch hygiene**: this plan ships on a new branch (e.g., `iter-26b-validator`). Do not extend the iter-26a branch; that one is closed.
