# `idea-validator` — sandbox spec

> The training task `ai_team` builds during Iterations 1–2 to validate the
> full agent loop (PM → Architect → Backend → QA → owner approval). It
> intentionally exercises every typical software pattern in a small package.

## Concept

A CLI that takes a description of a product idea and emits a structured
opinion: competitors, market estimate, top risks, top differentiators, and
a 1–10 viability score. Output is both human-readable markdown and
machine-readable JSON, so it composes into bigger pipelines.

Downstream value: once `ai_team`'s Market Researcher agent goes live in
later iterations, `idea-validator` becomes its primary internal tool —
this is deliberate dogfooding.

## CLI surface

```
$ idea-validator analyze \
    --idea "Платформа для подбора репетиторов с AI-матчингом" \
    --depth quick|standard|deep \
    --output-dir ./reports

→ creates reports/<slug>-<timestamp>/
  ├── input.json
  ├── competitors.json     # 3-5 competitors with URLs, positioning
  ├── market.md            # estimated TAM/SAM/SOM + reasoning
  ├── risks.md             # top 3 risks ranked
  ├── differentiators.md   # top 3 differentiators
  ├── score.json           # {"score": 6, "components": {...}, "rationale": "..."}
  └── report.md            # composed final report linking the rest
```

Other commands:

```
$ idea-validator list-reports                  # show all reports in cwd
$ idea-validator show <report-id>              # pretty-print one
$ idea-validator compare <id> <id>             # diff two ideas side-by-side
$ idea-validator schema                        # print JSON schemas for outputs
```

## Architecture

A small pipeline of pure-ish stages, each a Python module with one entry
function. All stages produce typed Pydantic outputs and are independently
testable.

```
parse_input  →  competitor_search  →  market_estimate  →  risk_analysis  →
differentiator_analysis  →  scoring  →  report_writer
```

- `parse_input` — load idea text, normalise.
- `competitor_search` — `httpx` against a search API (Brave Search or
  similar; selection TBD by Backend agent). Returns 3–5 entries.
- `market_estimate` — LLM-backed reasoning. Tokens budget capped.
- `risk_analysis` — LLM-backed, structured output.
- `differentiator_analysis` — LLM-backed.
- `scoring` — deterministic combination of upstream signals.
- `report_writer` — assemble markdown.

## Tech

- Python 3.11+, Click, `httpx`, Pydantic v2.
- `pytest`, `respx` for HTTP mocking, mocked LLM client (mirrors
  `core/llm/mock.py` patterns).
- Single `pyproject.toml`, `~/.local/bin/idea-validator` entry point.
- Layout: `examples/sandbox/idea-validator/{src,tests,README.md}`.

## Constraints

- Single binary install: `uv run idea-validator …` from the
  `examples/sandbox/idea-validator/` directory.
- No external service required to *run* (LLM calls go through the same
  `claude -p` substrate as `ai_team` itself; search API call is mocked
  in `--depth quick`).
- Total LOC target: **≤ 300 LOC** for code, plus tests. Don't let agents
  over-engineer it.
- Test coverage ≥ 80 % (same standard as `ai_team`).

## Acceptance criteria for the iteration

The sandbox spec is "done" when:

- PM agent has produced user stories from this spec and dropped them in
  `docs/backlog/idea-validator.md`.
- Architect agent has emitted an ADR or design note linking to it.
- Backend agent has implemented the pipeline with tests.
- QA agent has run the smoke suite and reported pass.
- Owner has approved the resulting PR.

## Why this task

1. **Dogfooding** — becomes a real tool for the Market Researcher agent
   later.
2. **Right size** — small enough to finish in one iteration, big enough
   to exercise PM/Architect/Backend/QA in one loop.
3. **Patterns covered** — CLI parsing, file I/O, async HTTP, LLM calls,
   structured output, Pydantic schemas, error handling, mocked tests.
4. **No frontend distraction** — pure backend, fits the "CLI now,
   Next.js in Iteration 6" plan.
