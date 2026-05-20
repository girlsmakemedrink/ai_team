from __future__ import annotations

from idea_validator.models import Competitor, CompetitorList, IdeaInput
from idea_validator.search import SearchClient


async def run(idea_input: IdeaInput, search: SearchClient) -> CompetitorList:
    results = await search.search(f"{idea_input.idea} competitors alternatives", n=5)
    if len(results) < 3:
        raise ValueError(f"Search returned {len(results)} results; need at least 3")
    items = [
        Competitor(
            name=(r.title.split(" - ")[0] or r.title)[:40],
            url=r.url,  # type: ignore[arg-type]
            positioning=(r.snippet or "No description")[:120],
        )
        for r in results[:5]
    ]
    return CompetitorList(items=items)
