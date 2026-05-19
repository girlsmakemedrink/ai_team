# `idea-validator` v2 — sandbox spec (iter-3 demo extension)

> Iter-3 extends the iter-2 idea-validator with two surfaces — a one-page
> web docs landing page and a Designer-written CLI UX brief — so the
> demo exercises **Designer → Frontend → QA** for the first time on top
> of the existing PM → Architect → Backend → QA chain.
>
> The iter-2 v1 spec (`idea_validator_spec.md`) remains the regression
> baseline; this file is read **only** by `scripts/demo_iter_3.sh`. The
> v1 spec is unchanged.

## Concept

Same as v1 (`idea_validator_spec.md`): a CLI that takes a product idea
and emits competitors, market estimate, risks, differentiators, and a
viability score in both Markdown and JSON.

## What's new in v2

Beyond the v1 CLI:

1. **A static landing page** at `apps/web/idea-validator/index.html` —
   single self-contained HTML file, no JS framework, ~80 lines. Describes
   the tool, shows a sample report rendered inline, and links to the CLI
   install instructions. Plain CSS only (no Tailwind, no React); the
   "frontend" here is one page Frontend can ship without a backend
   handshake.

2. **A Designer-written CLI UX brief** at `docs/design/idea-validator.md`
   — captures how the CLI's text output should be structured for
   readability: section headers, color conventions, table formatting,
   what's loud vs. quiet. Frontend reads this brief and reflects the
   same visual language in the landing page.

## Decomposition target (what TL should emit)

A 5–6 subtask DAG. **Use `depends_on` to express the ordering.**
Stages where work cannot meaningfully start until the predecessor
artifact exists must declare the dep.

```
pm_clarify (PM)            depends_on: []
  ↓
arch (Architect)           depends_on: [pm_clarify]
  ├── be (Backend)         depends_on: [arch]
  └── design (Designer)    depends_on: [arch]
        ↓
        fe (Frontend)      depends_on: [design]
                ↓
                qa (QA)    depends_on: [be, fe]
```

Recipients:
- `pm_clarify` → `product_manager` — produces user stories +
  acceptance criteria in `docs/backlog/idea-validator.md`.
- `arch` → `architect` — emits ADR referencing v1 spec, plus the v2
  landing page surface.
- `be` → `backend_developer` — implements the pipeline at
  `examples/sandbox/idea-validator/{src,tests}/` per v1.
- `design` → `designer` — writes the CLI UX brief at
  `docs/design/idea-validator.md`.
- `fe` → `frontend_developer` — writes the landing page at
  `apps/web/idea-validator/index.html`, reading the brief.
- `qa` → `qa_engineer` — runs the backend test suite and visually
  spot-checks the landing page renders.

## Acceptance criteria for the iter-3 demo

The iter-3 demo is "done" when:

- `audit_log` contains the full 6-stage chain (one assignment + one
  done report per recipient) for the single correlation_id.
- `tasks` table shows the root task flipped to `done` (Phase 3 rollup).
- A `pending_review` row exists for QA's final report.
- The per-message demo report SQL query (see below) returns rows for
  every agent with non-zero `tokens_in` + `cost_cents`.

## Tech constraints (carry over from v1)

- Same `examples/sandbox/idea-validator/` layout for backend code.
- Frontend file is a single HTML file, plain CSS, no JS bundler.
- Designer brief is plain Markdown — no Figma export.
- Test coverage on the backend ≥ 80 % (v1 standard).

## Per-message demo report SQL

```sql
SELECT
    id,
    sender,
    recipient,
    message_type,
    payload_json -> 'metadata' -> 'llm' ->> 'model'                       AS model,
    (payload_json -> 'metadata' -> 'llm' ->> 'tokens_in')::int            AS tokens_in,
    (payload_json -> 'metadata' -> 'llm' ->> 'tokens_out')::int           AS tokens_out,
    (payload_json -> 'metadata' -> 'llm' ->> 'cached_input')::int         AS cached_input,
    (payload_json -> 'metadata' -> 'llm' ->> 'cost_cents')::int           AS cost_cents,
    (payload_json -> 'metadata' -> 'llm' ->> 'duration_ms')::int          AS duration_ms,
    (payload_json -> 'metadata' -> 'llm' ->> 'validated_against_schema')  AS schema_ok
FROM audit_log
WHERE correlation_id = :cid
ORDER BY id;
```

The iter-3 demo report is one paste of this query's output — no
structlog grep.
