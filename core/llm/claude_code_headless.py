"""`claude -p` subprocess backend for LLMClient. See ADR-008.

Uses subscription auth: the `claude` CLI must already be logged in
(see `claude /login` or device-code flow). NO ANTHROPIC_API_KEY is read
or required.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import TYPE_CHECKING, Any

import structlog

from core.llm.base import (
    DEFAULT_MAX_BUDGET_USD_PER_TIER,
    LLMBudgetExhaustedError,
    LLMInvocationError,
    LLMResponse,
    LLMTimeoutError,
    ModelTier,
    TokensUsage,
    ToolUse,
    estimate_cost_cents,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

_log = structlog.get_logger(__name__)


_DEFAULT_MODEL_IDS: dict[ModelTier, str] = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-7",
}


def _resolve_model_id(tier: ModelTier) -> str:
    env_key = f"LLM_MODEL_{tier.upper()}"
    return os.environ.get(env_key, _DEFAULT_MODEL_IDS[tier])


def _is_budget_exhausted_stdout(out: str) -> bool:
    """Return True iff `out` contains the `error_max_budget_usd`
    marker from `claude -p`.

    iter-5's stdout-tee surfaced the iter-3/4 mystery: `claude -p`
    reports budget exhaustion as `{"type":"result","subtype":
    "error_max_budget_usd",...}` on stdout (exit 1, empty stderr).

    iter-8: substring-only match. The adapter's stdout cap (8 KB as
    of iter-8) can leave the response JSON incomplete; iter-6's
    JSON-parse-required version returned False on truncation, which
    defeated the BLOCKED branch in the iter-7 demo (Failure 2). The
    marker is a structured response field — not natural-language
    text — so false-positive risk is near-zero.
    """
    return "error_max_budget_usd" in out


class ClaudeCodeHeadlessClient:
    """Async wrapper around `claude -p ... --output-format json`.

    Notes on the underlying CLI (verified against `claude --help`,
    Claude Code 2.1.143):

    - System prompt is passed via `--append-system-prompt <string>`
      (arg, not file). argv on macOS allows ~256 KB total, so 10 KB
      prompts are fine. We use `create_subprocess_exec` (no shell), so
      special chars in args are not interpolated.
    - `--max-turns` is **not** an available flag. We rely on
      `--max-budget-usd` for hard budget enforcement and on the agent's
      own prompt to bound turns.
    - Session flags are split: `--session-id <uuid>` *creates* a session
      with that ID (errors with "Session ID is already in use" if the
      ID was previously used). `--resume <sid>` *reattaches* to an
      existing session (errors if it doesn't exist). This client tracks
      which IDs it has already created in this process and switches
      automatically: first call → `--session-id`, subsequent calls with
      the same ID → `--resume`. This is what gives us prompt caching
      across turns. On process restart the tracking is lost; callers
      must pass a fresh uuid (each AgentMessage already does, via its
      own correlation_id).
    - Sessions persist under `~/.claude` unless `--no-session-persistence`
      is set. We let them persist for resumption.
    """

    def __init__(self, *, binary: str = "claude") -> None:
        self._binary = binary
        # Session IDs this client has already passed via `--session-id`
        # in the current process. Subsequent calls with the same id are
        # rewritten to `--resume` so prompt caching works (see class
        # docstring). Plain set is fine — every invoke() awaits its own
        # subprocess and each AgentMessage carries a unique correlation_id,
        # so two concurrent invokes won't race on the same session_id.
        self._claimed_sessions: set[str] = set()

    async def invoke(
        self,
        *,
        system_prompt: str,
        user_message: str,
        model: ModelTier = "sonnet",
        allowed_tools: Sequence[str] = (),
        disallowed_tools: Sequence[str] = (),
        session_id: str | None = None,
        mcp_config_path: str | None = None,
        timeout_s: int = 120,
        max_turns: int = 8,  # kept for protocol compat; not passed to CLI
        json_schema: dict[str, Any] | None = None,
        max_budget_usd: float | None = None,
        env: dict[str, str] | None = None,
    ) -> LLMResponse:
        model_id = _resolve_model_id(model)
        effective_budget = (
            max_budget_usd if max_budget_usd is not None else DEFAULT_MAX_BUDGET_USD_PER_TIER[model]
        )

        cmd: list[str] = [
            self._binary,
            "-p",
            user_message,
            "--output-format",
            "json",
            "--model",
            model_id,
            "--append-system-prompt",
            system_prompt,
            "--max-budget-usd",
            f"{effective_budget:.4f}",
            # iter-5: acceptEdits auto-accepts file edits / tool uses inside
            # the agent's session so it doesn't stall on the interactive
            # write-approval prompt that blocked Frontend in iter-4's demo.
            # Defense-in-depth: dangerous shell commands still gate; per-MCP
            # path scope is enforced by ai-team-repo's AI_TEAM_PATH_PREFIXES.
            "--permission-mode",
            "acceptEdits",
        ]
        if allowed_tools:
            cmd += ["--allowed-tools", ",".join(allowed_tools)]
        if disallowed_tools:
            cmd += ["--disallowed-tools", ",".join(disallowed_tools)]
        if session_id:
            if session_id in self._claimed_sessions:
                cmd += ["--resume", session_id]
            else:
                cmd += ["--session-id", session_id]
                self._claimed_sessions.add(session_id)
        # When mcp_config_path isn't passed explicitly, fall back to the
        # AI_TEAM_MCP_CONFIG_PATH env var so the demo script can plumb in
        # the MCP servers without changing per-agent code. The env var is
        # the iter-2 wiring; per-agent config files are iter-2b material.
        effective_mcp = mcp_config_path or os.environ.get("AI_TEAM_MCP_CONFIG_PATH")
        if effective_mcp:
            cmd += ["--mcp-config", effective_mcp]
        if json_schema is not None:
            cmd += ["--json-schema", json.dumps(json_schema, separators=(",", ":"))]

        log = _log.bind(
            model=model_id,
            has_session=bool(session_id),
            tool_count=len(allowed_tools),
            user_msg_len=len(user_message),
            sys_prompt_len=len(system_prompt),
        )
        log.info("llm.invoke.start")
        start = time.perf_counter()

        # When caller passes env=..., merge on top of os.environ rather than
        # replace it (subprocess.Popen would otherwise drop PATH, HOME, etc.).
        # When env is None we let the subprocess inherit the parent's env
        # unchanged (no env kwarg to create_subprocess_exec).
        effective_env = {**os.environ, **env} if env else None

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=effective_env,
            )
        except FileNotFoundError as e:
            raise LLMInvocationError(
                f"`{self._binary}` not found on PATH; install Claude Code CLI"
            ) from e

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except TimeoutError as e:
            proc.kill()
            await proc.wait()
            # iter-7: drain whatever buffered stdout the process flushed
            # before the kill so the raised exception carries diagnostic
            # data. iter-6 demo's Architect timeout was a bare message;
            # mirrors iter-5 Phase 4 for the non-zero-exit path.
            # Drain failure is non-fatal — degrade gracefully to an
            # empty buffer rather than masking the timeout.
            buffered_out = ""
            try:
                drained_out, _drained_err = await proc.communicate()
                buffered_out = drained_out.decode(errors="replace")[:2000]
            except Exception as drain_err:
                # Best-effort drain — failure degrades diagnostics but
                # must not mask the timeout itself.
                log.warning("llm.invoke.timeout.drain_failed", error=str(drain_err))
            log.error(
                "llm.invoke.timeout",
                timeout_s=timeout_s,
                buffered_stdout=buffered_out,
            )
            raise LLMTimeoutError(
                f"claude -p timed out after {timeout_s}s; stdout={buffered_out!r}"
            ) from e

        duration_ms = int((time.perf_counter() - start) * 1000)

        if proc.returncode != 0:
            err = stderr.decode(errors="replace")[:1000]
            # iter-5: also capture stdout. iter-4 demo's Backend hit
            # `exited 1` with EMPTY stderr — the actual error was on
            # stdout. See iter_4_demo_report.md Failure 1.
            # iter-8: cap raised 2 KB → 8 KB so real-LLM error JSONs
            # (up to ~3-4 KB in practice) fit without truncating the
            # marker. iter-7 demo Failure 2 surfaced the truncation
            # gap. Substring detector below is the load-bearing fix;
            # the larger cap is defense-in-depth + richer diagnostics.
            out = stdout.decode(errors="replace")[:8000]
            log.error(
                "llm.invoke.failed",
                returncode=proc.returncode,
                stderr=err,
                stdout=out,
            )
            # iter-6: detect budget exhaustion specifically so the
            # dispatcher can route it to BLOCKED instead of FAILED
            # (no cascade-drop of dependents). See iter_6.md Phase 2.
            if _is_budget_exhausted_stdout(out):
                raise LLMBudgetExhaustedError(f"claude -p budget exhausted: stdout={out!r}")
            raise LLMInvocationError(
                f"claude -p exited {proc.returncode}: stderr={err!r} stdout={out!r}"
            )

        response = self._parse_response(stdout, model_id=model_id, duration_ms=duration_ms)
        log.info(
            "llm.invoke.ok",
            duration_ms=duration_ms,
            tokens_in=response.tokens.input,
            tokens_out=response.tokens.output,
            cost_cents=response.cost_estimate_cents,
            schema_requested=json_schema is not None,
            validated_against_schema=response.validated_against_schema,
        )
        return response

    async def reset_session(self, session_id: str) -> None:
        """Forget our local claim on this session id.

        The on-disk claude session is not deleted (it expires naturally).
        After this call, the next invoke() with the same id would issue a
        new `--session-id` and claude would reject it as already-in-use;
        callers should generate a new uuid instead. Provided for tests
        and as a potential unwind path on quota-exhausted errors.
        """
        self._claimed_sessions.discard(session_id)
        _log.debug("llm.reset_session.unclaimed", session_id=session_id)

    # ----- internals -----

    def _parse_response(
        self,
        raw_stdout: bytes,
        *,
        model_id: str,
        duration_ms: int,
    ) -> LLMResponse:
        try:
            data: dict[str, Any] = json.loads(raw_stdout.decode())
        except json.JSONDecodeError as e:
            preview = raw_stdout[:500]
            raise LLMInvocationError(f"claude -p emitted non-JSON output: {preview!r}") from e

        if data.get("is_error", False):
            raise LLMInvocationError(
                f"claude -p reported error: {data.get('result', '<no detail>')!r}"
            )

        usage_raw: dict[str, int] = data.get("usage") or {}
        tokens = TokensUsage(
            input=int(usage_raw.get("input_tokens", 0)),
            output=int(usage_raw.get("output_tokens", 0)),
            cached_input=int(usage_raw.get("cache_read_input_tokens", 0)),
            model=model_id,
        )

        text: str = str(data.get("result", ""))
        # When --json-schema was passed, the validated object lives in
        # `structured_output`. Otherwise try to extract JSON from the
        # natural-language `result`. `validated_against_schema` records
        # which branch we took so callers (and the feed digest) can see
        # per-turn schema conformance without re-parsing the raw blob.
        raw_structured = data.get("structured_output")
        if isinstance(raw_structured, dict):
            structured: dict[str, Any] | None = raw_structured
            validated_against_schema = True
        else:
            structured = self._maybe_parse_json(text)
            validated_against_schema = False

        tools_used: list[ToolUse] = []
        for t in data.get("tools_used", []):
            if not isinstance(t, dict):
                continue
            output_summary = t.get("output_summary")
            tools_used.append(
                ToolUse(
                    name=str(t.get("name", "")),
                    input=t.get("input", {}) or {},
                    output_summary=(
                        str(output_summary)[:500] if output_summary is not None else None
                    ),
                )
            )

        return LLMResponse(
            text=text,
            structured=structured,
            tools_used=tools_used,
            session_id=str(data.get("session_id", "")),
            tokens=tokens,
            cost_estimate_cents=estimate_cost_cents(model_id, tokens),
            duration_ms=duration_ms,
            validated_against_schema=validated_against_schema,
            raw=data,
        )

    @staticmethod
    def _maybe_parse_json(text: str) -> dict[str, Any] | None:
        """Try to extract a top-level JSON object from the model's text.

        Accepts either: (a) the entire text is a JSON object, or
        (b) a fenced ```json ... ``` block. Returns None otherwise.
        Agents that need structured output should pass `--json-schema`
        and read `LLMResponse.structured`.
        """
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                value = json.loads(stripped)
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                pass
        if "```json" in text:
            try:
                start = text.index("```json") + len("```json")
                end = text.index("```", start)
                inner = text[start:end].strip()
                value = json.loads(inner)
                return value if isinstance(value, dict) else None
            except (ValueError, json.JSONDecodeError):
                pass
        return None
