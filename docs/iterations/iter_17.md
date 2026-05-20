# Iteration 17 — Plan

- **Status**: Draft (awaiting owner approval)
- **Plan author**: Claude (Opus 4.7)
- **Date drafted**: 2026-05-20
- **Base commit**: `2097eba` on `main` (iter-16 squash)
- **Branch**: `worktree-iter-17` (cut from `origin/main` at plan
  commit)
- **Anchors (do not contradict)**: ADR-001 (orchestrator),
  ADR-008 (LLM access), iter-16 retro + demo report.
- **Carry-overs addressed**: item 2 of `iter_17_handoff.md` —
  startup-time MCP failure investigation. **Root cause
  identified BEFORE this plan was drafted**: all three
  MCP servers (`ai_team_repo`, `ai_team_bus`,
  `ai_team_tasks`) lack an `initialize` handler in their
  stdio loops. claude -p sends `initialize` first per MCP
  spec and waits for a `protocolVersion` + `capabilities`
  + `serverInfo` response; ours silently ignore the
  request. The 9-iteration "MCP race" was never a timing
  race — it's a 14-iteration latent protocol bug from
  iter-2 (commit `d8bc3e8`).
- **Deferred unchanged** (carry-over items 1, 3–13 from
  iter-17 handoff): demo auto-retry loop, TL auto-hop
  investigation, TL Backend decomposition, TL over-
  decomposition prompt hint, HoldQueue persistence,
  `pytest-rerunfailures` plugin pin, Architect spend
  watch, `audit_writer` Postgres role, hash-chain alert,
  `GitHubTargetRepo`, transactional TL, `BaseAgent`
  template refactor.

## Investigation evidence (already gathered)

1. **Read `tools/mcp_servers/ai_team_repo/__main__.py`** —
   stdio loop handles ONLY `tools/list` and `tools/call`;
   unknown methods (including `initialize`) are silently
   skipped. Same shape in `ai_team_bus/__main__.py` and
   `ai_team_tasks/__main__.py`.
2. **Manual reproduction**: spawned
   `python -m tools.mcp_servers.ai_team_repo`, piped:
   - `initialize` request (id=1)
   - `tools/list` request (id=2)
   Server responded ONLY to id=2. id=1 silently dropped.
3. **MCP spec** (via context7
   `/modelcontextprotocol/modelcontextprotocol`):
   `initialize` is the REQUIRED first request. Server
   MUST respond with `result.protocolVersion`,
   `result.capabilities`, `result.serverInfo`. Without
   the response, the client cannot proceed to
   tools/list or tools/call.
4. **Why iter-9 pre-flight didn't catch this**: the
   probe does in-process `importlib.import_module()`
   + `Context.from_env()`. It NEVER exercises the stdio
   loop. The docstring (`core/llm/mcp_health.py:11-13`)
   says "Stdio-handshake races are NOT caught; iter-10's
   planned substring router on the failure summary
   covers those." iter-10's router routes the symptom
   correctly to BLOCKED; iter-17 fixes the disease.

## Goal — one sentence

Add `initialize` handler to all three MCP servers'
stdio loops so claude -p's required JSON-RPC handshake
completes, then re-run the demo and finally close the
`pending_review` loop iter-3..16 all reached for.

## Success criteria (binary, measurable)

1. **`initialize` handler added** to all three MCP
   server `__main__.py` modules
   (`ai_team_repo`, `ai_team_bus`, `ai_team_tasks`).
   Each responds to `initialize` with a JSON-RPC result
   payload containing:
   - `protocolVersion`: echoes the client's requested
     version (or falls back to a server default).
   - `capabilities`: `{"tools": {}}` (servers expose
     tools, no listChanged subscription, no resources /
     prompts / sampling).
   - `serverInfo`: `{"name": "<server-name>", "version":
     "0.1.0"}`.

2. **Refactor the stdio loop for testability.** Extract
   a pure `_build_response(msg: dict) -> dict | None`
   helper in each server module. The loop becomes a
   thin wrapper. None return signals "notification,
   no response". This makes the handshake unit-testable
   without subprocess machinery.

3. **Unit tests** in
   `tests/unit/test_mcp_server_handshake.py` (new file):
   - For each of the 3 servers, test that `_build_response`
     returns the spec-correct initialize response for a
     valid `initialize` request.
   - Test `notifications/initialized` (no id) returns
     None (no response).
   - Test `tools/list` returns the tools list (regression
     guard against breaking the existing path).
   - Test unknown method returns None (forward-
     compatible — server doesn't crash on new method
     names).

4. **Integration smoke test** in
   `tests/integration/test_mcp_handshake_real_subprocess.py`
   (new file): spawn each MCP server as a subprocess,
   send `initialize` + `tools/list` over stdin, assert
   both get valid responses. Pinned via the MCP spec's
   protocolVersion `2025-06-18` or whatever the client
   sends. Marked `@pytest.mark.integration` (no
   testcontainers needed — pure subprocess).

5. **`make lint typecheck sec test test-integration
   smoke-llm`** all green. Diff-cover ≥ 80 %.
   `uv run ruff format --check .` clean. 0 high-severity
   bandit findings.

6. **Real-LLM demo** (`scripts/demo_iter_17.sh`) re-runs
   the iter-16-shape task. **Expected outcome**:
   Backend's MCP tools now connect cleanly → can run
   pytest + git commit + push + open PR → `task_report
   (done)` → QA picks up → emits `request_human_review`
   → `pending_review` row appears → demo auto-approves
   → **chain closes end-to-end for the first time in
   seventeen iterations**. Two failure-mode branches
   documented:
   - **(a) Loop closes.** As above. Demo report names
     this as the long-awaited closure.
   - **(b) Some other failure surfaces.** Even with
     MCP fixed, there could be other bugs (TL
     decomposition issues, target_repo scope errors,
     QA prompt issues). Demo report names the new
     blocker; iter-18 picks it up. The MCP fix is
     load-bearing regardless.

## Phases

Plan-before-code: this document lands as Phase 0's
commit. No Phase 1+ work until the owner approves.

### Phase 0 — Plan + branch setup

- [x] **Cut branch from origin/main** (done at draft time):
  ```bash
  git checkout -b worktree-iter-17 origin/main
  ```
- [ ] **Commit this plan**:
  ```bash
  git add docs/iterations/iter_17.md
  git commit -m "docs(iter-17): plan — fix MCP initialize handler, root cause of 9-iter race"
  ```
- [ ] **Open draft PR** with the plan link + the root
  cause findings as motivation.

### Phase 1 — `initialize` handler + refactor + tests (TDD)

**Files**:
- Modify: `tools/mcp_servers/ai_team_repo/__main__.py`
- Modify: `tools/mcp_servers/ai_team_bus/__main__.py`
- Modify: `tools/mcp_servers/ai_team_tasks/__main__.py`
- Create: `tests/unit/test_mcp_server_handshake.py`
- Create: `tests/integration/test_mcp_handshake_real_subprocess.py`

#### Step 1.1 — Failing tests first (RED)

- [ ] **Create `tests/unit/test_mcp_server_handshake.py`**
  with parametric tests:

  ```python
  """iter-17: MCP initialize handshake tests.

  Pre-iter-17 the three MCP servers had no `initialize`
  handler in their stdio loops. claude -p's required
  JSON-RPC handshake silently dropped → 14-iteration
  latent bug surfaced as ToolSearch "still-connecting"
  retries. See iter_17.md for the investigation.
  """
  import importlib
  import pytest

  _SERVERS = ["ai_team_repo", "ai_team_bus", "ai_team_tasks"]


  @pytest.mark.parametrize("server_pkg", _SERVERS)
  def test_initialize_returns_spec_correct_response(server_pkg):
      module = importlib.import_module(
          f"tools.mcp_servers.{server_pkg}.__main__"
      )
      msg = {
          "jsonrpc": "2.0",
          "id": 1,
          "method": "initialize",
          "params": {
              "protocolVersion": "2025-06-18",
              "capabilities": {},
              "clientInfo": {"name": "test", "version": "0"},
          },
      }
      response = module._build_response(msg)
      assert response is not None
      assert response["jsonrpc"] == "2.0"
      assert response["id"] == 1
      result = response["result"]
      assert "protocolVersion" in result
      assert result["protocolVersion"] == "2025-06-18"  # echo
      assert "capabilities" in result
      assert "tools" in result["capabilities"]
      assert "serverInfo" in result
      assert result["serverInfo"]["name"] == server_pkg
      assert "version" in result["serverInfo"]


  @pytest.mark.parametrize("server_pkg", _SERVERS)
  def test_initialized_notification_returns_no_response(server_pkg):
      """`notifications/initialized` is a JSON-RPC notification
      (no id). Server MUST NOT respond per MCP spec."""
      module = importlib.import_module(
          f"tools.mcp_servers.{server_pkg}.__main__"
      )
      msg = {"jsonrpc": "2.0", "method": "notifications/initialized"}
      assert module._build_response(msg) is None


  @pytest.mark.parametrize("server_pkg", _SERVERS)
  def test_tools_list_still_works_after_refactor(server_pkg):
      """Regression guard: refactor extracts _build_response,
      but `tools/list` must still return the existing tool list."""
      module = importlib.import_module(
          f"tools.mcp_servers.{server_pkg}.__main__"
      )
      msg = {"jsonrpc": "2.0", "id": 5, "method": "tools/list"}
      response = module._build_response(msg)
      assert response is not None
      assert response["id"] == 5
      assert "tools" in response["result"]
      assert len(response["result"]["tools"]) > 0


  @pytest.mark.parametrize("server_pkg", _SERVERS)
  def test_unknown_request_method_returns_none(server_pkg):
      """Forward-compat: unknown REQUESTS (with id) currently
      return None (silently dropped). This is the pre-iter-17
      behavior; we preserve it so claude -p's behaviour for
      unknown methods doesn't change."""
      module = importlib.import_module(
          f"tools.mcp_servers.{server_pkg}.__main__"
      )
      msg = {"jsonrpc": "2.0", "id": 99, "method": "resources/list"}
      assert module._build_response(msg) is None
  ```

- [ ] **Run** — expect IMPORT FAIL because
  `_build_response` doesn't exist yet:

  ```bash
  uv run pytest tests/unit/test_mcp_server_handshake.py -v
  ```

  Expected: errors importing — `_build_response` not
  defined.

#### Step 1.2 — Extract `_build_response` + add `initialize` handler (GREEN)

For each of the three MCP server `__main__.py` modules:

- [ ] **Extract pure builder function** with this shape:

  ```python
  _SERVER_NAME = "ai_team_repo"  # match module name
  _SERVER_VERSION = "0.1.0"
  _DEFAULT_PROTOCOL_VERSION = "2025-06-18"


  def _build_response(msg: dict[str, Any]) -> dict[str, Any] | None:
      """Build the JSON-RPC response for a single client message.

      Returns None when the message is a notification (no id) or
      an unknown method. The stdio loop translates None into
      "do not write anything to stdout".
      """
      method = msg.get("method")
      msg_id = msg.get("id")

      if method == "initialize":
          # iter-17: per MCP spec, server must respond with
          # protocolVersion + capabilities + serverInfo. We echo
          # the client's requested protocolVersion (any version
          # the client sends; we have no version-gated features
          # so any is fine).
          params = msg.get("params") or {}
          client_version = params.get("protocolVersion") or _DEFAULT_PROTOCOL_VERSION
          return {
              "jsonrpc": "2.0",
              "id": msg_id,
              "result": {
                  "protocolVersion": client_version,
                  "capabilities": {"tools": {}},
                  "serverInfo": {
                      "name": _SERVER_NAME,
                      "version": _SERVER_VERSION,
                  },
              },
          }

      if method == "tools/list":
          return {
              "jsonrpc": "2.0",
              "id": msg_id,
              "result": {"tools": TOOL_LIST},  # or _TOOL_LIST per existing names
          }

      # tools/call still needs the async handler dispatch; the
      # stdio loop handles that branch directly. _build_response
      # only covers the sync request shapes.
      return None
  ```

  For `ai_team_repo` specifically the `tools/call` path
  dispatches to async handlers and cannot fit in a sync
  helper; that branch stays in the loop. For the two
  stub servers (`ai_team_bus`, `ai_team_tasks`) the
  `tools/call` response is also sync (just a stub
  string), so they can include it in `_build_response`
  fully.

- [ ] **Rewrite the stdio loop** to call `_build_response`
  first; only fall through to async `tools/call`
  handling for `ai_team_repo`:

  ```python
  async def _stdio_loop() -> None:
      ctx = Context.from_env()  # ai_team_repo only
      loop = asyncio.get_event_loop()
      reader = asyncio.StreamReader()
      protocol = asyncio.StreamReaderProtocol(reader)
      await loop.connect_read_pipe(lambda: protocol, sys.stdin)
      while True:
          line = await reader.readline()
          if not line:
              return
          try:
              msg = json.loads(line.decode())
          except json.JSONDecodeError:
              continue

          # Sync request shapes: initialize, tools/list, unknown
          response = _build_response(msg)
          if response is not None:
              sys.stdout.write(json.dumps(response) + "\n")
              sys.stdout.flush()
              continue

          # ai_team_repo only — tools/call dispatches to async
          # handlers (Postgres / Redis / git operations).
          if msg.get("method") == "tools/call":
              params = msg.get("params") or {}
              name = params.get("name", "")
              arguments = params.get("arguments") or {}
              handler = HANDLERS.get(name)
              if handler is None:
                  result = {
                      "isError": True,
                      "content": [{"type": "text", "text": f"unknown tool: {name!r}"}],
                  }
              else:
                  result = await handler(ctx, arguments)
              sys.stdout.write(
                  json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": result}) + "\n"
              )
              sys.stdout.flush()
  ```

- [ ] **Run unit tests — expect GREEN**:

  ```bash
  uv run pytest tests/unit/test_mcp_server_handshake.py -v
  uv run pytest tests/unit -q
  ```

#### Step 1.3 — Integration subprocess test (TDD style, but optional)

- [ ] **Create
  `tests/integration/test_mcp_handshake_real_subprocess.py`**:

  ```python
  """End-to-end MCP handshake against the real Python subprocess
  spawn — closest possible reproduction of how claude -p talks
  to our MCP servers. iter-17 root cause was caught only when
  this test was written; the unit-test layer (handler-only)
  missed it for 14 iterations."""
  import json
  import subprocess
  import sys
  import pytest


  _SERVERS = ["ai_team_repo", "ai_team_bus", "ai_team_tasks"]


  @pytest.mark.integration
  @pytest.mark.parametrize("server_pkg", _SERVERS)
  def test_real_subprocess_initialize_then_tools_list(server_pkg):
      payload = (
          b'{"jsonrpc":"2.0","id":1,"method":"initialize",'
          b'"params":{"protocolVersion":"2025-06-18","capabilities":{},'
          b'"clientInfo":{"name":"test","version":"0"}}}\n'
          b'{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n'
      )
      proc = subprocess.Popen(
          [sys.executable, "-m", f"tools.mcp_servers.{server_pkg}"],
          stdin=subprocess.PIPE,
          stdout=subprocess.PIPE,
          stderr=subprocess.PIPE,
      )
      out, _err = proc.communicate(input=payload, timeout=10)
      lines = [ln for ln in out.decode().splitlines() if ln.strip()]
      assert len(lines) == 2, f"expected 2 responses, got {len(lines)}: {lines}"

      init_response = json.loads(lines[0])
      assert init_response["id"] == 1
      assert "protocolVersion" in init_response["result"]
      assert "serverInfo" in init_response["result"]

      tools_response = json.loads(lines[1])
      assert tools_response["id"] == 2
      assert len(tools_response["result"]["tools"]) > 0
  ```

  No testcontainers; uses `sys.executable` directly so
  it doesn't need a virtualenv-path hack. Fast (~3s for
  3 servers in parallel).

- [ ] **Run** the integration smoke:

  ```bash
  uv run pytest tests/integration/test_mcp_handshake_real_subprocess.py -v -m integration
  ```

  Expected: 6 parametric cases (3 servers × 2 tests)
  all pass against the iter-17 implementations.

#### Step 1.4 — Commit Phase 1

- [ ] **Lint + format + mypy**:

  ```bash
  uv run ruff check tools/mcp_servers tests/unit/test_mcp_server_handshake.py tests/integration/test_mcp_handshake_real_subprocess.py
  uv run ruff format --check tools/mcp_servers tests/unit/test_mcp_server_handshake.py tests/integration/test_mcp_handshake_real_subprocess.py
  uv run mypy tools/mcp_servers
  ```

- [ ] **Commit**:

  ```bash
  git add tools/mcp_servers tests/unit/test_mcp_server_handshake.py tests/integration/test_mcp_handshake_real_subprocess.py
  git commit -m "fix(mcp): add initialize handler — 14-iteration latent handshake bug"
  ```

### Phase 2 — Demo script + real-LLM run + report

**Files**:
- Create: `scripts/demo_iter_17.sh` — clone of
  `demo_iter_16.sh` with iter-17 header.
- Modify: `Makefile` — `make demo` aliases to
  `demo-iter-17`; iter-16 stays as regression baseline.

#### Step 2.1 — Demo script

- [ ] **Copy + adapt + commit**:

  ```bash
  cp scripts/demo_iter_16.sh scripts/demo_iter_17.sh
  chmod +x scripts/demo_iter_17.sh
  # Header narrative shift: iter-17 = MCP handshake fix.
  # .iter16-mcp.json → .iter17-mcp.json.
  # Auto-retry-blocked tail stays unchanged (defensive
  # readiness; iter-17's fix should remove the need for
  # any retry on the happy path).
  ```

- [ ] **Makefile alias**:

  ```makefile
  demo: demo-iter-17 ## Alias for the current iteration's demo

  demo-iter-17: ## Run iter-17 e2e (MCP initialize handshake fix + close loop)
  	bash scripts/demo_iter_17.sh

  demo-iter-16: ## Run iter-16 e2e — regression baseline (verb-set extension)
  	bash scripts/demo_iter_16.sh
  ```

- [ ] **Syntax check + commit**:

  ```bash
  bash -n scripts/demo_iter_17.sh
  git add scripts/demo_iter_17.sh Makefile
  git commit -m "chore(demo): demo_iter_17.sh + Makefile alias"
  ```

#### Step 2.2 — Pre-flight + real-LLM run

- [ ] **Pre-flight smoke** + **demo**:

  ```bash
  make smoke-llm
  AI_TEAM_DEMO_NON_INTERACTIVE=1 bash scripts/demo_iter_17.sh
  ```

  Wall-clock budget 45 min. Cost ceiling $5.00.

- [ ] **Capture outcome.** Expected (success criterion
  #6a): chain reaches `pending_review`, demo auto-
  approves. Pull the audit_log via `docker exec` for
  the timeline.

#### Step 2.3 — Demo report

- [ ] **Write
  `docs/iterations/iter_17_demo_report.md`** mirroring
  iter_16_demo_report.md's structure. If criterion 6a:
  **headline note that the `pending_review` loop
  closed end-to-end for the first time in seventeen
  iterations**. If 6b: name the new blocker for
  iter-18.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_17_demo_report.md
  git commit -m "docs(iter-17): real-LLM demo report"
  ```

### Phase 3 — Retro + iter-18 handoff + gates + merge

#### Step 3.1 — Final gate sweep

- [ ] **Gates**:

  ```bash
  make lint typecheck sec test test-integration smoke-llm
  uv run ruff format --check .
  uv run pytest tests/unit tests/integration --cov --cov-report=xml -q
  uv run diff-cover coverage.xml --compare-branch=origin/main --fail-under=80
  ```

#### Step 3.2 — Retro + iter-18 handoff

- [ ] **Write `iter_17_retro.md`** + **`iter_18_handoff.md`**.
  iter-18 priority depends on the demo outcome:
  - 6a (loop closed): TL Backend decomposition (now
    SEVEN-iteration carry-over), HoldQueue persistence,
    `pytest-rerunfailures` plugin pin, switch focus
    away from the MCP/router track to product/QA
    feedback loops.
  - 6b (new blocker): pick it up + carry-over rest.

- [ ] **Commit**:

  ```bash
  git add docs/iterations/iter_17_retro.md docs/iterations/iter_18_handoff.md
  git commit -m "docs(iter-17): retro + iter-18 handoff"
  ```

#### Step 3.3 — Mark PR ready, watch CI, squash-merge

- [ ] `gh pr ready && gh pr checks --watch && gh pr merge --squash`

## What we are NOT doing this iteration

- **Demo auto-retry loop** (iter-17 handoff #1). With
  the MCP fix, retries should not be needed on the
  happy path. Defer to iter-18 if the demo still trips
  on something the matcher catches.
- **TL auto-hop investigation** — iter-17 handoff #3.
- **TL Backend decomposition** — SEVEN-iteration carry-
  over. Defer; iter-17 must validate the fix-the-MCP
  hypothesis first.
- **TL over-decomposition prompt hint** — iter-17
  handoff #5.
- **All other carry-overs** untouched (HoldQueue,
  `pytest-rerunfailures`, audit_writer, hash-chain,
  GitHubTargetRepo, transactional TL, BaseAgent
  refactor).

## Risks

- **The fix isn't enough — claude -p's MCP client may
  reject our handshake** if our capabilities response
  is missing a field claude expects. Mitigation: the
  initialize response shape is taken verbatim from MCP
  spec docs (`/modelcontextprotocol/modelcontextprotocol`
  via context7). If claude -p logs reveal a mismatch
  during the demo, iterate on the response shape in
  the same PR.
- **Multiple concurrent claude -p instances all spawn
  the MCP server** — 6 agent sessions = 6 MCP server
  processes simultaneously trying to import + connect to
  Postgres/Redis. The pre-flight gate showed module
  imports are pure (no side effects), so concurrency
  shouldn't cause initialization deadlock. The MCP
  servers only open DB connections inside individual
  tool calls, not at startup.
- **Backend's session length grows once it can actually
  do work** (commit + push + pytest + open PR could
  push past 600s timeout). Mitigation: even a partial
  Backend session that commits the on-disk tree
  changes (already done in iter-15) before timeout
  would advance the chain. Worst case: iter-18 takes TL
  Backend decomposition.
- **CI flake recurrence** (`test_transitive_drops_
  cascade_through_hold_queue`). Re-run on the iter-17
  PR confirmed it's a pre-existing testcontainers
  port-mapping race, not iter-17-caused. Strategy:
  same as iter-16 — `gh run rerun --failed` on first
  flake, document for iter-18 to pin
  `pytest-rerunfailures`.
- **New phrasings escaping the matcher.** With MCP
  fixed, this risk disappears for the happy path. If
  a different failure mode (timeout, disk I/O error,
  permission) surfaces, the matcher won't catch it —
  but that's a NEW class of failure, not the same
  race.

## Cost projection

| Phase | Type                          | Estimate                  |
|-------|-------------------------------|---------------------------|
| 0     | docs                          | $0                        |
| 1     | code (3 server modules) + 8 tests | $0                    |
| 2     | shell + real-LLM demo (likely no retries needed) | ~$1.50 expected if happy path; +$1 if any retries |
| 3     | docs + CI                     | $0                        |
| **Total** |                           | **~$1.50 expected, $5 ceiling** |

iter-16 spent $1.33 with the matcher catching both
attempts. iter-17 expected even lower if the MCP fix
removes the need for ANY retry (Backend completes the
short commit+push+pytest+PR session in one shot).

## Workflow

- Plan-before-code: this file = Phase 0's commit.
- Conventional commits; squash-merge on the iter-17 PR.
- Each phase's "Commit" row is one (and only one) commit.
- Run `make lint typecheck sec test` after each phase.
- Final demo report goes in the same PR.

## Ready-to-paste prompt for iter-18

Lives in `docs/iterations/iter_18_handoff.md` (Phase 3.2).
