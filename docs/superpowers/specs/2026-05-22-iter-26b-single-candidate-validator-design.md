# Iter-26b — Single-candidate product validator

> **Status:** Approved design (2026-05-22). Pending implementation plan
> (writing-plans skill, next step). Owner: solo dev.
>
> **Prerequisite reads:** `CLAUDE.md`,
> `docs/superpowers/specs/2026-05-22-iter-26a-mr-brainstorm-design.md`,
> `docs/iterations/iter_26a.md`, `docs/products/_candidates/_combined_ranking.md`.

## 1. Context

Iter-26a closed on 2026-05-22 with a single-candidate owner pick:
**`telegram-tech-publisher`** (creator_tools niche, composite 22/25).
Approval recorded on QA pending_review rows `3dbd9b80…` and `d3859663…`.

Rationale captured in the audit log: only candidate of the 15 with a
structural moat tied to the owner specifically — CIS Telegram
developer-community distribution requires native Russian + existing
channel access, unreplicable by US-based competitors. Stack is Python +
Telegram Bot API + Claude, 6–8 week MVP estimate from MR's brainstorm.

The owner is committed to the pick but has not committed to skipping
validation. The job of iter-26b is to **stress-test the assumptions
behind that pick before committing to a 6–8 week MVP build**:

- Is the niche actually underserved at the depth claimed in the
  brainstorm, or did the 3-source MR scan miss an established competitor?
- Does the Telegram Bot API actually support the product as described
  (rate limits, message formatting, payment integration)?
- Does the unit economics work, or is the LLM-opex / pricing combination
  too tight for solo-dev margins?
- Is there a fatal flaw none of the 26a-shallow passes surfaced?

This spec covers **iter-26b only**, validation of one slug. If iter-26b
returns `pivot`, the next slug from the iter-26a shortlist
(`ai-technical-repurposer` or `ai-newsletter-digest-bot`) is validated
by re-running the same chain. If iter-26b returns `go`, iter-27 begins
in a separate repo per ADR-009 `TARGET_REPO` abstraction.

## 2. Goals

1. Produce a structured **build-or-pivot recommendation** for
   `telegram-tech-publisher` with explicit risk register and confidence
   level, before owner commits 6–8 weeks of build time.
2. Exercise the team framework on a third shape of work — diligence —
   after iter-2's build task and iter-26a's brainstorm task. This is
   the first real test of full-team coordination on a single
   shared subject (one slug, four agents, structured synthesis).
3. Lock in the `inputs.intent` pattern from iter-26a as the standard
   way to multiplex agent modes. No new architectural extensions.
4. Stay under the $20/day hard kill while crossing the $5/day soft
   warning — validation is intentional spend, not background drift.

## 3. Non-goals

- **No product code shipped.** Iter-27 (separate repo) builds the MVP.
- **No real customer interviews.** Validator does SIGNAL collection
  (Reddit / Indie Hackers / Twitter / forum scrape via WebFetch); real
  humans are out of scope.
- **No new agent classes.** Reuse existing PM, Architect, MR, QA.
- **No new bus / audit / dispatcher work.** Reuse iter-26a's
  `inputs.intent` pattern unchanged.
- **Not a re-rank of the 15 candidates.** iter-26a's ranking stands.
  iter-26b validates one slug.
- **Not a fix for the dispatcher per-role parallelism issue** (see
  carry-overs).
- **Not a fix for the 2-pending_reviews-per-QA-turn anomaly** (see
  carry-overs).

## 4. Surface contract

### 4.1 CLI command

New subcommand on `apps/cli/main.py`:

```
ai-team validate-product \
  --slug telegram-tech-publisher \
  --candidate-file docs/products/_candidates/_brainstorm_creator_tools.md \
  --depth standard \
  --constraints-json scripts/iter_26b_constraints.json
```

Options:

| Flag | Required | Default | Meaning |
|---|---|---|---|
| `--slug` | yes | — | Candidate slug (matches an H2 section heading in `--candidate-file`) |
| `--candidate-file` | yes | — | Path to the iter-26a brainstorm md that contains the slug's section |
| `--depth` | no | `standard` | `quick` \| `standard` \| `deep` — controls competitor-scan breadth |
| `--constraints-json` | no | `scripts/iter_26b_constraints.json` | JSON file with owner profile + budget envelope |

Depth → competitor-scan source-count:

| Depth | Competitors | Pain signals | Est. cost |
|---|---|---|---|
| `quick` | 5 | 3 | $4–7 |
| `standard` | 15 | 7 | $8–14 |
| `deep` | 30 | 12 | $14–22 |

The CLI:

1. Reads `--candidate-file`, finds the H2 section whose body contains
   `**Slug:** <slug>`, extracts that section's full markdown.
2. POSTs `/api/tasks` with:
   - `title`: `"Validate product: <slug>"`
   - `description`: the extracted section body
   - `inputs`: `{intent: "validate_product", slug, depth, candidate_brief: <extracted>, constraints: <parsed JSON>}`
3. Prints correlation_id; recommends `ai-team watch --correlation <id>`.

If the slug section is not found in the file, CLI exits 1 with a
clear error message (no API call made).

### 4.2 Output file layout

New per-candidate directory:

```
docs/products/<slug>/                       ← NEW dir per candidate
  ├── competitors.md         ← MR writes
  ├── tech_risk.md           ← Architect writes
  ├── revenue.md             ← PM writes
  └── _validation_summary.md ← QA writes (also emits the pending_review)
```

For `telegram-tech-publisher` specifically:
`docs/products/telegram-tech-publisher/{competitors,tech_risk,revenue,_validation_summary}.md`.

This is intentionally separate from `docs/products/_candidates/` (which
holds iter-26a brainstorm files). The `_candidates/` dir is the pool;
`<slug>/` dirs are the diligence outputs.

### 4.3 Structured pending_review payload

QA emits exactly one (or two, given the iter-25/26 anomaly)
pending_review. The full `report.structured` matches
`SYNTHESIZE_VALIDATION_SCHEMA` (§5.5) and contains 9 fields. The
owner-facing subset — the 6 fields that drive the decision — is:

```json
{
  "recommendation": "go" | "go_with_caveats" | "pivot" | "kill",
  "confidence": 0-5,
  "top_risks": [
    {"name": "string", "severity": 1-5, "mitigation": "string"}
  ],
  "fatal_flaws": ["string", ...],
  "build_window": "4-6 weeks" | "6-8 weeks" | "8-12 weeks" | "12+ weeks" | "unknown",
  "next_steps": ["string", ...]
}
```

The remaining 3 schema fields (`intent_completed`, `summary`,
`artifacts`) are routing/metadata only — not part of the owner's
decision surface.

`recommendation` semantics:

- `go` — no fatal flaws, top risks all have known mitigations.
  Owner proceeds to iter-27.
- `go_with_caveats` — no fatal flaws, but 1-2 risks lack mitigation
  and need scoping into iter-27's first sprint.
- `pivot` — at least one risk is high-severity and unresolved; the
  pick is dominated by a backup candidate. Owner returns to the iter-26a
  shortlist.
- `kill` — at least one fatal flaw (entry in `fatal_flaws[]`); the
  niche/idea cannot be salvaged at this constraint envelope.

If `fatal_flaws[]` is non-empty, `recommendation` MUST be `kill` or
`pivot`. QA schema enforces this.

Owner approves with:

```
ai-team approve <id> --comment "decision: go|pivot|kill — <rationale>"
```

The decision rationale lands in `audit_log.events[]` for the review row.

## 5. Agent flow + schemas

### 5.1 TL decomposition

TL receives a new top-level intent `validate_product`. Decomposition
target: 4 subtasks, 3-parallel + 1-gated.

```
MR     validate_competitors     depends_on: []          ─┐
Arch   validate_tech_risk       depends_on: []          ─┤→ QA  synthesize_validation
PM     validate_revenue_model   depends_on: []          ─┘    depends_on: [comp, tech, rev]
```

The 3-way parallel works because MR, Architect, and PM are different
roles. The dispatcher per-role serialization issue (iter-26a discovery
at `core/dispatcher.py:96`) does not apply across roles. QA is gated
on all 3 via `depends_on`.

TL prompt addition (`prompts/team_lead.md`):

```
### Intent: validate_product

When you receive a task with inputs.intent="validate_product", you are
orchestrating diligence on one product candidate (inputs.slug). Decompose
into exactly four subtasks:

1. id="comp", recipient="market_researcher", depends_on=[]
   - inputs: {intent: "validate_competitors", slug, depth,
              candidate_brief, constraints, target_market}
2. id="tech", recipient="architect", depends_on=[]
   - inputs: {intent: "validate_tech_risk", slug, candidate_brief,
              constraints}
3. id="rev", recipient="product_manager", depends_on=[]
   - inputs: {intent: "validate_revenue_model", slug, candidate_brief,
              target_market, constraints}
4. id="synth", recipient="qa_engineer", depends_on=["comp", "tech", "rev"]
   - inputs: {intent: "synthesize_validation", slug,
              upstream_ids: ["comp", "tech", "rev"]}

Extract candidate_brief from the task description (the iter-26a section
body verbatim). Extract target_market from the brief's "Target Buyer"
field. Pass constraints through from the task inputs unchanged.
```

`DECOMPOSITION_SCHEMA` is reused from iter-26a (no changes). The
optional `inputs` field on subtask items (added in commit `68e8c31`)
carries the per-agent intent dispatch.

### 5.2 MR — `validate_competitors`

Mode dispatch in `agents/market_researcher/agent.py` `handle()`:
when `inputs.intent == "validate_competitors"`, use
`VALIDATE_COMPETITORS_SCHEMA`. Otherwise fall through to existing
`brainstorm_niche` / `market_scan` dispatch.

Schema (additions to existing constants):

```python
VALIDATE_COMPETITORS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed", "competitors_found", "pain_signals_found",
        "distribution_feasibility", "verdict", "summary", "artifacts"
    ],
    "properties": {
        "intent_completed": {"const": "validate_competitors"},
        "competitors_found": {"type": "integer", "minimum": 0},
        "pain_signals_found": {"type": "integer", "minimum": 0},
        "distribution_feasibility": {
            "type": "object",
            "additionalProperties": False,
            "required": ["channel_estimate", "audience_reach_estimate", "conversion_to_paid_estimate", "notes"],
            "properties": {
                "channel_estimate": {"type": "string"},
                "audience_reach_estimate": {"type": "string"},
                "conversion_to_paid_estimate": {"type": "string"},
                "notes": {"type": "string"}
            }
        },
        "verdict": {"enum": ["underserved", "saturated", "marginal"]},
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {"type": "array", "items": {"type": "string"}, "minItems": 1}
    }
}
```

`_VALIDATE_DIR = _REPO_ROOT / "docs" / "products"` (write scope:
`docs/products/<slug>/`). Path prefix passed via
`mcp_env["AI_TEAM_PATH_PREFIXES"]` = adds `docs/products/<slug>` to
existing scopes.

`_render_competitors_markdown(response, slug)` writes
`docs/products/<slug>/competitors.md` deterministically from the
validated schema response. LLM may also write via tool-use; deterministic
path is authoritative (same iter-26a pattern).

**Per-call `max_budget_usd` bumped to $5.50** (Sonnet default $0.50
would trip on the $3-5 expected spend for depth=standard). See §11
for the full budget table.

Prompt section (`prompts/market_researcher.md`):

```
### Workflow: validate-competitors mode

When inputs.intent == "validate_competitors":

You are stress-testing one product candidate against its competitive
landscape. The candidate brief (from iter-26a brainstorm) is in
inputs.candidate_brief. Constraints in inputs.constraints. Target
market in inputs.target_market. Depth in inputs.depth (quick=5
competitors, standard=15, deep=30).

Produce three sections:

1. Competitor inventory — depth-scaled rows of:
   {name, URL, positioning, pricing (specific tier), audience size
    estimate, last-shipped-date signal, gap (what they don't do that
    our product would)}.
   Sources via WebFetch on competitor websites; cite URLs.

2. Pain-signal scrape — 5-12 verbatim quotes (depth-scaled) from
   Reddit / Indie Hackers / Twitter / forums where the target buyer
   explicitly asks for this product OR criticizes existing alternatives.
   Each with source URL + date.

3. Distribution feasibility — does the owner's claimed moat hold?
   Estimate channel count, audience reach, and realistic conversion-to-paid
   based on observed patterns in the niche.

Final verdict: "underserved" / "saturated" / "marginal" with one-paragraph
defense.
```

### 5.3 Architect — `validate_tech_risk`

Mode dispatch in `agents/architect/agent.py` `handle()`:
when `inputs.intent == "validate_tech_risk"`, use
`VALIDATE_TECH_RISK_SCHEMA`. Otherwise fall through to existing
architecture-review dispatch.

Schema:

```python
VALIDATE_TECH_RISK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed", "components", "risks_found", "top_risk",
        "llm_opex_at_scale", "build_window_weeks", "verdict",
        "summary", "artifacts"
    ],
    "properties": {
        "intent_completed": {"const": "validate_tech_risk"},
        "components": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "complexity", "dependency", "scaling_limit", "gotchas"],
                "properties": {
                    "name": {"type": "string"},
                    "complexity": {"type": "integer", "minimum": 1, "maximum": 5},
                    "dependency": {"type": "string"},
                    "scaling_limit": {"type": "string"},
                    "gotchas": {"type": "array", "items": {"type": "string"}}
                }
            },
            "minItems": 3,
            "maxItems": 12
        },
        "risks_found": {"type": "integer", "minimum": 0},
        "top_risk": {"type": "string", "maxLength": 500},
        "llm_opex_at_scale": {
            "type": "object",
            "additionalProperties": False,
            "required": ["per_user_per_day_at_100", "per_user_per_day_at_1000", "per_user_per_day_at_10000"],
            "properties": {
                "per_user_per_day_at_100": {"type": "number"},
                "per_user_per_day_at_1000": {"type": "number"},
                "per_user_per_day_at_10000": {"type": "number"}
            }
        },
        "build_window_weeks": {"enum": ["4-6 weeks", "6-8 weeks", "8-12 weeks", "12+ weeks", "unknown"]},
        "verdict": {"enum": ["feasible", "feasible_with_caveats", "blocked"]},
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {"type": "array", "items": {"type": "string"}, "minItems": 1}
    }
}
```

`_render_tech_risk_markdown()` writes `docs/products/<slug>/tech_risk.md`.

**Per-call `max_budget_usd` bumped to $4.50** (Opus default $2.00 may
bite on deep tech reasoning at $2-4 expected spend). See §11.

Prompt section (`prompts/architect.md`):

```
### Workflow: validate-tech-risk mode

When inputs.intent == "validate_tech_risk":

You are stress-testing the technical feasibility of one product candidate.
The brief is in inputs.candidate_brief. Constraints in inputs.constraints.

Sections:

1. Component breakdown — 3-12 components, each with complexity 1-5,
   dependency (3rd-party service / library / API), scaling limit, gotchas.

2. Platform-specific risks — for telegram-tech-publisher specifically:
   - Telegram Bot API rate limits (30 msg/sec to different users,
     1 msg/sec per chat). Validate against expected post volume.
   - Message formatting (Markdown/HTML, code blocks, file attachments).
   - Payment options (Telegram Stars vs Stripe redirect vs invoice link).
   - Webhook vs long-polling tradeoff.
   - Voice-tone calibration approach (few-shot, embeddings, fine-tune).

3. LLM opex model — per-user/day cost at 100/1000/10000 users.
   Identify which user-bucket breaks the $3/user/day ceiling.

4. Build-window estimate — weeks-to-MVP, with breakdown by component.
   Pick from {"4-6 weeks", "6-8 weeks", "8-12 weeks", "12+ weeks", "unknown"}.

5. Top risk — single-sentence description of the highest-impact risk.

Final verdict: "feasible" / "feasible_with_caveats" / "blocked".
```

### 5.4 PM — `validate_revenue_model`

Mode dispatch in `agents/product_manager/agent.py` `handle()`:
when `inputs.intent == "validate_revenue_model"`, use
`VALIDATE_REVENUE_SCHEMA`. Otherwise fall through to existing
PRD-clarification dispatch.

Schema:

```python
VALIDATE_REVENUE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed", "buyer_persona", "addressable_population_estimate",
        "pricing_tiers", "cac_envelope_usd", "ltv_envelope_usd",
        "time_to_first_revenue_weeks", "time_to_1k_mrr_weeks",
        "break_even_users", "revenue_forecast", "verdict",
        "summary", "artifacts"
    ],
    "properties": {
        "intent_completed": {"const": "validate_revenue_model"},
        "buyer_persona": {"type": "string", "maxLength": 1000},
        "addressable_population_estimate": {"type": "string"},
        "pricing_tiers": {
            "type": "array",
            "minItems": 2,
            "maxItems": 4,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "price_usd_monthly", "target_user"],
                "properties": {
                    "name": {"type": "string"},
                    "price_usd_monthly": {"type": "number", "minimum": 0},
                    "target_user": {"type": "string"}
                }
            }
        },
        "cac_envelope_usd": {"type": "number", "minimum": 0},
        "ltv_envelope_usd": {"type": "number", "minimum": 0},
        "time_to_first_revenue_weeks": {"type": "integer", "minimum": 1},
        "time_to_1k_mrr_weeks": {"type": "integer", "minimum": 1},
        "break_even_users": {"type": "integer", "minimum": 1},
        "revenue_forecast": {
            "type": "object",
            "additionalProperties": False,
            "required": ["conservative_mrr_month_6", "base_mrr_month_6", "optimistic_mrr_month_6"],
            "properties": {
                "conservative_mrr_month_6": {"type": "number"},
                "base_mrr_month_6": {"type": "number"},
                "optimistic_mrr_month_6": {"type": "number"}
            }
        },
        "verdict": {"enum": ["viable", "viable_with_caveats", "not_viable"]},
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {"type": "array", "items": {"type": "string"}, "minItems": 1}
    }
}
```

`_render_revenue_markdown()` writes `docs/products/<slug>/revenue.md`.

**Per-call `max_budget_usd` bumped to $3.50** (Sonnet default $0.50
would trip on the $2-3 expected spend). See §11.

Prompt section (`prompts/product_manager.md`):

```
### Workflow: validate-revenue-model mode

When inputs.intent == "validate_revenue_model":

You are stress-testing the monetization model for one product candidate.
Brief in inputs.candidate_brief. Constraints in inputs.constraints.
Target market in inputs.target_market.

Sections:

1. Buyer persona — who specifically buys (role, income bracket,
   currently-paid tools, pain).
2. Addressable population — best-effort size of the niche the buyer
   inhabits.
3. Pricing tiers — 3 tiers (Free / Pro / Power) with monthly USD price
   and target_user for each.
4. CAC envelope — given inputs.constraints.max_paid_acquisition_cost_per_user_usd
   (likely $0 for owner-distributed channels), what's a realistic CAC
   for paid acquisition if the owner channel saturates.
5. LTV envelope — months-to-churn estimate + monthly MRR per paid user.
6. Time to first revenue — weeks from launch to first paying user.
7. Time to $1k MRR — weeks from launch.
8. Break-even — paid-users needed to cover LLM opex + $5k/month owner
   cost-of-time.
9. Revenue forecast at month 6 — conservative / base / optimistic MRR.

Final verdict: "viable" / "viable_with_caveats" / "not_viable".
```

### 5.5 QA — `synthesize_validation`

Mode dispatch in `agents/qa_engineer/agent.py` `handle()`:
when `inputs.intent == "synthesize_validation"`, use
`SYNTHESIZE_VALIDATION_SCHEMA`. Otherwise fall through to existing
`rank_brainstorm_candidates` / `qa_review` dispatch.

QA `handle()` gathers upstream `task_report`s by `subtask_id` ∈
`inputs.upstream_ids` from the bus (existing pattern from iter-26a's
QA aggregation). Reads the 3 markdown artifacts via `read_file`
(no scope change needed — read scope is broader than write scope).

Schema:

```python
SYNTHESIZE_VALIDATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "intent_completed", "recommendation", "confidence",
        "top_risks", "fatal_flaws", "build_window",
        "next_steps", "summary", "artifacts"
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
                    "mitigation": {"type": "string", "maxLength": 500}
                }
            }
        },
        "fatal_flaws": {
            "type": "array",
            "items": {"type": "string", "maxLength": 500},
            "default": []
        },
        "build_window": {"enum": ["4-6 weeks", "6-8 weeks", "8-12 weeks", "12+ weeks", "unknown"]},
        "next_steps": {
            "type": "array",
            "minItems": 1,
            "maxItems": 7,
            "items": {"type": "string", "maxLength": 300}
        },
        "summary": {"type": "string", "maxLength": 2000},
        "artifacts": {"type": "array", "items": {"type": "string"}, "minItems": 1}
    }
}
```

**Cross-field invariant** (enforced in `_build_validation_outputs()`):
if `fatal_flaws[]` is non-empty, `recommendation` MUST be `kill` or
`pivot`. Validate before emitting `task_report`; on mismatch, override
to `kill` and log a warning.

`_render_validation_summary_markdown()` writes
`docs/products/<slug>/_validation_summary.md` with the structured
fields rendered as a top-of-file YAML block plus prose sections.

**Per-call `max_budget_usd` bumped to $2.50** (Sonnet default $0.50
would trip on the $1-2 expected spend; modest headroom for re-reads
of the 3 upstream artifacts). See §11.

Prompt section (`prompts/qa_engineer.md`):

```
### Intent: synthesize_validation

When inputs.intent == "synthesize_validation":

You are synthesizing a build-or-pivot recommendation from three
upstream agent reports (MR, Architect, PM) on one product candidate
(inputs.slug). Read the three artifacts from docs/products/<slug>/.

Sections:

1. Side-by-side verdicts — MR's "underserved/saturated/marginal",
   Architect's "feasible/feasible_with_caveats/blocked", PM's
   "viable/viable_with_caveats/not_viable". Surface conflicts.

2. Cross-cuts — risks that show up in multiple reports OR cross-agent
   risks that don't appear in any single report but emerge from
   combining them (e.g., MR finds competitor X with same moat AND PM
   confirms competitor X has same pricing → moat doesn't hold).

3. Risk register — top 5 risks (deduped across agents), each with
   severity 1-5 and a one-sentence mitigation.

4. Fatal flaws — list specific show-stoppers (Telegram ToS violation,
   already-saturated niche, sub-$0 unit economics, etc.). If empty,
   skip to recommendation.

5. Recommendation — exactly one of:
   - "go" — no fatal flaws, all top risks have mitigations
   - "go_with_caveats" — no fatal flaws, 1-2 risks lack mitigation
   - "pivot" — at least one high-severity risk dominates the pick
   - "kill" — at least one fatal flaw

6. Confidence — 0 (coin-flip) to 5 (highly confident).

7. Next steps — if go: top-3 open questions for iter-27 + suggested
   first-iteration scope. If pivot: top-2 backup candidates from
   docs/products/_candidates/_combined_ranking.md to validate next.
   If kill: what changed in our understanding.

If fatal_flaws is non-empty, recommendation MUST be "kill" or "pivot".
```

## 6. File-write path scopes

Per ADR-004 (least-privilege tool allowlist), add `docs/products/<slug>`
to each agent's `AI_TEAM_PATH_PREFIXES` env var when `inputs.intent`
matches the validation modes. Implementation: the `<slug>` is taken
from `inputs.slug`, validated against `^[a-z][a-z0-9-]{1,50}$`
(kebab-case slug regex from iter-26a), and concatenated to the prefix.

| Agent | Validate intent | Path prefix added |
|---|---|---|
| MR | `validate_competitors` | `docs/products/<slug>` |
| Architect | `validate_tech_risk` | `docs/products/<slug>` |
| PM | `validate_revenue_model` | `docs/products/<slug>` |
| QA | `synthesize_validation` | `docs/products/<slug>` |

If `inputs.slug` fails the regex, the agent BLOCKs with
`BLOCKED(input_validation)` — no path prefix is added, no file is
written. Test coverage: 1 negative test per agent.

## 7. CLI + configuration

### 7.1 `scripts/iter_26b_constraints.json`

```json
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
```

### 7.2 `apps/api/main.py` changes

None. Iter-26a already extended `SubmitTaskRequest` with the optional
`inputs: dict[str, Any] | None` field that propagates to
`TaskAssignmentPayload.inputs`. iter-26b reuses this unchanged.

### 7.3 `apps/cli/main.py` changes

Add `validate_product` subcommand (parallel to `brainstorm_products`):

```python
@cli.command(name="validate-product")
@click.option("--slug", required=True)
@click.option("--candidate-file", required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--depth", type=click.Choice(["quick", "standard", "deep"]), default="standard")
@click.option("--constraints-json", type=click.Path(exists=True, dir_okay=False),
              default="scripts/iter_26b_constraints.json")
@click.pass_context
def validate_product(ctx, slug, candidate_file, depth, constraints_json):
    """Submit a single-candidate validation task."""
    # Read candidate file, extract slug section, parse constraints, POST /api/tasks
```

CLI helper `_extract_candidate_section(file_text: str, slug: str) -> str`:
finds the H2 section whose body contains `**Slug:** <slug>`, returns the
section's full markdown (between its H2 and the next H2). Raises on
not-found.

## 8. Demo script

`scripts/demo_iter_26b.sh` mirrors `scripts/demo_iter_26a.sh` (7-phase
structure):

```
1/7 — Preflight quota check (claude -p ping)
2/7 — Start infra (make up)
3/7 — Apply migrations
4/7 — Start API + dispatcher in background
5/7 — Submit validate-product task (telegram-tech-publisher, depth=standard)
6/7 — Poll for QA pending_review (≤30 min)
7/7 — Collect demo report (audit rows + pending_reviews + artifacts + recommendation preview)
```

**Differences from demo_iter_26a.sh**:

- Poll deadline 30 min (vs 40) — 3-parallel agents don't serialize.
- No auto-approve (same as 26a).
- Phase 6.5 prints QA's `recommendation` field if present in the
  pending_review summary, so the owner sees "go" / "pivot" / "kill"
  at a glance before reading `_validation_summary.md`.
- Submits via `validate-product` subcommand, not `brainstorm-products`.

Stdin EOF safety (iter-26a fix in commit `baff0a8`) carries forward:
`read -r || true` + `[[ -t 0 ]]` tty checks.

## 9. Acceptance criteria

Iter-26b is "done" when all of the following hold for the
`telegram-tech-publisher` validation run:

1. `docs/products/telegram-tech-publisher/competitors.md`,
   `tech_risk.md`, `revenue.md`, `_validation_summary.md` all exist.
2. `_validation_summary.md` has a top-of-file YAML block with
   `recommendation ∈ {go, go_with_caveats, pivot, kill}`.
3. `audit_log` contains the full 5-stage chain (TL decomp + 3 upstream
   `task_report`s from MR/Architect/PM + 1 QA `task_report`) for the
   single correlation_id.
4. ≥1 `pending_review` row for QA's synthesis (2 acceptable per the
   iter-25/26 anomaly).
5. QA's pending_review `report.structured` includes the 6 fields from
   §4.3 (`recommendation`, `confidence`, `top_risks`, `fatal_flaws`,
   `build_window`, `next_steps`).
6. Owner manually approves with
   `ai-team approve <id> --comment "decision: <go|pivot|kill> — <rationale>"`;
   audit_log records the approval event.
7. Unit tests + new validation-mode tests pass. Integration tests still
   green. `make lint`, `make typecheck`, `make sec` (high-only) clean.
8. `make smoke-llm` and `scripts/demo_iter_26b.sh` both succeed in a
   real end-to-end run (gated by owner; not CI).

## 10. Branching outcomes

| QA recommendation | Owner approves with | Next iteration |
|---|---|---|
| `go` / `go_with_caveats` | `decision: go — <rationale>` | **iter-27**: build telegram-tech-publisher MVP in separate repo (ADR-009 TARGET_REPO) |
| `pivot` | `decision: pivot to <next-slug> — <why>` | iter-26b re-runs on next candidate from iter-26a shortlist |
| `kill` | `decision: kill — <what changed>` | Back to iter-26a (different niches, or relaxed constraints) |

Owner can override QA's recommendation in the comment — owner is always
final per CLAUDE.md "AI agents producing task_reports ALWAYS require
owner approval".

## 11. Cost + duration envelope

Per validation run at `depth=standard`:

| Agent | Tier | Expected cost | Per-call `max_budget_usd` | Default | Wall-clock |
|---|---|---|---|---|---|
| MR `validate_competitors` | Sonnet | $3–5 | **$5.50** | $0.50 | 10–15 min |
| Architect `validate_tech_risk` | Opus | $2–4 | **$4.50** | $2.00 | 10–18 min |
| PM `validate_revenue_model` | Sonnet | $2–3 | **$3.50** | $0.50 | 8–12 min |
| QA `synthesize_validation` | Sonnet | $1–2 | **$2.50** | $0.50 | 5–8 min (after upstreams) |
| **Total** | | **$8–14** | **$16.00 ceiling** | — | **15–25 min** |

- Expected spend $8–14 crosses **$5 daily soft warning** intentionally.
- Worst-case all-caps ceiling $16 stays under **$20 daily hard kill**.
- Every agent's default `max_budget_usd` would trip on this iteration —
  the four explicit bumps above (declared on a per-`inputs.intent` basis
  inside each agent module) are required, not optional.
- LLM timeout `llm_timeout_s=600` carries over from iter-26a's
  MR-timeout fix (commit `542168a`) — applied to all 4 validation modes
  to be safe.

## 12. Test plan

### 12.1 Unit tests (mocked LLM)

| File | Coverage |
|---|---|
| `tests/unit/test_cli_validate_product.py` | CLI flags, candidate-section extraction, slug-not-found error |
| `tests/unit/test_team_lead_validate_decomposition.py` | 4-subtask DAG, inputs propagation, depends_on shape |
| `tests/unit/test_market_researcher_validate_competitors.py` | Schema validation, markdown render, slug regex, max_budget=$5.50 bump |
| `tests/unit/test_architect_validate_tech_risk.py` | Schema validation, markdown render, max_budget=$4.50 bump |
| `tests/unit/test_product_manager_validate_revenue.py` | Schema validation, markdown render, max_budget=$3.50 bump |
| `tests/unit/test_qa_synthesize_validation.py` | Schema validation, fatal_flaws cross-field invariant, markdown render, max_budget=$2.50 bump |
| `tests/unit/test_api_submit_task_validate_inputs.py` | API accepts validate_product inputs unchanged |

### 12.2 Integration tests (mocked LLM, real bus + DB)

| File | Coverage |
|---|---|
| `tests/integration/test_iter_26b_e2e_validate.py` | Full chain TL → 3 parallel agents → QA → pending_review. Monkeypatched `_REPO_ROOT` + `_VALIDATE_DIR` to `tmp_path` (iter-26a pattern from commit `94d7d0e`). |

### 12.3 Real-LLM smoke (gated by `--real-llm`)

| File | Coverage |
|---|---|
| `tests/integration/test_validator_one_agent_real_llm.py` | One agent (probably MR `validate_competitors` with depth=quick to bound spend) against real claude -p. Owner runs manually. |

### 12.4 Demo (gated, manual)

`scripts/demo_iter_26b.sh` against real claude -p with
`depth=standard`. Owner runs once per iteration.

## 13. Risks / open questions for iter-26b itself

| # | Risk | Mitigation |
|---|---|---|
| 1 | Architect's tech-risk write may exceed $4.50 per-call cap on deep reasoning. | Monitor first demo run; bump to $6 if needed (carry-over). |
| 2 | MR's pain-signal scrape may hit WebFetch rate limits on Reddit/IH. | Depth=standard caps at 7 signals; if scraping fails, MR emits empty array and notes "scrape_blocked" in distribution_feasibility.notes. |
| 3 | Cross-field invariant (`fatal_flaws ⇒ recommendation ∈ {kill, pivot}`) is enforced in Python only, not JSON schema. | Acceptable for now; deterministic check in `_build_validation_outputs()` overrides if mismatched. Spec-test verifies override. |
| 4 | The 2-pending_reviews-per-QA-turn anomaly carries forward — owner may see 2 review rows for one validation. | Document in acceptance criteria #4. Investigation deferred to stabilization. |
| 5 | Telegram-specific knowledge in Architect prompt is hardcoded for this slug. Future slugs (e.g., `ai-newsletter-digest-bot`) need different prompts. | Spec covers telegram-tech-publisher only. When a different slug enters iter-26b, the platform-specific section in the Architect prompt is updated per slug (or a meta-section is added). Out of scope for this iteration. |

## 14. Carry-overs (NOT addressed in iter-26b)

Carried over from iter-26a retro + earlier handoffs:

- **Dispatcher per-role parallelism** (`core/dispatcher.py:96` — single-task await blocks consume loop). MR's `brainstorm_niche` runs hit this; iter-26b's 3-parallel doesn't because MR/Architect/PM are different roles. Real fix: `asyncio.create_task` + bounded concurrency + tests. Iter-26b would not benefit; the issue resurfaces for `idea-validator` if it ever runs N>1 same-role subtasks in parallel.
- **2-pending_reviews-per-QA-turn anomaly** (iter-25/26 P3) — duplicate row creation. Documented, not blocking.
- **HoldQueue Postgres persistence** — currently in-memory; restarts lose held tasks.
- **GitHubTargetRepo implementation** — ADR-009 stub.
- **BaseAgent.handle() template-method refactor** — agents duplicate dispatch logic.
- **mark_task_done / update_task_status real impls** — currently audit-only.
- **Hash-chain alert job** — `audit_log.prev_hash` chain verifier exists but no monitoring.
- **audit_writer restricted Postgres role** — ADR-005 spec vs. current implementation gap.

All carry-overs are stabilization-phase work, not blockers for iter-26b.

## 15. Out-of-scope deferrals (NOT in iter-26b, may resurface in iter-26b' or iter-27)

- **Multi-candidate iter-26b** (validate top-3 in parallel). Owner explicitly chose single-candidate. If iter-26b returns `pivot`, the next slug enters its own iter-26b run.
- **Customer interviews with real humans**. Validator does SIGNAL scrape only.
- **Live beta signup / waitlist**. Speculative validation only.
- **A/B testing of pricing tiers**. Pricing-tier hypothesis is QA's, not market-validated.
- **Per-slug Architect prompt** (different platform-specific sections). Spec is telegram-tech-publisher-specific; iter-26b' (next slug) updates the prompt section in place or adds a slug-keyed dispatch.
- **Streaming / real-time validation feedback**. Same poll pattern as iter-26a.

## 16. Iteration sequencing

```
iter-26a (DONE 2026-05-22)   → ranked 15 candidates → owner picks telegram-tech-publisher
iter-26b (THIS spec)         → validate one slug    → owner approves go|pivot|kill
  ↓ if go
iter-27 (separate repo)      → build telegram-tech-publisher MVP per ADR-009 TARGET_REPO
  ↓ if pivot
iter-26b'                    → validate next slug from shortlist
  ↓ if kill
iter-26a' or iter-26c        → broader brainstorm or constraint adjustment
```

iter-26b ships entirely inside the `ai_team` framework repo. iter-27
is the first iteration that creates a separate product repo (per
ADR-009) — `ai_team` becomes the framework, iter-27 starts the
product line.

---

**End of design. Implementation plan to follow via writing-plans skill.**
