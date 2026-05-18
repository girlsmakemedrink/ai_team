"""`ai-team` CLI. Click-based; uses the API over HTTP. See ADR-007."""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import click
import httpx
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()


# --- helpers ---

_ROLE_COLORS: dict[str, str] = {
    "user": "bold white",
    "team_lead": "bold yellow",
    "product_manager": "cyan",
    "designer": "magenta",
    "architect": "bold magenta",
    "backend_developer": "green",
    "frontend_developer": "bright_green",
    "devops": "blue",
    "qa_engineer": "bright_cyan",
    "sre_support": "red",
    "market_researcher": "bright_yellow",
    "broadcast": "dim",
}

_PRIORITY_STYLE: dict[str, str] = {
    "P1": "bold red on yellow",
    "P2": "bold red",
    "P3": "white",
    "P4": "dim",
}


def _color_for(agent: str) -> str:
    return _ROLE_COLORS.get(agent, "white")


def _api_base(ctx: click.Context) -> str:
    return ctx.obj["api_base"]


def _token_header(ctx: click.Context) -> dict[str, str]:
    token = ctx.obj.get("owner_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def _render_event(event: dict[str, Any]) -> Text:
    ts = event.get("timestamp", "")
    sender = str(event.get("sender", "?"))
    recipient = str(event.get("recipient", "?"))
    msg_type = str(event.get("message_type", "?"))
    priority = str(event.get("priority", "P3"))
    summary = str(event.get("summary", ""))
    cid = str(event.get("correlation_id", ""))[:8]

    line = Text()
    line.append(f"{ts}  ", style="dim")
    line.append(f"[{priority}]", style=_PRIORITY_STYLE.get(priority, "white"))
    line.append(f"  {cid}  ", style="dim")
    line.append(f"{sender}", style=_color_for(sender))
    line.append(" → ", style="dim")
    line.append(f"{recipient}", style=_color_for(recipient))
    line.append(f"  {msg_type}", style="bold")
    line.append(f"\n        {summary}", style="dim")
    return line


# --- root ---


@click.group()
@click.option("--api-base", default="http://localhost:8000",
              show_default=True, envvar="AI_TEAM_API_BASE",
              help="Base URL of the ai_team API.")
@click.option("--owner-token", envvar="OWNER_TOKEN",
              help="Owner token (or set OWNER_TOKEN in env / .env).")
@click.pass_context
def cli(ctx: click.Context, api_base: str, owner_token: str | None) -> None:
    """ai-team — multi-agent dev team CLI."""
    ctx.ensure_object(dict)
    ctx.obj["api_base"] = api_base.rstrip("/")
    ctx.obj["owner_token"] = owner_token


# --- commands ---


@cli.command()
def up() -> None:
    """Start infra (postgres, redis, prometheus, grafana) via `make up`."""
    import subprocess

    console.print("[bold]Running `make up`…[/]")
    subprocess.run(["make", "up"], check=False)  # noqa: S603, S607


@cli.command()
@click.option("--agent", default=None, help="Filter to one agent.")
@click.option("--correlation", default=None, help="Filter to one correlation_id.")
@click.option("--priority", default=None, help="Comma-separated priorities (e.g. P1,P2).")
@click.option("--no-internal/--with-internal", default=True,
              help="Hide heartbeats and low-signal events.")
@click.option("--json", "json_out", is_flag=True, default=False, help="Machine output.")
@click.pass_context
def watch(
    ctx: click.Context,
    agent: str | None,
    correlation: str | None,
    priority: str | None,
    no_internal: bool,
    json_out: bool,
) -> None:
    """Live-tail the team_feed."""
    priorities = set(priority.split(",")) if priority else None
    asyncio.run(_run_watch(
        api_base=_api_base(ctx),
        agent=agent,
        correlation=correlation,
        priorities=priorities,
        no_internal=no_internal,
        json_out=json_out,
    ))


async def _run_watch(
    *,
    api_base: str,
    agent: str | None,
    correlation: str | None,
    priorities: set[str] | None,
    no_internal: bool,
    json_out: bool,
) -> None:
    console.print(f"[dim]Connecting to {api_base}/api/feed/stream …[/]")
    async with httpx.AsyncClient(base_url=api_base, timeout=None) as client:
        async with client.stream("GET", "/api/feed/stream") as resp:
            if resp.status_code != 200:
                console.print(f"[red]Failed to connect: HTTP {resp.status_code}[/]")
                sys.exit(1)
            async for raw in resp.aiter_lines():
                if not raw or not raw.startswith("data:"):
                    continue
                payload = raw[len("data:"):].strip()
                if not payload:
                    continue
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue

                if agent and agent not in (event.get("sender"), event.get("recipient")):
                    continue
                if correlation and not str(event.get("correlation_id", "")).startswith(correlation):
                    continue
                if priorities and event.get("priority") not in priorities:
                    continue
                if no_internal and event.get("message_type") == "heartbeat":
                    continue

                if json_out:
                    sys.stdout.write(payload + "\n")
                    sys.stdout.flush()
                else:
                    console.print(_render_event(event))


@cli.command()
@click.option("--title", required=True)
@click.option("--description", required=True)
@click.option("--target-repo", default=None,
              help="Override TARGET_REPO (default: ai_team itself).")
@click.pass_context
def submit(ctx: click.Context, title: str, description: str,
           target_repo: str | None) -> None:
    """Submit a new task to the Team Lead."""
    body: dict[str, Any] = {"title": title, "description": description}
    if target_repo:
        body["target_repo"] = target_repo

    resp = httpx.post(
        f"{_api_base(ctx)}/api/tasks",
        json=body,
        headers=_token_header(ctx),
        timeout=30.0,
    )
    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.status_code} {resp.text}[/]")
        sys.exit(1)
    data = resp.json()
    console.print(Panel(
        f"[bold]Task queued.[/]\n"
        f"  task_id:        {data['task_id']}\n"
        f"  correlation_id: {data['correlation_id']}\n"
        f"  status:         {data['status']}",
        title="Task submitted", style="green",
    ))


@cli.command(name="list-pending")
@click.pass_context
def list_pending(ctx: click.Context) -> None:
    """List reviews awaiting your approval."""
    resp = httpx.get(
        f"{_api_base(ctx)}/api/reviews",
        headers=_token_header(ctx),
        timeout=10.0,
    )
    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.status_code}[/]")
        sys.exit(1)
    reviews = resp.json()
    if not reviews:
        console.print("[dim]No pending reviews.[/]")
        return
    table = Table(title="Pending reviews")
    table.add_column("ID", style="cyan")
    table.add_column("Agent")
    table.add_column("Summary")
    table.add_column("Created", style="dim")
    for r in reviews:
        table.add_row(r["id"][:8], r["requesting_agent"], r["summary"], r["created_at"])
    console.print(table)


@cli.command()
@click.argument("review_id", type=click.UUID)
@click.option("--comment", default=None)
@click.pass_context
def approve(ctx: click.Context, review_id: UUID, comment: str | None) -> None:
    """Approve a pending review."""
    _resolve_review(ctx, review_id, "approve", comment)


@cli.command()
@click.argument("review_id", type=click.UUID)
@click.option("--comment", required=True, help="Required when rejecting.")
@click.pass_context
def reject(ctx: click.Context, review_id: UUID, comment: str) -> None:
    """Reject a pending review."""
    _resolve_review(ctx, review_id, "reject", comment)


def _resolve_review(
    ctx: click.Context, review_id: UUID, verb: str, comment: str | None
) -> None:
    resp = httpx.post(
        f"{_api_base(ctx)}/api/reviews/{review_id}/{verb}",
        json={"comment": comment},
        headers=_token_header(ctx),
        timeout=15.0,
    )
    if resp.status_code != 200:
        console.print(f"[red]Failed: {resp.status_code} {resp.text}[/]")
        sys.exit(1)
    console.print(f"[green]Review {review_id} {verb}d.[/]")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Print health + summary."""
    resp = httpx.get(f"{_api_base(ctx)}/health", timeout=5.0)
    console.print(f"API: {resp.json()}")


@cli.command()
@click.pass_context
def digest(ctx: click.Context) -> None:
    """Request a checkpoint digest from Team Lead. (Iteration 1+)"""
    console.print("[yellow]Not yet implemented (Iteration 1).[/]")


if __name__ == "__main__":
    cli()
