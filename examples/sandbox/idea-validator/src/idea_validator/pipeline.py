"""Pipeline orchestrator (ADR-0021 Residual 2)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from idea_validator.llm import LLMClient
from idea_validator.models import ReportBundle
from idea_validator.search import SearchClient
from idea_validator.stages import (
    competitor_search,
    differentiator_analysis,
    market_estimate,
    parse_input,
    report_writer,
    risk_analysis,
    scoring,
)


class Pipeline:
    def __init__(
        self,
        llm: LLMClient,
        search: SearchClient,
        depth: Literal["quick", "standard", "deep"] = "standard",
        frozen_timestamp: datetime | None = None,
    ) -> None:
        self._llm = llm
        self._search = search
        self._depth = depth
        self._frozen_ts = frozen_timestamp

    async def run(self, idea: str) -> ReportBundle:
        inp = parse_input.run(idea, depth=self._depth, frozen_timestamp=self._frozen_ts)
        competitors = await competitor_search.run(inp, self._search)
        market = await market_estimate.run(inp, self._llm)
        risks = await risk_analysis.run(inp, self._llm)
        diffs = await differentiator_analysis.run(inp, self._llm)
        score = scoring.run(competitors, market, risks, diffs)
        report_md = report_writer.run(inp, competitors, market, risks, diffs, score)
        return ReportBundle(
            input=inp,
            competitors=competitors,
            market=market,
            risks=risks,
            differentiators=diffs,
            score=score,
            report_md=report_md,
        )
