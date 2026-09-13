---
paths:
  - "docs/**"
  - "core/**"
  - "apps/**"
---

<!-- вынесено из CLAUDE.md 13.09.2026: файл был 344 строки при целевых 200.
     Правило грузится, только когда Клод открывает файлы по paths выше. -->

## Key ADRs (`docs/adr/`)

| #   | What it says                                                                       |
|-----|------------------------------------------------------------------------------------|
| 001 | Hybrid orchestrator: custom Python actor system + `claude -p` subprocess substrate |
| 002 | `AgentMessage` Pydantic schema with discriminated-union payload + HMAC field       |
| 003 | Append-only Postgres `audit_log` with `prev_hash` chain; `audit_writer` role       |
| 004 | Per-agent tool allowlist (least-privilege); path-scope wrappers for write tools    |
| 005 | `OWNER_TOKEN` + HMAC for now; mTLS + Vault on Iteration 5 server move              |
| 006 | Tier per agent (haiku/sonnet/opus); --json-schema; budget gates on subscription    |
| 007 | `team_feed` = Pub/Sub + Postgres + SSE; TL emits structured checkpoint digests     |
| 008 | `LLMClient` adapter; `claude -p` primary; Agent SDK stub; **subscription only**    |
| 009 | `TARGET_REPO` abstraction; self-bootstrap is one impl of three                     |

Read in full before touching the architecture. Especially 001, 008, 009.
