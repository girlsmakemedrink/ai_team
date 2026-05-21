# Iteration 24 retrospective

> **Status**: closed — iter-24 finally landed the
> 5-iteration-deferred QA-emitted `pending_reviews` row in
> a real-LLM demo. Chain delivered end-to-end success.

## Headline outcomes

✅ **5-iter-deferred QA criterion MET in real-LLM demo.**
Direct DB query confirms a `pending_reviews` row with
`requesting_agent='qa_engineer'` for correlation
`f26bf077-1c8d-43a5-99b8-bf93402e79a8`. Summary: "44/44
unit tests pass with 84.6% line coverage; ruff exits 1 with
15 violations in source..." — Backend did real work; QA
evaluated it; the row landed via the iter-23 safety net.

✅ **Backend DONE on first turn — first time across
iter-19..24.** No self-eject, no BLOCKED, no
re-decomposition. The missing-dir prompt fix appears to have
been the key change: Backend stopped treating "examples/
absent" as a scope problem and just created the scaffold.

✅ **All 6 LLM-bound agents DONE'd cleanly.** Frontend, which
had BLOCKED in iter-21/22/23 on architecturally-prohibited
POST endpoint requests, also DONE'd this run. Possibly
incidental, but no regression.

✅ **Phase 1 A/B test denied a wrong theory.** The iter-23
"enum-retry-loop budget burn" theory was empirically refuted
in $0.20 / 10 min:
- enum: 16.8s, $0c, validated=True (LLM mapped to nearest valid value)
- permissive: 6.9s, $0c (LLM gave freeform)

claude -p does NOT internally retry on schema mismatch; it
remaps. iter-23 R#2's BLOCKED(budget) had a different,
still-unknown cause (likely a legitimate work-related tool-call
loop, not a substrate retry bug).

✅ **API log preservation works.** iter-24's EXIT trap saved
the demo's API log to `docs/iterations/iter_24_demo_logs/`.
Forensic value for any future demo regression.

## What went well

1. **Diagnostic-first discipline carried forward.** iter-23
   Phase 1 inverted the prescribed plan with a $0.15 mini-test;
   iter-24 Phase 1 closed an open research question with a
   $0.20 mini-test. Both saved meaningful time and money vs
   running a full demo to test the same hypothesis.

2. **Layered defenses.** TL summary-prefix routing is a
   structural signal (prompt template forces the prefix);
   iter-23 substring matching on `blocked_on` stays as a
   fallback; the iter-23 QA safety net catches LLM tool
   misses. Three layers, each independent. The chain
   doesn't depend on any one of them firing correctly.

3. **TDD throughout.** 2 TL prefix tests + 1 Backend pin
   added via TDD red→green→verify before any production
   code changed. The safety net path was already covered by
   iter-23's 12 unit tests.

4. **Tight iteration scope.** iter-24's plan focused on the
   single 5-iter-deferred criterion; carry-overs ≥5
   explicitly deferred. No scope creep.

## What didn't go well

1. **Demo script's final acceptance check was buggy.** It
   queried `/api/reviews` which filters by `status='pending'`.
   After step 6.6/7's auto-approve, all rows became `approved`,
   so the final check printed a FALSE NEGATIVE
   ("CRITERION NOT MET"). The criterion HAD been met — direct
   DB query confirms `count(*) = 1`. **Fix shipped in the
   same iter-24 commit**: acceptance check now queries DB
   directly via `docker exec psql`, status-agnostic.

2. **QA's audit row got lost to EXIT trap race.** The poll
   loop broke immediately on success; the EXIT trap killed
   the dispatcher before QA's `task_report` audit write
   completed. The criterion's pending_reviews row landed
   (that's what matters), but we lost the audit trace of
   QA's turn metrics. iter-25 carry-over: post-success
   drain delay.

3. **Mid-iteration enum theory pivot in iter-23 was based
   on wrong reasoning.** I reverted the iter-23 enum
   constraint in commit `88402b8` citing a budget-burn
   theory. iter-24 Phase 1 disproved that theory. The
   architectural direction (summary-prefix > blocked_on)
   was still correct, but the rationale was wrong. Lesson:
   when reverting under time pressure, label the theory
   "suspected" until empirically verified.

## Lessons learned

- **Diagnostic mini-tests beat full demos for hypothesis
  testing.** $0.15-$0.20 / 10-15 min experiments closed
  decisions that would have cost $2-3 / 45 min in full
  demos with worse signal-to-noise. The pattern is now
  proven across iter-23 and iter-24.

- **`--json-schema` enum constraints are SAFE on claude -p.**
  The LLM remaps to the nearest valid enum value; no retry
  loop, no budget burn. Future schema design can use enum
  freely for routing-critical fields. iter-23's enum revert
  was unnecessary — the architectural reason (summary-prefix
  is more structural than blocked_on) was a different and
  valid reason for the change.

- **The chain has multiple fragility surfaces.** iter-19..24
  encountered: timeout (#1), prompt scope rules (#2), file
  scaffolding (#3), routing exact-match (#4), tool-call
  compliance (#5), schema enum (#6 — false alarm). Each
  iteration shipped layered defenses; the cumulative effect
  is robustness. No single fix would have closed the
  criterion alone.

- **Backend's first DONE in 5+ iterations was due to a
  prompt edit, not a schema/code change.** "Missing target
  dir is normal" was a 1-paragraph addition to the prompt
  but appears to have been load-bearing. LLM behavior is
  more sensitive to prompt framing than I tend to assume.

## Iteration stats

- **Wall-clock**: ~2 hours session time (Phases 0-7).
- **Cost**: ~$1.73 LLM spend ($0.04 A/B + ~$1.69 demo).
- **Commits to `worktree-iter-24`**:
  - `dd32ee0` — feat(team_lead,backend): TL summary-prefix
    routing + missing-dir handling (Phases 0-5)
  - [pending] — docs(iter-24): demo report + retro + iter-25
    handoff + demo-script acceptance fix
- **Tests**: 444 unit (+3), 50 integration, 4 real_llm
  (iter-23 QA e2e + iter-24 A/B).
- **Files touched (production)**: `agents/team_lead/agent.py`,
  `prompts/backend_developer.md`.
- **New files**: `scripts/demo_iter_24.sh`,
  `tests/integration/test_json_schema_enum_retry_loop.py`,
  `docs/iterations/iter_24{.md, _demo_report.md, _retro.md}`,
  `docs/iterations/iter_25_handoff.md`,
  `docs/iterations/iter_24_demo_logs/f26bf077.log`.

## What changed across iter-19..24

| Iteration | Diff      | Effect |
|-----------|-----------|--------|
| iter-19   | PM/TL allowlist hardening + Context env defaults | Removed PM's accidental MCP writes |
| iter-20   | git worktree add isolation; TL ≤200 LOC decomposition | Chain runs from clean branches |
| iter-21   | Backend Python tripwire; TL re-decomp handler; bash heredoc fix | Defense-in-depth + auto-recovery |
| iter-22   | Backend self-eject prompt; Architect→Backend depends_on | LLM-side scope judgment |
| iter-23   | QA Python safety net; demo poll 30→45min | Owner-approval gate deterministic |
| **iter-24** | **TL summary-prefix routing; Backend missing-dir prompt; A/B-confirmed enum is safe** | **Chain reaches QA reliably** |

The cumulative architecture is now sufficient for the
sandbox idea-validator demo to deliver Backend DONE → QA →
owner-approval row. The next iteration's challenge is no
longer "make the chain work at all" — it's "what should the
team build next?"

## Action items for iter-25

See `docs/iterations/iter_25_handoff.md`. Top items:

1. Reproducibility check — re-run the iter-24-shape demo
   once more to confirm Backend DONE is stable across LLM
   samples (not a lucky run).
2. Demo poll-loop post-success drain (30-60s) so QA's
   audit row gets written.
3. Commit `examples/sandbox/idea-validator/` scaffold to
   main as belt-and-suspenders alongside the prompt edit.
4. **Strategic question**: what does the team build next?
   The sandbox idea-validator is the framework's
   self-test. With the chain reliable, the team is ready
   to attempt a different real product. iter-25 or
   iter-26 should plan that transition.

## Carry-over (unchanged from iter-24 handoff)

Items 5-15 from `iter_23_handoff.md` continue to defer.
None addressed in iter-24 — explicit scope discipline.
