"""Click CLI entry-point. See ADR-0014, ADR-0019 §US-2, ADR-0021 §Residual 1."""
from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import click

from idea_validator.llm import make_llm
from idea_validator.models import (
    CompetitorList,
    DifferentiatorList,
    IdeaInput,
    MarketEstimate,
    RiskList,
    Score,
)
from idea_validator.pipeline import Pipeline
from idea_validator.search import make_search
from idea_validator.security import marker_storm

_REPORTS_DIR = "reports"

# Exit codes per ADR-0021 §Residual 1
_EXIT_OK = 0
_EXIT_PARTIAL = 1        # report written but some stages failed
_EXIT_USAGE = 2          # Click usage error
_EXIT_BAD_OUTPUT_DIR = 10
_EXIT_NO_BRAVE_KEY = 11
_EXIT_UNKNOWN_REPORT = 20
_EXIT_PIPELINE_FAILED = 21
_EXIT_MARKER_STORM = 22


@click.group()
def cli() -> None:
    """idea-validator — analyse a product idea for viability."""


@cli.command()
@click.option("--idea", required=True, help="Product idea text.")
@click.option(
    "--depth",
    type=click.Choice(["quick", "standard", "deep"]),
    default="quick",
    show_default=True,
)
@click.option(
    "--output-dir",
    default=_REPORTS_DIR,
    show_default=True,
    help="Base directory for report output.",
)
@click.option("--frozen-timestamp", default=None, hidden=True)
def analyze(idea: str, depth: str, output_dir: str, frozen_timestamp: str | None) -> None:
    """Run a full analysis on an idea."""
    # Guard: marker storm (ADR-0021 exit 22)
    if marker_storm(idea):
        click.echo("idea text contains marker storm; refusing to sanitize", err=True)
        sys.exit(_EXIT_MARKER_STORM)

    # Guard: output-dir path safety (ADR-0018 §6, exit 10)
    base = Path(output_dir).expanduser().resolve()
    home = Path.home()
    cwd = Path.cwd().resolve()
    under_home = base == home or str(base).startswith(str(home) + "/")
    under_cwd = base == cwd or str(base).startswith(str(cwd) + "/")
    if ".." in base.parts or (not under_home and not under_cwd):
        click.echo(
            f"invalid output directory: {base} is not under $HOME or cwd", err=True
        )
        sys.exit(_EXIT_BAD_OUTPUT_DIR)

    ts: datetime | None = None
    if frozen_timestamp:
        ts = datetime.fromisoformat(frozen_timestamp)

    # Guard: BRAVE_API_KEY for non-quick depths (ADR-0021 exit 11)
    try:
        search = make_search(depth)
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        sys.exit(_EXIT_NO_BRAVE_KEY)

    tier = "haiku" if depth == "quick" else "sonnet"
    llm = make_llm(tier)  # type: ignore[arg-type]
    pipeline = Pipeline(llm=llm, search=search, depth=depth)  # type: ignore[arg-type]

    bundle = asyncio.run(pipeline.run(idea, frozen_timestamp=ts))

    import re

    slug = re.sub(r"[^a-z0-9]+", "-", idea.lower())[:40].strip("-")
    stamp = (ts or datetime.utcnow()).strftime("%Y%m%dT%H%M%SZ")
    report_dir = base / f"{slug}-{stamp}"
    bundle.write_to_dir(report_dir)
    click.echo(f"Report written to {report_dir}")


@cli.command("list-reports")
@click.option("--dir", "reports_dir", default=_REPORTS_DIR, show_default=True)
def list_reports(reports_dir: str) -> None:
    """List all reports in the output directory."""
    base = Path(reports_dir)
    if not base.exists():
        click.echo("(no reports found)")
        return
    dirs = sorted(d for d in base.iterdir() if d.is_dir())
    if not dirs:
        click.echo("(no reports found)")
        return
    for d in dirs:
        click.echo(d.name)


@cli.command()
@click.argument("report_id")
@click.option("--dir", "reports_dir", default=_REPORTS_DIR, show_default=True)
def show(report_id: str, reports_dir: str) -> None:
    """Pretty-print a saved report."""
    report_path = Path(reports_dir) / report_id / "report.md"
    if not report_path.exists():
        click.echo(f"error: report '{report_id}' not found", err=True)
        sys.exit(_EXIT_UNKNOWN_REPORT)
    click.echo(report_path.read_text())


@cli.command()
@click.argument("id1")
@click.argument("id2")
@click.option("--dir", "reports_dir", default=_REPORTS_DIR, show_default=True)
def compare(id1: str, id2: str, reports_dir: str) -> None:
    """Compare two saved reports sequentially."""
    base = Path(reports_dir)
    for rid in (id1, id2):
        if not (base / rid / "score.json").exists():
            click.echo(f"error: report '{rid}' not found", err=True)
            sys.exit(_EXIT_UNKNOWN_REPORT)

    s1 = json.loads((base / id1 / "score.json").read_text())
    s2 = json.loads((base / id2 / "score.json").read_text())
    i1 = json.loads((base / id1 / "input.json").read_text())
    i2 = json.loads((base / id2 / "input.json").read_text())

    col = 38
    click.echo(f"{'Field':<20} {id1[:col]:<{col}} {id2[:col]:<{col}}")
    click.echo("-" * (20 + col * 2 + 2))
    click.echo(
        f"{'idea':<20} {str(i1.get('idea', ''))[:col]:<{col}} "
        f"{str(i2.get('idea', ''))[:col]:<{col}}"
    )
    click.echo(
        f"{'score':<20} {str(s1.get('score', '')):<{col}} "
        f"{str(s2.get('score', '')):<{col}}"
    )
    click.echo(
        f"{'rationale':<20} {str(s1.get('rationale', ''))[:col]:<{col}} "
        f"{str(s2.get('rationale', ''))[:col]:<{col}}"
    )


@cli.command()
def schema() -> None:
    """Print JSON schemas for all output DTOs."""
    schemas = {
        "IdeaInput": IdeaInput.model_json_schema(),
        "CompetitorList": CompetitorList.model_json_schema(),
        "MarketEstimate": MarketEstimate.model_json_schema(),
        "RiskList": RiskList.model_json_schema(),
        "DifferentiatorList": DifferentiatorList.model_json_schema(),
        "Score": Score.model_json_schema(),
    }
    click.echo(json.dumps(schemas, indent=2))
