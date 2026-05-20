# idea-validator

Analyse a product idea for market viability from the command line.
Outputs competitors, market sizing, risks, differentiators, and a score.

## Install

```bash
cd examples/sandbox/idea-validator
uv pip install -e ".[dev]"
```

## Quick start (offline, no API keys)

```bash
idea-validator analyze \
  --idea "AI tutoring marketplace" \
  --depth quick \
  --output-dir ./reports
```

Output goes to `reports/<slug>-<timestamp>/` containing seven files:
`input.json`, `competitors.json`, `market.md`, `risks.md`,
`differentiators.md`, `score.json`, `report.md`.

## Depth modes

| Flag | LLM | Search | Use |
|------|-----|--------|-----|
| `--depth quick` | mock | stub list | CI / offline |
| `--depth standard` | real (`IDEA_VALIDATOR_REAL_LLM=1`) | Brave (`BRAVE_API_KEY`) | normal |
| `--depth deep` | real | Brave | thorough |

For `standard` / `deep` set environment variables:

```bash
export IDEA_VALIDATOR_REAL_LLM=1
export BRAVE_API_KEY=<your-key>
idea-validator analyze --idea "AI tutoring marketplace" --depth standard
```

## Other commands

```bash
idea-validator list-reports            # list all saved reports
idea-validator show <report-id>        # pretty-print one report
idea-validator compare <id-1> <id-2>   # side-by-side score diff
idea-validator schema                  # print JSON schemas for all DTOs
```

## Tests

```bash
pytest tests/ --cov=idea_validator
```

Coverage gate: ≥ 80 %.

## Refresh committed sample

```bash
bash scripts/refresh_sample.sh
```

Regenerates `sample/` using mock LLM and stub search (deterministic).
