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
        depth: Literal["quick", "standard", "deep"] = "quick",
    ) -> None:
        self._llm = llm
        self._search = search
        self._depth = depth

    async def run(
        self, idea: str, frozen_timestamp: datetime | None = None
    ) -> ReportBundle:
        idea_input = parse_input.run(idea, depth=self._depth, created_at=frozen_timestamp)
        competitors = await competitor_search.run(idea_input, self._search)
        market = await market_estimate.run(idea_input, self._llm)
        risks = await risk_analysis.run(idea_input, self._llm)
        diffs = await differentiator_analysis.run(idea_input, self._llm)
        score = scoring.run(competitors, market, risks, diffs)
        report_md = report_writer.run(idea_input, competitors, market, risks, diffs, score)
        return ReportBundle(
            input=idea_input,
            competitors=competitors,
            market=market,
            risks=risks,
            differentiators=diffs,
            score=score,
            report_md=report_md,
        )
