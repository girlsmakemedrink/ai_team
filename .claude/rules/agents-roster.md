---
paths:
  - "agents/**"
  - "prompts/**"
---

<!-- вынесено из CLAUDE.md 13.09.2026: файл был 344 строки при целевых 200.
     Правило грузится, только когда Клод открывает файлы по paths выше. -->

## Agents (9 + 1 stub)

All agents live on `main` as of iter-25 (2026-05-21). Status =
"shipped + exercised in real-LLM demos". Tier per ADR-006.

| Role | File | Tier | Status |
|------|------|------|--------|
| Team Lead | `agents/team_lead/agent.py` | Opus 4.7 | ✅ live (iter-1) |
| Product Manager | `agents/product_manager/agent.py` | Sonnet 4.6 | ✅ live (iter-1) |
| Architect | `agents/architect/agent.py` | Opus | ✅ live (iter-2) |
| Backend Developer | `agents/backend_developer/agent.py` | Sonnet | ✅ live (iter-2) |
| QA Engineer | `agents/qa_engineer/agent.py` | Sonnet | ✅ live (iter-2) |
| Designer | `agents/designer/agent.py` | Sonnet | ✅ live (iter-2b) |
| Frontend Developer | `agents/frontend_developer/agent.py` | Sonnet | ✅ live (iter-2b) |
| DevOps | `agents/devops/agent.py` | Sonnet | ✅ live (iter-2b) |
| SRE / Support | `agents/sre_support/agent.py` | Sonnet | ✅ live (iter-2b) |
| Market Researcher | `agents/market_researcher/agent.py` | Sonnet | ✅ live (stub, iter-2b) |

Every agent declares (`ClassVar`): `role`, `model_tier`, `allowed_tools`,
`system_prompt_path`. Override `build_outputs(response, incoming)` to
transform LLM response into outbound `AgentMessage`s. Override `handle()`
when you need richer logic (TL and PM both do).

System prompts live in `prompts/<role>.md`. They are flat markdown, loaded
once and cached per agent instance.
