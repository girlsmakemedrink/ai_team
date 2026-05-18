# ADR-0003 — Audit log strategy

- **Status**: Accepted
- **Date**: 2026-05-18

## Context

Every message and every tool call performed by an agent must be auditable
after the fact. We need:

- **Provenance** — who said what, when.
- **Tamper-evidence** — silent modification of the log must be detectable.
- **Replay** — the entire decision history of an iteration must be
  reconstructible from the log.
- **Compliance-readiness** — when (not if) we sell to a customer who asks,
  we should be able to point at an immutable trail.

Trade-offs:

- **Compromised agent ≠ compromised infra.** The MVP threat model assumes
  the owner controls the host. An agent gone rogue (prompt injection,
  hallucination) shouldn't be able to silently rewrite history, but an
  attacker with `psql` superuser can do anything — that's outside our scope
  for the personal-machine phase.
- We accept that **stronger isolation** (separate immutable store like S3
  Object Lock, separate hardened DB instance) is a post-MVP migration once
  there are multiple humans with system access.

## Decision

**Phase 1 (MVP, this iteration through Iteration 5):**

1. `audit_log` lives in the same Postgres instance as everything else.
2. Append-only at the SQL level:
   - Separate role `audit_writer` granted **only** `INSERT` on `audit_log`.
   - Application connects as `audit_writer` for writes; reads happen via a
     different role with `SELECT`.
   - No `UPDATE` or `DELETE` privilege exists for application roles.
3. Each row carries `prev_hash` linking to the previous row's `hmac_hash`
   value — a chain.
4. `hmac_hash` = `HMAC-SHA256(HMAC_SECRET, canonical_json(row_without_hash) || prev_hash)`.
5. A periodic verifier job recomputes the chain over a configurable window
   (default last 24 h) and writes a `chain_ok=true|false` row in
   `audit_log_verifications`. Mismatch → `P1` alert.
6. Backup snapshot of `audit_log` shipped daily to an off-host location
   (configured in Iteration 5; for now, local `pg_dump` artifact retained
   ≥ 30 days).

**Phase 2 (stretch, post-Iteration 6):**

- Migrate `audit_log` writes to S3 Object Lock (or equivalent) in addition
  to Postgres; Postgres becomes the queryable mirror, S3 becomes the
  immutable source.

### Schema

```sql
CREATE TABLE audit_log (
    id            BIGSERIAL PRIMARY KEY,
    timestamp     TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_id UUID NOT NULL,
    sender        TEXT NOT NULL,
    recipient     TEXT NOT NULL,
    message_type  TEXT NOT NULL,
    priority      TEXT NOT NULL,
    iteration     INTEGER,
    payload_json  JSONB NOT NULL,          -- full, unredacted
    hmac_sig      TEXT NOT NULL,           -- sender's HMAC on payload
    prev_hash     TEXT,                    -- previous row's hmac_hash
    hmac_hash     TEXT NOT NULL,           -- HMAC over canonical row + prev_hash
    INDEX (correlation_id, timestamp),
    INDEX (sender, timestamp)
);

CREATE TABLE audit_log_verifications (
    id        BIGSERIAL PRIMARY KEY,
    window_start_id BIGINT NOT NULL,
    window_end_id   BIGINT NOT NULL,
    verified_at     TIMESTAMPTZ NOT NULL,
    chain_ok        BOOLEAN NOT NULL,
    notes           TEXT
);
```

### What goes in the audit log

- Every `AgentMessage` after HMAC verification.
- Every tool invocation (tool name, params, return summary, agent id, time).
- Every human approval decision (approve/reject + comment).
- Every checkpoint digest emitted by Team Lead.
- Schema-version migrations.

### What does **not** go in

- LLM raw chain-of-thought / thinking blocks (those go to trace logs for
  debugging; not part of the audit story).
- Heartbeat messages and metrics scrape requests.
- Internal bus housekeeping (XACK, consumer group rebalance).

## Consequences

### Positive

- Strong tamper-evidence on a single Postgres without adding S3 dependency
  on day one.
- `INSERT`-only role removes ~90 % of accidental-mutation risk even before
  the hash chain catches the rest.
- Verifier job runs on a schedule and surfaces tampering as a `P1`,
  routing to SRE/Support agent automatically.
- Schema is replayable: from any `correlation_id` you can reconstruct the
  full task tree by SELECTing in `timestamp` order.

### Negative

- Hash-chain verification cost: O(N) per scan; with bounded window (24 h)
  this is bounded and fine.
- The `HMAC_SECRET` becomes a high-value secret. Compromise allows forging
  *new* tail entries but does **not** allow rewriting old ones without
  also rewriting every dependent prev_hash forward. Mitigation: secret in
  Vault (Iteration 5), rotated annually.
- Rich payloads in `JSONB` mean the audit table grows fast. Partitioning by
  month is planned for Iteration 5.

### Neutral

- We're not on S3 Object Lock yet. Documented as a follow-up; the migration
  path is straightforward and the schema is designed for it.

## Alternatives considered

- **Plain CSV log files.** Rejected — no queryability, easy to lose
  partial writes, no enforced append-only semantics.
- **Separate audit DB instance from day one.** Rejected for MVP — adds
  operational complexity (another container, another credential, another
  backup) for a personal-machine deployment. Revisit in Iteration 5.
- **Blockchain-style cryptographic notarization.** Rejected — overkill,
  hard to operate, vendor-locks.
- **Postgres logical replication to an immutable mirror.** Considered for
  Phase 2; tracked separately.

## References

- [ADR-002 — Message schema][ADR-002] (signs each message)
- [ADR-005 — Auth & secrets][ADR-005] (where HMAC_SECRET lives)
- Postgres docs on roles & GRANT.

[ADR-002]: 0002-message-schema.md
[ADR-005]: 0005-auth-secrets.md
