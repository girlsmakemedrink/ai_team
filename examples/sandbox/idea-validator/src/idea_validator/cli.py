"""CLI entry point — thin Click adapter (ADR-0019 US-2, ADR-0021)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import click

from idea_validator.llm import LLMClient, make_llm
from idea_validator.models import ReportBundle
from idea_validator.pipeline import Pipeline
from idea_validator.search import SearchClient, make_search

_SLUG_RE = re.compile(r"[^a-z0-9-]+")


def _resolve_output_dir(value: str) -> Path:
    p = Path(value).expanduser().resolve()
    for allowed in (Path.home().resolve(), Path.cwd().resolve()):
        try:
            p.relative_to(allowed)
            return p
        except ValueError:
            pass
    raise click.ClickException("invalid output directory")


@click.group()
def cli() -> None:
    pass


@cli.command()
@click.option("--idea", required=True, help="Product idea to analyse")
@click.option("--depth", type=click.Choice(["quick", "standard", "deep"]), default="standard")
@click.option("--output-dir", default="reports")
@click.option("--frozen-timestamp", default=None, hidden=True)
def analyze(idea: str, depth: str, output_dir: str, frozen_timestamp: str | None) -> None:
    from idea_validator.security import sanitize
    try:
        sanitize(idea)
    except ValueError as exc:
        click.echo(str(exc), err=True)
        sys.exit(22)

    if depth != "quick" and not os.environ.get("BRAVE_API_KEY"):
        click.echo("BRAVE_API_KEY not set; use --depth quick for offline runs", err=True)
        sys.exit(11)

    try:
        out_path = _resolve_output_dir(output_dir)
    except click.ClickException:
        click.echo("invalid output directory", err=True)
        sys.exit(10)

    ft: datetime | None = None
    if frozen_timestamp:
        ft = datetime.fromisoformat(frozen_timestamp)

    try:
        llm = make_llm("haiku" if depth == "quick" else "sonnet")
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        sys.exit(21)

    search = make_search(depth)
    pipe = Pipeline(llm=llm, search=search, depth=depth, frozen_timestamp=ft)
    bundle: ReportBundle = asyncio.run(pipe.run(idea))

    slug = bundle.input.slug or _SLUG_RE.sub("-", idea.lower()).strip("-")[:40]
    ts = (bundle.input.created_at or datetime.now(timezone.utc).isoformat())[:19].replace(":", "")
    report_dir = out_path / f"{slug}-{ts}"
    bundle.write_to_dir(report_dir)
    click.echo(f"Report written to {report_dir}")


@cli.command("list-reports")
@click.option("--dir", "reports_dir", default="reports")
def list_reports(reports_dir: str) -> None:
    p = Path(reports_dir)
    if not p.exists():
        click.echo("No reports found.")
        return
    dirs = sorted(
        (d for d in p.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for d in dirs:
        click.echo(d.name)


@cli.command()
@click.argument("report_id")
@click.option("--dir", "reports_dir", default="reports")
def show(report_id: str, reports_dir: str) -> None:
    p = Path(reports_dir) / report_id
    if not p.exists():
        click.echo(f"Report '{report_id}' not found.", err=True)
        sys.exit(20)
    rfile = p / "report.md"
    click.echo(rfile.read_text() if rfile.exists() else "(no report.md)")


@cli.command()
@click.argument("id1")
@click.argument("id2")
@click.option("--dir", "reports_dir", default="reports")
def compare(id1: str, id2: str, reports_dir: str) -> None:
    base = Path(reports_dir)
    for rid in (id1, id2):
        if not (base / rid).exists():
            click.echo(f"Report '{rid}' not found.", err=True)
            sys.exit(20)
    if id1 == id2:
        click.echo("No meaningful diff (same report).")
        return
    for rid in (id1, id2):
        sf = base / rid / "score.json"
        sc = json.loads(sf.read_text()).get("score", "?") if sf.exists() else "?"
        click.echo(f"=== {rid} ===\nScore: {sc}")


@cli.command()
def schema() -> None:
    from idea_validator.models import (
        CompetitorList, DifferentiatorList, IdeaInput,
        MarketEstimate, ReportBundle, RiskList, Score,
    )
    for dto in (IdeaInput, CompetitorList, MarketEstimate, RiskList, DifferentiatorList, Score, ReportBundle):
        click.echo(f"# {dto.__name__}")
        click.echo(json.dumps(dto.model_json_schema(), indent=2))
        click.echo()
