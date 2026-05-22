# Iter-26a — Market Researcher brainstorm-niche mode

> **Status:** Approved design (2026-05-22). Pending implementation plan
> (writing-plans skill, next step). Owner: solo dev.
>
> **Prerequisite reads:** `CLAUDE.md`, `docs/iterations/iter_25_retro.md`,
> `docs/iterations/iter_26_handoff.md` (strategic option (b) chosen).

## 1. Context

Iter-25 confirmed the framework is architecturally stable (N=2/2
quota-available real-LLM demos reproduced the Backend DONE → QA
`pending_review` chain). The iter-26 handoff opens with a strategic
decision: (a) keep iterating on the sandbox, (b) pivot to a real
monetizable product, (c) stabilization phase. **The owner has chosen
(b).**

Iter-26 is being split into two iterations:

- **iter-26a (this spec)** — use the team itself to generate candidate
  product ideas. Expands Market Researcher with a new "brainstorm-niche"
  mode and runs it across three niches in parallel. Output is a ranked
  list of 15 candidates plus the team's own top-3 shortlist. Owner
  picks 3 to advance to iter-26b.
- **iter-26b (separate spec, later)** — runs the existing
  `idea-validator` chain (PM → Architect → Backend → QA) on the 3
  candidates surviving 26a's owner review. Outputs market scans and a
  winner. iter-27+ implements the winner as a real product in a
  separate repo.

This spec covers **iter-26a only.**

## 2. Goals

1. Use the framework on a new shape of work (research / brainstorm)
   instead of the sandbox build-task it was trained on. This is the
   first real test of generalization beyond `examples/sandbox/idea-validator`.
2. Produce a credible shortlist of monetizable product candidates the
   owner can act on, anchored in evidence from `WebFetch`-sourced
   pages.
3. Promote Market Researcher from "stub used once" to a fully prompted,
   schema-validated agent with two distinct modes.
4. Land iter-26 handoff P1 (CLAUDE.md 429-vs-budget-cap gotcha) and P2
   (pre-demo quota check) along the way — they are cheap and fit
   naturally into this iteration.

## 3. Non-goals

- No `idea-validator` chain run. That is iter-26b.
- No PRD, no product code. That is iter-27+ on a different repo.
- No web UI for browsing candidates. Owner reads Markdown.
- No persistence of MR ranking history. Single demo, one snapshot.
- No carry-over closures (HoldQueue Postgres, GitHubTargetRepo,
  BaseAgent template-method refactor, `mark_task_done` real impl,
  etc.). Those continue to wait — iter-26a is deliberately small.
- No deduplication of candidates that show up in two niches. Owner
  can resolve manually during review.

## 4. Architecture

```
owner ──> ai-team CLI                     #  new sub-command
                │                            "brainstorm-products"
                ▼
          FastAPI submit ──> bus ──> Team Lead
                                       │
                                       │ TL recognises
                                       │ inputs.intent == "brainstorm_products"
                                       │ emits 3 parallel sub-tasks
                                       ▼
                  ┌──────────── Market Researcher (dev_tools) ─────────┐
                  ├──────────── Market Researcher (b2b_smb) ───────────┤
                  └──────────── Market Researcher (creator_tools) ─────┘
                                       │
                                       │ each MR:
                                       │   - WebFetch 3-5 pages
                                       │   - generate 5 candidates
                                       │   - self-score on 5 axes
                                       │   - write file to docs/products/_candidates/
                                       │   - return DONE with JSON in metadata
                                       ▼
                                  Team Lead (rollup)
                                       │
                                       │ all 3 DONE? emit single
                                       │ task_assignment to QA with
                                       │ inputs.intent == "rank_brainstorm_candidates"
                                       ▼
                                  QA Engineer
                                       │
                                       │ - read 3 brainstorm files
                                       │ - schema-validate each candidate
                                       │ - emit combined ranking
                                       │ - file: _combined_ranking.md
                                       ▼
                                 request_human_review
                                       │
                                       ▼
                                 pending_review row
                                       │
                                       ▼
                                 owner reviews,
                                 picks top-3 slugs,
                                 ai-team approve <id> --comment "..."
```

**Key design decisions:**

- Three MR instances run **in parallel** — they share the root
  `correlation_id` (per existing iter-3 chain convention) and are
  distinguished by their `task_id`. The session-id scheme used by
  the LLM adapter is an implementation concern for writing-plans;
  the architectural requirement is that the three MR sessions must
  not collide on `_claimed_sessions` or cross-contaminate prompt
  caches. The iter-2c parallel run (Frontend + Backend + SRE) already
  exercised this path under the current adapter. If we hit an account
  rate limit, fall back is a single config toggle to serial — but the
  cost of the toggle is intentionally NOT in scope.
- MR keeps its existing single-scan mode (used in 26b). New mode is
  selected via `inputs.mode == "brainstorm_niche"` in the
  `TaskAssignmentPayload`. No schema migration — `inputs` is already a
  free-form `dict[str, Any]`.
- QA is reused (no new role). QA's existing rank/review capability is
  extended with a branch for `inputs.intent == "rank_brainstorm_candidates"`.
- Owner approval gate is the existing `pending_review` flow shipped
  in iter-18. No new surface.
- Candidates land in **a new directory** `docs/products/_candidates/`
  (not the sandbox `docs/sandbox/ideas/`). This separates real product
  work from training material. Requires extending MR's
  `AI_TEAM_PATH_PREFIXES` env to `docs/sandbox/ideas,docs/market,docs/products`.

## 5. Components

### 5.1 CLI: `ai-team brainstorm-products`

New Click sub-command in `apps/cli/main.py`. ~30 lines, a thin wrapper
over the existing `ai-team submit` path.

```
ai-team brainstorm-products
    --niches dev_tools,b2b_smb,creator_tools
    --candidates-per-niche 5
    --constraints-json scripts/iter_26a_constraints.json
```

Reads the JSON, builds a `TaskAssignmentPayload`, submits it via the
existing FastAPI `/api/tasks/submit`. Prints the root `correlation_id`
so the owner can watch it via `ai-team watch <id>`.

Example constraints JSON (`scripts/iter_26a_constraints.json`):
```json
{
  "solo_developer": true,
  "max_product_llm_opex_usd_per_day": 3,
  "monetization_preferences": ["subscription", "per-seat", "usage"],
  "max_time_to_first_revenue_months": 6,
  "defensibility_floor": "minimal moat acceptable; user-distribution moat ok",
  "owner_expertise_hint": "Python backend, AI/agent systems, Russian-speaking"
}
```

### 5.2 Root task → Team Lead

```python
TaskAssignmentPayload(
    title="Brainstorm monetizable product candidates",
    description=("Decompose into 3 parallel sub-tasks to market_researcher, "
                 "one per niche. After all DONE, route ranking task to "
                 "qa_engineer. Constraints below."),
    inputs={
        "intent": "brainstorm_products",
        "niches": ["dev_tools", "b2b_smb", "creator_tools"],
        "candidates_per_niche": 5,
        "constraints": { ...same as 5.1 JSON... },
    },
)
```

### 5.3 Team Lead — prompt extension

Add one section to `prompts/team_lead.md`:

> ### Intent: brainstorm_products
>
> When the incoming `task_assignment.inputs.intent == "brainstorm_products"`,
> emit one `task_assignment` to `market_researcher` per niche in
> `inputs.niches`. Each sub-task's `inputs` is:
>
>     {
>       "mode": "brainstorm_niche",
>       "niche": "<one of inputs.niches>",
>       "candidates": <inputs.candidates_per_niche>,
>       "constraints": <inputs.constraints>
>     }
>
> Sub-tasks have no `depends_on` between them — they run in parallel.
> When all `market_researcher` reports come back DONE, emit ONE
> `task_assignment` to `qa_engineer` with `inputs.intent == "rank_brainstorm_candidates"`,
> `inputs.brainstorm_artifacts` = list of the 3 artifact paths, and
> `depends_on` = list of the 3 MR sub-task ids. Do not emit a Backend
> or Architect step.

### 5.4 Market Researcher — brainstorm-niche mode

`agents/market_researcher/agent.py` gets a second code path keyed off
`incoming.payload.inputs.get("mode")`. Existing single-scan mode is
unchanged.

New mode workflow:
1. Overwrite-on-rerun: if a brainstorm file for this niche already
   exists, overwrite it with the fresh result. No append-mode and no
   cross-run accumulation — single-shot demo (cf. non-goal: no
   persistence of MR ranking history). Owner triggers a fresh run for
   a re-roll.
2. `WebFetch` 3-5 relevant pages (vendor sites, complaint forums,
   Indie Hackers, Reddit threads, "what's missing in X" articles).
   Failure to fetch = log + continue with remaining sources.
3. Generate 5 candidates, each independently — must be distinguishable
   ideas, not 5 variations of one idea (enforced by prompt language).
4. Self-score each candidate on the 5 axes (see schema, section 6).
5. Produce the team's own top-3 shortlist by `composite_score`
   descending; ties broken by `defensibility` then `solo_fit`.
6. Write `docs/products/_candidates/_brainstorm_<niche>.md` via
   `write_file_in_scope`. Markdown rendering mirrors the JSON for
   owner-readability.
7. Return `task_report` DONE with the validated JSON in
   `metadata.llm.structured` (already standard).

Prompt addition (in `prompts/market_researcher.md`):

> ### Workflow: brainstorm-niche mode
>
> Selected when `inputs.mode == "brainstorm_niche"`. Inputs you receive:
> `niche` (one of `dev_tools | b2b_smb | creator_tools`), `candidates`
> (integer, expected 5), `constraints` (structured object — see below).
>
> Constraints object example:
>
>     {
>       "solo_developer": true,
>       "max_product_llm_opex_usd_per_day": 3,
>       "monetization_preferences": ["subscription", ...],
>       "max_time_to_first_revenue_months": 6,
>       ...
>     }
>
> All five candidates must respect the constraints. A candidate that
> needs three engineers to ship in twelve months violates
> `solo_developer + max_time_to_first_revenue_months: 6` and must not
> be proposed.
>
> Score every candidate on exactly five axes (1-5 each):
> - `tam_signal` — is there evidence of paying demand?
> - `solo_fit` — can one developer ship it in the time budget?
> - `llm_opex_fit` — does steady-state LLM cost per user respect the
>   `max_product_llm_opex_usd_per_day` ceiling?
> - `defensibility` — distribution, data, or workflow lock-in?
> - `time_to_first_revenue` — 5 means TTFR ≤ `max_time_to_first_revenue_months`,
>   1 means TTFR > 2× that ceiling.
>
> `composite_score = sum of the 5 axes` (max 25).
>
> Return JSON only — `BRAINSTORM_NICHE_SCHEMA` will validate.

### 5.5 QA Engineer — rank-brainstorm mode

`agents/qa_engineer/agent.py` gets a branch on
`incoming.payload.inputs.get("intent") == "rank_brainstorm_candidates"`.
Workflow:
1. Read the 3 brainstorm artifacts from
   `inputs.brainstorm_artifacts`.
2. Parse each file's JSON (mirror in Markdown), schema-check against
   `BRAINSTORM_NICHE_SCHEMA`. Any failure → emit FAILED task_report
   with the offending file + reason. Owner can re-trigger that niche.
3. Build a merged ranking: all 15 candidates sorted by
   `composite_score` desc.
4. Write `docs/products/_candidates/_combined_ranking.md` containing
   the merged sorted table + a "team top-3 from each niche" section
   (reproduces each MR's own top-3) for owner cross-reference.
5. Emit `request_human_review` referencing the ranking file.

QA prompt addition is one paragraph mirroring 5.4's intent-branch
language. No new tools needed — QA already has `Read`, `Glob`, and
`write_file_in_scope` on its allowlist.

### 5.6 Owner review

Standard `pending_review` flow from iter-18. Owner runs
`ai-team approve <id> --comment "top-3: <slug-1>, <slug-2>, <slug-3>"`.
The comment becomes the input to iter-26b. **No schema enforcement on
the comment in 26a** — iter-26b parses it and fails fast if it cannot
extract 3 slugs. Keeping 26a lightweight.

## 6. Schema — `BRAINSTORM_NICHE_SCHEMA`

```json
{
  "type": "object",
  "required": ["niche", "candidates", "researcher_top_3_slugs",
               "research_sources_used"],
  "additionalProperties": false,
  "properties": {
    "niche": {
      "type": "string",
      "enum": ["dev_tools", "b2b_smb", "creator_tools"]
    },
    "candidates": {
      "type": "array",
      "minItems": 5, "maxItems": 5,
      "items": {
        "type": "object",
        "required": ["title", "slug", "one_paragraph", "target_buyer",
                     "monetization", "known_competitors", "scores",
                     "composite_score", "rationale"],
        "additionalProperties": false,
        "properties": {
          "title":         {"type": "string", "minLength": 1, "maxLength": 120},
          "slug":          {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"},
          "one_paragraph": {"type": "string", "minLength": 1, "maxLength": 1500},
          "target_buyer":  {"type": "string", "minLength": 1, "maxLength": 300},
          "monetization": {
            "type": "string",
            "enum": ["subscription", "per-seat", "usage", "one-time", "freemium"]
          },
          "known_competitors": {
            "type": "array",
            "items": {
              "type": "object",
              "required": ["name", "positioning"],
              "additionalProperties": false,
              "properties": {
                "name":        {"type": "string"},
                "url":         {"type": "string"},
                "positioning": {"type": "string"}
              }
            }
          },
          "scores": {
            "type": "object",
            "required": ["tam_signal", "solo_fit", "llm_opex_fit",
                         "defensibility", "time_to_first_revenue"],
            "additionalProperties": false,
            "properties": {
              "tam_signal":            {"type": "integer", "minimum": 1, "maximum": 5},
              "solo_fit":              {"type": "integer", "minimum": 1, "maximum": 5},
              "llm_opex_fit":          {"type": "integer", "minimum": 1, "maximum": 5},
              "defensibility":         {"type": "integer", "minimum": 1, "maximum": 5},
              "time_to_first_revenue": {"type": "integer", "minimum": 1, "maximum": 5}
            }
          },
          "composite_score": {"type": "integer", "minimum": 5, "maximum": 25},
          "rationale":       {"type": "string", "minLength": 1, "maxLength": 1500}
        }
      }
    },
    "researcher_top_3_slugs": {
      "type": "array",
      "minItems": 3, "maxItems": 3,
      "items": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$"}
    },
    "research_sources_used": {
      "type": "array",
      "items": {"type": "string"}
    }
  }
}
```

The schema lives in `agents/market_researcher/agent.py` next to the
existing `MARKET_SCAN_SCHEMA`. The slugs in `researcher_top_3_slugs`
must match three of the slugs in `candidates`; this is asserted in
`build_outputs`, not the schema (out-of-schema cross-validation).

## 7. Demo

`scripts/demo_iter_26a.sh`:

1. **Pre-demo quota check** — `claude -p "Reply with exactly: pong"`.
   If the response is empty or contains `api_error_status=429`, abort
   with message: "Max-5x session limit hit. Reset time per the API
   log: <line>. Re-run after reset, or `ai-team retry-blocked` to
   resume a previously-blocked chain." This is iter-26 handoff P2.
2. `make up` — Postgres + Redis via docker compose.
3. Start FastAPI + dispatcher.
4. Submit:
   `ai-team brainstorm-products --niches dev_tools,b2b_smb,creator_tools --candidates-per-niche 5 --constraints-json scripts/iter_26a_constraints.json`
5. Watch (poll `tasks` and `audit_log` every 5s for up to 15 min):
   - 3 MR `task_report` rows with status=DONE
   - 1 QA `task_report` row with status=DONE
   - 1 `request_human_review` row in `pending_reviews`
6. **60s post-success drain** (iter-25 lesson — let audit_writer
   finish).
7. Demo report SQL (same shape as iter-3):
   ```sql
   SELECT id, sender, recipient, message_type,
          payload_json->'metadata'->'llm'->>'model'              AS model,
          (payload_json->'metadata'->'llm'->>'tokens_in')::int   AS tokens_in,
          (payload_json->'metadata'->'llm'->>'tokens_out')::int  AS tokens_out,
          (payload_json->'metadata'->'llm'->>'cached_input')::int AS cached_input,
          (payload_json->'metadata'->'llm'->>'cost_cents')::int  AS cost_cents,
          (payload_json->'metadata'->'llm'->>'duration_ms')::int AS duration_ms
   FROM audit_log WHERE correlation_id = :cid ORDER BY id;
   ```
8. Dump 4 artifacts to the demo report:
   `docs/products/_candidates/_brainstorm_dev_tools.md`,
   `_brainstorm_b2b_smb.md`,
   `_brainstorm_creator_tools.md`,
   `_combined_ranking.md`.

## 8. Acceptance criteria

The iter-26a demo is **done** when **all** of the following hold:

1. `audit_log` contains the full chain for a single `correlation_id`:
   1 root task → 3 MR assignments → 3 MR DONE reports → 1 QA
   assignment → 1 QA DONE → 1 `request_human_review`.
2. Each of the 3 brainstorm files exists, contains 5 candidates,
   passes `BRAINSTORM_NICHE_SCHEMA`, and `composite_score` equals the
   sum of the five axis scores.
3. `_combined_ranking.md` exists and lists 15 candidates sorted by
   composite_score descending.
4. A `pending_review` row exists, summarizing the ranking, awaiting
   owner approval.
5. The per-message SQL shows non-zero `tokens_in` and `cost_cents`
   for TL, all 3 MRs, and QA.
6. Total LLM spend across the demo is ≤ $5 (soft warning ceiling).

## 9. Tests

- **Unit** (mocked LLM, no infra):
  - `tests/unit/test_market_researcher_brainstorm_mode.py` — given
    `inputs.mode == "brainstorm_niche"`, MR uses
    `BRAINSTORM_NICHE_SCHEMA`, writes file to
    `docs/products/_candidates/`, asserts
    `researcher_top_3_slugs ⊆ candidate slugs`, fails cleanly on
    malformed LLM response.
  - `tests/unit/test_team_lead_brainstorm_decomposition.py` — TL with
    `inputs.intent == "brainstorm_products"` emits N sub-task
    assignments with correct per-niche `inputs.mode` and no
    `depends_on` between them; emits one QA assignment after all 3
    DONE with `depends_on` = those 3 task_ids.
  - `tests/unit/test_qa_rank_brainstorm.py` — QA with intent
    `rank_brainstorm_candidates` reads 3 files via `Glob`, merges,
    sorts, writes `_combined_ranking.md`, emits
    `request_human_review`.
- **Integration** (testcontainers Postgres+Redis, mocked LLM):
  - `tests/integration/test_iter_26a_e2e_brainstorm.py` — submit a
    root brainstorm task with `MockLLMClient` returning canned
    candidates; assert full audit chain + `pending_review` row.
- **Real-LLM** (gated by `@pytest.mark.real_llm`, not in CI):
  - `tests/real_llm/test_mr_brainstorm_one_niche.py` — one niche, 2
    candidates (cheap variant). Used for adversarial prompt-testing,
    not regression.
- Coverage gate stays at 80 % diff-cover. The new branches in MR/TL/QA
  are unit-testable with mocked LLM, so the gate is achievable.

## 10. Cost estimate

| Component          | Tier   | Est. cost   |
|--------------------|--------|-------------|
| TL decomposition   | Opus   | ~$0.15      |
| 3 × MR brainstorm  | Sonnet | ~$1.50-$2.40 (WebFetch + reasoning, $0.50-$0.80 each) |
| QA rank            | Sonnet | ~$0.20      |
| TL rollup          | Opus   | ~$0.05      |
| **Total**          |        | **~$2-3**   |

Budget per CLAUDE.md: $5/day soft warning, $20/day hard kill. iter-26a
fits comfortably under soft warning even with one retry.

## 11. Risks

- **R1 (medium):** WebFetch returns paywall, captcha, or empty body
  (known from iter-2c). MR must continue with remaining sources and
  log the skip. Validated by unit test that injects a 403 response.
- **R2 (low):** TL prompt does not recognize the new
  `intent: brainstorm_products` branch. Mitigated by the dedicated
  unit test in section 9; if it slips to demo, prompt is iterable
  per the standard plan-before-code loop.
- **R3 (low):** 3 parallel `claude -p` processes hit a per-account
  rate limit. Worked in iter-2c (3 parallel agents); if it breaks
  here, fall back to serial via a `parallelism: 1` config toggle.
  Toggle work is **not** scoped into 26a.
- **R4 (subjective):** Candidate quality is owner-judgement, not
  automated. If all 15 are mush, 26a is still valuable as
  process-validation (TL + MR + QA on a new shape) but does not seed
  26b. Recovery: tighten MR prompt, re-run one niche at a time
  (~$0.50-$0.80 each).
- **R5 (env, not architectural):** Max-5x session 429 mid-demo. Pre-
  demo quota check (section 7 step 1) prevents starting a doomed run;
  iter-15's `BLOCKED(budget)` synthesis handles a mid-flight 429.
  Recovery: wait for reset, `ai-team retry-blocked`.

## 12. Out-of-scope improvements (deferred)

These are valuable but explicitly NOT in iter-26a:

- Serial-fallback toggle for parallel MR (R3).
- Persistence of brainstorm history across runs.
- Cross-niche deduplication of candidate ideas.
- Idea-validator integration (that **is** iter-26b).
- Carry-overs from iter-25 (HoldQueue Postgres, GitHubTargetRepo,
  BaseAgent template-method refactor, `mark_task_done` real impl,
  hash-chain alert, `audit_writer` restricted role, etc.).

## 13. Deliverables

1. `agents/market_researcher/agent.py` — second mode branch in
   `handle()` / `build_outputs()`; new schema.
2. `prompts/market_researcher.md` — brainstorm-niche workflow section.
3. `agents/team_lead/agent.py` — handle the new intent (or, depending
   on TL's existing structure, just prompt extension).
4. `prompts/team_lead.md` — intent: brainstorm_products section.
5. `agents/qa_engineer/agent.py` — rank-brainstorm branch.
6. `prompts/qa_engineer.md` — rank-brainstorm-candidates intent
   section.
7. `apps/cli/main.py` — `brainstorm-products` sub-command.
8. `scripts/demo_iter_26a.sh` — demo script with quota check.
9. `scripts/iter_26a_constraints.json` — default constraints input.
10. `tests/unit/test_market_researcher_brainstorm_mode.py`
11. `tests/unit/test_team_lead_brainstorm_decomposition.py`
12. `tests/unit/test_qa_rank_brainstorm.py`
13. `tests/integration/test_iter_26a_e2e_brainstorm.py`
14. `tests/real_llm/test_mr_brainstorm_one_niche.py` (real_llm-marked)
15. `docs/iterations/iter_26a.md` — plan doc (written by
    writing-plans skill from this spec).
16. CLAUDE.md update — flag `docs/products/_candidates/` as the
    real-product candidates surface (one paragraph in "Where to look").
17. Update `core/config.py` (or wherever `AI_TEAM_PATH_PREFIXES`
    defaults live) to extend MR's path scope to include
    `docs/products`.

## 14. Open questions for the implementation plan

These do not block design approval, but writing-plans should address
them:

- Q1: Does TL emit the QA rollup task itself, or does the dispatcher
  detect "all sub-tasks DONE" and trigger it? Current iter-3..25
  pattern is TL-driven. Keep that; flag if it doesn't fit.
- Q2: If one MR fails (e.g. WebFetch outage), does QA still run on
  the surviving 2 niches, or does the whole iteration go BLOCKED?
  Recommend: QA still runs; ranking covers fewer candidates; owner
  decides whether to re-trigger.
- Q3: Should `BRAINSTORM_NICHE_SCHEMA` allow `additionalProperties`
  in `known_competitors` items so MR can include `pricing` or
  `last_funded` opportunistically? Recommend: no — keep strict; if
  pricing matters, add a field explicitly.

## 15. Approval

Design approved by owner via brainstorming dialog on 2026-05-22.
Next step: invoke writing-plans skill to produce
`docs/iterations/iter_26a.md` (the implementation plan).
