"""Stage 2: search for competitors using SearchClient."""
from __future__ import annotations

from idea_validator.models import Competitor, CompetitorList, IdeaInput
from idea_validator.search import SearchClient


async def run(idea_input: IdeaInput, search: SearchClient) -> CompetitorList:
    results = await search.search(f"competitors {idea_input.idea}", n=5)
    items = [
        Competitor(name=r.title, url=r.url, positioning=r.snippet)
        for r in results
    ]
    while len(items) < 3:
        i = len(items) + 1
        items.append(Competitor(name=f"Unknown {i}", url="https://example.com", positioning="N/A"))
    return CompetitorList(items=items[:5])
