---
paths:
  - "core/**"
  - "apps/**"
  - "agents/**"
  - "scripts/**"
  - "tools/**"
  - "tests/**"
---

<!-- вынесено из CLAUDE.md 13.09.2026: файл был 344 строки при целевых 200.
     Правило грузится, только когда Клод открывает файлы по paths выше. -->

## Where to look

```
agents/           # one package per role; _base/ has BaseAgent
apps/api/         # FastAPI app + dispatcher lifespan
apps/cli/         # ai-team CLI
core/audit/       # HMAC + prev_hash chain writer + verifier
core/dispatcher.py
core/llm/         # adapter + backends (headless / mock / stub) + factory
core/messaging/   # AgentMessage schemas, bus (Streams), feed (Pub/Sub + DB)
core/observability/  # structlog + prom metrics
core/persistence/ # SQLAlchemy models + Alembic + audit_writer SQL role
core/security/    # sanitizer, HMAC signer, redaction
core/target_repo/ # ABC; impls land in iter-2
prompts/<role>.md # system prompts per agent (also referenced by class)
tools/mcp_servers/    # ai-team-bus and ai-team-tasks MCP stubs (iter-2)
docs/adr/             # ADRs 0001..0009 (do not skip these)
docs/iterations/      # iter_N.md plan + iter_N_retro.md
docs/sandbox/         # idea_validator_spec.md (training-task surface)
docs/products/_candidates/  # iter-26a+: brainstormed product candidates
                            # from MR. Separate surface from
                            # docs/sandbox/ideas/ (sandbox = team
                            # training; products = real candidate
                            # pool). _combined_ranking.md is QA's
                            # merged shortlist; owner picks top-3 in
                            # the pending_review approval comment.
docs/products/<slug>/       # iter-26b+: per-candidate diligence outputs
                            # from the 4-agent validate-product chain.
                            # competitors.md (MR), tech_risk.md
                            # (Architect), revenue.md (PM),
                            # _validation_summary.md (QA + owner-facing
                            # YAML block with recommendation
                            # go|go_with_caveats|pivot|kill).
                            # Per-candidate dir is the staging ground
                            # between brainstorm and iter-27 build.
infra/docker-compose.yml
scripts/demo_iter_1.sh
```

**External product repos** (iter-27+): the actual product code lives
outside `ai_team`. Per-product GitHub repos under `girlsmakemedrink/<slug>`.
iter-27 = `git@github.com:girlsmakemedrink/telegram-tech-publisher.git`.
ai_team holds the iter spec (`docs/iterations/iter_27.md`) + retro + handoff;
the product repo holds PRD + ADRs + code.
