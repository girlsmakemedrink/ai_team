# Iter-26a Implementation Plan — MR brainstorm-niche

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend Market Researcher with a parallel-decomposed `brainstorm-niche` mode that produces 15 scored monetizable product candidates (5 per niche × 3 niches) for owner review, exercising the framework on a research shape of work for the first time.

**Architecture:** TL receives one root `task_assignment` with `inputs.intent = "brainstorm_products"`, decomposes into 3 parallel MR sub-tasks (one per niche). Each MR uses a new `brainstorm-niche` mode keyed by `inputs.mode`, runs `WebFetch` for 3-5 evidence pages, emits 5 candidates scored on 5 axes, writes a Markdown artifact to a new `docs/products/_candidates/` surface, and returns the validated JSON in metadata. After all 3 MR `task_report`s come back `DONE`, TL routes a single QA task with `inputs.intent = "rank_brainstorm_candidates"`. QA merges, schema-validates, ranks, writes `_combined_ranking.md`, emits `request_human_review`. Owner approves with a top-3 slug comment that seeds iter-26b.

**Tech Stack:** Python 3.11, Pydantic v2 (`extra="forbid"`), Click (CLI), FastAPI (API), pytest + pytest-asyncio + testcontainers (tests), `claude -p` subprocess via `ClaudeCodeHeadlessClient`, `MockLLMClient` for unit/integration tests, `BRAINSTORM_NICHE_SCHEMA` enforced via `--json-schema`. No new dependencies.

**Source spec:** `docs/superpowers/specs/2026-05-22-iter-26a-mr-brainstorm-design.md` (commit `eac7818`).

---

## File Structure

**Modified:**
- `apps/api/main.py` — `SubmitTaskRequest` gains `inputs: dict[str, Any] | None`; passed to `TaskAssignmentPayload`.
- `apps/cli/main.py` — `submit` gains `--inputs-json` option; new `brainstorm-products` sub-command (~30 lines).
- `agents/market_researcher/agent.py` — `BRAINSTORM_NICHE_SCHEMA` constant + `_render_brainstorm_markdown()` helper + mode dispatch in `handle()` + `build_outputs()` branch + path-prefix env update.
- `prompts/market_researcher.md` — `Workflow: brainstorm-niche mode` section.
- `prompts/team_lead.md` — `Intent: brainstorm_products` section.
- `agents/qa_engineer/agent.py` — intent dispatch in `handle()` + `build_outputs()` rank-brainstorm branch + ranking-file writer.
- `prompts/qa_engineer.md` — `Intent: rank_brainstorm_candidates` section.
- `CLAUDE.md` — one paragraph in "Where to look" pointing at `docs/products/_candidates/`.

**Created:**
- `scripts/preflight_quota_check.sh` — `claude -p` ping; exits non-zero with reset-time message on 429.
- `scripts/demo_iter_26a.sh` — orchestrates the full demo: preflight → `make up` → submit → 15-min poll → 60s drain → SQL + artifact dump.
- `scripts/iter_26a_constraints.json` — default `--constraints-json` payload.
- `tests/unit/test_market_researcher_brainstorm_mode.py`
- `tests/unit/test_team_lead_brainstorm_decomposition.py`
- `tests/unit/test_qa_rank_brainstorm.py`
- `tests/integration/test_iter_26a_e2e_brainstorm.py`
- `tests/real_llm/test_mr_brainstorm_one_niche.py`

**Files NOT touched** (out of scope; spec section 12): HoldQueue persistence, GitHubTargetRepo, `BaseAgent.handle()` refactor, `mark_task_done`/`update_task_status` real impls, hash-chain alert job.

---

## Task 1: Plumb `inputs` through API + CLI submit

Foundation work — `TaskAssignmentPayload.inputs: dict[str, Any]` already exists in `core/messaging/schemas.py:72`, but `apps/api/main.py:217` and `apps/cli/main.py:212` don't accept/pass it. Without this, the new `brainstorm-products` command has nowhere to put `intent`, `niches`, `constraints`.

**Files:**
- Modify: `apps/api/main.py:199` (`SubmitTaskRequest`) and `apps/api/main.py:244` (`TaskAssignmentPayload` construction).
- Modify: `apps/cli/main.py:207-237` (`submit` command).
- Test: `tests/unit/test_api_submit_task_inputs.py` (create).

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_api_submit_task_inputs.py`:

```python
"""SubmitTaskRequest must accept and forward an optional `inputs` dict
so brainstorm-products (and future structured-intent flows) can pass
typed metadata to TL without encoding it in description text."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.main import SubmitTaskRequest


def test_inputs_default_is_none() -> None:
    req = SubmitTaskRequest(title="t", description="d")
    assert req.inputs is None


def test_inputs_accepts_dict_with_nested_values() -> None:
    payload = {
        "intent": "brainstorm_products",
        "niches": ["dev_tools", "b2b_smb"],
        "candidates_per_niche": 5,
        "constraints": {"solo_developer": True, "ttfr_max_months": 6},
    }
    req = SubmitTaskRequest(title="t", description="d", inputs=payload)
    assert req.inputs == payload


def test_inputs_rejects_non_dict() -> None:
    with pytest.raises(ValidationError):
        SubmitTaskRequest(title="t", description="d", inputs=["not", "a", "dict"])
```

- [ ] **Step 2: Run test, verify it fails**

```bash
uv run pytest tests/unit/test_api_submit_task_inputs.py -v
```
Expected: `FAILED` — `SubmitTaskRequest` has no `inputs` field; `test_inputs_accepts_dict_with_nested_values` fails with `unexpected keyword argument 'inputs'` (Pydantic `extra="forbid"`) or extra-fields error.

- [ ] **Step 3: Add `inputs` to SubmitTaskRequest**

In `apps/api/main.py` around line 199, change:

```python
class SubmitTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    target_repo: str | None = None
    priority: Priority = Priority.P2
```

to:

```python
class SubmitTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    target_repo: str | None = None
    priority: Priority = Priority.P2
    inputs: dict[str, Any] | None = None
```

Ensure `from typing import Any` is imported at the top of the file (probably already is — confirm).

- [ ] **Step 4: Forward inputs into TaskAssignmentPayload**

In `apps/api/main.py` around line 244, change:

```python
        payload=TaskAssignmentPayload(
            task_id=task_id,
            title=req.title,
            description=req.description,
            target_repo=req.target_repo,
        ),
```

to:

```python
        payload=TaskAssignmentPayload(
            task_id=task_id,
            title=req.title,
            description=req.description,
            target_repo=req.target_repo,
            inputs=req.inputs or {},
        ),
```

- [ ] **Step 5: Run test, verify it passes**

```bash
uv run pytest tests/unit/test_api_submit_task_inputs.py -v
```
Expected: all 3 pass.

- [ ] **Step 6: Extend CLI submit with --inputs-json**

In `apps/cli/main.py` around line 207, add the option and forward it:

```python
@cli.command()
@click.option("--title", required=True, help="Task title.")
@click.option("--description", required=True, help="Task description.")
@click.option("--target-repo", default=None, help="Override TARGET_REPO (default: ai_team itself).")
@click.option(
    "--inputs-json",
    default=None,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to a JSON file passed as TaskAssignmentPayload.inputs.",
)
@click.pass_context
def submit(
    ctx: click.Context,
    title: str,
    description: str,
    target_repo: str | None,
    inputs_json: str | None,
) -> None:
    """Submit a new task to the Team Lead."""
    body: dict[str, Any] = {"title": title, "description": description}
    if target_repo:
        body["target_repo"] = target_repo
    if inputs_json:
        with open(inputs_json) as f:
            body["inputs"] = json.load(f)

    resp = httpx.post(
        f"{_api_base(ctx)}/api/tasks",
        json=body,
        headers=_token_header(ctx),
        timeout=30.0,
    )
    # ...rest unchanged
```

Ensure `import json` is at the top of the file (likely already imported — confirm with `grep "^import json" apps/cli/main.py`; add if missing).

- [ ] **Step 7: Sanity-check via lint + mypy**

```bash
uv run ruff check apps/api/main.py apps/cli/main.py tests/unit/test_api_submit_task_inputs.py
uv run mypy apps/api/main.py apps/cli/main.py
```
Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add apps/api/main.py apps/cli/main.py tests/unit/test_api_submit_task_inputs.py
git commit -m "feat(iter-26a): API+CLI submit accepts inputs dict — foundation for brainstorm-products"
```

---

## Task 2: BRAINSTORM_NICHE_SCHEMA + markdown renderer in MR

Pure data + rendering. No LLM. TDD-friendly.

**Files:**
- Modify: `agents/market_researcher/agent.py` — add `BRAINSTORM_NICHE_SCHEMA` constant and `_render_brainstorm_markdown()` helper next to existing `MARKET_SCAN_SCHEMA` and `_render_scan_markdown()`.
- Test: `tests/unit/test_market_researcher_brainstorm_schema.py` (create).

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_market_researcher_brainstorm_schema.py`:

```python
"""BRAINSTORM_NICHE_SCHEMA + renderer for the brainstorm-niche mode."""

from __future__ import annotations

import jsonschema
import pytest

from agents.market_researcher.agent import (
    BRAINSTORM_NICHE_SCHEMA,
    _render_brainstorm_markdown,
)


def _valid_brainstorm() -> dict[str, object]:
    candidate = {
        "title": "AI commit-message generator",
        "slug": "ai-commit-message-generator",
        "one_paragraph": "Reads `git diff --staged`, emits Conventional Commit messages via a local model.",
        "target_buyer": "Solo developers and small dev teams.",
        "monetization": "subscription",
        "known_competitors": [
            {"name": "Co-author Pro", "url": "https://example.com", "positioning": "JetBrains plugin"}
        ],
        "scores": {
            "tam_signal": 4,
            "solo_fit": 5,
            "llm_opex_fit": 4,
            "defensibility": 2,
            "time_to_first_revenue": 4,
        },
        "composite_score": 19,
        "rationale": "Strong solo fit; weak moat.",
    }
    return {
        "niche": "dev_tools",
        "candidates": [dict(candidate, slug=f"cand-{i}") for i in range(5)],
        "researcher_top_3_slugs": ["cand-0", "cand-1", "cand-2"],
        "research_sources_used": ["https://news.ycombinator.com/item?id=1"],
    }


def test_valid_brainstorm_passes_schema() -> None:
    jsonschema.validate(_valid_brainstorm(), BRAINSTORM_NICHE_SCHEMA)


def test_unknown_niche_rejected() -> None:
    bad = _valid_brainstorm()
    bad["niche"] = "fintech"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_four_candidates_rejected() -> None:
    bad = _valid_brainstorm()
    bad["candidates"] = bad["candidates"][:4]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_composite_score_out_of_range_rejected() -> None:
    bad = _valid_brainstorm()
    bad["candidates"][0]["composite_score"] = 26
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_score_axis_out_of_range_rejected() -> None:
    bad = _valid_brainstorm()
    bad["candidates"][0]["scores"]["tam_signal"] = 6
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, BRAINSTORM_NICHE_SCHEMA)


def test_render_brainstorm_markdown_contains_each_candidate_title() -> None:
    md = _render_brainstorm_markdown(_valid_brainstorm())
    assert "# Brainstorm — dev_tools" in md
    assert "## Researcher top-3" in md
    for cand in _valid_brainstorm()["candidates"]:
        assert cand["title"] in md
    assert "https://news.ycombinator.com" in md
```

- [ ] **Step 2: Run test, verify it fails**

```bash
uv run pytest tests/unit/test_market_researcher_brainstorm_schema.py -v
```
Expected: ImportError — `BRAINSTORM_NICHE_SCHEMA` and `_render_brainstorm_markdown` are not defined yet.

- [ ] **Step 3: Add schema + renderer**

In `agents/market_researcher/agent.py`, after the existing `MARKET_SCAN_SCHEMA` block (around line 77), add:

```python
BRAINSTORM_NICHE_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": [
        "niche",
        "candidates",
        "researcher_top_3_slugs",
        "research_sources_used",
    ],
    "additionalProperties": False,
    "properties": {
        "niche": {
            "type": "string",
            "enum": ["dev_tools", "b2b_smb", "creator_tools"],
        },
        "candidates": {
            "type": "array",
            "minItems": 5,
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": [
                    "title", "slug", "one_paragraph", "target_buyer",
                    "monetization", "known_competitors", "scores",
                    "composite_score", "rationale",
                ],
                "additionalProperties": False,
                "properties": {
                    "title":         {"type": "string", "minLength": 1, "maxLength": 120},
                    "slug":          {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
                    "one_paragraph": {"type": "string", "minLength": 1, "maxLength": 1500},
                    "target_buyer":  {"type": "string", "minLength": 1, "maxLength": 300},
                    "monetization": {
                        "type": "string",
                        "enum": ["subscription", "per-seat", "usage", "one-time", "freemium"],
                    },
                    "known_competitors": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "positioning"],
                            "additionalProperties": False,
                            "properties": {
                                "name":        {"type": "string"},
                                "url":         {"type": "string"},
                                "positioning": {"type": "string"},
                            },
                        },
                    },
                    "scores": {
                        "type": "object",
                        "required": [
                            "tam_signal", "solo_fit", "llm_opex_fit",
                            "defensibility", "time_to_first_revenue",
                        ],
                        "additionalProperties": False,
                        "properties": {
                            "tam_signal":            {"type": "integer", "minimum": 1, "maximum": 5},
                            "solo_fit":              {"type": "integer", "minimum": 1, "maximum": 5},
                            "llm_opex_fit":          {"type": "integer", "minimum": 1, "maximum": 5},
                            "defensibility":         {"type": "integer", "minimum": 1, "maximum": 5},
                            "time_to_first_revenue": {"type": "integer", "minimum": 1, "maximum": 5},
                        },
                    },
                    "composite_score": {"type": "integer", "minimum": 5, "maximum": 25},
                    "rationale":       {"type": "string", "minLength": 1, "maxLength": 1500},
                },
            },
        },
        "researcher_top_3_slugs": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
        },
        "research_sources_used": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


def _render_brainstorm_markdown(scan: dict[str, Any]) -> str:
    """Render BRAINSTORM_NICHE_SCHEMA output to human-readable Markdown."""
    lines: list[str] = [
        f"# Brainstorm — {scan['niche']}",
        "",
        f"- **Status**: Draft (Market Researcher; pending owner approval)",
        f"- **Candidates**: {len(scan['candidates'])}",
        "",
        "## Researcher top-3",
        "",
    ]
    by_slug = {c["slug"]: c for c in scan["candidates"]}
    for slug in scan["researcher_top_3_slugs"]:
        cand = by_slug.get(slug)
        if cand is None:
            lines.append(f"- [missing slug in candidates: `{slug}`]")
        else:
            lines.append(f"- **{cand['title']}** (`{slug}`) — composite {cand['composite_score']}/25")
    lines.append("")
    lines.append("## All candidates")
    lines.append("")
    for cand in scan["candidates"]:
        lines.append(f"### {cand['title']} (`{cand['slug']}`)")
        lines.append("")
        lines.append(cand["one_paragraph"].strip())
        lines.append("")
        lines.append(f"- **Target buyer**: {cand['target_buyer']}")
        lines.append(f"- **Monetization**: {cand['monetization']}")
        s = cand["scores"]
        lines.append(
            f"- **Scores**: TAM {s['tam_signal']} · solo {s['solo_fit']} · "
            f"LLM-OPEX {s['llm_opex_fit']} · defensibility {s['defensibility']} · "
            f"TTFR {s['time_to_first_revenue']} → composite {cand['composite_score']}/25"
        )
        lines.append("")
        if cand["known_competitors"]:
            lines.append("- **Known competitors**:")
            for comp in cand["known_competitors"]:
                url = f" ({comp.get('url')})" if comp.get("url") else ""
                lines.append(f"  - {comp['name']}{url}: {comp['positioning']}")
        lines.append("")
        lines.append(f"_Rationale_: {cand['rationale'].strip()}")
        lines.append("")
    lines.append("## Sources consulted")
    lines.append("")
    for src in scan["research_sources_used"]:
        lines.append(f"- {src}")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test, verify it passes**

```bash
uv run pytest tests/unit/test_market_researcher_brainstorm_schema.py -v
```
Expected: 6/6 pass.

- [ ] **Step 5: Lint + typecheck**

```bash
uv run ruff check agents/market_researcher/agent.py tests/unit/test_market_researcher_brainstorm_schema.py
uv run mypy agents/market_researcher/agent.py
```

- [ ] **Step 6: Commit**

```bash
git add agents/market_researcher/agent.py tests/unit/test_market_researcher_brainstorm_schema.py
git commit -m "feat(iter-26a): BRAINSTORM_NICHE_SCHEMA + markdown renderer in MR"
```

---

## Task 3: MR brainstorm-niche dispatch (handle + build_outputs + path scope)

Add mode-keyed branching so the same agent can do either a single-idea scan (existing) or a niche-brainstorm (new). Extend the path-prefix env so MR can write to `docs/products/_candidates/`.

**Files:**
- Modify: `agents/market_researcher/agent.py` — `handle()` selects schema by `inputs.mode`; `build_outputs()` selects renderer + destination by mode; `mcp_env["AI_TEAM_PATH_PREFIXES"]` adds `docs/products`.
- Test: `tests/unit/test_market_researcher_brainstorm_mode.py` (create).

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_market_researcher_brainstorm_mode.py`:

```python
"""End-to-end mode-dispatch in MR's handle() + build_outputs()."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from agents.market_researcher.agent import MarketResearcherAgent
from core.llm.mock import MockLLMClient, ScriptedResponse
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskStatus,
)


def _brainstorm_response(niche: str) -> dict[str, object]:
    cand = lambda i: {  # noqa: E731
        "title": f"{niche.title()} idea {i}",
        "slug": f"{niche}-idea-{i}",
        "one_paragraph": "x" * 30,
        "target_buyer": "y",
        "monetization": "subscription",
        "known_competitors": [{"name": "C", "positioning": "p"}],
        "scores": {
            "tam_signal": 3, "solo_fit": 3, "llm_opex_fit": 3,
            "defensibility": 3, "time_to_first_revenue": 3,
        },
        "composite_score": 15,
        "rationale": "r",
    }
    return {
        "niche": niche,
        "candidates": [cand(i) for i in range(5)],
        "researcher_top_3_slugs": [f"{niche}-idea-{i}" for i in range(3)],
        "research_sources_used": ["https://example.com/a"],
    }


def _assignment(niche: str, mode: str | None = "brainstorm_niche") -> AgentMessage:
    inputs: dict[str, object] = {"niche": niche, "candidates": 5, "constraints": {}}
    if mode is not None:
        inputs["mode"] = mode
    return AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title=f"Brainstorm {niche}",
            description="Brainstorm 5 candidates",
            inputs=inputs,
        ),
    )


@pytest.mark.asyncio
async def test_brainstorm_mode_writes_to_products_candidates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Redirect _REPO_ROOT for test so writes go to tmp_path.
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._BRAINSTORM_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    llm = MockLLMClient(responses=[ScriptedResponse(structured=_brainstorm_response("dev_tools"))])
    agent = MarketResearcherAgent(llm=llm)
    msg = _assignment("dev_tools")

    outputs = await agent.handle(msg)

    assert len(outputs) == 1
    report = outputs[0].payload
    assert report.status == TaskStatus.DONE
    assert any("_brainstorm_dev_tools.md" in a for a in report.artifacts)

    written = (tmp_path / "docs" / "products" / "_candidates" / "_brainstorm_dev_tools.md").read_text()
    assert "Brainstorm — dev_tools" in written


@pytest.mark.asyncio
async def test_brainstorm_mode_invalid_schema_fails_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._BRAINSTORM_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    # researcher_top_3_slugs references a slug NOT in candidates — cross-validation guard.
    bad = _brainstorm_response("dev_tools")
    bad["researcher_top_3_slugs"] = ["does-not-exist", "x", "y"]
    llm = MockLLMClient(responses=[ScriptedResponse(structured=bad)])
    agent = MarketResearcherAgent(llm=llm)

    outputs = await agent.handle(_assignment("dev_tools"))

    assert outputs[0].payload.status == TaskStatus.FAILED
    assert "top_3" in outputs[0].payload.summary.lower() or "slug" in outputs[0].payload.summary.lower()


@pytest.mark.asyncio
async def test_single_scan_mode_still_works(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression — the existing single-scan mode must keep working when mode is absent."""
    monkeypatch.setattr("agents.market_researcher.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.market_researcher.agent._IDEAS_DIR",
        tmp_path / "docs" / "sandbox" / "ideas",
    )

    scan = {
        "title": "Single-scan probe",
        "slug": "single-scan-probe",
        "summary": "short",
        "competitors": [],
        "market_size": "n/a",
        "top_risks": ["r1"],
        "top_opportunities": ["o1"],
        "viability_score": 5,
        "score_rationale": "ok",
    }
    llm = MockLLMClient(responses=[ScriptedResponse(structured=scan)])
    agent = MarketResearcherAgent(llm=llm)

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Scan one idea",
            description="Scan",
            inputs={},  # no mode = single-scan
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs[0].payload.status == TaskStatus.DONE
    assert (tmp_path / "docs" / "sandbox" / "ideas" / "single-scan-probe.md").exists()
```

> **Note for the executor:** Read the existing `MockLLMClient` + `ScriptedResponse` API before writing these tests — adjust import paths and constructor args to match. If `MockLLMClient` exposes a different interface, use it; the assertions above are the contract.

- [ ] **Step 2: Run test, verify it fails**

```bash
uv run pytest tests/unit/test_market_researcher_brainstorm_mode.py -v
```
Expected: FAIL — `_BRAINSTORM_DIR` not defined, dispatch returns the wrong status, etc.

- [ ] **Step 3: Add `_BRAINSTORM_DIR` constant + path-prefix env update**

In `agents/market_researcher/agent.py`, near the existing `_IDEAS_DIR` constant:

```python
_BRAINSTORM_DIR: Path = _REPO_ROOT / "docs" / "products" / "_candidates"
```

And update `mcp_env` on `MarketResearcherAgent`:

```python
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "docs/sandbox/ideas,docs/market,docs/products",
    }
```

- [ ] **Step 4: Refactor `handle()` to dispatch on `inputs.mode`**

Replace the existing `handle()` body in `agents/market_researcher/agent.py` (around line 181):

```python
    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type != MessageType.TASK_ASSIGNMENT:
            return []
        assert isinstance(msg.payload, TaskAssignmentPayload)
        mode = (msg.payload.inputs or {}).get("mode")
        schema = (
            BRAINSTORM_NICHE_SCHEMA if mode == "brainstorm_niche" else MARKET_SCAN_SCHEMA
        )
        response = await self._llm.invoke(
            system_prompt=self.system_prompt(),
            user_message=self._user_message_for(msg),
            model=self.model_tier,
            allowed_tools=self.allowed_tools,
            session_id=str(msg.payload.task_id),  # per-task isolation for parallel runs
            timeout_s=self.llm_timeout_s,
            max_turns=self.max_turns,
            json_schema=schema,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        return self._stamp_metrics(self.build_outputs(response, msg), response)
```

> **Note for the executor:** This switches `session_id` from `correlation_id` to `task_id` ONLY for MR. Verify by skimming `core/llm/claude_code_headless.py:_claimed_sessions` that this is safe under parallel runs. If `_claimed_sessions` is per-adapter-instance and the dispatcher shares one adapter across agents, this prevents collision between the 3 parallel MRs (they have different task_ids). The other agents (PM/Architect/Backend/QA) keep `session_id=correlation_id` because they run sequentially within a single chain. Cite the iter-2c demo as prior art for parallel agent runs with the current adapter; if the iter-2c test fixture used different session keys, mirror that.

- [ ] **Step 5: Refactor `build_outputs()` to dispatch on mode**

Replace the existing `build_outputs()` in `agents/market_researcher/agent.py` (around line 141):

```python
    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []
        mode = (incoming.payload.inputs or {}).get("mode")
        if mode == "brainstorm_niche":
            return self._build_brainstorm_outputs(response, incoming)
        return self._build_scan_outputs(response, incoming)

    def _build_scan_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        # ...existing body of build_outputs goes here, unchanged...
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        scan = response.structured
        if not scan or "title" not in scan or "slug" not in scan:
            return [self._fail(incoming, "LLM did not return a parseable market scan")]

        slug = str(scan["slug"])
        if not _SLUG_RE.match(slug):
            return [self._fail(incoming, f"invalid slug {slug!r}")]

        filename = f"{slug}.md"
        try:
            _IDEAS_DIR.mkdir(parents=True, exist_ok=True)
            (_IDEAS_DIR / filename).write_text(_render_scan_markdown(scan))
        except OSError as e:
            return [self._fail(incoming, f"failed to write market scan: {e}")]

        artifact_rel = f"docs/sandbox/ideas/{filename}"
        score = scan.get("viability_score", "?")
        summary = f"{scan['title']} — viability {score}/10"
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=AgentId.MARKET_RESEARCHER,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=incoming.priority,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=summary,
                    artifacts=[artifact_rel],
                ),
            )
        ]

    def _build_brainstorm_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        scan = response.structured
        if not scan or "niche" not in scan or "candidates" not in scan:
            return [self._fail(incoming, "LLM did not return a parseable brainstorm")]

        niche = str(scan["niche"])
        candidates = scan.get("candidates") or []
        candidate_slugs = {c.get("slug") for c in candidates}
        top_3 = scan.get("researcher_top_3_slugs") or []
        if not set(top_3).issubset(candidate_slugs):
            missing = set(top_3) - candidate_slugs
            return [self._fail(incoming, f"researcher_top_3 references unknown slugs: {sorted(missing)}")]

        # composite_score must equal sum of axes (spec section 8 #2)
        for cand in candidates:
            scores = cand.get("scores") or {}
            expected = sum(scores.get(k, 0) for k in (
                "tam_signal", "solo_fit", "llm_opex_fit",
                "defensibility", "time_to_first_revenue",
            ))
            if cand.get("composite_score") != expected:
                return [self._fail(
                    incoming,
                    f"composite_score mismatch for {cand.get('slug')!r}: "
                    f"got {cand.get('composite_score')}, expected sum {expected}",
                )]

        filename = f"_brainstorm_{niche}.md"
        try:
            _BRAINSTORM_DIR.mkdir(parents=True, exist_ok=True)
            (_BRAINSTORM_DIR / filename).write_text(_render_brainstorm_markdown(scan))
        except OSError as e:
            return [self._fail(incoming, f"failed to write brainstorm: {e}")]

        artifact_rel = f"docs/products/_candidates/{filename}"
        top_titles = ", ".join(
            next(c["title"] for c in candidates if c["slug"] == s) for s in top_3
        )
        summary = f"Brainstorm {niche}: 5 candidates; researcher top-3: {top_titles}"
        return [
            AgentMessage(
                correlation_id=incoming.correlation_id,
                sender=AgentId.MARKET_RESEARCHER,
                recipient=AgentId.TEAM_LEAD,
                message_type=MessageType.TASK_REPORT,
                priority=incoming.priority,
                payload=TaskReportPayload(
                    task_id=incoming.payload.task_id,
                    status=TaskStatus.DONE,
                    progress_pct=100,
                    summary=summary[:2_000],
                    artifacts=[artifact_rel],
                ),
            )
        ]
```

- [ ] **Step 6: Run all MR tests**

```bash
uv run pytest tests/unit/test_market_researcher_brainstorm_mode.py tests/unit/test_market_researcher_brainstorm_schema.py -v
```
Expected: all pass.

- [ ] **Step 7: Run pre-existing MR tests to confirm no regression**

```bash
uv run pytest tests/unit/test_market_researcher_agent.py -v  # if present; if not, grep for any test_market_researcher_*.py
```
Expected: pass.

- [ ] **Step 8: Lint + typecheck**

```bash
uv run ruff check agents/market_researcher/
uv run mypy agents/market_researcher/agent.py
```

- [ ] **Step 9: Commit**

```bash
git add agents/market_researcher/agent.py tests/unit/test_market_researcher_brainstorm_mode.py
git commit -m "feat(iter-26a): MR mode dispatch — brainstorm-niche branch + path scope"
```

---

## Task 4: MR prompt — brainstorm-niche workflow

Markdown change to `prompts/market_researcher.md`. No code, no test code — prompt correctness validated downstream in real_llm test (Task 10) and demo (Task 12).

**Files:**
- Modify: `prompts/market_researcher.md`.

- [ ] **Step 1: Append the new workflow section**

At the end of `prompts/market_researcher.md`, before the final newline:

```markdown

## Workflow: brainstorm-niche mode

Selected when the incoming task_assignment has
`inputs.mode == "brainstorm_niche"`. The inputs you receive:

- `niche` — one of `dev_tools`, `b2b_smb`, `creator_tools`.
- `candidates` — integer, expected to be 5.
- `constraints` — structured object, e.g.:
  ```json
  {
    "solo_developer": true,
    "max_product_llm_opex_usd_per_day": 3,
    "monetization_preferences": ["subscription", "per-seat", "usage"],
    "max_time_to_first_revenue_months": 6,
    "defensibility_floor": "minimal moat acceptable; user-distribution moat ok",
    "owner_expertise_hint": "..."
  }
  ```

### Steps

1. `WebFetch` 3–5 plausibly relevant pages (vendor sites, complaint
   forums, Reddit / Indie Hackers, "what's missing in X" articles).
   Failures (paywall, captcha, empty body) — log and continue with
   the remaining sources. Cite every URL you actually used in
   `research_sources_used`.
2. Generate **exactly 5 distinguishable candidates** in this niche.
   Five variations of one idea is wrong — they must differ in target
   buyer, monetization, or core mechanic.
3. Every candidate MUST respect the constraints. A candidate that
   needs 3 engineers and 12 months violates
   `solo_developer + max_time_to_first_revenue_months: 6` and must
   not be proposed.
4. Score every candidate on five axes (1–5 each):
   - `tam_signal` — evidence of paying demand?
   - `solo_fit` — can one developer ship in the time budget?
   - `llm_opex_fit` — steady-state LLM cost per user fits
     `max_product_llm_opex_usd_per_day`?
   - `defensibility` — distribution, data, workflow lock-in?
   - `time_to_first_revenue` — 5 ⇒ TTFR ≤ ceiling; 1 ⇒ > 2× ceiling.
5. **Compute `composite_score` as the integer sum** of the five
   axes. The downstream agent validates this — a mismatch fails the
   task.
6. Pick your top-3 by `composite_score` desc (ties: defensibility,
   then solo_fit). Put those 3 slugs in `researcher_top_3_slugs`.
   They MUST be slugs that exist in your `candidates`.
7. Write the Markdown file via `write_file_in_scope` to
   `docs/products/_candidates/_brainstorm_<niche>.md`. The renderer
   is deterministic — just produce the JSON; the agent code writes
   the file.

### What you produce (JSON only, validated by --json-schema)

```json
{
  "niche": "<one of dev_tools|b2b_smb|creator_tools>",
  "candidates": [
    {
      "title": "<≤120 chars>",
      "slug": "kebab-case",
      "one_paragraph": "<≤1500 chars>",
      "target_buyer": "<≤300 chars>",
      "monetization": "<subscription|per-seat|usage|one-time|freemium>",
      "known_competitors": [{"name": "...", "url": "...", "positioning": "..."}],
      "scores": {
        "tam_signal": 1-5, "solo_fit": 1-5, "llm_opex_fit": 1-5,
        "defensibility": 1-5, "time_to_first_revenue": 1-5
      },
      "composite_score": <sum of the five axes>,
      "rationale": "<≤1500 chars, one paragraph>"
    }
    // ...exactly 5 candidates
  ],
  "researcher_top_3_slugs": ["...", "...", "..."],
  "research_sources_used": ["https://...", "..."]
}
```

### Discipline (brainstorm-niche mode)

- Respond with JSON only. No prose outside the JSON.
- WebFetch must be used at least once. A brainstorm with no sources
  is rejected by the owner during review.
- Slug pattern: `^[a-z0-9]+(-[a-z0-9]+)*$`. No spaces, no underscores.
- "I don't know" `target_buyer` is unacceptable; if you can't name a
  buyer, the candidate doesn't belong on the list.
```

- [ ] **Step 2: Commit**

```bash
git add prompts/market_researcher.md
git commit -m "docs(iter-26a): MR prompt — brainstorm-niche workflow section"
```

---

## Task 5: TL prompt — brainstorm_products intent

Decomposition is prompt-driven in this codebase (see `agents/team_lead/agent.py:DECOMPOSITION_SCHEMA` — TL emits structured subtasks; the LLM decides recipients/depends_on). No agent-code change needed; the new intent lives entirely in the prompt.

**Files:**
- Modify: `prompts/team_lead.md`.
- Test: `tests/unit/test_team_lead_brainstorm_decomposition.py` (create).

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_team_lead_brainstorm_decomposition.py`:

```python
"""TL decomposition under inputs.intent == 'brainstorm_products' must
emit one MR sub-task per niche (no depends_on between them) and one
QA sub-task gated on all 3."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.team_lead.agent import TeamLeadAgent
from core.llm.mock import MockLLMClient, ScriptedResponse
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
)


def _scripted_decomposition() -> dict[str, object]:
    return {
        "summary": "Brainstorm 5 candidates per niche, then rank.",
        "subtasks": [
            {
                "id": "brainstorm_dev_tools",
                "recipient": "market_researcher",
                "title": "Brainstorm 5 dev_tools candidates",
                "description": "Brainstorm",
                "priority": "P2",
                "depends_on": [],
                "inputs": {"mode": "brainstorm_niche", "niche": "dev_tools",
                           "candidates": 5, "constraints": {}},
            },
            {
                "id": "brainstorm_b2b_smb",
                "recipient": "market_researcher",
                "title": "Brainstorm 5 b2b_smb candidates",
                "description": "Brainstorm",
                "priority": "P2",
                "depends_on": [],
                "inputs": {"mode": "brainstorm_niche", "niche": "b2b_smb",
                           "candidates": 5, "constraints": {}},
            },
            {
                "id": "brainstorm_creator_tools",
                "recipient": "market_researcher",
                "title": "Brainstorm 5 creator_tools candidates",
                "description": "Brainstorm",
                "priority": "P2",
                "depends_on": [],
                "inputs": {"mode": "brainstorm_niche", "niche": "creator_tools",
                           "candidates": 5, "constraints": {}},
            },
            {
                "id": "rank_candidates",
                "recipient": "qa_engineer",
                "title": "Rank all brainstorm candidates",
                "description": "Read 3 brainstorm artifacts; merge; rank.",
                "priority": "P2",
                "depends_on": ["brainstorm_dev_tools", "brainstorm_b2b_smb", "brainstorm_creator_tools"],
                "inputs": {"intent": "rank_brainstorm_candidates"},
            },
        ],
    }


@pytest.mark.asyncio
async def test_tl_decomposes_brainstorm_products() -> None:
    llm = MockLLMClient(responses=[ScriptedResponse(structured=_scripted_decomposition())])
    agent = TeamLeadAgent(llm=llm)

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.USER,
        recipient=AgentId.TEAM_LEAD,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Brainstorm monetizable product candidates",
            description="Decompose into 3 parallel MR sub-tasks + QA rank.",
            inputs={
                "intent": "brainstorm_products",
                "niches": ["dev_tools", "b2b_smb", "creator_tools"],
                "candidates_per_niche": 5,
                "constraints": {"solo_developer": True},
            },
        ),
    )

    outputs = await agent.handle(msg)

    assignments = [
        o for o in outputs
        if o.message_type == MessageType.TASK_ASSIGNMENT
    ]
    mr_assignments = [a for a in assignments if a.recipient == AgentId.MARKET_RESEARCHER]
    qa_assignments = [a for a in assignments if a.recipient == AgentId.QA_ENGINEER]

    assert len(mr_assignments) == 3, "expected 3 MR sub-tasks, one per niche"
    assert len(qa_assignments) == 1, "expected 1 QA rank sub-task"

    niches_seen = {a.payload.inputs["niche"] for a in mr_assignments}
    assert niches_seen == {"dev_tools", "b2b_smb", "creator_tools"}

    for a in mr_assignments:
        assert a.payload.inputs["mode"] == "brainstorm_niche"

    assert qa_assignments[0].payload.inputs["intent"] == "rank_brainstorm_candidates"
```

> **Note for the executor:** Read `agents/team_lead/agent.py` first — the TL probably routes subtasks through the HoldQueue when `depends_on` is non-empty. The QA sub-task with 3 `depends_on` won't appear in the *initial* outputs; it gets released after all 3 MR DONE reports arrive. The test above assumes the LLM emits all 4 subtasks at once and the agent code routes them; if the actual flow gates QA via HoldQueue, change the assertion to: 3 MR assignments emitted immediately, QA appears later when MR-DONE reports are processed. Pick the interpretation that matches the current TL code path; either is fine for the iter-26a goal.

- [ ] **Step 2: Run test, verify it fails**

```bash
uv run pytest tests/unit/test_team_lead_brainstorm_decomposition.py -v
```
Expected: test passes if the decomposition is purely prompt-driven and TL agent code already handles arbitrary subtasks. May fail if `TeamLeadAgent` assumes specific intent shapes — investigate before adding prompt-only fix.

- [ ] **Step 3: Append the new intent section to TL prompt**

At the end of `prompts/team_lead.md`, before the final newline:

```markdown

## Intent: brainstorm_products

When the incoming `task_assignment.inputs.intent == "brainstorm_products"`,
the inputs object contains:

- `niches: list[str]` — niches to brainstorm.
- `candidates_per_niche: int` — usually 5.
- `constraints: object` — structured constraints (solo_developer,
  max_product_llm_opex_usd_per_day, max_time_to_first_revenue_months,
  etc.). Pass verbatim to each sub-task.

Decompose into N + 1 sub-tasks:

1. One `market_researcher` sub-task per niche, with:
   ```json
   {
     "id": "brainstorm_<niche>",
     "recipient": "market_researcher",
     "title": "Brainstorm <candidates_per_niche> <niche> candidates",
     "description": "Brainstorm <N> monetizable candidates in the <niche> niche.",
     "priority": "P2",
     "depends_on": [],
     "inputs": {
       "mode": "brainstorm_niche",
       "niche": "<niche>",
       "candidates": <candidates_per_niche>,
       "constraints": <inputs.constraints>
     }
   }
   ```
   These sub-tasks have NO `depends_on` between them — they run in
   parallel.

2. One `qa_engineer` sub-task, gated on all 3 MR sub-tasks:
   ```json
   {
     "id": "rank_candidates",
     "recipient": "qa_engineer",
     "title": "Rank all brainstorm candidates",
     "description": "Read brainstorm artifacts; merge; rank by composite_score; write _combined_ranking.md; request_human_review.",
     "priority": "P2",
     "depends_on": ["brainstorm_<niche-1>", "brainstorm_<niche-2>", "brainstorm_<niche-3>"],
     "inputs": {"intent": "rank_brainstorm_candidates"}
   }
   ```

Do NOT emit Backend, Frontend, Architect, Designer, DevOps, or SRE
sub-tasks for this intent — `brainstorm_products` is a pure research
shape, not a build.
```

- [ ] **Step 4: Run test, verify it now passes**

```bash
uv run pytest tests/unit/test_team_lead_brainstorm_decomposition.py -v
```
Expected: PASS.

- [ ] **Step 5: Lint**

```bash
uv run ruff check tests/unit/test_team_lead_brainstorm_decomposition.py
```

- [ ] **Step 6: Commit**

```bash
git add prompts/team_lead.md tests/unit/test_team_lead_brainstorm_decomposition.py
git commit -m "feat(iter-26a): TL prompt — brainstorm_products intent + decomposition test"
```

---

## Task 6: QA rank-brainstorm-candidates intent

Add the rank-brainstorm branch to QA agent code + prompt.

**Files:**
- Modify: `agents/qa_engineer/agent.py` — intent dispatch in `handle()`; new `_build_rank_outputs()` + helpers; new schema constant.
- Modify: `prompts/qa_engineer.md` — `Intent: rank_brainstorm_candidates` section.
- Test: `tests/unit/test_qa_rank_brainstorm.py` (create).

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_qa_rank_brainstorm.py`:

```python
"""QA Engineer rank-brainstorm-candidates intent."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from agents.qa_engineer.agent import QAEngineerAgent
from core.llm.mock import MockLLMClient, ScriptedResponse
from core.messaging.schemas import (
    AgentId,
    AgentMessage,
    MessageType,
    Priority,
    TaskAssignmentPayload,
    TaskStatus,
)


def _brainstorm_md(niche: str, slugs: list[str]) -> str:
    """Minimal brainstorm artifact — just enough for QA to parse."""
    parts = [f"# Brainstorm — {niche}", "", "## All candidates", ""]
    for i, slug in enumerate(slugs):
        parts.append(f"### Title {i} (`{slug}`)")
        parts.append("")
        parts.append(f"- **Scores**: composite {10 + i}/25")
        parts.append("")
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_qa_rank_brainstorm_writes_combined_ranking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("agents.qa_engineer.agent._REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        "agents.qa_engineer.agent._RANKING_DIR",
        tmp_path / "docs" / "products" / "_candidates",
    )

    # Pre-populate 3 brainstorm artifacts.
    cands_dir = tmp_path / "docs" / "products" / "_candidates"
    cands_dir.mkdir(parents=True)
    artifacts = []
    for niche in ("dev_tools", "b2b_smb", "creator_tools"):
        path = cands_dir / f"_brainstorm_{niche}.md"
        path.write_text(_brainstorm_md(niche, [f"{niche}-{i}" for i in range(5)]))
        artifacts.append(str(path.relative_to(tmp_path)))

    rank_payload = {
        "intent_completed": "rank_brainstorm_candidates",
        "ranking_summary": "15 candidates ranked; top-3 listed.",
        "top_3_overall": ["dev_tools-4", "b2b_smb-4", "creator_tools-4"],
    }
    llm = MockLLMClient(responses=[ScriptedResponse(structured=rank_payload)])
    agent = QAEngineerAgent(llm=llm)

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Rank brainstorm candidates",
            description="Merge and rank.",
            inputs={
                "intent": "rank_brainstorm_candidates",
                "brainstorm_artifacts": artifacts,
            },
        ),
    )

    outputs = await agent.handle(msg)

    assert outputs[0].payload.status == TaskStatus.DONE
    ranking = cands_dir / "_combined_ranking.md"
    assert ranking.exists(), "_combined_ranking.md must be written"
    text = ranking.read_text()
    assert "dev_tools-4" in text
    assert "b2b_smb-4" in text
    assert "creator_tools-4" in text


@pytest.mark.asyncio
async def test_qa_existing_intent_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression — existing single-suite QA path unchanged when intent is absent."""
    llm = MockLLMClient(responses=[ScriptedResponse(structured={
        "suite_passed": True,
        "summary": "All 42 tests pass.",
        "coverage_pct": 91,
        "failures": [],
    })])
    agent = QAEngineerAgent(llm=llm)
    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.QA_ENGINEER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Run QA on Backend artifact",
            description="Run tests.",
            inputs={},
        ),
    )
    outputs = await agent.handle(msg)
    assert outputs[0].payload.status == TaskStatus.DONE
```

- [ ] **Step 2: Run test, verify it fails**

```bash
uv run pytest tests/unit/test_qa_rank_brainstorm.py -v
```
Expected: FAIL — intent branch and `_RANKING_DIR` not implemented.

- [ ] **Step 3: Add schema + helper + dispatch**

In `agents/qa_engineer/agent.py`, near the existing imports and constants:

```python
_RANKING_DIR: Path = _REPO_ROOT / "docs" / "products" / "_candidates"


RANK_BRAINSTORM_SCHEMA: dict[str, object] = {
    "type": "object",
    "required": ["intent_completed", "ranking_summary", "top_3_overall"],
    "additionalProperties": False,
    "properties": {
        "intent_completed": {"type": "string", "enum": ["rank_brainstorm_candidates"]},
        "ranking_summary": {"type": "string", "minLength": 1, "maxLength": 2_000},
        "top_3_overall": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
        },
    },
}
```

Update `mcp_env` to permit writes to `docs/products/_candidates`:

```python
    mcp_env: ClassVar[dict[str, str]] = {
        "AI_TEAM_PATH_PREFIXES": "tests/,docs/products",
    }
```

Refactor `handle()` (around line 136) to dispatch on intent:

```python
    async def handle(self, msg: AgentMessage) -> list[AgentMessage]:
        if msg.message_type != MessageType.TASK_ASSIGNMENT:
            return []
        assert isinstance(msg.payload, TaskAssignmentPayload)
        intent = (msg.payload.inputs or {}).get("intent")
        schema = (
            RANK_BRAINSTORM_SCHEMA if intent == "rank_brainstorm_candidates" else QA_REPORT_SCHEMA
        )
        response = await self._llm.invoke(
            system_prompt=self.system_prompt(),
            user_message=self._user_message_for(msg),
            model=self.model_tier,
            allowed_tools=self.allowed_tools,
            session_id=str(msg.correlation_id),
            timeout_s=self.llm_timeout_s,
            max_turns=self.max_turns,
            json_schema=schema,
            env=dict(self.mcp_env) if self.mcp_env else None,
        )
        outputs = self._stamp_metrics(self.build_outputs(response, msg), response)
        await self._ensure_pending_review_row(response, msg)
        return outputs
```

Refactor `build_outputs()`:

```python
    def build_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        if not isinstance(incoming.payload, TaskAssignmentPayload):
            return []
        intent = (incoming.payload.inputs or {}).get("intent")
        if intent == "rank_brainstorm_candidates":
            return self._build_rank_outputs(response, incoming)
        return self._build_qa_report_outputs(response, incoming)

    def _build_qa_report_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        """Existing single-suite QA report path (verbatim move from old build_outputs)."""
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        report = response.structured
        if not report or "suite_passed" not in report:
            return [
                self._report_to_tl(
                    incoming,
                    status=TaskStatus.FAILED,
                    summary="QA Engineer: LLM did not return a parseable QA report",
                )
            ]

        suite_passed = bool(report.get("suite_passed"))
        summary = str(report.get("summary", "")).strip()
        coverage_pct = report.get("coverage_pct")
        failures = [str(f) for f in report.get("failures") or []]

        full_summary = summary
        if coverage_pct is not None and "coverage" not in full_summary.lower():
            full_summary = f"{summary} ({coverage_pct}% coverage)"
        if failures and not suite_passed:
            sample = "; ".join(failures[:3])
            full_summary = f"{full_summary}. Failed: {sample}"

        return [
            self._report_to_tl(
                incoming,
                status=TaskStatus.DONE if suite_passed else TaskStatus.FAILED,
                summary=full_summary[:2_000],
            )
        ]

    def _build_rank_outputs(self, response: LLMResponse, incoming: AgentMessage) -> list[AgentMessage]:
        assert isinstance(incoming.payload, TaskAssignmentPayload)
        rank = response.structured or {}
        if rank.get("intent_completed") != "rank_brainstorm_candidates":
            return [self._report_to_tl(
                incoming,
                status=TaskStatus.FAILED,
                summary="QA: rank response missing intent_completed field",
            )]

        artifacts = (incoming.payload.inputs or {}).get("brainstorm_artifacts") or []
        top_3 = rank.get("top_3_overall", [])
        summary_text = rank.get("ranking_summary", "")

        try:
            _RANKING_DIR.mkdir(parents=True, exist_ok=True)
            ranking_md = self._render_combined_ranking(artifacts, top_3, summary_text)
            (_RANKING_DIR / "_combined_ranking.md").write_text(ranking_md)
        except OSError as e:
            return [self._report_to_tl(
                incoming,
                status=TaskStatus.FAILED,
                summary=f"QA: failed to write combined ranking: {e}",
            )]

        return [self._report_to_tl(
            incoming,
            status=TaskStatus.DONE,
            summary=f"Ranking complete. Top-3: {', '.join(top_3)}. {summary_text}"[:2_000],
        )]

    def _render_combined_ranking(
        self, artifact_paths: list[str], top_3: list[str], summary: str,
    ) -> str:
        lines: list[str] = [
            "# Combined brainstorm ranking",
            "",
            "- **Status**: Draft (QA-merged; pending owner review)",
            f"- **Source artifacts**: {len(artifact_paths)}",
            "",
            "## Overall top-3 (QA selection)",
            "",
        ]
        for slug in top_3:
            lines.append(f"- `{slug}`")
        lines.append("")
        lines.append("## Source brainstorms")
        lines.append("")
        for path in artifact_paths:
            lines.append(f"- {path}")
        lines.append("")
        lines.append("## QA notes")
        lines.append("")
        lines.append(summary.strip())
        lines.append("")
        return "\n".join(lines)
```

> **Note for the executor:** verify the existing `_report_to_tl` helper signature; the code above assumes `_report_to_tl(incoming, status=..., summary=...)`. Adjust if the real method has a different signature.

- [ ] **Step 4: Run all QA tests**

```bash
uv run pytest tests/unit/test_qa_rank_brainstorm.py tests/unit/test_qa_engineer*.py -v
```
Expected: all pass — the regression test in this file plus pre-existing QA suites.

- [ ] **Step 5: Append QA prompt section**

At the end of `prompts/qa_engineer.md`:

```markdown

## Intent: rank_brainstorm_candidates

Selected when `inputs.intent == "rank_brainstorm_candidates"`.

### Inputs

- `brainstorm_artifacts: list[str]` — repo-relative paths to MR
  brainstorm files, typically:
  ```
  docs/products/_candidates/_brainstorm_dev_tools.md
  docs/products/_candidates/_brainstorm_b2b_smb.md
  docs/products/_candidates/_brainstorm_creator_tools.md
  ```

### Steps

1. `Read` every artifact in `brainstorm_artifacts`. Each contains
   five candidates with composite scores 5–25.
2. Concatenate all 15 candidates. Sort descending by composite
   score. Ties broken by `defensibility`, then `solo_fit`.
3. Pick the overall top-3 slugs.
4. Call `mcp__ai_team_tasks__request_human_review` with a short
   summary referencing `_combined_ranking.md` (the agent code
   writes the file from the JSON you return).

### What you produce (JSON only)

```json
{
  "intent_completed": "rank_brainstorm_candidates",
  "ranking_summary": "<≤2000 chars; cite the top-3 with one-line
                      rationale each>",
  "top_3_overall": ["slug-1", "slug-2", "slug-3"]
}
```

### Discipline

- Do NOT re-score candidates. Trust MR's `composite_score`.
- Do NOT propose new candidates. You merge and rank, not generate.
- Top-3 slugs MUST appear in at least one of the brainstorm
  artifacts. If you can't find them, the test suite will fail the
  cross-check.
```

- [ ] **Step 6: Lint + typecheck**

```bash
uv run ruff check agents/qa_engineer/ tests/unit/test_qa_rank_brainstorm.py
uv run mypy agents/qa_engineer/agent.py
```

- [ ] **Step 7: Commit**

```bash
git add agents/qa_engineer/agent.py prompts/qa_engineer.md tests/unit/test_qa_rank_brainstorm.py
git commit -m "feat(iter-26a): QA rank-brainstorm-candidates intent + prompt"
```

---

## Task 7: CLI `ai-team brainstorm-products`

Wraps existing `/api/tasks` with structured inputs.

**Files:**
- Modify: `apps/cli/main.py` — new Click sub-command.
- Test: extends `tests/unit/test_cli_brainstorm_products.py` (create).

- [ ] **Step 1: Write failing test**

Create `tests/unit/test_cli_brainstorm_products.py`:

```python
"""ai-team brainstorm-products builds the correct request body."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from click.testing import CliRunner
from respx import MockRouter
import respx

from apps.cli.main import cli


@respx.mock
def test_brainstorm_products_posts_intent_inputs(tmp_path: Path) -> None:
    constraints = tmp_path / "constraints.json"
    constraints.write_text(json.dumps({
        "solo_developer": True,
        "max_product_llm_opex_usd_per_day": 3,
    }))

    route = respx.post("http://localhost:8000/api/tasks").mock(
        return_value=httpx.Response(200, json={
            "task_id": "00000000-0000-0000-0000-000000000001",
            "correlation_id": "00000000-0000-0000-0000-000000000002",
            "status": "in_progress",
        })
    )

    runner = CliRunner()
    result = runner.invoke(cli, [
        "brainstorm-products",
        "--niches", "dev_tools,b2b_smb,creator_tools",
        "--candidates-per-niche", "5",
        "--constraints-json", str(constraints),
    ])

    assert result.exit_code == 0, result.output
    assert route.called

    body = json.loads(route.calls.last.request.content)
    assert body["inputs"]["intent"] == "brainstorm_products"
    assert body["inputs"]["niches"] == ["dev_tools", "b2b_smb", "creator_tools"]
    assert body["inputs"]["candidates_per_niche"] == 5
    assert body["inputs"]["constraints"]["solo_developer"] is True
```

> **Note for the executor:** `respx` may not be in dev deps yet. Check `pyproject.toml`. If missing, add it to dev-deps via `uv add --dev respx` first; commit the lockfile bump together with this task.

- [ ] **Step 2: Run test, verify it fails**

```bash
uv run pytest tests/unit/test_cli_brainstorm_products.py -v
```
Expected: FAIL — `brainstorm-products` sub-command does not exist.

- [ ] **Step 3: Add the sub-command**

In `apps/cli/main.py`, after the existing `submit` command (around line 237):

```python
@cli.command(name="brainstorm-products")
@click.option(
    "--niches",
    required=True,
    help="Comma-separated niches (e.g. dev_tools,b2b_smb,creator_tools).",
)
@click.option(
    "--candidates-per-niche",
    default=5,
    type=int,
    help="Number of candidates per niche (default: 5).",
)
@click.option(
    "--constraints-json",
    required=True,
    type=click.Path(exists=True, dir_okay=False, readable=True),
    help="Path to JSON file with monetization/budget constraints.",
)
@click.pass_context
def brainstorm_products(
    ctx: click.Context,
    niches: str,
    candidates_per_niche: int,
    constraints_json: str,
) -> None:
    """Brainstorm monetizable product candidates across niches."""
    niche_list = [n.strip() for n in niches.split(",") if n.strip()]
    if not niche_list:
        console.print("[red]At least one niche required.[/]")
        sys.exit(1)

    with open(constraints_json) as f:
        constraints = json.load(f)

    body: dict[str, Any] = {
        "title": "Brainstorm monetizable product candidates",
        "description": (
            f"Decompose into {len(niche_list)} parallel market_researcher "
            f"sub-tasks (one per niche), then route a qa_engineer sub-task "
            f"to merge and rank. Constraints in inputs.constraints."
        ),
        "inputs": {
            "intent": "brainstorm_products",
            "niches": niche_list,
            "candidates_per_niche": candidates_per_niche,
            "constraints": constraints,
        },
    }
    resp = httpx.post(
        f"{_api_base(ctx)}/api/tasks",
        json=body,
        headers=_token_header(ctx),
        timeout=30.0,
    )
    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.status_code} {resp.text}[/]")
        sys.exit(1)
    data = resp.json()
    console.print(
        Panel(
            f"[bold]Brainstorm queued.[/]\n"
            f"  task_id:        {data['task_id']}\n"
            f"  correlation_id: {data['correlation_id']}\n"
            f"  niches:         {', '.join(niche_list)}\n"
            f"  watch:          ai-team watch --correlation {data['correlation_id']}",
            title="brainstorm-products submitted",
            style="green",
        )
    )
```

- [ ] **Step 4: Run test, verify it passes**

```bash
uv run pytest tests/unit/test_cli_brainstorm_products.py -v
```
Expected: PASS.

- [ ] **Step 5: Lint + typecheck**

```bash
uv run ruff check apps/cli/main.py tests/unit/test_cli_brainstorm_products.py
uv run mypy apps/cli/main.py
```

- [ ] **Step 6: Commit**

```bash
git add apps/cli/main.py tests/unit/test_cli_brainstorm_products.py pyproject.toml uv.lock
git commit -m "feat(iter-26a): ai-team brainstorm-products CLI sub-command"
```

---

## Task 8: Pre-demo quota check script

iter-26 handoff P2. Reusable across future demos.

**Files:**
- Create: `scripts/preflight_quota_check.sh`.
- Test: manual + invocation from `demo_iter_26a.sh` in Task 9.

- [ ] **Step 1: Create the script**

`scripts/preflight_quota_check.sh`:

```bash
#!/usr/bin/env bash
# Pre-demo quota check (iter-26 handoff P2).
#
# Sends a trivial prompt to `claude -p` and checks the result.
# Exits 0 on success.
# Exits 1 if the response contains api_error_status=429 or is empty;
# prints the 429 reset time line if available so the operator
# knows when to retry.
#
# Used by scripts/demo_iter_26a.sh and any later demo that wants to
# avoid burning 15 minutes on a doomed chain.

set -euo pipefail

if ! command -v claude >/dev/null 2>&1; then
  echo "preflight: claude CLI not found in PATH" >&2
  exit 2
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

if ! claude -p "Reply with exactly: pong" --output-format json --max-turns 1 > "$tmp" 2>&1; then
  echo "preflight: claude -p invocation failed" >&2
  cat "$tmp" >&2
  exit 1
fi

if grep -q '"api_error_status": *429' "$tmp"; then
  echo "preflight: Max-5x session quota hit (429)." >&2
  grep -oE '"resets [^"]+"' "$tmp" | head -1 >&2 || true
  echo "preflight: wait for the reset time above, then re-run." >&2
  exit 1
fi

# Heuristic — `result` or `structured_output` should contain "pong".
if ! grep -qi 'pong' "$tmp"; then
  echo "preflight: response did not contain 'pong'. Sample:" >&2
  head -c 1000 "$tmp" >&2
  exit 1
fi

echo "preflight: OK (quota available)."
exit 0
```

- [ ] **Step 2: Make executable + smoke test (manual)**

```bash
chmod +x scripts/preflight_quota_check.sh
scripts/preflight_quota_check.sh
```
Expected (if quota available): `preflight: OK (quota available).`

If 429: the script prints reset time and exits 1 — that's the success
shape of the 429 branch.

- [ ] **Step 3: Commit**

```bash
git add scripts/preflight_quota_check.sh
git commit -m "feat(iter-26a): scripts/preflight_quota_check.sh — iter-26 P2"
```

---

## Task 9: `scripts/demo_iter_26a.sh` + default constraints JSON

**Files:**
- Create: `scripts/demo_iter_26a.sh`.
- Create: `scripts/iter_26a_constraints.json`.

- [ ] **Step 1: Create the default constraints JSON**

`scripts/iter_26a_constraints.json`:

```json
{
  "solo_developer": true,
  "max_product_llm_opex_usd_per_day": 3,
  "monetization_preferences": ["subscription", "per-seat", "usage"],
  "max_time_to_first_revenue_months": 6,
  "defensibility_floor": "minimal moat acceptable; user-distribution moat ok",
  "owner_expertise_hint": "Python backend; AI/agent systems; Russian-speaking; comfortable with technical content"
}
```

- [ ] **Step 2: Create the demo script**

`scripts/demo_iter_26a.sh`:

```bash
#!/usr/bin/env bash
# iter-26a demo — uses the team to brainstorm 5 product candidates per
# niche across dev_tools / b2b_smb / creator_tools, then QA ranks and
# requests owner review.
#
# Spec: docs/superpowers/specs/2026-05-22-iter-26a-mr-brainstorm-design.md
# Plan: docs/iterations/iter_26a.md
#
# Run:  ./scripts/demo_iter_26a.sh
# Stop: Ctrl-C; the post-success drain (60s after success-detection)
#       must complete before reporting metrics.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

LOG_DIR="docs/iterations/iter_26a_demo_logs"
mkdir -p "$LOG_DIR"
RUN_TS="$(date +%Y%m%d_%H%M%S)"
RUN_LOG="$LOG_DIR/run_$RUN_TS.log"

echo "==> Phase 0: preflight quota check"
./scripts/preflight_quota_check.sh

echo "==> Phase 1: bring up Postgres + Redis"
make up

echo "==> Phase 2: start FastAPI + dispatcher (background)"
uv run uvicorn apps.api.main:app --port 8000 >> "$RUN_LOG" 2>&1 &
API_PID=$!
trap '[ -n "${API_PID:-}" ] && kill "$API_PID" 2>/dev/null || true' EXIT
sleep 3

echo "==> Phase 3: submit brainstorm-products"
SUBMIT_OUT=$(uv run ai-team brainstorm-products \
  --niches dev_tools,b2b_smb,creator_tools \
  --candidates-per-niche 5 \
  --constraints-json scripts/iter_26a_constraints.json)
echo "$SUBMIT_OUT" | tee -a "$RUN_LOG"
CID=$(echo "$SUBMIT_OUT" | grep -oE 'correlation_id:[[:space:]]+[0-9a-f-]+' | awk '{print $2}')
echo "correlation_id = $CID"

echo "==> Phase 4: poll for pending_review (≤15 min)"
DEADLINE=$(( $(date +%s) + 900 ))
SUCCESS=0
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
  COUNT=$(psql -tA postgresql://ai_team:ai_team@localhost:5432/ai_team \
    -c "SELECT COUNT(*) FROM pending_reviews WHERE correlation_id = '$CID'" 2>/dev/null || echo 0)
  if [ "${COUNT:-0}" -ge 1 ]; then
    SUCCESS=1
    break
  fi
  sleep 5
done

if [ "$SUCCESS" -ne 1 ]; then
  echo "DEMO FAILED — no pending_review row after 15 min." >&2
  echo "Run log: $RUN_LOG"
  exit 1
fi

echo "==> Phase 5: 60s post-success drain (iter-25 lesson)"
sleep 60

echo "==> Phase 6: collect demo report"
REPORT="$LOG_DIR/demo_report_$RUN_TS.md"
{
  echo "# iter-26a demo report — $RUN_TS"
  echo
  echo "- correlation_id: $CID"
  echo
  echo "## Per-message audit"
  echo
  psql postgresql://ai_team:ai_team@localhost:5432/ai_team -c "
    SELECT id, sender, recipient, message_type,
           payload_json->'metadata'->'llm'->>'model'              AS model,
           (payload_json->'metadata'->'llm'->>'tokens_in')::int   AS tokens_in,
           (payload_json->'metadata'->'llm'->>'tokens_out')::int  AS tokens_out,
           (payload_json->'metadata'->'llm'->>'cached_input')::int AS cached_input,
           (payload_json->'metadata'->'llm'->>'cost_cents')::int  AS cost_cents,
           (payload_json->'metadata'->'llm'->>'duration_ms')::int AS duration_ms
    FROM audit_log WHERE correlation_id = '$CID' ORDER BY id"
  echo
  for f in docs/products/_candidates/_brainstorm_dev_tools.md \
           docs/products/_candidates/_brainstorm_b2b_smb.md \
           docs/products/_candidates/_brainstorm_creator_tools.md \
           docs/products/_candidates/_combined_ranking.md; do
    echo "## $f"
    echo
    if [ -f "$f" ]; then
      cat "$f"
    else
      echo "_(missing)_"
    fi
    echo
  done
} > "$REPORT"

echo "==> Done. Report: $REPORT"
```

- [ ] **Step 3: Make executable + dry-run sanity check (syntax only)**

```bash
chmod +x scripts/demo_iter_26a.sh
bash -n scripts/demo_iter_26a.sh
```
Expected: no syntax errors.

- [ ] **Step 4: Commit**

```bash
git add scripts/demo_iter_26a.sh scripts/iter_26a_constraints.json
git commit -m "feat(iter-26a): demo_iter_26a.sh + default constraints JSON"
```

---

## Task 10: Integration test — full chain on mocked LLM

End-to-end testcontainers test with Postgres + Redis. No real `claude -p`. Validates the full chain shape end-to-end with deterministic scripted responses.

**Files:**
- Create: `tests/integration/test_iter_26a_e2e_brainstorm.py`.

- [ ] **Step 1: Write the test (it will fail at first, then pass once Tasks 1-7 are done)**

Create `tests/integration/test_iter_26a_e2e_brainstorm.py`:

```python
"""End-to-end iter-26a chain on Postgres + Redis + mocked LLM.

Asserts the full audit chain shape: 1 root → 3 MR assignments →
3 MR DONE → 1 QA assignment → 1 QA DONE → 1 pending_review row.

Real LLM coverage is in tests/real_llm/test_mr_brainstorm_one_niche.py.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

# Reuse the existing test harness — most projects have one for the
# iter-3+ chain demos. If it lives at `tests/integration/conftest.py`,
# import the fixtures from there.

pytestmark = pytest.mark.integration


@pytest.fixture
def scripted_responses() -> dict[str, Any]:
    """Pre-built LLM scripts keyed by (agent, intent/mode).

    The MockLLMClient in this codebase dispatches by request shape
    — confirm the exact key shape before adjusting these scripts.
    """
    return {
        ("team_lead", "brainstorm_products"): _tl_script(),
        ("market_researcher", "brainstorm_niche", "dev_tools"): _mr_script("dev_tools"),
        ("market_researcher", "brainstorm_niche", "b2b_smb"): _mr_script("b2b_smb"),
        ("market_researcher", "brainstorm_niche", "creator_tools"): _mr_script("creator_tools"),
        ("qa_engineer", "rank_brainstorm_candidates"): _qa_script(),
    }


def _tl_script() -> dict[str, Any]:
    return {
        "summary": "Decompose into 3 MR + 1 QA.",
        "subtasks": [
            {"id": f"brainstorm_{n}", "recipient": "market_researcher",
             "title": f"Brainstorm {n}", "description": "...", "priority": "P2",
             "depends_on": [],
             "inputs": {"mode": "brainstorm_niche", "niche": n,
                        "candidates": 5, "constraints": {}}}
            for n in ("dev_tools", "b2b_smb", "creator_tools")
        ] + [
            {"id": "rank_candidates", "recipient": "qa_engineer",
             "title": "Rank", "description": "...", "priority": "P2",
             "depends_on": ["brainstorm_dev_tools", "brainstorm_b2b_smb", "brainstorm_creator_tools"],
             "inputs": {"intent": "rank_brainstorm_candidates"}},
        ],
    }


def _mr_script(niche: str) -> dict[str, Any]:
    cand = lambda i: {  # noqa: E731
        "title": f"{niche.title()} #{i}",
        "slug": f"{niche}-{i}",
        "one_paragraph": "x" * 30,
        "target_buyer": "y",
        "monetization": "subscription",
        "known_competitors": [{"name": "C", "positioning": "p"}],
        "scores": {"tam_signal": 3, "solo_fit": 3, "llm_opex_fit": 3,
                   "defensibility": 3, "time_to_first_revenue": 3},
        "composite_score": 15,
        "rationale": "r",
    }
    return {
        "niche": niche,
        "candidates": [cand(i) for i in range(5)],
        "researcher_top_3_slugs": [f"{niche}-{i}" for i in range(3)],
        "research_sources_used": ["https://example.com/a"],
    }


def _qa_script() -> dict[str, Any]:
    return {
        "intent_completed": "rank_brainstorm_candidates",
        "ranking_summary": "All 15 candidates ranked.",
        "top_3_overall": ["dev_tools-4", "b2b_smb-4", "creator_tools-4"],
    }


@pytest.mark.asyncio
async def test_iter_26a_e2e_chain(
    api_client: httpx.AsyncClient,  # from tests/integration/conftest.py
    db_session_factory: Any,
    scripted_responses: dict[str, Any],
) -> None:
    """Submit one brainstorm-products task; assert the full chain lands."""

    # Hook the scripted_responses into the dispatcher's LLM mock.
    # The integration conftest already plumbs MockLLMClient; replace
    # its script with `scripted_responses`. See conftest for the exact
    # hook name (e.g. `set_llm_script`).

    resp = await api_client.post("/api/tasks", json={
        "title": "Brainstorm monetizable product candidates",
        "description": "iter-26a integration test.",
        "inputs": {
            "intent": "brainstorm_products",
            "niches": ["dev_tools", "b2b_smb", "creator_tools"],
            "candidates_per_niche": 5,
            "constraints": {},
        },
    })
    assert resp.status_code == 200
    cid = UUID(resp.json()["correlation_id"])

    # Poll up to 60s for pending_review row.
    for _ in range(60):
        async with db_session_factory() as s:
            result = await s.execute(
                "SELECT COUNT(*) FROM pending_reviews WHERE correlation_id = :cid",
                {"cid": str(cid)},
            )
            count = result.scalar() or 0
            if count >= 1:
                break
        await asyncio.sleep(1)
    else:
        pytest.fail("pending_review row never appeared")

    # Assert audit_log chain shape.
    async with db_session_factory() as s:
        result = await s.execute(
            "SELECT sender, recipient, message_type FROM audit_log "
            "WHERE correlation_id = :cid ORDER BY id",
            {"cid": str(cid)},
        )
        rows = result.fetchall()

    senders = [r[0] for r in rows]
    assert senders.count("market_researcher") == 3, "expected 3 MR DONE reports"
    assert senders.count("qa_engineer") == 1, "expected 1 QA DONE report"
    # 1 USER->TL + 3 TL->MR + 3 MR->TL + 1 TL->QA + 1 QA->TL → 9 rows total.
    assert len(rows) >= 9
```

> **Note for the executor:** This test references fixtures and hooks
> (`api_client`, `db_session_factory`, `set_llm_script`) that probably
> already exist in `tests/integration/conftest.py`. Read that file
> first; mirror the existing fixture names. If a hook for swapping the
> scripted responses doesn't exist, add a minimal one to the conftest
> (do that in a separate commit before this test).

- [ ] **Step 2: Run integration suite**

```bash
make up  # if not already
uv run pytest tests/integration/test_iter_26a_e2e_brainstorm.py -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_iter_26a_e2e_brainstorm.py
git commit -m "test(iter-26a): integration E2E — full chain on mocked LLM"
```

---

## Task 11: Real-LLM smoke (1 niche, 2 candidates)

Cheap real-LLM test, ~$0.30, run on demand, NOT in CI.

**Files:**
- Create: `tests/real_llm/test_mr_brainstorm_one_niche.py`.

- [ ] **Step 1: Write the test**

```python
"""Real `claude -p` smoke for MR brainstorm-niche mode.

Cost target: ≤ $0.50. Run on demand:
  uv run pytest tests/real_llm/test_mr_brainstorm_one_niche.py --real-llm -v

Excluded from CI. iter-26a uses this for adversarial prompt-tuning,
not regression."""

from __future__ import annotations

import pytest

from agents.market_researcher.agent import (
    BRAINSTORM_NICHE_SCHEMA,
    MarketResearcherAgent,
)
from core.llm.factory import build_llm_client
from core.messaging.schemas import (
    AgentId, AgentMessage, MessageType, Priority, TaskAssignmentPayload,
    TaskStatus,
)
from uuid import uuid4

pytestmark = pytest.mark.real_llm


@pytest.mark.asyncio
async def test_mr_brainstorm_dev_tools_two_candidates() -> None:
    llm = build_llm_client()  # real ClaudeCodeHeadlessClient
    agent = MarketResearcherAgent(llm=llm)

    msg = AgentMessage(
        correlation_id=uuid4(),
        sender=AgentId.TEAM_LEAD,
        recipient=AgentId.MARKET_RESEARCHER,
        message_type=MessageType.TASK_ASSIGNMENT,
        priority=Priority.P2,
        payload=TaskAssignmentPayload(
            task_id=uuid4(),
            title="Smoke: brainstorm 2 dev_tools candidates",
            description=(
                "Brainstorm 2 monetizable dev_tools candidates. "
                "Solo dev. ≤6mo TTFR. ≤$3/day product LLM-opex."
            ),
            inputs={
                "mode": "brainstorm_niche",
                "niche": "dev_tools",
                "candidates": 2,
                "constraints": {
                    "solo_developer": True,
                    "max_time_to_first_revenue_months": 6,
                    "max_product_llm_opex_usd_per_day": 3,
                },
            },
        ),
    )

    outputs = await agent.handle(msg)
    assert outputs[0].payload.status == TaskStatus.DONE, outputs[0].payload.summary
```

> **Note for the executor:** the iter-26a spec requires 5 candidates
> per niche under the production schema, which is `minItems: 5,
> maxItems: 5`. This smoke test asks for 2 — that violates the schema
> on purpose to keep cost low, so the test is expected to FAIL the
> production schema. Two options: (a) accept the test will be
> primarily exploratory (run with `--no-strict` if you have one), or
> (b) just run a 5-candidate smoke — costs ~$0.70. **Pick (b)** —
> simpler, no schema gymnastics, and the cost is still within budget.
> Update the test to `"candidates": 5`.

- [ ] **Step 2: Run (manual)**

```bash
uv run pytest tests/real_llm/test_mr_brainstorm_one_niche.py --real-llm -v
```
Expected: PASS, ~30-90s, ~$0.50-$0.80 spend.

- [ ] **Step 3: Commit**

```bash
git add tests/real_llm/test_mr_brainstorm_one_niche.py
git commit -m "test(iter-26a): real-LLM smoke — MR brainstorm one niche"
```

---

## Task 12: CLAUDE.md update — flag the new candidates surface

Small docs update. One paragraph.

**Files:**
- Modify: `CLAUDE.md`.

- [ ] **Step 1: Add the paragraph**

In `CLAUDE.md`, in the "Where to look" section, after the existing
`docs/sandbox/` line, add:

```markdown
docs/products/_candidates/   # iter-26a+: brainstormed product
                             # candidates from MR (real product
                             # surface, separate from sandbox training
                             # material in docs/sandbox/ideas/).
                             # _combined_ranking.md is the QA-merged
                             # shortlist; owner picks top-3 here.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(iter-26a): flag docs/products/_candidates/ surface in CLAUDE.md"
```

---

## Task 13: Run the demo end-to-end (validation)

This is the real validation step. The owner runs it manually after
the implementation is merged (it spends LLM budget).

- [ ] **Step 1: Run preflight**

```bash
./scripts/preflight_quota_check.sh
```
Expected: `preflight: OK (quota available).` If 429, wait for reset.

- [ ] **Step 2: Run the full demo**

```bash
./scripts/demo_iter_26a.sh
```
Expected: completes inside 15 min; final line `==> Done. Report: docs/iterations/iter_26a_demo_logs/demo_report_*.md`.

- [ ] **Step 3: Verify acceptance criteria** (spec section 8)

```bash
# 1. Audit chain
psql ai_team -c "SELECT sender, recipient, message_type FROM audit_log WHERE correlation_id = '<cid>' ORDER BY id;"
# expect 1 USER→TL + 3 TL→MR + 3 MR→TL + 1 TL→QA + 1 QA→TL + 1 request_human_review

# 2-3. Files exist + schema OK
for f in docs/products/_candidates/_brainstorm_*.md docs/products/_candidates/_combined_ranking.md; do
  [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"
done

# 4. pending_review row
psql ai_team -c "SELECT id, summary FROM pending_reviews WHERE correlation_id = '<cid>';"

# 5. Per-message metrics non-zero
# (already in the demo_report.md SQL output)

# 6. Total spend ≤ $5
psql ai_team -c "SELECT SUM((payload_json->'metadata'->'llm'->>'cost_cents')::int)/100.0 FROM audit_log WHERE correlation_id = '<cid>';"
```

- [ ] **Step 4: Approve via CLI**

After reviewing `_combined_ranking.md`:

```bash
ai-team list-pending
ai-team approve <id> --comment "top-3: <slug-1>, <slug-2>, <slug-3>"
```

This comment seeds iter-26b.

- [ ] **Step 5: Demo report + retro**

Write `docs/iterations/iter_26a_demo_report.md` and `iter_26a_retro.md`
following the iter-25 template. These are tracking docs, not part of
the implementation plan; the executor produces them after the demo.

---

## Final sanity checklist (run after all tasks done)

- [ ] `make lint typecheck test` all green on the merged branch.
- [ ] `make smoke-llm` passes (substrate health check, not iter-26a-specific).
- [ ] Diff coverage ≥ 80 % on the changes (CI gate).
- [ ] PR description references this plan + the source spec.
- [ ] iter_26a_handoff.md drafted with the iter-26b strategic decision (which 3 slugs go forward, owner's reasoning), even if iter-26b is not started.

## Notes for the executor

- **Conventional commits** are enforced by `wagoid/commitlint-github-action`.
  Each task's commit message above uses `feat(iter-26a):` / `test(iter-26a):` /
  `docs(iter-26a):` — pick the right prefix per task.
- **Squash-merge only** on merge to `main`. Branch protection forbids
  force-push and deletions.
- **Owner approves before merge** — even after CI is green, do not
  merge iter-26a until the demo has been run and the demo report
  reviewed. This is the dev-PR layer, but it's special: the iteration
  is the unit of progress, and the demo is the contract.
- **Cost guard:** `make smoke-llm` and Task 11 together spend ~$1; the
  full demo (Task 13) ~$2-3. Track cumulative spend across the
  session to avoid the iter-25 R#2 quota surprise.
- **If a parallel MR fails** (R3 / R5 from spec): re-run the demo
  after the failure cause is addressed. Do NOT cherry-pick a partial
  run for iter-26b — owner needs all 3 niches' candidates to choose
  fairly.
